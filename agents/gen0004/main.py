"""gen0004 — Track B: 土地購入スケール + メロン終盤波（親: gen0003）。

仮説（EXP0004）: 上位（torch $91k, 終盤日+$9k）に対抗する terminal acceleration の
正体は「高付加価値の one-time 作物を空き地に大量展開する」こと。**メロン**は
どの店舗も消費せず（需要は町センター 1個/日 のみ）、glut 曲線が T=300・sq・
above_target 3.60 なので ~158個を一度に叩き売って初めて暴落する。実運用の
15-30個規模なら価格は base $250 近辺に張り付く → 1タイル 6個 ≈ $1500。
gen0003 はメロンを保有時に売るだけで**一度も植えない**。よって
(1) NE(+SW) を購入して空き地を確保し、
(2) NW 空きタイル + 購入地にメロンを波状に植え（1タイル最大2サイクル）、
(3) hand を 4→6 に増やして拡張分の労働を賄う、
で終盤資金を押し上げる。動物・小麦の既存経済は gen0003 のまま温存し、
メロンの水やりは動物給餌・小麦水やりより低優先度にして本業を守る。
"""

ANIMALS = {
    "COW": {"cost": 400, "structure": "PASTURE", "product": "MILK",
            "value": 80, "last_buy": 18},
    "SHEEP": {"cost": 500, "structure": "PASTURE", "product": "WOOL",
              "value": 66, "last_buy": 19},
    "GOOSE": {"cost": 300, "structure": "COOP", "product": "EGG",
              "value": 55, "last_buy": 22},
}
# ミルク: 1x消費 / 毛糸: 単品店2x消費 / 卵: 1x消費（README 店舗テーブル）
MILK_SHOPS = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
WOOL_SHOPS = ("YARN_STORE",)
EGG_SHOPS = ("BAKERY", "BRUNCH_SPOT")

ANIMAL_TILES = [(1, 3), (2, 3), (3, 3), (4, 3), (1, 4), (2, 4), (3, 4), (4, 4),
                (0, 3), (0, 4)]  # 構造種は動的に決める(最大10頭)
WHEAT_TILES = [(0, 2), (1, 2), (2, 2), (3, 2), (4, 2), (2, 1), (3, 1), (4, 1)]
# メロン: NW の空き地 7 + NE 購入地 8 = 最大15タイル（LOCKED は実行時に除外）
MELON_TILES = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (0, 1), (1, 1),          # NW spares
               (5, 0), (6, 0), (7, 0), (8, 0), (9, 0), (5, 1), (6, 1), (7, 1)]  # NE
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]  # シェッド操作可能な立ち位置

LAST_PLANT_DAY = 25        # day25植付 → day29 に age4 で収穫が間に合う限界
LAST_PLANT_HOUR = 20       # 終業間際の植付は当日の水やりが間に合わず確定枯れ
LAST_FEED_DAY = 28         # day29 の給餌は生産に間に合わない
DUMP_DAY = 28              # これ以降は価格を問わず全量売却
FINAL_DAY = 29             # 手持ちを DROP してでも換金する日
TARGET_HANDS = 6           # gen0003 の 4 から増員（拡張分の労働）
MAX_ANIMALS = 10

# ---- メロン ----
MELON_FIRST_YIELD = 10     # age>=10 で収穫可能（one-time, max_yield_day12, base1+水5=6@age10）
MELON_PLANT_LAST = 18      # day18植付 → age10=day28(DUMP) までに収穫。早植えは自然に2サイクル
MELON_SEED_COST = 80
MELON_CASH_BUFFER = 1500   # メロン種購入時に残す運転資金（動物給餌・小麦を守る）

# ---- 土地購入 ----
LAND_PRICES = [1000, 2000, 4000]  # NE, SW, SE（README 準拠）
LAND_ORDER_Q = ["NE", "SW", "SE"]
LAND_MAX_EXTRA = 2                 # NE + SW まで（SE は割高で終盤 ROI 薄い）
# 各拡張は「その価格 + バッファ」を満たすときだけ購入（貧乏ゲームは lean のまま）
LAND_BUFFERS = [1500, 4000]        # NE 購入は money>=2500 / SW 購入は money>=6000

SELL_FLOORS = {"MILK": 96, "WOOL": 120}      # base比0.6: これ以上なら即全量売り
FERT_FLOOR = 70
ALWAYS_SELL = ["EGG", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
I0 = 10000
GLUT_SLACK = 10  # I0 をこれ以上超えて売らない(プレミアム品の暴落防止)


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


def demand_caps(shops):
    """店舗抽選と現在価格から動物種ごとの保有上限を出す。

    店舗需要(個/日): ミルク 6*店+1 / 毛糸 12*店+1 / 卵 6*店+1。
    産出(個/頭日): 牛0.5 / 羊0.33 / 鵞鳥1。店舗ゼロでも2頭は町センターで回る。
    """
    m = sum(shops.count(s) for s in MILK_SHOPS)
    y = sum(shops.count(s) for s in WOOL_SHOPS)
    e = sum(shops.count(s) for s in EGG_SHOPS)
    # 種別上限7: 単品全張りはミラー戦(相手も同品目供給)で暴落一蓮托生になる
    return {"COW": min(7, 2 + 6 * m), "SHEEP": min(7, 2 + 12 * y),
            "GOOSE": min(7, 2 + 3 * e)}


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
    hour = obs.get("hour", 0)
    money = me.get("money", 0)
    market_obs = obs.get("market") or {}
    prices = market_obs.get("prices") or {}
    minv = market_obs.get("inventory") or {}
    shops = list((obs.get("town") or {}).get("unlocked_shops") or [])
    caps = demand_caps(shops)
    n_extra_land = len(me.get("unlocked_quadrants") or ["NW"]) - 1

    def tile_at(x, y):
        try:
            return tiles[y][x]
        except Exception:
            return "LOCKED"

    # ---- 動物の棚卸し ----
    placed = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    carried_animals = {a: sum(inv.get(a, 0) for inv in invs) for a in ANIMALS}
    owned = {a: placed[a] + carried_animals[a] + shed.get(a, 0) for a in ANIMALS}
    unfed_animals = 0
    todos = []  # (priority, x, y, op(list), need)  need: None|"WHEAT"|動物種|...
    built = {"PASTURE": 0, "COOP": 0}
    empty_structs = {"PASTURE": [], "COOP": []}
    free_animal_tiles = []

    for x, y in ANIMAL_TILES:
        t = tile_at(x, y)
        if t is None:
            free_animal_tiles.append((x, y))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((2.6, x, y, ["DIG"], None))
        elif isinstance(t, dict) and t.get("kind") in ("PASTURE", "COOP"):
            built[t["kind"]] += 1
            if not t.get("animal"):
                empty_structs[t["kind"]].append((x, y))
            else:
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

    owned = {a: placed[a] + carried_animals[a] + shed.get(a, 0) for a in ANIMALS}
    owned_total = sum(owned.values())

    # ---- 次に買う動物(キャップ付き貪欲): 建設の先行にも使う ----
    next_buy = None
    if owned_total < MAX_ANIMALS:
        cands = [a for a, s in ANIMALS.items()
                 if day <= s["last_buy"] and owned[a] < caps[a]]
        if cands:
            next_buy = max(cands, key=lambda a: ANIMALS[a]["value"])

    # ---- 構造物の動的建設: 家なし動物(+購入予定1頭)ぶんだけ建てる ----
    need_struct = {"PASTURE": 0, "COOP": 0}
    for a, spec in ANIMALS.items():
        need_struct[spec["structure"]] += owned[a]
    if next_buy:
        need_struct[ANIMALS[next_buy]["structure"]] += 1
    for st in ("PASTURE", "COOP"):
        shortage = need_struct[st] - built[st]
        for x, y in free_animal_tiles[:max(0, shortage)]:
            todos.append((2.6, x, y, ["BUILD_" + st], None))
        free_animal_tiles = free_animal_tiles[max(0, shortage):]

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

    # ---- メロン: 空き地に波状植付。水やりは本業より低優先度、収穫は高優先度 ----
    free_melon_tiles = 0
    for x, y in MELON_TILES:
        t = tile_at(x, y)
        if t == "LOCKED":
            continue  # 未購入の区画。BUY_LAND 後に解放
        if t is None:
            free_melon_tiles += 1
            if day <= MELON_PLANT_LAST and hour <= LAST_PLANT_HOUR:
                todos.append((4.6, x, y, ["PLANT", "MELON"], "MSEED"))
        elif isinstance(t, dict) and t.get("kind") == "PLANT":
            age = day - t.get("planted_day", day)
            if age >= MELON_FIRST_YIELD and t.get("yield_units", 0) > 0:
                todos.append((1.9, x, y, ["HARVEST"], None))  # 高付加価値を確実に回収
            if not t.get("watered_today"):
                # 枯死防止(consecutive>=1)は本業に次ぐ優先、通常水やりは最後
                pri = 1.05 if t.get("consecutive_unwatered", 0) >= 1 else 3.2
                todos.append((pri, x, y, ["WATER"], None))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((6.0, x, y, ["DIG"], None))

    # 最終日: 手持ちの収穫物をシェッドに DROP して換金対象にする
    if day >= FINAL_DAY:
        for ui, inv in enumerate(invs):
            if sum(inv.values()) > 0:
                todos.append((2.1, -1, -1, ["DROP"], f"UNIT{ui}"))

    # 動物の設置: シェッドに動物がいて空き構造物があるなら PLACE / PICKUP
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
    planned_melon_use = 0
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
            if need == "MSEED" and planned_melon_use >= seeds.get("MELON", 0):
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
        if need == "MSEED":
            planned_melon_use += 1
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
    # プレミアム品: 高値なら全量、それ以外は市場在庫の I0 回帰ぶんだけ売る
    for item, floor in SELL_FLOORS.items():
        n = shed.get(item, 0)
        if n <= 0:
            continue
        if day >= DUMP_DAY or shed_total >= 85 or prices.get(item, 0) >= floor:
            market.append(["SELL", item, n])
        else:
            budget = I0 + GLUT_SLACK - minv.get(item, I0)
            if budget > 0:
                market.append(["SELL", item, min(n, budget)])
    n_fert = shed.get("FERTILIZER", 0)
    if n_fert > 0 and (prices.get("FERTILIZER", 0) >= FERT_FLOOR
                       or day >= DUMP_DAY or shed_total >= 85):
        market.append(["SELL", "FERTILIZER", n_fert])

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

    # 土地購入(拡張分の空き地を確保。潤沢なときだけ発火 → 貧乏ゲームは lean)
    if n_extra_land < LAND_MAX_EXTRA and day >= 3:
        price = LAND_PRICES[n_extra_land]
        if money >= price + LAND_BUFFERS[n_extra_land]:
            market.append(["BUY_LAND"])
            money -= price

    # 動物購入(需要キャップ付き貪欲、予算と期限内)
    if next_buy and money >= ANIMALS[next_buy]["cost"] + 200:
        market.append(["BUY_ANIMAL", next_buy, 1])
        money -= ANIMALS[next_buy]["cost"]

    # メロン種の補充(空き地ぶん、運転資金を残して)
    if day <= MELON_PLANT_LAST and free_melon_tiles > seeds.get("MELON", 0):
        want = min(free_melon_tiles - seeds.get("MELON", 0), 4)
        affordable = int(max(0, money - MELON_CASH_BUFFER) // MELON_SEED_COST)
        qty = min(want, affordable)
        if qty >= 1:
            market.append(["BUY_SEED", "MELON", qty])
            money -= qty * MELON_SEED_COST

    # 小麦種の補充
    empty_wheat = sum(1 for x, y in WHEAT_TILES if tile_at(x, y) is None)
    if day <= LAST_PLANT_DAY and empty_wheat > seeds.get("WHEAT", 0) and money >= 60:
        market.append(["BUY_SEED", "WHEAT", min(empty_wheat - seeds.get("WHEAT", 0), 4)])
        money -= 40

    # 雇用(最終日も回収+DROP要員として安価なので雇う)
    hires_today = me.get("hires_today", 0)
    if len(hand_pos) < TARGET_HANDS and hires_today < TARGET_HANDS and money > 60:
        market.append(["HIRE"])

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:12]}
