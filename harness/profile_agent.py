#!/usr/bin/env python
"""NFR-1: エージェントの1ターン処理時間を計測する(平均<0.1s・最悪<1sを確認)。

usage: profile_agent.py agents/gen0001/main.py [--opponent starter] [--seed 42] [--steps 720]
"""
import argparse
import importlib.util
import json
import statistics
import sys
import time
from pathlib import Path


def load_agent(path: str):
    p = Path(path).resolve()
    spec = importlib.util.spec_from_file_location("candidate_agent", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.agent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_path")
    ap.add_argument("--opponent", default="starter")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--steps", type=int, default=720)
    args = ap.parse_args()

    from kaggle_environments import make

    agent_fn = load_agent(args.agent_path)
    durations = []

    def timed_agent(obs):
        t0 = time.perf_counter()
        action = agent_fn(obs)
        durations.append(time.perf_counter() - t0)
        return action

    env = make(
        "kaggriculture",
        configuration={"episodeSteps": args.steps, "seed": args.seed},
        debug=True,
    )
    env.run([timed_agent, args.opponent])

    statuses = [s["status"] for s in env.steps[-1]]
    result = {
        "agent": args.agent_path,
        "turns": len(durations),
        "mean_s": round(statistics.mean(durations), 5),
        "p99_s": round(sorted(durations)[int(len(durations) * 0.99)], 5),
        "max_s": round(max(durations), 5),
        "statuses": statuses,
        "ok_mean_lt_0.1": statistics.mean(durations) < 0.1,
        "ok_max_lt_1.0": max(durations) < 1.0,
    }
    print(json.dumps(result, indent=1))
    if not (result["ok_mean_lt_0.1"] and result["ok_max_lt_1.0"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
