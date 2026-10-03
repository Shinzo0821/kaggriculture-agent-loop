---
status: done   # in_progress | done
gen: gen0050
parent: gen0048
---

# EXP0050: carrot 終盤清算（FIX0019 + FIX0020 を同時解決）
- 日付: 2026-09-08 ／ 世代: gen0050（親: gen0048＝現王者）
- 仮説: gen0048 は carrot 機構を発火させたが最終日清算に穴が残る。(A) d27 植え carrot が d29 収穫になり、収穫した hand がシェッドに届かず carried.CARROT=6 が未換金（3 smoke seed とも）。(B) 市場売却が carried 全量を DROP 可能として SELL 数に加算し、届かない在庫へ実行されない幽霊 SELL 注文を出す。~$300/試合の forgone upside で carrot 機構最大のレバー（`control/fixes.json` FIX0020 major / gen0048#1）。carrot を d28 までに刈り d29 を丸一日 DROP+SELL 搬送に空ければ carried→~0 で実換金でき、幽霊 SELL も止まる。あわせて d29 carrot 水やり不足（FIX0019 / gen0048#0）も『d29 に生きた carrot を残さない』設計で不要化する。IDEA_POLICY: 機構の穴を塞ぐ修正（数値 sweep ではない）。
- 変更（agents/gen0050/main.py。親 gen0048 のコピー＋carrot 終盤 3 箇所のみ）:
  1. `CROP_PLANS["CARROT"]["last_plant_day"]` 27 → **26**（FIX0020(A)）。d27 植えは age2 が d29 に来るが d29 は WATER が `day < FINAL_DAY(29)` ガードで発行されず増収 0（yield=1 のまま）かつ搬送不能で死蔵する。最後の有用な carrot 植えは d26（d28 に age2 で刈れる）。
  2. carrot ripe を `age >= 3 or (day >= FINAL_DAY and age >= 2)` → `age >= 3 or (day >= FINAL_DAY - 1 and age >= 2)`（FIX0020(A)+FIX0019）。d25 植え=d28 age3（収量2=d27+d28 水やり）、d26 植え=d28 age2（収量1=d28 水やり）。両方 d28 収穫→carried→d29 の丸一日で DROP+SELL。d29 に生きた carrot が残らないため FIX0019（d29 bonus WATER）は不要になり追加しない。
  3. 最終日の carried_item 集計を、その unit の選択済み action が今ターン DROP のときだけに限定（`if _ui < len(actions) and actions[_ui] and actions[_ui][0] == "DROP":`）（FIX0020(B)）。actions は上で全ユニット分組み終わっており DROP を出すのは今ターンにシェッド上で落とす unit だけ。FIX0003（今ターン DROP 分を shed 在庫に上乗せ）は温存しつつ届かない在庫への反復 SELL（無言 no-op）を止める。
- engine 検証（.venv/.../envs/kaggriculture/kaggriculture.py）: CARROT は非 ongoing。yield は WATER が age∈[2,3]（window_start=(3+1)//2=2, max_yield_day=3）のときだけ +1（肥料時 +2、max 4）。HARVEST は `day-planted_day >= first_yield_day(2)` かつ `yield>0`、非 ongoing は収穫でタイル消滅。WATER（通常・bonus）は `day < FINAL_DAY` ガード内。
- 結果（★**50seed 完了** `records/eval_gen0050.json`・baseline records/eval_gen0048.json）:
  - **gate.pass = False。** 全体マージン **+$27.8 [−12.1, +67.8]**（点推定正だが CI が 0 をまたぐ＝**検出不能**）／
    自資金 +$26.7 [−12.8, +66.1]（同じく検出不能）／ **強帯マージン −$1.6 [−51.6, +48.4]（フラット）**・強帯資金 −$1.4 ／
    slope +3.8 ／ rating Δ 0.0 ／ too_good None ／ errors 0。
  - **重要な発見: スモーク（vs starter・弱）は +$196〜255/試合だったが 50seed プールでは +$28 に縮んだ。**
    差の正体は carrot 市場の深さ: FIX0020 が換金する carrot 10-12 units を**実対戦相手も carrot を出す強帯では
    市場が食う**（強帯マージン −$1.6＝フラット）。starter 単独スモークは carrot 市場に競合が居らず満額 $75/unit で
    売れるので過大評価だった。**「回収できる carrot の金額は carrot 市場の深さに律速され、実プールでは競り消される」。**
  - 以下はスモーク（≤8 seed＝動作確認専用。上記の通り実プールと乖離した＝方向・昇格判定には使えない実例）:
    - vs starter seed 7/14/42: エラー 0・両者 DONE。final_money gen0050 [151318/161585/130508] vs gen0048 同 seed [151122/161368/130253] = **+196 / +217 / +255**（実プールでは +$28 に縮小）。
  - **fix の直接証拠（FIX0020(A)）**: 最終 carried.CARROT **6→0**（3 seed とも）。d29 shed.CARROT peak gen0050 12/12/8（全て売れて final 0）vs gen0048 3/6/3（carried.CARROT peak 6/6/7 が死蔵）。
  - **fix の直接証拠（FIX0020(B)）**: 市場 SELL CARROT 注文数 gen0048 15-17 件（78-82 units＝同一死蔵在庫への反復注文の合算）→ gen0050 **1-2 件（10-12 units＝実配送在庫ぶんの単発注文）**。幽霊注文が消えた。
- **判定**: **検出不能（棄却ではない）＋非昇格・非提出。** `指標: pool(v0.5) ／ シード: 50 ／ 全体マージン CI: [−12.1, +67.8]（0 をまたぐ）`。
  FIX0020 は**副作用ゼロの正当な欠陥修正**（自資金 +$27・強帯フラット・slope +3.8・errors 0）だが、単体では
  改善幅が seed ブレ以下＝gate.pass=False。**LB 計測の価値もない**（王者と同型・新しい型でない・ノイズ級）→ 単独提出しない。
  ただし FIX0020 は fix 台帳で **applied（gen0050/gen0051）** として王者系譜へ引き継がれる（次に昇格する世代へ自動伝播）。
  carrot 量を増幅する Stage B（gen0049）と合成した gen0051 で「量が増えれば FIX0020 の回収額も比例して大きくなるか」を測る。
- **説明（この分野を知らない人向け 3 行）**: gen0048 は終盤に人参を植えて収穫していたが、最終日 d29 に刈った人参を売店（シェッド）まで運べず腐らせ、しかも運べない在庫を「売れる」と数えて空の売り注文を毎ターン出していた。gen0050 は人参を 1 日早い d28 までに全部刈り、最終日 d29 を運搬と換金だけに使うようにした。結果、放置されていた人参 6 個が 0 になり全部売れて、空注文（15-17 件）も 1-2 件の本物の注文に減った。
- **改善幅は seed ブレより大きいか**: **いいえ。** 対応付き自資金差 +$26.7 の CI95 [−12.8, +66.1] は 0 を含む＝改善幅は seed ブレ以下。スモーク 3 seed の +196/+217/+255（符号一貫）は starter 単独の過大評価だった。
- **目標曲線との差**: d0-26 は親 gen0048 とバイト同一（下記 leak_check）。したがって `control/targets.json` cash_curve に対する d5/d10/d15/d20 の位置は王者と同一で、本世代が触るのは d27-29 の清算のみ＝目標曲線への影響は終盤だけ。
- **ミクロ指標**（`harness/micro_audit.py --assert` seed 7/14/42）: critical-three 全て OK（noop_total=0 / unfed_days=0 / uncared_days=0、3 seed とも）。他 NG（inplace_share 0.42-0.44 / last_water_hour 23 / melon_yield 5.73-5.93 / strawberry_yield 1.63-1.73 / tile_revisit 0.017-0.024 / tile_util 0.64-0.70 / wheat_yield 3.71-3.91）は gen0048 と同一集合・ほぼ同値＝FIX0013 の強帯到達目標（--limit 対象）で本世代の新規回帰は 0。profile mean/max=0.00021/0.019s（1 秒 OK）。
- **leak_check**: gen0050 vs gen0048（同 seed の replay で player0 の action を全ターン diff）で **d0-26 は 3 seed とも diff=0**（バイト同一）。初回 diff は d27 h2（last_plant_day 27→26 で gen0048 が d27 に植える carrot を gen0050 は植えない点）。diff は d27-29 のみ（seed7 60 / seed14 51 / seed42 48 件、全て d27/28/29）＝設計どおり carrot 終盤と最終日清算だけが変わる。
- **修正台帳**: `ops/check_fixes.py agents/gen0050/main.py --show-open` = applied 14/14 検出（FIX0019/FIX0020 が新たに applied）・回帰 0・open 6。`--audit` OK（meta.json review は placeholder＝findings 空なので未登録指摘なし）。FIX0020 detect require = `ripe = age >= 3 or \(day >= FINAL_DAY - 1 and age >= 2\)` ＋ `actions\[_ui\]\[0\] == "DROP"`。FIX0019 detect require = 同 FINAL_DAY-1 ripe 行（遠征を無くす方で解決したことを機械照合）。
- **レビュー記録**: Codex レビュー未実施（Supervisor が eval 後・昇格前に実施）。meta.json review は placeholder（捏造しない）。
- **却下した小手先案**: FIX0019 を『d29 に carrot bonus WATER を足す』で単独対処する案 / 該当禁止項目＝IDEA_POLICY 数値パッチの積み増し（かつ FIX0020 の最終日清算を悪化させる）。d28 収穫で d29 遠征そのものを無くす方（ゲーム構造からの導出）を採った。
- 学び: carrot は非 ongoing で「yield を作る WATER」が age∈[2,3]・WATER 自体が d<FINAL_DAY 限定という engine 構造から、d29 に生きた carrot を残す設計は必ず損（増収 0＋搬送不能）だと導ける。最終日は「生産日」ではなく「搬送・換金日」として設計する。SELL は shed 在庫からしか約定しない（届かない在庫への注文は無言 no-op）ので、最終日 SELL 数量は『今ターン実際に DROP する在庫』で決めるのが正しい。
```
```
