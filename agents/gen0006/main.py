"""gen0006 — Track A: gen0003 の Codex 修正版（親: gen0003）。

gen0003 は「需要適応の動物経済」で下振れ乱数を引き上げたが、提出後の Codex
レビューで3つの静かな欠陥が判明した:
 (1) プレミアム品の売却ペーシング分岐は実質デッドコード。価格が床値を割る時点で
     市場在庫は既に I0+30 超なので budget=I0+10−inv≤0 になり売却量ゼロ。
     結局 gen0002 と同じ「床未満なら保留 → shed 逼迫で全量ダンプ($1床)」に落ちる。
 (2) next_buy の先行建設が最後の空きタイルを誤種別で埋めると、後から買った動物が
     シェッドに恒久滞留しうる（構造物の空き確認が購入条件に無い）。
 (3) shed_total≥85 の全量ダンプ判定が当日夜のドロップ流入を織り込まず、
     プレミアム品保留分でオーバーフロー（超過は破棄）を起こしやすい。

本世代の修正:
 (1) 真のトリクル売り。床値未満でも「町が今日吸収する量」だけ売る。町吸収レート
     =町センター1/日+店舗（ミルク店6/日、毛糸店は単品2x=12/日）で、これは
     demand_caps の増頭ペースとほぼ釣り合うため価格をほとんど動かさない。
     価格が$1床に張り付いている時だけは保留（町の吸収で在庫が抜け価格が戻るのを待つ）。
 (2) next_buy は「今日中に家を確保できる」場合（空き構造物 or 所有動物の住宅を
     満たした後に残る空きタイル）のみ許可。空き構造物がある種別は先行建設しない。
 (3) 全量ダンプ判定を shed_total + 手持ち在庫（当夜ドロップ流入）で行う。
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
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]  # シェッド操作可能な立ち位置

LAST_PLANT_DAY = 25        # day25植付 → day29 に age4 で収穫が間に合う限界
LAST_PLANT_HOUR = 20       # 終業間際の植付は当日の水やりが間に合わず確定枯れ
LAST_FEED_DAY = 28         # day29 の給餌は生産に間に合わない
DUMP_DAY = 28              # これ以降は価格を問わず全量売却
FINAL_DAY = 29             # 手持ちを DROP してでも換金する日
TARGET_HANDS = 4
MAX_ANIMALS = 10

SELL_FLOORS = {"MILK": 96, "WOOL": 120}      # base比0.6: これ以上なら即全量売り
FERT_FLOOR = 70
ALWAYS_SELL = ["EGG", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
I0 = 10000
GLUT_SLACK = 10  # I0 をこれ以上超えて売らない(プレミアム品の暴落防止)
SHED_DUMP = 85   # shed+当日流入がこれ以上ならプレミアム品も全量ダンプ(overflow回避)


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


def premium_absorb(shops):
    """町がプレミアム品を1日に吸収する量（トリクル売りの安全レート）。

    町センターが全品1/日、加えて店舗インスタンスが townShopSellInterval(=4turn)
    ごとに1個 → 1日6個。単品店(毛糸のYARN_STORE)は2x=12個/日。
    この量だけ売れば市場在庫はほぼ横ばい＝価格をほとんど動かさない。
    """
    m = sum(shops.count(s) for s in MILK_SHOPS)
    y = sum(shops.count(s) for s in WOOL_SHOPS)
    return {"MILK": 1 + 6 * m, "WOOL": 1 + 12 * y}


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
    market_obs = obs.get("market") or {}
    prices = market_obs.get("prices") or {}
    minv = market_obs.get("inventory") or {}
    shops = list((obs.get("town") or {}).get("unlocked_shops") or [])
    caps = demand_caps(shops)

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

    # ---- 住宅需給の棚卸し ----
    # need_struct[st] = その構造種を要する所有動物数、built[st] = 建設済み(空含む)。
    # deficit>0: 新規建設が要る所有動物数 / deficit<0: 空き構造物がある。
    need_struct = {"PASTURE": 0, "COOP": 0}
    for a, spec in ANIMALS.items():
        need_struct[spec["structure"]] += owned[a]
    deficit = {st: need_struct[st] - built[st] for st in need_struct}
    tiles_for_owned = sum(max(0, d) for d in deficit.values())

    # ---- 次に買う動物(キャップ付き貪欲): 家を確保できる種のみ ----
    # (fix2) 空き構造物 or 所有動物の住宅を満たした後に残る空きタイルが無ければ買わない。
    #        買った動物のシェッド恒久滞留を防ぐ。
    next_buy = None
    if owned_total < MAX_ANIMALS:
        def has_home(a):
            st = ANIMALS[a]["structure"]
            if deficit[st] < 0:      # 空いた構造物がある(先行建設不要)
                return True
            return len(free_animal_tiles) > tiles_for_owned  # 追加建設の余地
        cands = [a for a, s in ANIMALS.items()
                 if day <= s["last_buy"] and owned[a] < caps[a] and has_home(a)]
        if cands:
            next_buy = max(cands, key=lambda a: ANIMALS[a]["value"])

    # ---- 構造物の動的建設: 所有動物の不足を埋め、空き構造の無い種の next_buy 分だけ足す ----
    build_need = dict(need_struct)
    if next_buy:
        st0 = ANIMALS[next_buy]["structure"]
        if deficit[st0] >= 0:        # 空き構造物が無い時だけ新規建設を予約
            build_need[st0] += 1
    for st in ("PASTURE", "COOP"):
        shortage = build_need[st] - built[st]
        for x, y in free_animal_tiles[:max(0, shortage)]:
            todos.append((2.6, x, y, ["BUILD_" + st], None))
        free_animal_tiles = free_animal_tiles[max(0, shortage):]

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
    # (fix3) 当夜シェッドにドロップされる手持ち在庫も逼迫判定に織り込む。
    carried_total = sum(sum(inv.values()) for inv in invs)
    shed_pressure = shed_total + carried_total

    # 売却
    feed_buffer = total_animals * 3 + 2
    if shed_wheat > feed_buffer or day >= DUMP_DAY:
        n = shed_wheat if day >= DUMP_DAY else shed_wheat - feed_buffer
        if n > 0:
            market.append(["SELL", "WHEAT", n])
    for item in ALWAYS_SELL:
        if shed.get(item, 0) > 0:
            market.append(["SELL", item, shed[item]])
    # プレミアム品(MILK/WOOL): 高値なら全量、床未満は町吸収レート分だけトリクル。
    # (fix1) 旧版は budget=I0+SLACK−inv が床未満域で必ず≤0 → 売却ゼロのデッドコード
    #        だった。町が今日吸収する量(=demand_caps の増頭ペースと釣り合う)を
    #        下限に足すことで、$1で腐らせず在庫を寝かせない。価格が$1床に
    #        張り付いている時だけは保留し、町の吸収で在庫が抜けるのを待つ。
    town_absorb = premium_absorb(shops)
    for item, floor in SELL_FLOORS.items():
        n = shed.get(item, 0)
        if n <= 0:
            continue
        if day >= DUMP_DAY or shed_pressure >= SHED_DUMP or prices.get(item, 0) >= floor:
            market.append(["SELL", item, n])
        else:
            trickle = town_absorb.get(item, 1) if prices.get(item, 0) > 1 else 0
            budget = max(trickle, I0 + GLUT_SLACK - minv.get(item, I0))
            if budget > 0:
                market.append(["SELL", item, min(n, budget)])
    n_fert = shed.get("FERTILIZER", 0)
    if n_fert > 0 and (prices.get("FERTILIZER", 0) >= FERT_FLOOR
                       or day >= DUMP_DAY or shed_pressure >= SHED_DUMP):
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

    # 動物購入(需要キャップ付き貪欲、予算と期限内)
    if next_buy and money >= ANIMALS[next_buy]["cost"] + 200:
        market.append(["BUY_ANIMAL", next_buy, 1])
        money -= ANIMALS[next_buy]["cost"]

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
