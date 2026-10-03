#!/usr/bin/env python
"""FR-8: 日次レポートの骨格を state/reports/YYYY-MM-DD.md に生成する。

数値部分(順位・レーティング・提出・実験一覧)を機械生成する。夜間セッションは
このスクリプトを実行した後、「所感・次の仮説」節を追記してよい。

2026-09-05 改訂(計画 §3-D): レポートを**採用判断シート**にする。先頭を必ず次の 5 行にする:
  1. 順位（LB のどこにいるか）
  2. 相関 n（ローカル指標を信じてよいか）
  3. 承認待ち（人が決める必要がある提出）
  4. 目標曲線との差（外の数字＝上位が出している資金に対してどこにいるか）
  5. 王者のミクロ実行（タイル利用率・収量・移動。資金の 4 行には出ない「実行の正しさ」）
通知は入れない方針（計画 §3-C）なので、**人が翌朝ここだけ読めば足りる**ことが要件。
運用上の問題（セッション上限・連続失敗）も state/ops_alerts.jsonl から自動転記する。
"""
import datetime as dt
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE = ["uvx", "--from", "kaggle==2.2.4", "kaggle"]


def load_json(rel, default=None):
    p = ROOT / rel
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        return default


def head_lines():
    """レポート先頭の固定 5 行(計画 §3-D + ミクロ実行プラン §2)。ここだけ読めば判断できることが要件。"""
    import sys
    sys.path.insert(0, str(ROOT / "ops"))
    out = []

    # 1. 順位
    ranks = tail_jsonl("ops/lb_rank_log.jsonl", 2)
    if ranks:
        r = ranks[-1]
        prev = ranks[0] if len(ranks) > 1 else None
        move = f"（前回比 {(r.get('rank') or 0) - (prev.get('rank') or 0):+d} 位）" if prev else ""
        gap = (r["top10pct_cutoff"] - r["score"]) if r.get("score") is not None else None
        out.append(f"1. **順位 {r.get('rank')} / {r.get('teams')}**（上位 {r.get('percentile')}%、"
                   f"スコア {r.get('score')}）{move}／ 上位10% まで {gap:+.0f}"
                   if gap is not None else
                   f"1. **順位 {r.get('rank')} / {r.get('teams')}**{move}")
    else:
        out.append("1. **順位**: スナップショットなし（ops/lb_rank_log.jsonl が空）")

    # 2. 相関 n
    try:
        from lb_calibration import submissions as _subs, local_metrics, gen_of
        subs = _subs()
        n = len({g for s in subs if (g := gen_of(s.get("description")))
                 and local_metrics(g).get("pool_rating") is not None
                 and str(s.get("publicScore") or "").replace(".", "", 1).isdigit()})
        trust = "**ローカル指標は参考**（n<5）" if n < 5 else "ローカル指標を判断に使ってよい"
        out.append(f"2. **相関 n = {n}**（ローカル指標 ↔ LB の対の数）→ {trust}")
    except Exception as e:  # noqa: BLE001
        out.append(f"2. **相関 n**: 算出失敗（{e}）")

    # 3. 承認待ち
    try:
        from preflight_submit import queue_path, queue_state
        policy = load_json("control/submission_policy.json", {})
        pend = [e for e in queue_state(queue_path(policy)).values() if e.get("event") == "queued"]
        if pend:
            out.append(f"3. **承認待ち {len(pend)} 件** → " + " ／ ".join(
                f"{e['gen']}（{e.get('note') or '理由未記入'}、rating_delta {e.get('rating_delta')}、"
                f"資金差 {(e.get('money_delta_paired') or {}).get('mean')}）" for e in pend))
            out.append("   承認: `.venv/bin/python ops/approve_submit.py <gen>` ／ "
                       "却下: `... --reject <gen> --why '理由'`")
        else:
            out.append("3. **承認待ち**: なし")
    except Exception as e:  # noqa: BLE001
        out.append(f"3. **承認待ち**: 算出失敗（{e}）")

    # 4. 目標曲線との差
    tg = load_json("control/targets.json", {}) or {}
    champ = (load_json("control/champion.json", {}) or {}).get("gen")
    ev = load_json(f"records/eval_{champ}.json", {}) if champ else {}
    pool = (ev or {}).get("pool") or {}
    if pool.get("money_mean") is not None:
        final_t = tg.get("final_money_median")
        band = tg.get("strong_band_money") or {}
        strong = pool.get("strong_money_mean")
        parts = [f"王者 {champ} の資金平均 ${pool['money_mean']:,.0f}"]
        if final_t:
            parts.append(f"上位中央値 ${final_t:,.0f} の {pool['money_mean'] / final_t:.0%}")
        if strong is not None and band.get("low"):
            parts.append(f"強帯戦 ${strong:,.0f}（相手 ${band['low']:,.0f}-{band['high']:,.0f}）")
        elif band.get("low"):
            parts.append("強帯資金は未計測（新形式の評価を取り直すと出る）")
        out.append("4. **目標曲線との差**: " + " ／ ".join(parts))
    else:
        out.append(f"4. **目標曲線との差**: 王者({champ})の評価が読めない")

    # 5. 王者のミクロ 5 指標（実行の正しさ。タイル日と 1 収穫あたり収量は上の 4 行には出ない）
    out.append("5. **王者のミクロ実行**: " + micro_line(tg))
    return out


def latest_own_replay():
    """毎晩の collect_feedback が DL した実戦リプレイのうち最新のもの。(path, my_index)。"""
    d = ROOT / "replays"
    if not d.is_dir():
        return None, None
    import sys
    sys.path.insert(0, str(ROOT / "ops"))
    try:
        from collect_feedback import judge_replay
    except Exception:  # noqa: BLE001
        return None, None
    for p in sorted(d.glob("episode-*-replay.json"), key=lambda q: q.stat().st_mtime,
                    reverse=True):
        my = judge_replay(p).get("my_index")
        if my is not None:
            return p, my
    return None, None


def micro_line(targets):
    """王者の実戦リプレイを harness/micro_audit.py で測り、目標との差を 1 行にする。"""
    path, my = latest_own_replay()
    if path is None:
        return ("実戦リプレイが無い（`ops/collect_feedback.py` の DL 待ち）。"
                "ローカルで見るなら `harness/run_match.py ... --replay r.json` → "
                "`harness/micro_audit.py r.json --assert`")
    import sys
    sys.path.insert(0, str(ROOT / "harness"))
    try:
        from micro_audit import audit
        _, m, _, _ = audit(json.loads(path.read_text()), my)
    except Exception as e:  # noqa: BLE001
        return f"{path.name} の監査に失敗（{type(e).__name__}: {str(e)[:80]}）"
    tm = (targets or {}).get("micro") or {}

    def cmp(name, fmt, direction):
        got, lim = m.get(name), tm.get(name)
        if got is None:
            return f"{name}=—"
        s = format(got, fmt)
        if lim is None:
            return f"{name}={s}"
        ok = got >= lim if direction == "min" else got <= lim
        if ok:
            return f"{name}={s}"
        sign = "≥" if direction == "min" else "≤"
        return f"{name}={s}({sign}{lim} 未達)"

    parts = [
        cmp("tile_util", ".0%", "min"),
        f"未使用{m.get('never_used_tile_count')}",
        cmp("wheat_yield", ".2f", "min"),
        cmp("melon_yield", ".2f", "min"),
        cmp("strawberry_yield", ".2f", "min"),
        cmp("moves3plus_share", ".0%", "max"),
        cmp("last_water_hour", "d", "max"),
    ]
    return f"{path.name}（座席 p{my}） " + " ／ ".join(parts)


def top_meta_lines():
    """上位メタとの差(ops/top_meta_gap.py が毎晩生成する state/top_meta/gap_LATEST.json)。無ければ 1 行。"""
    js = load_json("state/top_meta/gap_LATEST.json")
    if not js:
        return ["（未生成。`ops/top_meta_gap.py` をランチャーが回収時に実行する）"]
    o, t = js.get("ours") or {}, js.get("top_B") or {}
    stale = []
    try:  # gap の date はローカル日付、レポートは UTC 日付なので 1 日のずれは正常。2 日以上古ければ前夜データ
        age = (dt.datetime.now(dt.timezone.utc).date() - dt.date.fromisoformat(js.get("date"))).days
        if age > 1:
            stale = [f"- ⚠️ **前夜以前のデータ**（gap の date {js.get('date')} は {age} 日前。今夜の top_meta_gap が失敗している。回収ログの NG: 行を見る）"]
    except (TypeError, ValueError):
        stale = ["- ⚠️ gap_LATEST.json の date が読めない"]

    def money(m, d):
        v = m.get(f"money_d{d}")
        return f"${v:,.0f}" if v is not None else "-"

    out = stale + [f"- {js.get('date')} 王者 {js.get('champion')} vs {js.get('opponent')}（{js.get('n_own')} 記録）"
           f" ／ 上位 B 型 {js.get('n_topB')} 記録 ／ shared §7 解釈: {js.get('interpretation')}",
           f"- 資金 d10/d20/d29: 我々 {money(o,10)}/{money(o,20)}/{money(o,29)} ／ 上位 {money(t,10)}/{money(t,20)}/{money(t,29)}",
           f"- 新着: 初出の型 {len(js.get('new_signatures') or [])} 件、Top20 入り {', '.join(js.get('entrants') or []) or 'なし'}、"
           f"骨格 drift {', '.join(js.get('drift') or []) or 'なし'}"]
    out += [f"- 問い{i}: {q}" for i, q in enumerate((js.get("questions") or [])[:3], 1)]
    out.append("- 表: `state/top_meta/gap_LATEST.md`（上位側の元表は `../shared/top_meta/LATEST.md`）")
    return out


def ops_problem_lines():
    """運用上の問題(セッション上限・セッションエラー)。record_usage.py が書く。"""
    alerts = tail_jsonl("state/ops_alerts.jsonl", 10)
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    recent = [a for a in alerts if str(a.get("ts", "")).startswith(today)]
    if not recent:
        return ["（今日の警報なし）"]
    return [f"- ⚠️ **{a.get('kind')}** cycle={a.get('cycle')} model={a.get('model')}: {a.get('detail')}"
            for a in recent]


def tail_jsonl(path, n=20):
    p = ROOT / path
    if not p.exists():
        return []
    lines = [l for l in p.read_text().splitlines() if l.strip()]
    return [json.loads(l) for l in lines[-n:]]


def main():
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    out = subprocess.run(
        KAGGLE + ["competitions", "submissions", "kaggriculture", "-v"],
        capture_output=True, text=True, timeout=120,
    )
    sub_lines = []
    fetch_error = None
    header_lines = [l for l in out.stdout.splitlines() if l.startswith("ref,")] if out.returncode == 0 else []
    if out.returncode != 0:
        fetch_error = f"kaggle submissions 取得失敗: {out.stderr.strip()[:200]}"
    elif not header_lines:
        fetch_error = f"submissions CSV をパースできない: {out.stdout.strip()[:150]}"
    else:
        import csv, io
        lines = [l for l in out.stdout.splitlines() if l.strip()]
        start = next(i for i, l in enumerate(lines) if l.startswith("ref,"))
        for i, s in enumerate(csv.DictReader(io.StringIO("\n".join(lines[start:])))):
            mark = "←追跡中" if i < 2 else ""
            sub_lines.append(
                f"| {s.get('ref')} | {str(s.get('date',''))[:16]} | "
                f"{str(s.get('description',''))[:45]} | {s.get('status','').replace('SubmissionStatus.','')} | "
                f"{s.get('publicScore','')} | {mark} |")

    exps = sorted((ROOT / "knowledge/experiments").glob("EXP*.md"))
    recent_subs = tail_jsonl("ops/submissions_log.jsonl", 10)
    ratings = tail_jsonl("ops/ratings_log.jsonl", 12)
    usage = tail_jsonl("ops/token_log.jsonl", 8)

    try:
        import sys
        sys.path.insert(0, str(ROOT / "ops"))
        from lb_calibration import build as calib_build
        calib = calib_build(no_fetch=False)
    except Exception as e:  # noqa: BLE001
        calib = f"⚠️ lb_calibration 失敗: {e}"

    report = [
        f"# 日次レポート {today}",
        "",
        "## 採用判断シート（ここだけ読めば判断できる。計画 §3-D）",
        "",
        *head_lines(),
        "",
        "### 運用上の問題",
        "",
        *ops_problem_lines(),
        "",
        "## 上位メタとの差（自動。ops/top_meta_gap.py）",
        "",
        *top_meta_lines(),
        "",
        "## LB 順位とキャリブレーション（相関 n・目標は上位10%）",
        "",
        calib,
        "",
        "## 提出状況(上2件が追跡中=最終評価候補)",
        "",
        *( [f"⚠️ **{fetch_error}**", ""] if fetch_error else [] ),
        "| ref | date(UTC) | message | status | score | 追跡 |",
        "| --- | --- | --- | --- | --- | --- |",
        *sub_lines[:8],
        "",
        "## [auto] レーティング直近スナップショット",
        "",
        *(f"- {r['ts']} {r.get('description','')[:40]}: {r.get('score')}" for r in ratings),
        "",
        "## 実験記録(累計)",
        "",
        *(f"- {p.name}" for p in exps[-8:]),
        "",
        "## 直近の提出ログ",
        "",
        *(f"- {r['ts']} {r['generation']} → {r['status']}"
          + (f"（[auto] 上限 {r['auto_daily_cap']}: {r['auto_daily_cap_source']}）"
             if r.get("auto_daily_cap_source") not in (None, "policy") else "")
          for r in recent_subs),
        "",
        "## トークン/コスト(直近8サイクル、ops/token_log.jsonl)",
        "",
        "| night | cycle | model | min | turns | out_tok | cache_read | cost$ | rc |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *(f"| {u.get('night')} | {u.get('cycle')} | {u.get('model_requested')} | {u.get('duration_min','')} | "
          f"{u.get('num_turns','')} | {u.get('output_tokens','')} | {u.get('cache_read','')} | "
          f"{u.get('cost_usd','')} | {u.get('rc')} |" for u in usage),
        "",
        f"- 直近8サイクル合計: ${sum(u.get('cost_usd') or 0 for u in usage):.2f}",
        "",
        "## 所感・次の仮説(夜間セッションが追記)",
        "",
    ]
    dest = ROOT / "state/reports" / f"{today}.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(report) + "\n")
    print(f"written: {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
