"""評価キューの回帰テスト（2026-09-20 の FIX0037 と codex レビューで作った）。

    .venv/bin/python ops/test_eval_queue.py

守りたい性質は 2 つ:
  1. **積んだジョブが黙って消えない**（同秒衝突・同じ `--out` の衝突）
  2. **中断したジョブが黙って嘘をつかない**（`running` のまま滞留しない／
     前回の評価 JSON を今回の結果として `done` に畳まない／同じ `--out` に 2 プロセスが書かない）

本物の評価は走らせない。**テスト用の一時ディレクトリに `ops/eval_queue.py` を複製**し、
`harness/evaluate.py` を「n 秒寝てから out を書く」スタブに差し替えて CLI として叩く
（`eval_queue.py` は `ROOT = ops/ の親` なので、複製先がそのままテスト用のリポジトリになる）。
**実リポジトリの `state/eval_queue/` と `records/` には一切触れない。**
"""
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PYBIN = str(ROOT / ".venv/bin/python")

STUB_EVALUATE = """import sys, os, time, json, pathlib
time.sleep(float(os.environ.get("STUB_SLEEP", "0")))
out = sys.argv[sys.argv.index('--out') + 1]
pathlib.Path(out).write_text(json.dumps({'gate': {'pass': True}}))
"""

results = []


def check(ok, label):
    print(("PASS " if ok else "FAIL ") + label)
    results.append(bool(ok))


def dead_pid():
    """確実に存在しない PID を探す。"""
    pid = 999999
    while True:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:
            pass
        pid -= 1


def alive(pid):
    return subprocess.run(["ps", "-p", str(pid)], capture_output=True).returncode == 0


class Sandbox:
    """テスト用のミニリポジトリ。"""

    def __init__(self, tmp):
        # macOS の /var → /private/var があるので resolve しておく
        # （`eval_queue.py` の ROOT は resolve 済みで、渡すパスが未解決だと
        #  `log.relative_to(ROOT)` が落ちる。テスト環境だけの問題）。
        self.root = pathlib.Path(tmp).resolve()
        (self.root / "ops").mkdir()
        (self.root / "harness").mkdir()
        (self.root / "records").mkdir()
        (self.root / "agents/gen9999").mkdir(parents=True)
        (self.root / ".venv/bin").mkdir(parents=True)
        shutil.copy(ROOT / "ops/eval_queue.py", self.root / "ops/eval_queue.py")
        (self.root / "harness/evaluate.py").write_text(STUB_EVALUATE)
        (self.root / "agents/gen9999/main.py").write_text("# stub\n")
        (self.root / ".venv/bin/python").symlink_to(PYBIN)
        self.q = self.root / "state/eval_queue"

    def cli(self, *args, sleep="0", **kw):
        env = {**os.environ, "STUB_SLEEP": sleep}
        return subprocess.run([PYBIN, "ops/eval_queue.py", *args], cwd=self.root,
                              capture_output=True, text=True, env=env, **kw)

    def spawn(self, *args, sleep="0"):
        env = {**os.environ, "STUB_SLEEP": sleep}
        return subprocess.Popen([PYBIN, "ops/eval_queue.py", *args], cwd=self.root,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)

    def submit(self, out=None, gen="gen9999"):
        extra = ["--out", out] if out else []
        return self.cli("submit", "--gen", gen, "--candidate", "agents/gen9999/main.py", *extra)

    def names(self):
        return sorted(p.name for p in self.q.glob("*.json"))

    def read(self, name):
        return json.loads((self.q / name).read_text())

    def write(self, name, **kw):
        j = self.read(name)
        j.update(kw)
        (self.q / name).write_text(json.dumps(j, indent=1, ensure_ascii=False))
        return j

    def drop(self, name, *keys):
        j = self.read(name)
        for k in keys:
            j.pop(k, None)
        (self.q / name).write_text(json.dumps(j, indent=1, ensure_ascii=False))
        return j


def case_submit_collision(sb):
    """FIX0037: 同じ秒に同じ世代を 2 本積んでも、どちらも消えない。"""
    while time.time() % 1 > 0.3:    # 秒の頭で 2 連射して同じ stamp に入れる
        pass
    sb.submit("records/a.json")
    sb.submit("records/b.json")
    names = sb.names()
    check(len(names) == 2, f"同秒に積んだ 2 本が両方残る（{len(names)} 本）")
    outs = [sb.read(n)["out"] for n in names]
    check(outs == ["records/a.json", "records/b.json"],
          f"名前順 = 積んだ順（FIFO が保たれる）: {outs}")
    nxt = sb.cli("next").stdout.strip()
    check(nxt.endswith(names[0]), "next は古い方を返す")


def case_duplicate_out(sb):
    """同じ `--out` を指す未完了ジョブは拒む（ジョブを分けても結果が上書きされるため）。"""
    r = sb.submit("records/a.json")
    check(r.returncode != 0 and "同じ出力先" in (r.stdout + r.stderr),
          "同じ out の pending がある submit は NO-GO")
    n_before = len(sb.names())
    r = sb.submit()                                   # 既定 out = records/eval_gen9999.json
    r2 = sb.submit()                                  # 同じ既定 out の 2 本目
    check(r.returncode == 0 and r2.returncode != 0,
          "既定 out どうしの衝突も拒む（同じ世代を 2 回積んだとき）")
    for extra in sb.names()[n_before:]:               # 片付け
        (sb.q / extra).unlink()


def case_stale_old_output(sb):
    """**最も高くつく事故**: 前回の評価 JSON を今回の結果として done に畳まない。"""
    a = sb.names()[0]
    (sb.root / "records/a.json").write_text('{"gate": {"pass": true}, "note": "前回の評価"}')
    st = (sb.root / "records/a.json").stat()
    sb.write(a, status="running", pid=dead_pid(), started_at="2026-01-01T00:00:00+00:00",
             out_before={"mtime_ns": st.st_mtime_ns, "size": st.st_size})
    sb.cli("next")
    j = sb.read(a)
    check(j["status"] == "pending",
          f"実行前から在った JSON は done に畳まず積み直す（status={j['status']}）")
    check(json.loads((sb.root / "records/a.json").read_text())["note"] == "前回の評価",
          "回収は出力ファイルを壊さない")

    sb.write(a, status="running", pid=dead_pid(), out_before={"mtime_ns": 1, "size": 1})
    sb.cli("next")
    check(sb.read(a)["status"] == "done", "今回の実行が書いた出力なら done に畳む")

    sb.drop(a, "out_before", "recovered")
    sb.write(a, status="running", pid=dead_pid())
    sb.cli("next")
    check(sb.read(a)["status"] == "pending", "out_before が無い旧形式は畳まず積み直す（安全側）")


def case_legacy_running(sb):
    """旧コードが書いた `running`（pid 未記録）には触らない ＝ 判定不能は「生きている」側。"""
    a = sb.names()[0]
    sb.write(a, status="running")
    sb.drop(a, "pid", "eval_pid")
    nxt = sb.cli("next").stdout.strip()
    check(sb.read(a)["status"] == "running" and not nxt.endswith(a),
          "pid 未記録の running を next が奪わない")
    r = sb.cli("run", str(sb.q / a))
    check(r.returncode != 0 and "pid 未記録" in (r.stdout + r.stderr),
          "pid 未記録の running は run も拒む（--force が要る）")


def case_double_run(sb):
    """同じジョブを 2 つの run が拾って、同じ `--out` に 2 プロセスが書かない。"""
    a = sb.names()[0]
    sb.write(a, status="pending")
    sb.drop(a, "pid", "eval_pid", "out_before")
    (sb.root / "records/a.json").unlink(missing_ok=True)
    p1 = sb.spawn("run", str(sb.q / a), sleep="6")
    time.sleep(2.0)
    r2 = sb.cli("run", str(sb.q / a))
    check(r2.returncode != 0 and "ロック保持" in (r2.stdout + r2.stderr),
          "実行中のジョブを 2 本目の run が拒まれる")
    check(isinstance(sb.read(a).get("eval_pid"), int), "評価子の PID を記録している")
    nxt = sb.cli("next").stdout.strip()
    check(not nxt.endswith(a) and sb.read(a)["status"] == "running",
          "実行中のジョブを next が奪わない（他の pending は返してよい）")
    p1.wait()
    check(p1.returncode == 0 and sb.read(a)["status"] == "done", "正常終了で done になる")


def case_runner_killed(sb):
    """runner だけ SIGKILL され `eval_pid` を書く前だったときも、評価子が生きていれば再投入しない。"""
    a = sb.names()[0]
    sb.write(a, status="pending")
    sb.drop(a, "pid", "eval_pid", "out_before", "attempts", "rc", "minutes")
    (sb.root / "records/a.json").unlink(missing_ok=True)
    p1 = sb.spawn("run", str(sb.q / a), sleep="10")
    time.sleep(2.0)
    child = sb.read(a).get("eval_pid")
    if not isinstance(child, int):
        check(False, "（前提が崩れた）評価子の PID が記録されていない")
        p1.kill()
        return
    sb.drop(a, "eval_pid")                 # 「eval_pid を書く前に死んだ」状態を作る
    os.kill(p1.pid, signal.SIGKILL)
    p1.wait()
    check(alive(child), "（前提）runner を殺しても評価子は生き残る")
    sb.cli("next")
    check(sb.read(a)["status"] == "running",
          "評価子が継承したロックで、next が二重起動しない")
    r = sb.cli("run", str(sb.q / a), "--force")
    check(r.returncode != 0, "--force でも保持中のロックは迂回できない")
    os.kill(child, signal.SIGKILL)
    time.sleep(0.3)
    nxt = sb.cli("next").stdout.strip()
    check(sb.read(a)["status"] == "pending" and nxt.endswith(a),
          "評価子も死ねば pending に戻って拾い直される")
    check(len(sb.read(a).get("attempts", [])) >= 1, "再実行の履歴が attempts に残る")


def case_no_temp_files(sb):
    """更新は tmp → os.replace。ゴミも、`*.json` に混ざるファイルも残さない。"""
    check(not list(sb.q.glob("*.tmp")), "一時ファイルが残らない")
    check(all(p.suffix in (".json", ".log", ".lock") for p in sb.q.iterdir()),
          f"キューに未知の拡張子が無い: {sorted(p.suffix for p in sb.q.iterdir())}")


def main():
    print("評価キューの回帰テスト（実リポジトリの state/eval_queue と records には触らない）\n")
    with tempfile.TemporaryDirectory() as tmp:
        sb = Sandbox(tmp)
        for fn in (case_submit_collision, case_duplicate_out, case_stale_old_output,
                   case_legacy_running, case_double_run, case_runner_killed,
                   case_no_temp_files):
            print(f"--- {fn.__doc__.splitlines()[0]}")
            fn(sb)
    print()
    print(f"実行 {len(results)} ケース / 落ち {results.count(False)} 件")
    print("全て PASS" if all(results) else "落ちたケースあり")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
