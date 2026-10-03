#!/usr/bin/env python
"""FR-1: 2エージェントをシード指定で1戦させ、結果と時系列を構造化保存する。

usage:
  run_match.py AGENT_A AGENT_B --seed 42 [--steps 720] [--out records/match.json] [--replay replay.json]

AGENT は組み込み名 ("pass"/"random"/"starter") か main.py へのパス。
exit code: 0 正常。結果 JSON を stdout に出す。
"""
import argparse
import json
import sys
import time
from pathlib import Path


def resolve(name: str) -> str:
    if name in ("pass", "random", "starter"):
        return name
    p = Path(name)
    if not p.exists():
        sys.exit(f"agent not found: {name}")
    return str(p.resolve())


def run_match(agent_a: str, agent_b: str, seed: int, steps: int = 720):
    from kaggle_environments import make

    env = make(
        "kaggriculture",
        configuration={"episodeSteps": steps, "seed": seed},
        debug=False,
    )
    t0 = time.time()
    env.run([resolve(agent_a), resolve(agent_b)])
    wall = time.time() - t0

    money = [[], []]  # per-step bank balance per player
    prices_by_day = {}
    money_by_day = {}  # day(hour==0) -> [money_p0, money_p1]
    for step in env.steps:
        obs0 = step[0]["observation"]
        farms = obs0.get("farms")
        if not farms:
            continue
        for i in (0, 1):
            money[i].append(farms[i]["money"])
        if obs0.get("hour") == 0:
            prices_by_day[obs0.get("day")] = dict(obs0["market"]["prices"])
            money_by_day[obs0.get("day")] = [farms[0]["money"], farms[1]["money"]]

    final = env.steps[-1]
    rewards = [final[i]["reward"] for i in (0, 1)]
    statuses = [final[i]["status"] for i in (0, 1)]
    final_money = [money[0][-1] if money[0] else None, money[1][-1] if money[1] else None]
    if statuses[0] != "DONE" and statuses[1] == "DONE":
        winner = 1
    elif statuses[1] != "DONE" and statuses[0] == "DONE":
        winner = 0
    elif final_money[0] is None or final_money[1] is None:
        winner = None
    elif final_money[0] > final_money[1]:
        winner = 0
    elif final_money[1] > final_money[0]:
        winner = 1
    else:
        winner = None  # tie

    return {
        "agents": [agent_a, agent_b],
        "seed": seed,
        "steps": steps,
        "statuses": statuses,
        "rewards": rewards,
        "final_money": final_money,
        "winner": winner,
        "money_diff": (final_money[0] - final_money[1])
        if None not in final_money
        else None,
        "wall_seconds": round(wall, 2),
        "timeseries": {"money": money, "prices_by_day": prices_by_day,
                       "money_by_day": money_by_day},
    }, env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_a")
    ap.add_argument("agent_b")
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--out", help="結果JSONの保存先")
    ap.add_argument("--replay", help="リプレイJSON(env.toJSON())の保存先")
    ap.add_argument("--quiet", action="store_true", help="stdoutにはサマリ1行のみ")
    args = ap.parse_args()

    result, env = run_match(args.agent_a, args.agent_b, args.seed, args.steps)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result))
    if args.replay:
        Path(args.replay).parent.mkdir(parents=True, exist_ok=True)
        Path(args.replay).write_text(json.dumps(env.toJSON()))

    if args.quiet:
        summary = {k: v for k, v in result.items() if k != "timeseries"}
        print(json.dumps(summary))
    else:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
