#!/usr/bin/env python
"""リプレイの労働監査: 日次の unfed/uncared/hand-hour 内訳を表にする。

入力は `harness/run_match.py --replay out.json` が保存する kaggle-environments
リプレイ JSON。労働割当の退行検知に使う（gen0021 の「移動76%・CARE0%」の再発防止）。

使い方:
  .venv/bin/python harness/audit_replay.py replay.json --player 0
  .venv/bin/python harness/audit_replay.py replay.json --targets   # 上位の現金曲線と比較

--targets（計画 §1-D）は control/targets.json の cash_curve（上位の日次現金中央値）と
自分の日次現金を並べ、**どの日で遅れ始めるか**を出す。ローカル指標の自己参照から
抜けるための「外の数字」。EXP の「目標曲線との差」欄にこの出力を貼る。
"""
import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}


def tiles_iter(farm):
    for row in farm["tiles"]:
        for t in row:
            if isinstance(t, dict):
                yield t


def audit(replay_path, player):
    r = json.load(open(replay_path))
    steps = r["steps"]
    hours = len(steps)
    days = hours // 24
    rows = []
    for d in range(days):
        eod = steps[min(d * 24 + 23, hours - 1)]
        obs = eod[player]["observation"]
        farm = obs["farms"][player]
        anim = [t for t in tiles_iter(farm)
                if t.get("kind") in ("PASTURE", "COOP") and t.get("animal")]
        unfed = sum(1 for t in anim if not t.get("fed_today"))
        uncared = sum(1 for t in anim if not t.get("cared_today"))
        hands = len(farm["hands"])
        priv = obs.get("private") or {}
        feed_wheat = (priv.get("shed", {}).get("WHEAT", 0)
                      + sum(i.get("WHEAT", 0) for i in priv.get("inventories", [])))
        acts = collections.Counter()
        for h in range(24):
            a = steps[d * 24 + h][player].get("action") or {}
            for hl in (a.get("hands") or []):
                v = hl[0] if hl else "IDLE"
                acts["MOVE" if v in MOVES else v] += 1
        total = sum(acts.values())
        move_pct = 100.0 * acts.get("MOVE", 0) / total if total else 0.0
        rows.append(dict(day=d, animals=len(anim), unfed=unfed, uncared=uncared,
                         hands=hands, feed_wheat=feed_wheat,
                         money=farm["money"], move_pct=move_pct, acts=dict(acts)))
    return rows


def target_curve(path=None):
    p = Path(path) if path else (ROOT / "control/targets.json")
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    cc = d.get("cash_curve") or {}
    return {int(k[1:]): v for k, v in cc.items() if k.startswith("d") and k[1:].isdigit()}


# 序盤(d10 以前)の「手元現金」は多いほど良い指標ではない。上位は d10 に現金をほぼ 0 まで
# 再投資する。したがって早い日は OK/遅れ の判定を出さず、乖離の向きだけを示す。
REINVEST_DAYS = 10


def print_targets(rows, targets):
    """上位の現金曲線との差。**どの日で遅れ始めるか**が見たい情報。"""
    if not targets:
        print("(control/targets.json に cash_curve が無い)")
        return
    by_day = {r["day"]: r["money"] for r in rows}
    print("\n-- 目標曲線との差（control/targets.json の上位現金中央値）")
    print("day   自分     上位     比    判定")
    first_behind = None
    hoarding = []
    for d in sorted(targets):
        tgt = targets[d]
        mine = by_day.get(d)
        if mine is None:
            print(f"d{d:<3} (リプレイに無し)")
            continue
        ratio = mine / tgt if tgt else float("inf")
        if d <= REINVEST_DAYS:
            # 再投資期。上回っている＝現金を寝かせている疑い（gen0010 以前の失敗パターン）
            verdict = "寝かせ疑い" if ratio > 1.5 else "参考"
            if ratio > 1.5:
                hoarding.append(d)
        else:
            verdict = "OK" if ratio >= 1.0 else "遅れ"
            if ratio < 1.0 and first_behind is None:
                first_behind = d
        print(f"d{d:<3} {mine:8.0f} {tgt:8.0f}  {ratio:5.2f}x  {verdict}")
    if hoarding:
        print(f"-- d{'/d'.join(str(d) for d in hoarding)} は上位の 1.5 倍超の現金を持っている"
              "＝再投資が遅い疑い（上位は d10 に現金をほぼ 0 まで使う）")
    if first_behind is None:
        print(f"-- d{REINVEST_DAYS} より後は全ての目標日で上位の中央値以上")
    else:
        print(f"-- d{first_behind} で遅れ始める（ここが構造のボトルネック）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--player", type=int, default=0)
    ap.add_argument("--json", action="store_true", help="JSONL で出力")
    ap.add_argument("--targets", action="store_true",
                    help="control/targets.json の上位現金曲線と比較する")
    ap.add_argument("--targets-file", help="targets.json のパス(既定 control/targets.json)")
    args = ap.parse_args()
    rows = audit(args.replay, args.player)
    if args.json:
        for row in rows:
            print(json.dumps(row))
        if args.targets:
            print_targets(rows, target_curve(args.targets_file))
        return
    print("day anim unfed uncared hands feedW  money  move%  (FEED/CARE/WATER/HARVEST)")
    bad_feed = bad_care = 0
    for row in rows:
        a = row["acts"]
        print(f"d{row['day']:2d} {row['animals']:4d} {row['unfed']:5d} {row['uncared']:7d}"
              f" {row['hands']:5d} {row['feed_wheat']:5.0f} {row['money']:7.0f}"
              f" {row['move_pct']:5.1f}"
              f"  F{a.get('FEED', 0)} C{a.get('CARE', 0)} W{a.get('WATER', 0)}"
              f" H{a.get('HARVEST', 0)}")
        if 1 <= row["day"] <= 28:
            bad_feed += row["unfed"] > 0
            bad_care += row["uncared"] > 0
    print(f"-- d1-28: unfed>0 が {bad_feed} 日 / uncared>0 が {bad_care} 日"
          f"（両方 0 が gen0022 の合格ライン）")
    if args.targets:
        print_targets(rows, target_curve(args.targets_file))


if __name__ == "__main__":
    main()
