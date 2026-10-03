"""gen0023 — 3枚目土地(SW)解禁で3クアドラント化（親: gen0022）。

親 gen0022（ゾーン固定労働）が v0.5 初の正当昇格・新王者になり、**LB も 6 日間の
559 天井を破って 595 に上昇**（rank 4986→4743、ローカル pool.rating 905→1067 の改善が
LB 上昇を予測＝v0.5 の核心仮説の実証）。次段は「順序厳守: ゾーン化の実証 → 規模」。

gen0022 は CROP_PLANS に SW(y>=5,x<5)の作物タイル（イチゴ15・メロン2波4・小麦5）を
既に持つが、land_target が 2(NW+NE)に張られているため SW は locked のまま休眠していた。
gen0023 は SW を d11 に解禁し、これらのタイルを起動する。SW は作物区画（パスチャは
NW+NE で満杯・動物は 12 頭のまま）＝上位メタ「新土地にイチゴ」に一致。動物数不変
なので feed 現金要件も不変 → RESERVE=400 据置き。

変更（gen0022 からの差分のみ。市場・購買・売却・ゾーン割当機構は不変）:
- land_target: d11 に 3枚目(SW $2,000=LAND_PRICES[1])解禁。d10 メロン IPO の翌日に
  買うことで proceeds を運転資金として一晩バンクしてから拡張（gen0020 の d10 同ターン
  全額再投資=$20 starvation を回避）。
- hands_target: SW の追加作物労働に d11-28 を 12→13（fib 13人目 +$233/日）。峰は 14 据置き。
- codex 指摘の割当詰め2件:
  (1) FEED/CARE の最寄りユニット dmin を、zone_only パスでは「そのタイルのゾーン所有
      hand（+h12/h18 の救済者）」に限定。他ゾーン所有の近接 hand が dmin を下げて
      本来の担当 hand を距離ゲートで弾く穴を塞ぐ（SW でゾーンが広がると悪化する穴）。
  (2) 小麦一括 PICKUP(ZWHEAT)の在庫予約を「今ターン実際にシェッド上で PICKUP を
      実行する hand」に限定。シェッドへ移動中の hand が shed_wheat_free を予約して
      しまい、既にシェッド上の hand が実在庫を積めない穴を塞ぐ。

--- 以下 gen0022 由来のドキュメント ---
労働割当をゾーン固定に差し替え（親: gen0021）。

労働監査(knowledge/analysis/2026-09-05_gen0021-labor-audit.md): gen0021 は 12hands の
hand-hour の 76% が移動に消え、CARE がほぼ 0（uncared 10-12頭/日）、FEED も隔日で
9-12頭 unfed。原因は (1) 毎時グローバル最近傍再割当の通勤・振動、(2) CARE 優先度 3.5
のデッドレター、(3) 小麦携行2個制限のシェッド往復。是正:
- ゾーン固定割当: 動物タイル(重み4)+作物タイル(重み1)をクアドラント順に整列し、
  hands に負荷均等の連続ブロックで分配。hand は自ゾーンの仕事を優先し、無ければ
  グローバル todo に降りる。farmer は従来通り全体遊撃（シェッド操作・PLACE 等）。
- 小麦一括物流: 自ゾーンに未給餌がいる hand はシェッドで動物数+1 まで一括 PICKUP
 （旧「2個持ってたらスキップ」を撤廃）。
- CARE を FEED 直後の 1.3 に（羊毛 yield ボーナスの毎日バンク）。
市場・購買・売却ロジック(BUY_LAND/BUY_ANIMAL/HIRE/SELL)は gen0021 のまま維持。
骨格(メロンIPO d10・NE d6・小麦自給・RESERVE=400)も gen0021 から継承。

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
    "COW": {"cost": 400, "product": "MILK", "last_buy": 18, "max_held": 6},
    "SHEEP": {"cost": 500, "product": "WOOL", "last_buy": 10, "max_held": 6},
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
        return 13  # gen0023: SW 3枚目の追加作物労働に 12→13（fib 13人目 +$233/日）
    return 10


def land_target(day):
    """unlocked_quadrants の目標数。NE=d6, SW=d11。gen0023: gen0022 で労働(ゾーン化)が
    実証され RESERVE=400 で escape も止まったので、EXP0020 で棄却した SW(3枚目)を再解禁。
    d11(メロン IPO の翌日)に買い、proceeds を一晩バンクしてから拡張する。SE は買わない。"""
    if day >= 11:
        return 3
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
    animal_tiles = []  # (x, y, fed_today) — ゾーン割当の重み4アイテム
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
                animal_tiles.append((x, y, bool(t.get("fed_today"))))
                if day <= LAST_FEED_DAY:
                    if not t.get("fed_today"):
                        unfed_animals += 1
                        # gen0022: 1.2→0.9。枯死防止WATER(1.0)より上に置かないと
                        # 植付波の日に給餌が丸一日潰れる（seed42 監査で確認）
                        pri = 0.0 if t.get("consecutive_unfed", 0) >= 1 else 0.9
                        todos.append((pri, x, y, ["FEED"], "WHEAT"))
                    if not t.get("cared_today"):
                        # gen0022: 3.5(デッドレター)→0.95。FEED 直後・WATER/HARVEST より上
                        todos.append((0.95, x, y, ["CARE"], None))
                yu = t.get("yield_units", 0)
                if yu > 0:
                    # gen0022: 収穫タイミングで供給を絞る（労働側の出荷制御）。
                    # 毎日フル給餌+CAREの全力生産は町の吸収を超え、トリクル売り
                    # ($33/乳) に沈む。動物上で max_held=6 までバンクし、価格が
                    # SELL_FLOORS 以上に回復した時だけ収穫 → 既存 SELL が高値で
                    # 一括換金する。cap 目前(5+)は生産ロス回避で無条件収穫。
                    spec = ANIMALS.get(a)
                    if spec is None:
                        todos.append((2.0, x, y, ["HARVEST"], None))
                    else:
                        pp = prices.get(spec["product"], 0)
                        if (day >= DUMP_DAY or yu >= spec["max_held"] - 1
                                or pp >= SELL_FLOORS.get(spec["product"], 0)):
                            todos.append((2.0, x, y, ["HARVEST"], None))
                if t.get("fertilizer_available"):
                    todos.append((4.0, x, y, ["COLLECT_FERTILIZER"], None))

    carried_animals = {a: sum(inv.get(a, 0) for inv in invs) for a in ANIMALS}
    owned = {a: placed.get(a, 0) + carried_animals[a] + shed.get(a, 0)
             for a in ANIMALS}
    owned_total = sum(owned.values())

    # ---- パスチャ建設（1日先読み: 明日の牛購入分まで先に建てる）----
    # gen0022: 建設/除草タイルはゾーン割当対象(pasture_work_tiles)に入れ、担当
    # hand が朝のうちに建てる。建設が夕方までずれると当日の PLACE→給餌が全滅する。
    free_slots = []
    pasture_work_tiles = []
    for x, y in PASTURE_TILES:
        t = tile_at(x, y)
        if t is None:
            free_slots.append((x, y))
        elif isinstance(t, dict) and t.get("kind") == "WEED":
            todos.append((2.6, x, y, ["DIG"], None))
            pasture_work_tiles.append((x, y))
    want_built = min(len(PASTURE_TILES),
                     max(owned_total, 4 + cow_target(min(day + 1, 29))))
    shortage = want_built - built_pastures
    for x, y in free_slots[:max(0, shortage)]:
        todos.append((2.6, x, y, ["BUILD_PASTURE"], None))
        pasture_work_tiles.append((x, y))

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
    # gen0022: 夕方の新規設置はしない(PICKUP は h14 まで、PLACE は h18 まで)。
    # 遅い設置はその日の給餌・世話が物理的に間に合わず EOD unfed/uncared になる
    # だけ。シェッド泊で翌朝設置(daily reset で携行動物もシェッドに戻る)。
    for a in ANIMALS:
        if hour >= 18:
            break
        in_shed = shed.get(a, 0)
        for x, y in empty_pastures[: in_shed + carried_animals[a]]:
            todos.append((2.4, x, y, ["PLACE", a], a))
        if hour >= 14:
            continue
        if in_shed > 0 and empty_pastures:
            # gen0022: 空きパスチャ数まで一括で持ち出す（1頭ずつの往復だと
            # 4頭の設置に半日かかり、当日の給餌・世話が間に合わない）
            todos.append((2.5, 4, 4,
                          ["PICKUP", a, min(in_shed, len(empty_pastures))],
                          "SHEDOP"))

    # ---- 給餌用小麦 ----（gen0022: グローバル todo を廃止。各 hand が自ゾーンの
    #      動物数+1 まで一括 PICKUP する候補をユニット割当ループ内で生成する）
    shed_wheat = shed.get("WHEAT", 0)

    # ---- 手持ちの現金化 DROP（d10 メロンIPO を当日資金にする要）----
    for ui, inv in enumerate(invs):
        if day >= FINAL_DAY:
            if sum(inv.values()) > 0:
                todos.append((2.1, -1, -1, ["DROP"], "UNIT%d" % ui))
        else:
            val = sum(BASE_VALUE.get(k, 0) * v for k, v in inv.items())
            if val >= DROP_VALUE:
                todos.append((2.05, -1, -1, ["DROP"], "UNIT%d" % ui))

    # ---- ゾーン構築（gen0022）: 動物(重み4)+作物(重み1)タイルをクアドラント順に
    #      整列し、hands に負荷均等の連続ブロックで分配。入力（動物配置・植付計画・
    #      hands 数）が変わらない限り毎時同じ分配になる = 割当の持続性 ----
    hand_pos = list(me.get("hands") or [])
    n_hands = len(hand_pos)
    # hands は毎日ゼロから再雇用される(エンジンの daily reset)。朝の 3人/ターンの
    # 増員中にゾーン境界が動かないよう、区画数はその日の雇用目標で固定する。
    n_zones = max(n_hands, hands_target(day), 1)
    crop_work_tiles = []
    seen_ct = set()
    for crop, plan in CROP_PLANS.items():
        for x, y, from_day in plan["tiles"]:
            if day < from_day or (x, y) in seen_ct:
                continue
            t = tile_at(x, y)
            if t is None or (isinstance(t, dict) and t.get("kind") in ("PLANT", "WEED")):
                seen_ct.add((x, y))
                crop_work_tiles.append((x, y))
    zone_of = {}          # (x, y) -> zone index (0-based; zone i = hand i の担当)
    zone_animals = [0] * n_zones
    zone_unfed = [0] * n_zones
    items = ([(x, y, 4) for x, y, _fed in animal_tiles]
             + [(x, y, 1) for x, y in crop_work_tiles]
             + [(x, y, 1) for x, y in pasture_work_tiles])
    items.sort(key=lambda it: ((0 if it[1] < 5 else 2) + (0 if it[0] < 5 else 1),
                               it[1], it[0]))
    total_w = sum(w for _, _, w in items)
    acc = 0
    hi = 0
    for x, y, w in items:
        zone_of[(x, y)] = hi
        acc += w
        while hi < n_zones - 1 and acc * n_zones >= total_w * (hi + 1):
            hi += 1
    for x, y, fed in animal_tiles:
        h = zone_of.get((x, y))
        if h is not None:
            zone_animals[h] += 1
            if not fed:
                zone_unfed[h] += 1

    # ---- ユニット割当: hand は自ゾーン優先 → グローバル fallback。farmer は
    #      常にグローバル（シェッド操作・PLACE などの遊撃）----
    fx, fy = me.get("farmer", [4, 4])
    units = [(fx, fy)] + [(hx, hy) for hx, hy in hand_pos]
    unit_wheat = [(invs[i] if i < len(invs) else {}).get("WHEAT", 0)
                  for i in range(len(units))]
    claimed = set()
    planned_seed = {}
    shed_wheat_free = shed_wheat  # 一括 PICKUP の計画残（過剰予約防止）
    actions = []
    for ui, (ux, uy) in enumerate(units):
        inv = invs[ui] if ui < len(invs) else {}
        my_wheat = inv.get("WHEAT", 0)
        zid = ui - 1  # hands は 0-based ゾーン番号、farmer(-1) はゾーンなし

        def eval_todos(zone_only, _ux=ux, _uy=uy, _ui=ui, _inv=inv,
                       _my_wheat=my_wheat, _zid=zid):
            best = None
            best_key = None
            for pri, x, y, op, need in todos:
                if (pri, x, y, tuple(op)) in claimed:
                    continue
                if need and need.startswith("UNIT"):
                    if need != "UNIT%d" % _ui:
                        continue
                    x, y = min(SHED_TILES,
                               key=lambda p: abs(_ux - p[0]) + abs(_uy - p[1]))
                elif need == "SHEDOP":
                    if zone_only:
                        continue  # シェッド遊撃は farmer / 暇な hand のグローバル枠
                    if op[0] == "PICKUP" and op[1] in ANIMALS and _inv.get(op[1], 0) > 0:
                        continue
                    x, y = min(SHED_TILES,
                               key=lambda p: abs(_ux - p[0]) + abs(_uy - p[1]))
                elif zone_only and zone_of.get((x, y)) != _zid:
                    # 午後の溢れ救済: 自ゾーン外でも FEED(小麦持ち・h12+)と
                    # CARE(h18+)は拾う。担当 hand の小麦切れ・夕方設置の動物が
                    # 放置される穴を塞ぐ（seed42 d18 の unfed で確認）。
                    if op[0] == "FEED" and hour >= 12 and _my_wheat > 0:
                        pass
                    elif op[0] == "CARE" and hour >= 18:
                        pass
                    else:
                        continue
                if need == "WHEAT" and _my_wheat <= 0:
                    continue
                # FEED/CARE は最寄り担当制: 遠いユニットが claim して近い
                # ユニットが遊ぶ「unit 順 claim の逆転」を距離で断つ
                # (seed42 d28: 10タイル先の hand が claim し隣の hand が PASS)。
                # codex fix1: zone_only パスでは dmin 候補を「このタイルのゾーン所有
                # hand（+ h12/h18 の救済者）」に限定。他ゾーン所有の近接 hand が dmin を
                # 下げ、本来の担当 hand を距離ゲートで弾く穴を塞ぐ（SW でゾーンが広がる
                # ほど悪化する）。グローバル fallback パス(zone_only=False)は従来通り全体最寄り。
                if op[0] == "FEED":
                    dmin = min((abs(px - x) + abs(py - y)
                                for i, ((px, py), w) in enumerate(zip(units, unit_wheat))
                                if w > 0 and (not zone_only
                                              or zone_of.get((x, y)) == i - 1
                                              or hour >= 12)),
                               default=None)
                    if dmin is not None and abs(_ux - x) + abs(_uy - y) > dmin:
                        continue
                elif op[0] == "CARE":
                    cand = [abs(px - x) + abs(py - y)
                            for i, (px, py) in enumerate(units)
                            if (not zone_only or zone_of.get((x, y)) == i - 1
                                or hour >= 18)]
                    dmin = min(cand) if cand else None
                    if dmin is not None and abs(_ux - x) + abs(_uy - y) > dmin:
                        continue
                if need and need.startswith("SEED:"):
                    crop = need[5:]
                    if planned_seed.get(crop, 0) >= seeds.get(crop, 0):
                        continue  # 種数超過の PLANT は全員無効になる事故を防ぐ
                if need in ANIMALS and _inv.get(need, 0) <= 0:
                    continue
                # farmer の役割バイアス: シェッド操作(動物 PICKUP)と PLACE を
                # 朝一(緊急FEED/ZWHEATの次)で片付ける。2.4-2.5 のままだと全
                # hands 多忙時に h17-23 の設置になり、その日の給餌・世話が
                # 物理的に間に合わない(seed42 監査)。設置が朝なら、ゾーン担当
                # hand の携行余剰(+1)がその日のうちに新入りを養う。ランク付け
                # のみ変更し、claimed の同定は元の pri のまま。
                eff = pri
                if _ui == 0 and (need == "SHEDOP" or op[0] == "PLACE"):
                    eff = min(pri, 0.85)
                d = abs(_ux - x) + abs(_uy - y)
                key = (eff, d)
                if best_key is None or key < best_key:
                    best_key = key
                    best = (pri, x, y, op, need)
            return best, best_key

        best, best_key = (None, None)
        if 0 <= zid < n_zones:
            best, best_key = eval_todos(True)
            need_wheat = zone_unfed[zid]
        elif n_hands == 0 and hour >= 2:
            # 防御のみ: 雇用が本当に不能な時だけ farmer が給餌役になる。
            # (hour<2 は daily reset 直後の一瞬で、ここで shed 小麦を抱え込むと
            #  直後に湧く hands が給餌不能になる — seed42 監査で確認した事故)
            need_wheat = unfed_animals
        else:
            need_wheat = 0
        # 小麦一括 PICKUP 候補（朝の最初のシェッド訪問で自ゾーン分を積む）。
        # pri 0.8 = 通常 FEED(0.9) より先（小麦なしでは FEED を取れないため）。
        if (need_wheat > my_wheat and shed_wheat_free > 0
                and day <= LAST_FEED_DAY):
            cap = (zone_animals[zid] if 0 <= zid < n_zones else need_wheat) + 1
            want = min(cap - my_wheat, shed_wheat_free)
            if want > 0:
                sx, sy = min(SHED_TILES,
                             key=lambda p: abs(ux - p[0]) + abs(uy - p[1]))
                key = (0.8, abs(ux - sx) + abs(uy - sy))
                if best_key is None or key < best_key:
                    best_key = key
                    best = (0.8, sx, sy, ["PICKUP", "WHEAT", want], "ZWHEAT")
        if best is None:
            best, best_key = eval_todos(False)  # ゾーンに仕事がない → 全体を拾う
        if best is None:
            actions.append(["PASS"])
            continue
        pri, x, y, op, need = best
        if need == "ZWHEAT":
            # codex fix2: 今ターン実際にシェッド上で PICKUP を実行する hand だけが
            # 在庫を予約する。シェッドへ移動中の hand が予約すると、既にシェッド上に
            # いる後続 hand が実在庫を積めなくなる（歩行中の予約は次ターンに持ち越さ
            # れ幽霊予約になる）。claimed には入れないので複数 hand の同時積みは可。
            if (ux, uy) == (x, y):
                shed_wheat_free -= op[2]
        else:
            claimed.add((pri, x, y, tuple(op)))
            if need and need.startswith("SEED:"):
                planned_seed[need[5:]] = planned_seed.get(need[5:], 0) + 1
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
