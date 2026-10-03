#!/usr/bin/env python
"""リプレイJSON(ローカル run_match --replay / Kaggle DL)の日次サマリを出す Analyst 用ツール。

usage: analyze_replay.py replays/episode-XXX-replay.json [--player 0|1|both]
出力: 日ごとの 資金 / タイル構成 / ハンド数 / 解放クアドラント / 主要市場価格
"""
import argparse
import json
from collections import Counter


def tile_summary(tiles):
    c = Counter()
    for row in tiles:
        for t in row:
            if t is None:
                c["empty"] += 1
            elif t == "LOCKED":
                c["locked"] += 1
            elif isinstance(t, dict):
                k = t.get("kind")
                if k == "PLANT":
                    c[t.get("crop", "?").lower()] += 1
                elif k in ("COOP", "PASTURE"):
                    a = t.get("animal")
                    c[a.lower() if a else k.lower() + "(empty)"] += 1
                elif k == "WEED":
                    c["weed"] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--player", default="both")
    args = ap.parse_args()

    d = json.load(open(args.replay))
    steps = d["steps"]
    names = d.get("info", {}).get("TeamNames") or ["p0", "p1"]
    players = [0, 1] if args.player == "both" else [int(args.player)]

    print(f"players: {names} / steps: {len(steps)}")
    final = steps[-1]
    print(f"final rewards: {[a.get('reward') for a in final]}")

    for step in steps:
        obs = step[0].get("observation", {})
        farms = obs.get("farms")
        if not farms or obs.get("hour") != 23:
            continue
        day = obs.get("day")
        line = [f"d{day:02d}"]
        for p in players:
            f = farms[p]
            ts = tile_summary(f.get("tiles", []))
            comp = " ".join(f"{k}:{v}" for k, v in sorted(ts.items()) if k not in ("locked",))
            line.append(
                f"| P{p} ${f.get('money', 0):>7.0f} hands:{len(f.get('hands', []))} "
                f"quad:{len(f.get('unlocked_quadrants', []))} {comp}")
        prices = obs.get("market", {}).get("prices", {})
        key_prices = " ".join(f"{k[:3]}:{v}" for k, v in prices.items())
        line.append(f"| {key_prices}")
        print(" ".join(line))
    shops = steps[-1][0].get("observation", {}).get("town", {}).get("unlocked_shops", [])
    print("shops:", shops)


if __name__ == "__main__":
    main()
