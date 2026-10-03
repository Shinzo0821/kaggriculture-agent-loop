#!/usr/bin/env python
"""FR-6/FR-8: LB 順位の回収と「ローカル指標 vs 実レート」のキャリブレーション表。

usage:
  .venv/bin/python ops/lb_calibration.py [--no-fetch] [--markdown]

- leaderboard CSV を DL → 自チームの順位・パーセンタイル・上位10%カットオフとの距離を
  ops/lb_rank_log.jsonl に追記(毎晩の定点)。
- 追跡中(最新2)提出の LB スコアと、その世代の records/eval_genNNNN.json のローカル指標
  (pool rating / money_mean / slope_mean)を並べる。
- 判定: 直近2夜でローカルが「改善」と言った提出が LB で前提出を上回っていなければ
  「⚠ ローカル指標が LB を予測していない → 指標監査」を出す。夜間サイクル1はこれを最初に読む。

2026-09-05 追加(計画 §1-A): **提出済み全世代**についてローカル指標(pool.rating / money_mean /
strong_money) と LB スコアのスピアマン相関と n を先頭に出す。n が小さいうちは「ローカル指標は
参考」であることを毎回明示するのが目的（n=3 で 1 逆転している状態で指標を信用しないため）。
"""
import argparse
import csv
import datetime as dt
import io
import json
import math
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE = ["uvx", "--from", "kaggle==2.2.4", "kaggle"]
COMP = "kaggriculture"
TEAM = "Shinzo Takayama"
RANK_LOG = ROOT / "ops/lb_rank_log.jsonl"


def fetch_leaderboard():
    with tempfile.TemporaryDirectory() as td:
        out = subprocess.run(KAGGLE + ["competitions", "leaderboard", COMP, "-d", "-p", td],
                             capture_output=True, text=True, timeout=180)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip()[:300])
        zips = list(Path(td).glob("*.zip"))
        if not zips:
            raise RuntimeError("leaderboard zip がない")
        with zipfile.ZipFile(zips[0]) as z:
            name = [n for n in z.namelist() if n.endswith(".csv")][0]
            rows = list(csv.DictReader(io.StringIO(z.read(name).decode("utf-8-sig"))))
    return rows


def rank_snapshot(rows):
    rows = sorted(rows, key=lambda r: -float(r["Score"]))
    scores = [float(r["Score"]) for r in rows]
    n = len(scores)
    me = next((i for i, r in enumerate(rows) if r["TeamName"] == TEAM), None)
    snap = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "teams": n,
        "rank": (me + 1) if me is not None else None,
        "score": float(rows[me]["Score"]) if me is not None else None,
        "percentile": round((me + 1) / n * 100, 1) if me is not None else None,
        "top10pct_cutoff": scores[int(n * 0.10)],
        "top25pct_cutoff": scores[int(n * 0.25)],
        "median": scores[n // 2],
        "top1": scores[0],
        "top10_cutoff": scores[9] if n >= 10 else None,
    }
    return snap


def submissions():
    out = subprocess.run(KAGGLE + ["competitions", "submissions", COMP, "-v"],
                         capture_output=True, text=True, timeout=120)
    if out.returncode != 0:
        return []
    lines = [l for l in out.stdout.splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines) if l.startswith("ref,")), None)
    if start is None:
        return []
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def local_metrics(gen):
    p = ROOT / f"records/eval_{gen}.json"
    if not p.exists():
        return {}
    ev = json.loads(p.read_text())
    pool = ev.get("pool") or {}
    gate = ev.get("gate") or {}
    return {
        "pool_rating": pool.get("rating"),
        "money_mean": pool.get("money_mean"),
        "slope_mean": pool.get("slope_mean"),
        "strong_money": pool.get("strong_money_mean"),
        "rating_delta": gate.get("rating_delta"),
        "pool_sha": ev.get("pool_sha256"),
        # 昇格判定の実体。rating_delta ではなくこれが「ローカルが改善と言ったか」の正
        # （2026-09-10 監査: rating_delta は 9 世代連続 0.0 で、旧 local_up は常に False だった）
        "margin_ci_lo": ((gate.get("margin_delta_paired") or {}).get("ci95") or [None])[0],
        "gate_pass": gate.get("pass"),
        "legacy_champ_wr": (None if ev.get("pool_file") else
                            next((v.get("win_rate") for k, v in (ev.get("opponents") or {}).items()
                                  if k.startswith("agents/gen")), None)),
    }


MIN_N_FOR_TRUST = 5  # これ未満は「ローカル指標は参考」バナーを出す
RATINGS_LOG = ROOT / "ops/ratings_log.jsonl"


EPISODE_API = "https://www.kaggle.com/api/i/competitions.EpisodeService/ListEpisodes"
TEAM_NAME = "Shinzo Takayama"


def frozen_drift():
    """**コードを凍結したまま**の同一 ref の LB スコアが動いた幅（参考値）。

    ops/ratings_log.jsonl から、同一 ref の連続スナップショット間の |Δ| を集める。
    - 0.0 は「その提出はもう試合していない(追跡2本から押し出された)」なので除く
    - 各 ref の最初の Δ は 600 からの初期上昇＝収束であってノイズではないので除く
    残りにも収束成分が混ざるので、**これは判定に使わず「LB スコアはこれくらい平気で動く」
    という参考値としてだけ出す**（2026-09-10 監査 §提言 2: 26 点を定数にしない）。
    判定の本体は real_match_compare()。
    """
    if not RATINGS_LOG.exists():
        return {"n": 0, "obs": [], "median": None, "max": None}
    by_ref = {}
    for line in RATINGS_LOG.read_text().splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
            sc = float(d["score"])
        except (ValueError, TypeError, KeyError):
            continue  # score が None/欠損のスナップショットは飛ばす
        by_ref.setdefault(d.get("ref"), []).append((d.get("ts"), sc))
    obs = []
    for _ref, rows in by_ref.items():
        rows.sort()
        uniq = [o for i, o in enumerate(rows) if i == 0 or o[0] != rows[i - 1][0]]
        deltas = [abs(uniq[i + 1][1] - uniq[i][1]) for i in range(len(uniq) - 1)]
        obs += [d for d in deltas[1:] if d > 0]   # 先頭=初期上昇 / 0=試合していない
    obs.sort()
    if not obs:
        return {"n": 0, "obs": [], "median": None, "max": None}
    return {"n": len(obs), "obs": obs, "median": obs[len(obs) // 2], "max": obs[-1]}


def episode_records(ref, timeout=60):
    """公開 episode API から、その提出の全試合の勝敗と相手レートを取る。

    リプレイ本体(1件 30MB)を落とさずに実戦分布が取れる（2026-09-10 監査 §提言 4）。
    完全性は「始点 600・終点 = LB スコア」で検算できる（監査レポート §0）。
    """
    req = urllib.request.Request(
        EPISODE_API, data=json.dumps({"submissionId": int(ref)}).encode(),
        headers={"content-type": "application/json", "user-agent": "kaggriculture-agent-loop"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    mine = [int(t["id"]) for t in d.get("teams", []) if t.get("teamName") == TEAM_NAME]
    if len(mine) != 1:
        raise RuntimeError(f"自チームを特定できない (ref={ref})")
    my_id = mine[0]
    out = []
    for ep in d.get("episodes", []):
        if ep.get("state") != "COMPLETED":
            continue
        ags = sorted(ep.get("agents") or [], key=lambda a: a.get("index", 0))
        if len(ags) != 2:
            continue
        mi = [i for i, a in enumerate(ags) if a.get("teamId") == my_id]
        if len(mi) != 1:
            continue
        m, o = ags[mi[0]], ags[1 - mi[0]]
        if m.get("reward") is None or o.get("reward") is None:
            continue
        out.append({"my": m["reward"], "opp": o["reward"], "oppbefore": o.get("initialScore")})
    return out


def _wr(recs):
    n = len(recs)
    w = sum(1 for r in recs if r["my"] > r["opp"])
    ob = [r["oppbefore"] for r in recs if r["oppbefore"] is not None]
    return {"n": n, "w": w, "p": (w / n if n else None),
            "opp_mean": (sum(ob) / len(ob) if ob else None),
            "margin_mean": (sum(r["my"] - r["opp"] for r in recs) / n if n else None)}


def real_match_compare(new_ref, old_ref):
    """追跡中2本の**実戦成績**を比べ、「差が読めるか」を先に判定する。

    2026-09-10 の指標監査で分かったこと:
      - LB スコアの差(9.2点)は、コードを凍結した同一提出のドリフト(25.9点)より小さかった
      - 実戦マージンの sd は $25,620 で、ローカルの効果量 $313 は 3 桁足りない
      - 共通相手は 63 チーム中 1 チーム＝LB では対応付き比較が原理的に不可能
    したがって **LB スコアの大小をそのまま「ローカルが外れた」証拠にしてはいけない**。
    ここでは勝率の差を二項の近似 CI で見て、0 をまたぐなら「判定不能」を返す。
    警告を出すのは「差が読めて、かつローカルの向きと逆」のときだけにする。
    """
    a, b = _wr(episode_records(new_ref)), _wr(episode_records(old_ref))
    if not (a["n"] and b["n"]):
        return {"verdict": "no_data", "new": a, "old": b}
    diff = a["p"] - b["p"]
    se = math.sqrt(a["p"] * (1 - a["p"]) / a["n"] + b["p"] * (1 - b["p"]) / b["n"])
    lo, hi = diff - 1.96 * se, diff + 1.96 * se
    return {"verdict": ("unreadable" if lo <= 0 <= hi else ("new_better" if lo > 0 else "old_better")),
            "new": a, "old": b, "diff": diff, "ci": (lo, hi),
            # 相手の引きが効くので、相手平均レートの差も併記する（監査 §3: +100 で平均限界効果 -41.8pt）
            "opp_gap": ((a["opp_mean"] - b["opp_mean"])
                        if (a["opp_mean"] is not None and b["opp_mean"] is not None) else None)}


def spearman(xs, ys):
    """順位相関(タイは平均順位)。n<3 なら None。"""
    n = len(xs)
    if n < 3:
        return None

    def ranks(v):
        order = sorted(range(n), key=lambda i: v[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return round(num / (dx * dy), 3)


def correlation_block(subs):
    """提出済み全世代の (ローカル指標, LB スコア) 対から相関と n を出す(計画 §1-A)。

    レポートの**先頭**に置く。ここが「ローカル指標を信じてよいか」の唯一の根拠。
    """
    pairs = []
    seen = set()
    for s in subs:
        g = gen_of(s.get("description"))
        if not g or g in seen:
            continue
        try:
            lb = float(s.get("publicScore"))
        except (TypeError, ValueError):
            continue
        lm = local_metrics(g)
        if lm.get("pool_rating") is None:
            continue  # v0.5 形式の評価が残っていない旧世代は対にできない
        seen.add(g)
        pairs.append((g, lb, lm))
    n = len(pairs)
    lines = [f"### ローカル指標 ↔ LB の相関（n={n}、提出済みで v0.5 評価が残っている世代）", ""]
    if n < 3:
        lines += [f"- **n={n}: 相関を出せない。ローカル指標は参考値として扱うこと。**", ""]
        for g, lb, lm in sorted(pairs, key=lambda x: x[0]):
            lines.append(f"  - {g}: LB {lb} / rating {lm.get('pool_rating')} / "
                         f"money {lm.get('money_mean')} / strong {lm.get('strong_money')}")
        return "\n".join(lines + [""])
    rows = []
    for key, label in (("pool_rating", "pool.rating"), ("money_mean", "money_mean"),
                       ("strong_money", "strong_money")):
        xs, ys = [], []
        for _, lb, lm in pairs:
            if isinstance(lm.get(key), (int, float)):
                xs.append(lm[key])
                ys.append(lb)
        r = spearman(xs, ys) if len(xs) >= 3 else None
        rows.append((label, r, len(xs)))
    lines += ["| ローカル指標 | スピアマン相関 vs LB | n |", "| --- | --- | --- |"]
    for label, r, k in rows:
        lines.append(f"| {label} | {'—' if r is None else r} | {k} |")
    if n < MIN_N_FOR_TRUST:
        lines += ["", f"⚠️ **n={n} < {MIN_N_FOR_TRUST}: ローカル指標は参考。**"
                  " 相関の符号が正でも、この n では偶然と区別できない。"
                  " 昇格ゲートの本体は据置き（計画 §5）。"]
    lines += ["", "**この表は判定のトリガーではない**（2026-09-10 監査）。n≈10 のスピアマンは 2 点で 0.24 動き、"
              "判断が実際に行われている直近クラスタ（LB 幅 ~40 点）では相関を有意に検出できない"
              "（完全並べ替え検定 p=0.56）。プールが変わった世代（pool_sha256 が違う）も混ざる。"
              "判定は下の「キャリブレーション判定（ローカル vs 実戦）」を見ること。"]
    lines += ["", "対応表: " + " ／ ".join(
        f"{g}(LB {lb}, rating {lm.get('pool_rating')}, strong {lm.get('strong_money')})"
        for g, lb, lm in sorted(pairs, key=lambda x: x[0]))]
    return "\n".join(lines + [""])


def gen_of(desc):
    import re
    m = re.search(r"\[auto\]\s*(gen\d{4})", desc or "")
    return m.group(1) if m else None


def build(no_fetch):
    lines = []
    snap = None
    if not no_fetch:
        try:
            snap = rank_snapshot(fetch_leaderboard())
            with open(RANK_LOG, "a") as f:
                f.write(json.dumps(snap) + "\n")
        except Exception as e:  # noqa: BLE001
            lines.append(f"⚠️ leaderboard 取得失敗: {e}")
    if snap is None and RANK_LOG.exists():
        last = [l for l in RANK_LOG.read_text().splitlines() if l.strip()]
        if last:
            snap = json.loads(last[-1])
            lines.append(f"(前回スナップショット {snap['ts']} を表示)")

    if snap:
        gap10 = (snap["top10pct_cutoff"] - snap["score"]) if snap["score"] is not None else None
        lines += [
            f"- **順位 {snap['rank']} / {snap['teams']}**（上位 {snap['percentile']}%）、スコア {snap['score']}",
            f"- 上位10% カットオフ {snap['top10pct_cutoff']}（差 {gap10:+.1f}）／ 上位25% {snap['top25pct_cutoff']}"
            f" ／ 中央値 {snap['median']} ／ 賞金圏(10位) {snap['top10_cutoff']} ／ 1位 {snap['top1']}",
        ]
        prev = [json.loads(l) for l in RANK_LOG.read_text().splitlines() if l.strip()] if RANK_LOG.exists() else []
        prev = [p for p in prev if p["ts"] < snap["ts"]]
        if prev:
            p = prev[-1]
            lines.append(f"- 前回({p['ts'][:10]}) 順位 {p['rank']} / スコア {p['score']} → 変化 "
                         f"{(snap['rank'] or 0) - (p['rank'] or 0):+d} 位")

    subs = submissions()
    lines = [correlation_block(subs), ""] + lines
    rows = []
    for i, s in enumerate(subs[:6]):
        g = gen_of(s.get("description"))
        lm = local_metrics(g) if g else {}
        rows.append({
            "tracked": i < 2, "gen": g, "ref": s.get("ref"), "lb": s.get("publicScore"),
            **lm,
        })
    if rows:
        lines += ["", "| 追跡 | gen | LB score | local pool rating | local money | local slope | rating_delta | (旧)vs王者 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            lines.append(f"| {'●' if r['tracked'] else ''} | {r['gen']} | {r['lb']} | {r.get('pool_rating')} | "
                         f"{r.get('money_mean')} | {r.get('slope_mean')} | {r.get('rating_delta')} | {r.get('legacy_champ_wr')} |")
        lines += calibration_verdict(rows)
    return "\n".join(lines)


def calibration_verdict(rows):
    """追跡中2本について「ローカルの向き」と「実戦の向き」を突き合わせる。

    2026-09-10 の指標監査（knowledge/analysis/2026-09-10_metric-audit.md）で 2 つ直した:

    1. **旧 local_up は常に False だった。** `rating_delta > 0` を「ローカルが改善と言ったか」に
       使っていたが、プールの全相手の勝率が 0/100% に張り付いているので rating_delta は
       gen0024 以降 9 世代連続で 0.0。この分岐は一度も発火しない死んだコードだった
       （実際に「2 夜連続の警告」と呼ばれていたのは、下の相関表を人が目で見た判断）。
       → 昇格判定の実体である **対応付きマージン差の CI 下限 > 0** に変えた。
    2. **LB スコアの大小を証拠に使うのをやめた。** LB 差 9.2 点はコード凍結時のドリフト
       25.9 点より小さく、読めない。代わりに**実戦の勝敗**を取ってきて、
       勝率差の CI が 0 をまたぐなら「判定不能」と明示する。警告は
       **差が読めて、かつローカルの向きと逆のとき**だけ出す。
    """
    out = []
    auto = [r for r in rows if r["gen"]]
    if len(auto) < 2:
        return out
    new, old = auto[0], auto[1]

    ci_lo = new.get("margin_ci_lo")
    if ci_lo is not None:
        local_up = ci_lo > 0
        local_why = f"対応付きマージン差の CI 下限 {ci_lo:+.1f}"
    elif new.get("legacy_champ_wr") is not None:  # 旧形式(v0.4 以前)しか無い場合
        local_up = new["legacy_champ_wr"] > 0.55
        local_why = f"(旧形式) 王者 H2H 勝率 {new['legacy_champ_wr']}"
    else:
        local_up, local_why = None, "ローカル評価 JSON が無い"

    out += ["", "### キャリブレーション判定（ローカル vs 実戦）", "",
            f"- ローカルの向き: **{'改善' if local_up else '改善と言っていない' if local_up is not None else '不明'}**"
            f"（{new['gen']}: {local_why}）"]

    try:
        cmp_ = real_match_compare(new["ref"], old["ref"])
    except Exception as e:  # noqa: BLE001  ネットワーク断でレポート全体を落とさない
        out.append(f"- ⚠️ 実戦成績の取得に失敗: {str(e)[:120]}")
        out.append("- → **判定を保留**（LB スコアの大小だけでは判定しない。監査 §1）")
        return out

    a, b = cmp_["new"], cmp_["old"]
    out.append(f"- 実戦: {new['gen']} {a['w']}/{a['n']} = {100*a['p']:.1f}%（平均相手レート {a['opp_mean']:.0f}）"
               f" ／ {old['gen']} {b['w']}/{b['n']} = {100*b['p']:.1f}%（{b['opp_mean']:.0f}）")
    if cmp_["verdict"] == "no_data":
        out.append("- → **判定不能**（実戦データがまだ無い）")
        return out
    lo, hi = cmp_["ci"]
    out.append(f"- 勝率差 {100*cmp_['diff']:+.1f}pt、95%CI [{100*lo:+.1f}, {100*hi:+.1f}]pt"
               f"（相手平均レートの差 {cmp_['opp_gap']:+.1f}）")

    if cmp_["verdict"] == "unreadable":
        p_ = (a["p"] + b["p"]) / 2
        d_ = abs(cmp_["diff"])
        need = (2 * (1.96 + 0.8416) ** 2 * p_ * (1 - p_) / d_ ** 2) if d_ > 0 else float("inf")
        out += ["- → **判定不能**: 勝率差の CI が 0 をまたぐ。この差を power80% で検出するには "
                f"1 本あたり約 {need:,.0f} 試合要る（実際は {min(a['n'], b['n'])}-{max(a['n'], b['n'])} 試合）。",
                "  **ここで「ローカルが外れた」と結論しないこと。**"
                " LB スコアの大小も同じ理由で読めない（監査 §1-2）。"]
    elif cmp_["verdict"] == "old_better" and local_up:
        out += ["", f"⚠️ **キャリブレーション警告**: {new['gen']} はローカルで改善判定なのに、"
                f"実戦の勝率で {old['gen']} に**有意に**負けている。"
                " 相手平均レートの差（上記）で説明が付かないなら指標監査を最優先にすること"
                "（前回の監査: knowledge/analysis/2026-09-10_metric-audit.md）。"]
    elif cmp_["verdict"] == "new_better" and local_up:
        out.append("- ✓ ローカルの改善判定と実戦の勝率が一致（差が有意）。")
    else:
        out.append("- （ローカルが改善と言っていないので警告の対象外）")

    dr = frozen_drift()
    if dr["n"]:
        try:
            gap = abs(float(new["lb"]) - float(old["lb"]))
            out.append(f"- 参考: 2 本の LB スコア差は {gap:.1f} 点。**コードを凍結したままの同一提出でも**"
                       f" 中央値 {dr['median']:.1f} 点・最大 {dr['max']:.1f} 点動いている（n={dr['n']}）。"
                       " LB スコアの大小は判定に使わない。")
        except (TypeError, ValueError):
            pass
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--markdown", action="store_true", help="(既定と同じ) markdown を stdout に出す")
    args = ap.parse_args()
    print(build(args.no_fetch))


if __name__ == "__main__":
    main()
