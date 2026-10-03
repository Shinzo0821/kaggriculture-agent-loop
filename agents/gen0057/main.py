"""gen0046 — FIX0018 掃除世代（FIX0014 reconcile の残存精度。親: gen0045）。

gen0045 のコピー + FIX0018 のみ。市場予算の reconcile（FIX0014）が実約定可能性を
保証しない 3 つの穴を塞ぐ。効くのは SELL が 10 スロットで truncation される重い購入
ターンだけで、SELL が全数収まる通常ターン（no_trunc）は gen0045 とバイト同一の出力:
- (穴1) kept SELL の 0.7·price 一律過小評価で正当な BUY_LAND/BUY_ANIMAL を落とす
  → BETA 品目(WOOL/MELON)を engine の glut 価格式で 1 個ずつ足し込み実約定額を近似。
- (穴2) reconcile が RESERVE=400 の残置を再確認しない
  → 各 buy に購入後必要残高（feed=0/land・animal・seed=400/hire=20）を併記して判定。
- (穴3) nb-=1 が数量注文を丸ごと落とす（engine は 1 個ずつ約定＝部分約定が可能）
  → 末尾が数量注文なら RESERVE を残して買える数量へ縮小し、atomic だけ丸落とし。

--- 以下 funded wool expansion の説明（gen0045 から継承）---

設計書 state/plans/2026-09-07_gen0045-funded-wool.md。

仮説（§0）: YARN_STORE が 2 軒以上引かれた町（seed の約 12%）でだけ、d12-16 に
SE($4,000) を買い、羊を 4→8 に段階増頭し、SE に飼料小麦 6 枚を足す。y≤1 の町では一切
何もしない（親とバイト単位で同一挙動）。羊毛だけが供給不足市場（他品目は市場律速で CLOSED）
なので、上限価格に張り付いた y≥2 の町でだけ増産枠が浮く。非発火 seed のコストは厳密に 0 で、
対応付き評価の検出力を担保する。

不変条件: 非発火 seed（y<2 または SE 未取得）では拡張分岐（expansion_active / sheep_target の
8）は一切発火しない。SE タイルは LOCKED の間 tile_at が "LOCKED"（None でない）を返すので、
建設ループ・PLANT スケジューラ・fallback のいずれからも todo を生まない（engine README:
locked tile は文字列 "LOCKED"）。

同時に FIX0014-0016 を折り込む（gen0044 の Codex レビューの deferred。売買と WOOL を触るので自然）:
- FIX0014（major）: keep_sells で落とす SELL の架空代金で essential buy を組む不整合。実約定する
  SELL だけで購入予算を組み直し、賄えない末尾 buy を落として枠を SELL に返す（reconcile）。
- FIX0015（minor）: BETA_SELL 品目（WOOL）の収穫解除ゲートを固定 SELL_FLOORS から
  beta_sell_cap(...)>0 に合わせる。
- FIX0016（minor）: beta_sell_cap の int() を floor（int(I0+root)-market_inv+1）に。

--- 以下は gen0042 から継承 ---

gen0042 — 労働の質の open major 掃除（親: gen0036）。

修正台帳（knowledge/FIXES.md / control/fixes.json）の open major 2 件を潰す掃除世代。
どちらも「投入を増やさず、unit-hour の取りこぼしを回収する」= 原理 1「労働は量ではなく質」
と整合する。gen0036（掃除で +$2,039）と同じ系統で、機構は 2 つとも幽霊予約／相互停止で
unit-hour を丸ごと捨てる型の穴。

- FIX0004（gen0022 から継承・FIX0001 の種版）: 植付タイルへ**移動中**の hand が
  `planned_seed` を予約するため、`planned_seed >= seeds` で種切れと誤判定し、現地に立って
  今すぐ植える hand が弾かれる（幽霊予約）。種数の予約を「今ターン実際に植える hand」に限定。
- FIX0005: 所有者保護 `_owner_can_come` は farmer を弾くのに、FEED/CARE の最寄り判定（dmin）
  には farmer が残るため、farmer が近いだけで所有者の claim を潰し、farmer 自身も保護で降りて
  両者が譲り合い両方 PASS になる。dmin の候補集合を「実際に claim できる集合」に一致させる。

**FIX0003 / FIX0011 を gen0041 から移植した**（本世代の主眼ではないが、修正台帳で applied の
major/minor。gen0042 の親は gen0036 で、これらは gen0041 でしか入っていないため、移植しないと
王者系統に取り込まれた時に消える＝gen0023 の再演）。どちらも**最終行動ターンだけ**の会計修正
（FIX0003 = 最終日の DROP 分を SELL 数量に上乗せ ／ FIX0011 = 換金の手番が無い最終ターンの
COLLECT_FERTILIZER を抑制）で、Track A のイチゴ価格床ロジック（`LIVING_EXITS`）は**移植しない**
（それは Track A の固有変更で、混ぜると帰属が濁る）。終盤の 1〜2 手番にしか触れないので Track B
（FIX0004/0005）の日中の労働効果への交絡は限定的。ベースラインは gen0036。

FIX0006（窓の中の WATER が HARVEST より前）は本世代では**入れない**: (a) gen0032 の訪問完了
（d==0 の DAILY_TILE_OPS を VISIT_LAYER に持ち上げる）で「立っているタイルの ripe を先に収穫」は
既に成立しており、gen0036 の micro（inplace_share 0.410 / tile_revisit_share 0.012）で症状は
ほぼ解消している。(b) 残る visit_ok=False（最終日・植付締切）の帯で in-place HARVEST を持ち上げると
植付締切と競合する（visit_ok がその帯を除外しているのは意図的）。(c) 窓の bonus_water の
優先度配置は EXP0024 で A/B 済みの敏感な設計。混ぜると帰属が濁るので別途 careful に測る。
詳細は EXP0042 の「却下した小手先案」。

--- 以下は gen0036 から継承 ---

gen0031 — プレミアム品の自前の売却上限を 2 倍にする（親: gen0030）。

gen0030（粒度を細かくする）は**売却総量を 1 個も変えなかった**（MILK 186 個を 26 回 → 51 回、
WOOL 134 個を 18 回 → 92 回、STRAWBERRY 83 個を 13 回 → 46 回。いずれも総量同一）。
量を縛っているのは粒度ではなく `premium_absorb` の係数（tuned）だと確定したので、
**その tuned 定数を 2 倍にする削り世代**。gen0030 の粒度変更は載せたまま。

--- 以下は gen0030 から継承 ---

gen0030 — プレミアム品を 1 日かけて流す（親: gen0026）。

**動機**（EXP0029。同一試合 vs kaito_v48 s42 の売却を並べた）:

| | 自分 | kaito_v48 |
| --- | --- | --- |
| SELL 回数 | 134 | **571** |
| MILK | 258 個 / 34 回（1 回平均 **7.6**） | 335 個 / 123 回（1 回平均 **2.7**） |
| STRAWBERRY | 127 個 / 18 回（平均 7.1） | **428 個** / 103 回（平均 4.2） |
| WOOL | 120 個 / 13 回（平均 9.2） | 179 個 / 56 回（平均 3.2） |
| **プレミアム 3 品 合計** | **505 個** | **942 個** |

今日測った「入口を広げる」手は 3 つとも強帯に効かなかった——
土地 +25 タイル（EXP0027・強帯 検出不能）／待機時間の回収（EXP0028・検出不能）／
動物 +4 頭（EXP0029・**強帯 −$3,821**。牛乳の産出は +39% 増えたのに資金は −$20k）。
**出口が詰まっているところに入口を広げていた。**

**原因**: gen0026 の在庫予算は「いつ・いくつまで」を日単位でしか見ていない。
在庫が I0 を超えると `budget <= 0` になり、あとは **hour == 0 に 1 日ぶんをまとめて**
売るだけになる（`trickle` が `hour == 0` 条件つきだった）。
エンジンの価格は市場在庫の関数なので、19 個を一度に積むと自分でその場の価格を下げる。
町の消費は時間とともに効くので、**同じ量でも 1 日かけて流せば在庫が低いまま保てる**。

**変更（1 点）**: `trickle` を「hour == 0 に 1 日ぶん」から
「1 日ぶんを 24 時間に均等配分した、その時刻の取り分」に変える。
`absorb * (hour + 1) // 24 - absorb * hour // 24` は 0 か 1 を返し、
**1 日の合計はちょうど `absorb`**（吸収量そのものは増やさない）。売る総量ではなく
**粒度だけ**を変える変更なので、悪化するとしたら理由は取引回数のコストしかない。

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
MAX_ANIMALS = 12  # 牛8 + 羊4（非発火の room 上限。発火時は COW_MAX + sheep_target で置換）

# gen0045: 町抽選条件付きの羊増頭（funded wool expansion）。設計書 §4。
YARN_MIN = 2      # y>=2 でだけ拡張（§1b: y<=1 は増頭の限界収入が負〜ゼロ）
EXPAND_W0 = 12    # SE 購入トリガ窓の開始（d12）
EXPAND_W1 = 16    # 同・終了（d18 発火は SE 込みで損益ゼロなので窓を d16 で閉じる。§1c）
COW_MAX = 8       # 既存 cow_target の上限。羊と分けて room を組むために明示

MILK_SHOPS = ("PIZZA_SHOP", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP")
WOOL_SHOPS = ("YARN_STORE",)
STRAW_SHOPS = ("BRUNCH_SPOT", "ICE_CREAM_SHOP", "SMOOTHIE_SHOP", "FARMERS_MARKET")

# 12 パスチャ: NW 6（シェッド近傍）+ NE 6（d6 解放後）。シェッド4タイルは常に空ける。
# gen0045: SE 4 枚を末尾に追加（シェッド(5,5)隣接クラスタ、通勤ゼロ）。SE が LOCKED の
# 非発火 seed では tile_at="LOCKED"（None でない）なので建設ループが素通りし todo を生まない。
# free_slots の充足順を既存優先に保つため必ず末尾に置く（設計書 §7-3）。
PASTURE_TILES = [(3, 3), (2, 3), (3, 4), (2, 4), (1, 3), (1, 4),
                 (5, 3), (6, 3), (6, 4), (5, 2), (6, 2), (7, 3),
                 (6, 5), (7, 5), (5, 6), (6, 6)]

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
        # 早出し2 (d4, NW残地) + 第1波9 (d8, NE) + SW波15 (d8, gen0049 で d10→d8 前倒し)
        # + NE補完1 (9,1)=d10。age10 で初産、以後隔日×4。d13 植えが d29 收穫の限界。
        # gen0049 (Stage B): SW rows 6-8 の 15 枚だけ from_day 10→8。土地購入 d8(land_target)
        # と同時に動かし、decay を早め d28-30 低価格帯から d22-24 高値帯へ移す。枚数は不変。
        # NE (9,1,10) と MELON/WHEAT の SW タイル・早出し2 は触らない。
        "tiles": [(0, 3, 4), (0, 4, 4),
                  (5, 0, 8), (6, 0, 8), (7, 0, 8), (8, 0, 8), (9, 0, 8),
                  (5, 1, 8), (6, 1, 8), (7, 1, 8), (8, 1, 8),
                  (9, 1, 10),
                  (0, 6, 8), (1, 6, 8), (2, 6, 8), (3, 6, 8), (4, 6, 8),
                  (0, 7, 8), (1, 7, 8), (2, 7, 8), (3, 7, 8), (4, 7, 8),
                  (0, 8, 8), (1, 8, 8), (2, 8, 8), (3, 8, 8), (4, 8, 8)],
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
                  (0, 5, 19), (1, 5, 19), (2, 5, 19), (3, 5, 19),
                  # gen0045: SE 飼料小麦 6 枚（from_day 12）。パスチャ隣接で収穫→FEED 最短。
                  # 非発火 seed では SE が LOCKED なので PLANT スケジューラ・fallback とも素通り。
                  (7, 6, 12), (5, 7, 12), (6, 7, 12), (7, 7, 12), (8, 5, 12), (8, 6, 12)],
        "windows": [(0, 25)],
        "plant_pri": 2.80, "water_pri": 3.00, "seed_cost": 10, "buy_cap": 12,
        # gen0024 3-C: 計画外タイルへのフォールバック。計画タイルより後に回す
        "fallback_pri": 2.85,
    },
    "CARROT": {
        # gen0047: 終盤 fast-carrot ローテ。4 産を終えて engine が WEED 化したイチゴタイルだけを
        # d24-27 に転作する。タイル集合 = STRAWBERRY 計画から早出し2枚 (0,3)(0,4) を除いた 25 枚
        # （NE 5-9 行0-1 + (9,1) の 10 枚 + SW 0-4 行6-8 の 15 枚）。from_day は一律 24。
        # 早出し2枚を外す理由: d21 に WEED 化し fallback 小麦が既に回収済み。含めると d19-23 に
        # reserved 化して fallback を止め、非発火同一性が壊れる（設計書 §4）。
        # decay 済み判定は age/収穫回数の閾値を使わない: engine が「4 産完了 or 枯死」の時だけ
        # タイルを WEED にするので、「kind=WEED / None のタイルにしか触らない」がそのまま
        # 『decay 済みのみ』の機械保証になる。生きたイチゴ(kind=PLANT)は植付スケジューラが素通り。
        "tiles": [(5, 0, 24), (6, 0, 24), (7, 0, 24), (8, 0, 24), (9, 0, 24),
                  (5, 1, 24), (6, 1, 24), (7, 1, 24), (8, 1, 24),
                  (9, 1, 24),
                  (0, 6, 24), (1, 6, 24), (2, 6, 24), (3, 6, 24), (4, 6, 24),
                  (0, 7, 24), (1, 7, 24), (2, 7, 24), (3, 7, 24), (4, 7, 24),
                  (0, 8, 24), (1, 8, 24), (2, 8, 24), (3, 8, 24), (4, 8, 24)],
        "windows": [(24, 27)],
        "plant_pri": 2.24,   # gen0048 Stage A: carrot 転作は収量を作る行動なので層4→層2(2.24, イチゴHARVEST 2.2 の直上＝収穫がタイで勝つ)。他作物の plant_pri は不変
        "water_pri": 3.02, "seed_cost": 20, "buy_cap": 12,
        "last_plant_day": 26,   # FIX0020: d26 植えが最後の有用な carrot。d27 植えは age2 が
        # d29 に来るが d29 は WATER が FINAL_DAY ガードで発行されないため増収 0（yield=1 のまま、
        # bonus 窓の水やり無し）で、しかも d29 収穫は搬送が間に合わず死蔵する。d26 植えは d28 に
        # age2 で刈れる（下の ripe 第2節）ので d29 をシェッド搬送に空けられる。
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
BONUS_WINDOW = {"WHEAT": (2, 4), "MELON": (6, 12), "CARROT": (2, 3)}
MAX_YIELD = {"WHEAT": 6, "MELON": 6, "CARROT": 3}  # エンジン CROPS の max_yield（無肥料の小麦は 4・carrot は 3 で頭打ち）
# 収穫を後回しにするのは「水やり→収穫」の 2 手が当日中に収まる時だけ。
# 日をまたぐと max_lifespan_step の decay に入る作物があるため（小麦 age5、メロン age13）。
WATER_FIRST_LAST_HOUR = HOURS_PER_DAY - 3

# gen0024 3-C: フォールバック作付け。小麦は種 $10・age4 収穫の唯一の 4 日回転作物で、
# 飼料にも売りにも使える。計画がそのタイルを使い始めるまでに収穫が終わる見込みが
# 立つ時だけ植える（age4 収穫 + 1 日の余裕 = 5 日）。
FALLBACK_CROP = "WHEAT"
FALLBACK_CYCLE_DAYS = 5
# gen0057: ニンジン置き換えの対象になる小麦計画タイルの下限 from_day。
# 19 は CROP_PLANS["WHEAT"] が自分で「終盤ブロック12(d19: メロン跡地)」と宣言している
# 既存の区切りをそのまま使う（新しく引いた境界ではない）。これより前のタイル
# （NW 基幹 from_day 0・自給拡張 from_day 10・SE 飼料 from_day 12）は飼料の芯なので触らない。
WHEAT_LATE_FROM_DAY = 19

# gen0057: 「空いたタイルを何で埋めるか」を市場在庫で決める。
#
# 根拠（`knowledge/analysis/2026-09-19_sell-side-market-structure.md`）:
#  - 小麦は `BUY_PRODUCT` できる 2 品目の 1 つで、**相手は 1 試合で 105-487 個買っている**
#    （我々 83-119 個）。小麦は季節末も $36-50 と常に品薄側なので、我々の増産は
#    相手の飼料仕入れ値を直接下げる＝原理 3 の「増やす贈り物」。EXP0053 の
#    「自資金 ≒0 なのにマージン −$682」はこの署名。
#  - ニンジンは買い戻せない（engine: BUY_PRODUCT は WHEAT と FERTILIZER のみ）＝贈り物経路が無い。
#    そして 12/12 の試合で季節末在庫が I0 より 128-659 個少ない（町の需要が両者の供給合計を
#    上回り続ける）。価格が基準 $35 を割ったのは 12 戦中 1 戦だけ、季節末は $45-62。
#
# ただし「常時ニンジン」にはしない（IDEA_POLICY §5）。**その試合の市場在庫が許す枚数だけ**
# 置き換える。headroom は町の店抽選で決まるので試合ごとに違い、実測では
# d0-d8 は +0〜+8（＝0 枚。この時期の小麦は飼料なのでそのまま小麦）、
# d20 は +20〜+332、d28 は +142〜+624 と**季節と町で自動的に開く**。
# 閾値は勘で置かない: 1 枚が市場に出すのは無肥料 carrot の max_yield（MAX_YIELD["CARROT"]）
# ぶんなので、**headroom をその収量で割った枚数**を上限にする。売れば headroom が減るので
# 自動で止まる（自己制限）。
def carrot_fill_budget(minv, day):
    """今日この試合でニンジンに置き換えてよい『空きタイルの枚数』。

    0 なら従来どおり小麦で埋める（＝親 gen0051 と同一挙動）。
    """
    if day > CROP_PLANS["CARROT"].get("last_plant_day", LAST_PLANT_DAY):
        return 0
    headroom = I0 - minv.get("CARROT", I0)
    if headroom <= 0:
        return 0
    return int(headroom // MAX_YIELD["CARROT"])

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

# gen0032: 訪問完了（visit completion）の対象になる仕事。
# 条件は「毎日リセットされる／場所が動かない／いつやっても 1 時間」の 3 つで、
# エンジンの daily reset（kaggriculture.py 777-830）から機械的に決まる集合。
# 立っているタイルでこれらを済ませずに歩き出すと、後で必ず 2*距離 の往復が増える。
# PLANT / DIG / BUILD / 物流は入れない（盤面の形を変える＝場所も価値も動くため）。
# gen0057 では PLANT を足さない（EXP0038 の機構は**載せなかった**）。
# 理由は 2 つで、どちらも「棄却した」とは書かない —— スモーク 3 seed では方向を判断できない:
#  (1) 本世代の変更を「作物の選択」1 点に絞って効果の帰属を割らないため。
#  (2) 参考情報として、vs starter 3 seed の A/B 分離では PLANT 追加だけの版が
#      3 seed とも親を下回った（−$7〜16k）。**これは判断の根拠にならない**が
#      （単シードは ±$30k 振れる。実際この試合の資金差の大半は乳の投げ売り時刻の
#      ずれで説明が付く）、Stage B のイチゴ位相を崩す可能性があるので同時には入れない。
#      EXP0038 は gen0036 の上で +$44 だった。骨格が変われば再測が要る。
DAILY_TILE_OPS = ("FEED", "CARE", "WATER", "HARVEST", "COLLECT_FERTILIZER",
                  "FERTILIZE")
# 訪問完了で持ち上げる層。0（連続 unfed の緊急給餌）だけは他タイルでも先に行かせる
# ＝「立っているタイルの仕事は、家畜が死ぬ以外の何より先」。
VISIT_LAYER = 1
# 訪問完了は「後でやり直せる」ことが前提。**今日の締切に張り付いている仕事**が盤上に
# ある間は行わない。締切は 3 つあり、いずれも既存の定数から出る:
#   (a) 資産が今夜失われる仕事 = 連続 unfed の緊急給餌(pri 0.0) と枯死防止 WATER(pri 1.0)
#       → LOSS_PRIS。これは距離より先に見る（下の crit）。
#   (b) 植付の締切 LAST_PLANT_HOUR（当日の水やりが間に合わないと確定枯れ）
#   (c) 最終日 FINAL_DAY の清算（DROP → SELL が 1 ターンずれると全額落とす）
# (b)(c) の間は訪問完了そのものを止める（往復の節約より締切の方が高い）。
LOSS_PRIS = (0.0, 1.0)

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
LAST_ACTION_HOUR = 22  # FIX0011: 最終行動ターンは d29 h22（step 718）。以後は換金の手番が無い

SELL_FLOORS = {"MILK": 96, "WOOL": 120, "STRAWBERRY": 72}  # base比0.6。市場売却の床＋家畜収穫のバンク解除ゲート(589)
# gen0044 (H2): MELON を ALWAYS_SELL から外し、WOOL とともに β 解法パス（BETA_SELL）へ移す。
# WOOL は SELL_FLOORS に残すが市場売却ループでは skip する（589 の収穫バンクゲートでのみ使う）。
ALWAYS_SELL = ["FERTILIZER", "EGG", "CARROT", "TOMATO"]
# 肥料: d0が最高値で減衰 → 即売り。EGG/CARROT/TOMATO は T が大きく glut になりにくい。
I0 = 10000
GLUT_SLACK = 10
SHED_DUMP = 78  # shed+当日流入がこれ以上ならプレミアム品も全量ダンプ(overflow回避)

# gen0044 (H2「売り時 burst」): WOOL/MELON の SELL 量を限界価格から解く（β=0.55, 単一値・sweep しない）。
# エンジン MARKET_PARAMS（kaggriculture.py 41-51, WOOL/MELON とも above_func="sq"）から導出:
#   glut 側 price(inv) = base − amp·(inv−I0)², amp = above_target·base / T²（f(T)=T²）。
# 「最後の 1 個の限界価格 ≥ β·base」を満たす最大の SELL 量 N を解いて出す（beta_sell_cap）。
# scarcity/回復局面では price≥base で条件が常真＝生産律速の少量売り（勝者挙動）、glut では
# marg=β で止めて持ち越し、町 sink（WOOL）で価格が回復した日に自動で burst する（間隔ロジック不要）。
# MELON は町 sink≈0 で回復しないので同式が「終盤まで床へ落とさない累積キャップ」として働く。
BETA_SELL = ("WOOL", "MELON")
BETA_MKT = {  # derived: base/T/above_target は engine の MARKET_PARAMS そのもの
    "WOOL":  {"base": 200, "T": 105, "above_target": 3.20},   # amp = 3.20·200/105² = 0.05805
    "MELON": {"base": 250, "T": 300, "above_target": 3.60},   # amp = 3.60·250/300² = 0.01
}
BETA_SELL_FRAC = 0.55  # 勝者#1 が非終盤(d≤24)で割らなかった限界価格の床（Analyst 2026-09-07 実測）
MARKET_SLOTS = 10      # エンジン maxMarketOrdersPerTurn（FIX0009 のスロット確保に使う）
LAND_PRICES = [1000, 2000, 4000]
FIB = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
HIRES_PER_TURN = 3
# EXP0020: 現金 buffer を0にする再投資が動物 escape を招いた。discretionary buy
# (土地/動物/種) は RESERVE を残す。feed 小麦の買い増しは例外(維持が最優先)。
RESERVE = 400
# FIX0018: reconcile の realized 見積に掛ける残余ヘアカット。旧 reconcile は kept SELL を
# 一律 0.7·price で計上して own-slippage と共有市場スリッページを 1 係数に潰していた。
# gen0046 は own-slippage を BETA 品目の per-unit glut 価格式で明示的に織り込むので、
# ここは共有市場の同時売却（FIX0017・open）だけを hedge する軽いヘアカットに下げる。
SELL_REALIZE_SAFETY = 0.9


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


def hands_target(day, expand=False):
    """d10/d20 は土地+植付の最繁忙日で 14。fib コストは 12 人で $376/日と安い。

    gen0045: 発火時（expand）だけ hands を +1 する（d10/d20 の 14→15、d12-28 の 12→13）。
    羊 +4 頭（12→16 頭）の FEED/CARE を
    12 hands では吸収できず unfed/uncared が出る（seed7/14 実測: 供給ではなく hand-hour 律速。
    d21-26 で shed 小麦 15-21 個ありながら 16 頭中 1 頭が未給餌）。設計書 §4 注4 の「発火時のみ
    hands 曲線を動かす」の実装。expand=False の非発火では従来値のまま（IDEA_POLICY 禁止 2 の
    単独 hands+1 ではなく、拡張と束ねた発火限定の増員）。
    """
    if day == 0:
        return 5
    if day < 5:
        return 4
    if day < 10:
        return 7
    if day == 10 or day == 20:
        return 14 + (1 if expand else 0)
    if day < 29:
        return 12 + (1 if expand and day >= EXPAND_W0 else 0)
    return 10


def yarn_count(shops):
    """観測 unlocked_shops 中の YARN_STORE 軒数（羊毛需要の代理）。"""
    return shops.count("YARN_STORE")


def expansion_active(day, yarn, unlocked):
    """SE 資金の羊増頭を発火させるか（ステートレスに毎ターン導出）。設計書 §4。

    se_owned（SE を既に買った）か、まだでも d12-16 の購入窓なら発火。yarn は単調増加・
    unlocked_quadrants は減らないので、この式はステートで持たなくても一貫する。y<2 では
    増頭の限界収入が負〜ゼロ（§1b）なので発火しない。
    """
    se_owned = len(unlocked) >= 4
    return yarn >= YARN_MIN and (se_owned or EXPAND_W0 <= day <= EXPAND_W1)


def sheep_target(day, yarn, se_owned):
    """羊の目標頭数。y>=2 かつ SE 取得後だけ 8、それ以外は現状維持の 4。設計書 §4。

    day は署名の一貫性のため受けるが判定には使わない（頭数は yarn と se_owned で決まる）。
    """
    if yarn < YARN_MIN or not se_owned:
        return 4                 # y=0/1 または SE 未取得: 現状維持（過剰供給に踏み込まない）
    return 8                     # y>=2 かつ SE 取得後。設置は空きパスチャ数で自然に位相化


def land_target(day, yarn=0, unlocked=()):
    """unlocked_quadrants の目標数。NE=d6、SW=d8。SE は原則買わない。

    gen0049 (Stage B): SW 購入日を d11→d8 に前倒し。イチゴ SW 波(rows 6-8)の from_day 8 と
    型ごと同時に動かし、SW クアドラント購入 d8・植付完了 d9 を狙う（LB #1 実測目標）。買い
    ループの reconcile が現金不足なら自動で後日へ繰り延べる。SE・NE・expansion 分岐は不変。

    gen0045: expansion_active（y>=2 の町で d12-16 の窓、または SE 既取得）なら 4 を返し
    SE($4,000) の購入を許す。d17+ に未取得のままなら 3 に戻る（＝未購入なら永久に買わない。
    既購入なら len(unlocked)>=4 で下の購入ガード自体が閉じる）。設計書 §7-7。
    """
    if expansion_active(day, yarn, unlocked):
        return 4
    if day >= 8:
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
    # gen0031: 係数 6/12/6 は「床未満価格でのトリクル売りの安全レート」として
    # 当てにいった値（tuned）で、**町の実際の消費量から導いたものではない**。
    # 実測（vs kaito_v48 s42）では相手が MILK 335 個・STRAWBERRY 428 個を売るのに対し
    # こちらは 186 個・83 個しか売っていない。gen0030 で粒度を細かくしても総量は
    # 1 個も変わらなかった（縛っているのはこの係数）ので、tuned 定数の削り世代として
    # 2 倍にして「安全側に寄せすぎている分がいくら金になるか」を測る。
    # ここが効けば、次は係数ではなく在庫の実測ドレインから導く形に置き換える。
    return {"MILK": 1 + 12 * m, "WOOL": 1 + 24 * y, "STRAWBERRY": 1 + 12 * s}


def beta_sell_cap(item, market_inv, day):
    """gen0044 (H2): β·base 限界価格で許す最大 SELL 量 N を返す。
    エンジンの glut 価格式 price = base − amp·(inv−I0)², amp = above_target·base/T² を
    N について解く: price(inv+N−1) ≥ β·base ⇔ inv+N−1 ≤ I0 + sqrt((1−β)·base/amp)。
    N = floor(I0 + root − market_inv) + 1。scarcity（inv<I0）では root ≫ 0 で N が大きく、
    実際の shed 在庫で頭打ち＝生産律速の少量売りになる（勝者の marg≈1.0 挙動を自動再現）。
    終盤 d25 以降は β を DUMP_DAY に向けて線形に 0 へ逓減（terminal 持ち越しは全損）。
    d≥DUMP_DAY は呼び出し側が価格を問わず全量売りするのでここには来ない。"""
    m = BETA_MKT.get(item)
    if m is None:
        return None
    if day < 25:
        beta = BETA_SELL_FRAC
    else:
        # d25→DUMP_DAY(28) で 0.55 から 0 へ。span = DUMP_DAY − 24。
        beta = BETA_SELL_FRAC * max(0, DUMP_DAY - day) / float(DUMP_DAY - 24)
    base = m["base"]
    amp = m["above_target"] * base / float(m["T"] * m["T"])
    root = ((1.0 - beta) * base / amp) ** 0.5
    # FIX0016: floor を意図。int((I0+root)-market_inv) は差が負の境界で 0 方向へ切り捨て、
    # 正しい cap 0 のところ 1 を返して β·base を割る 1 個を売る。I0+root は正なので
    # int(I0+root)=floor、market_inv は整数なので下式が正しい floor になる。
    return int(I0 + root) - market_inv + 1  # FIX0016


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
    # gen0045: 拡張トリガをステートレスに導出（設計書 §4）。非発火 seed では expand=False で
    # 全拡張分岐が閉じ、親とバイト単位で同一挙動になる。
    unlocked = list(me.get("unlocked_quadrants") or ["NW"])
    yarn = yarn_count(shops)
    se_owned = len(unlocked) >= 4
    expand = expansion_active(day, yarn, unlocked)

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
                elif crop == "CARROT":
                    # gen0047: age3(max yield 日)で刈る。age4 から decay。
                    # FIX0020/FIX0019: 全 carrot を d28 までに刈り d29 をシェッド搬送に空ける。
                    # d25 植えは d28 に age3(第1節, 収量2=d27+d28 の水やり)。d26 植えは d28 に
                    # age2(第2節, 収量1=d28 の水やり)。どちらも d28 収穫→carried→d29 の丸一日で
                    # DROP+SELL。d29 に carrot bonus WATER を足す FIX0019 は不要（遠征を無くす方で解決）。
                    ripe = age >= 3 or (day >= FINAL_DAY - 1 and age >= 2)   # FIX0020: 全 carrot を d28 までに刈り d29 をシェッド搬送に空ける  # FIX0019
                    hpri, wpri = 2.2, 3.02
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
                            # FIX0006: 生産日にまだ水をやっていない株も、この同じターンで
                            # bonus_water（生産日の水やり）が出て水やり→施肥が対で必要になる。
                            # 施肥を FERT_PRI（層4・PLANT の後）に置くと、水やり（層2）だけが
                            # 済んで施肥が後回し→未施肥のまま +1 止まりになる株が出る
                            # （実測 1 収穫あたり 1.75u ＜ 強帯 1.99u）。水と同じ層2に上げ、
                            # 同じ訪問で対を閉じて 1 収穫あたり ≥1.9u を狙う。窓外・visit_ok=False
                            # の帯（最終日・植付締切）は day<FINAL の条件で従来どおり除外。
                            pri = (FERT_PRI_PAIR if (watered or bonus_water)
                                   else FERT_PRI)
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
                        prod = spec["product"]
                        pp = prices.get(prod, 0)
                        # FIX0015: BETA_SELL 品目（WOOL）の収穫解除ゲートを、市場売却と同じ
                        # 動的 β 判定に合わせる。固定 SELL_FLOORS だと $110-119 帯や d25-27 の
                        # 逓減床では β が売却可でも羊上の在庫を収穫せず d28 強制収穫へ先送りし、
                        # 回復日 burst を取り逃す。非 BETA 品目は従来の SELL_FLOORS 床のまま。
                        if prod in BETA_SELL:  # FIX0015
                            unlock = (beta_sell_cap(prod, minv.get(prod, I0), day)
                                      or 0) > 0
                        else:
                            unlock = pp >= SELL_FLOORS.get(prod, 0)
                        if (day >= DUMP_DAY or yu >= spec["max_held"] - 1
                                or unlock):
                            todos.append((2.0, x, y, ["HARVEST"], None))
                # FIX0011: 最終行動ターンに肥料を回収しても売る手番が無い（1 個死蔵）。
                if t.get("fertilizer_available") and not (
                        day >= FINAL_DAY and hour >= LAST_ACTION_HOUR):
                    todos.append((4.0, x, y, ["COLLECT_FERTILIZER"], None))

    carried_animals = {a: sum(inv.get(a, 0) for inv in invs) for a in ANIMALS}
    owned = {a: placed.get(a, 0) + carried_animals[a] + shed.get(a, 0)
             for a in ANIMALS}
    owned_total = sum(owned.values())
    # gen0045 §5: 飼料の先回り。拡張確定なら羊 8 頭ぶんの飼料在庫目標を「羊が来る前から」
    # 立てる（unfed_days=0 の機械保証）。非発火では expand=False → planned_total=owned_total
    # で親と厳密一致。購入日 T は se 未取得だが sheep_target(..., True)=8 で最終頭数を先取り
    # する（拡張は窓内で確定しているため）。
    if expand:
        planned_total = owned_total + max(0, sheep_target(day, yarn, True)
                                          - owned["SHEEP"])
    else:
        planned_total = owned_total

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
    # gen0045: 明日の羊+牛の目標ぶんまで先に建てる。非発火は sheep_target=4 で親と一致。
    want_built = min(len(PASTURE_TILES),
                     max(owned_total,
                         sheep_target(min(day + 1, 29), yarn, se_owned)
                         + cow_target(min(day + 1, 29))))
    shortage = want_built - built_pastures
    for x, y in free_slots[:max(0, shortage)]:
        todos.append((2.6, x, y, ["BUILD_PASTURE"], None))
        pasture_work_tiles.append((x, y))

    # ---- 植付スケジュール（役割タイル + 植付窓）----
    hour_ok = hour <= LAST_PLANT_HOUR
    plant_slots = {"MELON": 0, "STRAWBERRY": 0, "WHEAT": 0, "CARROT": 0}
    window_end = {}   # crop -> 今開いている窓の最終日（3-D の種購入で使う）
    # gen0057: 今ターン、空きタイルをニンジンに置き換えてよい枚数（市場在庫が決める）。
    # 0 なら以下の分岐は一切通らず親 gen0051 と同一挙動。
    carrot_fill_left = carrot_fill_budget(minv, day)
    # 置き換えの対象タイル: 小麦計画の「終盤ブロック」(from_day>=WHEAT_LATE_FROM_DAY) と
    # 計画外の fallback タイルだけ。**飼料の芯には触らない** ——
    # NW 基幹 7 枚 (from_day 0) と SE 飼料小麦 6 枚 (from_day 12) は小麦のまま。
    # d10 の自給拡張 13 枚も除外する（飼料の自給がこの期の設計前提）。
    for crop, plan in CROP_PLANS.items():
        # gen0047: per-crop 植付期限。既定は LAST_PLANT_DAY(25)。CARROT だけ 26
        # （FIX0020: d26 植えは d28 に age2 で刈れる。d27 植えは d29 収穫になり増収 0＋死蔵）。
        # キー無しの MELON/STRAWBERRY/WHEAT は既定のまま＝挙動不変。
        lpd = plan.get("last_plant_day", LAST_PLANT_DAY)
        open_w = [(a, b) for a, b in plan["windows"] if a <= day <= b]
        w_open = day <= lpd and bool(open_w)
        if not w_open:
            continue
        window_end[crop] = min(max(b for _a, b in open_w), lpd)
        for x, y, from_day in plan["tiles"]:
            if day < from_day:
                continue
            t = tile_at(x, y)
            if t is None:
                # gen0057: 終盤ブロックの空き小麦タイルだけ、市場在庫が許す枚数を
                # ニンジンに置き換える。**優先度は小麦計画のまま（plan["plant_pri"]）**＝
                # 層は動かさない。層を上げて労働を奪ったのが gen0053 の −$682 の原因なので、
                # ここは「何を植えるか」だけを変え、「いつ植えるか」は訪問完了(Edit A)に任せる。
                put = crop
                put_pri = plan["plant_pri"]
                if (crop == "WHEAT" and from_day >= WHEAT_LATE_FROM_DAY
                        and carrot_fill_left > 0):
                    put = "CARROT"
                    # 優先度も CARROT 計画のもの（2.24 = 層2）を使う。これは新しい昇格ではなく
                    # **gen0048 Stage A が carrot 植付に対して既に与えている分類**で、その根拠も
                    # 当時の設計に書いてある（「この 1 手は carrot 2-3 個 × $25-35 を新規に生むので
                    # 経済クラスはイチゴ HARVEST と同じ」）。作物が carrot なら層も carrot のものに
                    # 揃える、という一貫性の適用にとどめる。
                    put_pri = CROP_PLANS["CARROT"]["plant_pri"]
                    carrot_fill_left -= 1
                    window_end.setdefault(
                        "CARROT",
                        CROP_PLANS["CARROT"].get("last_plant_day", LAST_PLANT_DAY))
                plant_slots[put] += 1
                if hour_ok:
                    todos.append((put_pri, x, y,
                                  ["PLANT", put], "SEED:" + put))
            elif isinstance(t, dict) and t.get("kind") == "WEED":
                # 予定作業(植付)を今塞いでいる雑草だけ DIG（scout §5）
                # gen0048 Stage A: carrot 窓内の decay タイル DIG は「収量を作る行動」なので
                # 層3(2.6)→層2(2.22) に再分類（IDEA_POLICY §4）。他作物予定地 DIG は 2.6 のまま＝挙動不変。
                todos.append((2.22 if crop == "CARROT" else 2.6, x, y, ["DIG"], None))
                if crop == "CARROT":
                    # FIX0008 部分適用（carrot スコープ限定）: DIG 予定の decay タイルも
                    # 種需要に数え、DIG→(翌ターン)slots→購入→植付の 2 ターン遅れを縮める。
                    # 他作物 fallback には触れない（FIX0008 は台帳 open のまま）。この分岐は
                    # 窓が開いている間しか回らないので『carrot 窓が開いている間だけ』が自動で成立。
                    plant_slots["CARROT"] += 1

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
                # gen0057: 計画外タイルも同じ予算で置き換える（優先度は fallback_pri のまま）。
                put = FALLBACK_CROP
                put_pri = fb["fallback_pri"]
                if carrot_fill_left > 0:
                    put = "CARROT"
                    put_pri = CROP_PLANS["CARROT"]["plant_pri"]
                    carrot_fill_left -= 1
                    window_end.setdefault(
                        "CARROT",
                        CROP_PLANS["CARROT"].get("last_plant_day", LAST_PLANT_DAY))
                plant_slots[put] += 1
                if hour_ok:
                    todos.append((put_pri, x, y,
                                  ["PLANT", put], "SEED:" + put))
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
    n_zones = max(n_hands, hands_target(day, expand), 1)
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
    # gen0036 (codex P1-1): 重み分割をクアドラントの中で閉じる。
    # 旧: ソート済みの全 items を通しで累積して切っていたので、切れ目がクアドラント境界に
    # 揃わず、**NE の末尾と SW の先頭が同じゾーン**になっていた（実測 sm34_42 d11 の zone 9 は
    # NE(9,3),(9,4) + SW(0,5)..(0,8) で最遠 14 歩。コメントの「帯幅 + 行数 − 1」に収まっていない）。
    # 3 クアドラントで初めて顕在化する（2 クアドラントの時は NW→NE の 1 箇所だけだった）。
    # 直し方: クアドラントごとに重み比でゾーン本数を配り（最大剰余法）、その中で従来どおり切る。
    total_w = sum(w for _, _, w in items)
    q_of = lambda x, y: (0 if y < 5 else 2) + (0 if x < 5 else 1)
    groups = []            # [(q, [items...], weight)]
    for x, y, w in items:
        q = q_of(x, y)
        if groups and groups[-1][0] == q:
            groups[-1][1].append((x, y, w))
            groups[-1][2] += w
        else:
            groups.append([q, [(x, y, w)], w])
    if total_w > 0 and n_zones >= len(groups):
        # 最大剰余法。重みのあるクアドラントには最低 1 ゾーン。
        quota = [g[2] * n_zones / total_w for g in groups]
        share = [max(1, int(qq)) for qq in quota]
        while sum(share) > n_zones:            # 端数で溢れたら大きい方から削る
            # codex P1: 「最低 1 本」で底上げした小さい group を選んでしまうと
            # share[k] <= 1 で break し、**sum(share) > n_zones のまま抜ける**。
            # そのとき base + hi が n_zones を超え、zone_animals[h] が IndexError →
            # 最外層の except に落ちて**そのターンの全 hand が PASS**になる（静かな障害）。
            # 削れる group（share > 1）だけから選ぶ。n_zones >= len(groups) なので、
            # このループに入っている限り candidates は必ず非空。
            cands = [i for i, v in enumerate(share) if v > 1]
            if not cands:
                break
            k = max(cands, key=lambda i: (share[i] - quota[i], share[i]))
            share[k] -= 1
        while sum(share) < n_zones:            # 余りは剰余の大きい順に配る
            k = max(range(len(share)), key=lambda i: quota[i] - share[i])
            share[k] += 1
    else:
        share = None
    if share is None:
        acc = 0
        hi = 0
        for x, y, w in items:
            zone_of[(x, y)] = hi
            acc += w
            while hi < n_zones - 1 and acc * n_zones >= total_w * (hi + 1):
                hi += 1
    else:
        base = 0
        for gi, (_q, gitems, gw) in enumerate(groups):
            k = share[gi]
            acc = 0
            hi = 0
            for x, y, w in gitems:
                zone_of[(x, y)] = base + hi
                acc += w
                while hi < k - 1 and acc * k >= gw * (hi + 1):
                    hi += 1
            base += k
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

    # gen0032: 訪問完了を止める条件（上の LOSS_PRIS のコメント (b)(c)）。
    # (b) は「締切時刻に達していて、まだ植付の todo が残っている」時だけ止める。
    #     時刻を過ぎれば PLANT todo 自体が出ないので、止める理由も消える。
    visit_ok = (day < FINAL_DAY
                and not (hour >= LAST_PLANT_HOUR
                         and any(op[0] == "PLANT" for _p, _x, _y, op, _n in todos)))

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
                        if i == 0:
                            # FIX0005: farmer は所有者が今日まだ来られる間は
                            # _owner_can_come が global fallback で弾く（実際には claim
                            # できない）。最寄り判定にだけ farmer を残すと、farmer が
                            # 近いだけで所有者の FEED/CARE claim を潰し、farmer 自身も
                            # 保護で降りて両者が譲り合い両方 PASS になる（unit-hour の
                            # 全損）。保護の対象集合と最寄り判定の対象集合を一致させる。
                            # rescue 時・所有者不在時は _owner_can_come が False を返す
                            # ので farmer は従来どおり候補に残る。
                            if _owner_can_come(x, y, zi, op):
                                continue
                        elif not (rescue or owner is None or zi == owner):
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
                lay = pri_layer(eff)
                if visit_ok and d == 0 and op[0] in DAILY_TILE_OPS:
                    lay = min(lay, VISIT_LAYER)
                crit = 0 if pri in LOSS_PRIS else 1
                key = (lay, crit, d, eff)
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
            # gen0036 (codex P1-2): **gen0023 の codex fix2 の再適用**。
            # 今ターン実際にシェッド上で PICKUP を実行する hand だけが在庫を予約する。
            # シェッドへ移動中の hand が予約すると、既にシェッド上にいる後続 hand が
            # 実在庫を積めない（歩行中の予約は次ターンに持ち越されず幽霊予約になる）。
            # この修正は gen0023 に入っていたが、gen0023 が非昇格で gen0024 の親が
            # gen0022 だったため王者系統に伝わっていなかった（HANDOFF の繰越項目）。
            # claimed には入れないので複数 hand の同時積みは従来どおり可。
            if (ux, uy) == (x, y):
                shed_wheat_free -= op[2]
        elif need == "ZFERT":
            if (ux, uy) == (x, y):
                shed_fert_free -= op[2]   # 同上（肥料）
        else:
            claimed.add((pri, x, y, tuple(op)))
            if (need and need.startswith("SEED:")
                    and (ux, uy) == (x, y)):
                # FIX0004: 種数の予約は、今ターン実際に植える hand だけが行う
                # （FIX0001 の種版。gen0022 から継承）。移動中の hand が予約すると
                # planned_seed >= seeds で種切れと誤判定し、現地に立って今すぐ植える
                # hand が弾かれる（幽霊予約）。タイルの claim（上の claimed.add）は
                # 歩行中も維持するので、同じ苗床を二重取りすることはない。
                # 種購入（下の BUY_SEED）は plant_slots で数えており planned_seed を
                # 使わないので、予約を絞っても過剰購入にはならない。
                planned_seed[need[5:]] = planned_seed.get(need[5:], 0) + 1
        if (ux, uy) == (x, y):
            actions.append(list(op))
        else:
            actions.append([step_toward(ux, uy, x, y)])

    # ---- 市場（優先順に組み立て、10スロットに切る。SELL の代金は同ターンの
    #      後続スロットの BUY/HIRE/LAND に使える）----
    # FIX0009: maxMarketOrdersPerTurn=10。SELL を全部先頭に積むと HIRE/BUY_SEED が
    # 末尾で押し出される。SELL と essential buy を別リストに分け、最後に essential buy 用の
    # スロットを確保してから SELL を（品目価値の高い順に）詰める。mest は従来どおり
    # SELL→BUY の順で更新するので購入の資金ゲートは不変（最終リストの並びも SELL→BUY）。
    pre = []     # slot 0 固定（開幕 denial）
    sells = []   # SELL 群（value 降順に並べ、溢れたら安い品目から落とす）
    buys = []    # essential buy（BUY_PRODUCT/LAND/ANIMAL/HIRE/SEED）
    buy_costs = []  # FIX0014: 各 buy の見積代金（mest 減算分）。keep_sells 後の予算再組立てに使う
    mest = float(money)  # 概算残高（売却は7掛けで保守的に計上）

    # (0) 開幕 feed denial: 小麦5個の購入注文を必ず slot 0 に置く（scout §4）
    if day == 0 and hour == 0:
        pre.append(["BUY_PRODUCT", "WHEAT", 5])
        mest -= 5 * (prices.get("WHEAT", 25) + 2)

    # (1) 売却
    total_placed = sum(placed.values())
    shed_total = sum(shed.values())
    carried_total = sum(sum(inv.values()) for inv in invs)
    shed_pressure = shed_total + carried_total
    # gen0045 §5-2: 売却リーク防止も planned 基準に。トリガ日に余剰小麦を売ってから羊が来る、
    # を防ぐ。発火時は planned_total（既所有=placed+carried+shed ＋ 追加予定羊）で予約する。
    # 旧式 total_placed + (planned_total - owned_total) は、購入済み・未配置の羊が placed にも
    # 追加予定にも数えられず予約から消える穴があった（Codex gen0045#P1-1）。非発火は expand=False
    # で planned_total==owned_total だが total_placed を使い親と厳密一致させる。
    feed_buffer = (planned_total if expand else total_placed) * 3 + 2
    # FIX0003: 最終日は手持ちを DROP してから SELL する（DROP は step2 / SELL は step3 で
    # 同一ターン内で shed に載る）。売却数を『行動前の shed 在庫』で決めると DROP 分を
    # 取り逃すので、最終日だけ carried を上乗せする。過剰売却は無害（在庫尽きで停止）。
    # 最終日以外は carried_item が空なので .get は 0 を返す＝挙動不変。
    carried_item = {}
    if day >= FINAL_DAY:
        for _ui, _inv in enumerate(invs):
            # FIX0020: 今ターン実際に DROP する在庫だけを SELL 数に数える（届かない在庫の幽霊 SELL を止める）。
            # actions は上で全ユニット分組み終わっており、DROP を選ぶのは今ターンにシェッド上に
            # 立っていてこのターンに落とす unit だけ（歩行中の unit は MOVE を積む）。FIX0003
            # （今ターン DROP する分を shed 在庫に上乗せする）はこれで温存され、届かない在庫への
            # 反復 SELL 注文（無言 no-op）だけが消える。
            if _ui < len(actions) and actions[_ui] and actions[_ui][0] == "DROP":
                for k, v in _inv.items():
                    carried_item[k] = carried_item.get(k, 0) + v
    if shed_wheat > feed_buffer or day >= DUMP_DAY:
        n = (shed_wheat if day >= FINAL_DAY else shed_wheat - feed_buffer) + carried_item.get("WHEAT", 0)
        if n > 0:
            sells.append(["SELL", "WHEAT", n])
            mest += n * prices.get("WHEAT", 25) * 0.7
    for item in ALWAYS_SELL:
        n = shed.get(item, 0) + carried_item.get(item, 0)  # FIX0003: 最終日の DROP 分を含める
        if item == "FERTILIZER":
            # gen0025: 今日〜2 日以内に撒く予定の分は売らない。1 個で生産 2 回が
            # +1→+2（イチゴ 2 個 ≈ base $240）なので、肥料の売値 $100 より高い。
            n -= fert_soon
        if n > 0:
            sells.append(["SELL", item, n])
            mest += n * prices.get(item, BASE_VALUE.get(item, 1)) * 0.7
    # gen0044 (H2): WOOL/MELON は β 解法パスで売り時を解く。scarcity/回復日は生産律速の
    # 少量売り、glut は marg=β で止めて持ち越し、d≥DUMP_DAY・シェッド溢れは全量清算。
    for item in BETA_SELL:
        n = shed.get(item, 0) + carried_item.get(item, 0)  # FIX0003: 最終日の DROP 分を含める
        if n <= 0:
            continue
        p = prices.get(item, 0)
        if day >= DUMP_DAY or shed_pressure >= SHED_DUMP:
            qty = n  # 終盤の清算とシェッド溢れは価格を問わず全量
        else:
            cap = beta_sell_cap(item, minv.get(item, I0), day)
            qty = min(n, max(cap or 0, 0))
        if qty > 0:
            sells.append(["SELL", item, qty])
            mest += qty * p * 0.7
    town_absorb = premium_absorb(shops)
    for item, floor in SELL_FLOORS.items():
        if item in BETA_SELL:
            continue  # gen0044 (H2): WOOL は β パスで売る（SELL_FLOORS は 589 の収穫ゲート用に残す）
        n = shed.get(item, 0) + carried_item.get(item, 0)  # FIX0003: 最終日の DROP 分を含める
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
            # gen0030: 1 日ぶんの吸収量を 24 時間に均等配分し、その時刻の取り分だけ出す。
            # 旧は hour == 0 にまとめて出していたので、その瞬間だけ在庫が跳ねて
            # 自分で価格を下げていた。1 日の合計は変わらない（粒度だけの変更）。
            trickle = 0
            if p > 1:
                a = town_absorb.get(item, 1)
                trickle = a * (hour + 1) // HOURS_PER_DAY - a * hour // HOURS_PER_DAY
            budget = I0 + GLUT_SLACK - minv.get(item, I0)
            qty = min(n, max(trickle, budget, 0))
        if qty > 0:
            sells.append(["SELL", item, qty])
            mest += qty * p * 0.7

    # (2) 給餌用小麦の補充（自給不足分のみ。土地・種より優先 = 動物を守る）
    # gen0045 §5-1: owned_total を planned_total に置換。拡張確定なら羊が来る前から在庫目標が
    # 上がり、市場買い足しが T 日から始まる（unfed 対策）。非発火では planned_total=owned_total。
    carried_wheat = sum(inv.get("WHEAT", 0) for inv in invs)
    if planned_total > 0 and day <= LAST_FEED_DAY:
        stock = shed_wheat + carried_wheat
        if stock < planned_total:
            want = min(planned_total * 2 - stock, 12)
            wp = prices.get("WHEAT", 45)
            qty = min(want, int(mest // (wp + 5)))
            if qty >= 1:
                buys.append(["BUY_PRODUCT", "WHEAT", qty])
                # FIX0018 (1): reconcile 用の見積代金は数量決定と同じ保守単価 wp+5 で計上
                # （数量は上の int(mest // (wp + 5)) で決めている）。mest 減算は親と同じ wp+3 の
                # ままにして、通常ターンの buy 構築＝親とバイト同一を保つ（buy_costs は
                # truncation ターンの reconcile でしか読まれない）。
                buy_costs.append(qty * (wp + 5))
                mest -= qty * (wp + 3)

    # (3) 土地（d6: NE, d10: SW, gen0045: 発火時 d12-16 に SE。mest に売却代金込み）
    n_extra = len(unlocked) - 1
    if len(unlocked) < land_target(day, yarn, unlocked) and 0 <= n_extra < len(LAND_PRICES):
        cost = LAND_PRICES[n_extra]
        if mest >= cost + RESERVE:
            buys.append(["BUY_LAND"])
            buy_costs.append(cost)
            mest -= cost

    # (4) 動物購入（不足数を一括、パスチャ数でキャップ）
    # gen0045 §7-6,5,9: room・目標・購入窓・qty を拡張対応にする。非発火では
    # COW_MAX+sheep_target=8+4=12=MAX_ANIMALS・last=辞書値・tgt=4・cap 無しで親と厳密一致。
    room = (COW_MAX + sheep_target(day, yarn, se_owned)) - owned_total
    for a in ("SHEEP", "COW"):
        spec = ANIMALS[a]
        # §7-5: 拡張時のみ羊の購入窓を d18 まで延ばす（辞書値 10 は非発火で不変）。
        if a == "SHEEP" and expand:
            last = 18
        else:
            last = spec["last_buy"]
        if day > last:
            continue
        tgt = sheep_target(day, yarn, se_owned) if a == "SHEEP" else cow_target(day)
        deficit = min(tgt - owned[a], room)
        if deficit <= 0:
            continue
        afford = int((mest - RESERVE) // spec["cost"])
        qty = min(deficit, afford)
        # §7-9: 拡張の羊はシェッド滞留を作らないよう空きパスチャ数でキャップ。expand の時
        # だけ効かせる（非発火・d0 の基幹羊 4 頭は空きパスチャ 0 の朝でも買えねばならない）。
        if a == "SHEEP" and expand:
            qty = min(qty, len(empty_pastures))
        if qty >= 1:
            buys.append(["BUY_ANIMAL", a, qty])
            buy_costs.append(qty * spec["cost"])
            mest -= qty * spec["cost"]
            room -= qty

    # (5) 雇用（1ターン最大3件、fib 次コストで資金ゲート）
    tgt_h = hands_target(day, expand)
    hires_today = me.get("hires_today", 0)
    k = 0
    while (k < HIRES_PER_TURN and len(hand_pos) + k < tgt_h
           and hires_today + k < tgt_h):
        c = FIB[min(hires_today + k, len(FIB) - 1)]
        if mest < c + 20:
            break
        buys.append(["HIRE"])
        buy_costs.append(c)
        mest -= c
        k += 1

    # (6) 種の補充（開いている植付枠 − 所持種。メロン > イチゴ > 小麦の順）
    # gen0024 3-D: 買う数を「今この時刻から窓が閉じるまでに物理的に植えられる数」で
    # 頭打ちにする。1 unit は 1 時間に 1 回しか PLANT できず、LAST_PLANT_HOUR を過ぎた
    # 植付は当日の水やりが間に合わず確定枯れなので植えない。gen0022 は窓の最終日の
    # 夕方でも空きタイル数だけ買い、そのまま窓が閉じて死に種になっていた
    # （イチゴ $100・メロン $80、seed42 d15 で $440）。
    n_units = len(units)
    for crop in ("MELON", "STRAWBERRY", "WHEAT", "CARROT"):  # gen0047: carrot は優先最後
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
            buys.append(["BUY_SEED", crop, qty])
            buy_costs.append(qty * plan["seed_cost"])
            mest -= qty * plan["seed_cost"]

    # FIX0009: essential buy を確保してから SELL を詰める。SELL は品目価値（BASE_VALUE·qty）
    # 降順に並べ、溢れたら安い品目（WHEAT/EGG など）から落とす。SELL の代金は buy より前に
    # 積むので資金順は保たれる（denial buy は slot 0 固定で cheap＝開始資金で賄える）。
    sells.sort(key=lambda o: -BASE_VALUE.get(o[1], 0) * (o[2] if len(o) > 2 else 1))
    # FIX0014: mest は全 SELL 候補の 0.7 掛け代金を含むが、実約定するのは sells[:keep_sells]
    # だけ。落とした低価値 SELL の架空代金で資金ゲートを通した essential buy が、重い購入日に
    # 実代金不足で無言 no-op しうる（keep_sells が 1-2 に絞られ、落とす代金合計が RESERVE 超）。
    # 実約定する SELL だけで購入予算を組み直し、賄えない末尾の buy を落として（その枠を SELL に
    # 返して）安定させる。SELL が全数残る通常ターンでは realized>=total が必ず成り立ち buys 不変
    # ＝親と挙動一致（gen0044 が全 buy を発注できた＝money+全SELL代金>=総購入代金なので）。
    #
    # FIX0018: FIX0014 の reconcile を「実約定可能性」ベースに精緻化する。精緻化は SELL が
    # 10 スロットで truncation されるターンだけに効かせる。SELL が全数収まる通常ターン
    # （no_trunc）では、gen0045 の reconcile は必ず realized>=total で不発（各 buy は構築時に
    # mest でゲート済みで、no_trunc なら kept SELL=全 SELL＝mest が数えた SELL と一致するため
    # 最終 mest>=0）＝ buys 不変になる。よってこの分岐を丸ごとスキップし、親とバイト同一の
    # 市場注文列を保つ（buy_costs の wp+5 化・realized 近似・RESERVE 再確認・部分約定縮小は
    # すべて truncation ターンだけを変える）。
    no_trunc = (MARKET_SLOTS - len(pre) - len(buys)) >= len(sells)  # FIX0018
    if not no_trunc:
        pre_spend = 0.0
        for o in pre:
            if o[0] == "BUY_PRODUCT":
                pre_spend += o[2] * (prices.get(o[1], 25) + 2)

        # FIX0018 (穴1): realized の過小評価を減らす。旧 _proceeds は kept SELL を一律
        # 0.7·price で計上し、高値の WOOL/MELON を残した重い購入日に realized<sum(buy_costs)
        # と誤判定して正当な BUY_LAND/BUY_ANIMAL を落としていた。新 _proceeds は BETA 品目
        # （WOOL/MELON）をエンジンの glut 価格式 price = base − amp·(inv−I0)² で 1 個ずつ
        # 足し込み、実約定額を近似する: scarcity 側(inv<=I0)は base で頭打ち（実価格>base の
        # プレミアムは無視＝保守側）、glut 側は 1 個ごとに逓減＝大量 SELL のスリッページ保険が
        # 自然に残る。少量の高値売りは base 付近まで戻るので 0.7·base 一律の過小評価が消える。
        # 非 BETA 品目は amp が無いので現行価格に係数を掛ける（value 降順で末尾＝truncation で
        # 先に落ちるため kept 側の寄与は小さい）。全体に SELL_REALIZE_SAFETY(0.9) を掛けて
        # 共有市場の同時売却(FIX0017)を hedge する（own-slippage を per-unit で織り込んだので
        # 旧 0.7 より緩められる。engine 単独 realized の上限を超えないので over-buy は誘発しない）。
        def _proceeds(o):
            item = o[1]
            qty = o[2]
            p = prices.get(item, BASE_VALUE.get(item, 1))
            m = BETA_MKT.get(item)
            if m is None:
                return qty * p * SELL_REALIZE_SAFETY
            base = m["base"]
            amp = m["above_target"] * base / float(m["T"] * m["T"])
            inv0 = minv.get(item, I0)
            tot = 0.0
            for j in range(qty):
                over = inv0 + j - I0
                pj = base - amp * over * over if over > 0 else base
                tot += pj if pj > 0.0 else 0.0
            return tot * SELL_REALIZE_SAFETY

        # FIX0018 (穴2): 各 buy に「購入後に残すべき残高」を併記する。feed 小麦=0（維持最優先で
        # RESERVE 例外）／ 土地・動物・種=RESERVE(400)／ HIRE=20。reconcile は末尾 buy を残すのに
        # 要る残置まで満たすか（realized >= sum(buy_costs[:nb]) + 末尾の required_reserve）を見る。
        # buys の並びは feed→land→animal→hire→seed 固定なので末尾は present な最後の種別。
        def _required_reserve(o):
            k = o[0]
            if k == "HIRE":
                return 20.0
            if k == "BUY_PRODUCT":
                return 0.0  # feed 小麦は RESERVE 例外（維持が最優先）
            return float(RESERVE)  # BUY_LAND / BUY_ANIMAL / BUY_SEED

        nb = len(buys)
        while nb > 0:
            keep = max(0, MARKET_SLOTS - len(pre) - nb)
            realized = (float(money) - pre_spend
                        + sum(_proceeds(o) for o in sells[:keep]))
            need = sum(buy_costs[:nb]) + _required_reserve(buys[nb - 1])
            if realized >= need:
                break
            # FIX0018 (穴3): 末尾が数量注文なら、全落ちの前に RESERVE を残して買える数量へ
            # 縮小する。エンジンは市場注文を 1 個ずつ約定させるので部分約定（例 SHEEP 4→3 頭）が
            # 可能。atomic 注文（BUY_LAND / HIRE）と、数量 1 まで縮めても賄えない場合だけ従来
            # どおり丸ごと落とす（nb-=1 で枠を SELL に返す）。
            tail = buys[nb - 1]
            if (tail[0] in ("BUY_ANIMAL", "BUY_SEED", "BUY_PRODUCT")
                    and len(tail) > 2 and tail[2] > 1):
                unit = buy_costs[nb - 1] / float(tail[2])  # 見積単価（数量決定と同じ保守単価）
                budget = realized - sum(buy_costs[:nb - 1]) - _required_reserve(tail)
                newq = int(budget // unit) if unit > 0 else 0
                if 1 <= newq < tail[2]:
                    buys[nb - 1] = tail[:2] + [newq]
                    buy_costs[nb - 1] = newq * unit  # market と整合させる
                    break  # 縮小後は realized >= sum(buy_costs[:nb]) + reserve を必ず満たす
            nb -= 1  # atomic / 1 個でも賄えない → 末尾 buy を落として SELL 枠を返す
        buys = buys[:nb]
    keep_sells = max(0, MARKET_SLOTS - len(pre) - len(buys))
    market = pre + sells[:keep_sells] + buys
    return {"farmer": actions[0], "hands": actions[1:], "market": market[:MARKET_SLOTS]}


def agent(obs):
    """例外はゲーム内即敗因: 全コードパスで dict を返す。（末尾定義 = ローダ対策）"""
    try:
        return _agent(obs)
    except Exception:
        return {"farmer": ["PASS"], "hands": [], "market": []}
