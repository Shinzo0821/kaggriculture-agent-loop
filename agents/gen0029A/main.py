"""gen0029A — SW のイチゴ跡地を牧草地にして動物を 12 → 2 頭に増やす（親: gen0027）。

**動機**（EXP0028 の学び）: gen0026 は PASS（明示的な待機）を 1,680 ユニット時間も
出していて、越境を解禁して回収しようとしたが**資金は動かなかった**（24 シードで
マージン +$633-846、CI は 0 をまたぐ）。暇な hand が拾える仕事は歩く価値が無かった。
→ **制約は労働の量ではなく「やるべき仕事の量」**。仕事を増やす側に回す。

**なぜ動物か**:
- 動物は毎日 FEED と CARE を要求し、毎日産出する。**確実に労働時間を金に変える**。
  作物（植付 → 4-12 日後に収穫）と違って、増やした分がその日から効く。
- 相手（kaito_v48 $99.5k）は COW を 72 回・SHEEP を 32 回収穫している。こちらは 46 / 28。
- 上位は 10-12 hands で 12-17 頭を回している（`knowledge/analysis/2026-09-05_sparring-audit.md`）。

**なぜイチゴ跡地か**: NW+NE には空きタイルが (4,3) の 1 枚しか無い。一方 gen0027 の監査で
**SW を開けた後 d10-24 に空きタイルが 24-26 枚・遊休種が 25-27 個**出ている
（`knowledge/experiments/EXP0027_sw-unlock.md`）。**使えていない作物タイルを牧草地に
振り替えるコストは、実測上ほぼゼロ**。振り替えるのはシェッドに近い 2 枚
（(4, 6), (3, 6)）で、動物の日次 FEED/CARE はシェッド距離が効くため。

**変更 3 点**（親 gen0027 から）:
1. `PASTURE_TILES` に SW の 2 枚を足す（16 枚 → 上限 14 頭）。LOCKED タイルは
   `tile_at` が None を返さないので、SW を買う d11 まで自動的に建たない。
2. 同じタイルを `CROP_PLANS["STRAWBERRY"]` から外す。
3. `MAX_ANIMALS` 14 ／ `cow_target` は d12 以降 10（SW 購入 d11 の翌日）。

--- 以下は gen0027 から継承 ---

gen0027 — SW を解禁して 3 クアドラントに戻す（親: gen0026）。

**gen0023 の分離実験**（計画 §6）。gen0023 は「SW 解禁 ＋ hands 13 人目」を同時に入れて
検出不能（全体 +$870 [CI −1135, +2874]、**強帯だけ −$2,347**）だった。原因の仮説は
「その労働効率のままタイルだけ増やした」こと。gen0026 で労働効率を直した
（3 歩以上 25.9% → 15.3%、連続行動タイル間距離 1.41 → 1.01 で強帯を下回った）ので、
**土地だけを足して**再挑戦する。

- **hands は 12 のまま**（gen0023 の 13 人目を入れない。hands ±1 は IDEA_POLICY 禁止 2 番）。
- 変えるのは `land_target` に d11 の SW を足す 1 点だけ。作物の計画表（CROP_PLANS）は
  gen0022 から既に SW タイル（from_day 10）を含んでいるので、土地が開けば自動で使われる。
- 合格（計画 §6）: 75 タイルで利用率 ≥80%、unfed/uncared 0、最終 WATER ≤h16。
  金は 50 シードで**強帯資金 > 0 が必須**（gen0023 は −$2,347 だった）。
  ここが変わらなければ土地ではなく動物 12→14-16 に行く。

--- 以下は gen0026 から継承 ---

gen0026 — 労働割当を空間化する（親: gen0025）。

**目的は資金ではなく「同じ 12 hands で 75 タイルを回せる労働効率」**（計画 §5）。
gen0027（SW 解禁の再挑戦）の前提世代。KPI は決定論的なものを主にする。

ミクロ監査の数字: 畑仕事の直前に 3 歩以上歩いた割合が gen0022 で 31%（強帯 11-15%）、
同じ hand の連続する畑仕事のタイル間距離が 1.54-1.59（強帯 1.20-1.26）。
gen0025 でも 25-26% / 1.39-1.44 で、強帯にはまだ遠い。原因は 4 つ:

1. **ゾーンがクアドラント内 row-major の連続ブロック**。行末で折り返すと同じゾーンの中で
   5 タイル離れる。→ **2 列ずつの帯を上下に蛇行**する順に変え、ゾーンが「2 列 × 数行」の
   まとまりになるようにした。
2. **越境 claim**: ゾーンが片付いた hand が global fallback で他ゾーンの todo を先に claim し
   （unit 順で fallback が先に走る）、所有者が弾かれて別の todo へ歩く。
   → global fallback は「所有者のいないタイル」か「所有者が今日もう来られない
   （残り時間 < 距離 + 1）」だけを拾う。
3. **最寄り規則が全ユニット対象**: 通りすがりの hand が所有者を弾く（gen0023 の codex fix1 と
   同じ穴。王者には未適用だった）。→ FEED/CARE の最寄り判定を「その todo を実際に claim できる
   ユニット」＝所有者＋救済時間帯の hand＋farmer に限定した。
4. **優先度が連続値なので一筆書きにならない**: 2.90 と 3.05 の間を行ったり来たりする。
   → 優先度を**層**に丸め、層の中では距離だけで選ぶ（層の中で最近傍巡回になる）。

5. **出荷制御が旧スループット前提だった（1-4 を入れた結果として必要になった修正）**:
   労働効率が上がって出荷量が増えた途端、「価格が床以上なら全量売り」という旧規則が
   **自分でグラットを起こす**ようになった（実測: d25 の乳価 $84→$1、イチゴ $181→$1。
   相手の資金も $115k→$69k に落ちる＝市場破壊で相対的に勝っているだけの状態）。
   エンジンの価格は市場在庫が I0(=10000) を超えると下がり、在庫は町の消費でしか減らない
   （kaggriculture.py 192-206 / 735-747）。MILK/WOOL/STRAWBERRY は T が 105-122 と小さく、
   100 個ちょっと売ると base の 1.6-3.2 倍ぶん落ちて床($1)に張り付く。
   → **在庫予算（I0 + GLUT_SLACK − 現在庫）を常に適用する**。終盤の清算とシェッド溢れだけ例外。
   これは 1-4 が壊した前提を直す修正なので同じ世代に入れている（独立した改善ではない）。

--- 以下は gen0025 から継承 ---

gen0025 — 肥料をイチゴに撒く（親: gen0024）。

ミクロ監査(knowledge/analysis/2026-09-05_micro-audit-gen0022.md): 動物 12 頭から毎日 12 個出る
肥料を全部売っていた（FERTILIZE 0 回）。強帯はイチゴに撒いて **1 回あたり収量を 2 倍**にしている
（kaito 1.99・rayk 2.01 vs こちら 1.00）。

エンジン(kaggriculture.py 787-800): STRAWBERRY は ongoing で first_yield_day=10 / interval=2 /
max_yield=4。EOD 生産は `next_day - planted_day - 10` が 0,2,4,6 の時、つまり
**age（= day - planted_day）が 9, 11, 13, 15** の EOD。その時 `was_watered and
fertilized_until_day >= day` なら +2、そうでなければ +1。
FERTILIZE は `fertilized_until_day = day + 2`（= day, day+1, day+2 の 3 日間有効、481 行）。

→ 生産 age は全部奇数なので、**奇数 age に撒くと 2 回ぶんの生産をカバーする**
   （age 9 に撒けば 9 と 11、age 13 に撒けば 13 と 15）。1 株あたり肥料 2 個で 4 回全部が倍 = +4 個。
   偶数 age に撒くと 1 回しかカバーしないので撒かない。

- 需要: イチゴ 11 株（2 クアドラント）× 2 個 = 22 個/波。供給は動物 12 頭で 12 個/日。足りる。
- 物流: 「肥料を持つ hand だけが FERTILIZE を取れる」（FEED の小麦と同じ need）＋
  自ゾーンに撒く先がある hand はシェッドから一括 PICKUP（ZWHEAT と同じ形）。
- 売却: 今日〜2 日以内に撒く予定の個数だけシェッドに残し、余りは従来通り即売り
  （肥料は d0 が最高値で単調減衰するので寝かせる価値はない）。
- メロンへの拡張（age 6-12 の水やりボーナスが +1→+2 になる）は IPO 日程が変わるので別世代。

--- 以下は gen0024 から継承 ---

gen0024 — 計画を最後まで実行する（親: gen0022）。

ミクロ監査(knowledge/analysis/2026-09-05_micro-audit-gen0022.md): gen0022 は unfed 0・
uncared 0・no-op 0 と「きれい」に動いているのに強帯に資金で倍近い差をつけられている。
差はタイル日（利用率 66% vs 強帯 83-92%）と 1 収穫あたりの収量（小麦 2.88/4・
メロン 4.91/6・イチゴ 1.00/2）にあった。gen0024 は**書いてある計画を書いてある通りに
実行する**ための 4 点だけを直す。労働割当（ゾーン）には触らない（gen0026 の担当）。

- 3-A 収穫前に水をやる: 一時作物はボーナス窓の水やり 1 回につき +1 個。gen0022 は
  ripe になった瞬間に HARVEST を出し ripe タイルの WATER を抑止していた（収穫時
  watered_today=False が 45/45）。窓の中なら WATER を先に出す。
  **これは単調に得ではない**: 収穫＝換金が後ろにずれるので、特定の日の現金に依存する
  骨格（d10 メロン IPO）と競合する。また窓の中の WATER は PLANT より前に出るので、
  植付窓の最終日には植付機会を失うことがある。どちらもトレードオフとして受け入れている。
- 3-B PLANT を日課の WATER の前に: plant_pri は全 todo の最下位（3.30-3.40）で、WATER が
  h21-23 まで続くため PLANT は h14-20 に 1-3 回しか回らず LAST_PLANT_HOUR で締め切られて
  いた。**動物の物流（PLACE 2.4 / 動物 PICKUP 2.5 / パスチャ建設・除草 2.6）の直後、
  WATER（2.9-3.05）の直前**に置く。数値は順序を表すだけ。
  計画の «1.5 帯» はここでは採らない: 1.5 だと PLANT がパスチャ建設と動物設置まで
  追い越し、d7 の動物が 10→6 頭、d10 メロン IPO 時の現金が $5,134→$542 に落ちて
  骨格（d6 土地・d10 土地+増員+第2波）が崩れた（3 シードで再現）。
- 3-C 空きタイルのフォールバック作付け: 計画窓を逃した／どの計画にも無いタイル（(4,3)
  (4,4)(5,4)(6,1) 等）に小麦を植える。種 $10・4 日回転で飼料にも売りにも使える。
- 3-D 死に種を買わない: 種は「今この時刻から窓が閉じるまでに物理的に植えられる数」まで
  しか買わない（1 unit は 1 時間 1 回しか PLANT できない）。イチゴ $100・メロン $80 の
  死に種が毎試合 $440 出ていた（損失防止であって収益ではない）。

--- 以下は gen0022 から継承 ---

gen0022 — 労働割当をゾーン固定に差し替え（親: gen0021）。

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
MAX_ANIMALS = 14  # gen0029A: 牛10 + 羊4（SW のイチゴ跡地に牧草地を 2 枚足す）

MILK_SHOPS = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
WOOL_SHOPS = ("YARN_STORE",)
STRAW_SHOPS = ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")

# 12 パスチャ: NW 6（シェッド近傍）+ NE 6（d6 解放後）。シェッド4タイルは常に空ける。
PASTURE_TILES = [(3, 3), (2, 3), (3, 4), (2, 4), (1, 3), (1, 4),
                 (5, 3), (6, 3), (6, 4), (5, 2), (6, 2), (7, 3),
                 # gen0029A: SW（d11 解放）のイチゴ跡地。シェッドに近い順。
                 # LOCKED タイルは tile_at が None を返さないので d11 まで建たない。
                 (4, 6), (3, 6)]

# 作物タイルは (x, y, from_day)。windows は植付可能な日の帯（複数可）。
CROP_PLANS = {
    "MELON": {
        # 第1波: NW 8（d0 植え → d10 IPO）。第2波: 跡地8 + SW 4 = 12（d10-12 → d20）。
        "tiles": [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0),
                  (0, 1, 0), (1, 1, 0), (2, 1, 0),
                  (0, 5, 10), (1, 5, 10), (2, 5, 10), (3, 5, 10)],
        "windows": [(0, 2), (10, 12)],
        "plant_pri": 2.70, "water_pri": 2.90, "seed_cost": 80, "buy_cap": 12,
    },
    "STRAWBERRY": {
        # 早出し2 (d4, NW残地) + 第1波9 (d8, NE) + 第2波16 (d10, SW+NE)。
        # age10 で初産、以後隔日×4。d13 植えが d29 收穫の限界。
        "tiles": [(0, 3, 4), (0, 4, 4),
                  (5, 0, 8), (6, 0, 8), (7, 0, 8), (8, 0, 8), (9, 0, 8),
                  (5, 1, 8), (6, 1, 8), (7, 1, 8), (8, 1, 8),
                  (9, 1, 10),
                  (0, 6, 10), (1, 6, 10), (2, 6, 10),
                  (0, 7, 10), (1, 7, 10), (2, 7, 10), (3, 7, 10), (4, 7, 10),
                  (0, 8, 10), (1, 8, 10), (2, 8, 10), (3, 8, 10), (4, 8, 10)],
        "windows": [(4, 13)],
        "plant_pri": 2.75, "water_pri": 3.05, "seed_cost": 100, "buy_cap": 16,
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
        "plant_pri": 2.80, "water_pri": 3.00, "seed_cost": 10, "buy_cap": 12,
        # gen0024 3-C: 計画外タイルへのフォールバック。計画タイルより後に回す
        "fallback_pri": 2.85,
    },
}

BASE_VALUE = {"MELON": 250, "WOOL": 200, "MILK": 160, "STRAWBERRY": 120,
              "FERTILIZER": 100, "TOMATO": 60, "EGG": 50, "CARROT": 35}
DROP_VALUE = 500  # 手持ち売却価値がこれ以上なら日中に DROP（Rayk C72: 閾値500が最良）

LAST_PLANT_DAY = 25   # d25 植付 → d29 に age4 で收穫が間に合う限界
LAST_PLANT_HOUR = 20  # 終業間際の植付は当日の水やりが間に合わず確定枯れ
HOURS_PER_DAY = 24

# gen0024 3-A: 一時作物の水やりボーナス窓（エンジン kaggriculture.py 438-443）。
# yield_units は 1 で始まり、window_start = (max_yield_day+1)//2 から max_yield_day まで
# の水やり 1 回につき +1（肥料があれば +2）。窓を過ぎた水やりは収量に効かない。
BONUS_WINDOW = {"WHEAT": (2, 4), "MELON": (6, 12)}
MAX_YIELD = {"WHEAT": 6, "MELON": 6}  # エンジン CROPS の max_yield（無肥料の小麦は 4 で頭打ち）
# 収穫を後回しにするのは「水やり→収穫」の 2 手が当日中に収まる時だけ。
# 日をまたぐと max_lifespan_step の decay に入る作物があるため（小麦 age5、メロン age13）。
WATER_FIRST_LAST_HOUR = HOURS_PER_DAY - 3

# gen0024 3-C: フォールバック作付け。小麦は種 $10・age4 収穫の唯一の 4 日回転作物で、
# 飼料にも売りにも使える。計画がそのタイルを使い始めるまでに収穫が終わる見込みが
# 立つ時だけ植える（age4 収穫 + 1 日の余裕 = 5 日）。
FALLBACK_CROP = "WHEAT"
FALLBACK_CYCLE_DAYS = 5

# gen0025: イチゴの EOD 生産が起きる age（規則から導出。上の docstring を参照）。
# 全部奇数なので、この age に撒けば 1 個で 2 回ぶんの生産をカバーする。
STRAW_PROD_AGES = (9, 11, 13, 15)
# 肥料を撒いてから 2 日先まで効く（エンジン: fertilized_until_day = day + 2）
FERT_COVER_DAYS = 2
# 優先度: PLANT(2.70-2.85) の後、WATER(2.90-3.05) の前。撒く日は動かせないので
# 通常の水やりより前に置くが、動物の物流や植付より前には出さない
# （gen0024 で「上げすぎると骨格が壊れる」ことを実測している）。
FERT_PRI = 2.88
FERT_PICKUP_PRI = 2.87

# gen0026: ゾーンを切る帯の幅（列数）。2 なら「2 列 × 数行」のまとまりになる。
ZONE_BAND_WIDTH = 2
# gen0026-4: 優先度の層。層の中では距離だけで選ぶ（＝層ごとの最近傍巡回）。
# 境界は既存の優先度の意味の切れ目に置く。層の中の 0.05 の差で遠くへ歩かないための丸め。
#   0: 緊急（連続 unfed の給餌）
#   1: 動物の日課（FEED 0.9 / CARE 0.95）と枯死防止 WATER 1.0
#   2: 収量を作る行動（収穫 1.9-2.2 / 窓の中と生産日の水やり / 対を閉じる施肥 2.06）
#   3: 物流と建設（DROP 2.05-2.1 / PLACE 2.4 / 動物 PICKUP 2.5 / DIG・建設 2.6）
#   4: 植付と施肥（2.70-2.88）
#   5: 維持の水やり（2.90-3.05）
#   6: 肥料回収（4.0）
LAYER_BOUNDS = (0.5, 1.5, 2.25, 2.65, 2.89, 3.5)


def pri_layer(pri):
    for i, b in enumerate(LAYER_BOUNDS):
        if pri < b:
            return i
    return len(LAYER_BOUNDS)
# 既に水やり済みの生産日タイル: あと肥料だけで +2 が確定する（イチゴ 2 個 ≈ base $240）
FERT_PRI_PAIR = 2.06
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
    if day < 12:
        return 8
    # gen0029A: SW を買う d11 の翌日から。牧草地は d11 に建ち始める。
    return 10


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
    """unlocked_quadrants の目標数。NE=d6、SW=d11。SE は買わない（上位メタでも ROI 負）。

    gen0027: SW を d11 に戻した。EXP0020 で SW を買った時は維持力を超えてメロン
    proceeds を食い潰し動物 escape を招き、gen0023 でも強帯資金が −$2,347 だったが、
    どちらも**労働効率を直す前**の話。gen0026 で 3 歩以上 25.9%→15.3%・連続行動タイル間
    距離 1.41→1.01（強帯を下回る）まで詰めたので、同じ 12 hands で 75 タイルを回せるかを
    ここで測る。d10 のメロン IPO の翌日にすることで、購入原資を IPO の proceeds から出す。
    """
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
    planted_tiles = []  # 今 PLANT が乗っているタイル（計画外のフォールバック苗を含む）
    fert_tiles = []     # gen0025: 今日 FERTILIZE を撒くイチゴタイル
    fert_soon = 0       # gen0025: 今日〜2 日以内に撒く予定の個数（売却の予約分）
    for y in range(len(tiles)):
        row = tiles[y] or []
        for x in range(len(row)):
            t = row[x]
            if not isinstance(t, dict):
                continue
            kind = t.get("kind")
            if kind == "PLANT":
                planted_tiles.append((x, y))
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
                # gen0024 3-A: 窓の中の一時作物は WATER を HARVEST より先に出す。
                # 1 回の水やりが +1 個（小麦 3→4、メロン 5→6）。**収穫の遅れは 1 時間とは
                # 限らない**: 水やり済みの株の HARVEST(1.90) より他の株の WATER(1.89) が
                # 先に来るので、実測では同じ株の収穫が h6→h19 まで遅れた（seed42 d10）。
                # 窓を過ぎた ripe（小麦 age5+）は従来通り即収穫する（decay が始まるので待つと損）。
                # ongoing のイチゴは対象外（収穫と水やりが独立。水やりは EOD 生産の前提であって
                # 収量ではない）。
                bw = BONUS_WINDOW.get(crop)
                watered = bool(t.get("watered_today"))
                # 窓の中の水やりは **収量を作る**行動（+1 個）。窓の外の水やりは枯死を防ぐだけ。
                # 価値が違うので優先度も分ける。上限に達した株（メロン 6）は
                # 水をやっても増えないので窓の中でも対象外にする。
                # **トレードオフ**: この帯（1.89-2.19）は PLANT(2.70-2.85)より前なので、
                # 植付窓の最終日に「未成熟株への水やり」が「最後の植付」に勝つ盤面がある
                # （レビュー再現: d13 h20、隣に未水やりの小麦 age2 があるとイチゴを植えない）。
                # 「増収するから常に PLANT より先」は規則からは導けない設計判断。締切付近の
                # PLANT 保護は別途検証する（EXP0024「今後の検証」）。
                bonus_water = (bw is not None and not watered and day < FINAL_DAY
                               and yu < MAX_YIELD.get(crop, 0)
                               and bw[0] <= age <= bw[1]
                               and hour <= WATER_FIRST_LAST_HOUR)
                # gen0025: イチゴ（ongoing）は窓ではなく**生産日**に水が要る。
                # エンジン 798-800: EOD 生産の +1/+2 は `was_watered` が前提で、
                # 生産日以外の水やりは枯死防止（consecutive_unwatered < 2）にしか効かない。
                # 一時作物の bonus_water と同じ原理: 収量を作る水やりと、枯らさないための
                # 水やりは価値が違う。実測では、これを分けないと肥料を撒いた株の 35.5% が
                # 生産日に未水やりで、撒いた肥料がそのまま無駄になった。
                if crop == "STRAWBERRY" and not watered and day < FINAL_DAY:
                    bonus_water = age in STRAW_PROD_AGES
                # 収穫を 1 時間止めてよいのは「今すぐ収穫できて、待てば +1 個になる」株だけ。
                # ripe でない株には HARVEST todo がそもそも出ないので、止める対象にならない。
                water_first = bonus_water and yu > 0 and ripe
                if yu > 0 and ripe and not water_first:
                    todos.append((hpri, x, y, ["HARVEST"], None))
                if not watered and day < FINAL_DAY:
                    if crop == "STRAWBERRY" and age >= 16:
                        pass  # 生産終了(4回産み切り)、水やり無価値
                    elif t.get("consecutive_unwatered", 0) >= 1:
                        todos.append((1.0, x, y, ["WATER"], None))  # 枯死防止
                    elif bonus_water:
                        # 窓の中の水やりは収量を作るので、通常 WATER(2.90-3.05)ではなく
                        # その株の HARVEST の直前に置く。
                        # レビューで「HARVEST の後ろに置いて同じ訪問で水やり→収穫を完了させては」
                        # と指摘され、24 シードで A/B した（EXP0024）。後ろに置くと小麦 3.82→3.69・
                        # メロン 6.00→5.39 と収量が落ち、全体の後半 slope も −260 [CI −440, −80]。
                        # **最終資金の優劣は検出できなかった**（B−A の対応付き差 +$59 [CI −2,914, +3,032]）。
                        # 収量と slope を理由に前のままを暫定採用。収穫＝換金が遅れる副作用は残る。
                        todos.append((min(wpri, hpri) - 0.01, x, y, ["WATER"], None))
                    elif not (yu > 0 and ripe):
                        todos.append((wpri, x, y, ["WATER"], None))
                # gen0025: イチゴの生産日（奇数 age）に肥料を撒くと、その日と 2 日後の
                # 生産が +1→+2 になる。既に効いている間は撒かない（fertilized_until_day）。
                if crop == "STRAWBERRY" and day < FINAL_DAY:
                    covered = t.get("fertilized_until_day", -1) >= day
                    if not covered:
                        if age in STRAW_PROD_AGES:
                            # 既に水をやった株は「あと肥料だけ」で +2 が確定するので、
                            # 生産日の水やりと同じ帯まで上げて対を閉じる（実測: 水やり済みだが
                            # 肥料が届かなかった株が生産日の 18.9% あった）。
                            pri = FERT_PRI_PAIR if watered else FERT_PRI
                            todos.append((pri, x, y, ["FERTILIZE"], "FERTILIZER"))
                            fert_tiles.append((x, y))
                            fert_soon += 1
                        elif any(age < a <= age + FERT_COVER_DAYS
                                 for a in STRAW_PROD_AGES):
                            fert_soon += 1  # 近日中に撒くので売らずに残す
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
    window_end = {}   # crop -> 今開いている窓の最終日（3-D の種購入で使う）
    for crop, plan in CROP_PLANS.items():
        open_w = [(a, b) for a, b in plan["windows"] if a <= day <= b]
        w_open = day <= LAST_PLANT_DAY and bool(open_w)
        if not w_open:
            continue
        window_end[crop] = min(max(b for _a, b in open_w), LAST_PLANT_DAY)
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

    # ---- gen0024 3-C: 計画が使っていない空きタイルに小麦を植える ----
    # gen0022 は計画表がタイル→作物→窓の固定表で、窓を逃したタイルと計画に無い
    # タイルが試合終了まで空いたままだった（利用率 66%、一度も使わないタイル 4-5 枚）。
    # 「今すぐ計画が要求していない・近いうちにも要求しない」タイルだけを埋める。
    fallback_tiles = []
    if day <= LAST_PLANT_DAY:
        reserved = set(PASTURE_TILES)  # パスチャ予定地には植えない
        soon = day + FALLBACK_CYCLE_DAYS
        for _crop, plan in CROP_PLANS.items():
            for x, y, from_day in plan["tiles"]:
                for a, b in plan["windows"]:
                    # その計画がこのタイルを使い始める日
                    start = max(a, from_day)
                    if b >= day and start <= soon:
                        reserved.add((x, y))
        fb = CROP_PLANS[FALLBACK_CROP]
        for y in range(len(tiles)):
            row = tiles[y] or []
            for x in range(len(row)):
                if (x, y) in reserved:
                    continue
                if isinstance(row[x], dict) and row[x].get("kind") == "WEED":
                    # フォールバック地の雑草は計画地でもゾーン対象でもないので、
                    # ここで DIG を出さないと試合終了まで残る（そのタイルを永久に失う）
                    todos.append((2.6, x, y, ["DIG"], None))
                    fallback_tiles.append((x, y))
                    continue
                if row[x] is not None:
                    continue  # LOCKED / 作物 / 動物 / パスチャ は対象外
                fallback_tiles.append((x, y))
                plant_slots[FALLBACK_CROP] += 1
                if hour_ok:
                    todos.append((fb["fallback_pri"], x, y,
                                  ["PLANT", FALLBACK_CROP],
                                  "SEED:" + FALLBACK_CROP))
        if fallback_tiles:
            window_end.setdefault(FALLBACK_CROP, LAST_PLANT_DAY)

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
    for x, y in planted_tiles + fallback_tiles:
        if (x, y) not in seen_ct:
            seen_ct.add((x, y))
            crop_work_tiles.append((x, y))
    zone_of = {}          # (x, y) -> zone index (0-based; zone i = hand i の担当)
    zone_animals = [0] * n_zones
    zone_unfed = [0] * n_zones
    items = ([(x, y, 4) for x, y, _fed in animal_tiles]
             + [(x, y, 1) for x, y in crop_work_tiles]
             + [(x, y, 1) for x, y in pasture_work_tiles])
    # gen0026-1: ゾーンを空間で切る。旧: クアドラント内 row-major（行末で折り返すと
    # 同じゾーンの中で 5 タイル離れる）。新: クアドラント内を **2 列ずつの帯**に分け、
    # 帯の中は上下に蛇行する。連続ブロックで切るとゾーンが「2 列 × 数行」のまとまりになり、
    # ゾーン内の最遠 2 点の距離は（帯の幅 1）＋（行数 − 1）に収まる。
    def zone_order(it):
        x, y = it[0], it[1]
        q = (0 if y < 5 else 2) + (0 if x < 5 else 1)   # クアドラント（従来と同じ）
        qx0, qy0 = (0 if x < 5 else 5), (0 if y < 5 else 5)
        band = (x - qx0) // ZONE_BAND_WIDTH             # 2 列ずつの帯
        yy = (y - qy0) if band % 2 == 0 else -(y - qy0)  # 帯ごとに上下を折り返す
        return (q, band, yy, x)

    items.sort(key=zone_order)
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
    # gen0025: 自ゾーンに撒く先がある hand だけがシェッドへ肥料を取りに行く
    zone_fert = [0] * n_zones
    for x, y in fert_tiles:
        h = zone_of.get((x, y))
        if h is not None:
            zone_fert[h] += 1

    # ---- ユニット割当: hand は自ゾーン優先 → グローバル fallback。farmer は
    #      常にグローバル（シェッド操作・PLACE などの遊撃）----
    fx, fy = me.get("farmer", [4, 4])
    units = [(fx, fy)] + [(hx, hy) for hx, hy in hand_pos]
    unit_wheat = [(invs[i] if i < len(invs) else {}).get("WHEAT", 0)
                  for i in range(len(units))]
    def _owner_can_come(x, y, zid, op):
        """このタイルに所有者がいて、今日まだ来られるか（= 他人が拾ってはいけないか）。

        「来られる」は残り時間で判定する: 歩く距離 + 実行の 1 時間が今日の残り時間に
        収まるなら所有者が自分でやる。収まらないなら放置されるので拾ってよい。
        救済時間帯の FEED/CARE と、肥料を持つ hand の FERTILIZE は従来どおり例外。
        """
        owner = zone_of.get((x, y))
        if owner is None or owner == zid:
            return False
        if op[0] == "FEED" and hour >= 12:
            return False
        if op[0] in ("CARE", "FERTILIZE") and hour >= 18:
            return False
        if owner >= len(hand_pos):
            return False  # まだ雇われていない区画 = 所有者不在
        ox, oy = hand_pos[owner]
        return abs(ox - x) + abs(oy - y) + 1 <= HOURS_PER_DAY - hour

    claimed = set()
    planned_seed = {}
    shed_wheat_free = shed_wheat  # 一括 PICKUP の計画残（過剰予約防止）
    shed_fert_free = shed.get("FERTILIZER", 0)  # gen0025: 同上（肥料）
    actions = []
    for ui, (ux, uy) in enumerate(units):
        inv = invs[ui] if ui < len(invs) else {}
        my_wheat = inv.get("WHEAT", 0)
        my_fert = inv.get("FERTILIZER", 0)
        zid = ui - 1  # hands は 0-based ゾーン番号、farmer(-1) はゾーンなし

        def eval_todos(zone_only, _ux=ux, _uy=uy, _ui=ui, _inv=inv,
                       _my_wheat=my_wheat, _my_fert=my_fert, _zid=zid):
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
                elif not zone_only and _owner_can_come(x, y, _zid, op):
                    # gen0026-2: global fallback は所有者の仕事を先取りしない。
                    # 旧: ゾーンが片付いた hand が unit 順で先に走り、まだ動いていない
                    # 所有者の todo を claim して、所有者が別の todo へ歩いていた。
                    continue
                elif zone_only and zone_of.get((x, y)) != _zid:
                    # 午後の溢れ救済: 自ゾーン外でも FEED(小麦持ち・h12+)と
                    # CARE(h18+)は拾う。担当 hand の小麦切れ・夕方設置の動物が
                    # 放置される穴を塞ぐ（seed42 d18 の unfed で確認）。
                    if op[0] == "FEED" and hour >= 12 and _my_wheat > 0:
                        pass
                    elif op[0] == "CARE" and hour >= 18:
                        pass
                    elif op[0] == "FERTILIZE" and _my_fert > 0:
                        # gen0025: 肥料を持っている hand は自ゾーン外でも撒く。
                        # 肥料は動物タイルで湧くのに撒く先はイチゴで、ゾーンは
                        # クアドラント内 row-major なので（NE はイチゴ y0-1・動物 y2-4）、
                        # **肥料を持つ hand と撒く先が別ゾーンになる**のが常態。
                        # ゾーン内に閉じると 22 回撒くべきところが 8-9 回しか回らなかった（実測）。
                        # 撒く日は動かせない（age 9/11/13/15 の当日）ので時刻の条件は付けない。
                        pass
                    else:
                        continue
                if need == "WHEAT" and _my_wheat <= 0:
                    continue
                # gen0025: 肥料を持っている hand だけが FERTILIZE を取れる（FEED と同じ）
                if need == "FERTILIZER" and _my_fert <= 0:
                    continue
                # FEED/CARE は最寄り担当制: 遠いユニットが claim して近い
                # ユニットが遊ぶ「unit 順 claim の逆転」を距離で断つ
                # (seed42 d28: 10タイル先の hand が claim し隣の hand が PASS)。
                # gen0026-3: 最寄り判定を「その todo を実際に claim できるユニット」に
                # 限定する。旧は全ユニットを見ていたので、**claim する資格がない**通りすがりの
                # hand が dmin を作り、所有者まで弾いていた（gen0023 の codex fix1 と同じ穴で、
                # 王者には未適用だった）。資格 = 所有者 / 救済時間帯の hand / farmer。
                if op[0] in ("FEED", "CARE"):
                    owner = zone_of.get((x, y))
                    rescue = hour >= (12 if op[0] == "FEED" else 18)
                    ds = []
                    for i, (px, py) in enumerate(units):
                        if op[0] == "FEED" and unit_wheat[i] <= 0:
                            continue
                        zi = i - 1
                        if not (i == 0 or rescue or owner is None or zi == owner):
                            continue
                        ds.append(abs(px - x) + abs(py - y))
                    dmin = min(ds, default=None)
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
                # gen0026-4: 層に丸めてから距離。層の中では距離だけで選ぶので、
                # 0.05 の優先度差のために 5 タイル歩く（旧: key=(eff, d)）ことがなくなる。
                d = abs(_ux - x) + abs(_uy - y)
                key = (pri_layer(eff), d, eff)
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
        # gen0025: 肥料の一括 PICKUP（自ゾーンに今日撒く先がある hand だけ）。
        # 手元の肥料は COLLECT_FERTILIZER でも増えるが、イチゴのゾーンに動物が
        # いないことがある（ゾーンはクアドラント内 row-major で、NE はイチゴが y0-1・
        # 動物が y2-4）ので、シェッドから取りに行く経路が要る。
        if (0 <= zid < n_zones and zone_fert[zid] > my_fert
                and shed_fert_free > 0 and day < FINAL_DAY):
            want = min(zone_fert[zid] - my_fert, shed_fert_free)
            if want > 0:
                sx, sy = min(SHED_TILES,
                             key=lambda p: abs(ux - p[0]) + abs(uy - p[1]))
                key = (FERT_PICKUP_PRI, abs(ux - sx) + abs(uy - sy))
                if best_key is None or key < best_key:
                    best_key = key
                    best = (FERT_PICKUP_PRI, sx, sy,
                            ["PICKUP", "FERTILIZER", want], "ZFERT")
        if best is None:
            best, best_key = eval_todos(False)  # ゾーンに仕事がない → 全体を拾う
        if best is None:
            actions.append(["PASS"])
            continue
        pri, x, y, op, need = best
        if need == "ZWHEAT":
            shed_wheat_free -= op[2]  # 予約のみ（claimed に入れず複数 hand 可）
        elif need == "ZFERT":
            shed_fert_free -= op[2]   # 同上（肥料）
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
        if item == "FERTILIZER":
            # gen0025: 今日〜2 日以内に撒く予定の分は売らない。1 個で生産 2 回が
            # +1→+2（イチゴ 2 個 ≈ base $240）なので、肥料の売値 $100 より高い。
            n -= fert_soon
        if n > 0:
            market.append(["SELL", item, n])
            mest += n * prices.get(item, BASE_VALUE.get(item, 1)) * 0.7
    town_absorb = premium_absorb(shops)
    for item, floor in SELL_FLOORS.items():
        n = shed.get(item, 0)
        if n <= 0:
            continue
        p = prices.get(item, 0)
        # gen0026s: 在庫予算を**常に**適用する（旧: 価格が床以上なら全量売り）。
        # エンジンの価格は市場在庫が I0(=10000) を超えると下がり、在庫は町の消費でしか
        # 減らない。MILK/WOOL/STRAWBERRY は T が 105-122 と小さく、
        # 100 個ちょっと売っただけで base の 1.6-3.2 倍ぶん値が落ちて床($1)に張り付く。
        # 「床以上なら全量」は旧スループット前提の規則で、労働効率が上がると自分で
        # グラットを起こす（gen0026 実測: d25 の乳価 $84→$1、イチゴ $181→$1）。
        if day >= DUMP_DAY or shed_pressure >= SHED_DUMP:
            qty = n  # 終盤の清算とシェッド溢れは価格を問わず全量
        else:
            trickle = 0
            if hour == 0 and p > 1:
                trickle = town_absorb.get(item, 1)
            budget = I0 + GLUT_SLACK - minv.get(item, I0)
            qty = min(n, max(trickle, budget, 0))
        if qty > 0:
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
    # gen0024 3-D: 買う数を「今この時刻から窓が閉じるまでに物理的に植えられる数」で
    # 頭打ちにする。1 unit は 1 時間に 1 回しか PLANT できず、LAST_PLANT_HOUR を過ぎた
    # 植付は当日の水やりが間に合わず確定枯れなので植えない。gen0022 は窓の最終日の
    # 夕方でも空きタイル数だけ買い、そのまま窓が閉じて死に種になっていた
    # （イチゴ $100・メロン $80、seed42 d15 で $440）。
    n_units = len(units)
    for crop in ("MELON", "STRAWBERRY", "WHEAT"):
        plan = CROP_PLANS[crop]
        end = window_end.get(crop)
        if end is None:
            continue  # 窓が開いていない → そもそも植える先がない
        # エンジンはユニット行動 → 市場購入の順に解決するので、今買う種が使えるのは
        # 次のターンから。当日分に「今の 1 時間」を数えると窓の最終日 h20 に $100 の
        # イチゴ種を買って確実に死なせる（+1 ではなく素の差）。
        cap = max(0, LAST_PLANT_HOUR - hour) * n_units
        cap += max(0, end - day) * (LAST_PLANT_HOUR + 1) * n_units
        deficit = min(plant_slots[crop], cap) - seeds.get(crop, 0)
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
