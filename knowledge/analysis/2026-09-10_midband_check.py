import json, math, statistics as st, collections, sys, os
from pathlib import Path

MID = ["gen0044", "gen0045", "gen0051"]

def load(path):
    d = json.load(open(path))
    by = collections.defaultdict(lambda: collections.defaultdict(list))  # opp -> seed -> [win,...]
    for g in d["games"]:
        opp = g["opponent"].split("/")[1] if "/" in g["opponent"] else g["opponent"]
        by[opp][g["seed"]].append((g["cand_side"], 1 if g["cand_final"] > g["opp_final"] else 0,
                                   g["cand_final"] - g["opp_final"]))
    return by

def seed_ci(by, opp):
    per = [st.mean(w for _, w, _ in v) for v in by[opp].values()]
    n = len(per); mu = st.mean(per)
    sd = st.stdev(per) if n > 1 else 0.0
    se = sd / math.sqrt(n)
    return mu, (mu - 1.96*se, mu + 1.96*se), n

def sides(by, opp):
    s = collections.defaultdict(list)
    for v in by[opp].values():
        for side, w, _ in v: s[side].append(w)
    return {k: (sum(v), len(v)) for k, v in sorted(s.items())}

runs = [(f, Path(f).stem.replace("audit_mid_", "")) for f in sorted(sys.argv[1:]) if os.path.exists(f)]
print("=== 各候補 × 中間帯候補の勝率（シード単位 CI・席別）===")
print(f"{'run':22} {'相手':10} {'勝率':>7} {'シード単位95%CI':>20} {'side0':>9} {'side1':>9} {'マージン':>10}")
data = {}
for f, label in runs:
    by = load(f); data[label] = by
    for opp in MID:
        if opp not in by: continue
        mu, ci, n = seed_ci(by, opp)
        sd_ = sides(by, opp)
        marg = st.mean(m for v in by[opp].values() for _, _, m in v)
        s0 = f"{sd_[0][0]}/{sd_[0][1]}" if 0 in sd_ else "-"
        s1 = f"{sd_[1][0]}/{sd_[1][1]}" if 1 in sd_ else "-"
        print(f"{label:22} {opp:10} {100*mu:6.1f}% {f'[{100*ci[0]:.1f}, {100*ci[1]:.1f}]':>20} {s0:>9} {s1:>9} {marg:10,.0f}")
    print()

print("=== (a) 再現性: gen0048 を別 seed_base で ===")
for opp in MID:
    r = []
    for lab in ("gen0048_sb1000", "gen0048_sb5000"):
        if lab in data and opp in data[lab]:
            mu, ci, _ = seed_ci(data[lab], opp); r.append((lab, mu, ci))
    if len(r) == 2:
        d = r[1][1] - r[0][1]
        print(f"  {opp}: sb1000 {100*r[0][1]:.1f}% [{100*r[0][2][0]:.1f},{100*r[0][2][1]:.1f}] → "
              f"sb5000 {100*r[1][1]:.1f}% [{100*r[1][2][0]:.1f},{100*r[1][2][1]:.1f}]  差 {100*d:+.1f}pt")

print("\n=== (b) 識別力: 中間帯は「良い候補」と「棄却された候補」を分けるか ===")
print("  gen0048=王者 / gen0052=非昇格(検出不能) / gen0053=明確に棄却(全体マージン -681.8 CI 全域<0) / gen0036=2 世代前の旧型")
print(f"  {'候補':16} " + " ".join(f"{o:>12}" for o in MID) + f" {'3体平均':>10}")
for lab in sorted(data):
    if not all(o in data[lab] for o in MID): continue
    ms = [seed_ci(data[lab], o)[0] for o in MID]
    print(f"  {lab:16} " + " ".join(f"{100*m:11.1f}%" for m in ms) + f" {100*st.mean(ms):9.1f}%")

print("\n=== (c) 冗長性: 3 体の勝敗はシードごとに揃って動くか（揃うなら 1 体で足りる）===")
for lab in sorted(data):
    if not all(o in data[lab] for o in MID): continue
    seeds = sorted(set(data[lab][MID[0]]))
    vecs = {o: [st.mean(w for _, w, _ in data[lab][o][s]) for s in seeds] for o in MID}
    print(f"  {lab}:", end=" ")
    for i in range(len(MID)):
        for j in range(i+1, len(MID)):
            a, b = vecs[MID[i]], vecs[MID[j]]
            ma, mb = st.mean(a), st.mean(b)
            num = sum((x-ma)*(y-mb) for x, y in zip(a, b))
            den = math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
            r = num/den if den else float('nan')
            print(f"{MID[i][-4:]}~{MID[j][-4:]} r={r:+.2f}", end="  ")
    print()
