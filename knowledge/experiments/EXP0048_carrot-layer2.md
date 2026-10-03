---
status: done
gen: gen0048
parent: gen0047
---

# EXP0048: carrot 窓内 DIG/PLANT を層2に再分類（Stage A・非発火の解消）
- 日付: 2026-09-08 ／ 世代: gen0048（親: gen0047。コード基盤は gen0047 のみ carrot 機構を持つ。王者系譜は gen0045≡gen0046+FIX0018）
- 仮説: carrot 窓内の WEED-DIG（層3 2.6）と PLANT（層4 2.82）を『収量を作る行動』の経済クラス＝層2（イチゴ HARVEST と同層）に再分類すれば、d24-27 の潤沢な IDLE hand-hour（反証実測§1: 層≤2 稼働 30%・13-24 IDLE/日）で DIG→PLANT が LAST_PLANT_HOUR(20) 前に回り、gen0047 の非発火（植付 0）を潰して carrot 2-3 個/枚を純増できる。IDEA_POLICY §4（層所属の決め直し。数値 sweep ではない）。主目的は carrot 機構の end-to-end 発火実証（Stage B の前提）。
- 変更（2 箇所のみ、他作物・非 carrot コードは不変）:
  1. CROP_PLANS["CARROT"]["plant_pri"] 2.82 → 2.24（層4→層2。イチゴ HARVEST hpri 2.2 の直上＝収穫がタイで勝つ）。carrot の PLANT todo 発行でのみ参照。
  2. 予定タイルを塞ぐ WEED の DIG todo を carrot だけ `(2.22 if crop=="CARROT" else 2.6)` に。他作物予定地 DIG は 2.6 のまま。層2 内 2.22(DIG)<2.24(PLANT) で DIG 先導、両方>2.2(全 HARVEST) で収穫がタイ勝ち。
- 結果（`records/eval_gen0048.json`・50 seed・baseline gen0045・pool sparring・too_good None・errors 0）:
  - pool.rating 631.6 ±18.9 ／ rating_delta 0.0
  - **全体マージン差 +$313.2 [+218.1, +408.4]（CI 下限 >0）** ／ 自分の資金差 +$362.0 [+268.9, +455.1] ／ slope_delta +51.7
  - **強帯マージン差 +$353.7 [+226.8, +480.5]（点推定正・CI 下限 >0）** ／ 強帯資金差 +$416.1 [+292.1, +540.1] ／ 強帯 slope +59.4
  - スモーク（≤8 seed＝方向判断には使わない）: vs starter seed 7/14/42 final_money [151122/161368/130253]（gen0047 比 +$336〜+$632）。
- **判定**: **昇格・提出（新王者）**。指標: pool(v0.5) ／ シード: 50 ／ CI: 全体マージン [+218,+408]・強帯マージン [+227,+481]。gate.pass=True かつ強帯マージン点推定 +$354 ≥0（CI 下限も >0）。提出 ref=sub-18（--reason promote・2026-09-07 UTC・当日 1/5・[auto] 1/4）。期待 +$400-700 の下端付近だが「発火実証・マージンも検出可能」で当夜ループの分岐1（clean pass）。carrot 機構を王者系譜に載せた（Stage B の前提）。
- **説明（この分野を知らない人向け 3 行）**: 終盤に空いた畑へ人参を植える行動が、gen0047 では「後回し」の優先度クラスにいたため、忙しいイチゴ収穫に押されて一度も実行されなかった。gen0048 はその「畑を耕す・種を植える」を収穫と同じ「稼ぎを作る仕事」クラスに格上げした。結果、seed 7/14/42 とも人参の植付が 7 回ずつ実際に走り、d28-29 に 78-82 個を収穫・売却するようになった。
- **改善幅は seed ブレより大きいか**: はい。対応付き資金差 CI 下限 +$268.9 > 0（50 seed）。マージン CI 下限 +$218.1 > 0。単シード ±$30k のブレを 50 seed 対応付きで抜けている。
- **★発火検証（本世代のゲート）**: carrot PLANT が d24-27 で発火。seed 7/14/42 とも **7 件（gen0047 は 3 seed とも 0 件）**、内訳 seed7/14 {d25:2,d26:3,d27:2}・seed42 {d25:1,d26:4,d27:2}。→ 非発火（BLOCKED_NONFIRING）を解消。
  - **★訂正（Codex P1-2 で判明）**: 発火当初 meta に書いた「carrot SELL 78-82 units」は市場注文の合算であって実約定量ではない。3 smoke seed とも最終 carried.CARROT=6 / shed.CARROT=0（最終日 d27 植え carrot を d29 に収穫した hand がシェッドに届かず未換金・~$300/試合）。発火の正しい証拠は PLANT 7 件＋eval の純マージン +$313 であって SELL units 数ではない。この未換金は carrot 最大の残レバーで gen0050（FIX0020）で回収する。
- **目標曲線との差**: carrot 収穫は d28-29 のみで d5/d10/d15/d20 の現金曲線には影響しない（窓 (24,27)）。d0-23 は親 gen0046 とバイト同一（leak_check 参照）。
- **ミクロ指標**（スモーク seed 7/14/42、micro_audit --json。基準は targets.json の micro＝FIX0013 強帯到達目標）: 利用率 tile_util 0.641/0.642/0.703（目標 0.83 未達＝gen0047 と同水準・回帰なし）／ 未使用タイル: none_reported ／ 収量: melon 5.733/5.733/5.933・strawberry 1.629/1.629/1.729・wheat 3.711/3.663/3.913（いずれも gen0047 と同値、strawberry 回帰なし）／ 3歩以上% moves3plus 0.127/0.129/0.137（OK）／ 最終 WATER 時刻 23（gen0047 と同値・回帰なし）。critical-three（noop/unfed/uncared）は 3 seed とも 0。micro NG 集合は gen0047/0045 と同一（新規回帰 0）。
- **レビュー記録**: Codex（gpt-5.6-sol / high・2026-09-07 UTC・thread <redacted-id>）。**P0（即死級）0**。P1×3 すべて非致命・deferred（実コード＋replay で検証済み）:
  - P1-1（minor→FIX0019）: 最終日 d29 は carrot の bonus WATER が `day<FINAL_DAY(29)` ガードで出ず、d27 植え=1 個止まり（想定 2-3 個/枚を下回る）。単独修正は最終日清算を悪化させるので FIX0020 と同時に gen0050 で。
  - P1-2（**major**→FIX0020）: 最終日収穫の carrot がシェッドに届かず未換金（carried 6/shed 0・~$300/試合）＋ carried 在庫を売却可能量に数える幽霊 SELL。carrot 最大レバー。Stage B(gen0049) で増幅（carrot 7→18-21）。
  - P1-3（minor→既存 FIX0008 に gen0048#2 追記）: WEED 種先読みが DIG 実行可能性を予約せず種 2 個/試合が死蔵（買 9・PLANT 7）。最終窓 d27 h20+ でも DIG todo が残る。
  - P2×3（trivial・コメントのみ・main.py SHA 固定のため未修正・gen0050 で整理）: 層2 の 2.22/2.24 は同距離タイブレークが正確／「decay 済みのみ」は水切れ死・自然雑草でも WEED になるので厳密には強い（ただし生きたイチゴを掘らない保証は成立）／ MAX_YIELD[CARROT]=3 は無施肥上限で正しいが engine 実定数は 4 でコメントが不正確。
  - 機械記録は meta.json review（candidate_sha256 3b7aa7dc…・blocking_resolved=true）。ledger 反映済み（--audit OK）。
- **却下した小手先案**（2026-09-07 分析§4 の表を参照）: carrot plant_pri 2.82→2.5 の数値下げ / §4 単一 sweep・層2飽和は数値では越えられない。LAST_PLANT_HOUR 20→21/22 / §1 微調整・当日水やり不能で確定枯れ。carrot windows sweep / §1・§4・decay 日は動かない。STRAWBERRY buy_cap 単独変更 / §4 単一 sweep。FALLBACK_CROP を終盤 carrot / §5「常時○○」型。終盤 hands +1 / §2 hands±1・EXP0039 で −$8,656 棄却済み。イチゴ 44 枚増枚 / CLOSED（EXP0035/0043 強帯市場律速）。
- 学び: 行動の優先度は数値 sweep でなく「その行動がゲームのどの経済クラスに属するか（収量を作る＝層2）」で決めるべき。gen0047 の非発火は decay タイミング（P1）と層 starvation（P2）の複合だったが、P2 は層所属の決め直しだけで解けた（decay 前提 P1 は Stage B でイチゴ波を前倒しして接続する）。carrot 機構が end-to-end で回ることを実証＝Stage B の前提が成立。d0-23 の親同一性（下振れ 0 のオプション構造）も維持。

## リンク
- 設計: knowledge/analysis/2026-09-07_carrot-nonfiring-and-next-lever.md §2 Stage A ／ knowledge/analysis/2026-09-08_stagea-preflight.md
- 前世代: EXP0047_fast-carrot-nonfiring.md（非発火の finding）
