"""gen0009 — Track B 新系統: 段階的スケール再投資（親: gen0008）。

負け分析 ep104768100（knowledge/analysis/2026-09-03_loss-scale-reinvestment.md）:
上位帯（Hazqeel）は day16 まで互角のあと day20 以降に約$6k/日で加速し、
最終盤は 10 hands / 3クアドラント / トマト18枚 の大規模作付けだった。こちらは
4 hands / NW のみ / 作物ゼロで $2k/日頭打ち。**中核（動物経済）が資金化された
後の段階的スケール再投資**（hand 追加＋ hinge 作物トマトの増設）が最重要の未装備
レバー、というのが本世代の仮説。

gen0004（Track B の先行世代）は同じ「拡張」でも**序盤**（day>=3, money>=2500）に
土地購入とメロン一括で走り、中核キャッシュを枯らして自滅した（vs 王者21.7%）。
本世代はその轍を踏まないよう、次の規律を課す:

 (1) 段階投資は「中核が資金化された後」にのみ発火: day>=SCALE_DAY(12) かつ
     money>=SCALE_CASH(6000)。この条件を割ったらトマト新規投資と増員を止める
     （既存のトマトは水やり・収穫を継続し、見捨てない）。
 (2) 土地購入はしない。gen0004 で local H2H では割に合わないと実証済み
     （NW に既に空き7タイル、律速は労働と需要）。増設は NW 空きタイルに限定し、
     単一変数（＝トマト作付け）で gen0008 と比較する。land は勝ってから次世代で足す。
 (3) 作物はトマトを選ぶ: hinge(below_target0.40) なので pizza/farmers market の
     需要がある限り base$60 付近を保ち、glut 側は sqrt(0.60) で暴落しにくい
     （メロン/イチゴのような premium 床落ちが無い）。ongoing×4 で 1タイル4個。
     day<=LAST_TOMATO_PLANT(18) までに植えれば 4 結実（age8-11）が day29 までに間に合う。

トマトは ALWAYS_SELL に元から入っているので売却側は gen0008 のまま
（毎日4-5個程度の少量売りで hinge 曲線を動かさない）。
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
# NW 空きタイル(y0 の5枚 + (0,1)(1,1)) = 段階投資フェーズのトマト作付け地
TOMATO_TILES = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (0, 1), (1, 1)]
SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]  # シェッド操作可能な立ち位置

LAST_PLANT_DAY = 25        # day25植付 → day29 に age4 で収穫が間に合う限界
LAST_PLANT_HOUR = 20       # 終業間際の植付は当日の水やりが間に合わず確定枯れ
LAST_FEED_DAY = 28         # day29 の給餌は生産に間に合わない
DUMP_DAY = 28              # これ以降は価格を問わず全量売却
FINAL_DAY = 29             # 手持ちを DROP してでも換金する日
TARGET_HANDS = 4
SCALE_HANDS = 8            # 段階投資フェーズの増員先(farmer込み9ユニット)。
                          # 中核(10動物+8小麦)だけで7ユニットが飽和するため、
                          # トマトの植付・水やり労働を賄うには追加の手が要る。
                          # hand 追加コストは fib和で 8頭 88/日と安価(NFR: 数百$/18日)。
MAX_ANIMALS = 10

# --- 段階的スケール再投資(gen0009) ---
SCALE_DAY = 12             # これ以前は投資しない(中核の資金化を待つ)
SCALE_CASH = 6000          # この現金があれば中核は回っている(段階投資GO)
LAST_TOMATO_PLANT = 18     # day18植付 → age8-11=day26-29 に4結実が間に合う限界
TOMATO_SEED = 50           # トマト種の単価(README Object Types)
TOMATO_BUY_MAX = 3         # 1回の種購入上限(現金保護のため小分け)

SELL_FLOORS = {"MILK": 96, "WOOL": 120}      # base比0.6: これ以上なら即全量売り
FERT_FLOOR = 70
ALWAYS_SELL = ["EGG", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
I0 = 10000
GLUT_SLACK = 10  # I0 をこれ以上超えて売らない(プレミアム品の暴落防止)
SHED_DUMP = 78   # shed+当日流入がこれ以上ならプレミアム品も全量ダンプ(overflow回避)


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
    """店舗抽選と現在価格から動物種ごとの保有上限を出す。"""
    m = sum(shops.count(s) for s in MILK_SHOPS)
    y = sum(shops.count(s) for s in WOOL_SHOPS)
    e = sum(shops.count(s) for s in EGG_SHOPS)
    return {"COW": min(7, 2 + 6 * m), "SHEEP": min(7, 2 + 12 * y),
            "GOOSE": min(7, 2 + 3 * e)}


def premium_absorb(shops):
    """町がプレミアム品を1日に吸収する量（トリクル売りの安全レート）。"""
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

    # 段階投資フェーズ判定: 中核(動物経済)が資金化された後にのみトマトを増設する。
    scaling = day >= SCALE_DAY and money >= SCALE_CASH

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
    need_struct = {"PASTURE": 0, "COOP": 0}
    for a, spec in ANIMALS.items():
        need_struct[spec["structure"]] += owned[a]
    deficit = {st: need_struct[st] - built[st] for st in need_struct}
    tiles_for_owned = sum(max(0, d) for d in deficit.values())

    # ---- 次に買う動物(キャップ付き貪欲): 家を確保できる種のみ ----
    next_buy = None
    if owned_total < MAX_ANIMALS:
        def has_home(a):
            st = ANIMALS[a]["structure"]
            if deficit[st] < 0:
                return True
            return len(free_animal_tiles) > tiles_for_owned
        cands = [a for a, s in ANIMALS.items()
                 if day <= s["last_buy"] and owned[a] < caps[a] and has_home(a)]
        if cands:
            next_buy = max(cands, key=lambda a: ANIMALS[a]["value"])

    # ---- 構造物の動的建設 ----
    build_need = dict(need_struct)
    if next_buy:
        st0 = ANIMALS[next_buy]["structure"]
        if deficit[st0] >= 0:
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
                pri = 1.0 if t.get("consecutive_unwatered", 0) >= 1 else 3.0
                todos.append((pri, x, y, ["WATER"], None))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((6.0, x, y, ["DIG"], None))

    # ---- 段階的スケール再投資: NW空きタイルにトマトを増設(gen0009) ----
    # 中核資金化後(scaling)のみ植付。ongoing crop なので水やり・収穫は
    # scaling が解けても継続する(見捨てない)。トマトは HARVEST 時に tile が
    # 残る(4結実まで)ので、収穫は yield_units>0 で判定するだけでよい。
    for x, y in TOMATO_TILES:
        t = tile_at(x, y)
        if t is None:
            if scaling and day <= LAST_TOMATO_PLANT and hour <= LAST_PLANT_HOUR:
                # 植付は pri 2.3: 中核が飽和した労働の中でも確実に発火させる
                # (CARE 3.5 / COLLECT_FERTILIZER 4.0 / 通常WATER 3.0 を preempt)。
                # 一時作物6枚を数ターン埋めるだけなので低価値雑務からの奪取は僅少。
                # 枯死寸前の緊急WATER(1.0)や給餌(0-1.2)には譲る。
                todos.append((2.3, x, y, ["PLANT", "TOMATO"], "TSEED"))
        elif isinstance(t, dict) and t.get("kind") == "PLANT":
            if t.get("yield_units", 0) > 0:
                todos.append((2.15, x, y, ["HARVEST"], None))
            if not t.get("watered_today"):
                pri = 1.0 if t.get("consecutive_unwatered", 0) >= 1 else 3.0
                todos.append((pri, x, y, ["WATER"], None))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((6.0, x, y, ["DIG"], None))

    # 最終日: 手持ちの収穫物をシェッドに DROP して換金対象にする
    if day >= FINAL_DAY:
        for ui, inv in enumerate(invs):
            if sum(inv.values()) > 0:
                todos.append((2.1, -1, -1, ["DROP"], f"UNIT{ui}"))

    # 動物の設置
    for a, spec in ANIMALS.items():
        empties = list(empty_structs[spec["structure"]])
        in_shed = shed.get(a, 0)
        for x, y in empties[: in_shed + carried_animals[a]]:
            todos.append((2.4, x, y, ["PLACE", a], a))
        if in_shed > 0 and empties:
            for sx, sy in SHED_TILES:
                todos.append((2.5, sx, sy, ["PICKUP", a, 1], "SHEDOP"))
                break

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
    planned_tseed_use = 0
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
            if need == "TSEED" and planned_tseed_use >= seeds.get("TOMATO", 0):
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
                        continue
                if op[0] == "PICKUP" and op[1] in ANIMALS and inv.get(op[1], 0) > 0:
                    continue
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
        if need == "TSEED":
            planned_tseed_use += 1
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
    town_absorb = premium_absorb(shops)
    for item, floor in SELL_FLOORS.items():
        n = shed.get(item, 0)
        if n <= 0:
            continue
        if day >= DUMP_DAY or shed_pressure >= SHED_DUMP or prices.get(item, 0) >= floor:
            market.append(["SELL", item, n])
        else:
            trickle = 0
            if hour == 0 and prices.get(item, 0) > 1:
                trickle = town_absorb.get(item, 1)
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
            qty = min(want, affordable)
            if qty >= 1:
                market.append(["BUY_PRODUCT", "WHEAT", qty])
                money -= qty * wheat_price

    # 動物購入(需要キャップ付き貪欲、予算と期限内)
    if next_buy and money >= ANIMALS[next_buy]["cost"] + 200:
        market.append(["BUY_ANIMAL", next_buy, 1])
        money -= ANIMALS[next_buy]["cost"]

    # 種の補充(小麦)
    empty_wheat = sum(1 for x, y in WHEAT_TILES if tile_at(x, y) is None)
    if day <= LAST_PLANT_DAY and empty_wheat > seeds.get("WHEAT", 0) and money >= 60:
        market.append(["BUY_SEED", "WHEAT", min(empty_wheat - seeds.get("WHEAT", 0), 4)])
        money -= 40

    # トマト種の補充(段階投資フェーズのみ、現金保護のため小分け・運転資金を残す)
    if scaling and day <= LAST_TOMATO_PLANT:
        empty_tom = sum(1 for x, y in TOMATO_TILES if tile_at(x, y) is None)
        have_tom = seeds.get("TOMATO", 0)
        short = empty_tom - have_tom
        if short > 0 and money >= SCALE_CASH:
            qty = min(short, TOMATO_BUY_MAX)
            market.append(["BUY_SEED", "TOMATO", qty])
            money -= TOMATO_SEED * qty

    # 雇用(段階投資フェーズは SCALE_HANDS まで増員して拡張作物の労働を賄う)
    target_hands = SCALE_HANDS if scaling else TARGET_HANDS
    hires_today = me.get("hires_today", 0)
    if len(hand_pos) < target_hands and hires_today < target_hands and money > 60:
        market.append(["HIRE"])

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}
