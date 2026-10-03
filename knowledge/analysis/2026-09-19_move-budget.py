#!/usr/bin/env python
"""MOVE 予算の分解: 3,275 unit-hour の MOVE が何に使われているかをリプレイから数える。

背景: `knowledge/analysis/2026-09-19_gen0051-vs-7turn.md` §3-3 の全量会計で、
王者 gen0051 は相手(dmitriigluzdov_7turn)より総 unit-hour が +491 多いのに
PASS に +892・MOVE に +484 を余計に使い、生産行動を約 760 回少なく打っている。
MOVE は 3,275 unit-hour (45.9%) で最大の支出項目。**その中身を出す**のが本スクリプト。

数え方（すべてリプレイ由来。エージェントを再実行しない＝新規対戦ゼロ）:
  - 1 unit-hour = 1 ユニット(farmer + hands)の 1 時間の行動。micro_audit.py と同じく
    「d 日 h 時の行動」は steps[d*24+h+1]["action"]、盤面は steps[d*24+h]["observation"]。
  - **MOVE 区間**: 同じユニットの、同じ日の中で連続する MOVE の並び。区間は最初の
    非 MOVE 行動で閉じ、その行動を「区間の終点行動」とする。日が終わるまで閉じなければ
    終点は END_OF_DAY（＝歩いたまま 1 日が終わった＝到達しなかった）。
  - **無駄足** = 終点行動が PASS の区間 ＋ END_OF_DAY の区間。どちらも「歩いたのに
    何も起きなかった時間」で、盤面だけから曖昧さなく決まる。
    END_OF_DAY が全損なのはエンジン規則から出る: `_end_of_day` は farmer を既定スポーンへ
    戻し `farm["hands"] = []` で hands を捨てる（kaggriculture.py 879-881）。
    **その日のうちに到達しなかった歩行は、翌朝には無かったことになる。**
    とくに h23 の MOVE は定義上 100% 捨て。
  - **迂回率** = 区間の歩数 / |start - end| の manhattan 距離。1.0 なら最短、
    大きいほど途中で目的地が変わった（追随した todo が入れ替わった）ことを意味する。

使い方:
  .venv/bin/python knowledge/analysis/2026-09-19_move-budget.py \
      records/probe_gen0051_vs_7turn_s5000_replay.json [--day 15] [--json]
"""
import argparse
import collections
import json
import statistics
import sys

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
SHED = {(4, 4), (5, 4), (4, 5), (5, 5)}
LOGISTICS = {"PICKUP", "DROP", "PLACE"}
# 「生産行動」= MOVE でも PASS でもない全行動（§3-3 の表と同じ集合）
# core = そのうち物流(PICKUP/DROP/PLACE)を除いた、盤面に直接価値を作る行動
CORE = {"WATER", "HARVEST", "PLANT", "FEED", "CARE", "FERTILIZE",
        "COLLECT_FERTILIZER", "DIG", "BUILD_PASTURE", "BUILD_COOP"}
CROPS_FIRST_YIELD = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}


def quad(x, y):
    return (0 if y < 5 else 2) + (0 if x < 5 else 1)


def tile_at(farm, x, y):
    try:
        return farm["tiles"][y][x]
    except Exception:
        return "LOCKED"


def dest_kind(farm, x, y):
    if (x, y) in SHED:
        return "SHED"
    t = tile_at(farm, x, y)
    if t == "LOCKED":
        return "LOCKED"
    if t is None:
        return "EMPTY"
    if isinstance(t, dict):
        if t.get("animal"):
            return "ANIMAL"
        if t.get("kind") == "PLANT":
            return "PLANT"
        if t.get("kind") == "WEED":
            return "WEED"
        return t.get("kind") or "OTHER"
    return "OTHER"


def board_work(farm, day, seeds_total):
    """盤面から「今できる仕事」を列挙する。(kind, x, y) のリスト。

    エージェントの todo 生成には依存しない（依存すると設計の自己弁護になる）。
    エンジン規則だけから決まるもの: 水やり待ち / 収穫可 / 未給餌 / 未世話 / 空きタイル(種あり) / 雑草。
    """
    out = []
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            if t == "LOCKED":
                continue
            if t is None:
                if seeds_total > 0:
                    out.append(("PLANTABLE", x, y))
                continue
            if not isinstance(t, dict):
                continue
            if t.get("animal"):
                if not t.get("fed_today"):
                    out.append(("FEEDABLE", x, y))
                if not t.get("cared_today"):
                    out.append(("CAREABLE", x, y))
                if t.get("yield_units", 0) > 0:
                    # 動物の収穫は gen0051 が価格床(SELL_FLOORS)で意図的に据え置く
                    # ことがある（収穫バンク）。作物と混ぜないよう別の種類にする。
                    out.append(("HARVEST_ANIMAL", x, y))
            elif t.get("kind") == "PLANT":
                if not t.get("watered_today"):
                    out.append(("WATERABLE", x, y))
                age = day - t.get("planted_day", day)
                if t.get("yield_units", 0) > 0 and age >= CROPS_FIRST_YIELD.get(t.get("crop"), 99):
                    out.append(("HARVEST_PLANT", x, y))
            elif t.get("kind") == "WEED":
                out.append(("DIGGABLE", x, y))
            elif t.get("kind") in ("PASTURE", "COOP") and not t.get("animal"):
                out.append(("PLACEABLE", x, y))
    return out


def analyse(steps, p, focus_day=15):
    total = len(steps)
    days = total // 24

    acts = collections.Counter()               # 行動カテゴリ -> unit-hour
    per_day = collections.defaultdict(collections.Counter)
    runs = []                                  # MOVE 区間
    edge_noop = 0                              # 盤端への MOVE（座標が動かない。h<23 でのみ判定可）
    h23_move = 0                               # h23 の MOVE = 日跨ぎのリセットで消える歩行
    h23_move_day = collections.Counter()
    quad_cross_hours = 0                       # 区間の start/end が別クアドラント
    quad_cross_by_day = collections.Counter()
    pass_events = []                           # PASS の文脈
    day_unit = collections.defaultdict(lambda: collections.Counter())   # (day, unit) -> stats
    focus_trace = collections.defaultdict(list)

    open_run = {}       # unit -> dict(start_pos, hours, path)
    prev_day = -1
    did = collections.defaultdict(list)   # (day, (x,y)) -> [(hour, unit, op)]
    stop_work = collections.Counter()     # 停止 1 回あたりの生産行動数の分布
    cur_stop = collections.Counter()      # unit -> 今の停止で打った手数
    shed_dist = collections.Counter()     # 生産行動のシェッドからの距離
    noop_move_ev = []   # 盤外 MOVE の現場（方向・座標）
    byunit = collections.defaultdict(collections.Counter)   # "F" / "H" -> 行動

    for t in range(1, total):
        pre = steps[t - 1][p]["observation"]
        act = steps[t][p].get("action") or {}
        day, hour = pre["day"], pre["hour"]
        farm = pre["farms"][p]
        priv = pre.get("private") or {}
        invs = priv.get("inventories") or []
        seeds_total = sum((priv.get("seeds") or {}).values())
        units = [("F", tuple(farm["farmer"]))] + [
            ("H%d" % i, tuple(hp)) for i, hp in enumerate(farm.get("hands") or [])
        ]
        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        # 次ステップの座標（盤外 MOVE の判定に使う）
        nxt = steps[t][p]["observation"]["farms"][p] if t < total else None
        nxt_units = [tuple(nxt["farmer"])] + [tuple(h) for h in (nxt.get("hands") or [])]

        if day != prev_day:
            # 日をまたぐ区間は閉じる（hands は daily reset で作り直される）
            for uname, r in open_run.items():
                r["end_kind"] = "END_OF_DAY"
                r["end_pos"] = r["path"][-1]
                runs.append(r)
            open_run = {}
            prev_day = day

        work = None
        # この時間に「誰かが実際に手を付けたタイル」= 取られている仕事
        busy = set()
        for ui2, (_u2, pos2) in enumerate(units):
            o2 = ops[ui2] if ui2 < len(ops) else ["PASS"]
            if o2 and o2[0] not in MOVES and o2[0] != "PASS":
                busy.add(pos2)
                did[(day, pos2)].append((hour, _u2, o2[0]))
        for ui, (uname, pos) in enumerate(units):
            op = ops[ui] if ui < len(ops) else ["PASS"]
            if not op:
                op = ["PASS"]
            name = op[0]
            cat = "MOVE" if name in MOVES else ("PASS" if name == "PASS" else name)
            acts[cat] += 1
            per_day[day][cat] += 1
            du = day_unit[(day, uname)]
            du[cat] += 1
            byunit["F" if ui == 0 else "H"][cat] += 1

            if cat == "MOVE":
                if hour == 23:
                    # 日跨ぎで farmer/hands がリセットされるので、この歩行は消える
                    h23_move += 1
                    h23_move_day[day] += 1
                    noop_move_ev.append(dict(day=day, hour=hour, unit=uname,
                                             pos=pos, dir=name))
                elif ui < len(nxt_units) and nxt_units[ui] == pos:
                    edge_noop += 1        # 盤端への MOVE（エンジンが無視する）
                r = open_run.get(uname)
                if r is None:
                    if work is None:
                        work = board_work(farm, day, seeds_total)
                    # 2026-09-19 c6 修正（gen0058 の Codex レビュー P1-1）:
                    # 旧 `23 - hour` は 1 少ない。時刻 hour のユニットは h..23 の
                    # **24 - hour 手**打てる（h23 にも 1 手ある）。距離 d の仕事は
                    # d + 1 <= 24 - hour で今日中に片付く（agent 側の
                    # `_owner_can_come` / 到達可能性ゲートと同じ式）。
                    # 旧値で出した「到達可能な代替が実在した 259-367 h」は
                    # **過小評価（保守側）**なので、結論の向きは変わらない。
                    left = 24 - hour            # 今日あと何手打てるか
                    reach = [1 for k, x, y in work
                             if (x, y) not in busy
                             and abs(pos[0] - x) + abs(pos[1] - y) + 1 <= left]
                    r = dict(day=day, unit=uname, start_hour=hour, start_pos=pos,
                             hours=0, path=[pos], start_kind=dest_kind(farm, *pos),
                             reachable_at_start=len(reach), left=left)
                    open_run[uname] = r
                r["hours"] += 1
                r["path"].append(pos)
                if uname in cur_stop:
                    stop_work[cur_stop.pop(uname)] += 1
                continue

            r = open_run.pop(uname, None)
            if r is not None:
                r["end_kind"] = cat
                r["end_pos"] = pos
                r["end_tile"] = dest_kind(farm, *pos)
                runs.append(r)

            if cat != "PASS":
                cur_stop[uname] += 1
                shed_dist[min(abs(pos[0] - sx) + abs(pos[1] - sy) for sx, sy in SHED)] += 1
            if cat == "PASS":
                if work is None:
                    work = board_work(farm, day, seeds_total)
                inv = invs[ui] if ui < len(invs) else {}
                dmin = {}
                dmin_free = {}     # 同じ時間に誰も手を付けていない仕事だけ
                has_animal = any(inv.get(a, 0) > 0 for a in ("COW", "SHEEP", "GOOSE"))
                for k, x, y in work:
                    # 持ち物が要る仕事は、その unit が持っていなければ「できる仕事」ではない
                    if k == "FEEDABLE" and inv.get("WHEAT", 0) <= 0:
                        continue
                    if k == "PLACEABLE" and not has_animal:
                        continue
                    d = abs(pos[0] - x) + abs(pos[1] - y)
                    if d < dmin.get(k, 99):
                        dmin[k] = d
                    if (x, y) not in busy and d < dmin_free.get(k, 99):
                        dmin_free[k] = d
                near = [(k, x, y) for k, x, y in work
                        if (x, y) not in busy and abs(pos[0] - x) + abs(pos[1] - y) <= 3
                        and not (k == "FEEDABLE" and inv.get("WHEAT", 0) <= 0)
                        and not (k == "PLACEABLE" and not has_animal)]
                pass_events.append(dict(
                    day=day, hour=hour, unit=uname, pos=pos, nwork=len(work),
                    near=near, is_farmer=(ui == 0),
                    dmin=dmin, dmin_free=dmin_free,
                    wheat=inv.get("WHEAT", 0), fert=inv.get("FERTILIZER", 0),
                    seeds=seeds_total,
                    kinds=collections.Counter(k for k, _x, _y in work),
                ))
            if day == focus_day:
                focus_trace[uname].append((hour, cat, pos))

        if day == focus_day:
            pass

    for uname, n in list(cur_stop.items()):
        stop_work[n] += 1
    for uname, r in open_run.items():
        r["end_kind"] = "END_OF_DAY"
        r["end_pos"] = r["path"][-1]
        runs.append(r)

    # 区間の派生量
    for r in runs:
        sp, ep = r["start_pos"], r.get("end_pos", r["path"][-1])
        r["net"] = abs(sp[0] - ep[0]) + abs(sp[1] - ep[1])
        r["detour"] = (r["hours"] / r["net"]) if r["net"] else None
        r["qcross"] = quad(*sp) != quad(*ep)
        if r["qcross"]:
            quad_cross_hours += r["hours"]
            quad_cross_by_day[r["day"]] += r["hours"]

    # PASS の近傍にあった仕事が、その日のうちに誰の手で片付いたか
    for e in pass_events:
        later_other = later_self = never = 0
        for _k, x, y in e["near"]:
            ev = [(h, u) for h, u, _o in did.get((e["day"], (x, y)), []) if h > e["hour"]]
            if not ev:
                never += 1
            elif any(u != e["unit"] for h, u in ev):
                later_other += 1
            else:
                later_self += 1
        e["near_n"] = len(e["near"])
        e["later_other"] = later_other
        e["later_self"] = later_self
        e["never"] = never

    return dict(acts=acts, per_day=per_day, runs=runs, edge_noop=edge_noop,
                h23_move=h23_move, h23_move_day=h23_move_day, pass_events=pass_events,
                stop_work=stop_work, shed_dist=shed_dist,
                day_unit=day_unit, focus_trace=focus_trace, byunit=byunit,
                noop_move_ev=noop_move_ev,
                quad_cross_hours=quad_cross_hours, quad_cross_by_day=quad_cross_by_day,
                days=days)


def work_actions(acts):
    return sum(v for k, v in acts.items() if k not in ("MOVE", "PASS"))


def core_actions(acts):
    return sum(v for k, v in acts.items() if k in CORE)


def report(res, label, focus_day, window=(11, 20)):
    acts = res["acts"]
    wa, ca = work_actions(acts), core_actions(acts)
    mv = acts["MOVE"]
    tot = sum(acts.values())
    print("=" * 78)
    print("[%s] total unit-hour %d / MOVE %d (%.1f%%) / PASS %d (%.1f%%) / work %d / core %d"
          % (label, tot, mv, 100 * mv / tot, acts["PASS"], 100 * acts["PASS"] / tot, wa, ca))
    print("  Q1 MOVE hours per work action = %.2f   per core action = %.2f"
          % (mv / max(wa, 1), mv / max(ca, 1)))
    lo, hi = window
    wmv = sum(res["per_day"][d]["MOVE"] for d in range(lo, hi + 1))
    wwa = sum(work_actions(res["per_day"][d]) for d in range(lo, hi + 1))
    wca = sum(core_actions(res["per_day"][d]) for d in range(lo, hi + 1))
    wpa = sum(res["per_day"][d]["PASS"] for d in range(lo, hi + 1))
    wtot = sum(sum(res["per_day"][d].values()) for d in range(lo, hi + 1))
    print("  Q1 d%d-d%d: unit-hour %d / MOVE %d (%.1f%%) / PASS %d / work %d -> %.2f hop/work, %.2f hop/core"
          % (lo, hi, wtot, wmv, 100 * wmv / max(wtot, 1), wpa, wwa,
             wmv / max(wwa, 1), wmv / max(wca, 1)))

    print("  -- 日次 (day: unit-hour MOVE PASS work  hop/work) --")
    for d in range(res["days"]):
        pd = res["per_day"][d]
        w = work_actions(pd)
        print("   d%-2d %4d %4d %4d %4d  %.2f" % (
            d, sum(pd.values()), pd["MOVE"], pd["PASS"], w, pd["MOVE"] / max(w, 1)))

    runs = res["runs"]
    print("  Q2 MOVE 区間 %d 本 / 総 %d unit-hour（acts の MOVE と一致すべき: %d）"
          % (len(runs), sum(r["hours"] for r in runs), mv))
    by_end = collections.Counter()
    hours_by_end = collections.Counter()
    for r in runs:
        by_end[r["end_kind"]] += 1
        hours_by_end[r["end_kind"]] += r["hours"]
    print("  終点行動別（区間数 / unit-hour / 平均長）:")
    for k, h in hours_by_end.most_common():
        print("    %-18s %4d 本 %5d h  平均 %.2f" % (k, by_end[k], h, h / by_end[k]))
    eod = [r for r in runs if r["end_kind"] == "END_OF_DAY"]
    if eod:
        have = sum(1 for r in eod if r.get("reachable_at_start", 0) > 0)
        hh = sum(r["hours"] for r in eod if r.get("reachable_at_start", 0) > 0)
        print("  Q2d 日跨ぎ未到達の区間 %d 本 %d h のうち、歩き出した時点で『今日中に到達して 1 手打てる"
              "空いた仕事』が在ったもの %d 本 %d h (%.0f%%)。歩き出した時の残り時間の中央値 %d h"
              % (len(eod), sum(r["hours"] for r in eod), have, hh, 100 * have / len(eod),
                 statistics.median([r.get("left", 0) for r in eod])))
        print("      歩き出した時刻の分布: %s"
              % dict(sorted(collections.Counter(r["start_hour"] for r in eod).items())))
    waste = hours_by_end["PASS"] + hours_by_end["END_OF_DAY"]
    print("  ★無駄足 = 終点PASS %d h + 日跨ぎ未到達(翌朝リセットで消える) %d h = %d h (MOVE の %.1f%%, 総の %.1f%%)"
          % (hours_by_end["PASS"], hours_by_end["END_OF_DAY"], waste,
             100 * waste / max(mv, 1), 100 * waste / max(tot, 1)))
    print("     うち h23 の MOVE（定義上 100%% 捨て） %d h ／ 盤端への no-op MOVE %d h"
          % (res["h23_move"], res["edge_noop"]))
    wwaste = sum(r["hours"] for r in runs
                 if lo <= r["day"] <= hi and r["end_kind"] in ("PASS", "END_OF_DAY"))
    wh23 = sum(res["h23_move_day"][d] for d in range(lo, hi + 1))
    print("     うち d%d-d%d: %d h (うち h23 %d h)" % (lo, hi, wwaste, wh23))

    # 目的地の種類
    dk = collections.Counter()
    for r in runs:
        if r["end_kind"] in ("PASS", "END_OF_DAY"):
            dk["(無駄足)"] += r["hours"]
        else:
            dk[r.get("end_tile", "?")] += r["hours"]
    print("  終点タイル種別の unit-hour:", dict(dk.most_common()))

    # 区間長の分布
    lens = collections.Counter(r["hours"] for r in runs)
    print("  区間長分布（長さ: 本数 / その長さが占める unit-hour）:")
    for L in sorted(lens):
        if L <= 12 or lens[L] > 3:
            print("    %2d: %4d 本 %5d h" % (L, lens[L], L * lens[L]))
    long_h = sum(L * n for L, n in lens.items() if L >= 4)
    print("    長さ>=4 の区間が %d h (MOVE の %.1f%%)" % (long_h, 100 * long_h / max(mv, 1)))

    # 迂回
    det = [r for r in runs if r["net"]]
    extra = sum(r["hours"] - r["net"] for r in det)
    print("  迂回（歩数 − 最短距離）合計 %d h。到達できた区間の平均迂回率 %.2f"
          % (extra, statistics.mean(r["detour"] for r in det) if det else 0))

    print("  Q2b 停止 1 回あたりの生産行動 = work / MOVE区間数 = %.2f（＝1 回止まって何手打つか）"
          % (wa / max(len(runs), 1)))
    sw = res["stop_work"]
    nstop = sum(sw.values())
    print("  Q4 停止サイズ（1 回止まって打った生産行動の数）の分布: %s"
          % {k: sw[k] for k in sorted(sw)})
    print("     停止 %d 回 / 1 手だけで歩き出した停止 %.0f%% / 3 手以上 %.0f%%"
          % (nstop, 100 * sw[1] / max(nstop, 1),
             100 * sum(v for k, v in sw.items() if k >= 3) / max(nstop, 1)))
    sd = res["shed_dist"]
    nsd = sum(sd.values())
    print("  Q4 生産行動のシェッドからの距離: 平均 %.2f / 分布 %s"
          % (sum(k * v for k, v in sd.items()) / max(nsd, 1), {k: sd[k] for k in sorted(sd)}))
    nm = res["noop_move_ev"]
    if nm:
        print("  Q2c h23 の MOVE %d h（翌朝 farmer は既定スポーン・hands は破棄）。ユニット: F %d / hands %d"
              % (len(nm), sum(1 for e in nm if e["unit"] == "F"),
                 sum(1 for e in nm if e["unit"] != "F")))
        print("      日 top5: %s" % collections.Counter(e["day"] for e in nm).most_common(5))
    bu = res["byunit"]
    for who in ("F", "H"):
        c = bu.get(who) or collections.Counter()
        tt = sum(c.values())
        if tt:
            print("  Q3b [%s] unit-hour %d / MOVE %d (%.0f%%) / PASS %d (%.0f%%) / work %d"
                  % ("farmer" if who == "F" else "hands", tt, c["MOVE"], 100 * c["MOVE"] / tt,
                     c["PASS"], 100 * c["PASS"] / tt, work_actions(c)))
    print("  Q3 クアドラント跨ぎ区間の unit-hour: %d (MOVE の %.1f%%)。d%d-d%d: %d"
          % (res["quad_cross_hours"], 100 * res["quad_cross_hours"] / max(mv, 1), lo, hi,
             sum(res["quad_cross_by_day"][d] for d in range(lo, hi + 1))))

    print("  Q3 d%d のユニット別（unit: MOVE / work / core / PASS / 訪問タイル数 / クアドラント数）:" % focus_day)
    for uname in sorted(res["day_unit"], key=lambda k: (k[0], k[1])):
        d, u = uname
        if d != focus_day:
            continue
        c = res["day_unit"][uname]
        tr = [x for x in res["focus_trace"][u]]
        tiles = {pos for _h, cat, pos in tr if cat not in ("MOVE", "PASS")}
        quads = {quad(*pos) for _h, cat, pos in tr if cat not in ("MOVE", "PASS")}
        print("    %-4s MOVE %2d  work %2d  core %2d  PASS %2d  tiles %2d  quads %s"
              % (u, c["MOVE"], work_actions(c), core_actions(c), c["PASS"],
                 len(tiles), sorted(quads)))

    # Q5 PASS の文脈
    pe = res["pass_events"]
    if pe:
        print("  Q5 PASS %d 件。時刻分布:" % len(pe))
        byh = collections.Counter(e["hour"] for e in pe)
        print("    " + " ".join("h%02d:%d" % (h, byh.get(h, 0)) for h in range(24)))
        wpe = [e for e in pe if lo <= e["day"] <= hi]
        for tag, subset in (("全期間", pe), ("d%d-d%d" % (lo, hi), wpe)):
            if not subset:
                continue
            nearest = []
            for e in subset:
                dm = e["dmin"]
                nearest.append(min(dm.values()) if dm else 99)
            has = sum(1 for n in nearest if n < 99)
            near3 = sum(1 for n in nearest if n <= 3)
            print("    [%s] n=%d / 盤上に仕事がある時の PASS %d (%.0f%%) / そのうち 3 歩以内に仕事 %d (%.0f%%)"
                  % (tag, len(subset), has, 100 * has / len(subset), near3, 100 * near3 / len(subset)))
            kinds = collections.Counter()
            for e in subset:
                for k in e["dmin"]:
                    kinds[k] += 1
            print("       PASS 時に盤上に在った仕事の種類（件数 = その仕事がある PASS の数）:",
                  dict(kinds.most_common()))
            dk3 = collections.Counter()
            for e in subset:
                for k, dd in e["dmin"].items():
                    if dd <= 3:
                        dk3[k] += 1
            print("       うち 3 歩以内:", dict(dk3.most_common()))
            npl = sum(1 for e in subset if e["dmin"].get("PLANTABLE") is not None)
            print("       空きタイル(種在庫>0)が在るのに PASS: %d (%.0f%%)"
                  % (npl, 100 * npl / len(subset)))
            # 「他のユニットが同じ時間に手を付けていない仕事」だけで測り直す
            free3 = sum(1 for e in subset
                        if any(d <= 3 for d in e["dmin_free"].values()))
            free0 = sum(1 for e in subset
                        if any(d == 0 for d in e["dmin_free"].values()))
            print("       ★他ユニットが取っていない仕事が 3 歩以内: %d (%.0f%%) / 足元(0 歩): %d (%.0f%%)"
                  % (free3, 100 * free3 / len(subset), free0, 100 * free0 / len(subset)))
            fk = collections.Counter()
            for e in subset:
                for k, dd in e["dmin_free"].items():
                    if dd <= 3:
                        fk[k] += 1
            print("       その内訳:", dict(fk.most_common()))
            f0 = collections.Counter()
            for e in subset:
                for k, dd in e["dmin_free"].items():
                    if dd == 0:
                        f0[k] += 1
            print("       ★足元(0 歩)の空いている仕事の内訳:", dict(f0.most_common()))
            plantable_ok = sum(1 for e in subset
                               if e["hour"] <= 20 and e["seeds"] > 0
                               and e["dmin_free"].get("PLANTABLE", 99) <= 3)
            print("       ★植付締切(h<=20)内・種あり・空きタイル 3 歩以内なのに PASS: %d (%.0f%%)"
                  % (plantable_ok, 100 * plantable_ok / len(subset)))
            n_any = [e for e in subset if e["near_n"]]
            if n_any:
                tot_near = sum(e["near_n"] for e in n_any)
                print("       ★近傍(<=3歩)の空いていた仕事 %d 件の行方: 同日に他ユニットが実行 %d (%.0f%%) / "
                      "自分が後で実行 %d (%.0f%%) / その日は誰もやらなかった %d (%.0f%%)"
                      % (tot_near,
                         sum(e["later_other"] for e in n_any), 100 * sum(e["later_other"] for e in n_any) / tot_near,
                         sum(e["later_self"] for e in n_any), 100 * sum(e["later_self"] for e in n_any) / tot_near,
                         sum(e["never"] for e in n_any), 100 * sum(e["never"] for e in n_any) / tot_near))
            print("       farmer の PASS: %d (%.0f%%)"
                  % (sum(1 for e in subset if e["is_farmer"]),
                     100 * sum(1 for e in subset if e["is_farmer"]) / len(subset)))
    return dict(total=tot, move=mv, work=wa, core=ca, pass_=acts["PASS"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("replay")
    ap.add_argument("--day", type=int, default=15)
    ap.add_argument("--players", default="0,1")
    args = ap.parse_args()
    steps = json.load(open(args.replay))["steps"]
    names = {0: "gen0051 (us)", 1: "opponent"}
    for p in [int(x) for x in args.players.split(",")]:
        res = analyse(steps, p, focus_day=args.day)
        report(res, "%s p%d %s" % (args.replay.split("/")[-1], p, names.get(p, "")), args.day)


if __name__ == "__main__":
    main()
