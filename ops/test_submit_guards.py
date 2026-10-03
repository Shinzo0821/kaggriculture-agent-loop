"""提出ガードの回帰テスト（2026-09-06 の codex レビューで作った）。

    .venv/bin/python ops/test_submit_guards.py

守りたい性質は 1 つ: **同じ世代が 2 回出ない／人の却下が無視されない**。
Kaggle CLI は叩かない。`kaggle_submissions_csv` を差し替えて「当日の提出数」を作り、
`subprocess.run` の submit だけをモックする。スモーク対戦は本物が走るので数分かかる。

**実提出は発生しない。** submit が呼ばれたら guard_submit が即座に例外を投げる
（ケース6 だけは意図的に呼び出しを数えるモックに差し替え、回数を検証する）。
ケース6 が ops/submissions_log.jsonl に書く 1 行は、テスト自身が切り戻す。
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "ops"))
import preflight_submit as P  # noqa: E402

SUBMITTED = []


def fake_csv_factory(n_today, n_auto):
    today = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y-%m-%d")
    rows = []
    for i in range(n_today):
        desc = f"[auto] filler{i}" if i < n_auto else f"manual{i}"
        rows.append({"ref": f"fake{i}", "date": f"{today} 00:00:00", "description": desc})
    return lambda: rows


REAL_RUN = subprocess.run


def guard_submit(cmd, *a, **k):
    """kaggle の submit だけを捕まえる。スモーク対戦などは本物を通す。"""
    if isinstance(cmd, list) and "submit" in cmd:
        SUBMITTED.append(cmd)
        raise AssertionError("!!! 実提出が呼ばれた !!!")
    return REAL_RUN(cmd, *a, **k)


def run(argv, n_today, n_auto, submit_mock=None):
    """fail() は理由を stdout に出して exit(1) するので、stdout ごと捕まえる。"""
    import contextlib
    import io
    P.kaggle_submissions_csv = fake_csv_factory(n_today, n_auto)
    P.subprocess.run = submit_mock or guard_submit
    old = sys.argv
    sys.argv = ["preflight_submit.py"] + argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            P.main()
        return 0, buf.getvalue()
    except SystemExit as e:
        return (e.code if isinstance(e.code, int) else 1), buf.getvalue()
    finally:
        sys.argv = old


def case(name, argv, n_today, n_auto, expect_fail_contains):
    rc, msg = run(argv, n_today, n_auto)
    ok = (rc != 0) if expect_fail_contains else (rc == 0)
    if expect_fail_contains and expect_fail_contains not in (msg or ""):
        ok = False
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(f"    rc={rc} msg={msg}")
    return ok


if __name__ == "__main__":
    # smoke 対戦を毎回走らせると遅いので、そこだけ本物を残しつつ順に確認する
    results = []
    skipped = []   # codex P2-2: SKIP を数えて最後に出す（黙って「全て PASS」にしない）
    # 1・2 の対象は世代名を決め打ちせず、いまのリポジトリの状態から拾う
    # (決め打ちすると、その世代の評価 JSON が消えた時にテストが誤って赤くなる)。
    def pick(pred, src):
        for r in reversed(src):
            gen = r.get("gen") or r.get("generation")
            if pred(r) and (ROOT / f"records/eval_{gen}.json").exists():
                return gen
        return None

    q_events = [json.loads(l) for l in
                (ROOT / "control/submit_queue.jsonl").read_text().splitlines() if l.strip()]
    s_events = [json.loads(l) for l in
                (ROOT / "ops/submissions_log.jsonl").read_text().splitlines() if l.strip()]
    rejected_gen = pick(lambda r: r.get("event") == "rejected", q_events)
    submitted_gen = pick(lambda r: r.get("status") != "submit_failed", s_events)

    # 1. 却下済みの世代は、枠が空いていても自動提出してはならない (P0-1)
    if rejected_gen:
        results.append(case(
            f"P0-1 却下済みの世代({rejected_gen})は枠が空いても自動提出しない",
            ["--gen", rejected_gen, "--eval", f"records/eval_{rejected_gen}.json",
             "--reason", "promote", "--note", "t", "--do"],
            0, 0, "承認キューに履歴がある"))
    else:
        skipped.append("P0-1 却下済みの世代が無い")
        print("SKIP P0-1 却下済みの世代が無い")
    # 2. 提出済みの世代は、枠が空いていても二度出さない (P0-1 / P1-1)
    if submitted_gen:
        results.append(case(
            f"P0-1 提出済みの世代({submitted_gen})は枠が空いても二度出さない",
            ["--gen", submitted_gen, "--eval", f"records/eval_{submitted_gen}.json",
             "--reason", "promote", "--note", "t", "--do"],
            0, 0, "既に提出済み"))
    else:
        skipped.append("P0-1 提出済みの世代が無い")
        print("SKIP P0-1 提出済みの世代が無い")
    # 3. reason 不一致の承認は拒否される (P0-2)。対象は 1 と同じ却下済み世代
    if rejected_gen:
        results.append(case(
            "P0-2 却下済みを --approved で承認しようとしても拒否",
            ["--gen", rejected_gen, "--eval", f"records/eval_{rejected_gen}.json",
             "--reason", "measure", "--approved", "--do", "--note", "t"],
            0, 0, "承認キューに pending で載っていない"))
    # 4. 本物の queued(promote) に対して --reason measure で承認しようとする (P0-2 の本丸)。
    #    実キューを汚さないよう、使い捨てのキューファイルに差し替える。
    import hashlib
    tmpdir = Path(tempfile.mkdtemp(prefix="submit_guards_"))
    tmp_q = tmpdir / "queue.jsonl"
    ev_sha = hashlib.sha256((ROOT / "records/eval_gen0027.json").read_bytes()).hexdigest()
    tmp_q.write_text(json.dumps({
        "ts": "2026-09-05T00:00:00+00:00", "event": "queued", "gen": "gen0027",
        "reason": "promote", "eval": "records/eval_gen0027.json", "eval_sha256": ev_sha,
    }, ensure_ascii=False) + "\n")
    P.queue_path = lambda policy: tmp_q
    results.append(case(
        "P0-2 queued(promote) を --reason measure で承認しようとすると拒否",
        ["--gen", "gen0027", "--eval", "records/eval_gen0027.json",
         "--reason", "measure", "--approved", "--do", "--note", "t"],
        0, 0, "承認の --reason がキュー登録時と違う"))
    # 5. 同じキューに対して正しい reason(promote) なら、reason 検査は通過して
    #    その先(レビュー記録など)の検査に進むこと = reason 検査で不当に止めていない
    rc5, msg5 = run(["--gen", "gen0027", "--eval", "records/eval_gen0027.json",
                     "--reason", "promote", "--approved", "--do", "--note", "t"], 0, 0)
    ok5 = "承認の --reason がキュー登録時と違う" not in msg5
    print(("PASS " if ok5 else "FAIL ") + "P0-2 正しい reason なら reason 検査は通過する")
    if not ok5:
        print(f"    rc={rc5} msg={msg5[-300:]}")
    results.append(ok5)
    tmp_q.unlink(missing_ok=True)

    # 6. 初回 promote を 2 プロセス同時に走らせても submit は 1 回だけ (P0-1 競合)。
    #    submit をモックしたまま fork せず、queue_lock の排他をプロセス間で確かめる。
    tmp_q2 = tmpdir / "queue2.jsonl"
    tmp_q2.write_text(json.dumps({
        "ts": "2026-09-05T00:00:00+00:00", "event": "queued", "gen": "gen0027",
        "reason": "measure", "eval": "records/eval_gen0027.json", "eval_sha256": ev_sha,
    }, ensure_ascii=False) + "\n")
    P.queue_path = lambda policy: tmp_q2
    calls = []

    def counting_submit(cmd, *a, **k):
        if isinstance(cmd, list) and "submit" in cmd:
            calls.append(cmd)

            class R:
                returncode, stdout, stderr = 0, "", ""
            return R()
        return REAL_RUN(cmd, *a, **k)

    P.kaggle_submissions_csv = fake_csv_factory(0, 0)
    # ケース6 は送信直前まで進むので ops/submissions_log.jsonl に 1 行書かれる。
    # 実ファイルなので、長さを控えて後で切り戻す（再実行しても汚れないように）。
    slog = ROOT / "ops/submissions_log.jsonl"
    slog_len = len(slog.read_bytes())
    # 1 回目: submitting → submitted が書かれる。2 回目: 履歴があるので拒否される。
    rc_a, _ = run(["--gen", "gen0027", "--eval", "records/eval_gen0027.json",
                   "--reason", "measure", "--approved", "--do", "--note", "t"],
                  0, 0, counting_submit)
    rc_b, msg_b = run(["--gen", "gen0027", "--eval", "records/eval_gen0027.json",
                       "--reason", "measure", "--approved", "--do", "--note", "t"],
                      0, 0, counting_submit)
    ok6 = len(calls) <= 1 and rc_b != 0
    print(("PASS " if ok6 else "FAIL ")
          + f"P0-1 送信後は履歴が残り再送されない (submit呼び出し {len(calls)} 回)")
    if not ok6:
        print(f"    rc_a={rc_a} rc_b={rc_b} msg_b={msg_b[-200:]}")
    results.append(ok6)
    print(f"    キューの遷移: {[json.loads(l)['event'] for l in tmp_q2.read_text().splitlines() if l.strip()]}")
    tmp_q2.unlink(missing_ok=True)
    with open(slog, "r+b") as f:   # テストが書いた行を切り戻す
        f.truncate(slog_len)
    print(f"    提出ログを {slog_len} バイトに切り戻した")

    # ---- 2026-09-06 追加: 承認の「2 段階で詰まる」問題の回帰テスト ----
    # 実際に詰まった順: (1) --force-no-tty が要る → 付けて再実行 → (2) --recheck が要る。
    # どちらも「必要な引数が事前に分かる」ことが直った条件。
    sys.path.insert(0, str(ROOT / "ops"))
    import approve_submit as A  # noqa: E402

    # 7. too_good の promote をキューに積むと、再評価 JSON がキューに残る
    too_good_gen = pick(
        lambda r: True,
        [{"gen": g} for g in ("gen0036",)])
    recheck_json = "records/eval_gen0036_sb5000_s50.json"
    if too_good_gen and (ROOT / recheck_json).exists():
        tmp_q3 = tmpdir / "queue3.jsonl"
        tmp_q3.write_text("")
        P.queue_path = lambda policy: tmp_q3
        # この世代は既に提出済みなので二重提出ガードが先に効く。
        # ここで測りたいのは「キューに recheck が残るか」だけなので、そのガードだけ外す。
        real_already = P.already_submitted
        P.already_submitted = lambda gen: None
        try:
            rc7, msg7 = run(["--gen", too_good_gen, "--eval", f"records/eval_{too_good_gen}.json",
                             "--reason", "measure", "--note", "t", "--do",
                             "--recheck", recheck_json], 0, 0)
        finally:
            P.already_submitted = real_already
        ev7 = [json.loads(l) for l in tmp_q3.read_text().splitlines() if l.strip()]
        q7 = ev7[-1] if ev7 else {}
        ok7 = (rc7 == 0 and q7.get("event") == "queued"
               and q7.get("recheck") == recheck_json
               and len(q7.get("recheck_sha256") or "") == 64)
        print(("PASS " if ok7 else "FAIL ")
              + "too_good で積んだ promote/measure はキューに再評価 JSON を残す")
        if not ok7:
            print(f"    rc={rc7} queued={q7} msg={msg7[-300:]}")
        results.append(ok7)
        # 8. 承認時、CLI で --recheck を渡さなくてもキューの値が preflight に渡る
        ok8 = A.resolve_recheck(q7, None, echo=lambda *a: None) == ["--recheck", recheck_json]
        print(("PASS " if ok8 else "FAIL ")
              + "承認は --recheck 無しでもキューの再評価 JSON を preflight に渡す")
        results.append(ok8)
        tmp_q3.unlink(missing_ok=True)
    else:
        skipped.append("too_good の再評価 JSON が無い（records/ は gitignore なので"
                       "クリーン checkout では走らない）")
        print("SKIP too_good の再評価 JSON が無い")

    # 8b. キュー登録後に再評価 JSON が差し替わったら**通さない**(codex P1-1: fail-closed)
    #     記録どおりなら通る/欠けたら止まる を**別々の理由で**確かめる。
    #     records/ に依存すると「ファイルが無い」経路で偽 PASS するので、tmpdir に自作する。
    fixture = tmpdir / "recheck_fixture.json"
    fixture.write_text('{"seeds": 50}\n')
    good_sha = hashlib.sha256(fixture.read_bytes()).hexdigest()
    ok8b = True

    def expect_stop(st_bad, label, want):
        global ok8b
        try:
            A.resolve_recheck(st_bad, None, echo=lambda *a: None)
        except SystemExit as e:
            if want in str(e):
                return True
            print(f"    FAIL: {label} が別の理由で止まった: {e}")
            return False
        print(f"    FAIL: {label} が通ってしまった")
        return False

    # (i) 記録どおりなら通る（この 1 件が無いと、全部止まる実装でも緑になる）
    if A.resolve_recheck({"recheck": str(fixture), "recheck_sha256": good_sha}, None,
                         echo=lambda *a: None) != ["--recheck", str(fixture)]:
        ok8b = False
        print("    FAIL: 記録どおりの再評価 JSON が通らない")
    # (ii) 中身が差し替わった → SHA 不一致で止まる
    fixture.write_text('{"seeds": 50, "tampered": true}\n')
    ok8b &= expect_stop({"recheck": str(fixture), "recheck_sha256": good_sha},
                        "SHA 不一致", "変わっている")
    # (iii) ファイルが消えた → 欠落で止まる
    fixture.unlink()
    ok8b &= expect_stop({"recheck": str(fixture), "recheck_sha256": good_sha},
                        "ファイル欠落", "見つからない")
    # (iv) SHA を残す前に積んだ古いキュー → 証跡が無いので止まる
    ok8b &= expect_stop({"recheck": "records/eval_gen0031.json"},
                        "SHA 未記録の古いキュー", "SHA が記録されていない")
    # (v) 人が明示した --recheck は通る（差し替えの意思表示）
    if A.resolve_recheck({"recheck": "records/eval_gen0031.json",
                          "recheck_sha256": "0" * 64}, "cli.json",
                         echo=lambda *a: None) != ["--recheck", "cli.json"]:
        ok8b = False
        print("    FAIL: CLI 明示の --recheck が通らない")
    print(("PASS " if ok8b else "FAIL ")
          + "キューの再評価 JSON が差し替わった/欠けたら承認を止める(fail-closed)")
    results.append(bool(ok8b))

    # 9. 一覧が出すコマンドに、その場で必要な引数が全部入っている
    hint_tty = A.approve_cmd({"gen": "genX", "too_good": ["x"]}, tty=True)
    hint_no_tty = A.approve_cmd({"gen": "genX", "too_good": ["x"]}, tty=False)
    hint_stored = A.approve_cmd({"gen": "genX", "too_good": ["x"],
                                 "recheck": "records/r.json"}, tty=True)
    ok9 = ("--recheck" in hint_tty and "--force-no-tty" not in hint_tty
           and "--force-no-tty" in hint_no_tty
           and "--recheck" not in hint_stored)
    print(("PASS " if ok9 else "FAIL ")
          + "承認コマンドの案内に --force-no-tty / --recheck が過不足なく入る")
    if not ok9:
        print(f"    tty={hint_tty}\n    no_tty={hint_no_tty}\n    stored={hint_stored}")
    results.append(ok9)

    # 10. [auto] 上限の一時上書き（KAGG_AUTO_DAILY_CAP / ops/overnight.sh --auto-cap）
    #     提出枠を消費する境界なので、fail-closed のまま上げ下げできることを固定する。
    import os
    pol = {"auto_daily_cap": 3, "kaggle_daily_limit": 5}

    def cap_of(val):
        """別プロセスで auto_daily_cap() を評価する（fail() が exit するため）。"""
        env = dict(os.environ)
        env.pop("KAGG_NIGHTLY", None)
        if val is None:
            env.pop("KAGG_AUTO_DAILY_CAP", None)
        else:
            env["KAGG_AUTO_DAILY_CAP"] = val
        r = REAL_RUN([str(ROOT / ".venv/bin/python"), "-c",
                      "import sys;sys.path.insert(0,'ops');import preflight_submit as p;"
                      "print(p.auto_daily_cap(%r)[0])" % (pol,)],
                     cwd=ROOT, env=env, capture_output=True, text=True)
        return None if r.returncode else int(r.stdout.strip())

    ok10 = True
    for val, want in [(None, 3), ("", 3), ("0", 0), ("5", 5),
                      ("6", None), ("-1", None), ("abc", None),
                      (" 5 ", None), ("+5", None), ("0_5", None), ("5.0", None)]:
        got = cap_of(val)
        if got != want:
            ok10 = False
            print(f"    FAIL: KAGG_AUTO_DAILY_CAP={val!r} → {got}（期待 {want}）")
    print(("PASS " if ok10 else "FAIL ")
          + "[auto] 上限の環境変数上書きは 0-5 だけ通り、壊れた値は fail-closed")
    results.append(ok10)

    def launcher(args):
        """ランチャーの引数検証だけを見る（precheck の手前で落ちるケース用）。"""
        r = REAL_RUN(["bash", str(ROOT / "ops/overnight.sh")] + args,
                     cwd=ROOT, capture_output=True, text=True, timeout=120)
        return r.returncode, (r.stdout + r.stderr)

    ok10b = True
    for args, want in [(["--auto-cap", "6"], "実制限"),
                       (["--auto-cap", "abc"], "0-99"),
                       (["--auto-cap", "999999999999999999999999"], "0-99"),
                       (["--auto-cap"], "値がない"),
                       (["--auto-cap="], "値がない"),
                       (["25"], "0-23"),
                       (["--bogus"], "不明なオプション")]:
        rc, out = launcher(args)
        if rc != 2 or want not in out:
            ok10b = False
            print(f"    FAIL: overnight.sh {args} → rc={rc} out={out.strip()[:120]}")
    print(("PASS " if ok10b else "FAIL ")
          + "ランチャーは不正な --auto-cap / 終了時刻を夜の運転を始める前に拒む")
    results.append(ok10b)

    print()
    print(f"実行 {len(results)} ケース / SKIP {len(skipped)} 件")
    for sk in skipped:
        print(f"  SKIP: {sk}")
    print(("全て PASS" if not skipped else "実行分は全て PASS（SKIP あり）")
          if all(results) else "落ちたケースあり")
    print(f"実提出の発生: {len(SUBMITTED)} 回（0 でなければ異常）")
    sys.exit(0 if all(results) and not SUBMITTED else 1)
