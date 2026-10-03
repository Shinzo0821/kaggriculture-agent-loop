#!/usr/bin/env python
"""FR-5: 提出前チェックリストの機械化。全チェック通過時のみ --do で実際に提出する。

usage:
  # 昇格した世代（gate.pass=True）→ 従来通り自動提出
  .venv/bin/python ops/preflight_submit.py --gen gen0024 --eval records/eval_gen0024.json \
      --reason promote --note "zone labor v3" --do
  # 別の型の LB 計測 → 提出せずキューに積む（人が ops/approve_submit.py で承認して初めて提出）
  .venv/bin/python ops/preflight_submit.py --gen gen0024 --eval records/eval_gen0024.json \
      --reason measure --note "3quad の LB 計測" --do

チェック内容 (CLAUDE.md / REQUIREMENTS v0.5 §7b、2026-09-05 の計画 §3-A/§2-B/§7-A):
  1. control/SUBMIT.lock が存在しない(提出直前にも再確認)
  2. 破滅回避ゲート(v2): eval JSON で エラー0 / 相手プール・レーティングが王者比 -100 以上
     (eval JSON は厳格検証: candidate完全一致・SHA-256一致・試合数・値域)
  2b. too_good フラグ(計画 §2-B): rating_delta / 資金差 / マージン差が閾値を超えたら「良すぎる=測り方の事故」を疑い、
     別 seed-base での再評価 JSON を --recheck で要求する
  3. 提出物の静的検査(ops/static_check.py: agent 束縛・標準ライブラリのみ・I/O 無し)
  4. 提出物単体でスモーク対戦が通る
  5. 当日(UTC)の実提出数 < 5 かつ [auto] 提出数 < auto_daily_cap
     (auto_daily_cap は環境変数 KAGG_AUTO_DAILY_CAP で一時上書きできる。
      ops/overnight.sh --auto-cap N が export する。Kaggle の 5 本/日は超えられない)
     (CLI出力がパースできない場合は fail-closed で NO-GO)
     **枠切れは落とさずキューへ**: 日が変われば通る種類の不合格なので、捨てると
     夜間サイクルの昇格が痕跡なく消える(2026-09-06)。提出しない点は変わらない。
  6. 探索期間内 (exploration_end_utc 前)。以降は --late-override が必要
  7. --reason による分岐:
       promote = gate.pass=True かつ EXP にレビュー記録あり → 即提出（従来の自動提出）
                 ただし 5 で枠切れなら measure と同じくキューへ積んで終了
       measure = 全チェック通過後、**提出せず** control/submit_queue.jsonl に積んで終了
     measure と「枠切れで積まれた promote」は ops/approve_submit.py <gen> が --approved を
     付けて再実行することで提出される（積まれた時の reason のまま再実行するので、
     promote のレビュー必須チェックは外れない）。通常の promote はここを通らず直接送る。
     ただし一度キューに載った世代は、以後どの経路でも自動提出しない（人の却下を無視しないため）
exit 0 = go (--do かつ提出可なら提出済み。枠切れでキューに積んだ場合も 0), exit 1 = no-go(理由を表示)
"""
import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from static_check import check_file as static_check_file  # noqa: E402

KAGGLE = ["uvx", "--from", "kaggle==2.2.4", "kaggle"]
COMP = "kaggriculture"
LOCK = ROOT / "control/SUBMIT.lock"
MIN_GAMES_PER_OPP = 40  # seeds30×両側=60 が標準。40未満の評価は統計不足として拒否
CANONICAL_POOL = "control/sparring_pool.json"  # 評価に使ってよいプールはこれだけ
KNOWN_EVENTS = {"queued", "approved", "rejected", "submitting", "submitted",
                "submit_unconfirmed", "submit_failed"}
REQUIRED_EVENT_KEYS = {"ts", "event", "gen"}
DEFAULT_QUEUE = "control/submit_queue.jsonl"


def fail(msg):
    print(f"NO-GO: {msg}")
    sys.exit(1)


def rel(path):
    """表示用の相対パス(リポジトリ外なら絶対のまま)。"""
    try:
        return str(Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def valid_rate(x):
    return isinstance(x, (int, float)) and math.isfinite(x) and 0.0 <= x <= 1.0


def kaggle_submissions_csv():
    """提出一覧CSV。パースできない場合は fail-closed。"""
    out = subprocess.run(
        KAGGLE + ["competitions", "submissions", COMP, "-v"],
        capture_output=True, text=True, timeout=120,
    )
    if out.returncode != 0:
        fail(f"kaggle submissions の取得に失敗: {out.stderr.strip()[:300]}")
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    header = [i for i, l in enumerate(lines) if l.startswith("ref,")]
    if not header:
        fail(f"submissions CSV のヘッダが見つからない(fail-closed): {out.stdout.strip()[:200]}")
    rows = list(csv.DictReader(io.StringIO("\n".join(lines[header[0]:]))))
    for r in rows:
        if not (r.get("ref") and r.get("date")):
            fail("submissions CSV に必須列(ref/date)が欠けた行がある(fail-closed)")
    return rows


def auto_daily_cap(policy):
    """今回有効な [auto] 提出上限/日(UTC)と、その出所。

    既定は control/submission_policy.json の auto_daily_cap。環境変数
    KAGG_AUTO_DAILY_CAP があればその値で上書きする(policy ファイルは書き換えない)。
    夜間ループでは ops/overnight.sh --auto-cap N がこの環境変数を export する。
    Kaggle の 1 日 5 本という実制限(kaggle_daily_limit)は上書きできない。
    値が壊れていたら fail-closed(既定に落とさない)。
    """
    base = policy["auto_daily_cap"]
    raw = os.environ.get("KAGG_AUTO_DAILY_CAP")
    if raw is None or raw == "":
        return base, None
    # int() は " 5 " / "+5" / "0_5" を 5 として受ける。壊れた値が「上限 5」として
    # 通ると自主上限が黙って上がるので、10 進数字だけを受ける(2026-09-07 codex P1-1)。
    if not re.fullmatch(r"[0-9]{1,2}", raw):
        fail(f"KAGG_AUTO_DAILY_CAP は 0-99 の 10 進整数で指定: {raw!r}")
    cap = int(raw)
    hard = policy["kaggle_daily_limit"]
    if cap > hard:
        fail(f"KAGG_AUTO_DAILY_CAP={cap} は Kaggle の実制限 {hard} を超えている")
    return cap, f"env KAGG_AUTO_DAILY_CAP={cap}(policy 既定 {base})"


def queue_path(policy):
    return ROOT / (policy.get("submit_reasons", {}).get("queue_file") or DEFAULT_QUEUE)


@contextlib.contextmanager
def queue_lock(path):
    """キューの read-check-append を排他する(codex レビュー指摘2)。

    承認と夜間サイクルが同時にキューを触ると、却下済みの世代を提出したり
    二重提出したりできてしまうため、状態を見て書くまでを 1 つのロックで囲む。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = path.with_name(path.name + ".lock")
    with open(lock_file, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def read_queue_events(path):
    """イベントを読む。**構文もスキーマも fail-closed**（壊れた行を黙って無視しない）。"""
    if not path.exists():
        return []
    out = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            fail(f"承認キューに壊れた行がある(fail-closed): {path}:{i} / {line[:80]}")
        if not isinstance(r, dict) or not REQUIRED_EVENT_KEYS <= r.keys():
            fail(f"承認キューの行に必須キー{sorted(REQUIRED_EVENT_KEYS)}が無い(fail-closed): {path}:{i}")
        if r["event"] not in KNOWN_EVENTS:
            fail(f"承認キューに未知の event がある(fail-closed): {path}:{i} / {r['event']}")
        out.append(r)
    return out


def queue_state(path):
    """世代ごとの最新イベント(append-only ログの畳み込み)。"""
    state = {}
    for e in read_queue_events(path):
        if e.get("gen"):
            state[e["gen"]] = e
    return state


def append_queue_event(path, rec):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def already_submitted(gen):
    """ops/submissions_log.jsonl に成功記録がある世代なら、その行を返す。

    枠切れの promote をキューに積めるようにした結果(2026-09-06)、承認が数日後になりうる。
    既に出した世代を積んでおくと、承認時に同じ物をもう一度出してしまうので先に弾く。"""
    p = ROOT / "ops/submissions_log.jsonl"
    if not p.exists():
        return None
    for i, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            fail(f"提出ログに壊れた行がある(fail-closed): {rel(p)}:{i}")
        # 成功ステータスを列挙しない(fail-closed)。過去ログには "COMPLETE" もあり、
        # 列挙側で書くと知らない値が「未提出」に倒れる(codex レビュー P1-1)。
        # 明示的な失敗だけを除外し、それ以外は「出した」とみなす。
        if r.get("generation") == gen and r.get("status") != "submit_failed":
            return r
    return None


def find_review_record(gen, agent_file):
    """`agents/<gen>/meta.json` の構造化 review を検証する。(ok, 説明) を返す。

    昇格(promote)提出の条件（計画 §2-A、codex レビュー指摘1 で厳格化）。
    **散文の長さでは判定しない。** レビューは次を満たすこと:
      - review.candidate_sha256 が今の main.py と一致（レビューしたコードと提出物が同一）
      - review.date が YYYY-MM-DD で未来日でない
      - review.blocking_resolved が True
      - findings が配列で、severity=fatal のものは全て resolution=fixed
      - meta.exp が指す EXP が実在し、その frontmatter の gen が一致
    """
    import re
    meta_p = ROOT / "agents" / gen / "meta.json"
    if not meta_p.exists():
        return False, f"{rel(meta_p)} が無い"
    try:
        meta = json.loads(meta_p.read_text())
    except json.JSONDecodeError:
        return False, f"{rel(meta_p)} が壊れている"
    rv = meta.get("review")
    if not isinstance(rv, dict):
        return False, (f"{rel(meta_p)} に review が無い。"
                       "knowledge/REVIEW_CHECKLIST.md の 7 観点で Codex レビューを通し、"
                       'meta.json に {"review": {"date","reviewer","candidate_sha256",'
                       '"findings":[{"severity","what","resolution"}],"blocking_resolved"}} を書くこと')
    sha_now = hashlib.sha256(agent_file.read_bytes()).hexdigest()
    if rv.get("candidate_sha256") != sha_now:
        return False, ("review.candidate_sha256 が今の main.py と一致しない"
                       "（レビュー後にコードが変わっている。レビューし直すこと）")
    d = str(rv.get("date", ""))
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        return False, f"review.date が YYYY-MM-DD でない: {d!r}"
    if d > dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d"):
        return False, f"review.date が未来日: {d}"
    if rv.get("blocking_resolved") is not True:
        return False, f"review.blocking_resolved が True でない: {rv.get('blocking_resolved')!r}"
    findings = rv.get("findings")
    if not isinstance(findings, list):
        return False, "review.findings が配列でない（指摘なしなら [] と書く）"
    for f in findings:
        if not isinstance(f, dict) or "severity" not in f:
            return False, f"review.findings の要素が不正: {str(f)[:60]}"
        if str(f.get("severity")).lower() in ("fatal", "blocking", "即死"):
            if str(f.get("resolution", "")).lower() not in ("fixed", "修正済み"):
                return False, f"即死級の指摘が未修正: {str(f.get('what'))[:60]}"

    # EXP の存在と世代の一致（別世代の EXP を流用できないようにする）
    exp_id = meta.get("exp")
    if not exp_id:
        return False, f"{rel(meta_p)} に exp が無い"
    exps = sorted((ROOT / "knowledge/experiments").glob(f"{exp_id}_*.md"))
    if not exps:
        return False, f"{exp_id} の実験記録が見つからない"
    head = exps[0].read_text()[:400]
    if f"gen: {gen}" not in head:
        return False, f"{rel(exps[0])} の frontmatter の gen が {gen} でない"
    n_fatal = sum(1 for f in findings
                  if str(f.get("severity")).lower() in ("fatal", "blocking", "即死"))
    return True, (f"{rel(meta_p)} review {d} by {rv.get('reviewer')} "
                  f"（指摘 {len(findings)} 件・うち即死級 {n_fatal} 件、全て修正済み）")


def too_good_reasons(g, policy):
    """計画 §2-B: 『良すぎる』評価は測り方の事故を疑う。該当理由のリストを返す。

    閾値が読めない/不正なときは**検査不能として理由を立てる**（fail-closed）。
    黙って「問題なし」にすると、閾値を消すだけでチェックを無効化できてしまう。"""
    tg = policy.get("too_good_flag")
    if not isinstance(tg, dict):
        return ["control/submission_policy.json に too_good_flag が無い(検査不能)"]
    reasons = []
    for key, label, val, fmt in (
            ("rating_delta_max", "rating_delta", g.get("rating_delta"), "{:+.1f}"),
            ("money_delta_mean_max", "money_delta_paired.mean",
             (g.get("money_delta_paired") or {}).get("mean"), "{:+.0f}"),
            ("margin_delta_mean_max", "margin_delta_paired.mean",
             (g.get("margin_delta_paired") or {}).get("mean"), "{:+.0f}")):
        thr = tg.get(key)
        if not (type(thr) in (int, float) and math.isfinite(thr)):
            reasons.append(f"too_good_flag.{key} が有限数でない(検査不能): {thr!r}")
            continue
        if isinstance(val, (int, float)) and math.isfinite(val) and val > thr:
            reasons.append(f"{label} {fmt.format(val)} > {thr}")
    return reasons


def check_recheck(recheck_json, ev, gen, agent_file, gate_policy):
    """too_good フラグ時に要求する再評価 JSON の検証。

    codex レビュー指摘5 の修正: **本評価とまったく同じ厳格検証(check_eval)を通す**。
    以前は候補 SHA と steps しか見ておらず、別プール・少数シード・ベースライン非互換の
    JSON でも「再現した」ことにできた。その上で「別の seed-base」「同じ方向」を要求する。"""
    rp = ROOT / recheck_json if not Path(recheck_json).is_absolute() else Path(recheck_json)
    print(f"  --recheck を検証: {rel(rp)}")
    rv = check_eval(rp, agent_file, gen, gate_policy)   # 不合格なら fail() で終了
    rsb, sb = rv.get("seed_base"), ev.get("seed_base")
    if not isinstance(rsb, int):
        fail(f"--recheck の seed_base が整数でない: {rsb!r}")
    if rsb == sb:
        fail(f"--recheck の seed_base が本評価と同じ({rsb})。別の seed-base で取り直すこと")
    if rv.get("seeds") != ev.get("seeds"):
        fail(f"--recheck のシード数 {rv.get('seeds')} が本評価 {ev.get('seeds')} と違う")
    rg = rv.get("gate") or {}
    rrd = rg.get("rating_delta")
    rmd = (rg.get("margin_delta_paired") or {}).get("mean")
    # 2026-09-05: 昇格ゲートを rating_delta >= 0 に緩めたので、ここも >= 0 に合わせる。
    # > 0 のままだと、現プールで rating が動かない世代（gen0025/gen0026 は 0.0）は
    # too_good が立った瞬間に再評価検証で必ず落ちる（ゲートは通るのに提出不能になる穴）。
    if not (type(rrd) in (int, float) and math.isfinite(rrd) and rrd >= 0):
        fail(f"--recheck の rating_delta が負({rrd}) = 本評価の改善が再現しない")
    # 資金は昇格ゲートと同じ**マージン**で見る（自分の資金だけでは削りを取りこぼす）。
    if not (type(rmd) in (int, float) and math.isfinite(rmd) and rmd > 0):
        fail(f"--recheck のマージン差平均が正でない({rmd}) = 本評価の改善が再現しない")
    print(f"  recheck OK: seed_base {rsb} で rating_delta {rrd:+.1f} / margin {rmd:+.0f}")
    return rp


def check_eval(ev_path, agent_file, gen, gate):
    """評価 JSON を厳格検証し、検証済みの dict を返す。"""
    if not ev_path.exists():
        fail(f"評価ファイルがない: {ev_path}")
    ev = json.loads(ev_path.read_text())

    # 候補の同一性: パス完全一致 + ファイル内容のSHA-256一致
    cand = ev.get("candidate")
    expect = f"agents/{gen}/main.py"
    if cand != expect:
        fail(f"評価の candidate ({cand}) が {expect} と不一致")
    sha_now = hashlib.sha256(agent_file.read_bytes()).hexdigest()
    sha_eval = ev.get("candidate_sha256")
    if not sha_eval:
        fail("評価JSONに candidate_sha256 がない(古い形式)。evaluate.py を再実行すること")
    if sha_eval != sha_now:
        fail("評価後に main.py が変更されている(SHA-256不一致)。evaluate.py を再実行すること")

    opps = ev.get("opponents")
    if not isinstance(opps, dict) or not opps:
        fail("評価JSONに opponents がない")
    for k, v in opps.items():
        n = v.get("games")
        err = v.get("error_or_timeout_games")
        if not isinstance(n, int) or n < MIN_GAMES_PER_OPP:
            fail(f"vs {k} の試合数 {n} が不足(最低{MIN_GAMES_PER_OPP})")
        if not isinstance(err, int) or err < 0:
            fail(f"vs {k} の error_or_timeout_games が不正: {err}")
        if err > gate["max_error_games"]:
            fail(f"vs {k} でエラー/タイムアウト {err} 試合 > 許容 {gate['max_error_games']}")
        if not valid_rate(v.get("win_rate")):
            fail(f"vs {k} の win_rate が不正: {v.get('win_rate')}")

    # v2 ゲート(2026-09-04, codex レビュー反映で厳格化): 自系統 H2H ではなく
    # 「相手プールに対するレーティング」で判定。JSON の値を信用せず preflight 側で再計算し、
    # ベースライン互換(プール SHA / シード / steps)と現在のプールファイル一致を必須にする。
    def finite_number(x):
        return type(x) in (int, float) and math.isfinite(x)

    g = ev.get("gate")
    pool = ev.get("pool")
    if not isinstance(g, dict) or not isinstance(pool, dict) or not ev.get("pool_file"):
        fail("評価JSONが旧形式(pool/gate なし)。evaluate.py --pool control/sparring_pool.json --baseline ... で再評価すること")
    required = {"errors_zero", "baseline", "baseline_compatible", "rating_delta", "submit_ok"}
    if not required <= g.keys():
        fail(f"gate の必須キーが不足: {sorted(required - g.keys())}")
    if ev.get("steps") != 720:
        fail(f"steps={ev.get('steps')} (720 以外の評価は提出判定に使えない)")
    # codex レビュー指摘6 の修正: 評価 JSON が自称するパスではなく、**正典のプール**と比べる。
    # 旧プールのコピーを pool_file に書けば現行プールの変更を無視できてしまうため。
    if ev["pool_file"] != CANONICAL_POOL:
        fail(f"評価のプールが {CANONICAL_POOL} でない: {ev['pool_file']}（正典のプールで再評価すること）")
    pool_file = ROOT / CANONICAL_POOL
    if not pool_file.exists():
        fail(f"プールファイルがない: {CANONICAL_POOL}")
    if hashlib.sha256(pool_file.read_bytes()).hexdigest() != ev.get("pool_sha256"):
        fail(f"評価時のプール(SHA-256)が現在の {CANONICAL_POOL} と一致しない。再評価すること")
    if pool.get("rated_opponents", 0) < gate.get("min_rated_opponents", 3):
        fail(f"レーティング付きの相手が {pool.get('rated_opponents')} 体しかない(最低 {gate.get('min_rated_opponents', 3)})")
    if not finite_number(pool.get("rating")):
        fail(f"pool.rating が有限数でない: {pool.get('rating')}(全勝/全敗で MLE 不在の可能性。プールの強さ帯を調整)")
    if g["errors_zero"] is not True:
        fail("エラー/タイムアウトのある試合が存在する")
    if not g["baseline"]:
        fail("--baseline(王者の同条件評価)なしでは提出判定できない")
    if g["baseline_compatible"] is not True:
        fail("ベースラインがプール/シード/steps で不一致(gate.baseline_compatible が真でない)")
    rd = g["rating_delta"]
    if not finite_number(rd):
        fail(f"rating_delta が有限数でない: {rd}")
    expected_submit = bool(g["errors_zero"] and rd > gate["rating_delta_min"])
    if g["submit_ok"] is not expected_submit:
        fail("evaluate.py の submit_ok と preflight の再計算が一致しない")
    if not expected_submit:
        fail(f"王者比 rating_delta {rd:+.1f} <= {gate['rating_delta_min']}(大幅劣化=破滅回避ゲート不通過)")
    print(f"gate OK: pool rating {pool.get('rating')} (±{pool.get('rating_se')}), "
          f"rating_delta {rd:+.1f}, margin_delta_paired {g.get('margin_delta_paired')}, "
          f"money_delta_paired {g.get('money_delta_paired')}, slope_delta {g.get('slope_delta')}")
    if g.get("strong_money_delta_paired") is not None or g.get("strong_slope_delta") is not None:
        print(f"  強帯(tier=strong): マージン差 {g.get('strong_margin_delta_paired')} / "
              f"資金差 {g.get('strong_money_delta_paired')} / "
              f"傾き差 {g.get('strong_slope_delta')}")
    return ev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True, help="世代名 (例: gen0002)")
    ap.add_argument("--eval", dest="eval_json", required=True)
    ap.add_argument("--reason", required=True, choices=["promote", "measure"],
                    help="promote=昇格(gate.pass+レビュー記録)で即提出 / measure=LB計測(承認キューに積む)")
    ap.add_argument("--note", default="", help="提出メッセージの補足")
    ap.add_argument("--do", action="store_true", help="チェック通過時に実際に提出する(measure は承認まで積むだけ)")
    ap.add_argument("--recheck", help="too_good フラグ時に要求する別 seed-base の再評価 JSON")
    ap.add_argument("--approved", action="store_true",
                    help="(ops/approve_submit.py 専用) 承認済み measure を実際に提出する")
    ap.add_argument("--late-override", action="store_true",
                    help="探索期間後の提出を許可(ユーザー明示指示時のみ)")
    args = ap.parse_args()

    policy = json.loads((ROOT / "control/submission_policy.json").read_text())
    agent_file = ROOT / "agents" / args.gen / "main.py"
    if not agent_file.exists():
        fail(f"{agent_file} がない")
    message = f"[auto] {args.gen}: {args.note}".strip()
    qpath = queue_path(policy)

    # 0. --approved は人の承認経路(ops/approve_submit.py)専用。夜間セッションからは使えない。
    if args.approved:
        # reason は measure(LB計測)と promote(枠切れで積まれた昇格)の両方がありうる。
        # どちらであれ「キューに queued で載っていること」が承認の実体なので下で確かめる。
        if os.environ.get("KAGG_NIGHTLY") == "1":
            fail("夜間セッション(KAGG_NIGHTLY=1)からは承認提出できない。承認は人が ops/approve_submit.py で行う")
        st = queue_state(qpath).get(args.gen)
        if not st or st.get("event") != "queued":
            fail(f"{args.gen} は承認キューに pending で載っていない(現在: {st.get('event') if st else 'なし'})")
        # 2026-09-06 の codex レビュー P0-2: reason は**キューに積まれた時のもの**と一致させる。
        # promote のキューを --reason measure で承認すると、下の find_review_record()
        # (レビュー記録の必須チェック)が丸ごと外れる。既定値で補わない(fail-closed)。
        if st.get("reason") != args.reason:
            fail(f"承認の --reason がキュー登録時と違う(キュー: {st.get('reason')!r} / 指定: {args.reason!r})。"
                 "ops/approve_submit.py <gen> を使うこと")
        ev_sha_now = hashlib.sha256((ROOT / args.eval_json).read_bytes()).hexdigest() \
            if (ROOT / args.eval_json).exists() else None
        if st.get("eval_sha256") != ev_sha_now:
            fail("キュー登録時と評価 JSON が変わっている(再評価して積み直すこと)")

    # 1. SUBMIT.lock
    if LOCK.exists():
        fail("control/SUBMIT.lock が存在(ユーザーによる提出停止中)。候補はキュー扱いとし STATUS.md に記録すること")

    # 1b. 既提出の早期打ち切り（2026-09-06）。
    # 同じ検査は「キューに積む直前」と「提出直前」にもある（時間が経って状況が変わるため）が、
    # **一番手前にも置く**。理由は 2 つ:
    #   - 既に出した世代に対して、重い評価 JSON の再検証や too_good の再評価要求が先に走り、
    #     「--recheck を渡せ」という**実行しても無駄な指示**が返っていた（実際にテストが
    #     この順序で偽陰性になった）。人にも自動化にも、まず「もう出してある」と言うのが正しい。
    # 却下済みはここで打ち切らない。却下の判定は「評価が更新されたか」を見るため
    # 評価 JSON の検証を先に通す必要があり、メッセージも既存の
    # 「承認キューに履歴がある」に一本化しておく（ops/test_submit_guards.py が固定）。
    done = already_submitted(args.gen)
    if done:
        fail(f"{args.gen} は既に提出済み({done.get('ts')}, ref={done.get('submission_id')})。"
             "二重提出しない（別の世代を出すこと）")

    # 2. 破滅回避ゲート(厳格検証)
    ev = check_eval(ROOT / args.eval_json, agent_file, args.gen, policy["submit_gate"])
    g = ev["gate"]
    cand_sha_checked = hashlib.sha256(agent_file.read_bytes()).hexdigest()

    # 2b. too_good フラグ(計画 §2-B): 良すぎる評価は測り方の事故を疑い、別 seed-base の再評価を要求
    tg = too_good_reasons(g, policy)
    recheck_rec = {}
    if tg:
        print(f"⚠ too_good フラグ: {' / '.join(tg)}")
        if not args.recheck:
            fail("too_good フラグが立っている。昇格前に (1) --seed-base を変えた再評価, "
                 "(2) harness/audit_replay.py で unfed/uncared/move%, (3) Codex レビュー の3点を済ませ、"
                 "(1) の JSON を --recheck で渡すこと")
        recheck_path = check_recheck(args.recheck, ev, args.gen, agent_file,
                                     policy["submit_gate"])
        recheck_rec = {
            "recheck": args.recheck,
            # キューの記録は信用せず承認時に検証し直すが、SHA を残しておくと
            # 「承認までの間に別物へ差し替わった」ことに気づける。
            "recheck_sha256": hashlib.sha256(recheck_path.read_bytes()).hexdigest(),
        }

    # 2c. 理由ごとの追加条件
    if args.reason == "promote":
        if g.get("pass") is not True:
            fail(f"--reason promote だが gate.pass={g.get('pass')}(昇格していない)。"
                 "別の型の LB 計測なら --reason measure(人の承認制)")
        if policy.get("submit_reasons", {}).get("promote_requires_review_record", True):
            ok, detail = find_review_record(args.gen, agent_file)
            if not ok:
                fail(f"昇格提出にはレビュー記録が必要: {detail}")
            print(f"review OK: {detail}")

    # 3. 提出物の静的検査(計画 §7-A)
    allowed = policy.get("static_check", {}).get("allowed_nonstdlib", [])
    problems = static_check_file(agent_file, allowed)
    if problems:
        fail("静的検査 NG: " + " / ".join(problems))
    print(f"static OK: {rel(agent_file)}")

    # 4. 提出物単体スモーク
    smoke = subprocess.run(
        [str(ROOT / ".venv/bin/python"), str(ROOT / "harness/run_match.py"),
         str(agent_file), "starter", "--seed", "999", "--quiet"],
        capture_output=True, text=True, timeout=300, cwd=ROOT,
    )
    if smoke.returncode != 0:
        fail(f"スモーク対戦が失敗: {smoke.stderr.strip()[:300]}")
    sm = json.loads(smoke.stdout)
    if sm["statuses"][0] != "DONE":
        fail(f"スモーク対戦で候補が異常終了: {sm['statuses']}")

    # 5. 提出枠 (UTC当日、個人の手動提出含む)
    subs = kaggle_submissions_csv()
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    todays = [s for s in subs if str(s.get("date", "")).startswith(today)]
    autos_today = [s for s in todays if str(s.get("description", "")).startswith("[auto]")]
    # 枠切れは「日が変われば通る」種類の不合格なので、候補を捨てずに承認待ちへ積む。
    # (捨てると夜間サイクルの昇格が痕跡なく消える。提出しない点は fail-closed のまま)
    # 実際に送ろうとしている時(--approved)だけ枠切れを NO-GO にする。
    quota_hits = []
    if len(todays) >= policy["kaggle_daily_limit"]:
        quota_hits.append(f"当日の実提出 {len(todays)}/{policy['kaggle_daily_limit']} で残枠なし")
    cap, cap_src = auto_daily_cap(policy)
    if cap_src:
        print(f"[auto] 上限は上書き中: {cap_src}")
    if len(autos_today) >= cap:
        quota_hits.append(f"[auto] 提出 {len(autos_today)}/{cap} で自主上限到達")
    over_quota = " / ".join(quota_hits) or None
    if over_quota and args.approved:
        fail(over_quota)

    # 6. 探索期間
    if today >= policy["exploration_end_utc"] and not args.late_override:
        fail(f"探索期間終了({policy['exploration_end_utc']})後。最終提出はユーザーと相談("
             "明示指示があるときのみ --late-override)")

    if over_quota:
        print(f"NO-GO(枠切れ): {over_quota} — 提出せず承認待ちへ積む")
    else:
        print(f"GO: 全チェック通過 (当日 {len(todays)}/{policy['kaggle_daily_limit']}, "
              f"[auto] {len(autos_today)}/{cap})")
    print(f"  message: {message}")

    # 7. 提出せずキューへ(人の承認待ち)。measure は常に、promote は枠切れの時だけ。
    #    --approved が付いている時だけ提出に進む。
    if (args.reason == "measure" or over_quota) and not args.approved:
        if not args.do:
            print("  (dry-run: --do でキューに積む)")
            return
        done = already_submitted(args.gen)
        if done:
            fail(f"{args.gen} は既に提出済み({done.get('ts')}, ref={done.get('submission_id')})。"
                 "キューに積まない(承認時の重複提出を防ぐ)")
        eval_sha = hashlib.sha256((ROOT / args.eval_json).read_bytes()).hexdigest()
        with queue_lock(qpath):
            st = queue_state(qpath).get(args.gen)
            if st and st.get("event") == "queued":
                if st.get("eval_sha256") == eval_sha:
                    print(f"  既にキュー済み({st.get('ts')})。重複登録しない")
                    return
                # 評価を取り直した場合は積み直す(古い queued を置き換える)
                print(f"  {args.gen} は評価が更新されている。キューを積み直す")
            elif st and st.get("event") in ("submitting", "submitted", "submit_unconfirmed"):
                fail(f"{args.gen} は既に提出処理に入っている(event={st['event']})。二重提出を防ぐため中止")
            elif st and st.get("event") == "rejected":
                # 人が却下した世代を毎晩積み直さない。**評価 JSON が変わっている時だけ**
                # 積み直せる(却下の理由が「評価が古い」ことがあるため、再評価は正当な再提案)。
                # SHA が違うことは再評価の証明ではない(整形し直しでも変わる)。これは
                # うっかり同じものを積み直すのを止めるガードで、提出には結局人の承認が要る。
                # eval_sha256 が記録に無い古い却下は fail-closed 側に倒す。
                if st.get("eval_sha256") in (None, eval_sha):
                    fail(f"{args.gen} は人が却下済み({st.get('ts')}: {st.get('why') or '理由未記入'})。"
                         "評価を取り直してから積み直すこと")
                print(f"  {args.gen} は却下後に評価が更新されている。積み直す")
            append_queue_event(qpath, {
                "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "event": "queued",
                "gen": args.gen,
                "reason": args.reason,
                "eval": args.eval_json,
                "eval_sha256": eval_sha,
                "candidate_sha256": cand_sha_checked,
                "note": args.note,
                "message": message,
                "rating_delta": g.get("rating_delta"),
                "margin_delta_paired": g.get("margin_delta_paired"),
                "money_delta_paired": g.get("money_delta_paired"),
                "strong_margin_delta_paired": g.get("strong_margin_delta_paired"),
                "strong_money_delta_paired": g.get("strong_money_delta_paired"),
                "gate_pass": g.get("pass"),
                "too_good": tg or None,
                "over_quota": over_quota,
                # 2026-09-06: too_good で要求した再評価 JSON をキューに残す。
                # 残さないと、承認時に preflight が再び --recheck を要求し、人が
                # 「どのファイルだったか」を思い出す必要があった（実際に詰まった）。
                # 承認側はこれを既定値として渡すだけで、検証は preflight が毎回やり直す。
                **recheck_rec,
            })
        print(f"QUEUED: {args.gen} を承認待ちに積んだ → {rel(qpath)}")
        print("  提出するには人が実行: .venv/bin/python ops/approve_submit.py " + args.gen)
        return

    if not args.do:
        print("  (dry-run: --do で提出)")
        return

    # ---- 提出直前の再確認（チェックと提出の間に状況が変わりうる） ----
    if LOCK.exists():
        fail("チェック中に control/SUBMIT.lock が作成された。提出中止")
    # codex レビュー指摘6: 検査した内容と提出物が同一であることを送信直前に確かめる
    if hashlib.sha256(agent_file.read_bytes()).hexdigest() != cand_sha_checked:
        fail("チェック中に main.py が変更された(SHA-256 不一致)。提出中止")
    # codex レビュー指摘2 ＋ 2026-09-06 の P0-1: **どの経路でも**「送る権利」を
    # queue_lock の中で 1 度だけ取ってから送る。ロックの中で
    #   (1) 提出ログを見る (2) キューの最新イベントを見る (3) submitting を書く
    # をひとまとめにする。読むだけでロックを離すと、2 プロセスが同時に
    # 「ログなし・キュー履歴なし」を確認して同じ世代を 2 回送れてしまう。
    # submitting は queued ではないので、却下や二重承認が割り込んでも二度は送られない。
    with queue_lock(qpath):
        done = already_submitted(args.gen)
        if done:
            fail(f"{args.gen} は既に提出済み({done.get('ts')}, ref={done.get('submission_id')})。"
                 "二重提出を防ぐため中止")
        st = queue_state(qpath).get(args.gen)
        if args.approved:
            if not st or st.get("event") != "queued":
                fail(f"提出直前にキューの状態が変わった(event={st.get('event') if st else 'なし'})。提出中止")
            if st.get("eval_sha256") != hashlib.sha256((ROOT / args.eval_json).read_bytes()).hexdigest():
                fail("提出直前に評価 JSON が変わった。提出中止")
        elif st and st.get("event") != "submit_failed":
            # 自動提出はキューに履歴のある世代を出さない。これが無いと、枠が空いた翌日に
            # 同じ promote を再実行するだけで (a) 承認待ちを承認なしで出せる
            # (b) 人が却下した世代を出せる。submit_failed だけは再試行を許す。
            fail(f"{args.gen} は承認キューに履歴がある(event={st['event']})。自動提出しない。"
                 f"提出は人が実行: .venv/bin/python ops/approve_submit.py {args.gen}"
                 + ("（却下済み。出すなら理由を確かめてから積み直す）"
                    if st.get("event") == "rejected" else ""))
        append_queue_event(qpath, {
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "event": "submitting", "gen": args.gen, "eval": args.eval_json,
            "eval_sha256": (st or {}).get("eval_sha256")
                           or hashlib.sha256((ROOT / args.eval_json).read_bytes()).hexdigest(),
            "reason": args.reason, "approved": bool(args.approved),
            "note": args.note, "message": message,
        })

    sub = subprocess.run(
        KAGGLE + ["competitions", "submit", COMP, "-f", str(agent_file), "-m", message],
        capture_output=True, text=True, timeout=300,
    )

    # 成否は提出一覧に新しい ref が現れたかで確認(stdout文言に依存しない)
    new_ref = None
    try:
        after = kaggle_submissions_csv()
        for s in after:
            if s.get("description") == message and s["ref"] not in {x["ref"] for x in subs}:
                new_ref = s["ref"]
                break
    except SystemExit:
        pass  # 確認自体の失敗は提出結果を不明扱いにする(下で記録)

    if new_ref:
        status = "submitted"
    elif sub.returncode == 0:
        status = "submitted_unconfirmed"
    else:
        status = "submit_failed"

    rec = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generation": args.gen,
        "file": str(agent_file.relative_to(ROOT)),
        "message": message,
        "status": status,
        "submission_id": new_ref,
        "eval": args.eval_json,
        "reason": args.reason,
        "approved": bool(args.approved),
        # その提出時に効いていた [auto] 上限とその出所。翌朝「なぜ N 本出たのか」を
        # 提出ログだけで追えるようにする(2026-09-07 codex P1-3)。
        "auto_daily_cap": cap,
        "auto_daily_cap_source": cap_src or "policy",
    }
    with open(ROOT / "ops/submissions_log.jsonl", "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 送信前に submitting を書いたのは全経路なので、終端イベントも全経路で書く
    # (2026-09-06 の P0-1)。承認経路だけだと自動提出が submitting のまま残り、
    # submit_failed でない履歴として以後の再試行を永久に塞いでしまう。
    # 結果が不明(submitted_unconfirmed)でも queued には戻さない。
    # 実際には受理されている可能性があるので、再送は人が Kaggle 側を確認してから。
    ev_name = {"submitted": "submitted",
               "submitted_unconfirmed": "submit_unconfirmed",
               "submit_failed": "submit_failed"}[status]
    with queue_lock(qpath):
        append_queue_event(qpath, {
            "ts": rec["ts"], "event": ev_name, "gen": args.gen,
            "eval": args.eval_json, "note": args.note,
            "submission_id": new_ref, "status": status,
        })

    if status == "submit_failed":
        fail(f"提出コマンド失敗: {sub.stdout.strip()[-200:]} {sub.stderr.strip()[-200:]}")
    if status == "submitted_unconfirmed":
        print("⚠ 提出コマンドは成功したが提出一覧で確認できなかった。"
              "Kaggle 側を目視確認するまで再送しないこと（キューは submit_unconfirmed）")
    print(f"SUBMITTED ({status}, ref={new_ref})")


if __name__ == "__main__":
    main()
