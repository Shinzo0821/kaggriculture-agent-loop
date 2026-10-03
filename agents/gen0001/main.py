"""gen0001 — Phase 0: 全タイル稼働のルールベース農場運営。

戦略:
- NWクアドラント25タイルを小麦/ニンジンの混作で全稼働(タイル座標の偶奇で固定割当)
- 毎日ファームハンドを雇用(フィボナッチ初期の激安枠のみ)し、行動数を5倍化
- 水やり最優先(2日未給水の全損を絶対に防ぐ)、最大収量日に収穫、毎ターン全量売却
- 動物・肥料・土地購入は Phase 0 では扱わない
"""

CROPS = {
    "WHEAT": {"seed": 10, "max_yield_day": 4},
    "CARROT": {"seed": 20, "max_yield_day": 3},
}
SELLABLE = ["WHEAT", "CARROT", "TOMATO", "STRAWBERRY", "MELON",
            "EGG", "MILK", "WOOL", "FERTILIZER"]
TARGET_HANDS = 4          # farmer + 4 hands = 5 units (雇用費 1+1+2+3 = $7/日)
LAST_PLANT_DAY = {"WHEAT": 25, "CARROT": 26}  # 30 - (max_yield_day + 1)
SEASON_DAYS = 30


def crop_for_tile(x, y):
    return "WHEAT" if (x + y) % 2 == 0 else "CARROT"


def step_toward(px, py, tx, ty):
    if px < tx:
        return "EAST"
    if px > tx:
        return "WEST"
    if py < ty:
        return "SOUTH"
    if py > ty:
        return "NORTH"
    return "PASS"


def agent(obs):
    try:
        return _agent(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}


def _agent(obs):
    player = obs.get("player", 0)
    farms = obs.get("farms") or []
    if player >= len(farms):
        return {"farmer": ["PASS"], "hands": [], "market": []}
    me = farms[player]
    private = obs.get("private") or {}
    seeds = dict(private.get("seeds") or {})
    shed = private.get("shed") or {}
    tiles = me.get("tiles") or []
    day = obs.get("day", 0)
    money = me.get("money", 0)

    # ---- todo 収集(優先度: 小さいほど緊急) ----
    todos = []  # (priority, x, y, op)
    empty_by_crop = {"WHEAT": 0, "CARROT": 0}
    for y, row in enumerate(tiles):
        for x, tile in enumerate(row):
            if tile == "LOCKED":
                continue
            if tile is None:
                crop = crop_for_tile(x, y)
                if day <= LAST_PLANT_DAY[crop]:
                    empty_by_crop[crop] += 1
                    todos.append((3, x, y, ("PLANT", crop)))
                continue
            if not isinstance(tile, dict):
                continue
            kind = tile.get("kind")
            if kind == "PLANT":
                crop = tile.get("crop")
                age = day - tile.get("planted_day", day)
                ripe = crop in CROPS and age >= CROPS[crop]["max_yield_day"]
                decaying = tile.get("max_lifespan_step", -1) != -1 and tile.get("yield_units", 0) > 0 \
                    and crop in CROPS and age > CROPS[crop]["max_yield_day"]
                if ripe or decaying:
                    todos.append((1, x, y, ("HARVEST",)))
                elif not tile.get("watered_today", False):
                    pri = 0 if tile.get("consecutive_unwatered", 0) >= 1 else 2
                    todos.append((pri, x, y, ("WATER",)))
            elif kind == "WEED":
                todos.append((4, x, y, ("DIG",)))

    # ---- ユニットへの割当 ----
    fx, fy = me.get("farmer", [0, 0])
    hand_pos = list(me.get("hands") or [])
    units = [(fx, fy)] + [(hx, hy) for hx, hy in hand_pos]
    claimed = set()
    planned_plants = {"WHEAT": 0, "CARROT": 0}
    actions = []
    for ux, uy in units:
        best = None
        best_key = None
        for pri, x, y, op in todos:
            if (x, y) in claimed:
                continue
            if op[0] == "PLANT":
                crop = op[1]
                if planned_plants[crop] >= seeds.get(crop, 0):
                    continue
            d = abs(ux - x) + abs(uy - y)
            key = (pri, d)
            if best_key is None or key < best_key:
                best_key = key
                best = (x, y, op)
        if best is None:
            actions.append(["PASS"])
            continue
        x, y, op = best
        claimed.add((x, y))
        if op[0] == "PLANT":
            planned_plants[op[1]] += 1
        if (ux, uy) == (x, y):
            actions.append(list(op))
        else:
            actions.append([step_toward(ux, uy, x, y)])

    # ---- 市場 ----
    market = []
    # 収穫物は毎ターン全量売却(シェッド溢れ対策も兼ねる)
    for item in SELLABLE:
        n = shed.get(item, 0)
        if n > 0:
            market.append(["SELL", item, n])
    # 種の補充: 空きタイル数まで(1回の注文は5個まで)
    for crop in ("WHEAT", "CARROT"):
        need = empty_by_crop[crop] - seeds.get(crop, 0) - planned_plants[crop]
        cost = CROPS[crop]["seed"]
        if need > 0 and money >= cost * 2:
            qty = min(need, 5, max(1, int(money // (cost * 2))))
            market.append(["BUY_SEED", crop, qty])
            money -= cost * qty
    # 雇用: 毎日 TARGET_HANDS 体まで(残り日数が少なければ縮小)
    if day < SEASON_DAYS - 1:
        hires_today = me.get("hires_today", 0)
        if len(hand_pos) < TARGET_HANDS and hires_today < TARGET_HANDS and money > 100:
            market.append(["HIRE"])

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}
