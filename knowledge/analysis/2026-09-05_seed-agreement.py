"""使い捨て(計画 §1-B): 先頭 N シードのゲート判定が seeds50 の判定とどれだけ一致するか。

既存の records/eval_*.json（seeds50・同一 seed_base）を切り詰めて再計算するだけ。
新規に試合は回さない。結果は knowledge/analysis/ にまとめる。
"""
import itertools
import json, sys
from pathlib import Path
sys.path.insert(0, "harness")
from evaluate import paired_delta, fit_rating  # noqa: E402

ROOT = Path(".")
# 4 世代とも同じプール SHA・同じ seed_base=1000・同じ 50 シードで評価済みなので、
# どの順序対も「対応付き比較」として妥当（実際に夜間で使った 3 対に加え、全 12 対で測る）。
GENS = ["gen0013", "gen0018", "gen0022", "gen0023"]
PAIRS = [(c, b) for c, b in itertools.permutations(GENS, 2)]
SUBSETS = [8, 12, 24, 50]


def load(g):
    return json.loads((ROOT / f"records/eval_{g}.json").read_text())


def rating_of(ev, games):
    opps = ev["opponents"]
    inputs = [(opps[g["opponent"]]["rating"], g["score"]) for g in games
              if opps.get(g["opponent"], {}).get("rating") is not None]
    return fit_rating(inputs)


def verdict(cand, base, n):
    """先頭 n シードだけで gate.pass 相当を再計算する。"""
    seeds = sorted({g["seed"] for g in cand["games"]})[:n]
    keep = set(seeds)
    # 相手集合をベースラインと揃える（候補側に champion 等の追加相手がいる場合がある）
    pool_paths = {p for p in base["opponents"] if p in cand["opponents"]}
    cg = [g for g in cand["games"] if g["seed"] in keep and g["opponent"] in pool_paths]
    bg = [g for g in base["games"] if g["seed"] in keep and g["opponent"] in pool_paths]
    rd = rating_of(cand, cg)
    rb = rating_of(base, bg)
    md = paired_delta(cg, bg)
    if rd is None or rb is None or md is None:
        return None, None, None
    delta = round(rd - rb, 1)
    return bool(delta > 0 and md["ci95"][0] > 0), delta, md


print(f"{'pair':22} {'N':>3}  {'gate':>6}  {'rating_delta':>12}  {'money mean':>11}  CI95")
agree = {n: [0, 0] for n in SUBSETS if n != 50}
detail, signs = {}, {}
for c, b in PAIRS:
    cand, base = load(c), load(b)
    truth, _, _ = verdict(cand, base, 50)   # 正解を先に確定させる
    key = f"{c}|{b}"
    detail[key], signs[key] = {}, {}
    for n in SUBSETS:
        v, delta, md = verdict(cand, base, n)
        detail[key][n] = v
        signs[key][n] = (md["mean"] > 0) if md else None
        line = (f"{c+' vs '+b:22} {n:>3}  {str(v):>6}  {delta:>12}  "
                f"{md['mean']:>11}  {md['ci95']}")
        if n != 50 and v is not None:
            agree[n][1] += 1
            if v == truth:
                agree[n][0] += 1
                line += "  ←一致"
            else:
                line += "  ←**不一致**"
        print(line)
    print()

print("-- 一致率（seeds50 の gate.pass と同じ判定を出した割合）")
for n, (ok, tot) in agree.items():
    print(f"  先頭 {n:>2} シード: {ok}/{tot}")
print()
print("-- 内訳（誤りの向き）")
for n in [x for x in SUBSETS if x != 50]:
    fp = sum(1 for k in detail if detail[k][n] is True and detail[k][50] is False)
    fn = sum(1 for k in detail if detail[k][n] is False and detail[k][50] is True)
    print(f"  先頭 {n:>2}: 偽の昇格(50では非昇格) {fp} 件 / 見逃し(50では昇格) {fn} 件")
print()
print("-- 資金差の符号が seeds50 と一致した割合（『方向』の安定性）")
for n in [x for x in SUBSETS if x != 50]:
    ok = sum(1 for k in signs if signs[k][n] is not None and signs[k][50] is not None
             and signs[k][n] == signs[k][50])
    tot = sum(1 for k in signs if signs[k][n] is not None and signs[k][50] is not None)
    print(f"  先頭 {n:>2} シード: {ok}/{tot}")
