# FIXES — 世代から独立した修正台帳

**なぜ要るか。** 世代は不変で、新世代は親の `main.py` をコピーして作る。だから**非昇格に終わった
世代に入れた修正は、次の世代の親がその世代でなければ消える**。実際 gen0023 の codex fix2
（移動中 hand による在庫の幽霊予約）は gen0023 が非昇格で gen0024 の親が gen0022 だったため
王者系統に伝わらず、**13 世代あとの gen0034 レビューで同じ指摘を受けた**
（`knowledge/experiments/EXP0036_zone-and-reservation-cleanup.md`）。
世代の系統樹から独立した台帳を置き、新世代を作るたびに機械照合する。

- 機械可読の正は **`control/fixes.json`**。このファイルは人が読む版で、**ID は必ず両方に存在させる**
  （`ops/check_fixes.py` が片方だけの更新を検出して落とす）。
- 検査: `.venv/bin/python ops/check_fixes.py agents/genNNNN/main.py [--show-open]`
- 網羅検査: `.venv/bin/python ops/check_fixes.py --audit`
  （`agents/*/meta.json` の `resolution` が `fixed…` でない指摘が、台帳に載っているか）

## 運用

1. **新世代を作ったら必ず `ops/check_fixes.py agents/genNNNN/main.py` を通す。**
   `status: applied` が検出できなければ**回帰**なので、評価に回す前に直す。
2. **新世代の仮説を立てるとき `--show-open` を見る。** `status: open` は「既に指摘済みで、まだ
   直っていない穴」。新機能より安い前進であることが多い（特に severity: major）。
3. **Codex レビューで `resolution: deferred` にした指摘は、その場で台帳に足す。**
   足さないと `--audit` が未登録として落とす。`sources` は `genNNNN#<findings のインデックス>`。
4. **直したら `status` を `applied` にし、`applied_since` と `detect` を書く。**
   `detect` が無い `applied` は台帳の読み込み時点で弾かれる（検証されないまま OK を返さないため）。
   判定の順序は **forbid → require → marker**:
   - `forbid` にマッチしたら未適用（marker では覆せない）
   - `require` があるなら**すべてマッチして初めて適用済み**。`marker` だけでは通らない
     （コメントを写して実装を戻した世代を通してしまうため）。リファクタで正規表現が外れたら、
     台帳の正規表現も同時に直す
   - `require` が無い項目だけ `marker`（`main.py` に `# FIX0001` のように ID を残す）で判定する
5. **直さないと決めたら `wontfix` にして `why` に理由を書く。** 消さない（同じ指摘が再来するため）。

新世代の `main.py` には、台帳に載っている修正の該当箇所に **`# FIX0001` のようなマーカーを残す**。
コードを読む人に「これは台帳の項目で、消すと回帰になる」と伝わる。ただし**マーカーは
`require` を持つ項目の判定を通す力を持たない**（上の 4）。判定はあくまで本文の照合で行う。

## 一覧（2026-09-06 初版）

| ID | 状態 | 重さ | 内容 |
| --- | --- | --- | --- |
| FIX0001 | applied (gen0036) | major | 移動中 hand による在庫の幽霊予約（ZWHEAT / ZFERT） |
| FIX0002 | applied (gen0036) | major | ゾーンの重み分割がクアドラント境界で切れない |
| FIX0003 | applied (gen0041) | major | 終盤清算の漏れ（最終ターンの DROP が SELL 数に反映されない） |
| FIX0004 | applied (gen0042) | major | 移動中ユニットによる `planned_seed` の幽霊予約 |
| FIX0005 | applied (gen0042) | major | farmer と所有者 hand が互いを止めて両方 PASS |
| FIX0006 | applied (gen0043) | major | 窓の中の WATER が HARVEST より前／生産日の水＋肥料ペアの取りこぼし |
| FIX0007 | open | minor | 施肥ゾーンの所有者が未雇用だと肥料が取り出せない |
| FIX0008 | open | minor | fallback 地の DIG と同ターンに種を買えず植付が 1 ターン遅れる |
| FIX0009 | applied (gen0044) | minor | 小口 SELL が 1 ターン 10 件の市場枠を食って HIRE / BUY_SEED を押し出す |
| FIX0010 | open | minor | シェッド一括 PICKUP の比較キーが層空間になっていない |
| FIX0011 | applied (gen0041) | minor | 最終ターンの COLLECT_FERTILIZER で換金できない肥料 1 個が残る |
| FIX0012 | open | minor | `DAILY_TILE_OPS` の説明が厳密でない（コメントのみ） |
| FIX0013 | open | minor | `control/targets.json` の micro 基準は導出ではなく強帯の実測 |
| FIX0019 | applied (gen0050) | minor | 最終日 d29 に carrot の bonus WATER が出ず想定収量が 1 個/枚不足 |
| FIX0020 | applied (gen0050) | major | 最終日収穫の carrot がシェッドへ戻れず未換金・carried 在庫を売却可能量に数える幽霊 SELL |

（FIX0014〜FIX0018 の行は下の詳細節を参照。表は FIX0001〜0013 の初版分のみ掲載。FIX0019/0020 は gen0048 の Codex レビューで検出し **gen0050 で同時解決**。詳細は下節 ＋ `control/fixes.json`。）

## 詳細

### FIX0001 — 移動中の hand による在庫の幽霊予約（ZWHEAT / ZFERT）

シェッドへ歩いている hand が `shed_wheat_free` / `shed_fert_free` を減らすため、既にシェッド上に
いる後続 hand が実在庫を積めない。歩行中の予約は次ターンに持ち越されないので純粋な取りこぼし。
在庫の減算を `if (ux, uy) == (x, y):`（今ターン実際に PICKUP する hand）で囲む。
gen0023 → 消失 → gen0034 で再指摘 → **gen0036 で再適用**。この台帳を作った直接の原因。

### FIX0002 — ゾーンの重み分割がクアドラント境界で切れない

ソート済み items を通しで累積して切るため、NE の末尾と SW の先頭が同じゾーンになる（実測で最遠
14 歩）。3 クアドラントで初めて顕在化した。隣接する同クアドラントの区間を `groups` にまとめ、
最大剰余法でゾーン本数を配ってから group 内で切る。**gen0036 で適用**。
土地を増やす世代を作るときは必ず確認すること。

### FIX0003 — 終盤清算の漏れ（applied gen0041, major）

最終行動は step=718 / d29 h22。シェッド上で手持ち MILK があり shed 在庫が 0 の場合、DROP は出すが
SELL は出さず、納屋に残って換金されない。市場数量を「行動前の shed 在庫」で決めているため。
**gen0024 / gen0025 / gen0026 / gen0031 の 4 世代で同じ指摘**。gen0041 で、最終日(`day >= FINAL_DAY`)
だけ手持ち在庫（`carried_item`）を各 SELL 数量に上乗せして対処。DROP は step2 / SELL は step3 で
同一ターン内に shed へ載り、過剰売却は在庫尽きでエンジンが安全に停止するため純粋な会計修正で済む。

### FIX0004 — `planned_seed` の幽霊予約（applied gen0042, major）

FIX0001 と同じ型（gen0022 から継承）。植付タイルへ**移動中**のユニットが `planned_seed` を予約するため、
`planned_seed >= seeds` で種切れと誤判定し、現地に立って今すぐ植える hand が弾かれる。
**gen0042 で、種数の予約を「今ターン実際に植える hand（`(ux, uy) == (x, y)`）」に限定して対処。**
タイルの `claimed` は歩行中も維持するので同じ苗床を二重取りすることはなく、種購入は `plant_slots`
（開いている植付枠の数）で数えており `planned_seed` を使わないので、予約を絞っても過剰購入にはならない。

### FIX0005 — farmer と所有者 hand の相互停止（applied gen0042, major）

所有者保護（`_owner_can_come`）は farmer を除外するのに、FEED/CARE の最寄り判定（dmin）には farmer が
残るため、farmer が近いだけで所有者の claim を潰し、farmer 自身も保護で降りて両者が譲り合い両方 PASS になる。
**gen0042 で、dmin の候補から farmer を「所有者が今日まだ来られる間（`_owner_can_come` が True）」は外して対処**
（保護の対象集合と最寄り判定の対象集合を一致させた）。rescue 時・所有者不在時は `_owner_can_come` が
False を返すので farmer は従来どおり候補に残る。unit-hour をまるごと捨てる型の損で、「労働は量ではなく質」の
原理から見て優先度が高かった。

### FIX0006 — 窓の中の WATER が HARVEST より前／生産日の水＋肥料ペア（applied gen0043, major）

WATER(1.89) が HARVEST(1.90) より前なので、水やり済みの株をその場で収穫せず別の株へ移る
（seed42 d10 で h6→h19）。gen0036 で悪化した `inplace_share` / `tile_revisit_share` と同じ根。
**melon/wheat の harvest-vs-water 側は gen0032 の訪問完了（`visit_ok` かつ `d == 0` の
DAILY_TILE_OPS を `VISIT_LAYER` に持ち上げる）で「立っているタイルの ripe を先に収穫」が成立し、
gen0036 の micro（`inplace_share` 0.410 / `tile_revisit_share` 0.012）で症状はほぼ消えている。
残る `visit_ok=False`（最終日・植付締切）の帯で in-place HARVEST を持ち上げると植付締切と競合する
（その帯を除外しているのは意図的で触らない）。**gen0043 (EXP0043) で直した actionable な取りこぼし**:
イチゴ生産日（age∈STRAW_PROD_AGES）に水やり(層2)は済むのに施肥が `FERT_PRI`(層4・PLANT の後)で
後回しになり、未施肥のまま +1 止まり＝1 収穫あたり 1.75u（強帯 1.99u）だった。まだ水やり前の株でも
同ターンに `bonus_water`（生産日の水やり）が出るので、施肥を `FERT_PRI_PAIR`(層2)に上げて
同じ訪問で水＋肥料の対を閉じる（`pri = FERT_PRI_PAIR if (watered or bonus_water) else FERT_PRI`）。
`day < FINAL_DAY` で visit_ok=False の帯は従来どおり除外。`bonus_water` の優先度配置そのもの
（EXP0024 で A/B 済みの敏感な設計）は変えていない。
補足: 台帳の `sources` は指摘の出所（`gen0024#1`）を保つ規約なので gen0043 は足さず、
`first_fixed_in` / `applied_since` で gen0043 を記録した（`--audit` の dangling 検査対策）。

### FIX0007〜FIX0013（minor。FIX0011 は applied gen0041、他は open）

`control/fixes.json` の各エントリに症状と直し方を書いてある（`--show-open` で一覧できる）。
FIX0011（最終ターンの COLLECT_FERTILIZER 死蔵）は gen0041 で `LAST_ACTION_HOUR` 以降の
産出行動を抑制して対処済み。
FIX0012 / FIX0013 はコードではなくコメント・基準値の記述の問題（`kind: doc` / `ops`）。

### FIX0014〜FIX0017（gen0044 の Codex レビューで検出。詳細は `control/fixes.json`）

gen0044（H2 売り時 burst）の昇格前 Codex レビュー（gpt-5.6-sol/high, 2026-09-06 UTC）で出た 4 件。
**いずれも即死級ではなく（1100 戦エラー 0・gate.pass）deferred で昇格**。gen0045 が売買サブシステムと
WOOL を触るので **FIX0014-0016 は gen0045 で同時に直した**（applied since gen0045。
`state/plans/2026-09-07_gen0045-funded-wool.md`）。FIX0017（共有市場の soft bound）は本設計の範囲外で open のまま。

- **FIX0014（major）**: FIX0009 の keep_sells 切り捨てと mest 計上の不整合。全 SELL の代金で mest を
  加算してから低価値 SELL を落とすので、落とした SELL の架空代金で組んだ土地/動物購入が資金不足で
  無言 no-op しうる（重い購入日で keep_sells が絞られ、落とす代金が RESERVE=400 を超える時）。
  aggregate は通るが seed 単位で取りこぼす。**open major = 新機能より安い前進**。
- **FIX0015（minor）**: BETA_SELL 品目の収穫解除ゲート(main.py L626)が固定 SELL_FLOORS のまま。β が
  売却可でも $110-119 帯・d25-27 逓減床では羊上の在庫が収穫されず d28 強制収穫へ先送り。主戦場
  （供給不足 WOOL $200+）では束縛しない。修正は解除条件を `beta_sell_cap(...) > 0` に合わせる。
- **FIX0016（minor）**: beta_sell_cap の `int()` が負数を floor でなく 0 方向へ切り捨て、境界で cap 0 の
  ところ 1 を返し β·base をわずかに割る 1 個を売る。修正は `int(I0+root) - market_inv + 1`。
- **FIX0017（minor）**: β 限界価格は共有市場の soft bound。相手の同時売却で実約定が β·base を割りうる
  （エラーでなく β が甘い上限になるだけ）。共有市場の構造上ゼロにはできない。観測可能な相手の同品目
  売却で headroom を割り引く（`未使用の観測の利用`）か wontfix 化が選択肢。

### FIX0018（minor, applied gen0046。gen0045 の Codex レビュー P1-2）

gen0045 の昇格前 Codex レビュー（gpt-5.6-sol/high, 2026-09-06 UTC・thread <redacted-id>）で出た、
**FIX0014 の reconcile の残存精度**。FIX0014 の中核（実約定 SELL だけで予算を組み直し末尾 buy を落とす）
は applied だが、reconcile の見積が粗かった 3 つの穴を **gen0046 で applied 化**（掃除世代。
gen0045 のコピー + FIX0018 のみ）。

- (1) realized は kept SELL を 0.7 掛けで**過小評価**するので、高値 SELL を残した重い購入日に
  `realized < sum(buy_costs)` と誤判定して**正当な BUY_LAND/BUY_ANIMAL を落としうる**（gen0044 なら
  約定できた購入を落とす＝過剰修正）。
- (2) reconcile は `realized >= sum(buy_costs)` しか見ず **RESERVE=400 の残置を再確認しない**。
- (3) `nb -= 1` は数量注文（`BUY_ANIMAL SHEEP 4` 等）を丸ごと落とす。エンジンは 1 個ずつ約定するので
  本来は**部分約定（3 頭）が可能**。

**gen0046 の実装**（`agents/gen0046/main.py` の市場 reconcile。`# FIX0018` マーカー）:

- **truncation ターン限定で発火**: `no_trunc = (MARKET_SLOTS - len(pre) - len(buys)) >= len(sells)`
  が真（SELL が 10 スロットに全数収まる通常ターン）なら reconcile を丸ごとスキップ。この場合
  gen0045 の reconcile は必ず `realized >= total` で不発（buys 不変）なので、親と**バイト同一の
  市場注文列**を保つ。差が出るのは truncation ターンだけ。**実測: gen0045 vs starter / 強帯
  （kaito・prvsiyan）のどの試合でも市場注文は最大 9 件で 10 スロットを超えず、truncation ターンは
  出現しない**（＝この修正は observed trajectory では発火しない latent-state の堅牢化。50 seed eval
  でもマージン差は 0 になるのが正しい挙動）。
- (穴1) `_proceeds`: BETA 品目（WOOL/MELON）はエンジンの glut 価格式 `price = base − amp·(inv−I0)²`
  を 1 個ずつ足し込み実約定額を近似（scarcity 側は base で頭打ち＝保守、glut 側は逓減＝大量 SELL の
  スリッページ保険が自然に残る）。非 BETA は現行価格×係数。全体に `SELL_REALIZE_SAFETY=0.9` を掛けて
  共有市場の同時売却（FIX0017・open）を hedge。own-slippage を per-unit で織り込んだので旧 0.7 より
  緩め、engine 単独 realized の上限を超えない＝over-buy を誘発しない。
- (穴2) `_required_reserve`: feed 小麦=0／BUY_LAND・BUY_ANIMAL・BUY_SEED=RESERVE(400)／HIRE=20。
  判定を `realized >= sum(buy_costs[:nb]) + _required_reserve(buys[nb-1])`（末尾 buy を残すのに要る
  残置まで満たすか）に。buys の並びは feed→land→animal→hire→seed 固定なので末尾＝present な最後の種別。
- (穴3) 末尾が数量注文（BUY_ANIMAL/BUY_SEED/BUY_PRODUCT）なら、丸落としの前に RESERVE を残して
  買える数量へ縮小（`buys[nb-1] = tail[:2] + [newq]`, buy_costs も整合）。atomic（BUY_LAND/HIRE）と
  数量 1 まで縮めても賄えない場合だけ従来どおり丸ごと落とす。
- (1 の補足) feed 小麦の `buy_costs` を数量決定と同じ保守単価 `wp+5` で計上（mest 減算は親と同じ
  `wp+3` のまま＝通常ターンの buy 構築を親とバイト同一に保つ。buy_costs は reconcile でしか読まれない）。
- **合成シナリオでの動作確認**（observed trajectory では発火しないため）: 11 SELL × 2 番目土地
  ($2000) の重い購入ターンで、旧 reconcile は kept MELON を 0.7 掛けで過小評価し realized $1925 < $2000
  で土地を誤って落とすが、新 reconcile は glut+0.9 で realized $2475 ≥ $2000+RESERVE($400) と正しく
  判定して土地を救済。数量注文 `SHEEP 4` の末尾は、旧は全 4 頭を落とすが新は 3 頭へ縮小。
- **FIX0014 の detect 更新**: FIX0018 が同じ reconcile 領域を書き換え、`realized >= sum(buy_costs[:nb])`
  の行が `realized >= need` に変わったため、FIX0014 の require 正規表現を `sum(buy_costs[:nb])` と
  `buys = buys[:nb]`（どちらも gen0045・gen0046 両方に実コードとして残る）に緩めた。FIX0014 の機構
  （実約定 buy_costs から予算を組み直し末尾から落とす）を引き続き本文照合で検証する。

### FIX0019 + FIX0020（carrot 終盤清算。applied gen0050。gen0048 の Codex レビュー P1-1/P1-2）

gen0048 が carrot 機構を発火させたあと、最終日清算に穴が残った（`# FIX0019` / `# FIX0020`
マーカー）。engine 検証: CARROT は非 ongoing。yield は WATER が age∈[2,3] のとき **だけ** 積む
（+1・肥料時 +2、max 4）。HARVEST は `day - planted_day >= first_yield_day(2)` かつ `yield>0`。
WATER（通常・bonus とも）は `day < FINAL_DAY(29)` ガードの内側なので **d29 は水やり 0 件**。

- **FIX0020(A)（major）**: d27 植え carrot は d29 に age2 でしか刈れず、収穫した hand が h17-22 を
  移動に費やしてもシェッドに届かず SELL は毎ターン無言 no-op。3 smoke seed とも
  `carried.CARROT=6 / shed.CARROT=0`（~$300/試合の未換金）。
- **FIX0020(B)（major）**: 最終日の SELL 数量組み立てが carried 在庫を全量 DROP 可能として加算し、
  届かない在庫へ実行されない幽霊 SELL 注文を出す（meta の「carrot SELL 78-82 units」は反復注文の
  合算で実約定量ではない）。
- **FIX0019（minor）**: d29 は WATER 0 なので d27 植え=d29 age2 の yield が 1 個止まり（想定 2-3 個/枚を下回る）。

**gen0050 の解決（遠征を無くす方向で 3 つ同時に）**:
- `last_plant_day` 27→**26**（d26 植えは d28 に age2 で刈れる限界）。
- carrot ripe を `age >= 3 or (day >= FINAL_DAY - 1 and age >= 2)`（d25 植え=d28 age3=収量2、
  d26 植え=d28 age2=収量1）。全 carrot を **d28 までに収穫**し、d29 を丸一日 DROP+SELL 搬送に空ける。
  これで **d29 に生きた carrot が残らない** ため FIX0019（d29 水やり不足）は不要になり、d29 bonus
  WATER は追加しない。
- 最終日 carried_item 集計を、その unit の選択済み action が今ターン DROP のときだけに限定
  （`if _ui < len(actions) and actions[_ui] and actions[_ui][0] == "DROP":`）。FIX0003（今ターン DROP
  分を shed 在庫に上乗せ）は温存しつつ、届かない在庫への幽霊 SELL を止める。

detect: FIX0020 は `ripe = age >= 3 or (day >= FINAL_DAY - 1 and age >= 2)` と
`actions[_ui][0] == "DROP"` の 2 本を require。FIX0019 は同じ FINAL_DAY-1 の ripe 行を require
（d28 収穫にして遠征を無くす方で解決したことを機械照合）。

### FIX0021 / FIX0022 / FIX0023（gen0056 の相手適応乳エクスポージャ。open。gen0056 Codex レビュー 2026-09-14）

gen0056 は gate.pass（マージン経路）だが、Codex（gpt-5.6-sol/high）と Claude の検証で機構の前提が崩れた。
**gen0056 を親にする世代はこの 3 件を継承する**ので、継ぐなら先に直す。

- **FIX0021（major）**: `milk_flood` の連言は床が相手由来であることを保証しない（相手牛>=6 は能力であって原因ではない）。
  eval の対応一致は starter/georgy だけ 100/100、kaito 35・rayk 33・gen0044/45 32-35・boatlee_v29 24/100。
  「kaito/rayk では必ず False」の設計主張は偽。`FLOOD_COW_HERD=6` の origin も derived ではない（sources: gen0056#0, #3）。
- **FIX0022（major）**: 乳バンクゲート即時解除は MILK 限定の条件式だが、HARVEST が全品目共通の作業キューと競合し、
  shed に移った乳が `shed_pressure`（`>= SHED_DUMP=78` でプレミアム品も全量ダンプ）を押し上げる。
  自資金 −244.2 [−376.9, −111.5]・強帯自資金 −188.9 [−354.7, −23.2] と整合（因果分解は未実施。sources: gen0056#1）。
- **FIX0023（minor）**: ヒステリシスが無く `cow_target` が 6↔8 を往復する。現プールでは既に 8 頭なので実害は小（sources: gen0056#2）。

### FIX0024 / FIX0025 / FIX0026（gen0057 の市場条件付き埋め作物。open。gen0057 Codex レビュー 2026-09-19）

gen0057 は P0 ゼロで昇格をブロックする指摘は無いが、**3 件とも「実装 ≠ 設計の説明」**である。
検証の全量は `knowledge/analysis/2026-09-19_gen0057-review-verification.md`。
**gen0057 を親にする世代はこの 3 件を継承する。**

- **FIX0024（major）**: 置き換え枚数の予算が**毎ターン再発行**され、上限として機能していない。
  `carrot_fill_left` はターン内ローカルで、既に植えた株・買った種・shed 在庫を控除しない。
  実測（スモーク 3 seed）: d03 は予算 1 枚/ターンに対し **3 枚**植付。逆に d18 以降は予算が
  **36-57 枚/ターン**まで開き、空きタイル（12-25 枚）を常に上回る＝**機構が発火する窓で条件が binding でない**。
  ＝実装されているのは「市場在庫が許す枚数だけ」ではなく **「終盤ブロックと計画外タイルは headroom>0 なら
  ニンジンで埋める」**。EXP0057 の「d0-d8 は 0-2 枚＝この時期は小麦のまま」も falsify（d03/05/06 に 6 枚、
  seed 42 は d08-d18 にさらに 12 枚。親は d25 以前のニンジン 0 枚）。
  併せて除数 `MAX_YIELD["CARROT"]=3` はエンジンの `max_yield`=**4** と違う（無肥料到達値が 3 なので
  運用上は正しいが、定数名とコメント「エンジン CROPS の max_yield」が誤り。予算を直すと 33% の過大評価として効く）。
  (sources: gen0057#0, gen0057#2)
- **FIX0025（minor）**: 置換元は d25 で閉じるのに `window_end.setdefault("CARROT", 26)` が d26 を立てるため、
  d25 夕方に「d26 に植えられる」として種を買える。実害は現状小（季節末残種は親と同等以下）。
  **FIX0024 を直して予算が binding になると表に出る。** (sources: gen0057#1)
- **FIX0026（minor）**: 「優先度は小麦計画のまま＝層は動かさない」というコメントの 8 行下で
  層 2（2.24）に上げている。層の変更は意図どおり（meta.json に記載）だが**コメントだけが旧設計**。
  世代は不変なので永久に残る。 (sources: gen0057#3)
- **FIX0027（minor・wontfix）**: `market.inventory` の値が非整数（`None` 等）なら算術で例外 →
  そのターン全 PASS。**gen0057 が持ち込んだものではなく親 gen0051 の `beta_sell_cap()`（`main.py:579`）が
  既に同じ算術をしている＝系譜全体の性質。** 観測仕様上は整数で、30 世代・数千試合で未発火。
  ガードを撒くと例外が握り潰されて静かな劣化に変わる方が危険（発火すれば `noop_total` が跳ねて気づける）。
  Codex の指摘を**反証として記録**したもの。 (sources: gen0057#4)

### FIX0028（最終日の肥料死蔵。**open に差し戻し**（gen0061 は非昇格）。gen0059 Codex レビュー 2026-09-18）

- **FIX0028（minor）**: FIX0011 は「最終日 h22 以降の `COLLECT_FERTILIZER` を止める」だけなので、
  **h21 にシェッドから 1 歩以上離れたタイルで回収すると h22 はシェッドへの MOVE になり DROP の手番が無い**。
  実測: gen0059 の 3 スモークは farmer が `{"FERTILIZER": 1}` を抱えて終局（最終 action は `["EAST"]`）。
  **ただし親 gen0051 も同じ 1 個を hand（index 6 / 1）が抱えて終局しているので gen0059 の回帰ではなく系譜の性質。**
  （Codex は farmer スロットだけを見て「親は空」＝ gen0059 の回帰と報告したが、hand を見ると同量が死蔵していた。
  **指摘の中身は正しく、attribution だけが誤り**という形の典型例。）
  直し方: 最終日だけ「回収してからシェッドへ戻って DROP できるか」を距離で判定する
  （`hour + shed_d + 1 <= LAST_ACTION_HOUR`）。損失は肥料 1 個ぶんで小さく、gen0059 の機構とは
  無関係な終盤清算の穴なので、**次に終盤清算を触る世代でまとめて直す**（ここで直すと帰属が割れる）。
  (sources: gen0059#1)

### FIX0029 / FIX0030 / FIX0031（gen0058 の到達可能性ゲート。**FIX0030 は gen0060 で applied**・**FIX0029 / FIX0031 は open に差し戻し**（gen0061 は非昇格）。gen0058 昇格前 Codex レビュー 2026-09-18）

gen0058 は P0 ゼロで昇格した（全体マージン +$1,706 [+1,068, +2,344]）。**gen0058 を親にする世代はこの 3 件を継承する。**

- **FIX0029（minor）**: ゲートの `FINAL_DAY` carve-out が**終端規則と逆向き**。最終日は「届かなくても運ぶ」
  価値があるのではなく、位置も在庫も持ち越せないので**届かない移動の価値は通常日以上にゼロ**。
  しかも最終行動は h22（`LAST_ACTION_HOUR`）。最終日は残り時間を h22 で切るのが正しい。
  **FIX0028 と同じ根（最終日の到達可能性）なので同時に直すのが安い。** (sources: gen0058#1)
- **FIX0030（major）**: **枯死防止 WATER(pri 1.0) に最寄り担当制が無い。** FEED/CARE には `dmin` があるのに
  WATER には無く、`LOSS_PRIS` の carve-out が到達可能性ゲートも免除するので、**遠いゾーン所有者が
  移動中に claim すると到達可能な hand が弾かれる**。エンジンは `consecutive_unwatered >= 2` で即 WEED 化
  （`kaggriculture.py:777`）＝ 1 ターンの取り違えでタイルを失う。**FEED/CARE と WATER の非対称そのものが欠陥。**
  ただし 3 スモーク＋1,300 戦で unfed/uncared/noop は全 0 ＝ **critical-three が枯死を直接見ていない**ので
  発火の有無が分からない。**まず `new_weed_from_unwatered` 相当の指標を足すのが順序。** (sources: gen0058#2)
  → **applied gen0060**（`# FIX0030` マーカー）: `dmin` ブロックの対象 op に `op[0] == "WATER" and pri in LOSS_PRIS`
  を足し、WATER は `rescue = False` にした（`_owner_can_come` に WATER の時刻 carve-out が無いので、非所有者が
  取れるのは所有権が解放されている時だけ ＝ **最寄り判定の対象集合 = 実際に claim できる集合**。揃えないと
  gen0058 が警告した『誰も来ない穴』ができる）。所有権の解除規則そのものを触る世代（gen0060）に同居させた。
  **発火の観測は相変わらず無い**（枯死を見る指標が無いのは未解決。人への提案は HANDOFF）。
- **FIX0031（minor）**: `ZWHEAT` / `ZFERT` の一括 PICKUP は `eval_todos` の**外**で比較されるので
  **到達可能性ゲートを迂回する**。加えて `zone_unfed` / `zone_fert` / `fert_soon` はゲート前の todo を数える。
  実測: gen0058 の真の h23 残存 MOVE 7/6/10 のうち **6/6/9 がシェッド方向**＝今日使えない物を取りに歩いている。
  (sources: gen0058#3)

### FIX0032 / FIX0033（gen0060 のバックログ解放。open。gen0060 昇格前 Codex レビュー 2026-09-19）

gen0060 は 3 ラウンドのレビューで P0/P1 ゼロまで持っていった（P1 は計 4 件、すべて **昇格前に fixed**）。
残った 2 件は deferred:

- **FIX0032（minor）**: **解放に履歴が無く、ターンをまたいだ目的地の振動が起きうる。** `zone_doable` と
  `claimed` は毎ターン作り直されるので、ターン T に解放された他ゾーンの todo が T+1 に保護へ戻ると、
  向かっていた非所有者が目的地を変える。Codex 実測（seed 123）: 作業を挟まない**正反対の MOVE が 17 → 44 回**。
  seed 123 の `tile_revisit_share` 0.0204（基準 0.02・親 0.0147）の一部はこれ。
  **世代のエージェントは状態を持てない**ので、直すなら観測から再導出できる形に限る。
  **50 シード評価の結果を見てから対処を決める**（効果が出ているなら振動は許容コスト）。(sources: gen0060#5)
- **FIX0033（minor/doc）**: `_zone_backlog_doable` 前後のコメントが旧実装のまま（「最近傍順」「VISIT_LAYER は
  入れない」「先頭が必ず保護される」）。**実装 ≠ 説明の 6 例目。** gen0060 自身では直さない
  （レビュー済み SHA を固定するため。Codex 自身が deferred を推奨）。**meta.json と EXP0060 の説明は
  正しい方に直してある。** (sources: gen0060#6)


---

## 2026-09-19 cycle8: 到達可能性ゲートの穴 3 件（gen0061）と、台帳そのものへの学び

gen0061（親 gen0058）が **FIX0028 / FIX0029 / FIX0031** を同時に実装した。3 件とも
「歩き出しても今日は実行できない行動を選ばない」という gen0058 の規則の**適用漏れ**で、新規定数は 0 件。
評価は 50 シードで投入済み（`records/eval_gen0061.json`）。詳細は `knowledge/experiments/EXP0061_*.md`。

- **FIX0028 / FIX0029 → applied（gen0061）。ただし資金効果はゼロ。**
  親 gen0058 と gen0061（FIX0031 を入れる前の版）の **719 ターンぶんの行動列を突き合わせた**結果、
  差分は 3 シードとも **d29 h19 以降の「futile MOVE → PASS」だけ**で（seed 7 は 9 手、42 は 3 手、
  123 は 9 手）、**最終資金は 3/3 で 1 ドルも動かなかった**（75,179 / 60,437 / 69,754 が完全一致）。
  浮いた unit-hour は 1 つも生産行動に変換されていない ——最終日の夕方には、そのユニットが今日中に
  着いて実行できる代替の仕事が盤上に無いから。
  → **台帳の `severity` は「正しさの重大さ」であって「効果量の見積り」ではない。** FIX0029 の `why` に
  書いた「効果量は小さいが確実」と HANDOFF の「安い前進」は**この点で誤り**だった。以後、`severity` と
  効果量は別の欄として扱うこと。
  - 副産物（エンジン仕様の確定）: **最終の有効行動は d29 h22 ＝ `LAST_ACTION_HOUR` は正しい。**
    リプレイ index 719（d29 h23）にも行動は記録されるが、interpreter 冒頭の `if env.done: return state`
    で**一度も解釈されない**（DONE は step 718 の処理直後に `step >= cfg.episodeSteps - 2` で立つ）。

- **FIX0031 → open のまま（`attempts` に記録）。最小案はスモーク 3/3 で負。**
  ZWHEAT / ZFERT にゲートを課す最小案を gen0061 が実装したが、**親 vs 親の mirror を対照に取った
  対応付きスモーク**で 3/3 とも負だった（−979 / −757 / −1,310・平均 −$1,015）。3 シードは方向判断に
  使えない（要 24）ので保留だが、**50 シード評価の主要な確認対象**。悪化が確認されたら最小案は
  wontfix として閉じ、別案（PICKUP から FEED まで届くかで切る等）へ移す。
  → 一般化: **無駄な行動を消しても価値は生まれない。浮いた時間の行き先（`eval_todos(False)` の
  fallback）が元より悪いことがある。** c7 の「PASS を消すと 2/3 が通勤 MOVE に化ける」と同じ形で、
  今夜 3 例目。

- **台帳の運用上の穴（人への提案）: `ops/check_fixes.py` は「兄弟枝で applied」を表現できない。**
  gen0061 は親が gen0058 なので **FIX0030（`applied_since: gen0060`）を構造上継承しない**。gen0060 は
  まだ未評価の兄弟枝で王者ではないから、先取りすれば gen0060 の測定と重複し gen0061 の帰属も割れる
  ——つまり**入れない方が正しい**。しかし `check_fixes.py` はこれを「NG 回帰」と出す。
  同様に、FIX0028 / FIX0029 を applied にしたことで **gen0060 / gen0058 を検査すると 2 件の NG が出る**
  ようになった（これも正しい状態ではない）。
  対処案（人の判断）: `fixes.json` に `branch`（どの親系統で applied か）を持たせ、`check_fixes.py` が
  候補の `meta.json` の `parent` を辿って**祖先に `applied_since` が無ければ NG にしない**ようにする。
  それまでは、NG を見た人が `applied_since` の世代が自分の祖先かどうかを手で確かめること。

## 2026-09-20 c3 — gen0062（合流世代）の Codex レビューで出た deferred 4 件

いずれも **昇格ブロッカーではない**（Codex round2/3 で「50 シード評価へ進めてよい」を確認）。
**gen0062 で直さなかった理由は 3 件とも同じ: この世代の目的は「2 機構を合流させたときの効果」を
50 シードで測ることなので、測定対象に第 3 の変更を混ぜない**（1 世代に 2 機構を混ぜて効果の帰属が
割れた gen0057 の反省）。

- **FIX0034 [minor] farmer の自ゾーン外の仕事がバックログ予算に計上されない → farmer ゾーンの過剰保護。**
  `_zone_backlog_doable()` は全ゾーンについて「所有者は残り時間を自ゾーンだけに使う」と仮定する。
  farmer は同時に SHEDOP と自ゾーン外 PLACE を `farmer_shed` 例外で取る（crit=1 ＝ 高優先）のに、
  その時間が予算から引かれない。**規模: 実行回数で 25-29 回 / 30 日（PLACE 12 = 動物 12 頭ぶんで d0-d8 に集中）。
  ただし目的地への MOVE は含まないので「1 日 1 時間」とまでは確定していない**（Codex round2 の留保）。
  → **近似の種類自体は親 gen0060 から在る**（hands も自ゾーン外の救済 FEED/CARE・FERTILIZE・
  ZWHEAT/ZFERT のシェッド往復をする）。新しいのは**適用範囲が広がったこと**であって別種の欠陥ではない。
  Codex の初案「`owner == farmer_zone` なら保護を全面的に外す」は**採らなかった**（gen0059 とも gen0060 とも
  違う第 3 の割当方式になる）。

- **FIX0035 [minor] 既に行動を確定した unit が FEED/CARE の `dmin` を作る（系譜全体・gen0051 から）。**
  gen0062 で新しいのは、farmer が自分の区画では `owner == zid` により `ds` に残るようになった＝
  **対象が farmer ゾーンにも広がった**点だけ。**gen0060 のレビューで Codex 自身が同じ性質を指摘し、
  それを根拠に FIX0030 の dmin 案を撤回している。** 最小案 `if i < _ui: continue` は系譜全体の
  FEED/CARE 割当を変えるので、単独世代で測る。

- **FIX0036 [minor] シェッド容量超過時に携行中の動物が EOD で破棄されうる。**
  gen0058 の到達可能性ゲートの根拠「携行中の動物は日の終わりにシェッドへ戻るので損失ゼロ」の**反例**。
  エンジンは `room = max(0, capacity - current)` / `take = min(n, room)` のあと入り切らない分を
  `del inv[item]` で捨てる（README: `overflow is lost`）。実測では `shed + carried` が 120/115/105 と
  容量 100 を超える瞬間はあるが、**EOD に動物を携行していた日は 0 件**＝ 3 seed では未発火。
  → **設計の根拠そのものへの反例なので、発火しなくても記録が要る。** 正しい言い方は
  「通常は翌朝シェッドへ戻るが、容量超過時は破棄されうる」。

- **FIX0037 [minor/ops] `ops/eval_queue.py submit` が同じ秒の 2 回呼び出しでジョブを黙って上書きする。**
  ジョブ ID が `{UTC 秒}_{gen}.json` だけで決まる（`ops/eval_queue.py:135`）。**c3 で実際に踏んだ**:
  gen0062 の本命（新王者 gen0060 比）と 2 本目（gen0058 比）を続けて積んだら、**2 本目が 1 本目を上書きし、
  両方とも `QUEUED` と表示された**。出力の `→ records/...` が 2 行とも同じジョブファイルを指していたことで
  気づき、手で積み直した。サイクルは「積んで終える」運用なので、**気づく機会が次サイクルの読みしかない。**

### この 4 件から出た一般的な教訓

**自分が書いた設計根拠こそレビューの対象にする。** c3 は G1/G2 の carve-out 非対称の理由として
「到達不能な近いユニットが `dmin` を作り、到達できる遠いユニットを弾く」と書いたが、**これは成立しない**
（ゲートは距離の単調関数なので、降りるユニットは通るユニットより必ず遠い）。Codex round2 が撤回させた。
正しい理由は「**全ユニットが到達不能な盤面では `ds` が空 → `dmin=None` → 最寄り判定が無効**になり、
『誰も来られないなら誰が取ってもよい』が保たれる」。
gen0060 の「自己申告の不変条件が偽だった」（EXP0060 学び 2）と**同じ形が 2 世代続けて出ている。**

## 2026-09-20 c4 — gen0061 の 50 シード評価で確定したこと ＋ 評価キューの ops 修正 2 件

### FIX0028 / FIX0029 / FIX0031 の現況（**3 件とも open に戻した / open のまま**）

`records/eval_gen0061.json`（50 シード・13 体 `e3f96592`・baseline `records/eval_gen0058.json`）:
**`gate.pass=False`**・対応付きマージン **+$32.4 [−36.8, +101.7]**・自資金 −$34.6 [−154.9, +85.6]・
強帯マージン +$47.3 [−39.9, +134.6]・`rating_delta` +6.9 [−41.1, +54.9]・pool rating 668.0 ± 17.3。

- **gen0061 が昇格しなかったので、この 3 件は王者系統（gen0060 → gen0062）に入っていない。**
  台帳の `applied` は「王者系統に入っている」という意味（`conventions.status`）なので、
  **FIX0028 / FIX0029 を `applied` から `open` に戻した**（`applied_since: gen0061` は兄弟枝を指していた）。
  実装と測定は `attempts` に残してある。これで **`check_fixes.py agents/gen0060|0062/main.py` の
  「NG 回帰 FIX0028 / FIX0029」が消える** —— HANDOFF が「正常だが紛らわしい」と書いていた表示は、
  台帳側が実態とズレていたのであって検査器の穴ではなかった。
- **FIX0031 は「検出不能」ではなく「効果量の上限が付いた」。** 対応付き CI の幅が ±$70 しかない
  （変更が発火する場面が稀で、ほとんどの対が完全に同一のため）＝ **効果は最大でも +$102/試合**で、
  典型的な昇格効果 $1.7-3.1k の 1/20 以下。**単独世代として測り直す価値はもう無い**（同じ場所を
  触る世代への同梱は安い）。
- **3 シードの対応付きスモークは 3/3 負（平均 −$1,015）だった。** 50 シードの真値は +$32 ± 70。
  `2026-09-05_seed-detection-limit.md` の「スモークで方向を語らない」の、**符号ごと逆になる実例**。

### FIX0037 / FIX0038（評価キュー。**applied**。`ops/eval_queue.py`）

- **FIX0037 = 同秒衝突**（既報）。連番 suffix `_NN`（ゼロ詰め）＋ `O_EXCL` で排他作成。
  **あわせて「同じ `--out` を指す未完了ジョブがある submit」を NO-GO にした** —— ジョブファイルを
  分けても既定 out が `records/eval_<gen>.json` なので、**結果の方が上書きされる**（Codex P1-2）。
- **FIX0038 = kill されたジョブが `running` のまま滞留する**（2026-09-19 のバッテリー切れで発生）。
  `run` が `pid` / `eval_pid` / `out_before`（出力の実行前 stat）を記録し、`next` が
  「PID が全部死んでいて実行ロックも空いている」ジョブを回収する。
  - **回収して `done` に畳むのは、出力が今回の実行で書かれたと確信できるときだけ。** それ以外は
    `pending` に戻す。理由: `harness/evaluate.py:518` は全試合が終わってから out を**一度だけ**書くので、
    **前回の評価 JSON が残っていると 1 戦も終わっていなくても「出力が揃っている」ように見える**。
    これを done に畳むと**古い評価 JSON で昇格判定をする**（Codex P1-1。このプロジェクトで最も高くつく失敗）。
  - 実行権は `<job>.lock` の flock で原子的に取り、**その fd を評価子に継承させる**ので、
    runner だけ殺されて `eval_pid` を書く前でも二重起動しない（Codex round2 P1-1）。
  - **判定不能は「生きている」側に倒す**: 旧コードが書いた `pid` 無しの running は回収しない。
- 回帰テスト **`ops/test_eval_queue.py`（22 ケース）**。実リポジトリの `state/eval_queue/` と
  `records/` には触らず、一時ディレクトリに複製して CLI を叩く。
- Codex レビュー **gpt-5.6-sol / high・2 ラウンド**で P1 を計 9 件受けて全件修正（P0 なし）。
  1 ラウンド目で止めていたら、上の「古い評価 JSON を done に畳む」を入れたまま commit していた。

### 台帳そのものの変更: `kind: "ops"` を回帰検査の対象外にした

`ops/check_fixes.py` は `agents/genNNNN/main.py` を検査する道具なので、**対象が `ops/` や `control/` の
修正（`kind: "ops"`）は `detect` を書いても判定できない。** これまで `status=applied` には `detect` が
必須だったため、**ops の修正は直しても台帳に applied と書けなかった**（FIX0013 が open のまま残っている
のもこれが理由の一部）。`kind == "ops"` のときだけ (1) `applied` に `detect` を要求しない
(2) 回帰・未検証の集計から外す —— に変更。一覧には従来どおり出る。

### FIX0039（`ALWAYS_SELL` の TOMATO 即売り。**open**・minor・**未発火**）

- `ALWAYS_SELL = [FERTILIZER, EGG, CARROT, TOMATO]` のコメントは「EGG/CARROT/TOMATO は T が大きく
  glut になりにくい」と書いているが、engine の実値は **TOMATO の `T` = 200**（EGG 332・CARROT 450・
  WHEAT 400。プレミアム品を除けば最小）。above 側は `sqrt` / `above_target 0.60` なので
  **I0 を 200 個超えた時点で $24、400 個で $9**。
- **現行世代はトマトを 1 個も産まないので未発火**（2026-09-20 に 30 戦で確認。在庫は 21/21 で I0 未満）。
  発火条件が「将来トマトを植えること」なので、**世代が不変である以上この台帳にしか残せない**。
- 直し方: トマトを植える世代では `ALWAYS_SELL` から外し、メロン/乳と同じ**町の吸収レート以下のトリクル売り**
  （Pizza 6 個/日 + town center 1 個/日、Farmers Market が引かれれば +6）に回す。コメントの数値も直す。
- 出所: `knowledge/analysis/2026-09-20_tomato-track2b.md` §5（Track 2b の設計可否調査の副産物）。

### FIX0040（gen0063 のトマト差し替えゲート (c-2) が小麦の成熟日を見ない。**open**・minor）

- gen0063 の飼料ゲートは **(c-1)** 次の小麦収穫までは手元在庫だけで賄える ＋ **(c-2)** 手元 ＋
  `wheat_live * 4` で小麦 1 回転（4 日）ぶんを賄える、の 2 条件。**(c-2) は株の age を見ない**ので
  「age3 が 1 枚・age0 が 8 枚」でも『4 日ぶんある』と通る（実際に穫れるのは翌日の 4 個だけ）。
- 実測の症状: vs starter 3 シードのうち 2 シードで `BUY_PRODUCT WHEAT` が親比 **+12 個**（$300-500 相当）。
  **`unfed` は 3/3 で 0**（飼料の担保はこのゲートではなく既存の買い足しと評価側の `unfed_days = 0`）。
- 直し方: 小麦を成熟日（`planted_day + 4`）別に積み、bridge の各日末残高が非負かを見る。
  安全側に倒すだけなら (c-2) を手元在庫のみにするが、**ゲートがほぼ常に閉じて機構が発火しなくなる**
  恐れがある（c6 で窓を d19-20 に狭めた版が 3/3 シード発火 0 になった前例）。
- 出所: Codex レビュー round2 P1-1 / round3 P1（gpt-5.6-sol / high・2026-09-20）。`gen0063#0`。

### FIX0039 は gen0063 で applied

- `ALWAYS_SELL` から TOMATO を外して `SELL_FLOORS`（町の吸収レート／在庫予算に従うトリクル売り）へ移し、
  併せて `premium_absorb` に `"TOMATO": 1 + 6 * t` を追加した（`t` = PIZZA_SHOP + FARMERS_MARKET の軒数。
  **6 = 24 ステップ / `townShopSellInterval` 4** ＝ engine 由来で tuned ではない。Codex gen0063#round1-P1-3）。

### FIX0041（`TOMATO_SEED_BUFFER = 1` の出所。**wontfix**・minor）

- gen0063 のトマト種 JIT バッファ `1` は**ゲーム規則から導けない実測由来の定数**。
  役割は「買った種は売れないので使う直前にだけ買う」という JIT 在庫であって、勝率を当てにいった閾値ではない
  （2 と 1 の 2 点だけを比べ、植付枚数 3 枚は同じまま死蔵が $250 → $50 に減る方を採った。sweep はしていない）。
- **wontfix**。ただし台帳に残す理由: 出所を書かないと後の世代が「検証済みの定数」と誤解して sweep を始める。
  トマトの植付枚数が増える設計に変えるなら、その世代で候補枚数から導く形に置き換えること。
- 出所: Codex レビュー round1 P2-2（gpt-5.6-sol / high・2026-09-20）。`gen0063#7`。
