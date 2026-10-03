#!/usr/bin/env python
"""公開実装（sparring プール）の欠陥 audit（計画 §4-C）。

各スパーリング相手を 1 試合走らせてリプレイを取り、`harness/audit_replay.py` の指標
（unfed / uncared / move% / 日次現金）を 1 表にする。
**目的は真似ではなく差別化**: 上位型が構造的に落としているもの（世話落ち・売り崩し・
終盤の遊び）が、こちらの勝ち筋の候補になる。

usage:
  .venv/bin/python ops/audit_sparring.py --seeds 3 --out knowledge/analysis/YYYY-MM-DD_sparring-audit.md
"""
import argparse
import datetime as dt
import json
import statistics
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "harness"))
from run_match import run_match  # noqa: E402
from audit_replay import audit, target_curve  # noqa: E402


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def audit_agent(path, seeds, opponent="starter"):
    """自分(player 0)として 1 試合ずつ走らせ、日次指標の中央値を返す。"""
    rows_all = []
    finals = []
    with tempfile.TemporaryDirectory() as td:
        for s in seeds:
            rp = Path(td) / f"r{s}.json"
            result, env = run_match(path, opponent, s, 720)
            rp.write_text(json.dumps(env.toJSON()))
            finals.append(result["final_money"][0])
            rows_all.append(audit(str(rp), 0))
    days = min(len(r) for r in rows_all)
    out = {"final_money": med(finals)}
    unfed_days, uncared_days, moves, cash = [], [], [], {}
    for rows in rows_all:
        unfed_days.append(sum(1 for r in rows[1:29] if r["unfed"] > 0))
        uncared_days.append(sum(1 for r in rows[1:29] if r["uncared"] > 0))
        moves.append(med([r["move_pct"] for r in rows[1:days]]))
        for d in (5, 10, 15, 20):
            if d < len(rows):
                cash.setdefault(d, []).append(rows[d]["money"])
    out.update({"unfed_days": med(unfed_days), "uncared_days": med(uncared_days),
                "move_pct": med(moves),
                "animals_end": med([rows[min(28, len(rows) - 1)]["animals"] for rows in rows_all]),
                "hands_end": med([rows[min(28, len(rows) - 1)]["hands"] for rows in rows_all]),
                "cash": {d: med(v) for d, v in cash.items()}})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--seed-base", type=int, default=4200)
    ap.add_argument("--pool", default="control/sparring_pool.json")
    ap.add_argument("--include-disabled", action="store_true",
                    help="プールで無効の相手も監査する(改編候補を先に見たい時)")
    ap.add_argument("--also", default="", help="追加で監査するパス(カンマ区切り。王者など)")
    ap.add_argument("--out", help="Markdown 表の出力先")
    args = ap.parse_args()

    pool = json.loads((ROOT / args.pool).read_text())["opponents"]
    targets = target_curve()
    seeds = [args.seed_base + i for i in range(args.seeds)]
    entries = [(e["name"], e["path"], e.get("tier"), e.get("enabled", True)) for e in pool
               if e.get("enabled", True) or args.include_disabled]
    for p in [x.strip() for x in args.also.split(",") if x.strip()]:
        entries.append((Path(p).parent.name, p, "self", True))

    rows = []
    for name, path, tier, enabled in entries:
        print(f"  auditing {name} ...", file=sys.stderr)
        try:
            r = audit_agent(path, seeds)
        except Exception as e:  # noqa: BLE001
            print(f"    失敗: {e}", file=sys.stderr)
            continue
        if r:
            r.update(name=name, tier=tier, enabled=enabled)
            rows.append(r)

    rows.sort(key=lambda r: -(r["final_money"] or 0))
    md = [f"# 公開実装(sparring)の欠陥 audit — {dt.date.today()}", "",
          f"- 手法: 各エージェントを **vs starter・{args.seeds} シード**（seed {seeds[0]}-{seeds[-1]}）で走らせ、"
          "`harness/audit_replay.py` の日次指標の中央値を取った。",
          "- 目的（計画 §4-C）: **真似ではなく差別化**。上位型が構造的に落としているもの"
          "（世話落ち・移動の無駄・現金の寝かせ）がこちらの勝ち筋の候補になる。",
          "- 注意: vs starter は市場競合がほぼ無いので**上振れ**する。順位付けではなく"
          "「その実装が何を落としているか」を見るための表。", "",
          "| エージェント | 帯 | 最終資金 | unfed>0 の日 | uncared>0 の日 | move% | 動物 | hands | d5 | d10 | d15 | d20 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        c = r["cash"]
        md.append(f"| {r['name']}{'' if r['enabled'] else ' (無効)'} | {r['tier']} | "
                  f"${r['final_money']:,.0f} | {r['unfed_days']:.0f} | {r['uncared_days']:.0f} | "
                  f"{r['move_pct']:.0f}% | {r['animals_end']:.0f} | {r['hands_end']:.0f} | "
                  + " | ".join(f"${c.get(d, 0):,.0f}" for d in (5, 10, 15, 20)) + " |")
    if targets:
        md += ["", "目標曲線（`control/targets.json`）: "
               + " ／ ".join(f"d{d} ${targets[d]:,}" for d in sorted(targets))]
    md += ["", "## 読み方（差別化の候補）", "",
           "- **uncared>0 の日が多い相手**は羊毛/牛乳の質を落としている＝こちらが CARE を切らさなければ単価で勝てる。",
           "- **move% が高い相手**は労働の 6-7 割を移動に使っている＝同じ hands 数でこちらの実効行動数が上回る。",
           "- **d10 の現金が高い相手**は再投資が遅い＝後半の伸びで抜ける余地がある。",
           "- 具体的な狙い所は上の表から 1 つ選び、EXP の仮説にする（`knowledge/IDEA_POLICY.md` の「出してよい」5 番）。"]
    text = "\n".join(md) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text)
        print(f"written: {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
