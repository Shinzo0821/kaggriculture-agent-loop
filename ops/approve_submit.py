#!/usr/bin/env python
"""承認提出（計画 §3-A）: 「別の型の LB 計測」目的の提出を**人が**承認して実行する。

夜間セッションは `ops/preflight_submit.py --reason measure --do` でキューに積むだけで、
提出はしない。人がこのスクリプトを実行して初めて提出される。

昇格（`--reason promote`）は原則このスクリプトを通さず自動提出だが、**2 つだけ例外**があり
どちらもここに来る（2026-09-06）:
  - 枠切れ（当日 5 本 / auto_daily_cap 到達）で保留された promote。捨てると痕跡なく消えるため
  - 一度キューに載った世代は、以後 preflight の自動提出経路が拒否する（却下の無視を防ぐ）
再実行時の `--reason` は**キューに積まれた時のもの**を使う。promote を measure に落とすと
preflight のレビュー記録チェック（find_review_record）が外れるため。

usage:
  .venv/bin/python ops/approve_submit.py --list          # 承認待ちを見る
  .venv/bin/python ops/approve_submit.py gen0024         # 承認して提出する
  .venv/bin/python ops/approve_submit.py --reject gen0024 --why "強帯資金が動いていない"

安全側の設計:
- 提出そのものは preflight_submit.py を `--approved --do` で**再実行**して行う。
  ロック・提出枠・プール SHA・候補 SHA・静的検査は承認時にもう一度ぜんぶ通る（時間が経って
  条件が変わっている可能性があるため、キューの記録を信用しない）。
- 夜間セッション（環境変数 KAGG_NIGHTLY=1）と非対話実行（TTY なし）を拒否する。

**この 2 つは「うっかり」を止めるガードレールであって、セキュリティ境界ではない。**
夜間セッションは原理上 `env -u KAGG_NIGHTLY` などで回避できる。回避しないことは
`ops/NIGHTLY.md` の制約（規約）で担保している。本当に止めたい時は `control/SUBMIT.lock`
を置くこと（こちらは preflight が提出直前にも再確認する）。
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preflight_submit import (queue_path, queue_state, append_queue_event,  # noqa: E402
                              queue_lock, rel)


def load_policy():
    return json.loads((ROOT / "control/submission_policy.json").read_text())


def pending(policy):
    """承認待ち（最新イベントが queued）の一覧を古い順で返す。"""
    st = queue_state(queue_path(policy))
    return sorted([e for e in st.values() if e.get("event") == "queued"], key=lambda e: e.get("ts", ""))


def age_days(ts):
    try:
        t = dt.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.timezone.utc)
    return (dt.datetime.now(dt.timezone.utc) - t).days


def fail_approval(msg):
    sys.exit(f"NO-GO: {msg}")


def resolve_recheck(st, cli_recheck, echo=print):
    """preflight に渡す `--recheck ...` を決める（2026-09-06）。

    too_good で要求した再評価 JSON はキュー登録時に記録してある。CLI 指定があればそれを
    優先し、無ければキューの値を使う。**検証は preflight が毎回やり直す**
    （seed_base が本評価と別・シード数が同じ・rating_delta >= 0・マージン差 > 0）ので、
    キューの値を信用したことにはならない。
    **SHA が合わない・ファイルが無い・SHA が記録されていない場合は fail-closed**
    （本評価 JSON が SHA 不一致で拒否されるのと揃える。codex P1-1）。
    人が `--recheck` を明示した時だけ、差し替えの意思表示として通す。
    """
    if cli_recheck:
        # 人が明示的に別ファイルを指すのは差し替えの意思表示なので通す。
        # 中身は preflight の check_recheck() が必ず検証する。
        return ["--recheck", cli_recheck]
    recheck = st.get("recheck")
    if not recheck:
        return []
    sha = st.get("recheck_sha256")
    if not sha:
        # SHA を残す前に積まれた古いキュー。証跡が無いので人に渡させる。
        fail_approval(f"キューの {recheck} に SHA が記録されていない（古いキュー）。"
                      "--recheck で明示的に渡し直すこと")
    rp = Path(recheck)
    if not rp.is_absolute():
        rp = ROOT / rp
    # 2026-09-06(codex P1-1): **fail-closed**。本評価 JSON は SHA 不一致で拒否している
    # （preflight の「キュー登録時と評価 JSON が変わっている」）のに、too_good の必須証跡である
    # 再評価 JSON だけ警告で通すのは整合しない。差し替え後が偶然「別の有効な再評価」でも、
    # **人がキュー登録時に確認したものとは別物**なので通さない。
    if not rp.exists():
        fail_approval(f"キューが指す再評価 JSON が見つからない: {recheck}。"
                      "--recheck で明示的に渡し直すこと")
    now = hashlib.sha256(rp.read_bytes()).hexdigest()
    if now != sha:
        fail_approval(f"キュー登録後に {recheck} が変わっている"
                      f"（積んだ時 {sha[:12]} → 今 {now[:12]}）。"
                      "中身を確認して --recheck で明示的に渡し直すこと")
    return ["--recheck", recheck]


def approve_cmd(e, tty=None):
    """この項目をそのまま提出できるコマンド文字列。

    2026-09-06: 承認が 2 段階で失敗する（まず --force-no-tty、次に --recheck）ため、
    「必要な引数を全部つけた 1 行」をここで組み立てて表示する。人が試行錯誤しない。
    """
    if tty is None:
        tty = sys.stdin.isatty()
    argv = [".venv/bin/python", "ops/approve_submit.py", str(e.get("gen", ""))]
    if e.get("too_good") and not e.get("recheck"):
        # シェルのリダイレクト記号にならないトークンにする（codex P2-1）
        argv += ["--recheck", "RECHECK_JSON(別 seed-base・本評価と同じシード数)"]
    if not tty:
        argv.append("--force-no-tty")
    return shlex.join(argv)


def describe(e, ttl):
    a = age_days(e.get("ts"))
    stale = " ⚠TTL超過" if (a is not None and ttl and a > ttl) else ""
    md = e.get("money_delta_paired") or {}
    kind = e.get("reason") or "measure"
    if e.get("over_quota"):
        kind += f" ⚠枠切れで保留: {e['over_quota']}"
    tg = ""
    if e.get("too_good"):
        tg = f"\n    ⚠ too_good: {e['too_good']}"
        tg += (f"\n      再評価 JSON はキューに記録済み: {e['recheck']}（承認時に自動で渡す）"
               if e.get("recheck") else
               "\n      ⚠ 再評価 JSON がキューに無い。--recheck で渡すこと")
    return (f"- {e['gen']}  ({e.get('ts')}, {a}日前{stale})  [{kind}]\n"
            f"    理由: {e.get('note') or '(なし)'}\n"
            f"    eval: {e.get('eval')}  gate.pass={e.get('gate_pass')}  "
            f"rating_delta={e.get('rating_delta')}\n"
            f"    資金差(対応付き): {md.get('mean')} CI {md.get('ci95')}  "
            f"／ 強帯: {e.get('strong_money_delta_paired')}"
            + tg
            + f"\n    → 承認: {approve_cmd(e)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gen", nargs="?", help="承認して提出する世代 (例: gen0024)")
    ap.add_argument("--list", action="store_true", help="承認待ちの一覧を表示して終了")
    ap.add_argument("--reject", metavar="GEN", help="この世代を却下してキューから外す")
    ap.add_argument("--why", default="", help="--reject の理由(記録に残る)")
    ap.add_argument("--recheck", help="too_good フラグ時に preflight へ渡す再評価 JSON")
    ap.add_argument("--late-override", action="store_true", help="探索期間終了後も提出する")
    ap.add_argument("--force-no-tty", action="store_true",
                    help="対話端末以外から承認する(人が自分のスクリプトから呼ぶ場合のみ)")
    args = ap.parse_args()

    if os.environ.get("KAGG_NIGHTLY") == "1":
        sys.exit("NO-GO: 夜間セッションからは承認できない。承認は人が自分の端末で実行する")
    if (args.gen or args.reject) and not (sys.stdin.isatty() or args.force_no_tty):
        # 2026-09-06: 「何を足せばよいか」を必ず 1 行で出す。旧メッセージは
        # --force-no-tty の名前しか出さないので、再実行してから今度は --recheck で
        # 落ちる、という 2 段階の試行錯誤になっていた。
        again = shlex.join([".venv/bin/python", "ops/approve_submit.py"]
                           + sys.argv[1:] + ["--force-no-tty"])
        sys.exit("NO-GO: 対話端末からの実行ではない。人が自分の端末で実行すること。\n"
                 f"  意図して非対話で実行するなら: {again}")

    policy = load_policy()
    ttl = policy.get("submit_reasons", {}).get("queue_ttl_days")
    qpath = queue_path(policy)
    items = pending(policy)

    if args.list or (not args.gen and not args.reject):
        if not items:
            print("承認待ちなし")
            return
        print(f"承認待ち {len(items)} 件 ({rel(qpath)}):\n")
        for e in items:
            print(describe(e, ttl))
        print("\n却下: .venv/bin/python ops/approve_submit.py --reject <gen> --why '理由'"
              + ("" if sys.stdin.isatty() else " --force-no-tty"))
        return

    if args.reject:
        # 却下の read-check-append も preflight と同じロックで囲む(codex レビュー P0-2)。
        # 囲まないと「queued を読む → 承認側が submitting に進める → 古い判断のまま
        # rejected を書いて REJECTED と表示 → 実際には提出される」が起きる。
        with queue_lock(qpath):
            st = queue_state(qpath).get(args.reject)
            if not st or st.get("event") != "queued":
                sys.exit(f"NO-GO: {args.reject} は承認待ちではない"
                         f"(現在: {st.get('event') if st else 'なし'})")
            append_queue_event(qpath, {
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "event": "rejected", "gen": args.reject, "why": args.why,
                "eval": st.get("eval"), "note": st.get("note"),
                # 「何を却下したか」を残す。preflight はこれと一致する評価での積み直しを拒む
                "eval_sha256": st.get("eval_sha256"),
            })
        print(f"REJECTED: {args.reject}（{args.why or '理由未記入'}）")
        return

    st = queue_state(qpath).get(args.gen)
    if not st or st.get("event") != "queued":
        sys.exit(f"NO-GO: {args.gen} は承認待ちではない(現在: {st.get('event') if st else 'なし'})")
    a = age_days(st.get("ts"))
    if ttl and a is not None and a > ttl:
        print(f"⚠ キュー登録から {a} 日経過（TTL {ttl} 日）。評価が古い可能性がある")

    print(describe(st, ttl))
    print("\n上記を提出します。preflight を --approved --do で再実行します…\n")
    # 積まれた時の reason で再実行する。枠切れで積まれた promote を measure に落とすと
    # レビュー記録の必須チェックが外れてしまうため(preflight の find_review_record)。
    # 既定値で補わない: preflight 側が「キューの reason と --reason の一致」を承認条件に
    # しているので、ここで測って埋めると承認境界が fail-open になる(codex レビュー P0-2)。
    reason = st.get("reason")
    if reason not in ("promote", "measure"):
        sys.exit(f"NO-GO: キューの reason が不正: {reason!r}。積み直すこと")
    cmd = [str(ROOT / ".venv/bin/python"), str(ROOT / "ops/preflight_submit.py"),
           "--gen", args.gen, "--eval", st["eval"], "--reason", reason,
           "--note", st.get("note") or "", "--approved", "--do"]
    cmd += resolve_recheck(st, args.recheck)
    if args.late_override:
        cmd.append("--late-override")
    env = {k: v for k, v in os.environ.items() if k != "KAGG_NIGHTLY"}
    rc = subprocess.run(cmd, cwd=ROOT, env=env).returncode
    sys.exit(rc)


if __name__ == "__main__":
    main()
