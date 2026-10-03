#!/usr/bin/env python
"""スパーリング相手プールの固定レーティングを総当たりで算出し、control/sparring_pool.json に書き戻す。

usage:
  rate_pool.py --pool control/sparring_pool.json [--seeds 30] [--jobs 8] [--write] [--extra agents/genNNNN/main.py,...]

- プール内の全ペアを両側×seeds 戦。Bradley-Terry を MM 法で最尤推定し Elo 尺度(400)に変換。
- アンカー: "starter" がプールにあれば starter=0、無ければ平均0。
- --extra で王者などを一緒に回すと、その相手の暫定レーティングも表示する(書き戻しはプール内のみ)。
- レーティングは「プール内での相対値」であり LB のスコアとは無関係。候補の評価(evaluate.py)は
  このレーティングに対する最尤推定なので、プールを変えたら必ず再実行して尺度を合わせること。
"""
import argparse
import concurrent.futures as cf
import itertools
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_match import run_match  # noqa: E402


def one(a, b, seed, steps):
    r, _ = run_match(a, b, seed, steps)
    w = r["winner"]
    s = 0.5 if w is None else (1.0 if w == 0 else 0.0)
    return a, b, s, r["statuses"], r["final_money"]


def bt_fit(names, wins, iters=500, prior=0.5):
    """wins[i][j] = i が j に勝った回数(引き分けは0.5ずつ)。MM 法(Hunter 2004)。
    prior: 各ペアに仮想的な勝ち/負けを prior ずつ足す(全敗/全勝の相手で MLE が発散するのを防ぐ正則化)。"""
    n = len(names)
    wins = [[wins[i][j] + (prior if i != j else 0.0) for j in range(n)] for i in range(n)]
    p = [1.0] * n
    for _ in range(iters):
        new = []
        for i in range(n):
            w_i = sum(wins[i][j] for j in range(n) if j != i)
            denom = 0.0
            for j in range(n):
                if j == i:
                    continue
                g = wins[i][j] + wins[j][i]
                if g > 0:
                    denom += g / (p[i] + p[j])
            new.append(w_i / denom if denom > 0 else p[i])
        s = sum(new) / n
        p = [x / s for x in new]
    return [400 * math.log10(max(x, 1e-12)) for x in p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", required=True)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--seed-base", type=int, default=5000)
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--extra", default="", help="プール外で一緒に回す相手(カンマ区切り)")
    ap.add_argument("--write", action="store_true", help="プール JSON に rating を書き戻す")
    ap.add_argument("--prior", type=float, default=0.5, help="BT の仮想勝敗(正則化)。全敗相手の発散防止")
    ap.add_argument("--refit", metavar="ROUNDROBIN_JSON",
                    help="試合を回さず、保存済み records/pool_roundrobin.json の勝敗から "
                         "レーティングだけ計算し直す。総当たりが終わったのに後続の処理が落ちた"
                         "ときに 1872 戦を捨てないための入口(2026-09-10 追加)。"
                         "保存時の相手集合が今のプールと違えば中止する(fail-closed)。")
    args = ap.parse_args()

    pool_path = Path(args.pool)
    pool = json.loads(pool_path.read_text())
    entries = [e for e in pool["opponents"] if e.get("enabled", True)]
    paths = [e["path"] for e in entries]
    extras = [x.strip() for x in args.extra.split(",") if x.strip()]
    all_paths = paths + [x for x in extras if x not in paths]
    if len(all_paths) < 2 or len(set(all_paths)) != len(all_paths):
        sys.exit("プールは重複なしで2体以上必要")
    if args.prior <= 0:
        sys.exit("--prior は正の値")
    idx = {p: i for i, p in enumerate(all_paths)}
    n = len(all_paths)
    wins = [[0.0] * n for _ in range(n)]
    errors = {p: 0 for p in all_paths}

    if args.refit:
        saved = json.loads(Path(args.refit).read_text())
        if saved.get("agents") != all_paths:
            sys.exit("--refit 中止: 保存時の相手集合が今のプールと違う\n"
                     f"  保存: {saved.get('agents')}\n  現在: {all_paths}")
        wins = [[float(x) for x in row] for row in saved["wins"]]
        errors = {p: int((saved.get("errors") or {}).get(p, 0)) for p in all_paths}
        args.seeds = saved.get("seeds", args.seeds)
        args.seed_base = saved.get("seed_base", args.seed_base)
        print(f"  refit: {args.refit} ({saved.get('ts')}) の勝敗から再計算", file=sys.stderr)
        return _finish(args, pool, pool_path, all_paths, idx, n, wins, errors, extras, [], time.time())

    tasks = [(a, b, args.seed_base + s, args.steps)
             for a, b in itertools.permutations(all_paths, 2)
             for s in range(args.seeds)]
    # permutations で (a,b),(b,a) 両方入る = 両側対戦
    t0 = time.time()
    with cf.ProcessPoolExecutor(max_workers=args.jobs) as ex:
        futs = [ex.submit(one, *t) for t in tasks]
        for i, f in enumerate(cf.as_completed(futs), 1):
            a, b, s, st, _ = f.result()
            wins[idx[a]][idx[b]] += s
            wins[idx[b]][idx[a]] += 1 - s
            if st[0] != "DONE":
                errors[a] += 1
            if st[1] != "DONE":
                errors[b] += 1
            if i % 50 == 0 or i == len(futs):
                print(f"  {i}/{len(futs)} games", file=sys.stderr)

    return _finish(args, pool, pool_path, all_paths, idx, n, wins, errors, extras, tasks, t0)


def _finish(args, pool, pool_path, all_paths, idx, n, wins, errors, extras, tasks, t0):
    # 生データを先に保存(フィットが失敗しても総当たり結果を失わない)。
    # 失わないために保存しているので、使う入口が --refit（2026-09-10 追加）。
    rr_out = Path(__file__).resolve().parent.parent / "records/pool_roundrobin.json"
    rr_out.parent.mkdir(parents=True, exist_ok=True)
    if not args.refit:  # refit は自分が読んだファイルを上書きしない
        rr_out.write_text(json.dumps({"agents": all_paths, "wins": wins, "errors": errors,
                                      "seeds": args.seeds, "seed_base": args.seed_base,
                                      "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, indent=1))
    ratings = bt_fit(all_paths, wins, prior=args.prior)
    if "starter" in idx:
        anchor = ratings[idx["starter"]]
        ratings = [r - anchor for r in ratings]
    else:
        m = sum(ratings) / n
        ratings = [r - m for r in ratings]

    print(f"\nround-robin: {len(tasks)} games in {time.time()-t0:.0f}s")
    print(f"{'agent':50s} {'rating':>8s} {'W':>7s} {'L':>7s} err")
    for p in sorted(all_paths, key=lambda x: -ratings[idx[x]]):
        i = idx[p]
        w = sum(wins[i]); l = sum(wins[j][i] for j in range(n))
        print(f"{p:50s} {ratings[i]:8.1f} {w:7.1f} {l:7.1f} {errors[p]}")

    if args.write and any(errors.values()):
        sys.exit("ERROR/TIMEOUT を含む試合があるためレーティングを書き戻さない(records/pool_roundrobin.json は保存済み)")
    if args.write:
        for e in pool["opponents"]:
            if e["path"] in idx:
                e["rating"] = round(ratings[idx[e["path"]]], 1)
                e["rated_games"] = int(sum(wins[idx[e["path"]]]) + sum(wins[j][idx[e["path"]]] for j in range(n)))
        pool["rated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        pool["rated_seeds"] = args.seeds
        pool["rated_seed_base"] = args.seed_base
        pool["rated_steps"] = args.steps
        pool["rated_prior"] = args.prior
        pool["rated_extra"] = extras
        pool_path.write_text(json.dumps(pool, indent=1, ensure_ascii=False))
        print(f"written: {pool_path}")


if __name__ == "__main__":
    main()
