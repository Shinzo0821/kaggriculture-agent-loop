---
status: done   # in_progress | done。評価を回し始めたら in_progress で先にコミットする
gen: gen0056
parent: gen0051
---

# EXP0056: 相手適応型の乳エクスポージャ（乳の洪水を検知して cow 8→6 + バンクゲート即時解除）

- 日付: 2026-09-13（eval 完走・レビュー 2026-09-14）／ 世代: gen0056（親: gen0051＝現王者）
- 仮説: 王者 gen0051 は rating 4σ 上だが `money_delta_paired −243.4`・`slope_delta −331.1` の「相手を削るが自分は伸びない」型（主題＝自資金と slope の回復）。EXP0055 の棄却（卵＝非競合小市場は差の源泉でない）と Analyst の上位 #1 解剖（Majkel1337 も**共有市場で denial-positive に勝つ**）から、自資金を上げる正解は「相手適応の production で共有市場を取る」と見立てた。単一レバー = 「乳の洪水型」（相手が乳の設置牛を積み共有乳市場が床に張り付く）を検知し、発火時だけ (a) `cow_target 8→6` と (b) 乳の収穫バンクゲート即時解除を行う。洪水相手では乳価が `SELL_FLOORS[MILK]=96` に戻らず、乳が牛上に `max_held−1` まで滞留して d28 強制収穫で深い glut にダンプされる穴を、**総量不変の前倒しダンプ**に変える想定。IDEA_POLICY §2（未使用の観測 `obs[farms][opp]` 牛数・`minv[MILK]` の利用）＋§1。
- 変更: gen0051 のコピー＋ `milk_flood()` 新設と真偽の配線 6 hunk のみ（詳細 `agents/gen0056/meta.json` の `changes`／`mechanisms`）。
  - `milk_flood(farms, player, prices, minv)` = **連言**: (1) 相手農場の設置 COW 数 ≥ `FLOOD_COW_HERD=6` AND (2) 共有乳市場が床（`prices[MILK] ≤ 96` かつ `minv[MILK] ≥ I0`）。
  - `cow_target(day, flooded)`: `return 6 if flooded else 8`（d0-7 ランプ不変）。
  - バンクゲート: `if milk_flooded and prod == "MILK": unlock = True`。
  - 設計上の主張: 非洪水（starter/georgy=相手牛0・kaito/rayk=牛多いが市場が床にならない）では全分岐が閉じ gen0051 とバイト同一。**→ 検証で偽と判明（下記）。**
- 結果（`records/eval_gen0056.json`・50 シード・12 体プール `6e07bb6a`・baseline `records/eval_gen0051.json`）:
  - `gate.pass = True`（`pass_route = margin`）
  - 対応付きマージン差 **+136.9 [+55.0, +218.7]**
  - rating_delta +9.1 [−40.1, +58.3]（pool.rating 683 相当）
  - **対応付き自資金差 −244.2 [−376.9, −111.5]**（主題の逆・CI 上限 < 0）
  - slope_delta −45.8
  - **強帯マージン差 +131.2 [+11.4, +251.0]** ／ 強帯自資金差 **−188.9 [−354.7, −23.2]**
  - 相手別: 中帯 gen0044 勝率 69→71%（自資金 −760）・gen0045 77→80%（自資金 −659）。強帯は全相手 0% のまま、差は ±$800 以内。
- **判定**: **昇格ゲート通過・昇格は推奨しない（人の判断に委ねる）** — `指標: pool(v0.6 margin) ／ シード: 50 ／ CI: [+55.0, +218.7]`（強帯マージン CI [+11.4, +251.0]、自資金 CI [−376.9, −111.5]）。
  理由: (1) 規約「マージンで勝っていても自分の絶対額が下がる型は避ける」に、全体・強帯とも CI で抵触。(2) 主題（DIRECTIVES 2026-09-10「自資金と slope を戻す」）の逆方向で、gen0051 の相手削り型をさらに深める。(3) 設計の中心主張（非発火時の同一性・総量不変の前倒し）が実装と eval で偽と確認された（レビュー記録）。昇格すると「なぜ効いたか」を説明できない機構を王者系譜に入れることになる。
- **説明（この分野を知らない人向け 3 行）**: 相手が牛を多く飼って牛乳市場が値崩れしている時だけ、牛乳を溜めずに即売りする切替を入れた。対戦全体の勝ち幅（自分−相手）は少し広がったが、自分の手元に残るお金は減った。「値崩れは相手のせい」と見分けるつもりの条件が、実は自分の安売りでも成り立ってしまい、狙った相手以外のほとんどの対戦で切替が起きていた。
- **改善幅は seed ブレより大きいか**: マージンは CI 下限 +55.0 > 0 で yes。**自資金は CI 上限 −111.5 < 0 で、悪化の方が seed ブレより大きい。**
- **目標曲線との差**: 未測定（replay 単位の `audit_replay.py --targets` はしていない）。gap_LATEST（王者 gen0051 vs boatlee_v29）は d10 $1,032 vs 上位 $15,106 で d10 から遅れる。gen0056 は d15 以降の乳の扱いしか変えないので、d10 の遅れには効かない。
- **ミクロ指標**（`harness/micro_audit.py --assert`。基準 `control/targets.json` の `micro`）:
  - critical-three（noop_total / unfed_days / uncared_days）: vs starter s42・vs boatlee_v29 s42 とも全 0 = OK。
  - vs starter s42: `tile_util 0.698`・`wheat_yield 3.88`・`melon_yield 5.812`・`strawberry_yield 1.887`・`inplace_share 0.407`・`last_water_hour 23`・`moves3plus 0.131`。NG 集合は FIX0013 強帯目標（--limit 対象）で gen0051 と同一（starter は相手牛 0 なので実際にバイト同一）。
- **レビュー記録**（2026-09-14・Codex gpt-5.6-sol / high・thread `<redacted-id>…`。機械記録は `agents/gen0056/meta.json` の `review`）:
  - fatal なし。例外パス・`obs[farms][opp]` の読み（player 反転・None/空）・1 秒制約（最大 0.0087 秒）・終盤清算は問題なし。
  - [P1・確認済み] 連言は床が相手由来であることを保証しない。Claude の対応付け検証で親と完全一致は starter/georgy 100/100 のみ、kaito 35・rayk 33・gen0044 35・gen0045 32・boatlee_v29 24/100。→ **deferred / FIX0021**。
  - [P1・経路は確認・因果は未分解] 即時解除の HARVEST が全品目共通の作業キューと競合し、shed に移った乳が `shed_pressure`（≥78 で全品目ダンプ）を押し上げる。自資金の悪化と整合。→ **deferred / FIX0022**。
  - [P1→minor・確認済み] ヒステリシスなし（cow_target 6↔8 往復）。現プールでは発火時に既に 8 頭なので実害は小。→ **deferred / FIX0023**。
  - [P2] `FLOOD_COW_HERD=6` の出所は derived ではない。→ FIX0021 に併記。
  - 昇格しないので修正世代は作っていない。gen0056 を親にする世代を作るなら、この 3 件を先に直す。
- **却下した小手先案**:
  - `乳の売却ルーティング（店条件付き販売先切替）` / 前提（gap の乳 −$9,011・床値 116 個）が測定アーティファクト（2026-09-10 分析で棄却済み）。`knowledge/analysis/2026-09-13_gen0056-lever-reconciliation.md`。
  - `SELL_FLOORS[MILK] の微調整で早売り` / IDEA_POLICY §禁止1（閾値・定数の ±微調整）。
  - `cow_target を常時 6 に下げる` / IDEA_POLICY §禁止（「常時○○」型）。
  - `FLOOD_COW_HERD を 5/7/8 に振って非発火同一を回復` / IDEA_POLICY §禁止1（単一パラメータ sweep）。原因判定は状態量の閾値では作れない（FIX0021）。
- 学び:
  - **共有市場の状態量（価格・在庫）からは「誰が床に落としたか」が分からない。** 相手の能力（牛の頭数）を足しても原因にはならない。相手起因を判定するには、相手の yield 減少と市場在庫増を同時に見る**履歴信号**が要る。
  - **「非発火時は親とバイト同一」は主張ではなく測定で確かめる。** eval の (相手, seed, 席) 対応で完全一致率を出せば数秒で分かる。今回はスモーク 2 本（starter と boatlee）しか見ておらず、中間の相手を見落とした。次から新しい条件分岐を入れた世代では、相手ごとの一致率を EXP に書く。
  - 乳の前倒し売りは、マージン（denial）と自資金をトレードする。gen0051 → gen0056 で「相手を削るが自分は伸びない」が 2 世代続いた。主題を進めるのは乳の扱いではなく、d10 までの資金形成（gap §4-1）の側にある。
