# Scout 2026-09-04: 公開情報から抽出した「なぜ効くか」

- 取得日: 2026-09-04（JST 夜）／取得方法: Discussion は Browser ツール（WebFetch は JS シェルのみで空）、Notebook 一覧は `kaggle kernels list --competition kaggriculture --sort-by voteCount`、本文は `kaggle kernels pull` で ipynb を取得しマークダウン層を読解。boatlee V16-RC5 に埋め込まれた公開ルート（Nikita Lugovoy 上位提出の再構成）は zlib+b85 をデコードして日次集計のみ行った（コード流用なし）。
- 目的: 我々が LB ~500-560 で頭打ち（最終 $40-65k）に対し、上位は $85-155k。個人参加者の公開知見を**ゲーム構造上の理由**に還元する。
- 取得できなかったもの: Kaggle の Code 一覧ページ（JS で描画されず空。CLI で代替）。Discussion 4-8 ページ目は未読（1-3 ページの戦略関連スレッドを優先）。

## 0. LB スナップショット（2026-09-04 取得時点）

- Top: Crop Dusta 3016.8 / keiz 2983.8 / Jesse Bullard 2967.8 / Giulio Ravasio 2923.4 / 薄和叶 2902.9。Top20 は 2812-3017。
- 我々: gen0013 = 559.0、gen0018 = 499.4（`state/STATUS.md` より）。上位と ~2400 点差。
- kaggle-environments: PyPI 最新 **1.32.7**（2026-08-15）、ローカルも 1.32.7。**差分なし**。運営は「1.32.7 がゲーム破壊バグ以外の最終変更」と明言（[Small balance change](https://www.kaggle.com/competitions/kaggriculture/discussion/735311)）。
- メタゲーム動向: 9/1-9/2 に LB #1 が 1 日で 10 回以上入れ替わり、上位陣が強エージェントを短時間出して引っ込める「リプレイ収穫回避」行動が観測されている（[destbreso](https://www.kaggle.com/competitions/kaggriculture/discussion/739179)）。終盤に未公開の強い型が出てくる前提で臨むこと。

## 1. 現在のメタ（上位の最終農場の形）

出典: [cjlcjlcjl: What the Top Farms Do — a Live Meta](https://www.kaggle.com/code/cjlcjlcjl/kaggriculture-what-the-top-farms-do-a-live-meta)（公式デイリーデータセットの Elo 3100+ 帯を集計、8/11 時点）、[Rayk Kretzschmar: Findings from Zero to Top Meta](https://www.kaggle.com/code/raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta)

| 項目 | 上位の modal 値 | 根拠 |
| --- | --- | --- |
| 動物 | **牛 8-9 + 羊 4-6**（8/8: 8c6s → 8/11: 9c4s に移行） | 羊数が主要な分岐軸 |
| 土地 | **NE+SW 購入、SE は買わない**（≈0%） | 3 quadrant = 75 タイル |
| hands | **10-12/日**（旧メタは 8） | fib コストは 10 人で $143/日 |
| 作物 | 小麦（飼料自給）+ イチゴ 6-7 + メロン 16-21 粒（序盤） | 小麦は「売る」より「餌」 |
| 最終資金 | 中央値 $84k、最大 $155k（両者が市場を分け合う実戦） | 公開 NB 同士の自己対戦では $140k 規模 |
| 現金曲線 | d5=$545 → d10=$2.2k → d15=$11.8k → d20=$36.4k | **d15 まで現金は殆ど無く、全部資産に変えている** |

- Rayk のリプレイ解剖では 8/9 時点で **top20 の 200 エピソードのうち 144 が同一 field hash**（40 チームが同じ農場ルートを複製）。上位の差は農場でなく**市場の売却タイミング**（c16→c18 は field 20 ターン差 vs market 112 ターン差）。
- **なぜこの形か**（構造への還元）:
  1. 動物は「CARE 込みで 1 + interval 個/回」＝牛 3 倍、羊 4 倍、かつ**肥料 1 個/日を餌の有無に関わらず無料で落とす**（`_daily_refresh_animals` は fed_today を見ない）。肥料は町のドレイン 0 だが glut 曲線が緩く ~$98 で売れ続け、シーズン $2,900/頭 ≒ 名目製品（乳/毛 $1.3-1.8k）の 1.6-2 倍。**動物 1 頭 = 製品 + 肥料の二重収入**（[Luka Duvanov スレッド内 destbreso コメント](https://www.kaggle.com/competitions/kaggriculture/discussion/734412)）。
  2. 牛乳・羊毛・イチゴは**町が掘った穴（scarcity 側）に売ると base の数倍**。町のシーズン消費量: 小麦 525、イチゴ 426、ニンジン/牛乳 327、トマト/卵/羊毛 228、メロン 30、肥料 0（[同スレッド](https://www.kaggle.com/competitions/kaggriculture/discussion/734412)、destbreso が独立に同値を導出）。イチゴを「穴」に売ると $100k、平場にダンプすると $4k（24 倍差）。
  3. SE ($4k) は「労働 + 通勤 + 雑草露出 + 資金拘束」で ROI 負。Rayk は 3 実装族 × 450 戦で全て 10-0 敗（[§13](https://www.kaggle.com/code/raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta)）。土地の真のコストは**それを働かせる hands と通勤**。

## 2. 開幕ビルド（上位ルートの日次骨格）

出典: [boatlee V16-RC5](https://www.kaggle.com/code/boatlee/v16-rc5-high-score-8c-4s-premium-market-lead) に埋め込まれた Nikita Lugovoy 提出 `sub-01` の再構成ルート（3 リプレイで field 同一・market 99.9% 一致）を日次集計。cjlcjlcjl の Elo3100+ 集計（初土地 d6、初 hire/牛/羊 d0、序盤種: 小麦 11.4・メロン 6.3・イチゴ 2.8）とも整合。

| 日 | 市場注文（要約） | hands | 農作業の主体 |
| --- | --- | --- | --- |
| **d0** | 飼料小麦 14、HIRE×5、**牛 1 + 羊 4**、メロン種 8、小麦種 7 | 5 | BUILD_PASTURE×5、PLACE、PLANT 10、WATER、**CARE 28** |
| d1-d5 | 肥料 5/日を売却、飼料小麦 2-17/日、イチゴ種 3-4、d5 に牛 +1 | 1-4 | CARE/FEED/COLLECT_FERTILIZER の日課 + WATER |
| **d6** | **BUY_LAND #1 (NE)**、牛 +2、小麦 17 + 羊毛 9 を売却 | 4 | EAST 移動が増える（NE 展開） |
| d7 | 牛 +2、イチゴ種 9、飼料小麦 15 | 7 | PLANT 14、WATER 33、CARE 31 |
| d8 | 牛 +2 → **牛 8 完成（step 192）** | 6 | |
| d9 | 初の牛乳売却 3 | 7 | |
| **d10** | **BUY_LAND #2 (SW)**、**メロン 39 売却（IPO）**、メロン種 12 + イチゴ種 16、飼料小麦 20 | **14** | 移動 144、CARE 68、PLANT 24 — 一日で最も忙しい |
| d11-d19 | 小麦種 1-11/日（自給へ移行、飼料購入は減少）、牛乳 3-27・羊毛 12-25・イチゴ 24-28（d16 から）を**分割売却** | 8-13 | WATER 40-60/日、HARVEST 14-25/日 |
| d20 | 第 2 波メロン 73 売却、**小麦種 49 購入**（終盤小麦ブロック） | 14 | |
| d21-d28 | イチゴ 11-37/日、牛乳 8-28/日、小麦 7-55/日、肥料 5-26/日 | 10-14 | |
| d29 | 小麦 161・牛乳 54・イチゴ 22・肥料 18 を最終清算、DROP 17 | 10 | |

**なぜ効くか**:
- **d0 に羊 4 頭**: 羊は間隔が最長（CARE 倍率 4 倍）かつ羊毛が最高単価。d6 から羊毛が売れ始め、初期の現金源になる（[Georgy Mamarin §6](https://www.kaggle.com/code/georgymamarin/kaggriculture-visualized-what-every-crop-pays): 「一番遅くて一番高い羊が最終的に先頭」）。
- **牛は d5-d8 に 7 頭追加**: 羊毛・肥料・メロンの現金が入ってから。d0 に牛を多数買うと餌が切れて d2 に逃げる（Rayk §7 の高頻度バグ）。
- **メロンは 2 波（d0 に 8 粒 → d10 IPO、d10 に 12 粒 → d20 売却）**: メロンは水だけで age 10 に 6 個上限（fertilize 無駄）。d10 の 39 個は「土地 2 枚目 + hands 14」への資金転換イベント。**上位は IPO 直後に 5-6 個ずつではなく 39 個をまとめて売る**＝I0=10,000 の深さに対しシーズン合計 ~100 個なら床（158 個）に届かないため。
- **d6 / d10 の土地購入は現金ではなく「働かせられる hands 数」で決まる**: NE は $1k で d6 に払えるが、hands が 7→14 に増える d10 まで SW は待つ。Georgy §8「土地と hands は一つの決断」。
- **小麦は d11 以降ほぼ自給**（種 1-11/日、飼料購入は 1-6）。我々の cycle6 分析「相手が小麦自給して買わない構造差 −$6-8k」と一致。

## 3. ショップ抽選（unlocked_shops）の読み方

出典: [Georgy §10](https://www.kaggle.com/code/georgymamarin/kaggriculture-visualized-what-every-crop-pays)、[tetsutani: Adaptive Farming Strategy](https://www.kaggle.com/code/tetsutani/adaptive-farming-strategy-for-kaggriculture)、[Kaito v48](https://www.kaggle.com/code/kaitofukami/40-40-early-floor-39-46-top-10-v48-fast-routes)、[prvsiyan: The Moon Counts Melons](https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-moon-counts-melons)

- 仕組み: 3 日ごと（day d の終わりに (d+1)%3==0）に 8 種から**復元抽出**、最大 8 軒。中央値シーズンは **5 種類しか開かない**。各店は 4 ターンごとに menu を消費（単品店は 2 倍）。合計 132 shop-instance-days。
- 分布の要点: 小麦・イチゴは多くの menu に載り**必ず買い手がいる**。**羊毛は YARN_STORE のみ → 34% のシーズンに買い手ゼロ**、幸運なら 3 軒。ニンジンは 10% で 0、p95 で 684。**メロンはどの menu にも無い**（町センターの 1 個/日 = 30 個/シーズンが唯一の吸収口）。
- 上位の使い方（**全員が「最初の 1-3 軒」を分岐シグナルにしている**）:
  - tetsutani: YARN_STORE が 1/2/3 番目 → 羊多めルート 3 種、ピザ/アイス/スムージー（牛乳系）が最初の 3 軒に → 作物寄りルート、その他 → 汎用。**「スポット価格は一時的、店の需要はシーズン中ずっと続く」**が根拠。
  - Kaito v48: step 88 の初店 YARN / step 120 の初店 FARMERS_MARKET / step 153 の 2 軒目 YARN / BAKERY→PIZZA で分岐（6 ルート・4 観測イベント）。
  - yhay81: 144 ターンごとに「ニンジンは高いか」「肥料は安いか」「現金差は正か」で 6 日ブロックを選ぶ決定木。
  - prvsiyan V189C: **step 0 に PASS して $3,000 を温存し、step 72 の初店を見てから特化**（YARN が先なら牛 5 頭分を羊に転換）。360 戦 86.7% 勝率。ただし RNG を消費する行動（作物・動物購入）で店の抽選自体が変わることを利用している。
- **重要な落とし穴（評価設計に直結）**: 店の抽選は**雑草スポーンと同じ乱数ストリーム**を使うため、**両農場の空きタイル数で店の並びが変わる**。同じ 12 シードで相手ボットを変えると 12/12 で店リストが変わった（Georgy §10）。→ 自分のボットの小改変では店が一致（対照実験になる）が、**相手を変えたベンチマークでは店が変わる**。我々の `evaluate.py` のシード固定比較は「同じ相手」の時のみ店統制が効く。
- 1.32.7 の変更点: ニンジン/トマト/卵の scarcity 側に hinge（T=450/200/332、knee 超えで 8×(x/T−1)² 加算）。**ニンジンは below_target 0.20→1.00 の方が効いている**（knee 以下でも単価 $41→$60）。町のドレインは中央値で knee に届かない（ニンジン 327 vs T=450、卵 228 vs 332）ので、**発火するのは店が偏った 1/4-1/2 のシーズンだけ**。上位は「ニンジンは d25 以降・5 個ずつ」の限定的採用（[destbreso / Luka Duvanov の実測](https://www.kaggle.com/competitions/kaggriculture/discussion/734412)）。Georgy の集計では 1.32.7 後にニンジン植付が 6%→44% に急増したが銀行残高の中央値は動かず（[Small balance change コメント](https://www.kaggle.com/competitions/kaggriculture/discussion/735311)）。

## 4. 価格モデルの扱いと売却タイミング

出典: [pilkwang §1](https://www.kaggle.com/code/pilkwang/kaggriculture-structured-economic-policy)、[Georgy §9](https://www.kaggle.com/code/georgymamarin/kaggriculture-visualized-what-every-crop-pays)、[cjlcjlcjl §4/§7](https://www.kaggle.com/code/cjlcjlcjl/kaggriculture-what-the-top-farms-do-a-live-meta)、[starkhushi 価格ログ](https://www.kaggle.com/competitions/kaggriculture/discussion/737736)

- 価格 = base ± amp·f(|inv − I0|)、I0=10,000、**scarcity 側と glut 側は別形状・別傾き**。清算は 1 個ずつ（R(x|I)=Σ p(I+i)）なので**両者の注文順が価格を決める**。$1 床での売却は在庫に加算されない（純損）。
- 床までの個数: 羊毛/イチゴ/牛乳 **~60-80 個**（最も脆い）、メロン 158（2 次）、トマト/ニンジン 500-850、小麦/卵 ~3000（事実上崩れない）。
- 上位の売却リズム（Elo3100+ 8/11）: 肥料 d4〜 4.9 個/回、羊毛 d6〜 9.8、小麦 d8〜 11.6、メロン d10〜 7.7、牛乳 d11〜 7.7、イチゴ d15〜 15.4。**全品目「小口・継続・価格が持つ間に多め」**。勝者はイチゴを d14、敗者は d16 に初売り＝**同じ農場なら先に売った方が勝つ**。
- 実測価格（上位 5 リプレイ）: 肥料は d0 の $100 が最高でひたすら減衰（→ 集めたら即売る）。プレミアム品のピークは **d9-14**（メロン 272@d10、牛乳 204@d9、羊毛 226@d12、イチゴ 204@d14）。d25 のメロンは d12 の 1/5。安い品（小麦・ニンジン・卵）は逆に終盤に**上がる**（小麦 25→45@d21）。暴落は回復しない（メロン 89@d16 → 96@d19）。
- **ミラー戦での差別化は「1 ターン先回り」**: 相手（近いクローン）の次ターン予定売却を公開在庫の変化から推定し、自分の予定売却の一部を 1 ターン前倒しし、**同量を翌ターンから引く**（総量不変、時刻だけ移す）。Hamburger 発、Rayk c15/C45/C94/C95、boatlee V16-RC5/V29-R1 が採用。C94 は「肥料のみ・最大 10 個」の前倒しが 18 体総当たりで 1 位（88-14）。逆に「もっと売る」「全リプレイの market tape を移植」「2 ターン先読み」は全て回帰（[Rayk §16](https://www.kaggle.com/code/raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta)）。
- 上位の負け方（Rayk C92 の 103 ライブ戦・31 敗の解剖）: **生産量は無関係で市場だけが敗因**。(a) 開幕 feed denial: 相手が d0 に小麦 14-19 個を先に買い、こちらの 5 個注文が 4 個しか買えず羊 1 頭が餓死（−$13.6k）→ 対策は「小麦 5 個を market slot 0 に置く」だけ（6 個に増やすと別ルートに負ける）。(b) 相手が肥料/小麦をこちらの 1 ターン前に売る → 同一農場で ±$5.3-5.7k が逆転。
- **中盤の現金化ルール**（Rayk C72）: プレミアム品を $2,000 相当以上持ち、かつ shed まで 1 手以内の hand だけ迂回して DROP+SELL。閾値 500/1000、2 手迂回は全て 0-8 で負け。「常時売る」は害。
- V29-R1（boatlee 最新）: 在庫圧力（shed+運搬+予定需要+公開在庫）が**複数ターン持続した時だけ**売却量を変える hysteresis、品目別 reserve を季節で漸減、価格ゲートで早期安売り禁止、両農場が近い形なら保守的経路に固定（ミラー同時大量売却の回避）、終盤は reserve 緩和→末尾清算。現行 top20 代表 12 シード × 両席で 196/216。

## 5. 労働・移動・実行の細部（静かに効く部分）

- hands の fib コストは 10 人で $143/日、**230 アクション**。Luka の最初のエージェントは unit-turn の 83% が移動（毎ターン目標再計算でスラッシング）→ 「今いるタイルの FEED/CARE/HARVEST/COLLECT を終えてから動く」で 55% に、最終資金 3 倍（[734412](https://www.kaggle.com/competitions/kaggriculture/discussion/734412)）。Georgy の 6 タイル 1 人ボットでも 33% 移動 + 16% PASS。**移動が半分を食うのが普通**。
- hands は day 0 に NW 以外の中央 4 タイルにスポーンする（1.32.3 以降は未購入地も歩ける）。
- PLANT は**作物ごとに合計要求数 > 所持種なら全員 PASS**（占有タイル上の要求もカウント）。複数ユニットで種を植えるとき静かに全滅する（Georgy §11）。
- HARVEST はユニット在庫へ、SELL は shed からのみ → **DROP を挟まないと当日中の売却資金にならない**（メロン IPO が資金にならず土地購入が遅れる典型バグ）。shed 100 個上限、夜に超過分は消滅。
- step 718 は実行される、index 719 は実行されない（Hamburger 発、Rayk c27 で終盤 controller を 712→717 にずらしただけで 90-10）。
- **メロン水やり d6-10 の優先度を CARE より上に**（下げると 96→70 個）。
- 雑草: 「全部抜く」は×。**予定作業（BUILD/PLANT/PLACE）を今塞いでいる雑草だけ DIG に置換し、1 ターン遅らせて次の PASS で吸収**（Rayk C92: −$7,288 敗 → +$3,455 勝に反転した例）。
- ファイルローダは**最後に束縛された callable**を agent として選ぶ。ヘルパー関数を最後に定義するとそれが呼ばれ 3,000 で終わる（Kaito v47 の 11 戦全 PASS 事故、Rayk §14）。

## 6. 評価手法（上位者が共通して守っていること）

- **目的関数は勝率 Pr[win]=Φ(μ/σ)、資金差ではない**。負けている時は分散を増やす方が期待値を増やすより効く（destbreso "Wins, not money"、[734412](https://www.kaggle.com/competitions/kaggriculture/discussion/734412)）。Rayk C70 は 83-5 で +$14k 平均でも sub-3000 で停滞：**既に勝っている相手の margin を増やしても rating は動かない**。
- **両席・同一シード・ペア比較**。市場は unit-by-unit 清算なので席で結果が反転しうる。標準誤差 2 倍を超え、かつ大半のシードが同方向で採用。
- **親世代と現王者を拒否権付き相手にし、無関係な公開ファミリーを 2 つ以上混ぜる**。Rayk の horizon 25 は「弱い過去世代への総合勝率」で親への回帰を隠していた（0-6 で判明）。→ **我々の「自系統 + starter のみ」評価は上位者が明示的に警告している落とし穴**（STATUS の指摘と一致）。
- 公開ノートを相手にする場合、**同じ SHA の tape が複数ノートに再掲されている**（Navaz/Tran と Hamburger anchor は同一 SHA）ので独立確認とみなさない。
- rating 側: 新提出は 600 から ~60 戦で 90% 収束、以後 a+b·ln(n)。50 点差はノイズ。再提出は無意味（[Ryo Hasegawa](https://www.kaggle.com/competitions/kaggriculture/discussion/736219)）。最終は締切後 2 週間の Bradley-Terry で再計算。

## 7. RL/BC の現状（参考、我々の方針には非推奨のまま）

- 上位は**ほぼ全員 rule-based/route-based**。BC/PPO 勢は 25-80k 止まり（[Zhenyu Zhang](https://www.kaggle.com/competitions/kaggriculture/discussion/738079)、[Mark Schatza PPO 80k](https://www.kaggle.com/competitions/kaggriculture/discussion/738619)、[dzjiann](https://www.kaggle.com/competitions/kaggriculture/discussion/736567)）。共通の教訓: 「実行層（経路・合法性・依存）を決定論に、モデルは高レベル選択だけ」でないと土地購入すら学ばない。

## 8. 我々への含意（Supervisor / Strategist 向け）

1. **$40-65k → $90k の差は「エンジン本数」で、公開知見と STATUS の結論が完全一致**: 上位は d6/d10 に土地 2 枚、d10 に hands 14、牛 8 + 羊 4-6、イチゴ 6-7 を**新規土地の上に**置く。我々は quad1・hands 7-8・土地 0。土地は現金でなく hands で決めるので、**BUY_LAND と HIRE 増員を同じ日に束ねる**のが正しい（片方だけだと Rayk C93 のように負ける）。
2. **d0 の羊 4 頭は最重要の未実装候補**。羊毛が d6 から現金源、CARE 4 倍、肥料 1/日。YARN が来ないシーズン（34%）でも羊毛は町センター 30 個 + glut 曲線で売れ、肥料収入は店に依存しない。
3. **肥料は集めた瞬間に売る**（d0 が最高値、町のドレイン 0）。既に動物を持つ我々にとって最も安い +$2-3k/頭。
4. **小麦自給への切替**（d11 以降、種 5-10/日）。cycle6 の −$6-8k の正体。
5. **売却は先手・小口**。プレミアム品の初売り日を 1-2 日早める方が、量を増やすより勝率に効く（イチゴ d14 vs d16）。ミラー戦の 1 ターン前倒し（総量保存）は実装コストが小さく、Track B 候補。
6. **評価の盲点対策は上位者の標準手続き**: STATUS の提案(a)「拡張型スパーリング相手」は Rayk/Kaito/boatlee 全員が「公開ファミリーを 2 つ以上、両席、拒否権付き」で実施している内容と同じ。相手を変えると店抽選が変わる点だけ注意（ペア比較は同じ相手同士で）。
7. **SE quadrant は触らない**。ニンジン hinge は「店が偏った時のみ d25 以降に少量」の限定戦術。
8. リスク: 9/1-9/2 以降、強エージェントが LB から意図的に引っ込められている。最終 2 週間の BT トーナメントで未見の型と当たる前提で、**固定ルートよりも公開状態（店・相手の農場形）で分岐する構造**が上位で一般化している（tetsutani 5 ルート、Kaito 6 ルート、yhay81 6 日ブロック、boatlee 近ミラー hysteresis）。

## 出典一覧

- Discussion: [736219 Ryo Hasegawa 提出戦略](https://www.kaggle.com/competitions/kaggriculture/discussion/736219) / [733431 Balance Changes](https://www.kaggle.com/competitions/kaggriculture/discussion/733431) / [735311 Small balance change](https://www.kaggle.com/competitions/kaggriculture/discussion/735311) / [732450 Docs vs Engine](https://www.kaggle.com/competitions/kaggriculture/discussion/732450) / [734212 Kaito: How I Keep Iterating](https://www.kaggle.com/competitions/kaggriculture/discussion/734212) / [738079 BC の教訓](https://www.kaggle.com/competitions/kaggriculture/discussion/738079) / [736567 End-to-End RL](https://www.kaggle.com/competitions/kaggriculture/discussion/736567) / [731215 Daily Top Episodes Dataset](https://www.kaggle.com/competitions/kaggriculture/discussion/731215) / [734412 価格表は逆順](https://www.kaggle.com/competitions/kaggriculture/discussion/734412) / [734308 4th quadrant](https://www.kaggle.com/competitions/kaggriculture/discussion/734308) / [737736 価格曲線実測](https://www.kaggle.com/competitions/kaggriculture/discussion/737736) / [738619 PPO 80k](https://www.kaggle.com/competitions/kaggriculture/discussion/738619) / [733173 opponent-agnostic optimum](https://www.kaggle.com/competitions/kaggriculture/discussion/733173) / [739179 強エージェントの退場](https://www.kaggle.com/competitions/kaggriculture/discussion/739179)
- Notebook: [raykkretzschmar/findings-from-zero-to-top-meta](https://www.kaggle.com/code/raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta) / [boatlee/v16-rc5](https://www.kaggle.com/code/boatlee/v16-rc5-high-score-8c-4s-premium-market-lead) / [boatlee/v29-r1](https://www.kaggle.com/code/boatlee/v29-r1-adaptive-market-hysteresis) / [kaitofukami/v48](https://www.kaggle.com/code/kaitofukami/40-40-early-floor-39-46-top-10-v48-fast-routes) / [cjlcjlcjl/live-meta](https://www.kaggle.com/code/cjlcjlcjl/kaggriculture-what-the-top-farms-do-a-live-meta) / [georgymamarin/visualized](https://www.kaggle.com/code/georgymamarin/kaggriculture-visualized-what-every-crop-pays) / [tetsutani/adaptive-farming-strategy](https://www.kaggle.com/code/tetsutani/adaptive-farming-strategy-for-kaggriculture) / [tetsutani/shape-the-shop](https://www.kaggle.com/code/tetsutani/shape-the-shop-work-the-pasture-kaggriculture) / [pilkwang/structured-economic-policy](https://www.kaggle.com/code/pilkwang/kaggriculture-structured-economic-policy) / [yhay81/six-day-fieldbook](https://www.kaggle.com/code/yhay81/six-day-public-state-fieldbook) / [prvsiyan/the-moon-counts-melons](https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-moon-counts-melons)
- データセット: [kaggle/kaggriculture-episodes-index](https://www.kaggle.com/datasets/kaggle/kaggriculture-episodes-index)（公式デイリー上位リプレイ）、[georgymamarin/kaggriculture-episodes](https://www.kaggle.com/datasets/georgymamarin/kaggriculture-episodes)
