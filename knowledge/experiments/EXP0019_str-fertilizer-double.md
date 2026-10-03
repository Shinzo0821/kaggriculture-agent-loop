# EXP0019: STR 肥料2倍化（STR系統2世代目）
- 日付: 2026-09-04 ／ 世代: gen0019（親: gen0017）
- 仮説: gen0017（無肥料 shop-aware STR ピボット）は vs gen0013 34.0%/−$893 で棄却された。敗因は「無肥料 STR はタイル単価でメロン2波に勝てない」（STR 4収穫×base$120 = $480-800/タイル vs メロン ~$1,500/タイル）。ongoing 作物は「肥料が効く日 かつ 水やり済みの日」に scheduled 産出が 1→2 に倍化する（engine 実測）。STR を age9/13 に FERTILIZE すれば4収穫全部が2倍化し $960-1,600/タイルとメロン同等以上になるはず。肥料は自軍動物の COLLECT_FERTILIZER 産（新規現金流出なし）なので、機会費用 ≪ 追加ベリー収入。

## 肥料機構の engine 実測（kaggriculture.py:769-800, 475-482）
- STRAWBERRY: first_yield_day=10, interval=2, max_yield=4（4回 scheduled 産出）。base$120, T=100, above_target=1.60 linear（＝**glut時に価格が急落する薄い市場**）。
- scheduled 産出は end-of-day リフレッシュ（`_daily_refresh_plants(farm, current_day)`）で `next_day - planted - 10` が interval の倍数の時に yield_units を加算。planted=P なら current_day = **P+9, P+11, P+13, P+15**（＝収穫が age10/12/14/16 で立つ前日）。
- 倍化条件（line 799）: `fertilized = was_watered and fertilized_until_day >= current_day`。つまり産出前日に「水やり済み かつ 施肥有効」なら +2、でなければ +1。
- FERTILIZE（line 481）: `fertilized_until_day = day+2`（当日含め3日有効）。
- → **age9 に施肥で eve 9・11（収穫1・2）、age13 で eve 13・15（収穫3・4）を覆う**。肥料2個/タイルで4収穫全部2倍。
- **計画の「age10/14」は off-by-one**（age10施肥は fert_until=P+12 で eve 11 しか覆えず収穫2・4のみ倍化）。engine 真値に合わせ **age9/13 に修正**して実装した。

## 変更（gen0017 からの単一系統レバー）
1. STRAWBERRY タイルが `age∈{9,11,13,15}` かつ `fertilized_until_day < day` なら FERTILIZE todo（pri 1.7）。`<day` ガードで実発火は age9・13 の2回/タイル、施肥漏れ時は age11 等で自己回復。
2. shed の FERTILIZER を PICKUP（pri 0.6、代表1ユニットが今日の対象数ぶん確保）→ FERTILIZE（need="FERT"、肥料保有ユニットのみ）。
3. 肥料供給確保: str_mode 中は COLLECT_FERTILIZER の優先度を 4.0→2.7 に上げる（非STR時は従来通り 4.0）。
4. 売却 reserve: str_mode かつ day<DUMP_DAY は `2×若STR枚数(age≤13)` を残して施肥枯渇を防ぐ。overflow/DUMP は例外で全売り。

## 結果（harness/evaluate.py, seeds=100=対戦相手ごと200戦, jobs=8）
- **vs gen0018（現行王者）: 36.5%** Wilson[30.1, 43.4]、平均 **−$913.6**
- vs starter: 100% Wilson[98.1,100]、平均 +$62,855
- 400戦エラー0・タイムアウト0（~1.4ms/turn）
- ゲート: starter≥95% ✓ / champion>55% ✗ → **昇格せず**。破滅回避ゲート（≥30%）は通るが**絶対資金増を満たさない**（−$913）ので**提出も見送り**（gen0017 と同じ判断）。

## 判定: 棄却

## 学び（次に活きる知見）
- **倍化機構は正しく発火・機能した**（プローブ seed99: gen0017 STR売却16個 → gen0019 24個 = +8、施肥8回）。にもかかわらず結果は悪化した（seed99 diff −2412→−3924）。つまり**「STRを2倍にする」こと自体が勝ちに繋がらない**。
- **敗因1: STR は自分の薄い市場を潰す。** STRAWBERRY は T=100・above_target=1.60 linear で、両者供給下では売れば売るほど価格が急落する。2倍化で供給を増やすと単価が下がり、増量メリットを相殺する（自己 glut）。base$120 前提の $960-1,600/タイル試算は「価格が張り付く」前提で、実際は張り付かない。
- **敗因2: 肥料物流が労働を奪う。** COLLECT_FERTILIZER 優先度2.7への引き上げ＋PICKUP＋FERTILIZE がメロン/動物コアの水やり・CARE から手を引き、メロン収穫タイミングまでズラす（seed303 では gen0017=STR不発 だったのが gen0019 では STR 発火するほど労働配分が変わった＝副作用）。肥料単独レバーのつもりが労働配分も動かしている。
- **STR系統 2世代連続棄却（gen0017 34% / gen0019 36.5%）。** §7 の3世代打ち切りに1世代を残すが、上記2つの構造欠陥は**対戦相手非依存**（自己 glut は相手が誰でも起きる）なので、STATUS line25 の「local 盲点（自系統相手だから拡張型経験が再現されない）」論では救えない。**イチゴを主エンジンにする路線は打ち切りが妥当**。3世代目（無条件化/増量）は作らない。
- **示唆**: LB の真の敗因は cycle6 分析どおり「ビルド凍結」（土地0・hands8止まり・主エンジン規模の小ささ）であり、特定作物(STR)の有無ではない。次の Track B は「需要口数最大の品目へ資本を寄せる汎用ピボット」＋「土地/hands 拡大で主エンジン規模を上げる」方向へ（cycle3-losses 分析の結論を待つ）。
- 副次: STR を薄い市場に大量供給するのが悪手なら、逆に **MELON（base$250, T=300）の方が市場が厚く単価維持しやすい** という既存路線（メロン資本スプリント）の優位性が再確認された。
