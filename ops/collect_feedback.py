#!/usr/bin/env python
"""FR-6: 提出のレーティング推移とエピソード(リプレイ・ログ)を回収する。

usage:
  .venv/bin/python ops/collect_feedback.py [--replays N] [--no-download]

- submissions 一覧から [auto] 提出のスコアを ops/ratings_log.jsonl に追記(キャリブレーション基盤)
- 追跡中(最新2)の [auto] 提出について新規エピソードを replays/ にDL(1回あたり最大 N 件)
- 負けエピソードは stdout に列挙(Analyst の入力)
"""
import argparse
import csv
import datetime as dt
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE = ["uvx", "--from", "kaggle==2.2.4", "kaggle"]
COMP = "kaggriculture"


def run_kaggle(args, timeout=180):
    out = subprocess.run(KAGGLE + args, capture_output=True, text=True, timeout=timeout)
    return out


TEAM_NAME = "Shinzo Takayama"  # リプレイの TeamNames で自分を特定するのに使う


def read_csv_stdout(stdout):
    lines = [l for l in stdout.splitlines() if l.strip()]
    start = next((i for i, l in enumerate(lines) if "," in l), 0)
    return list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def judge_replay(path):
    """リプレイJSONから自分の勝敗と最終資金を判定する。判定不能なら UNKNOWN。"""
    try:
        d = json.loads(path.read_text())
        rewards = [a.get("reward") for a in d["steps"][-1]]
        names = d.get("info", {}).get("TeamNames") or []
        my = next((i for i, n in enumerate(names) if n == TEAM_NAME), None)
        if my is None or len(rewards) != 2 or None in rewards:
            return {"result": "UNKNOWN", "my_index": my, "rewards": rewards,
                    "opp_name": None, "my_money": None, "opp_money": None}
        opp = 1 - my
        result = ("WIN" if rewards[my] > rewards[opp]
                  else "LOSS" if rewards[my] < rewards[opp] else "TIE")
        return {"result": result, "my_index": my, "my_money": rewards[my],
                "opp_money": rewards[opp], "opp_name": names[opp]}
    except Exception as e:
        return {"result": "UNKNOWN", "my_index": None, "error": str(e)[:100],
                "opp_name": None, "my_money": None, "opp_money": None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replays", type=int, default=6, help="今回DLする新規リプレイの最大数")
    ap.add_argument("--no-download", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    out = run_kaggle(["competitions", "submissions", COMP, "-v"])
    if out.returncode != 0:
        sys.exit(f"submissions 取得失敗: {out.stderr.strip()[:300]}")
    subs = read_csv_stdout(out.stdout)
    autos = [s for s in subs if str(s.get("description", "")).startswith("[auto]")]

    # レーティングのスナップショット追記
    with open(ROOT / "ops/ratings_log.jsonl", "a") as f:
        for s in autos:
            f.write(json.dumps({
                "ts": now, "ref": s.get("ref"),
                "description": s.get("description"),
                "status": s.get("status"), "score": s.get("publicScore") or None,
            }, ensure_ascii=False) + "\n")
    print(f"ratings_log: {len(autos)} 件のスナップショット追記")

    # 追跡中 = 全提出のうち最新2件(それのみが対戦する)
    tracked = subs[:2]
    tracked_autos = [s for s in tracked if str(s.get("description", "")).startswith("[auto]")]
    print("tracked(最新2):", [(s.get("ref"), s.get("description", "")[:40], s.get("publicScore")) for s in tracked])

    if args.no_download:
        return

    seen_path = ROOT / "ops/episodes_seen.json"
    seen = set(json.loads(seen_path.read_text())) if seen_path.exists() else set()
    downloaded = 0
    results = []
    for s in tracked_autos:
        ref = s.get("ref")
        ep_out = run_kaggle(["competitions", "episodes", ref, "-v", "-q"])
        if ep_out.returncode != 0:
            print(f"  episodes {ref} 取得失敗(スキップ): {ep_out.stderr.strip()[:200]}")
            continue
        rows = read_csv_stdout(ep_out.stdout)
        # 末尾の案内文などCSV外の行を除外: id が数値の行のみ有効
        rows = [r for r in rows
                if str(r.get("id") or r.get("episodeId") or "").isdigit()]
        print(f"  submission {ref}: episodes {len(rows)} 件")
        for row in rows:
            ep_id = str(row.get("id") or row.get("episodeId"))
            if ep_id in seen:
                continue
            if downloaded >= args.replays:
                break
            dest = ROOT / "replays"
            dest.mkdir(exist_ok=True)
            rp = run_kaggle(["competitions", "replay", ep_id, "-p", str(dest)])
            if rp.returncode != 0:
                print(f"  replay {ep_id} DL失敗: {rp.stderr.strip()[:150]}")
                continue
            seen.add(ep_id)
            downloaded += 1
            outcome = judge_replay(dest / f"episode-{ep_id}-replay.json")
            outcome.update({"episode": ep_id, "submission": ref})
            results.append(outcome)
            # 負け試合は本番エージェントログも回収(Analyst用)
            if outcome.get("result") == "LOSS" and outcome.get("my_index") is not None:
                logdir = ROOT / "logs"
                logdir.mkdir(exist_ok=True)
                lg = run_kaggle(["competitions", "logs", ep_id,
                                 str(outcome["my_index"]), "-p", str(logdir)])
                if lg.returncode != 0:
                    print(f"  logs {ep_id} DL失敗: {lg.stderr.strip()[:150]}")
    seen_path.write_text(json.dumps(sorted(seen)))
    print(f"replays: 新規 {downloaded} 件DL → replays/")
    for r in sorted(results, key=lambda x: x.get("result", "")):
        print(f"  {r['result']:4} ep {r['episode']} (sub {r['submission']}) "
              f"my={r.get('my_money')} opp={r.get('opp_money')} vs {r.get('opp_name')}")
    losses = [r for r in results if r.get("result") == "LOSS"]
    if losses:
        print(f"負け {len(losses)} 件 → リプレイは replays/、自ログは logs/ (Analystの入力)")


if __name__ == "__main__":
    main()
