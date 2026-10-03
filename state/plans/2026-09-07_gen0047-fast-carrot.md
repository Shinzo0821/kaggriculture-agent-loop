# gen0047 実装設計書 — 終盤 fast-carrot ローテーション（decay 済みイチゴタイル → CARROT）

- 作成: 2026-09-07 ／ Strategist（設計のみ。実装は Implementer）
- 親世代: **gen0046**（gen0045 + FIX0018。observed trajectory では gen0045 とバイト同一の latent 修正版。
  meta.json `leak_check` で全 719 ターン diff=0 を確認済み）
- 出所: `knowledge/scout/2026-09-07_next-structural-lever.md` 提案1（本命）。提案2（shop 依存 size）は今回**実装しない**（§6）。
- 裏付けリプレイ: `replays/top/episode-106191684-replay.json` ／ `replays/top/episode-106190768-replay.json`
  （LB #1 我都先道歉の両席勝ち）。対照: `knowledge/analysis/2026-09-07_ep106190289-blowout.md` 修正候補2/3。

---

## 0. 前提の裏取り（設計の成立条件。Strategist が README・エンジン実装で確認済み）

1. **carrot は d26-27 植えで d29 収穫に間に合う** — README 作物表 L14: CARROT one-time / 種$20 / base$35 /
   **Time to First Yield 2 日** / Time to Max Yield 3 日 / Max Yield 4（**無肥料 3**）。
   - d26 植え → d29 に age3（max yield 日）。水やり age2(d28)+age3(d29) で **3 個**。
   - d27 植え → d29 に age2（first yield）。水やり age2(d29) で **2 個**。← 間に合う最終日
   - d28 植え → age2 が d30 ＝存在しない。**植付は d27 で打ち切りが必須**。
   - ボーナス窓（README L123: `ceil(max_yield_day/2)` から）= **age 2〜3**。水やり 1 回 +1、開始収量 1。
   - decay: 一時作物は `max_lifespan_step = (planted+max_yield_day+1)*24`（エンジン L224）→ carrot は
     **age4 から目減り**。age3 で刈るのが正。
2. **decay 済みイチゴは engine が WEED にする** — ongoing は累積 4 産で `max_lifespan_step=(next_day+1)*24`
   （エンジン L800-802）→ 翌日から 2 step ごとに yield_units−1、0 で `{"kind":"WEED"}`（L762-765）。
   イチゴ植付日 P に対し **WEED 化 ≈ P+17**。うちの骨格（CROP_PLANS）では:
   - NE 波（from_day 8, 10 枚）→ **WEED d25-26**
   - SW 波 +(9,1)（from_day 10, 17 枚）→ **WEED d27-28**（d11-13 植えのぶんは d28+ ＝転作対象外でよい。
     それらは d28-29 までイチゴを産み続けるので遊休ではない）
   - 早出し 2 枚（from_day 4）→ WEED ~d21。**これは今回の対象から外す**（§2 タイル集合の注記）。
3. **上位実測（Scout 表を本設計でスポットチェック再計測、一致確認済み）** — ep106191684:
   #1(P0) の CARROT/WEED = d24 3/1・**d26 17/0・d27 23/0**・d28 11/2・d29 7/2。
   #2(P1) = d26 5/12・**d28 11/18・d29 5/18**。ep106190768 も同傾向（#1 d24 開始・終盤 WEED 0-2、
   #2 は d28-29 に WEED 13）。**勝者は decay タイルを即 carrot 化して終盤 WEED≈0、敗者は 12-18 枚を $0 で放置**。
4. **gen0045/0046 に carrot は無い** — CROP_PLANS は MELON/STRAWBERRY/WHEAT のみ（L250-291）。CARROT は
   `ALWAYS_SELL`（L375）と `BASE_VALUE`（L294）に既在だが在庫が発生しないので死にコード。イチゴタイルの
   WEED は d26 以降 DIG する経路が無く（計画 DIG は窓が開いている時のみ L777、fallback は d≤25 のみ L786）、
   **敗者側と同じ「終盤 WEED 放置」になっている**。

---

## 1. 仮説（なぜマージンが上がるか）

**decay して $0 になったイチゴタイル（10〜17 枚）を d24-27 に DIG→CARROT 化すると、d27-29 に
carrot 2-3 個/枚 × base $35 が純増する。転作対象は「4 産を終えて engine が WEED 化したタイルのみ」
なので、我々のイチゴ供給は 1 個も減らず（HANDOFF 原理3「供給を減らす変更は贈り物」に抵触しない）、
失うのは carrot 種 $20/枚と層 2-5 の余剰 labor だけ。worst case は「carrot todo が消化されず WEED の
まま」＝ gen0046 と同一 ＝ 下振れ 0 のオプション構造（gen0045 funded-wool と同型）。**

- IDEA_POLICY 該当: **§1 日次骨格の変更**（作付け計画に CARROT 窓を追加し終盤の型を変える）＋
  **§5 上位公開実装の欠陥を突く差別化**（LB #1 が両席で再現する実挙動を取り込み、我々自身と
  スパーリング相手の「終盤タイル放置」の穴を塞ぐ）。
- 期待金額（正直な見積り）: 自産ぶん NE 10 枚 ×3 個 + SW 早期 decay ぶん ~5 枚 ×2 個 ≈ 40 個 ×
  $25-35（glut 込み）− 種 ~$300 ≈ **+$700〜1,400/試合**。carrot hinge（below_target 1.00, T=450, max $70）が
  26% の試合で発火すれば上振れ。Scout の $2-4k は「敗者側 WEED 18 枚」を含む相対スイングで、
  相手が既に carrot をやる強帯では我々の自産ぶんに縮む。**昇格判定の想定は gen0045 の +$854 と同スケール
  （全体マージン +$500〜1,500）**。

---

## 2. 発火条件と実装仕様（gen0046 → gen0047 の差分。全て `agents/gen0047/main.py` 1 ファイル）

### 2-1. CROP_PLANS に "CARROT" を追加（L250-291 領域、~30 行）

```python
"CARROT": {
    # 終盤ローテ: 4産を終えて decay したイチゴタイルだけを転作する。
    # タイル集合 = STRAWBERRY 計画から早出し2枚 (0,3)(0,4) を除いた 25 枚（NE 5-9行0-1 + SW 0-4行6-8 + (9,1)）。
    # 早出し2枚は d21 に WEED 化して fallback 小麦サイクル（d21植え→d25収穫）が既に回収して
    # いるので対象外（含めると reserved 化で d21-23 の fallback を止め、非発火同一性が壊れる。§4）。
    "tiles": [(x, y, 24) for (x, y) は上記 25 座標],   # from_day は一律 24
    "windows": [(24, 27)],
    "plant_pri": 2.82,   # WHEAT 計画 2.80 の後・fallback 2.85 の前（既存帯に挿すだけ。層4のまま）
    "water_pri": 3.02, "seed_cost": 20, "buy_cap": 12,
    "last_plant_day": 27,   # 新キー（2-2）。d27 植えが d29 収穫の限界（§0-1）
},
```

**decay 済み判定に age や収穫回数の閾値は使わない。** engine 自身が「4 産完了 or 枯死」の時だけタイルを
WEED にする（§0-2）ので、**「kind=WEED または None のタイルにしか触らない」ことがそのまま
『decay 済みのみ』の機械保証**になる。生きているイチゴ（kind=PLANT）は植付スケジューラが素通りする
（既存 L771-779 の構造のまま）。

### 2-2. 植付スケジューラの per-crop 植付期限（L759-779、~6 行）

- `plant_slots` 初期化 dict に `"CARROT": 0` を追加（L760）。
- L763-767 を `lpd = plan.get("last_plant_day", LAST_PLANT_DAY)` で一般化:
  `w_open = day <= lpd and bool(open_w)` ／ `window_end[crop] = min(max(b...), lpd)`。
  **MELON/STRAWBERRY/WHEAT はキー無し → 既定 25 のまま＝挙動不変。** グローバル `LAST_PLANT_DAY` 自体は
  触らない（±1 微調整ではなく carrot 専用の期限追加）。
- L777 の「計画タイル上の WEED を DIG」は carrot 窓 (24,27) が開くと自動で発火する（既存コードのまま）。
  DIG(2.6) → 翌ターン None → PLANT CARROT(2.82) → 既存 WATER 機構、の 3 手が既存 todo スケジューラに載る。

### 2-3. carrot の種購入（L1358、1 行 + WEED 先読み ~3 行）

- 種購入ループのタプルを `("MELON", "STRAWBERRY", "WHEAT", "CARROT")` に（優先は最後）。
  数量・資金は既存の generic 機構（`plant_slots`×窓キャップ、`RESERVE=400` ゲート、`buy_cap`）が使える。
- **WEED タイルの先読み**: 既存の `plant_slots` は t is None のタイルしか数えないので、DIG →（翌ターン）
  slots 加算 → 種購入 → 翌々ターン植付、と 2 ターン遅れる（＝open の FIX0008 そのもの）。carrot 窓が
  開いている間だけ、carrot 計画タイル上の WEED も `plant_slots["CARROT"]` に数える（L777 の分岐に 1 行）。
  **carrot スコープに限定して FIX0008 を部分適用**する（他作物の fallback には触れない。FIX0008 は open の
  まま台帳に残し、EXP0047 に部分適用の旨を書く）。

### 2-4. 収穫の carrot 分岐（L595-597、~3 行）と定数 2 つ

- L592 の elif 連鎖に追加:
  `elif crop == "CARROT": ripe = age >= 3 or (day >= FINAL_DAY and age >= 2); hpri, wpri = 2.2, 3.02`
  - age3（max yield 日）で刈る。age4 から decay（§0-1）なので放置しない。
  - d27 植えの株は d29(FINAL_DAY) に age2 で刈る（このときの水やりは既存 `water_first` 機構が
    WATER→HARVEST の順に並べる。bonus 窓 age2 なので +1 が乗ってから刈れる）。
- `BONUS_WINDOW["CARROT"] = (2, 3)`・`MAX_YIELD["CARROT"] = 3`（L304-305。無肥料上限。施肥は今回
  スコープ外: FERTILIZER は ALWAYS_SELL で即売しており終盤在庫が無い。効けば次世代で検討）。

### 2-5. 売却・換金は**既存機構そのまま（変更 0 行）**

- CARROT は既に `ALWAYS_SELL`（L375）・`BASE_VALUE=35`（L294）に載っている。収穫 → 手持ち → daily reset
  でシェッド帰着 or FINAL_DAY の DROP(2.1) → 市場 SELL、はイチゴの d29 産と同じ経路。
- 市場: carrot は hinge（below_target 1.00, T=450）× above sqrt 0.70。売却 ~40 個は T=450 に対し小さく、
  base 近辺で捌ける想定。売り時ロジック（BETA_SELL）には**載せない**（WOOL/MELON の β 解法は glut 市場の
  持ち越し装置。carrot は d27-29 の即売品目で持ち越す夜が無い）。

### 2-6. meta.json

- `parent: "gen0046"`、mechanisms に `fast_carrot_rotation`（constants: 窓 (24,27)・last_plant_day 27・
  タイル 25 座標・plant_pri 2.82、origin: "observed"（LB #1 両席の実測）、ablation:
  `records/eval_gen0046.json`（出ていなければ `records/eval_gen0045.json`））。
- `leak_check` 欄: §4 の非発火同一性テストの結果を gen0046 と同形式で記録する。

---

## 3. 下振れ 0 の設計（機械保証。funded-wool と同じ思想）

| リスク | 機械保証 |
| --- | --- |
| イチゴ供給を減らす（贈り物） | 触るのは kind=WEED / None のみ。生きた PLANT は構造上触れない（§2-1）。engine が WEED 化の唯一の判定者 |
| feed/care/緊急水やりを削る | carrot の todo は全て層 2-5（DIG 2.6・PLANT 2.82・WATER 3.02/1.0/≈2.19）。層 0-1（緊急給餌 0.0 / FEED 0.9 / CARE 0.95 / 枯死防止 WATER 1.0）は割当ループが**常に先に**消化する（LAYER_BOUNDS は不変）。unfed/uncared は carrot todo の量に依存しない |
| melon 収穫を食う | メロンは d20-22 に収穫済み（第2波 d10-12 植え・age10）。carrot 窓 d24-27 と重ならない。d24+ に残る層 2 はイチゴ d13 植えの収穫・施肥対のみで、carrot の層 2 参加は water_first（自タイルの WATER→HARVEST 対）だけ |
| 労働が足りない seed | worst case = carrot todo が starve して WEED のまま ＝ gen0046 と同一。**失敗モードが「現状維持」に閉じる** |
| 資金 | 種 $20×≤12/ターン、RESERVE=400 ゲート既存。終盤資金 $30k+ に対し誤差 |
| 確定枯れ植付 | 既存 LAST_PLANT_HOUR=20 ゲートが carrot にもかかる。d28 以降の植付は last_plant_day=27 で構造的に不能 |
| 植えた carrot の water 忘れ | consecutive_unwatered>=1 → 既存の枯死防止 WATER(1.0, 層1) が拾う |

**手順**: 実装後スモークで `harness/micro_audit.py <replay> --assert` の **unfed_days / uncared_days /
noop_total = 0 を確認してから**評価キューに積む（gen0040 の教訓・CLAUDE.md 絶対ルール）。

---

## 4. gen0046 との差分規模と非発火同一性

- **差分: 1 ファイル・5 箇所・約 35-45 行**（CROP_PLANS 追加 ~30・スケジューラ一般化 ~6・種購入 ~4・
  収穫分岐 ~3・定数 2）。`ops/check_fixes.py agents/gen0047/main.py --show-open` で FIX0018 の継承
  （applied 12/12・回帰 0）を必ず確認する。
- **非発火バイト同一性**（機械検証は gen0046 の `leak_check` と同じ obs 軌跡 diff 方式）:
  - **d0-18: 常に同一**。carrot の窓 (24,27)・from_day 24 に対し fallback の reserved 判定は
    `start(24) <= day+5` ⇔ day≥19 で初めて真になる。それ以前は reserved・todo・種購入とも差が出ない。
  - **d19-25: ほぼ同一**。carrot 計画タイルが reserved に入るが、生きたイチゴ（kind=PLANT）は fallback が
    元々 skip するので通常 seed では差 0。**差が出るのは「イチゴが水切れ等で d24 より前に死んだ」稀な
    seed のみ**（gen0046: fallback 小麦を植える ／ gen0047: d24 の carrot まで温存。経済価値は同程度、
    $100 小麦 vs $105 carrot+hinge 上振れ）。早出し 2 枚を対象から外したのはこの差を「稀な seed」に
    閉じ込めるため（含めると大半の seed で d21-23 の fallback 小麦が止まる）。
  - **d24-29: 発火域**（これがレバー本体）。
  - leak_check は d0-23 の diff=0（通常 seed）と、早期枯死 seed での差分内容の目視確認を記録する。

---

## 5. 判定計画

- **手順**: スモーク（seed 7/14/42、micro_audit --assert 3 点 0 確認）→ 方向 24 seeds → 昇格 50 seeds
  （検出限界ドキュメント遵守。スモークの数字で改善を語らない）。
- **baseline**: `records/eval_gen0046.json`（GATE_PENDING_EVAL。出ればそれ。gen0046 は observed
  trajectory で gen0045 と同一挙動なのでマージン≈0 が正しい）。出ていなければ `records/eval_gen0045.json`。
  王者ベースラインの規約上、preflight/gate は現王者 gen0045 比で判定される点に注意。
- **見る数字**:
  - 全体 `margin_delta_paired` CI 下限 > 0（gate.pass）。想定 +$500〜1,500。
  - **強帯 `strong_margin_delta_paired` 点推定 ≥ 0 必須**（2026-09-06 規約。CI またぎは検出不能で棄却しない）。
    強帯相手は自分も carrot を売る可能性があり共有市場で薄まる → 点推定が全体より小さくても負でなければ前進。
  - 診断: `money_delta_paired`（自分の絶対額が下がっていないこと）・slope（d24-29 の傾き改善が出るはず）。
- **ミクロ検証**（発火の実在確認。マクロが動かなくてもここで機構の生死を判定できる）:
  - 発火 seed のリプレイで d26-29 の自陣 WEED 枚数（目標: gen0046 の実測比で大幅減、LB #1 並みの 0-2）。
  - carrot 収穫個数/枚（目標 ≥2.5 on d25-26 植え、d27 植えは 2）。植付日分布（d28 植えが 1 件でもあればバグ）。
  - unfed/uncared/noop = 0、last_water_hour・イチゴ収量が gen0046 と同値（供給非減の実証）。
- **反証条件**: 24 seeds で全体マージン点推定が負、または carrot 植付がほぼ発火しない（イチゴ WEED 化が
  想定より遅い）なら、窓・タイル集合を疑う前に **リプレイで実際の WEED 化日を測る**（仮説より指標・実測が先）。

## 6. 却下した小手先案・再提案しない CLOSED 系統

| 案 | 扱い |
| --- | --- |
| 提案2: PET_CAFE/FARMERS_MARKET の抽選で carrot 枚数を変える | **却下ではなく順序付けで先送り**（Scout 明記）。まず提案1 を shop 非依存で 24 seeds 測り、効いたら §2（未使用観測）として別世代で条件化。先に入れると効果の帰属が割れる。町抽選は空きタイル数に依存（`2026-09-06_town-draw-depends-on-empty-tiles.md`）し、carrot 転作自体が空きタイルを変える二次効果もあるため分離必須 |
| `FALLBACK_CROP` を終盤 carrot に切替（常時 carrot 埋め） | 却下 / IDEA_POLICY 禁止 §5「常時○○」型。本設計は窓＋タイル状態ゲートの条件付き機構 |
| `LAST_PLANT_DAY` 25→26 の単独変更 | 却下 / 禁止 §1（±微調整）・§4（単一パラメータ）。per-crop `last_plant_day` は骨格追加の一部であり sweep しない |
| carrot の施肥（max 3→4） | 先送り（却下ではない）。FERTILIZER は即売しており在庫ゼロ。売却抑制まで触るとスコープが割れる |
| 再提案しない CLOSED 系統 | イチゴ増産（EXP0035/0043・市場律速）／土地追加（EXP0023/0027・検出不能）／動物増（EXP0029/0037/0040・棄却）／労働量増（EXP0028/0038/0039・確定棄却）。本設計は「終盤の遊休タイル回収＝労働の質」系譜（gen0026/0032/0036 と同カテゴリ）で、上のどれとも独立 |

## 7. 落とし穴（実装・検証時に必ず見る）

1. **d29 に間に合わない seed**: 植付が d27 h20 を過ぎたら植えない（既存ゲート）。d27 植えは 2 個止まりで
   期待値が半減する — 発火タイルの植付日分布を micro で確認し、d27 比率が高すぎるなら「WEED 化が
   d27 に集中している」証拠なので、SW 波のイチゴ植付を早める案（別世代・骨格変更）に接続する。
2. **melon/イチゴ labor との競合**: 層構造で保護済み（§3）だが、funded-wool 発火 seed（羊 8 頭 + SE）では
   d24-29 の hand-hour が最もタイトになる。発火×発火の seed を micro_audit で個別確認（noop=0・
   last_water_hour 劣化なし）。
3. **WEED 化タイルの water 忘れ → 二度目の WEED**: 枯死防止 WATER(1.0) が拾う設計だが、リプレイで
   carrot タイルの consecutive_unwatered ≥2 由来の WEED 化が 0 件であることを確認する。
4. **carrot glut**: 両者が d28-29 に carrot をダンプすると sqrt 0.70 側で価格が落ちる（100 個の純増で
   ≈$23）。代替が $0(WEED) なので下方リスクは限定的だが、**強帯マージンが全体より大きく劣る場合は
   共有市場の薄まりを疑う**（→ 提案2 の需要条件化 or 早出し優先の検討材料）。
5. **d28-29 の WEED DIG は無駄手**: carrot 窓が d27 で閉じるので新たな DIG は出ない（既存構造で保証）。
   d28+ に WEED が残るのは仕様（そこからの回収手段は存在しない）。
6. **収穫→換金の取り落とし**: d29 収穫ぶんは DROP(2.1)→SELL が LAST_ACTION_HOUR=22 に間に合う必要。
   イチゴ d29 産と同じ既存経路だが、carrot 収穫が増えるぶん FINAL_DAY の手数を micro（最終時刻の
   noop/取り残し在庫）で確認する。
