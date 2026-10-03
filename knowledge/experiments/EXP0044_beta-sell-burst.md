---
status: done   # 2026-09-07 cycle4: eval 完了・判定=昇格・Codex レビュー済み・ref=sub-16 提出
gen: gen0044
parent: gen0042
---

# EXP0044: 売り時 burst（WOOL/MELON の限界収入を価格式から解く / H2）

- 日付: 2026-09-07 ／ 世代: gen0044（親: gen0042）
- 仮説（IDEA_POLICY「未使用の観測の利用／労働割当の構造変更」＝出口の詰まった品目の**売り方**を変える。
  増産ではないので gen0043 の「イチゴ市場律速」の壁には当たらない）:
  上位 #1（我都先道歉）は WOOL/MELON の**限界価格を base の 0.5-0.55 より下へ落とさず持ち越し**、
  敗者が先に床までダンプする（`knowledge/analysis/2026-09-07_top12-endgame-sell-rates.md` の #1 vs #2
  2 戦の実測）。売り崩しの深さの差＝勝敗差。SELL 量 N を「最後の 1 個の限界価格 ≥ β·base（β=0.55）」で
  価格式から解けば、(1) scarcity/回復局面では price≥base で条件が常真＝生産律速の少量売り（勝者挙動を
  自動再現）、(2) glut では marg=β で止めて持ち越し、(3) 町 sink のある WOOL は価格が回復した日に自動で
  burst（β キャップの毎ターン評価で回復日に条件が再び真になる）、(4) sink≈0 の MELON では同式が
  「終盤まで床へ落とさない累積キャップ」として働く。terminal 持ち越しは全損なので d25-27 は β を
  DUMP_DAY(28) へ向け 0 へ逓減し、d≥28 は価格を問わず全量清算。
- 変更（親 gen0042 からの diff。3 点。詳細は `agents/gen0044/meta.json` の `changes`）:
  - **H2 本体（新機構 `beta_marginal_sell_wool_melon`）**: WOOL を SELL_FLOORS の在庫予算パスから、
    MELON を ALWAYS_SELL の全量売りから外し、両者を BETA_SELL の β 解法パスに載せた。
    `beta_sell_cap(item, market_inv, day)` がエンジンの glut 価格式 `price=base−amp·(inv−I0)²`
    （`amp = above_target·base/T²`、WOOL/MELON とも above_func='sq'）を N について解く:
    `N = floor(I0 + sqrt((1−β)·base/amp) − market_inv) + 1`。β=0.55（BETA_SELL_FRAC・単一値・sweep しない）。
    d<25 は β=0.55、d25-27 は DUMP_DAY へ向け線形に 0 へ逓減、d≥28・シェッド溢れ(SHED_DUMP)は全量。
    amp はハードコードせず engine MARKET_PARAMS の base/T/above_target から導く（WOOL amp=0.05805・
    MELON amp=0.01）。明示 burst 間隔（2 日）は入れない — β キャップの毎ターン評価で回復日 burst が
    自動再現される（Analyst 実測の推奨: 間隔=1 でも WOOL 回復は拾える）。
  - **FIX0006（gen0043 から移植・major）**: イチゴ生産日の施肥を、まだ水やり前でも bonus_water が出る
    株は FERT_PRI_PAIR(層2)に上げて同じ訪問で水＋肥料の対を閉じる。gen0043 の他 diff（イチゴ31枚・
    窓(4,15)・FALLBACK STRAWBERRY）は**市場律速で棄却済みのため持ち込まない**（EXP0043）。
  - **FIX0009（open minor → applied）**: 市場注文を pre（開幕 denial buy, slot 0 固定）/ sells / buys の
    3 リストに分け、essential buy 用スロットを確保してから SELL を品目価値（BASE_VALUE·qty）降順で詰める
    （keep_sells = MARKET_SLOTS − len(pre) − len(buys)）。溢れたら安い品目から落ち、HIRE/BUY_SEED が
    押し出されない。mest 更新順は SELL→BUY のままで購入の資金ゲートは不変。H2 と同じ SELL サブシステム
    なので同根で同梱。
- 結果（`records/eval_gen0044.json`・seeds 50・seed_base 1000・baseline gen0036・pool 11 体×50×両席=1100 戦。
  2026-09-07 cycle4 に読解）: pool.rating **631.6 ±18.9**・rating_delta **0.0**（既知の飽和）・win_rate 0.273・
  **errors 0**・**too_good なし**。**全体マージン差 +$2,256.3 [+1,704.8, +2,807.8]**・自分の資金差 +$1,261.9
  [+12.9, +2,511.0]・slope_delta +123.5。**強帯マージン差 +$2,365.2 [+1,686.5, +3,043.9]（点推定正・CI 下限 >0）**・
  強帯の自分の資金差 +$993.7 [−649.9, +2,637.2]（診断用・0またぎ）・強帯 slope +68.4。
  相手別（自分の資金 delta vs gen0036）: 強帯で rayk_c95 **+$5,779**・boatlee_v16 +$2,014・prvsiyan +$1,229・
  pilkwang +$1,244・kaito +$581・boatlee_v29 +$143 が正、sokolovsky −$1,743・tetsutani −$1,298 が負
  （8 体中 6 体で正）。弱・自系統も全て正（starter +$2,588・gen0018 +$2,563・georgy +$781）。
- **判定**: **昇格**（提出 ref=sub-16・2026-09-06 UTC） — `指標: pool(v0.5・マージン) ／ シード: 50 ／
  全体 CI: [+1,705, +2,808] ／ 強帯 CI: [+1,687, +3,044]`。`gate.pass=True`。判定の主眼＝**強帯マージン点推定
  +$2,365（正）** で前進、かつ CI 下限も 0 超。gen0042 単独が −24（中立）・FIX0006 単独は micro 級なので、
  マージン差はほぼ H2（売り方の変更）に帰属できる。gen0031(+$538)・gen0036(+$9,159 だが親が別) と比べても
  堅実な前進で、gen0031 と違い**自分の絶対資金も正**（CI 下限は +$13 と薄いが 0 超）。
- **説明（この分野を知らない人向け 3 行）**: 羊毛とメロンを「いくつ売るか」を、値段が base の 55% を割らない
  ぎりぎりの個数で毎ターン計算して売る（値崩れの底では売り控えて持ち越す）ようにした。羊毛は町が毎日
  買って値が戻るので、戻った日に自然にまとめ売りになる。最終盤（残り数日）は腐らせないよう全部売り切る。
- **改善幅は seed ブレより大きいか**: **はい。** 全体マージンの対応付き CI 下限 +$1,705・強帯マージンの
  CI 下限 +$1,687 でともに 0 を大きく超える（50 シード）。自分の資金は CI 下限 +$13 で 0 は超えるが薄い
  ＝利得の主因は「マージン（自分−相手）」で、相手の希少プレミアム削り（売り時 denial）が効いている。
- **目標曲線との差**（control/targets.json d5/d10/d15/d20）: H2 は売り方の変更で作付けを触らないため生産の
  現金曲線（d5-d20）は親 gen0042 とほぼ同じはず。差が出るのは売却タイミング（glut 日の売り控えと回復日
  burst）。50 シード eval と daily_report の対応付きマージンで確認する。
- **ミクロ指標**（micro_audit s42 --json。括弧内 親 gen0042 s42。詳細は meta.json `smoke`）:
  - 合格ライン: noop_total=0 ／ unfed_days=0 ／ uncared_days=0 の 3 つとも **OK**。audit_replay s42 で
    d1-28 unfed/uncared=0。
  - strawberry_yield 1.837(1.724) ・ melon_yield 5.933(5.867) は FIX0006 で改善。
  - NG（inplace_share 0.4133<0.44・tile_util 0.6926<0.83・last_water_hour 23>14・各収量）は FIX0013 の
    強帯到達目標で、親 gen0042 も**同一 6 件が NG＝H2 による新規回帰なし**。
  - 品目別（s42, gen0044 vs gen0042）: WOOL sold 120/120 rev $9,997/$9,960・final_shed 0/0 ／
    MELON sold 89/88 rev $20,990/$20,745・final_shed 0/0 ／ MILK rev $61,653/$60,630 ／
    STRAWBERRY sold 191/181 rev $50,705/$48,262。**全品目で売上が下がらず WOOL/MELON の terminal
    在庫 0**（腐らせ・DUMP_DAY 突入なし）＝β キャップの落とし穴（持ち越し腐敗・DUMP 突入・売り逃し）を
    回避できている（スモークの範囲では）。
  - profile mean 0.0002s / max 0.0198s（1 秒 OK）。static_check OK。check_fixes applied 8/8・open 5 minor。
- **レビュー記録**: Codex（gpt-5.6-sol / reasoning high）2026-09-06 UTC 実施（thread <redacted-id>・SHA 一致・
  7 観点）。**即死級 0**（1100 戦エラー 0・全パス dict フォールバック・sqrt/除算は現定数で安全・BETA_MKT
  未登録は None→cap or 0 で安全）。指摘 P1×3/P2×1 はすべて非致命で **deferred**（`meta.json` review・
  `control/fixes.json` FIX0014-0017・`knowledge/FIXES.md`）→ 昇格。実コードで一件ずつ検証済み:
  - **FIX0014（major）**: FIX0009 の keep_sells 切り捨てと mest 計上の不整合。全 SELL 代金で mest を積んで
    から低価値 SELL を落とすので、落とした架空代金で組んだ土地/動物購入が資金不足で無言 no-op しうる
    （重い購入日で keep_sells が 1-2 に絞られ、落とす代金が RESERVE=400 を超える時）。aggregate は通るが
    seed 単位で取りこぼす。gen0045 が売買を触るので同時修正。
  - **FIX0015（minor）**: WOOL の収穫解除ゲート(L626)が固定 SELL_FLOORS($120)のままで β 動的売却と非対称。
    $110-119 帯・d25-27 逓減床では羊上在庫が d28 強制収穫へ先送り。主戦場（WOOL $200+）では非束縛。
  - **FIX0016（minor）**: beta_sell_cap の int() が負数を floor でなく 0 方向へ切り捨て、境界で cap 0 の
    ところ 1 個売る。修正 `int(I0+root)-market_inv+1`。
  - **FIX0017（minor）**: β は共有市場の soft bound（相手の同時売却で実約定が β·base を割りうる）。エラー
    でなく β が甘くなるだけ。主戦場では非束縛。共有市場の構造上ゼロ化不可。
  - **Codex の追加所見**: β=0.55 の最適性・β 単独寄与（FIX0006/0009 同梱ゆえ分離不可）は確認できず。ただ
    amp のエンジン導出・market.inventory 参照元・base/T/above_target・d28/d29 清算順は一次情報と一致を確認。
- **却下した小手先案**:
  - β の sweep（0.3/0.55/0.8 を評価で選ぶ）/ IDEA_POLICY「単一パラメータ sweep」禁止。β=0.55 は勝者 #1 が
    非終盤で割らなかった限界価格の床の実測クラスタ（WOOL 0.51-0.60 / MELON 0.50-0.59）から 1 回固定。
  - 明示 burst 間隔ロジック（2 日タイマー）の追加 / β キャップの毎ターン評価で回復日 burst が自動再現され、
    タイマーは冗長（Analyst 実測: 間隔=1 でも WOOL 回復を拾う）。
  - MILK/FERTILIZER の売り方も β 化 / β・amp は WOOL/MELON でしか実測していないため、他品目を変えると
    eval デルタが H2 に帰属できなくなる。denial dump（gen0037）はそのまま残す。
  - イチゴの売り時も burst 化 / STRAWBERRY は市場律速（gen0043 で確定）。売り方より枚数の壁が先。今回は触らない。
- 学び:
  0. **売り時 burst は昇格した（王者比マージン +$2,256・強帯 +$2,365）。** gen0043 で「増産は市場律速」と
     閉じた後、**同じ生産量で売り時を変える**方向が強帯で効くと実証できた。利得の主因はマージン（自分−相手）
     で、自分の資金は薄く（CI 下限 +$13）相手の希少プレミアム削りが半分を占める＝**売り時は denial レバー
     でもある**（gen0037 の投げ売り denial とは逆に「相手が床までダンプする前に持ち越す」形の denial）。
  1. gen0043 で「増産は強帯戦で市場律速」と確定したので、残る攻め筋は**同じ生産量で単価×売り時を上げる**
     方向。ep 106190289 の惨敗解剖（`2026-09-07_ep106190289-blowout.md`）も、負けの主因が「メロンを
     ピーク 270 で売り抜けず底 60 で放出」＝**売り時**だったと構造で確認している。H2 はこのレバーを直接突く。
  2. 「上位は床でも投げ続ける」（2026-09-06 版）は**投げ続けた敗者側**の挙動だった。#1/#2 帯を分解すると
     勝者は限界価格を 0.5 前後で止めて持ち越す。**品目の出口の余地は "勝者の挙動" で測る必要がある**
     （gen0043 の「出口の余地は相手の型込みで測る」の続き）。
  3. WOOL（町 sink あり＝価格回復）と MELON（sink≈0＝一方通行）で最適挙動が構造的に二分される。同じ
     β キャップ式が、WOOL では「回復日 burst」・MELON では「床落ち防止の累積キャップ」として別の働きを
     する。amp を engine パラメータから導くことで両者を 1 本の式で扱えた。
