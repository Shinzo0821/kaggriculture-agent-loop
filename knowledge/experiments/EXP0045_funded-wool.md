---
status: done   # cycle6(2026-09-07): 50 seed eval で gate.pass → 昇格・提出 ref=sub-17
gen: gen0045
parent: gen0044
---

# EXP0045: funded wool expansion（町抽選条件付き・SE 資金の羊増頭 ＋ FIX0014-0016）

- 日付: 2026-09-07 ／ 世代: gen0045（親: gen0044・王者 ref=sub-16）
- 仮説（IDEA_POLICY §1「畜産構成＋土地＋作付けを同じ日にまとめて動かす型変更」＋§2「未使用の観測
  unlocked_shops の YARN_STORE 軒数を頭数決定に使う」）: 羊毛だけが供給不足市場（他品目は市場律速で
  CLOSED, EXP0043。`2026-09-06_which-market-is-actually-closed.md` §6）。町抽選で YARN_STORE が 2 軒以上
  引かれた seed（約 12%）では需要 25+/日 ≫ 供給で価格が上限帯 $237-240 に張り付き、こちらが +5.3/日
  足しても在庫は I0 未満＝**自己値崩れゼロ**。そこでだけ SE($4,000) を買い羊を 4→8 に増頭すれば増産枠が
  浮く。y≤1 の町では増頭の限界収入が負〜ゼロ（設計書 §1b）なので**発火しない**。EXP0040（羊 4→8）は
  イチゴ 4 枚を削って原資を作り棄却＝「生きた品目の自供給を削る変更は相手への贈り物」。本設計は SE 購入で
  **何も削らず**頭数を足す（設計書 §3 で牛→羊スワップ・メロンカットの資金調達を数値で棄却）。
- 変更（親 gen0044 からの diff。設計書 `state/plans/2026-09-07_gen0045-funded-wool.md` §7・meta.json `changes`）:
  - **拡張本体（新機構 `funded_wool_expansion`）**: `expansion_active`（yarn≥2 かつ d12-16 窓 or SE 既取得）で
    `land_target` が 4 を返し SE($4,000)購入 → SE パスチャ 4 枚建設（(6,5)(7,5)(5,6)(6,6)）→ `sheep_target`=8 で
    羊を**空きパスチャ数キャップ付き**で 4→8 に増頭。CROP_PLANS WHEAT に SE 飼料小麦 6 枚(from_day 12)。
    room=COW_MAX+sheep_target、発火時のみ羊購入窓 d10→18。**すべて expand/se_owned/yarn≥2 でゲート、
    非発火では拡張分岐は完全に不活性**（SE タイルは 'LOCKED' なので建設・PLANT・fallback を素通り）。
  - **unfed=0 の先回り（新機構 `feed_buffer_lookahead_on_expansion`）**: 市場飼料買いを `planned_total`
    基準に、feed_buffer(SELL 抑制)を `planned_total if expand else total_placed` 基準に（Codex P1-1 修正後）。
  - **発火時のみ hands +1（新機構 `expansion_hands_bump`）**: 羊 4→8（12→16 頭）は 12 hands の hand-hour を
    超え unfed/uncared が出た（設計書 §5 の飼料在庫先回りだけでは塞がらない＝**供給でなく logistics 律速**：
    shed 小麦 15-21 個ありながら 16 頭中 1 頭が未給餌）。expand 時のみ d12 以降 hands_target を +1。
    同世代内 A/B: +0 は unfed 3 日（絶対条件違反で棄却）／+2 は unfed=0 だが日次雇用 fib コスト高／
    +1 が 4 発火 seed とも unfed=0 かつ最安。設計書 §8 リスク4 の v2 機構を v1 に前倒し。
    **非発火では expand=False で従来値**＝IDEA_POLICY 禁止2（単独 hands+1）ではなく拡張と束ねた発火限定の増員。
  - **FIX0014（open major → applied）**: 落とした低価値 SELL の架空代金で essential buy を組む不整合。
    実約定 SELL だけで realized 予算を組み、賄えない末尾 buy を落として枠を SELL に返す reconcile。
  - **FIX0015（open minor → applied）**: WOOL の家畜収穫解除ゲートを固定 SELL_FLOORS(120) から
    beta_sell_cap>0 に（市場売却の動的 β 判定と対称化）。非 BETA 品目は従来床のまま。
  - **FIX0016（open minor → applied）**: beta_sell_cap の int() を正しい floor（int(I0+root)-market_inv+1）に。
- **結果**（`records/eval_gen0045.json`・baseline gen0044・pool sparring・seeds 50・jobs 8）:
  - pool.rating **631.6 ±18.9** ／ gate.rating_delta **+0.0** ／ too_good **None** ／ errors 0。
  - 全体マージン差 **+$854.2 [+585.6, +1122.8]**（n_pairs 1100）＝ CI 下限 >0。
  - 対応付き資金差（自分） **+$629.9 [+161.3, +1098.6]**＝正（絶対額も下がらない）。slope_delta **+113.1**。
  - **強帯マージン差 +$884.3 [+577.6, +1191.1]**（判定に使う。点推定 正・CI 下限も >0）／
    強帯資金差 +$590.3 [−26.4, +1207.0]（診断・点推定 正）／ 強帯 slope +119.2。
  - **発火/非発火別の分解は未算出**: 全プールのゲートが CI 下限 >0 で clean pass したため 3 分岐は分岐1
    （昇格）に確定し、分解は判定に不要だった。**FIX0014-0016 と拡張の寄与分離は knowledge の宿題**として
    未解決リスク2 に残す（下）。次に売買を触る世代で FIX0018 と併せて分離計測する価値。
- **判定**: **昇格**（gate.pass=True）。**提出 ref=sub-17**（cycle6・当日 UTC 実提出 2/5・[auto] 2/5）。
  `指標: pool(v0.5・マージン) ／ シード: 50 ／ CI: 全体 [+585.6, +1122.8]・強帯 [+577.6, +1191.1]`。
- **説明（この分野を知らない人向け 3 行）**: 羊毛は「町が毎日買うので売り切れやすい唯一の品目」。町に
  羊毛屋が 2 軒以上できた運のいい試合（約 8 回に 1 回）でだけ、土地を買い足して羊を倍にして羊毛を増産する。
  それ以外の試合では一切何もしない（親と同じ動き）ので、当たれば得・外れても損しない「オプション」型。
- **改善幅は seed ブレより大きいか**: **YES**。対応付き資金差 +$629.9 の CI 下限 +$161.3 が 0 を超える。
  発火率 12% で検出不能に沈むリスクを懸念していたが、拡張＋FIX0014-0016 の束で全体 CI 下限 >0 に届いた
  （＝薄い発火でも束で検出できた or FIX の寄与が効いた。分離は未解決リスク2）。
- **目標曲線との差**（control/targets.json d5/d10/d15/d20）: 拡張は発火 seed の d13 以降だけ生産を増やす。
  非発火・y≤1 は親と同じ現金曲線。発火 seed の羊毛収入は d19 以降に立ち上がる（羊 age6→産出）。eval 後に確認。
- **ミクロ指標**（micro_audit --assert。vs starter・発火 seed 7/10/14/15）:
  - **合格ライン: noop_total=0 / unfed_days=0 / uncared_days=0 — 発火 4 seed すべて OK**（Codex P1-1 修正後に
    再検証）。replay に SE unlock・羊 8 頭・SE パスチャ 4 枚・SE 小麦植付（計画6＋fallback で 21 枚）・
    **WOOL final_shed=0**（d29 産の羊毛も換金）を確認。
  - 非発火 seed: 拡張機構は完全不活性（12 seed とも max_sheep≤4・SE 未 unlock・SE タイル 0＝**拡張リーク 0**）。
    seed 4 は親 gen0044 とバイト単位で完全一致（$156,637）。**ただし FIX0015 で非発火でも売買が分岐する
    seed がある**（seed 0: gen0045 $93,561 vs 親 $99,001。vs starter 単一 seed なのでノイズだが要監視。下記リスク2）。
  - NG（inplace_share/tile_util/last_water_hour/各収量・tile_revisit）は FIX0013 の強帯到達目標で、親
    gen0044 も同一集合が NG＝拡張による新規回帰なし（SE 増設で tile_util はさらに低下・tile_revisit は
    0.016→0.024。--limit 対象）。profile mean/max = 0.0002/0.0122s（1 秒 OK）。static_check OK。
    check_fixes applied 11/11・回帰 0・open 7。
- **レビュー記録**: Codex（gpt-5.6-sol / reasoning high）2026-09-06 UTC 実施（thread <redacted-id>・7 観点・
  SHA 2c3ea8f6 一致）。**即死級 0（P0 なし）→ 昇格可**。leak-free 性・hands+1 の発火限定・FIX0015/0016・
  例外パス・計算量・終盤清算は実コードで確認済み。指摘 P1×2/P2×1:
  - **P1-1（major・fixed）**: feed_buffer が購入済み・未配置の羊を予約から落とす（買った羊が placed にも
    追加予定にも数えられず予約が 50→38 へ一時減＝unfed リーク＝設計の unfed=0 保証の穴）。修正:
    `feed_buffer=(planned_total if expand else total_placed)*3+2`（1212）。発火 4 seed 再検証で unfed/uncared/
    noop=0・非発火 seed4 は親と厳密一致を維持。Codex 再確認（同 thread）で解消を確認。
  - **P1-2（minor・deferred → FIX0018 open 登録）**: FIX0014 の reconcile が実約定可能性を保証しない
    （kept SELL の 0.7 掛け過小評価で正当な重い購入を落としうる・RESERVE 未再確認・nb-=1 が数量注文を
    全落ち）。即死級でなく、gen0044 の raw no-op よりは安全側（枠を SELL に返す）。売買を触る次世代で対処。
  - **P2（trivial・fixed）**: 設計書 §7/§8 が hands+1・FIX 同梱前の記述のまま／hands 機構の origin 表現。
    設計書 §7 に実装追記・meta の origin を capacity_for_unfed に改めた。
- **却下した小手先案**（IDEA_POLICY・設計書 §9）:
  - 羊 6 頭を無条件で試す / 禁止4（単一パラメータ sweep）＋ EXP0040 で棄却済み。
  - 拡張窓 d16 の ±1 日調整・YARN_MIN=1/2 の比較評価 / 禁止1・4（閾値微調整・sweep）。
  - hands 12→13 単独 / 禁止2（hands ±1）。※本世代の hands+1 は拡張と束ねた発火限定なので該当しない。
  - 牛→羊スワップ / gen0037 で用量反応つき棄却。メロン第2波カットで資金調達 / gen0035/0037/0040 の
    「供給を削る」失敗形。相手農場の羊数で y=1 増頭を判定 / y=1 の限界 ROI が SE コストで負のまま。
- **未解決リスク（eval 読解時に必ず見る）**:
  1. **発火率 12% は薄い**。50 seed で発火 ~6 本。拡張効果が発火 seed +$3k 級でも全体 CI 下限 >0 に届くかは
     微妙。**検出不能（CI が 0 をまたぐ）なら棄却でなく「検出不能」として CLOSED.md 再検討へ**。
  2. **FIX0014-0016 が全 seed の売買を変える＝拡張効果と分離できない**。設計書 §8 の「非発火=0 variance」
     前提は崩れている（meta.json `leak_check`）。50 seed eval のマージン差は**拡張＋売買修正の束**。特に
     **FIX0015 が非発火 seed0 で −$5,440（vs starter・単一 seed）** と負方向に振れた点は要監視。もし
     gen0045 が gate.pass せず、かつ発火 seedサブセットは正なのに全体が負なら、**FIX0014-0016 を別の掃除
     世代に分離して単独計測する**（拡張コードは leak-free 確認済みで分離容易）。
  3. 発火後の抽選分岐（設計書 §1a）: SE 解禁で d15+ の雑草・抽選 rng が親とずれる。発火サブセットの CI は参考値。
- 学び:
  0. **羊毛は「増産の壁（市場律速）」が唯一立っていない品目**（EXP0043 でイチゴ増産が CLOSED した後の消去法）。
     発火が seed の 12% に限られる「下振れ 0 のオプション」型だったが、拡張＋同梱 FIX の束で全体マージン
     +$854・強帯 +$884（CI 下限とも >0）を出して昇格した。**薄い条件付きレバーでも、下振れ 0 なら束ねて
     計測すれば検出できる**（発火率が低くても非発火で親と同一なら分散は増えない）。
  2. **昇格の clean pass では発火/非発火分解は判定に不要**。分解は 3 分岐（gate.pass / 検出不能 / 負）の
     分岐選択のための道具であって、分岐1に確定した以上は攻略上の宿題（寄与分離）に格下げしてよい。
  1. **設計の unfed=0 機械保証は「飼料在庫の先回り」だけでは足りず hand-hour が律速だった**（P1-1 とは別に、
     hands+1 が必要だった）。増頭は飼料だけでなく労働 logistics も同時に増やさないと unfed が出る。
