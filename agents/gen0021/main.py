"""gen0021 — gen0020(上位型丸ごと実装)の over-reinvestment 破綻を是正（親: gen0020）。

EXP0020: gen0020 は メロンIPO(d10)の proceeds を全額 SW土地+2波+動物10+hands14 に
即投入して現金 buffer を $20 にし、feed 小麦が買えず動物が d14 に escape（milk/wool
喪失）→ 最終 $6-11k で gen0018($52k) に大敗。原因は「維持力(labor/feed)を超えた拡張」。
是正: (1) 土地は 2枚まで(SW を買わない)、(2) 全 discretionary buy(土地/動物/種)に
現金リザーブ RESERVE を課し、メロン proceeds を運転資金として残す。動物 escape を止め
資金曲線を立ち上げる。骨格(メロン第1波・NE d6・小麦自給・hands 装備)は gen0020 から継承。

6日間の LB 停滞（~559 vs 上位 2800+、最終資金 $40-65k vs $85-155k）を破る大改造。
出典: knowledge/scout/2026-09-04_public-knowledge.md §2（日次骨格）/§4（売却）/§5（実行細部）。

日次骨格:
- d0: 羊4購入（PASTURE建設）、メロン種8、小麦種7、飼料小麦5を market slot 0
      （開幕 feed denial 対策）、HIRE 5。現金はほぼ使い切る。
- d2-8: 牛を肥料/羊毛収入で 8 頭まで積み増し（d0 は資金上メロン優先で牛なし）。
- d6: BUY_LAND #1 (NE $1k)。羊毛初売り（CARE 6日分バンク → 4頭×6個）が原資。
- d8: イチゴ種9 を NE に植付（早出し2本は d4 に NW 残地へ）。
- d10: メロン8タイル収穫 → DROP → 一括SELL → 同ターンの後続スロットで
      BUY_LAND #2 (SW $2k) + HIRE を 14 へ + メロン種12/イチゴ種16（第2波）。
      SELL は shed からのみなので DROP を挟む（挟まないと土地購入が翌日にずれる）。
- d11-19: 小麦自給（20タイル回転で飼料12/日を賄う）、牛乳/羊毛/イチゴは
      高値即売り + hour==0 トリクル。肥料は毎朝即売り（d0 が最高値で単調減衰）。
- d19-25: メロン跡地に終盤小麦ブロック（小麦は終盤に値上がりする唯一の帯）。
- d29: 全量清算 + 手持ち DROP。
- SE とガチョウは買わない（上位メタ: 牛8-9+羊4-6、SE は ROI 負）。

機構（ユニット割当 todos キュー + 最近傍割当 + claimed、市場売却の床/トリクル、
給餌日課、種数カウントによる全員PASS事故防止）は gen0018 から再利用。
agent は必ずファイル末尾で定義（ローダは最後に束縛された callable を選ぶ）。
"""

SHED_TILES = [(4, 4), (5, 4), (4, 5), (5, 5)]  # シェッド操作可能な立ち位置

ANIMALS = {
    "COW": {"cost": 400, "product": "MILK", "last_buy": 18},
    "SHEEP": {"cost": 500, "product": "WOOL", "last_buy": 10},
}
MAX_ANIMALS = 12  # 牛8 + 羊4

MILK_SHOPS = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
WOOL_SHOPS = ("YARN_STORE",)
STRAW_SHOPS = ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")

# 12 パスチャ: NW 6（シェッド近傍）+ NE 6（d6 解放後）。シェッド4タイルは常に空ける。
PASTURE_TILES = [(3, 3), (2, 3), (3, 4), (2, 4), (1, 3), (1, 4),
                 (5, 3), (6, 3), (6, 4), (5, 2), (6, 2), (7, 3)]

# 作物タイルは (x, y, from_day)。windows は植付可能な日の帯（複数可）。
CROP_PLANS = {
    "MELON": {
        # 第1波: NW 8（d0 植え → d10 IPO）。第2波: 跡地8 + SW 4 = 12（d10-12 → d20）。
        "tiles": [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0),
                  (0, 1, 0), (1, 1, 0), (2, 1, 0),
                  (0, 5, 10), (1, 5, 10), (2, 5, 10), (3, 5, 10)],
        "windows": [(0, 2), (10, 12)],
        "plant_pri": 3.30, "water_pri": 2.90, "seed_cost": 80, "buy_cap": 12,
    },
    "STRAWBERRY": {
        # 早出し2 (d4, NW残地) + 第1波9 (d8, NE) + 第2波16 (d10, SW+NE)。
        # age10 で初産、以後隔日×4。d13 植えが d29 收穫の限界。
        "tiles": [(0, 3, 4), (0, 4, 4),
                  (5, 0, 8), (6, 0, 8), (7, 0, 8), (8, 0, 8), (9, 0, 8),
                  (5, 1, 8), (6, 1, 8), (7, 1, 8), (8, 1, 8),
                  (9, 1, 10),
                  (0, 6, 10), (1, 6, 10), (2, 6, 10), (3, 6, 10), (4, 6, 10),
                  (0, 7, 10), (1, 7, 10), (2, 7, 10), (3, 7, 10), (4, 7, 10),
                  (0, 8, 10), (1, 8, 10), (2, 8, 10), (3, 8, 10), (4, 8, 10)],
        "windows": [(4, 13)],
        "plant_pri": 3.35, "water_pri": 3.05, "seed_cost": 100, "buy_cap": 16,
    },
    "WHEAT": {
        # 基幹7 (NW) + 自給拡張13 (d10: SW南列 + NE東列) + 終盤ブロック12
        # (d19: メロン跡地。d20-21 に空く → d25 植付で d29 收穫が間に合う)。
        "tiles": [(3, 1, 0), (4, 1, 0), (0, 2, 0), (1, 2, 0), (2, 2, 0),
                  (3, 2, 0), (4, 2, 0),
                  (0, 9, 10), (1, 9, 10), (2, 9, 10), (3, 9, 10), (4, 9, 10),
                  (7, 2, 10), (8, 2, 10), (9, 2, 10), (8, 3, 10), (9, 3, 10),
                  (8, 4, 10), (9, 4, 10), (7, 4, 10),
                  (0, 0, 19), (1, 0, 19), (2, 0, 19), (3, 0, 19), (4, 0, 19),
                  (0, 1, 19), (1, 1, 19), (2, 1, 19),
                  (0, 5, 19), (1, 5, 19), (2, 5, 19), (3, 5, 19)],
        "windows": [(0, 25)],
        "plant_pri": 3.40, "water_pri": 3.00, "seed_cost": 10, "buy_cap": 12,
    },
}

BASE_VALUE = {"MELON": 250, "WOOL": 200, "MILK": 160, "STRAWBERRY": 120,
              "FERTILIZER": 100, "TOMATO": 60, "EGG": 50, "CARROT": 35}
DROP_VALUE = 500  # 手持ち売却価値がこれ以上なら日中に DROP（Rayk C72: 閾値500が最良）

LAST_PLANT_DAY = 25   # d25 植付 → d29 に age4 で收穫が間に合う限界
LAST_PLANT_HOUR = 20  # 終業間際の植付は当日の水やりが間に合わず確定枯れ
LAST_FEED_DAY = 28
DUMP_DAY = 28         # これ以降は価格を問わず全量売却
FINAL_DAY = 29        # 手持ちを DROP してでも換金する日

SELL_FLOORS = {"MILK": 96, "WOOL": 120, "STRAWBERRY": 72}  # base比0.6で即全量売り
ALWAYS_SELL = ["MELON", "FERTILIZER", "EGG", "CARROT", "TOMATO"]
# メロン: シーズン合計~110個 < 床158個 → 常に全量。肥料: d0が最高値で減衰 → 即売り。
I0 = 10000
GLUT_SLACK = 10
SHED_DUMP = 78  # shed+当日流入がこれ以上ならプレミアム品も全量ダンプ(overflow回避)
LAND_PRICES = [1000, 2000, 4000]
FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
HIRES_PER_TURN = 3
# EXP0020: 現金 buffer を0にする再投資が動物 escape を招いた。discretionary buy
# (土地/動物/種) は RESERVE を残す。feed 小麦の買い増しは例外(維持が最優先)。
RESERVE = 400


def cow_target(day):
    """d0 は資金上メロン8粒を優先（牛は d2 の肥料収入から）。d8 に 8 頭完成。"""
    if day < 2:
        return 0
    if day < 5:
        return 1
    if day < 6:
        return 2
    if day < 7:
        return 4
    if day < 8:
        return 6
    return 8


def hands_target(day):
    """d10/d20 は土地+植付の最繁忙日で 14。fib コストは 12 人で $376/日と安い。"""
    if day == 0:
        return 5
    if day < 5:
        return 4
    if day < 10:
        return 7
    if day == 10 or day == 20:
        return 14
    if day < 29:
        return 12
    return 10


def land_target(day):
    """unlocked_quadrants の目標数。NE=d6 のみ。EXP0020: SW(3枚目)は維持力を超え
    メロン proceeds を食い潰して動物 escape を招いたので買わない。SE も買わない。"""
    if day >= 6:
        return 2
    return 1


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


def premium_absorb(shops):
    """町がプレミアム品を1日に吸収する量（床未満価格でのトリクル売りの安全レート）。"""
    m = sum(shops.count(s) for s in MILK_SHOPS)
    y = sum(shops.count(s) for s in WOOL_SHOPS)
    s = sum(shops.count(s) for s in STRAW_SHOPS)
    return {"MILK": 1 + 6 * m, "WOOL": 1 + 12 * y, "STRAWBERRY": 1 + 6 * s}


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

    def tile_at(x, y):
        try:
            return tiles[y][x]
        except Exception:
            return "LOCKED"

    todos = []  # (priority, x, y, op(list), need)

    # ---- 盤面パス（内容駆動: どのタイルに何があっても世話する）----
    placed = {"COW": 0, "SHEEP": 0, "GOOSE": 0}
    unfed_animals = 0
    built_pastures = 0
    empty_pastures = []
    for y in range(len(tiles)):
        row = tiles[y] or []
        for x in range(len(row)):
            t = row[x]
            if not isinstance(t, dict):
                continue
            kind = t.get("kind")
            if kind == "PLANT":
                crop = t.get("crop")
                age = day - t.get("planted_day", day)
                yu = t.get("yield_units", 0)
                if crop == "MELON":
                    ripe = age >= 10
                    hpri, wpri = 1.9, 2.90
                elif crop == "STRAWBERRY":
                    ripe = True  # ongoing: yield_units>0 なら即収穫
                    hpri, wpri = 2.08, 3.05
                else:  # WHEAT (and defensively any other one-time crop)
                    ripe = age >= 4 or (day >= DUMP_DAY and age >= 2)
                    hpri, wpri = 2.2, 3.00
                if yu > 0 and ripe:
                    todos.append((hpri, x, y, ["HARVEST"], None))
                if not t.get("watered_today") and day < FINAL_DAY:
                    if crop == "STRAWBERRY" and age >= 16:
                        pass  # 生産終了(4回産み切り)、水やり無価値
                    elif t.get("consecutive_unwatered", 0) >= 1:
                        todos.append((1.0, x, y, ["WATER"], None))  # 枯死防止
                    elif not (yu > 0 and ripe):
                        todos.append((wpri, x, y, ["WATER"], None))
            elif kind in ("PASTURE", "COOP"):
                if kind == "PASTURE":
                    built_pastures += 1
                a = t.get("animal")
                if not a:
                    if kind == "PASTURE":
                        empty_pastures.append((x, y))
                    continue
                placed[a] = placed.get(a, 0) + 1
                if day <= LAST_FEED_DAY:
                    if not t.get("fed_today"):
                        unfed_animals += 1
                        pri = 0.0 if t.get("consecutive_unfed", 0) >= 1 else 1.2
                        todos.append((pri, x, y, ["FEED"], "WHEAT"))
                    if not t.get("cared_today"):
                        todos.append((3.5, x, y, ["CARE"], None))
                if t.get("yield_units", 0) > 0:
                    todos.append((2.0, x, y, ["HARVEST"], None))
                if t.get("fertilizer_available"):
                    todos.append((4.0, x, y, ["COLLECT_FERTILIZER"], None))

    carried_animals = {a: sum(inv.get(a, 0) for inv in invs) for a in ANIMALS}
    owned = {a: placed.get(a, 0) + carried_animals[a] + shed.get(a, 0)
             for a in ANIMALS}
    owned_total = sum(owned.values())

    # ---- パスチャ建設（1日先読み: 明日の牛購入分まで先に建てる）----
    free_slots = []
    for x, y in PASTURE_TILES:
        t = tile_at(x, y)
        if t is None:
            free_slots.append((x, y))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((2.6, x, y, ["DIG"], None))
    want_built = min(len(PASTURE_TILES),
                     max(owned_total, 4 + cow_target(min(day + 1, 29))))
    shortage = want_built - built_pastures
    for x, y in free_slots[:max(0, shortage)]:
        todos.append((2.6, x, y, ["BUILD_PASTURE"], None))

    # ---- 植付スケジュール（役割タイル + 植付窓）----
    hour_ok = hour <= LAST_PLANT_HOUR
    plant_slots = {"MELON": 0, "STRAWBERRY": 0, "WHEAT": 0}
    for crop, plan in CROP_PLANS.items():
        w_open = (day <= LAST_PLANT_DAY
                  and any(a <= day <= b for a, b in plan["windows"]))
        if not w_open:
            continue
        for x, y, from_day in plan["tiles"]:
            if day < from_day:
                continue
            t = tile_at(x, y)
            if t is None:
                plant_slots[crop] += 1
                if hour_ok:
                    todos.append((plan["plant_pri"], x, y,
                                  ["PLANT", crop], "SEED:" + crop))
            elif isinstance(t, dict) and t.get("kind") == "WEED":
                # 予定作業(植付)を今塞いでいる雑草だけ DIG（scout §5）
                todos.append((2.6, x, y, ["DIG"], None))

    # ---- 動物の設置: シェッドに動物がいて空きパスチャがあるなら PICKUP → PLACE ----
    for a in ANIMALS:
        in_shed = shed.get(a, 0)
        for x, y in empty_pastures[: in_shed + carried_animals[a]]:
            todos.append((2.4, x, y, ["PLACE", a], a))
        if in_shed > 0 and empty_pastures:
            todos.append((2.5, 4, 4, ["PICKUP", a, 1], "SHEDOP"))

    # ---- 給餌用小麦の受け取り ----
    shed_wheat = shed.get("WHEAT", 0)
    if unfed_animals > 0 and shed_wheat > 0:
        todos.append((0.5, 4, 4,
                      ["PICKUP", "WHEAT", min(shed_wheat, unfed_animals, 6)],
                      "SHEDOP"))

    # ---- 手持ちの現金化 DROP（d10 メロンIPO を当日資金にする要）----
    for ui, inv in enumerate(invs):
        if day >= FINAL_DAY:
            if sum(inv.values()) > 0:
                todos.append((2.1, -1, -1, ["DROP"], "UNIT%d" % ui))
        else:
            val = sum(BASE_VALUE.get(k, 0) * v for k, v in inv.items())
            if val >= DROP_VALUE:
                todos.append((2.05, -1, -1, ["DROP"], "UNIT%d" % ui))

    # ---- ユニット割当（gen0018 の最近傍割当 + claimed）----
    fx, fy = me.get("farmer", [4, 4])
    hand_pos = list(me.get("hands") or [])
    units = [(fx, fy)] + [(hx, hy) for hx, hy in hand_pos]
    claimed = set()
    planned_seed = {}
    planned_wheat_pickup = 0
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
            if need and need.startswith("SEED:"):
                crop = need[5:]
                if planned_seed.get(crop, 0) >= seeds.get(crop, 0):
                    continue  # 種数超過の PLANT は全員無効になる事故を防ぐ
            if need in ANIMALS and inv.get(need, 0) <= 0:
                continue
            if need and need.startswith("UNIT"):
                if need != "UNIT%d" % ui:
                    continue
                x, y = min(SHED_TILES,
                           key=lambda p: abs(ux - p[0]) + abs(uy - p[1]))
            if need == "SHEDOP":
                if op[0] == "PICKUP" and op[1] == "WHEAT":
                    if my_wheat >= 2 or planned_wheat_pickup >= 2:
                        continue
                if op[0] == "PICKUP" and op[1] in ANIMALS and inv.get(op[1], 0) > 0:
                    continue
                x, y = min(SHED_TILES,
                           key=lambda p: abs(ux - p[0]) + abs(uy - p[1]))
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
        if need and need.startswith("SEED:"):
            planned_seed[need[5:]] = planned_seed.get(need[5:], 0) + 1
        if need == "SHEDOP" and op[0] == "PICKUP" and op[1] == "WHEAT":
            planned_wheat_pickup += 1
        if (ux, uy) == (x, y):
            actions.append(list(op))
        else:
            actions.append([step_toward(ux, uy, x, y)])

    # ---- 市場（優先順に組み立て、10スロットに切る。SELL の代金は同ターンの
    #      後続スロットの BUY/HIRE/LAND に使える）----
    market = []
    mest = float(money)  # 概算残高（売却は7掛けで保守的に計上）

    # (0) 開幕 feed denial: 小麦5個の購入注文を必ず slot 0 に置く（scout §4）
    if day == 0 and hour == 0:
        market.append(["BUY_PRODUCT", "WHEAT", 5])
        mest -= 5 * (prices.get("WHEAT", 25) + 2)

    # (1) 売却
    total_placed = sum(placed.values())
    shed_total = sum(shed.values())
    carried_total = sum(sum(inv.values()) for inv in invs)
    shed_pressure = shed_total + carried_total
    feed_buffer = total_placed * 3 + 2
    if shed_wheat > feed_buffer or day >= DUMP_DAY:
        n = shed_wheat if day >= FINAL_DAY else shed_wheat - feed_buffer
        if n > 0:
            market.append(["SELL", "WHEAT", n])
            mest += n * prices.get("WHEAT", 25) * 0.7
    for item in ALWAYS_SELL:
        n = shed.get(item, 0)
        if n > 0:
            market.append(["SELL", item, n])
            mest += n * prices.get(item, BASE_VALUE.get(item, 1)) * 0.7
    town_absorb = premium_absorb(shops)
    for item, floor in SELL_FLOORS.items():
        n = shed.get(item, 0)
        if n <= 0:
            continue
        p = prices.get(item, 0)
        if day >= DUMP_DAY or shed_pressure >= SHED_DUMP or p >= floor:
            market.append(["SELL", item, n])
            mest += n * p * 0.7
        else:
            # 床未満は hour==0 の1日1回だけ町吸収レート分をトリクル（gen0008/0018）
            trickle = 0
            if hour == 0 and p > 1:
                trickle = town_absorb.get(item, 1)
            budget = max(trickle, I0 + GLUT_SLACK - minv.get(item, I0))
            if budget > 0:
                qty = min(n, budget)
                market.append(["SELL", item, qty])
                mest += qty * p * 0.7

    # (2) 給餌用小麦の補充（自給不足分のみ。土地・種より優先 = 動物を守る）
    carried_wheat = sum(inv.get("WHEAT", 0) for inv in invs)
    if owned_total > 0 and day <= LAST_FEED_DAY:
        stock = shed_wheat + carried_wheat
        if stock < owned_total:
            want = min(owned_total * 2 - stock, 12)
            wp = prices.get("WHEAT", 45)
            qty = min(want, int(mest // (wp + 5)))
            if qty >= 1:
                market.append(["BUY_PRODUCT", "WHEAT", qty])
                mest -= qty * (wp + 3)

    # (3) 土地（d6: NE, d10: SW。mest には同ターンの売却代金が入っている）
    unlocked = list(me.get("unlocked_quadrants") or ["NW"])
    n_extra = len(unlocked) - 1
    if len(unlocked) < land_target(day) and 0 <= n_extra < len(LAND_PRICES):
        cost = LAND_PRICES[n_extra]
        if mest >= cost + RESERVE:
            market.append(["BUY_LAND"])
            mest -= cost

    # (4) 動物購入（不足数を一括、パスチャ数 12 でキャップ）
    room = MAX_ANIMALS - owned_total
    for a in ("SHEEP", "COW"):
        spec = ANIMALS[a]
        if day > spec["last_buy"]:
            continue
        tgt = 4 if a == "SHEEP" else cow_target(day)
        deficit = min(tgt - owned[a], room)
        if deficit <= 0:
            continue
        afford = int((mest - RESERVE) // spec["cost"])
        qty = min(deficit, afford)
        if qty >= 1:
            market.append(["BUY_ANIMAL", a, qty])
            mest -= qty * spec["cost"]
            room -= qty

    # (5) 雇用（1ターン最大3件、fib 次コストで資金ゲート）
    tgt_h = hands_target(day)
    hires_today = me.get("hires_today", 0)
    k = 0
    while (k < HIRES_PER_TURN and len(hand_pos) + k < tgt_h
           and hires_today + k < tgt_h):
        c = FIB[min(hires_today + k, len(FIB) - 1)]
        if mest < c + 20:
            break
        market.append(["HIRE"])
        mest -= c
        k += 1

    # (6) 種の補充（開いている植付枠 − 所持種。メロン > イチゴ > 小麦の順）
    for crop in ("MELON", "STRAWBERRY", "WHEAT"):
        plan = CROP_PLANS[crop]
        deficit = plant_slots[crop] - seeds.get(crop, 0)
        if deficit <= 0:
            continue
        qty = min(deficit, plan["buy_cap"],
                  int(max(0.0, mest - RESERVE) // plan["seed_cost"]))
        if qty >= 1:
            market.append(["BUY_SEED", crop, qty])
            mest -= qty * plan["seed_cost"]

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}


def agent(obs):
    """例外はゲーム内即敗因: 全コードパスで dict を返す。（末尾定義 = ローダ対策）"""
    try:
        return _agent(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
