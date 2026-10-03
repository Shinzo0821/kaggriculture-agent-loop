"""gen0019 — Track B: STR 肥料2倍化（親: gen0017、STR系統2世代目）。

gen0017（shop-aware STR ピボット）は vs gen0013 34.0%/−$893 で棄却された。
敗因は「無肥料 STR はタイル単価でメロン2波に勝てない」: STR 4収穫×base$120
= $480-800/タイル vs メロン ~$1,500/タイル。本世代の単一レバーは STR の肥料
2倍化で、これを $960-1,600/タイルに引き上げメロン同等以上にする。

【肥料機構（engine 実測、kaggriculture.py:769-800）】
 ongoing 作物は「肥料が効いている日 かつ 水やり済みの日」に scheduled 産出が
 1→2 に倍化。STR の scheduled 産出は end-of-day リフレッシュで
 planted+{9,11,13,15} 日（＝収穫が age10/12/14/16 で立つ前日）に yield_units を
 加算する。倍化条件は fertilized_until_day>=その日 かつ その日が watered。
 FERTILIZE は fertilized_until_day = day+2（当日含め3日有効）。
 → **age9 に FERTILIZE すれば eve 9・11（収穫1・2）を、age13 で eve 13・15
   （収穫3・4）を覆う**。肥料2個/タイルで4収穫全部2倍。
 （注: 計画時の「age10/14」は off-by-one で収穫2・4しか倍化しない。engine
   真値に合わせ age9/13 に修正した。）
 肥料は自軍動物の COLLECT_FERTILIZER 産（新規現金流出なし）。shed の余剰は
 従来通り売るが、STR 生育中は 2×若STR枚数を reserve して枯渇を防ぐ。

以下は親 gen0017 の設計メモ:

LB 敗戦分析（cycle3-5）で3サイクル連続、敗因＝「イチゴ(STR)を植えていない」。
STR は8ショップ型中4型（BRUNCH/ICE_CREAM/SMOOTHIE/FARMERS_MARKET）が需要で、
1店あたり6個/日を恒久吸収 → 需要店≥2 なら供給(7タイル×4収穫=28個)を吸収
(13-25個/日×10日)が大きく上回り、価格は base$120 以上に張り付く見込み。
STR は age10/12/14/16 に1個ずつ産出（ongoing）で、d13 植えが4収穫全取りの最終日。

gen0013 からの差分（単一レバー）: メロン2波目の shop-aware STR 差し替え。
 - `unlocked_shops` の STR 需要店 ≥2 で発動（抽選は d3/6/9/... の日境界で反映、
   エンジン kaggriculture.py:886 で確認）。
 - 発動時: メロンタイル(7)の空きに STRAWBERRY を植える（期限 d13、種$100）。
 - d10-11 で未発動なら植え付け保留（d12 朝に4回目抽選が見えるまで待つ）。
   d12 で <2 確定なら即メロン2波に復帰 → 不発時のコストは最大2日の遊休のみ
   （メロン d12-13 植え → d22-23 収穫は DUMP_DAY=28 に十分間に合う）。
 - STR は ongoing: yield_units>0 で即収穫(1.9)、植え替えなし・タイルは~d29 占有。
   水やりはメロンと同じ優先度体系（枯死防止 1.05 / 通常 3.2）。
 - 売却は ALWAYS_SELL のまま（需要店≥2 の吸収があるので即売りで暴落しない）。
 - 肥料2倍化（FERTILIZE は day+2 まで有効、当日肥料+水で収穫2倍）は物流が
   第2レバーになるため本世代では入れない（gen0018 候補）。

gen0013 の中核は不変: メロン資本スプリント d0 + TARGET_HANDS=7 + SCALE_HANDS=8。
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
TARGET_HANDS = 7           # (gen0013) 4→7: メロン7タイルぶんの仕事を先に作った上での
                           # 序盤増員。アブレーション h5/h6/h7/h8 = +3.4k/+16.0k/+23.2k/+11.2k
MAX_ANIMALS = 10

# --- 資金化後の増員（gen0010, 作物なし）---
SCALE_DAY = 12             # これ以前は増員しない（中核の資金化を待つ）
SCALE_CASH = 6000          # この現金があれば中核は回っている（増員GO）
SCALE_HANDS = 8            # 資金化後の増員先。EXP0009 アブレーションで
                           # 8hands・トマト無が gen0008 に +985/5戦だった値。
                           # 追加の手は中核動物(CARE/収穫/水やり/給餌/肥料)の
                           # 被覆にのみ回る。hand コストは fib和で安価。

# --- メロン資本スプリント（gen0012, gen0007モジュール移植 + d0開幕）---
MELON_TILES = [(0, 0), (1, 0), (2, 0), (3, 0), (4, 0), (0, 1), (1, 1)]  # NW spares
MELON_FIRST_YIELD = 10     # age>=10 で収穫可能（one-time, base1+水5=6@age10）
MELON_START_DAY = 0        # d0 開幕（gen0007 の 8 から変更。資本スプリント）
MELON_PLANT_LAST = 18      # day18植付 → age10=day28(DUMP) までに収穫
MELON_SEED_COST = 80
MELON_CASH_BUFFER = 2000   # メロン種購入時に残す運転資金（動物購入・給餌を守る）

# --- shop-aware STR ピボット（gen0017）---
STR_SHOPS = ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")
STR_PIVOT_MIN = 2          # STR 需要店がこれ以上で発動（吸収 13個/日 > 供給 2.8個/日）
STR_PLANT_LAST = 13        # d13 植え → age10/12/14/16 = d23/25/27/29 の4収穫全取り
STR_HOLD_FIRST = 10        # d10-11 は未発動でも植え付け保留（d12 の抽選を待つ）
STR_HOLD_LAST = 11
STR_SEED_COST = 100
# (gen0019) 肥料2倍化: age9/13 に FERTILIZE（各 fertilized_until_day=day+2 で
# eve 9,11 / 13,15 を覆う）。fertilized_until_day<day なら未カバー→施肥。
STR_FERT_AGES = (9, 11, 13, 15)   # eve 判定に使う奇数age（<day ガードで実発火は 9,13）
STR_FERT_AGE_MIN = 9
STR_FERT_AGE_MAX = 15

SELL_FLOORS = {"MILK": 96, "WOOL": 120}      # base比0.6: これ以上なら即全量売り
FERT_FLOOR = 70
ALWAYS_SELL = ["EGG", "CARROT", "TOMATO", "STRAWBERRY", "MELON"]
I0 = 10000
GLUT_SLACK = 10  # I0 をこれ以上超えて売らない(プレミアム品の暴落防止)
SHED_DUMP = 78   # shed+当日流入がこれ以上ならプレミアム品も全量ダンプ(overflow回避)
                 # (gen0008) 85→78: 同一ターン複数HARVESTのジャンプ(最大~16)でも
                 # 容量100を跨がないよう余裕を拡大(codexレビュー指摘)


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

    # (gen0017) STR ピボット判定。unlocked_shops は単調増加なので毎ターン再計算で安全。
    str_mode = sum(shops.count(s) for s in STR_SHOPS) >= STR_PIVOT_MIN
    plant_str_window = str_mode and day <= STR_PLANT_LAST
    str_hold = (not str_mode) and STR_HOLD_FIRST <= day <= STR_HOLD_LAST

    # 資金化後の増員判定（gen0010）: 中核が資金化された後にのみ手を足す。作物は足さない。
    scaling = day >= SCALE_DAY and money >= SCALE_CASH

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
                    # (gen0019) STR 施肥中は肥料供給を確保するため優先度を上げる
                    # （2.7: HARVEST/FEED より下・水やり/植付より上。非STR時は従来4.0）
                    fpri = 2.7 if str_mode else 4.0
                    todos.append((fpri, x, y, ["COLLECT_FERTILIZER"], None))

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

    # ---- メロン: 空き地に波状植付。水やりは本業より低優先度、収穫は高優先度 ----
    # (gen0007 準拠) MELON_TILES は NW 空き地で ANIMAL/WHEAT タイルと排他 → 中核を奪わない。
    free_melon_tiles = 0
    str_fert_today = 0     # (gen0019) 今日 FERTILIZE 対象の STR タイル数
    str_fert_reserve = 0   # (gen0019) 売らずに残す肥料量（2×若STR枚数）
    for x, y in MELON_TILES:
        t = tile_at(x, y)
        if t == "LOCKED":
            continue  # 未購入の区画（本世代は土地購入しないので通常発火しない）
        if t is None:
            free_melon_tiles += 1
            if hour <= LAST_PLANT_HOUR:
                if plant_str_window:
                    todos.append((4.6, x, y, ["PLANT", "STRAWBERRY"], "SSEED"))
                elif not str_hold and MELON_START_DAY <= day <= MELON_PLANT_LAST:
                    todos.append((4.6, x, y, ["PLANT", "MELON"], "MSEED"))
        elif isinstance(t, dict) and t.get("kind") == "PLANT":
            age = day - t.get("planted_day", day)
            if t.get("crop") == "STRAWBERRY":
                # ongoing: 産出が乗り次第即回収（4収穫消化後は decay で目減りするため）
                if t.get("yield_units", 0) > 0:
                    todos.append((1.9, x, y, ["HARVEST"], None))
                # (gen0019) 肥料2倍化: eve age(9/11/13/15) かつ未カバーなら施肥。
                # <day ガードで実発火は age9・13（各3日有効で 9,11 / 13,15 を覆う）。
                if age <= 13:
                    str_fert_reserve += 2   # まだ最大2回施肥が要りうる若STR
                if (STR_FERT_AGE_MIN <= age <= STR_FERT_AGE_MAX
                        and age in STR_FERT_AGES
                        and t.get("fertilized_until_day", -1) < day):
                    str_fert_today += 1
                    # pri 1.7: HARVEST(1.9) より上・FEED(1.2) より下。水やりは別途継続。
                    todos.append((1.7, x, y, ["FERTILIZE"], "FERT"))
            elif age >= MELON_FIRST_YIELD and t.get("yield_units", 0) > 0:
                todos.append((1.9, x, y, ["HARVEST"], None))  # 高付加価値を確実に回収
            if not t.get("watered_today"):
                # 枯死防止(consecutive>=1)は本業に次ぐ優先、通常水やりは最後
                pri = 1.05 if t.get("consecutive_unwatered", 0) >= 1 else 3.2
                todos.append((pri, x, y, ["WATER"], None))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((6.1, x, y, ["DIG"], None))

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

    # (gen0019) STR 施肥用の肥料をシェッドから受け取る（代表1ユニットが今日の対象数ぶん確保）
    shed_fert = shed.get("FERTILIZER", 0)
    if str_fert_today > 0 and shed_fert > 0:
        for sx, sy in SHED_TILES:
            todos.append((0.6, sx, sy, ["PICKUP", "FERTILIZER", min(shed_fert, str_fert_today, 6)], "SHEDOP"))

    # ---- ユニット割当 ----
    fx, fy = me.get("farmer", [4, 4])
    hand_pos = list(me.get("hands") or [])
    units = [(fx, fy)] + [(hx, hy) for hx, hy in hand_pos]
    claimed = set()
    planned_seed_use = 0
    planned_melon_use = 0
    planned_str_use = 0
    planned_pickup = {"WHEAT": 0, "FERTILIZER": 0}
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
            if need == "SSEED" and planned_str_use >= seeds.get("STRAWBERRY", 0):
                continue
            if need in ANIMALS and inv.get(need, 0) <= 0:
                continue
            if need == "FERT" and inv.get("FERTILIZER", 0) <= 0:
                continue  # (gen0019) 肥料を持っているユニットのみ FERTILIZE 可
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
                if op[0] == "PICKUP" and op[1] == "FERTILIZER":
                    # (gen0019) 代表1ユニットが今日の対象数ぶんを一括確保すれば足りる
                    if inv.get("FERTILIZER", 0) >= 1 or planned_pickup["FERTILIZER"] >= 1:
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
        if need == "SSEED":
            planned_str_use += 1
        if need == "SHEDOP" and op[0] == "PICKUP" and op[1] == "WHEAT":
            planned_pickup["WHEAT"] += 1
        if need == "SHEDOP" and op[0] == "PICKUP" and op[1] == "FERTILIZER":
            planned_pickup["FERTILIZER"] += 1
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
            # (fix4/gen0008) town_absorb は「1日分」の吸収量。毎ターン(毎時)売ると
            # 最大24倍速のダンプになりグラットを自ら悪化させるため、hour==0 の
            # 1日1回だけトリクルする。minv ベースの budget は市場在庫上限で
            # 自己制動するので毎ターンのままでよい。
            trickle = 0
            if hour == 0 and prices.get(item, 0) > 1:
                trickle = town_absorb.get(item, 1)
            budget = max(trickle, I0 + GLUT_SLACK - minv.get(item, I0))
            if budget > 0:
                market.append(["SELL", item, min(n, budget)])
    n_fert = shed.get("FERTILIZER", 0)
    # (gen0019) STR 生育中は 2×若STR枚数を残して施肥枯渇を防ぐ。DUMP/overflow は例外。
    reserve = str_fert_reserve if (str_mode and day < DUMP_DAY
                                   and shed_pressure < SHED_DUMP) else 0
    sellable_fert = n_fert - reserve
    if sellable_fert > 0 and (prices.get("FERTILIZER", 0) >= FERT_FLOOR
                              or day >= DUMP_DAY or shed_pressure >= SHED_DUMP):
        market.append(["SELL", "FERTILIZER", sellable_fert])

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

    # メロン/STR 種の補充(空き地ぶん、運転資金 MELON_CASH_BUFFER を残して)
    # (gen0017) STR 発動中は STR 種、保留中(d10-11 未発動)はどちらも買わない
    if plant_str_window and free_melon_tiles > seeds.get("STRAWBERRY", 0):
        want = min(free_melon_tiles - seeds.get("STRAWBERRY", 0), 4)
        affordable = int(max(0, money - MELON_CASH_BUFFER) // STR_SEED_COST)
        qty = min(want, affordable)
        if qty >= 1:
            market.append(["BUY_SEED", "STRAWBERRY", qty])
            money -= qty * STR_SEED_COST
    elif (not str_hold and MELON_START_DAY <= day <= MELON_PLANT_LAST
          and free_melon_tiles > seeds.get("MELON", 0)):
        want = min(free_melon_tiles - seeds.get("MELON", 0), 4)
        affordable = int(max(0, money - MELON_CASH_BUFFER) // MELON_SEED_COST)
        qty = min(want, affordable)
        if qty >= 1:
            market.append(["BUY_SEED", "MELON", qty])
            money -= qty * MELON_SEED_COST

    # 種の補充
    empty_wheat = sum(1 for x, y in WHEAT_TILES if tile_at(x, y) is None)
    if day <= LAST_PLANT_DAY and empty_wheat > seeds.get("WHEAT", 0) and money >= 60:
        market.append(["BUY_SEED", "WHEAT", min(empty_wheat - seeds.get("WHEAT", 0), 4)])
        money -= 40

    # 雇用(最終日も回収+DROP要員として安価なので雇う)
    # 資金化後は SCALE_HANDS まで増員し、中核動物の CARE/収穫/給餌/肥料被覆を上げる。
    # scaling が解けたら TARGET_HANDS に戻す(新規雇用停止。既存の hand は解雇しない)。
    target_hands = SCALE_HANDS if scaling else TARGET_HANDS
    hires_today = me.get("hires_today", 0)
    if len(hand_pos) < target_hands and hires_today < target_hands and money > 60:
        market.append(["HIRE"])

    return {"farmer": actions[0], "hands": actions[1:], "market": market[:10]}
