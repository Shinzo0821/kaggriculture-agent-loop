"""gen0002 — Track B: 動物経済（牛中心+羊/鶏で店舗乱数に分散）+ 小麦自給。

仮説（EXP0002）: 動物は行動単価が作物の3〜5倍（1頭3.5行動/日で$300-450/日)。
プレミアム品(ミルク/ウール)は町需要が供給を上回る限り価格が上昇し続ける。
早期全力投資(first yield まで8日)+毎日の FEED/CARE/COLLECT_FERTILIZER 完全遵守で
gen0001($9-12k) の2倍以上を狙う。土地は買わない($44k相手に倣う)。
"""

ANIMALS = {
    "COW": {"cost": 400, "structure": "PASTURE", "product": "MILK"},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL"},
    "GOOSE": {"cost": 300, "structure": "COOP", "product": "EGG"},
}
BUY_SEQUENCE = ["COW", "COW", "GOOSE", "GOOSE", "COW", "SHEEP", "COW", "SHEEP", "COW", "COW"]
PASTURE_TILES = [(1, 3), (2, 3), (3, 3), (4, 3), (1, 4), (2, 4), (3, 4), (4, 4)]
COOP_TILES = [(0, 3), (0, 4)]
WHEAT_TILES = [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (2, 1), (3, 1), (4, 1)]
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]  # シェッド操作可能な立ち位置

LAST_ANIMAL_BUY_DAY = 18   # cow first yield 8日: これ以降の購入は回収不能
LAST_PLANT_DAY = 25        # day25植付 → day29 に age4 で収穫が間に合う限界
LAST_PLANT_HOUR = 20       # 終業間際の植付は当日の水やりが間に合わず確定枯れ
LAST_FEED_DAY = 28         # day29 の給餌は生産に間に合わない
DUMP_DAY = 28              # これ以降は価格を問わず全量売却
FINAL_DAY = 29             # 手持ちを DROP してでも換金する日
TARGET_HANDS = 4
SEASON_DAYS = 30

SELL_FLOORS = {"MILK": 96, "WOOL": 120, "FERTILIZER": 70}  # base比0.6-0.7
ALWAYS_SELL = ["EGG", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]


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
    seeds = private.get("seeds") or {}
    shed = private.get("shed") or {}
    invs = private.get("inventories") or []
    tiles = me.get("tiles") or []
    day = obs.get("day", 0)
    money = me.get("money", 0)
    prices = (obs.get("market") or {}).get("prices") or {}

    def tile_at(x, y):
        try:
            return tiles[y][x]
        except Exception:
            return "LOCKED"

    # ---- 農場の棚卸し ----
    placed = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    unfed_animals = 0
    todos = []  # (priority, x, y, op(list), need)  need: None|"WHEAT"|動物種

    for kind, positions in (("PASTURE", PASTURE_TILES + COOP_TILES),):
        pass  # 位置リストは下で個別に回す

    structure_plan = [(x, y, "PASTURE") for x, y in PASTURE_TILES] + \
                     [(x, y, "COOP") for x, y in COOP_TILES]
    empty_structs = {"PASTURE": [], "COOP": []}
    for x, y, want in structure_plan:
        t = tile_at(x, y)
        if t is None:
            if day <= LAST_ANIMAL_BUY_DAY + 1:
                todos.append((2.6, x, y, ["BUILD_" + want], None))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((2.6, x, y, ["DIG"], None))
        elif isinstance(t, dict) and t.get("kind") == want and not t.get("animal"):
            empty_structs[want].append((x, y))
        elif isinstance(t, dict) and t.get("animal"):
            a = t["animal"]
            placed[a] = placed.get(a, 0) + 1
            if not t.get("fed_today") and day <= LAST_FEED_DAY:
                unfed_animals += 1
                pri = 0.0 if t.get("consecutive_unfed", 0) >= 1 else 1.2
                todos.append((pri, x, y, ["FEED"], "WHEAT"))
            if t.get("yield_units", 0) > 0:
                todos.append((2.0, x, y, ["HARVEST"], None))
            if not t.get("cared_today") and day <= LAST_FEED_DAY:
                todos.append((3.5, x, y, ["CARE"], None))
            if t.get("fertilizer_available"):
                todos.append((4.0, x, y, ["COLLECT_FERTILIZER"], None))

    hour = obs.get("hour", 0)
    for x, y in WHEAT_TILES:
        t = tile_at(x, y)
        if t is None:
            if day <= LAST_PLANT_DAY and hour <= LAST_PLANT_HOUR:
                todos.append((5.0, x, y, ["PLANT", "WHEAT"], "SEED"))
        elif isinstance(t, dict) and t.get("kind") == "PLANT":
            age = day - t.get("planted_day", day)
            ripe = age >= 4 or (day >= DUMP_DAY and age >= 2)
            if ripe and t.get("yield_units", 0) > 0:
                todos.append((2.2, x, y, ["HARVEST"], None))
            if not t.get("watered_today"):
                # 収穫待ちでも水やりは継続(枯死防止 + age<=4はボーナス窓)
                pri = 1.0 if t.get("consecutive_unwatered", 0) >= 1 else 3.0
                todos.append((pri, x, y, ["WATER"], None))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((6.0, x, y, ["DIG"], None))

    # 最終日: 手持ちの収穫物をシェッドに DROP して換金対象にする
    if day >= FINAL_DAY:
        for ui, inv in enumerate(invs):
            if sum(inv.values()) > 0:
                todos.append((2.1, -1, -1, ["DROP"], f"UNIT{ui}"))

    # 動物の設置: シェッドに動物がいて空き構造物があるなら PLACE / PICKUP
    carried_animals = {a: sum(inv.get(a, 0) for inv in invs) for a in ANIMALS}
    for a, spec in ANIMALS.items():
        empties = list(empty_structs[spec["structure"]])
        in_shed = shed.get(a, 0)
        for x, y in empties[: in_shed + carried_animals[a]]:
            todos.append((2.4, x, y, ["PLACE", a], a))
        if in_shed > 0 and empties:
            for sx, sy in SHED_TILES:
                todos.append((2.5, sx, sy, ["PICKUP", a, 1], "SHEDOP"))
                break  # 最寄り計算はユニット側で行うため代表1つで十分

    # 給餌用小麦の受け取り
    shed_wheat = shed.get("WHEAT", 0)
    if unfed_animals > 0 and shed_wheat > 0:
        for sx, sy in SHED_TILES:
            todos.append((0.5, sx, sy, ["PICKUP", "WHEAT", min(shed_wheat, unfed_animals, 6)], "SHEDOP"))

    # ---- ユニット割当 ----
    fx, fy = me.get("farmer", [4, 4])
    hand_pos = list(me.get("hands") or [])
    units = [(fx, fy)] + [(hx, hy) for hx, hy in hand_pos]
    claimed = set()
    planned_seed_use = 0
    planned_pickup = {"WHEAT": 0}
    actions = []
    for ui, (ux, uy) in enumerate(units):
        inv = invs[ui] if ui < len(invs) else {}
        my_wheat = inv.get("WHEAT", 0)
        best = None
        best_key = None
        for pri, x, y, op, need in todos:
            if (pri, x, y, tuple(op)) in claimed:
                continue
            if need == "WHEAT" and my_wheat <= 0:
                continue
            if need == "SEED" and planned_seed_use >= seeds.get("WHEAT", 0):
                continue
            if need in ANIMALS and inv.get(need, 0) <= 0:
                continue
            if need and need.startswith("UNIT"):
                if need != f"UNIT{ui}":
                    continue
                x, y = min(SHED_TILES, key=lambda p: abs(ux - p[0]) + abs(uy - p[1]))
            if need == "SHEDOP":
                if op[0] == "PICKUP" and op[1] == "WHEAT":
                    if my_wheat >= 2 or planned_pickup["WHEAT"] >= 2:
                        continue  # 既に持っている/2ユニットが向かっている
                if op[0] == "PICKUP" and op[1] in ANIMALS and inv.get(op[1], 0) > 0:
                    continue
                # シェッド操作は最寄りの立ち位置に置き換える
                x, y = min(SHED_TILES, key=lambda p: abs(ux - p[0]) + abs(uy - p[1]))
            d = abs(ux - x) + abs(uy - y)
            key = (pri, d)
            if best_key is None or key < best_key:
                best_key = key
                best = (pri, x, y, op, need)
        if best is None:
            actions.append(["PASS"])
            continue
        pri, x, y, op, need = best
        claimed.add((pri, x, y, tuple(op)))
        if need == "SEED":
            planned_seed_use += 1
        if need == "SHEDOP" and op[0] == "PICKUP" and op[1] == "WHEAT":
            planned_pickup["WHEAT"] += 1
        if (ux, uy) == (x, y):
            actions.append(list(op))
        else:
            actions.append([step_toward(ux, uy, x, y)])

    # ---- 市場 ----
    market = []
    total_animals = sum(placed.values())
    shed_total = sum(shed.values())

    # 売却
    feed_buffer = total_animals * 3 + 2
    if shed_wheat > feed_buffer or day >= DUMP_DAY:
        n = shed_wheat if day >= DUMP_DAY else shed_wheat - feed_buffer
        if n > 0:
            market.append(["SELL", "WHEAT", n])
    for item in ALWAYS_SELL:
        if shed.get(item, 0) > 0:
            market.append(["SELL", item, shed[item]])
    for item, floor in SELL_FLOORS.items():
        n = shed.get(item, 0)
        if n > 0 and (prices.get(item, 0) >= floor or day >= DUMP_DAY or shed_total >= 85):
            market.append(["SELL", item, n])

    # 給餌用小麦の補充(自給不足分を市場から)
    carried_wheat = sum(inv.get("WHEAT", 0) for inv in invs)
    if total_animals > 0 and day <= LAST_FEED_DAY:
        stock = shed_wheat + carried_wheat
        if stock < total_animals:
            want = min(total_animals * 2 - stock, 10)
            wheat_price = prices.get("WHEAT", 45)
            affordable = int(money // (wheat_price + 5))
            qty = min(want, affordable)  # 全量買えなくても買える分だけ買う
            if qty >= 1:
                market.append(["BUY_PRODUCT", "WHEAT", qty])
                money -= qty * wheat_price

    # 動物購入(シーケンス順、予算と期限内)
    owned_total = total_animals + sum(carried_animals.values()) + \
        sum(shed.get(a, 0) for a in ANIMALS)
    if day <= LAST_ANIMAL_BUY_DAY and owned_total < len(BUY_SEQUENCE):
        nxt = BUY_SEQUENCE[owned_total]
        if money >= ANIMALS[nxt]["cost"] + 200:
            market.append(["BUY_ANIMAL", nxt, 1])
            money -= ANIMALS[nxt]["cost"]

    # 種の補充
    empty_wheat = sum(1 for x, y in WHEAT_TILES if tile_at(x, y) is None)
    if day <= LAST_PLANT_DAY and empty_wheat > seeds.get("WHEAT", 0) and money >= 60:
        market.append(["BUY_SEED", "WHEAT", min(empty_wheat - seeds.get("WHEAT", 0), 4)])
        money -= 40

    # 雇用(最終日も回収+DROP要員として安価なので雇う)
    hires_today = me.get("hires_today", 0)
    if len(hand_pos) < TARGET_HANDS and hires_today < TARGET_HANDS and money > 60:
        market.append(["HIRE"])

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}
