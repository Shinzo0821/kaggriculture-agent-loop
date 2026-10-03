"""Track 2a 設計判定用: 「その日誰にも実行されなかった PLANT」(never-PLANT) の作物内訳・
メロン第 2 波の植付日・種/現金律速の切り分け・メロン販売の位相。

`2026-09-20_destination_inventory.py` の agent 再実行（todo スナップショット）をそのまま使う。
資金・勝敗の判断には使わない（決定論的な行動会計だけ）。

使い方:
  .venv/bin/python knowledge/analysis/2026-09-20_track2a_never_plant.py records/di5[89]_*_replay.json
  .venv/bin/python knowledge/analysis/2026-09-20_track2a_never_plant.py records/t2a_6[02]_7turn_s*_replay.json
世代はファイル名から引く（di58/di59/t2a_60/t2a_62/smoke_gen00NN）。`--agent` で明示もできる。
"""
import sys, os, re, json, argparse, collections, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
spec = importlib.util.spec_from_file_location(
    "di", os.path.join(HERE, "2026-09-20_destination_inventory.py"))
di = importlib.util.module_from_spec(spec)
spec.loader.exec_module(di)
MOVES = di.MOVES


def gen_of(base):
    if "di58" in base:
        return "gen0058"
    if "di59" in base:
        return "gen0059"
    m = re.search(r"gen00\d\d|t2a_(\d\d)", base)
    if not m:
        raise SystemExit("世代をファイル名から引けない: %s（--agent を使う）" % base)
    return m.group(0) if m.group(0).startswith("gen") else "gen00" + m.group(1)


def analyse(rp, agent_path):
    mod = di.load_patched_agent(agent_path)
    steps = json.load(open(rp))["steps"]
    did = di.build_did(steps, 0)
    plans = mod.CROP_PLANS
    planted = collections.defaultdict(list)
    buys = collections.defaultdict(collections.Counter)
    sold = collections.Counter(); rev = collections.Counter()
    for t in range(1, len(steps)):
        pre = steps[t - 1][0]["observation"]; act = steps[t][0].get("action") or {}
        farm = pre["farms"][0]; d = pre["day"]
        units = [tuple(farm["farmer"])] + [tuple(h) for h in (farm.get("hands") or [])]
        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        for ui, o in enumerate(ops):
            if o and o[0] == "PLANT" and ui < len(units):
                planted[units[ui]].append((d, o[1]))
        price = (pre["market"]["prices"] or {}).get("MELON", 0)
        for o in (act.get("market") or []):
            if o and o[0] == "BUY_SEED":
                buys[d][o[1]] += o[2]
            if o and o[0] == "SELL" and o[1] == "MELON":
                sold[d] += o[2]; rev[d] += o[2] * price
    # メロン第 2 波（12 枚）の最初の植付日
    w2 = collections.Counter()
    for x, y, fd in plans["MELON"]["tiles"]:
        days = sorted(d for d, c in planted[(x, y)] if c == "MELON" and d >= 10)
        w2[days[0] if days else "never"] += 1
    # イチゴ計画タイルの from_day からの遅延
    st = collections.Counter()
    for x, y, fd in plans["STRAWBERRY"]["tiles"]:
        days = sorted(d for d, c in planted[(x, y)] if c == "STRAWBERRY" and d >= fd)
        st[(days[0] - fd) if days else "never"] += 1
    # never-PLANT（d10-25・遊休ユニット到達圏・その日誰も植えず）作物別、種律速の切り分け
    never = {}; lab = collections.Counter()
    for t in range(1, len(steps)):
        pre = steps[t - 1][0]["observation"]; act = steps[t][0].get("action") or {}
        day, hour = pre["day"], pre["hour"]
        if not (10 <= day <= 25):
            continue
        farm = pre["farms"][0]; seeds = (pre.get("private") or {}).get("seeds") or {}
        units = [tuple(farm["farmer"])] + [tuple(h) for h in (farm.get("hands") or [])]
        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        ops = [(o or ["PASS"]) for o in ops]
        while len(ops) < len(units):
            ops.append(["PASS"])
        idle = [ui for ui, _ in enumerate(units) if ops[ui][0] in MOVES or ops[ui][0] == "PASS"]
        if not idle:
            continue
        mod.__dict__.pop("_TODO_SNAP", None); mod.agent(pre)
        snap = mod.__dict__.get("_TODO_SNAP") or []
        left = 24 - hour
        by_crop = collections.defaultdict(list)
        for _p, x, y, op, need in snap:
            if op[0] == "PLANT":
                by_crop[op[1]].append((x, y))
        for crop, tiles in by_crop.items():
            nv = [(x, y) for x, y in tiles
                  if any(abs(units[ui][0] - x) + abs(units[ui][1] - y) + 1 <= left for ui in idle)
                  and not any(h > hour and o == "PLANT" for h, u, o in did.get((day, (x, y)), []))]
            for x, y in nv:
                never[(day, x, y)] = crop
            if nv and crop in ("MELON", "STRAWBERRY"):
                k = ("labor" if seeds.get(crop, 0) >= len(tiles)
                     else ("partial" if seeds.get(crop, 0) > 0 else "seed0"))
                lab[(crop, k)] += len(nv)
    np_ = collections.Counter(never.values())
    npd = collections.defaultdict(collections.Counter)
    for (d, x, y), c in never.items():
        npd[c][d] += 1
    seeds13 = (steps[13 * 24][0]["observation"].get("private") or {}).get("seeds") or {}
    tail = sum(v for d, v in sold.items() if d >= 20)
    tail_rev = sum(v for d, v in rev.items() if d >= 20)
    return dict(w2=w2, st=st, never=np_, never_day=npd, lab=lab,
                buys={d: dict(c) for d, c in sorted(buys.items()) if 8 <= d <= 13},
                dead_melon_seed_d13=seeds13.get("MELON", 0),
                melon_sold={d: v for d, v in sorted(sold.items())},
                melon_tail=(tail, tail_rev / tail if tail else 0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replays", nargs="+")
    ap.add_argument("--agent")
    a = ap.parse_args()
    W2 = collections.Counter(); ST = collections.Counter(); NP = collections.Counter(); LAB = collections.Counter()
    for rp in a.replays:
        base = os.path.basename(rp)
        agent = a.agent or os.path.join(ROOT, "agents", gen_of(base), "main.py")
        r = analyse(rp, agent)
        print(base)
        print("   第2波メロン 植付日:", dict(r["w2"]), "| イチゴ遅延(日):", dict(r["st"]))
        print("   never-PLANT d10-25 作物別:", dict(r["never"]), "| 種律速の切り分け:", dict(r["lab"]))
        print("   BUY_SEED d8-13:", r["buys"], "| d13 死にメロン種:", r["dead_melon_seed_d13"])
        print("   MELON SELL 日別:", r["melon_sold"], "| d20+ %d 個 平均 $%.0f" % r["melon_tail"])
        W2.update(r["w2"]); ST.update(r["st"]); NP.update(r["never"]); LAB.update(r["lab"])
    print("== 合計 第2波メロン:", dict(W2))
    print("== 合計 イチゴ遅延:", dict(ST))
    print("== 合計 never-PLANT:", dict(NP), "| WHEAT 比 %.1f%%" % (100.0 * NP["WHEAT"] / max(1, sum(NP.values()))))
    print("== 合計 種律速の切り分け:", dict(LAB))


if __name__ == "__main__":
    main()
