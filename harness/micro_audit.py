#!/usr/bin/env python
"""ミクロ監査: リプレイから unit-hour 単位の無駄・タイル利用率・収量・日内タイムラインを出す。

なぜ要るか: `harness/audit_replay.py` が見るのは unfed / uncared / move% / 資金の 4 つだけで、
gen0022 はその 4 つが全部きれい（no-op 0・unfed 0・uncared 0）なのに強帯に資金で倍近い差を
つけられている（`knowledge/analysis/2026-09-05_micro-audit-gen0022.md`）。効いていたのは
**タイル日**（何タイルを何日生産に使ったか）と **1 収穫あたりの収量**で、どちらも既存監査の外。
このスクリプトはその 2 つを含む「実行の正しさ」を機械可読で出し、`--assert` で退行を止める。

使い方:
  .venv/bin/python harness/micro_audit.py replay.json --player 0
  .venv/bin/python harness/micro_audit.py replay.json --both          # 自分と相手を同じ物差しで
  .venv/bin/python harness/micro_audit.py replay.json --json          # EXP に貼る用
  .venv/bin/python harness/micro_audit.py replay.json --assert        # 機械判定（失敗で exit 1）
  .venv/bin/python harness/micro_audit.py replay.json --assert --limit tile_util=0.78 --limit never_used_tiles=0

入力は `harness/run_match.py --replay out.json` が保存する kaggle-environments リプレイ JSON。

`--assert` の基準（重要）:
  既定値は `control/targets.json` の `micro` 節＝**強帯の実測か、エンジン規則から出る最大値**だけ。
  「今の自分の数字」を基準に置くと自己参照になるので入れない
  （`state/plans/2026-09-05_micro-execution-plan.md` §8 末尾）。世代ごとの緩い基準は
  `--limit NAME=VALUE` で明示的に上書きする（出力に基準の出所が出る）。
"""
import argparse
import collections
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
OPPOSITE = {"NORTH": "SOUTH", "SOUTH": "NORTH", "EAST": "WEST", "WEST": "EAST"}
# 物流用の 4 タイル（エンジン: _shed_access_tiles(10) = 内側の 4 隅）。
# PICKUP/DROP/PLACE-into-shed はここでのみ成立し、タイルの中身は見ない
# （kaggriculture.py 344/359/394）ので、作物を植えても物流は壊れない。
SHED = {(4, 4), (5, 4), (4, 5), (5, 5)}
# 物流アクション: 「歩数の直前」統計から外す（畑仕事ではないので距離の意味が違う）
LOGISTICS = ("PICKUP", "DROP", "PLACE")
# 日課のタイル仕事（毎日リセットされ、場所が動かず、1 手で終わる）。
# この 6 つに限れば「同じ日に同じタイルへ 2 回目の訪問をした」は曖昧さなく無駄と言える:
# 2 回目にやった仕事は 1 回目の訪問時にも盤面に出ていたため（日内で新しく生えない）。
# PLANT/DIG/BUILD/PLACE は日内に前提が変わるので数えない。
DAILY_TILE_OPS = ("FEED", "CARE", "WATER", "HARVEST", "COLLECT_FERTILIZER",
                  "FERTILIZE")


def tile_at(farm, x, y):
    try:
        return farm["tiles"][y][x]
    except Exception:
        return "LOCKED"


def classify(op, tile, inv, pos, has_private=True):
    """(category, noop_reason)。noop_reason が非 None ＝ エンジン側で何も起きない行動。

    has_private=False は Kaggle からDLした実戦リプレイのように private（種・各 unit の
    持ち物）が入っていない場合。持ち物を見る判定（FEED の小麦・FERTILIZE の肥料）は
    「持っていない」と「見えない」を区別できないので、その 2 つだけ判定を降りる。
    """
    name = op[0] if op else "PASS"
    if name in MOVES:
        return "MOVE", None
    if name == "PASS":
        return "PASS", None
    if name in ("PICKUP", "DROP") or (
        name == "PLACE"
        and not (isinstance(tile, dict) and tile.get("kind") in ("PASTURE", "COOP"))
    ):
        if pos not in SHED:
            return name, "not_shed_adjacent"
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
        if has_private and inv.get("WHEAT", 0) <= 0:
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
        if has_private and inv.get("FERTILIZER", 0) <= 0:
            return name, "no_fertilizer_inv"
        return name, None
    return name, None


def audit(replay, player):
    """リプレイ 1 本 × 1 プレイヤーの監査。(per_day 行, metrics dict) を返す。"""
    p = player
    steps = replay["steps"]
    total_steps = len(steps)
    days = total_steps // 24

    # private が入っているか（実戦リプレイでは落ちていることがある）
    has_private = any((st[p]["observation"].get("private") or {}).get("inventories")
                      for st in steps[:24])

    per_day = []
    tile_prod_days = collections.Counter()
    tile_unlocked_days = collections.Counter()
    harvest_plant = collections.defaultdict(list)   # crop -> [(age, yield_units)]
    harvest_animal = collections.defaultdict(list)
    fert_total = 0
    noop_total = collections.Counter()
    steps_before_action = collections.Counter()     # 直前に何歩歩いたか（hands の畑仕事のみ）
    hop_distances = []                              # 連続する畑仕事のタイル間マンハッタン距離
    harv_watered = collections.Counter()            # (crop, watered_today) -> n
    since_move = collections.defaultdict(int)
    last_prod_pos = {}
    # 訪問の数え方: (unit, day, tile) ごとに「日課仕事をした連続区間」を 1 訪問と数える。
    # 2 訪問目以降が revisit（＝往復し直した回数）。
    visit_of = collections.Counter()          # (unit, day, pos) -> 訪問回数
    seg_of = {}                               # unit -> 今いる連続区間 (day, pos)
    seg_credited = set()                      # 既に 1 訪問として数えた区間
    revisit_ops = collections.Counter()
    seg_id = collections.Counter()            # unit -> 区間の通し番号

    for d in range(days):
        acts = collections.Counter()
        noops = collections.Counter()
        last_hour = {"FEED": -1, "WATER": -1, "CARE": -1, "PLANT": -1, "any": -1}
        reversals = 0
        prev_move = {}
        hand_hours = 0
        # 2026-09-06(codex P1-2): EOD の盤面は `steps[d*24+23]` = **h23 の行動を反映する前**。
        # h23 の行動は `steps[d*24+24]` に入っていて、その観測はもう翌日（daily reset 後）なので、
        # **h23 に給餌・世話した個体は、どの観測でも fed_today/cared_today が True にならない**。
        # 盤面だけで数えると h23 の FEED/CARE が unfed/uncared に誤計上される。
        # そこで「その日に成立した FEED/CARE の座標」を行動側から拾って併用する。
        # なお **h23 に新規 PLACE された動物は EOD 盤面に居らず、この集計から漏れる**。
        # エンジン上、新規個体は consecutive_unfed = 0 で始まり初日は未給餌でも死なない
        # （envs/kaggriculture/README.md）ので、その日を unfed に数えないのは意図どおり。
        fed_by_action = set()
        cared_by_action = set()
        for h in range(24):
            # steps[t]["action"] は steps[t-1]["observation"] に対して取られた行動
            # （実測: idx1 の WEST が idx1 の座標を作っている）。よって「d 日 h 時の行動」は
            # インデックス d*24+h+1 に入っている。旧コードは t=d*24+h を使っていたので、
            # 全部の行動が 1 時間ぶん後ろの日・時に記録されていた（last_water_hour などの
            # 既存指標も 1 時間ずれていた）。
            t = d * 24 + h + 1
            if t >= total_steps:
                continue   # 最後の行動は d29 h22（エピソードは 720 step で終わる）
            pre = steps[t - 1][p]["observation"]
            post = steps[t][p]["observation"]
            act = steps[t][p].get("action") or {}
            farm = pre["farms"][p]
            priv = pre.get("private") or {}
            invs = priv.get("inventories") or []
            units = [("F", tuple(farm["farmer"]))] + [
                ("H%d" % i, tuple(hp)) for i, hp in enumerate(farm.get("hands") or [])
            ]
            ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
            for ui, (uname, pos) in enumerate(units):
                op = ops[ui] if ui < len(ops) else ["PASS"]
                if not op:
                    op = ["PASS"]
                inv = invs[ui] if ui < len(invs) else {}
                tile = tile_at(farm, pos[0], pos[1])
                cat, why = classify(op, tile, inv, pos, has_private)
                hand_hours += 1
                # 区間の切れ目は**実際に座標が変わった時だけ**。PASS・その場の
                # PICKUP/DROP/PLACE・盤外への no-op MOVE では座標が動かないので切らない
                # （旧: 行動の種類で切っていたため FEED→PASS→CARE が「訪問し直し」になった）。
                if seg_of.get(uname) != (d, pos):
                    seg_of[uname] = (d, pos)
                    seg_id[uname] += 1
                if cat == "MOVE":
                    acts["MOVE"] += 1
                    since_move[uname] += 1
                    if prev_move.get(uname) == OPPOSITE[op[0]]:
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
                # PLANT の種不足失敗はエンジンが黙って無視する（post が None のまま）
                if cat == "PLANT" and tile_at(post["farms"][p], pos[0], pos[1]) is None:
                    noops["PLANT:seed_blocked"] += 1
                    acts["NOOP"] += 1
                    continue
                acts[cat] += 1
                if cat in DAILY_TILE_OPS:
                    vk = (uname, d, pos)
                    sk = (uname, seg_id[uname])
                    if sk not in seg_credited:
                        seg_credited.add(sk)
                        visit_of[vk] += 1
                        if visit_of[vk] > 1:
                            revisit_ops[cat] += 1
                if uname != "F" and cat not in LOGISTICS:
                    steps_before_action[min(since_move[uname], 9)] += 1
                    prev_pos = last_prod_pos.get(uname)
                    if prev_pos is not None:
                        hop_distances.append(
                            abs(prev_pos[0] - pos[0]) + abs(prev_pos[1] - pos[1])
                        )
                    last_prod_pos[uname] = pos
                since_move[uname] = 0
                if cat in last_hour:
                    last_hour[cat] = h
                last_hour["any"] = h
                if cat == "HARVEST":
                    if tile.get("kind") == "PLANT":
                        harvest_plant[tile["crop"]].append(
                            (pre["day"] - tile["planted_day"], tile["yield_units"])
                        )
                        harv_watered[(tile["crop"], bool(tile.get("watered_today")))] += 1
                    else:
                        harvest_animal[tile["animal"]].append(tile["yield_units"])
                if cat == "FERTILIZE":
                    fert_total += 1
                # h23 の行動だけを拾う（h22 以前は EOD 盤面に反映済みなので union しても
                # 何も変わらない。範囲を絞っておかないと、将来 classify が緩んだ時に
                # 早い時刻の失敗まで「成立した」と数えて基準を素通りさせうる）。
                # FEED は private（各 unit の持ち物）が無いと小麦不足を判定できないので、
                # 実戦 DL リプレイのように private が落ちている入力では補正しない
                # ＝ 盤面だけで数える従来どおりの（安全側に厳しい）判定に倒す。codex 指摘。
                if h == 23:
                    if cat == "FEED" and has_private:
                        fed_by_action.add(pos)
                    elif cat == "CARE":
                        cared_by_action.add(pos)

        # EOD の盤面
        eod = steps[min(d * 24 + 23, total_steps - 1)][p]["observation"]
        farm = eod["farms"][p]
        priv = eod.get("private") or {}
        n_prod_tiles = n_unlocked = weeds = empty = 0
        animals = unfed = uncared = 0
        for y, row in enumerate(farm["tiles"]):
            for x, tl in enumerate(row):
                if tl == "LOCKED":
                    continue
                n_unlocked += 1
                tile_unlocked_days[(x, y)] += 1
                if isinstance(tl, dict):
                    if tl.get("animal"):
                        animals += 1
                        unfed += not (tl.get("fed_today") or (x, y) in fed_by_action)
                        uncared += not (tl.get("cared_today") or (x, y) in cared_by_action)
                    if tl.get("kind") == "PLANT" or tl.get("animal"):
                        n_prod_tiles += 1
                        tile_prod_days[(x, y)] += 1
                    elif tl.get("kind") == "WEED":
                        weeds += 1
                    else:
                        empty += 1  # 空のパスチャ/コープ
                else:
                    empty += 1
        seeds_idle = sum((priv.get("seeds") or {}).values()) if has_private else None
        shed = priv.get("shed") or {}
        for k, v in noops.items():
            noop_total[k] += v
        per_day.append(dict(
            day=d, hh=hand_hours, acts=acts, noops=noops, last=last_hour,
            reversals=reversals, n_prod=n_prod_tiles, n_unlocked=n_unlocked,
            weeds=weeds, empty=empty, seeds_idle=seeds_idle, animals=animals,
            unfed=unfed, uncared=uncared,
            shed_items=sum(v for k, v in shed.items() if k != "WHEAT"),
            money=farm["money"], hands=len(farm.get("hands") or []),
        ))

    never_used = sorted(t for t in tile_unlocked_days if tile_prod_days[t] == 0)
    tot_u = sum(tile_unlocked_days.values())
    tot_p = sum(tile_prod_days.values())
    n_sba = sum(steps_before_action.values())

    def crop_stats(crop):
        lst = harvest_plant.get(crop) or []
        if not lst:
            return None
        return dict(
            n=len(lst),
            yield_mean=round(statistics.mean(y for _, y in lst), 3),
            age_mean=round(statistics.mean(a for a, _ in lst), 2),
            dist=dict(collections.Counter(y for _, y in lst)),
        )

    def watered_share(crop):
        w = harv_watered.get((crop, True), 0)
        n = w + harv_watered.get((crop, False), 0)
        return round(w / n, 3) if n else None

    mid = [r for r in per_day if 10 <= r["day"] <= 24]
    season = [r for r in per_day if 1 <= r["day"] <= 28]
    metrics = dict(
        player=p,
        days=days,
        final_money=per_day[-1]["money"] if per_day else None,
        hands=per_day[-1]["hands"] if per_day else None,
        tile_days_prod=tot_p,
        tile_days_unlocked=tot_u,
        tile_util=round(tot_p / tot_u, 4) if tot_u else None,
        never_used_tiles=[list(t) for t in never_used],
        empty_tiles_d10_24=[min(r["empty"] for r in mid), max(r["empty"] for r in mid)] if mid else None,
        seeds_idle_d15=next((r["seeds_idle"] for r in per_day if r["day"] == 15), None),
        has_private=has_private,
        seeds_idle_max_d10_24=max((r["seeds_idle"] for r in mid if r["seeds_idle"] is not None),
                                  default=None),
        wheat_yield=(crop_stats("WHEAT") or {}).get("yield_mean"),
        melon_yield=(crop_stats("MELON") or {}).get("yield_mean"),
        strawberry_yield=(crop_stats("STRAWBERRY") or {}).get("yield_mean"),
        crops={c: crop_stats(c) for c in sorted(harvest_plant)},
        animals_harvest={a: dict(n=len(v), yield_mean=round(statistics.mean(v), 3))
                         for a, v in sorted(harvest_animal.items())},
        harvest_watered_share={c: watered_share(c) for c in sorted(harvest_plant)},
        fertilize_count=fert_total,
        moves3plus_share=round(
            sum(v for k, v in steps_before_action.items() if k >= 3) / n_sba, 4) if n_sba else None,
        # gen0032: 1 回の訪問で仕事を何手できたか。0 歩＝直前の仕事と同じタイルで続けた手。
        # 層（仕事の種類）で農場を何周もしていると下がる。強帯 0.44-0.52 / gen0031 0.32。
        inplace_share=round(steps_before_action[0] / n_sba, 4) if n_sba else None,
        # gen0032: 同じ日に同じタイルへ訪問し直した回数 / (unit,day,tile) 組。
        tile_revisit_share=round(
            (sum(visit_of.values()) - len(visit_of)) / len(visit_of), 4) if visit_of else None,
        tile_revisits=sum(visit_of.values()) - len(visit_of),
        tile_revisit_ops=dict(revisit_ops.most_common()),
        steps_before_action=[steps_before_action[i] for i in range(10)],
        mean_hop_distance=round(statistics.mean(hop_distances), 3) if hop_distances else None,
        last_water_hour=max((r["last"]["WATER"] for r in season), default=None),
        last_feed_hour=max((r["last"]["FEED"] for r in season), default=None),
        last_care_hour=max((r["last"]["CARE"] for r in season), default=None),
        noop_total=sum(noop_total.values()),
        noops=dict(noop_total.most_common()),
        unfed_days=sum(1 for r in season if r["unfed"] > 0),
        uncared_days=sum(1 for r in season if r["uncared"] > 0),
        move_share=round(sum(r["acts"]["MOVE"] for r in season) / sum(r["hh"] for r in season), 4)
        if season else None,
    )
    metrics["never_used_tile_count"] = len(never_used)
    return per_day, metrics, tile_prod_days, tile_unlocked_days


# ---- 機械判定 -------------------------------------------------------------
# direction: "min" = この値以上で合格 / "max" = この値以下で合格
CHECKS = {
    "tile_util":            ("min", "タイル利用率（生産タイル日/解放タイル日）"),
    "wheat_yield":          ("min", "WHEAT の 1 収穫あたり収量（無肥料の規則上限 4）"),
    "melon_yield":          ("min", "MELON の 1 収穫あたり収量（規則上限 6）"),
    "strawberry_yield":     ("min", "STRAWBERRY の 1 回収量（肥料ありで 2）"),
    "moves3plus_share":     ("max", "畑仕事の直前に 3 歩以上歩いた割合"),
    "inplace_share":        ("min", "畑仕事のうち、移動せず同じタイルで続けてできた割合"),
    "tile_revisit_share":   ("max", "同じ日に同じタイルへ訪問し直した回数 /(unit,day,tile)"),
    "mean_hop_distance":    ("max", "同じ hand の連続する畑仕事のタイル間距離（平均）"),
    "last_water_hour":      ("max", "最後の WATER の時刻（d1-28 の最大）"),
    "last_feed_hour":       ("max", "最後の FEED の時刻（d1-28 の最大）"),
    "never_used_tile_count": ("max", "一度も生産に使わなかった解放タイル数"),
    "noop_total":           ("max", "エンジン側で何も起きなかった行動の総数"),
    "seeds_idle_d15":       ("max", "d15 EOD の未植付の種"),
    "unfed_days":           ("max", "unfed>0 の日数（d1-28）"),
    "uncared_days":         ("max", "uncared>0 の日数（d1-28）"),
    "fertilize_count":      ("min", "FERTILIZE の回数"),
}


def load_limits(targets_file, overrides):
    """(name -> (value, source)) を返す。既定は targets.json の micro、--limit が上書き。"""
    limits = {}
    p = Path(targets_file) if targets_file else (ROOT / "control/targets.json")
    if p.exists():
        micro = (json.loads(p.read_text()).get("micro") or {})
        for k, v in micro.items():
            if k in CHECKS and isinstance(v, (int, float)):
                limits[k] = (float(v), str(p))
    for item in overrides or []:
        if "=" not in item:
            sys.exit(f"--limit は NAME=VALUE の形で書く: {item!r}")
        k, v = item.split("=", 1)
        k = k.strip()
        if k not in CHECKS:
            sys.exit(f"未知の指標 {k!r}。使えるのは: {', '.join(sorted(CHECKS))}")
        limits[k] = (float(v), "--limit")
    return limits


def run_asserts(metrics, limits):
    """[(ok, name, value, direction, limit, source)] を返す。"""
    results = []
    for name, (value, source) in sorted(limits.items()):
        direction = CHECKS[name][0]
        got = metrics.get(name)
        if got is None:
            ok = None  # 判定不能（その作物を一度も収穫していない等）
        elif direction == "min":
            ok = got >= value
        else:
            ok = got <= value
        results.append((ok, name, got, direction, value, source))
    return results


# ---- 出力 -----------------------------------------------------------------
def print_table(per_day, metrics, tile_prod_days, tile_unlocked_days, label):
    print(f"== {label}")
    print("day hh  MOVE PASS NOOP prod  move% pass% | lastFEED lastWATER lastCARE lastANY | rev "
          "| tiles prod/unlocked weeds empty | seeds_idle shed | money")
    for r in per_day:
        ac = r["acts"]
        prod = sum(v for k, v in ac.items() if k not in ("MOVE", "PASS", "NOOP"))
        hh = r["hh"] or 1
        L = r["last"]
        print(f"d{r['day']:2d} {hh:3d} {ac['MOVE']:4d} {ac['PASS']:4d} {ac['NOOP']:4d} {prod:4d}  "
              f"{100*ac['MOVE']/hh:4.0f}% {100*ac['PASS']/hh:4.0f}% | "
              f"{L['FEED']:6d} {L['WATER']:8d} {L['CARE']:8d} {L['any']:7d} | {r['reversals']:3d} | "
              f"{r['n_prod']:3d}/{r['n_unlocked']:3d} {r['weeds']:3d} {r['empty']:3d} | "
              f"{'   -' if r['seeds_idle'] is None else format(r['seeds_idle'], '4d')} "
              f"{r['shed_items']:4d} | {r['money']:7.0f}")
    print("-- noop 合計:", metrics["noops"])
    print("-- FERTILIZE 合計:", metrics["fertilize_count"])
    print(f"-- hands の畑仕事の直前の歩数 0..9+: {metrics['steps_before_action']}"
          f"  (3歩以上: {100*(metrics['moves3plus_share'] or 0):.0f}%"
          f" / 0歩=その場で継続: {100*(metrics['inplace_share'] or 0):.0f}%)"
          f"  連続行動タイル間距離 平均 {metrics['mean_hop_distance']}")
    print(f"-- 同じ日の同じタイルへの訪問し直し: {metrics['tile_revisits']} 回"
          f" ({metrics['tile_revisit_share']} /タイル日)  内訳 {metrics['tile_revisit_ops']}")
    print("-- HARVEST 時に当日水やり済みの割合:", metrics["harvest_watered_share"])
    for crop, st in metrics["crops"].items():
        if st:
            print(f"-- HARVEST {crop}: n={st['n']} yield平均={st['yield_mean']:.2f} "
                  f"(分布 {sorted(st['dist'].items())}) age平均={st['age_mean']:.1f}")
    for an, st in metrics["animals_harvest"].items():
        print(f"-- HARVEST {an}: n={st['n']} yield平均={st['yield_mean']:.2f}")
    print(f"-- タイル利用率(生産タイル日/解放タイル日): {metrics['tile_days_prod']}"
          f"/{metrics['tile_days_unlocked']} = {100*(metrics['tile_util'] or 0):.0f}%")
    print(f"-- 一度も使わなかった解放タイル: {[tuple(t) for t in metrics['never_used_tiles']]}")
    low = sorted((t, tile_prod_days[t], tile_unlocked_days[t]) for t in tile_unlocked_days
                 if 0 < tile_prod_days[t] < 0.5 * tile_unlocked_days[t])
    print(f"-- 利用率<50%: {low}")
    print("-- 利用日数マップ (x→, y↓):")
    for y in range(10):
        print("   " + " ".join(f"{tile_prod_days[(x, y)]:2d}" if tile_unlocked_days[(x, y)]
                               else " ." for x in range(10)))


def print_asserts(results, label):
    print(f"-- 機械判定 ({label})")
    ng = 0
    for ok, name, got, direction, limit, source in results:
        sign = "≥" if direction == "min" else "≤"
        mark = "OK " if ok else ("?? " if ok is None else "NG ")
        ng += ok is False
        got_s = "(判定不能)" if got is None else f"{got}"
        print(f"   {mark} {name:24s} {got_s:>12s} {sign} {limit:<10g} [{Path(source).name}]"
              f"  {CHECKS[name][1]}")
    return ng


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay")
    ap.add_argument("--player", type=int, default=0)
    ap.add_argument("--both", action="store_true",
                    help="両プレイヤーを同じ物差しで並べる（相手が強帯なら目標が読める）")
    ap.add_argument("--json", action="store_true",
                    help="指標を JSON で出す（EXP に貼る用。表は出さない）")
    ap.add_argument("--assert", dest="do_assert", action="store_true",
                    help="control/targets.json の micro を基準に機械判定する（NG があれば exit 1）")
    ap.add_argument("--limit", action="append", metavar="NAME=VALUE",
                    help="基準の上書き・追加（繰り返し可）。使える NAME は --list-checks で")
    ap.add_argument("--targets-file", help="targets.json のパス（既定 control/targets.json）")
    ap.add_argument("--list-checks", action="store_true", help="判定できる指標を並べて終了")
    args = ap.parse_args()

    if args.list_checks:
        for name, (direction, doc) in sorted(CHECKS.items()):
            print(f"{name:24s} {direction:3s}  {doc}")
        return

    replay = json.loads(Path(args.replay).read_text())
    players = [0, 1] if args.both else [args.player]
    limits = load_limits(args.targets_file, args.limit) if args.do_assert else {}

    out = {}
    ng_total = 0
    for p in players:
        per_day, metrics, prod, unlocked = audit(replay, p)
        label = f"player {p}  ({args.replay})"
        if args.json:
            out[str(p)] = metrics
        else:
            print_table(per_day, metrics, prod, unlocked, label)
        if args.do_assert:
            results = run_asserts(metrics, limits)
            if args.json:
                out[str(p)]["asserts"] = [
                    dict(ok=ok, name=n, value=v, direction=d, limit=lim, source=src)
                    for ok, n, v, d, lim, src in results
                ]
                ng_total += sum(1 for r in results if r[0] is False)
            else:
                ng_total += print_asserts(results, label)
        if not args.json and len(players) > 1:
            print()

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))

    if args.do_assert:
        # --assert は「基準を 1 つでも割ったら落ちる」。相手プレイヤー側の NG も数える
        # （--both で自分だけを見たい時は --player を使う）。
        if ng_total:
            if not args.json:
                print(f"-- NG {ng_total} 件", file=sys.stderr)
            sys.exit(1)
        if not args.json:
            print("-- 全て OK")


if __name__ == "__main__":
    main()
