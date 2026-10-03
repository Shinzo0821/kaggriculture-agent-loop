#!/usr/bin/env python
"""ミクロ監査（試作）: リプレイから unit-hour 単位の無駄・タイル利用率・日内タイムラインを出す。
usage: micro_audit.py replay.json --player 0
"""
import argparse, collections, json, statistics

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
SHED = {(4, 4), (5, 4), (4, 5), (5, 5)}


def tile_at(farm, x, y):
    try:
        return farm["tiles"][y][x]
    except Exception:
        return "LOCKED"


def classify(op, tile, inv, pos):
    """(category, noop_reason)"""
    name = op[0] if op else "PASS"
    if name in MOVES:
        return "MOVE", None
    if name == "PASS":
        return "PASS", None
    if name in ("PICKUP", "DROP") or (name == "PLACE" and not (isinstance(tile, dict) and tile.get("kind") in ("PASTURE", "COOP"))):
        if pos not in SHED:
            return name, "not_shed_adjacent"
        if name == "PICKUP" and len(op) > 1 and op[1] == "WHEAT":
            return name, None
        return name, None
    if tile == "LOCKED":
        return name, "locked_tile"
    if name == "WATER":
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return name, "no_plant"
        if tile.get("watered_today"):
            return name, "already_watered"
        return name, None
    if name == "FEED":
        if not (isinstance(tile, dict) and tile.get("animal")):
            return name, "no_animal"
        if tile.get("fed_today"):
            return name, "already_fed"
        if inv.get("WHEAT", 0) <= 0:
            return name, "no_wheat"
        return name, None
    if name == "CARE":
        if not (isinstance(tile, dict) and tile.get("animal")):
            return name, "no_animal"
        if tile.get("cared_today"):
            return name, "already_cared"
        return name, None
    if name == "HARVEST":
        if not isinstance(tile, dict) or tile.get("yield_units", 0) <= 0:
            return name, "nothing_to_harvest"
        return name, None
    if name == "COLLECT_FERTILIZER":
        if not (isinstance(tile, dict) and tile.get("fertilizer_available")):
            return name, "no_fertilizer"
        return name, None
    if name == "PLANT":
        if tile is not None:
            return name, "tile_occupied"
        return name, None
    if name in ("BUILD_PASTURE", "BUILD_COOP"):
        if tile is not None:
            return name, "tile_occupied"
        return name, None
    if name == "FERTILIZE":
        if not (isinstance(tile, dict) and tile.get("kind") == "PLANT"):
            return name, "no_plant"
        if inv.get("FERTILIZER", 0) <= 0:
            return name, "no_fertilizer_inv"
        return name, None
    if name == "DIG":
        return name, None
    if name == "PLACE":
        return name, None
    return name, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--player", type=int, default=0)
    ap.add_argument("--days", default="")
    a = ap.parse_args()
    p = a.player
    r = json.load(open(a.replay))
    steps = r["steps"]
    T = len(steps)
    days = T // 24

    per_day = []
    tile_prod_days = collections.Counter()
    tile_unlocked_days = collections.Counter()
    harvest_plant = collections.defaultdict(list)  # crop -> yields
    harvest_animal = collections.defaultdict(list)
    fert_total = 0
    noop_total = collections.Counter()
    mba = collections.Counter()            # productive action の直前に何歩歩いたか (hands のみ)
    harv_watered = collections.Counter()   # one-time crop の HARVEST 時に当日水やり済みか
    since_move = collections.defaultdict(int)
    for d in range(days):
        acts = collections.Counter()
        noops = collections.Counter()
        last_hour = {"FEED": -1, "WATER": -1, "CARE": -1, "any": -1}
        first_prod_hour = []  # per hand
        moves_per_unit = collections.Counter()
        prod_per_unit = collections.Counter()
        reversals = 0
        prev_move = {}
        plant_fail = 0
        hand_hours = 0
        for h in range(24):
            t = d * 24 + h
            if t == 0:
                continue
            pre = steps[t - 1][p]["observation"]
            post = steps[t][p]["observation"]
            act = steps[t][p].get("action") or {}
            farm = pre["farms"][p]
            priv = pre.get("private") or {}
            invs = priv.get("inventories") or []
            units = [("F", tuple(farm["farmer"]))] + [("H%d" % i, tuple(hp)) for i, hp in enumerate(farm.get("hands") or [])]
            ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
            for ui, (uname, pos) in enumerate(units):
                op = ops[ui] if ui < len(ops) else ["PASS"]
                if not op:
                    op = ["PASS"]
                inv = invs[ui] if ui < len(invs) else {}
                tile = tile_at(farm, pos[0], pos[1])
                cat, why = classify(op, tile, inv, pos)
                hand_hours += 1
                if cat == "MOVE":
                    acts["MOVE"] += 1
                    moves_per_unit[uname] += 1
                    since_move[uname] += 1
                    opp = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}
                    if prev_move.get(uname) == opp[op[0]]:
                        reversals += 1
                    prev_move[uname] = op[0]
                    continue
                prev_move[uname] = None
                if cat == "PASS":
                    acts["PASS"] += 1
                    continue
                if why:
                    noops[cat + ":" + why] += 1
                    acts["NOOP"] += 1
                    continue
                # PLANT の種不足失敗: post タイルが None のまま
                if cat == "PLANT":
                    if tile_at(post["farms"][p], pos[0], pos[1]) is None:
                        plant_fail += 1
                        noops["PLANT:seed_blocked"] += 1
                        acts["NOOP"] += 1
                        continue
                acts[cat] += 1
                prod_per_unit[uname] += 1
                if uname != "F" and cat not in ("PICKUP", "DROP", "PLACE"):
                    mba[min(since_move[uname], 9)] += 1
                since_move[uname] = 0
                if cat in last_hour:
                    last_hour[cat] = h
                last_hour["any"] = h
                if cat == "HARVEST":
                    if tile.get("kind") == "PLANT":
                        harvest_plant[tile["crop"]].append((pre["day"] - tile["planted_day"], tile["yield_units"]))
                        harv_watered[(tile["crop"], bool(tile.get("watered_today")))] += 1
                    else:
                        harvest_animal[tile["animal"]].append(tile["yield_units"])
                if cat == "FERTILIZE":
                    fert_total += 1
        # EOD state
        eod = steps[min(d * 24 + 23, T - 1)][p]["observation"]
        farm = eod["farms"][p]
        priv = eod.get("private") or {}
        n_prod_tiles = 0
        n_unlocked = 0
        weeds = 0
        empty = 0
        for y, row in enumerate(farm["tiles"]):
            for x, tl in enumerate(row):
                if tl == "LOCKED":
                    continue
                n_unlocked += 1
                tile_unlocked_days[(x, y)] += 1
                if isinstance(tl, dict):
                    if tl.get("kind") == "PLANT" or tl.get("animal"):
                        n_prod_tiles += 1
                        tile_prod_days[(x, y)] += 1
                    elif tl.get("kind") == "WEED":
                        weeds += 1
                    else:
                        empty += 1  # empty pasture
                else:
                    empty += 1
        seeds_idle = sum((priv.get("seeds") or {}).values())
        shed = priv.get("shed") or {}
        for k, v in noops.items():
            noop_total[k] += v
        per_day.append(dict(day=d, hh=hand_hours, acts=acts, noops=noops, last=last_hour,
                            reversals=reversals, n_prod=n_prod_tiles, n_unlocked=n_unlocked,
                            weeds=weeds, empty=empty, seeds_idle=seeds_idle,
                            shed_items=sum(v for k, v in shed.items() if k not in ("WHEAT",)),
                            money=farm["money"], hands=len(farm.get("hands") or [])))

    print(f"== player {p}  ({a.replay})")
    print("day hh  MOVE PASS NOOP prod  move% pass% | lastFEED lastWATER lastCARE lastANY | rev | tiles prod/unlocked weeds empty | seeds_idle shed | money")
    for r_ in per_day:
        ac = r_["acts"]
        prod = sum(v for k, v in ac.items() if k not in ("MOVE", "PASS", "NOOP"))
        hh = r_["hh"] or 1
        L = r_["last"]
        print(f"d{r_['day']:2d} {hh:3d} {ac['MOVE']:4d} {ac['PASS']:4d} {ac['NOOP']:4d} {prod:4d}  {100*ac['MOVE']/hh:4.0f}% {100*ac['PASS']/hh:4.0f}% | "
              f"{L['FEED']:6d} {L['WATER']:8d} {L['CARE']:8d} {L['any']:7d} | {r_['reversals']:3d} | "
              f"{r_['n_prod']:3d}/{r_['n_unlocked']:3d} {r_['weeds']:3d} {r_['empty']:3d} | {r_['seeds_idle']:4d} {r_['shed_items']:4d} | {r_['money']:7.0f}")
    print("-- noop 合計:", dict(noop_total.most_common()))
    print("-- FERTILIZE 合計:", fert_total)
    n_mba = sum(mba.values()) or 1
    print(f"-- hands の productive action 直前の歩数 0..9+: {[mba[i] for i in range(10)]}"
          f"  (3歩以上: {100*sum(v for k, v in mba.items() if k >= 3)/n_mba:.0f}%)")
    print("-- HARVEST 時に当日水やり済みか (crop, watered_today):", dict(harv_watered))
    for crop, lst in harvest_plant.items():
        ys = [y for _, y in lst]
        ages = [ag for ag, _ in lst]
        print(f"-- HARVEST {crop}: n={len(lst)} yield平均={statistics.mean(ys):.2f} (分布 {collections.Counter(ys).most_common()}) age平均={statistics.mean(ages):.1f}")
    for an, ys in harvest_animal.items():
        print(f"-- HARVEST {an}: n={len(ys)} yield平均={statistics.mean(ys):.2f} 分布 {collections.Counter(ys).most_common()}")
    # tile utilization
    never = sorted(t for t in tile_unlocked_days if tile_prod_days[t] == 0)
    low = sorted((t, tile_prod_days[t], tile_unlocked_days[t]) for t in tile_unlocked_days
                 if 0 < tile_prod_days[t] < 0.5 * tile_unlocked_days[t])
    tot_u = sum(tile_unlocked_days.values())
    tot_p = sum(tile_prod_days.values())
    print(f"-- タイル利用率(生産タイル日/解放タイル日): {tot_p}/{tot_u} = {100*tot_p/tot_u:.0f}%")
    print(f"-- 一度も使わなかった解放タイル: {never}")
    print(f"-- 利用率<50%: {low}")
    # utilization map (days productive) for the 10x10
    print("-- 利用日数マップ (x→, y↓):")
    for y in range(10):
        print("   " + " ".join(f"{tile_prod_days[(x, y)]:2d}" if tile_unlocked_days[(x, y)] else " ." for x in range(10)))


if __name__ == "__main__":
    main()
