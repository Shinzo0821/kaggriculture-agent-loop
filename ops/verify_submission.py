#!/usr/bin/env python
"""提出後の一致検査（計画 §7-B）。

ローカル評価で $X 出る世代が、実際の Kaggle 環境でも同じ分布を出しているかを確かめる。
ズレていたら**エージェントの強さの問題ではなく、環境差かローダの誤選択**を疑う
（提出物が想定と違う、環境のバージョン差、観測フォーマットの差など）。
これを見ていないと「LB が動かない」の原因をエージェント側だけで探し続けることになる。

やること:
  1. 対象世代の提出（ops/submissions_log.jsonl）に紐づくエピソードのリプレイを replays/ から拾う
  2. 自分の d5/d10/d15/d20 現金と最終資金、PASS/エラー率を出す
  3. 同世代のローカル評価（records/eval_<gen>.json の games）の分布と比べる
  4. control/submission_policy.json の post_submit_verify を満たさなければ警告する

usage:
  .venv/bin/python ops/verify_submission.py --gen gen0022
  .venv/bin/python ops/verify_submission.py --gen gen0022 --json
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAM = "Shinzo Takayama"
CHECK_DAYS = (5, 10, 15, 20)


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def my_index(replay):
    names = (replay.get("info") or {}).get("TeamNames") or []
    return next((i for i, n in enumerate(names) if n == TEAM), None)


def episode_stats(path):
    """1 エピソードから自分の日次現金・最終資金・状態を取る。"""
    d = json.loads(Path(path).read_text())
    me = my_index(d)
    if me is None:
        return None
    steps = d.get("steps") or []
    if not steps:
        return None
    cash = {}
    for day in CHECK_DAYS:
        i = day * 24
        if i < len(steps):
            obs = steps[i][0].get("observation") or {}
            farms = obs.get("farms")
            if farms and len(farms) > me:
                cash[day] = farms[me].get("money")
    last = steps[-1]
    status = last[me].get("status")
    reward = last[me].get("reward")
    opp = last[1 - me].get("reward")
    return {"episode": Path(path).stem, "cash": cash, "final_money": reward,
            "opp_money": opp, "status": status,
            "result": None if None in (reward, opp) else
                      ("WIN" if reward > opp else "LOSS" if reward < opp else "TIE")}


def local_distribution(gen):
    p = ROOT / f"records/eval_{gen}.json"
    if not p.exists():
        return None
    ev = json.loads(p.read_text())
    finals = [g.get("cand_final") for g in ev.get("games", [])]
    pool = ev.get("pool") or {}
    return {"money_mean": pool.get("money_mean"), "money_median": med(finals),
            "n_games": len(finals), "strong_money_mean": pool.get("strong_money_mean")}


def submission_refs(gen):
    p = ROOT / "ops/submissions_log.jsonl"
    if not p.exists():
        return []
    refs = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r.get("generation") == gen and r.get("submission_id"):
            refs.append(str(r["submission_id"]))
    return refs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gen", required=True)
    ap.add_argument("--replays", default="replays", help="リプレイの置き場")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    policy = json.loads((ROOT / "control/submission_policy.json").read_text())
    cfg = policy.get("post_submit_verify") or {}
    min_eps = cfg.get("min_episodes", 20)
    ratio_min = cfg.get("money_ratio_min", 0.70)
    max_err = cfg.get("max_error_rate", 0.0)

    # ops/collect_feedback.py が落としたリプレイのうち、この世代の提出のものを拾う。
    # エピソードと提出の対応表が無い場合は、全リプレイから自分視点の統計を取る（注記付き）。
    eps = []
    for p in sorted(Path(args.replays).glob("episode-*-replay.json")):
        st = episode_stats(p)
        if st:
            eps.append(st)
    refs = submission_refs(args.gen)

    local = local_distribution(args.gen)
    finals = [e["final_money"] for e in eps]
    errors = [e for e in eps if e["status"] not in ("DONE", None)]
    out = {
        "gen": args.gen,
        "submission_refs": refs,
        "episodes": len(eps),
        "actual_money_median": med(finals),
        "actual_money_mean": round(statistics.mean([f for f in finals if f is not None]), 1)
                             if any(f is not None for f in finals) else None,
        "actual_cash_curve": {d: med([e["cash"].get(d) for e in eps]) for d in CHECK_DAYS},
        "win_rate": (round(sum(1 for e in eps if e["result"] == "WIN") / len(eps), 3)
                     if eps else None),
        "error_rate": round(len(errors) / len(eps), 3) if eps else None,
        "local": local,
        "problems": [],
        "note": ("replays/ 内の全エピソードを対象にしている（エピソードと提出 ref の対応表が無いため）。"
                 "世代を切り分けたい場合は該当時期のリプレイだけを別ディレクトリに置いて --replays で指定する。"),
    }
    if len(eps) < min_eps:
        out["problems"].append(f"エピソードが {len(eps)} 件で {min_eps} 件に満たない（判定保留）")
    if out["error_rate"] is not None and out["error_rate"] > max_err:
        out["problems"].append(f"エラー率 {out['error_rate']} > 許容 {max_err}"
                               "（環境差・例外パスを疑う）")
    if local and local.get("money_mean") and out["actual_money_mean"]:
        ratio = out["actual_money_mean"] / local["money_mean"]
        out["money_ratio_vs_local"] = round(ratio, 3)
        if ratio < ratio_min:
            out["problems"].append(
                f"実戦の平均資金がローカルの {ratio:.0%}（下限 {ratio_min:.0%}）。"
                "エージェントの強さではなく、環境差・ローダ誤選択・提出物違いを先に疑うこと")

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    print(f"# 提出後の一致検査: {args.gen}")
    print(f"- 提出 ref: {', '.join(refs) or '(submissions_log に無し)'}")
    print(f"- 実戦 {out['episodes']} エピソード / 勝率 {out['win_rate']} / エラー率 {out['error_rate']}")
    print(f"- 実戦の最終資金: 中央値 {out['actual_money_median']} / 平均 {out['actual_money_mean']}")
    print(f"- 実戦の現金曲線: " + " ／ ".join(f"d{d} {v}" for d, v in out["actual_cash_curve"].items()))
    if local:
        print(f"- ローカル評価: 平均 {local['money_mean']} / 中央値 {local['money_median']}"
              f" （{local['n_games']} 戦、強帯 {local['strong_money_mean']}）")
        if "money_ratio_vs_local" in out:
            print(f"- **実戦 / ローカル = {out['money_ratio_vs_local']:.0%}**（下限 {ratio_min:.0%}）")
    else:
        print(f"- ローカル評価 records/eval_{args.gen}.json が無い")
    print(f"- 注: {out['note']}")
    if out["problems"]:
        print("\n⚠ 問題:")
        for p in out["problems"]:
            print(f"  - {p}")
        sys.exit(1)
    print("\nOK: ローカル分布と実戦分布に大きなズレなし")


if __name__ == "__main__":
    main()
