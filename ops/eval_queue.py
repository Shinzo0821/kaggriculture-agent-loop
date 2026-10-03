#!/usr/bin/env python
"""評価ジョブのキュー（計画 §6-A）。**LLM をポーリングに使わないための仕組み。**

これまでは夜間サイクル（`claude -p`）が `harness/evaluate.py` を自分で起動して
20-30 分待っていたため、8 サイクル中 5 サイクルが「評価の完了待ち」で消えていた。

新しい流れ:
  1. LLM サイクルは `eval_queue.py submit ...` でジョブを置いて**すぐ終わる**
  2. ランチャー(`ops/overnight.sh`)が `eval_queue.py run <job>` をバックグラウンドで実行する
  3. ランチャーは結果ファイル(`records/eval_<gen>.json`)の出現を待ってから、
     その結果が要る LLM サイクルを起動する

安全のため、実行できるコマンドは `harness/evaluate.py` に限定している
（キューのファイルは LLM が書くので、任意コマンドの実行経路にしない）。

usage:
  eval_queue.py submit --gen gen0024 --candidate agents/gen0024/main.py \
      --pool control/sparring_pool.json --baseline records/eval_gen0022.json --seeds 50 --jobs 8
  eval_queue.py next            # 最も古い pending のジョブファイルのパスを出す(無ければ空)
  eval_queue.py run <job.json>  # 実行する(ランチャー用。running→done/failed を書く)
  eval_queue.py status          # 人間向けの一覧
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QDIR = ROOT / "state/eval_queue"
ALLOWED_SCRIPT = "harness/evaluate.py"
# 出力先はリポジトリ内の records/ 配下だけに限る。キューのファイルは LLM が書くので、
# control/ や ops/ のファイルを上書きできる経路を残さない。
ALLOWED_OUT_DIR = "records"

# ジョブに書いてよい引数だけを列挙する（codex レビュー 2026-09-05 指摘3 の修正）。
# **生のコマンド配列は実行しない。** run 時にこの表からコマンドを組み立てるので、
# `--out` の重複指定・`--out=...` 形式・未知のフラグでガードを迂回できない。
ARG_SPEC = {
    "candidate": ("--candidate", str),
    "pool": ("--pool", str),
    "baseline": ("--baseline", str),
    "champion": ("--champion", str),
    "seeds": ("--seeds", int),
    "seed_base": ("--seed-base", int),
    "steps": ("--steps", int),
    "jobs": ("--jobs", int),
}


def check_out(out):
    """出力先が records/ 配下か。symlink 解決後も検査する。問題があれば理由を返す。"""
    if not out or not isinstance(out, str):
        return f"出力先が文字列でない: {out!r}"
    p = Path(out)
    if p.is_absolute() or ".." in p.parts:
        return f"出力先は相対パスで {ALLOWED_OUT_DIR}/ 配下にすること: {out}"
    if p.parts[:1] != (ALLOWED_OUT_DIR,) or len(p.parts) < 2:
        return f"出力先は {ALLOWED_OUT_DIR}/ 配下にすること: {out}"
    # symlink 経由で外に出ないこと（親ディレクトリの実体で判定する）
    base = (ROOT / ALLOWED_OUT_DIR).resolve()
    target = (ROOT / p)
    parent = target.parent
    while not parent.exists() and parent != ROOT:
        parent = parent.parent
    try:
        parent.resolve().relative_to(base)
    except ValueError:
        return f"出力先が symlink 等で {ALLOWED_OUT_DIR}/ の外を指している: {out}"
    return None


def build_cmd(job):
    """ジョブの構造化フィールドから実行コマンドを組み立てる。問題があれば (None, 理由)。"""
    args = job.get("args")
    if not isinstance(args, dict):
        return None, "job.args が無い(古い形式のジョブ)。積み直すこと"
    unknown = sorted(set(args) - set(ARG_SPEC))
    if unknown:
        return None, f"未知の引数: {unknown}"
    bad = check_out(job.get("out"))
    if bad:
        return None, bad
    if not args.get("candidate"):
        return None, "candidate が無い"
    cmd = [ALLOWED_SCRIPT]
    for key, (flag, typ) in ARG_SPEC.items():
        v = args.get(key)
        if v is None:
            continue
        if not isinstance(v, typ) or (typ is str and ("\n" in v or not v.strip())):
            return None, f"{key} の値が不正: {v!r}"
        cmd += [flag, str(v)]
    cmd += ["--out", job["out"]]
    return cmd, None


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def jobs():
    QDIR.mkdir(parents=True, exist_ok=True)
    out = []
    for p in sorted(QDIR.glob("*.json")):
        try:
            out.append((p, json.loads(p.read_text())))
        except json.JSONDecodeError:
            print(f"⚠ 壊れたジョブファイル: {p.name}", file=sys.stderr)
    return out


def write_job(path, job, exclusive=False):
    """exclusive=True なら「まだ無いときだけ」書く（O_EXCL。同秒の同時 submit でも上書きしない）。

    既存ジョブの更新は tmp → `os.replace` の**原子的な置換**にする。`open("w")` は先に
    truncate するので、書き込み中に電源断や kill が入ると空/途中の JSON が残り、
    `jobs()` の `JSONDecodeError` 経路に落ちて**そのジョブが永久に読まれなくなる**
    （ランチャーは `next 2>/dev/null` なので警告も見えない）。
    """
    body = json.dumps(job, indent=1, ensure_ascii=False) + "\n"
    if exclusive:
        with path.open("x") as f:
            f.write(body)
        return
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w") as f:
        f.write(body)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def lock_path(path):
    return path.with_name(path.stem + ".lock")


_CLAIM = []   # 取得した実行ロックの fd を保持する（GC で閉じるとロックが外れる）


def claim(path):
    """ジョブの実行権を原子的に取る（flock）。取れたら True。

    `run` の read→check→write は原子的でないので、2 つの `run` が同じ pending を
    同時に読むと両方が評価を起動し、同じ `--out` に 2 プロセスが書きうる（Codex P1-3）。
    flock は**プロセスが死ねば OS が必ず解放する**ので、kill された runner のロックは残らない。
    """
    f = lock_path(path).open("a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return False
    _CLAIM.append(f)   # 実行中ずっと開いたままにする
    return True


def claim_fd(path):
    """保持中の実行ロックの fd（無ければ None）。評価子プロセスに継承させるために使う。"""
    lp = lock_path(path)
    for f in _CLAIM:
        if Path(f.name) == lp:
            return f.fileno()
    return None


def release(path):
    """実行権を手放す（`next` が回収に使うだけ。`run` は実行中ずっと保持する）。"""
    lp = lock_path(path)
    for f in list(_CLAIM):
        if Path(f.name) == lp:
            fcntl.flock(f, fcntl.LOCK_UN)
            f.close()
            _CLAIM.remove(f)


def locked_by_other(path):
    """他のプロセスが実行ロックを握っているか。握っていれば True。"""
    lp = lock_path(path)
    if not lp.exists():
        return False
    try:
        f = lp.open("a+")
    except OSError:
        return True   # 判定できない = 生きている側に倒す
    with f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
    return False


def pid_alive(pid):
    """その PID が生きているか。PID が無い/不正なら False（判定は job_alive がまとめる）。"""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # 他ユーザーのプロセス = 生きている
    return True


def pids_alive(job):
    """記録された PID から見た生死。**自分がロックを保持している文脈ではこちらを使う**
    （`locked_by_other` は同一プロセスの別 fd でも「他人」と判定するため）。"""
    if "pid" not in job:
        return True                  # 旧コードが書いた running = 判定不能。人が確かめる
    # runner が死んでも子の evaluate.py が生き残る経路があるので両方見る（Codex P1-4）。
    return any(pid_alive(job.get(k)) for k in ("pid", "eval_pid"))


def job_alive(path, job):
    """`running` のジョブが本当に生きているか。**判定できないものは「生きている」側に倒す**
    （二重起動で同じ `--out` に 2 プロセスが書く事故を作らないため）。"""
    return pids_alive(job) or locked_by_other(path)


def out_stat(outp):
    """出力ファイルの「実行前の状態」。存在しなければ None。"""
    try:
        st = outp.stat()
    except OSError:
        return None
    return {"mtime_ns": st.st_mtime_ns, "size": st.st_size}


def out_is_fresh(job, outp):
    """その出力を **今回の実行が書いたか**。書いたと確信できるときだけ True。

    `harness/evaluate.py:518` は全試合が終わったあと**最後に一度だけ** `--out` を書く。
    よって同じ `--out` に**前回の正常な JSON** が残っていると、評価が 1 戦も終わらないうちに
    kill されても「出力が揃っている」ように見える ——それを done に畳むと
    **古い評価 JSON を昇格判定に使う**（このプロジェクトで最も高くつく失敗。Codex P1-1）。
    実行開始時に記録した mtime/size と比べ、変化していなければ「前回のもの」と判定する。
    """
    before = job.get("out_before", "unknown")
    if before == "unknown":
        return False          # 旧形式のジョブ = 判定できない → 畳まず積み直す（再実行は安全側）
    return out_stat(outp) != before


def recover_stale(path, job):
    """`running` のまま PID が消えたジョブを畳む。done に畳めたら True、pending に戻したら False。

    2026-09-19 の事故: 本体がバッテリー切れでハイバネートし、起床後に `wait_eval` が
    タイムアウトで job を kill した。`run` は正常終了時にしか done/failed を書かないので
    job は `running` のまま残り、`next` が二度と拾わなかった（人が手で戻した）。
    """
    outp = ROOT / job["out"] if job.get("out") else None
    if outp is not None and outp.exists() and out_is_fresh(job, outp):
        try:
            json.loads(outp.read_text())
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            pass          # 途中で切れた出力 = 信用しない。下で積み直す
        else:
            job.update(status="done", finished_at=now(),
                       recovered="PID 消失。出力が揃っていたので done に畳んだ")
            write_job(path, job)
            print(f"⚠ {path.name}: running のまま PID が消えていたが出力は揃っている → done",
                  file=sys.stderr)
            return True
    job.setdefault("attempts", []).append(
        {"started_at": job.get("started_at"), "pid": job.get("pid"), "requeued_at": now()})
    job.update(status="pending")
    job.pop("pid", None)
    write_job(path, job)
    print(f"⚠ {path.name}: running のまま PID が消え、今回の実行が書いた出力が無い → pending に戻す"
          f"(再実行 {len(job['attempts'])} 回目)", file=sys.stderr)
    return False


def cmd_submit(args):
    if not (ROOT / args.candidate).exists():
        sys.exit(f"NO-GO: 候補がない: {args.candidate}")
    out = args.out or f"records/eval_{args.gen}.json"
    job = {
        "gen": args.gen, "out": out, "note": args.note,
        "args": {k: v for k, v in (
            ("candidate", args.candidate), ("pool", args.pool), ("baseline", args.baseline),
            ("champion", args.champion), ("seeds", args.seeds), ("seed_base", args.seed_base),
            ("jobs", args.jobs)) if v is not None},
        "status": "pending", "requested_at": now(),
    }
    cmd, bad = build_cmd(job)
    if bad:
        sys.exit(f"NO-GO: {bad}")
    # 同じ `--out` を指す未完了ジョブがあると、ジョブファイルを分けても**結果の方が上書きされる**
    # （既定の out は `records/eval_<gen>.json` なので、同じ世代を 2 本積むと必ず衝突する。Codex P1-2）。
    for p, j in jobs():
        if j.get("out") == out and j.get("status") in ("pending", "running"):
            sys.exit(f"NO-GO: 同じ出力先を指す未完了のジョブがある: {p.name} ({j.get('status')})\n"
                     f"  → 別の出力先を `--out records/eval_<gen>_vs_<何か>.json` で指定すること")
    job["cmd_preview"] = " ".join(cmd)  # 人が読むためだけ。実行時は組み立て直す
    QDIR.mkdir(parents=True, exist_ok=True)
    # FIX0037: ID が「UTC 秒 + gen」だけだと、同じ秒に同じ世代を 2 本積んだとき 2 本目が
    # 1 本目を黙って上書きする（2026-09-20 c3 で本命の 1 本が消えた）。衝突したら連番を足す。
    # suffix は `_` にする（`.` (0x2E) < `_` (0x5F) なので名前順 = 積んだ順が保たれる）。
    stamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d_%H%M%S')
    for n in range(1, 100):
        path = QDIR / (f"{stamp}_{args.gen}.json" if n == 1 else f"{stamp}_{args.gen}_{n:02d}.json")
        try:
            write_job(path, job, exclusive=True)   # O_EXCL。同時 submit でも片方しか勝たない
            break
        except FileExistsError:
            continue
    else:
        sys.exit(f"NO-GO: ジョブ ID が 99 件衝突した: {stamp}_{args.gen}")
    print(f"QUEUED: {path.relative_to(ROOT)} → {out}")
    print("  このサイクルは評価の完了を待たずに終えること（ランチャーが実行する）")


def cmd_next(_args):
    # 標準出力に出すのはジョブのパス 1 行だけ（ランチャーが `$(... next)` で受ける）。
    # 警告は stderr へ。
    for p, j in jobs():
        st = j.get("status")
        if st == "running" and not job_alive(p, j):
            # `jobs()` のスナップショットは古いかもしれない（読んだ直後に runner が done を
            # 書き終えている等）。**ロックを取ってから読み直して再確認する**（Codex round2 P1-3）。
            if not claim(p):
                continue                      # ちょうど誰かが実行権を取った = 生きている
            try:
                j = json.loads(p.read_text())
                if j.get("status") != "running" or pids_alive(j):
                    st = j.get("status")      # 状況が変わっていた。回収しない
                elif recover_stale(p, j):
                    continue                  # done に畳んだ
                else:
                    st = "pending"            # 積み直した
            finally:
                release(p)                    # 実行するのは `run` なので手放す
        if st == "pending":
            print(p)
            return
    # 何も出力しない = pending 無し


def cmd_run(args):
    path = Path(args.job)
    if not path.is_absolute():
        path = ROOT / path
    # 実行権はロックで取る（read→check→write の競合を潰す。Codex P1-3）。
    # ロックは flock なので、握っているプロセスが死ねば OS が必ず解放する。
    # **取れない = 本当に誰かが実行中**。`--force` でも迂回させない（二重書き込みの明示的な許可になる）。
    if not claim(path):
        sys.exit(f"NO-GO: このジョブは別のプロセスが実行中(ロック保持): {path.name}")
    job = json.loads(path.read_text())   # **ロックを取ってから読む**
    if job.get("status") == "running" and pids_alive(job) and not args.force:
        why = ("旧コードが書いた running のジョブ(pid 未記録)" if "pid" not in job
               else f"pid={job.get('pid')} / eval_pid={job.get('eval_pid')} が生きている")
        sys.exit(f"NO-GO: {why}。生死を人が確かめて --force: {path.name}")
    # **ジョブに書かれたコマンド文字列は実行しない。** 構造化フィールドから組み立て直す。
    cmd, bad = build_cmd(job)
    if bad:
        job.update(status="failed", error=f"ジョブが不正: {bad}", finished_at=now())
        write_job(path, job)
        sys.exit(f"NO-GO: {bad}")
    outp = ROOT / job["out"]
    job.update(status="running", started_at=now(), pid=os.getpid(),
               out_before=out_stat(outp))   # 回収時に「今回書いた出力か」を判定するため
    job.pop("recovered", None)
    write_job(path, job)
    log = path.with_suffix(".log")
    t0 = dt.datetime.now(dt.timezone.utc)
    with log.open("w") as f:
        # ロック fd を評価子にも継承させる。**`eval_pid` を書く前に runner が殺されても**
        # 評価子が生きているかぎりロックが残り、`next` が二重起動しない（Codex round2 P1-1）。
        lfd = claim_fd(path)
        proc = subprocess.Popen([str(ROOT / ".venv/bin/python")] + cmd,
                                cwd=ROOT, stdout=f, stderr=subprocess.STDOUT,
                                pass_fds=() if lfd is None else (lfd,))
        job["eval_pid"] = proc.pid   # runner だけ死んで子が残る経路に備える
        write_job(path, job)
        rc = proc.wait()
    mins = round((dt.datetime.now(dt.timezone.utc) - t0).total_seconds() / 60, 1)
    ok = rc == 0 and outp.exists()
    job.update(status="done" if ok else "failed", rc=rc, minutes=mins, finished_at=now(),
               log=str(log.relative_to(ROOT)))
    if not ok:
        tail = log.read_text()[-400:] if log.exists() else ""
        job["error"] = f"rc={rc} out_exists={outp.exists()} tail={tail[-200:]}"
    write_job(path, job)
    print(f"{'DONE' if ok else 'FAILED'}: {job['gen']} ({mins} 分) → {job['out']}")
    sys.exit(0 if ok else 1)


def cmd_status(_args):
    js = jobs()
    if not js:
        print("評価キューは空")
        return
    for p, j in js:
        extra = f" {j.get('minutes')}分" if j.get("minutes") else ""
        if j.get("attempts"):
            extra += f" (再実行 {len(j['attempts'])} 回)"
        err = f"\n      {j['error'][:160]}" if j.get("error") else ""
        print(f"  [{j.get('status'):7}] {j.get('gen')}  {p.name}{extra}  → {j.get('out')}{err}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit", help="評価ジョブを積む(LLM サイクル用)")
    s.add_argument("--gen", required=True)
    s.add_argument("--candidate", required=True)
    s.add_argument("--pool", default="control/sparring_pool.json")
    s.add_argument("--baseline")
    s.add_argument("--champion")
    s.add_argument("--seeds", type=int, default=50)
    s.add_argument("--seed-base", type=int)
    s.add_argument("--jobs", type=int, default=8)
    s.add_argument("--out")
    s.add_argument("--note", default="")
    s.set_defaults(func=cmd_submit)
    for name, fn, helptext in (("next", cmd_next, "最も古い pending のパスを出す"),
                               ("status", cmd_status, "一覧")):
        q = sub.add_parser(name, help=helptext)
        q.set_defaults(func=fn)
    r = sub.add_parser("run", help="ジョブを実行する(ランチャー用)")
    r.add_argument("job")
    r.add_argument("--force", action="store_true",
                   help="status=running でも実行する(PID が生きていないと人が確認した時だけ)")
    r.set_defaults(func=cmd_run)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
