---
status: done   # 2026-09-13 c2: 50seed eval(12体新baseline 6e07bb6a)で決定的棄却
gen: gen0055
parent: gen0051
---

# EXP0055: ガチョウ（卵）＝唯一の非競合市場で gen0051 の自資金・slope を回復する
- 日付: 2026-09-10 ／ 世代: gen0055（親: gen0051＝現王者）
- 仮説（`knowledge/IDEA_POLICY.md` §1「畜産構成の変更」）: gen0051 は対応付きマージンで勝つが
  **自資金 `money_delta_paired −243.4`・後半 `slope_delta −331.1`** が沈む「相手には勝つが自分が
  伸びない」型（王者交代の留意点・DIRECTIVES 2026-09-10）。Analyst の解剖
  （`knowledge/analysis/2026-09-10_gen0051-endgame-flatline.md`）で **主因は「売り方」でも「生産量」でも
  「終盤労働」でもなく、premium 3品（乳・羊毛・イチゴ・メロン）が共有市場で床値に叩き合われる価格競争**と
  確定した（同一 gen0051 が無競争 georgy 相手には乳 216 個を平均 $238・床値 0 で売り切るが、競合 boatlee
  相手では同じ 216 個が平均 $24-47・床値 54-156 個）。**卵は engine 上唯一の非競合市場**（boatlee は卵 0 個・
  上位B中央値も 74 個どまり）で `GOOSE first_yield_day=4 / interval=1`（設置 4 日後から毎日産卵）。
  → **premium 売却に一切触れず（＝denial マージンを壊さず）、遊休した終盤労働を相手非依存で埋め、
  自資金と slope を素直に上げられる唯一のレバー**。乳ルーティング（当初の第一候補）は §2 で denial を
  壊すため棄却、carrot 跡地確保は次点。
- 変更: gen0051 のコピー ＋ **ガチョウ 3 羽（COOP + EGG）の配線のみ**。premium 作物・全 4 品の売却・
  carrot ローテ・骨格（土地/牛羊/hire 曲線）は 1 行も変えていない。詳細は `agents/gen0055/meta.json`
  の `changes` / `mechanisms.goose_egg_market`。要点:
  - `ANIMALS` に `GOOSE`（cost 300 / product EGG / last_buy 20 / max_held 4）。`carried_animals`/`owned`/
    room/PLACE ループは `for a in ANIMALS` 経由で自動的にガチョウを会計に含む。EGG は gen0051 で既に
    `ALWAYS_SELL` 配線済み。
  - `COOP_TILES` 新設＝ **NE x=8 列の低価値自給小麦 (8,2)(8,3)(8,4) を `CROP_PLANS["WHEAT"]` から削除して
    転用** ＋ SE 予備 2 枚（LOCKED 中は素通り）。NE パスチャ列（x5-7）隣接で同一動物ゾーンの hand が牛と
    一緒に給餌でき、シェッドからの小麦運搬も最短。
  - `goose_target=3`（d14+）・COOP 前日建設・購入（afford ＋ empty_coops キャップ）・PLACE を empty_coops へ・
    fallback reserved に COOP 追加 ＋ **発火限定 +1 hand（d13-28）**（gen0045 の funded expansion と同型。
    COOP を x=8 に co-locate したことで +2 でなく +1 で 3 seed とも unfed/uncared=0 を達成＝location が本質）。
- **★c3 §4 からの逸脱（昇格前に Supervisor が採否を仰ぐ）**: c3 §4 は「crop plans と非重複の空き COOP_TILES を
  新設」を前提にしたが、**gen0051 の盤面は確実解放の 75 タイルを 1 枚残らず埋めている**（実測 seed42:
  unlocked-but-ever-empty = 0。唯一の空き (4,3) すら fallback 小麦が埋める）。SE の空きは expansion（≈12%）でしか
  解放されず「全 seed で発火」を満たせない。従って全 seed で COOP を建てるには何かを退けるしかなく、
  **最も価値の低い NE 自給小麦 3 枚を退けた**。根拠: 小麦は**非競合**（vs georgy $39・vs boatlee $41 で価格ほぼ
  同一）なので減産は相手への利得供与（原理 3）に**ならない**／小麦増産は EXP0038 で +$44 [CI −1,213, +1,301]＝
  限界価値 ≈ 0／premium・パスチャ・carrot は無傷。逸脱の妥当性は eval 後の自資金・slope で判定する。
- 結果（2026-09-13 c2・`records/eval_gen0055.json`・50seed・12体新 baseline `6e07bb6a`・v0.6）:
  **決定的に悪化。** `gate.pass=False`（pass_route=None）。
  - rating_delta **−131.3** [−181.8, −80.8]（rating_informative=True・有意にレート劣化）
  - margin_delta_paired **−2825.7** [−3259.8, −2391.5]（CI 全域 < 0）
  - **money_delta_paired −3307.3** [−4355.2, −2259.3]（＝主題「自資金回復」の逆・自資金がむしろ下がった）
  - slope_delta **+109.1**（唯一の正だが小・弱帯 slope）
  - **強帯マージン −2850.7** [−3189.1, −2512.3]／強帯資金 −3645.2／強帯 slope +9.0
  （前回 20260910 の eval は 13体 pool 9f4aa362＝reform と衝突し無効。この 12体 eval が正）
- **判定**: **棄却（検出不能ではない。CI が全域 0 未満の決定的悪化）** —
  `指標: pool(v0.6) ／ シード: 50 ／ margin CI: [−3260, −2392]`
- **説明（この分野を知らない人向け 3 行）**: 王者は「相手を安売り競争に巻き込んで勝つ」が自分の稼ぎは
  横ばいだった。牛乳やイチゴは相手も売るので値崩れするが、**卵だけは誰も作っていない**ので高く売れる。
  だから卵を産むガチョウを 3 羽足して、値崩れしない出口で自分の稼ぎだけを増やそうとした。
- **改善幅は seed ブレより大きいか**: 未取得（50seed eval で `money_delta_paired` の CI 下限が 0 を
  超えるかを見る。卵は自資金を直接押し上げるので gen0051 の弱点 −243 に最も素直に効く見込み）。
- **目標曲線との差**: c3 実測で終盤 slope d25→d29 = $1,591/日（s42）に対し上位B中央値 ≈$5,482/日。
  卵は初売り d19-20 から終盤（PASS 35-50% の帯）を埋めるので d24→d29 の傾きを狙う。eval 後に
  `audit_replay --targets` で d 別の追いつきを確認する。
- **ミクロ指標**（スモーク seed 42。決定論なので断定してよい部分のみ）: check_fixes applied **14/14**・
  open 6（gen0051 と同一・新規回帰 0）／ `micro_audit --assert` の **noop_total / unfed_days / uncared_days
  = 0**（seed 7/14/42 全て）／ never_used_tile 0（COOP は使われる）／ strawberry_yield 1.887→1.792（微減・
  両世代とも <2 の NG＝ガチョウ労働トレードオフ。残る NG 集合は gen0051 とバイト同一＝FIX0013 強帯目標）／
  profile max **0.0103s**（<1.0）／ **卵 70/76/74 個売却・ガチョウ 3 羽設置＆給餌・COOP 3 棟・初売り d19-20**
  （＝レバーが全 seed で発火することの確認）。
  - スモーク final_money vs starter: 121913/144046/102789（参考 gen0051 同 seed 149253/155185/103829）。
    **vs starter で下がるのは想定内**（非競合なので premium が満額 ~$240・そこへ $50 卵に労働を割くのは悪
    トレード）。**競合プールでは premium が床値 $24-47 に潰れるので卵への振り替えが正へ反転する**見込み＝
    これが仮説の核。**スモークの資金で「改善/悪化」を判定しない**（検出限界・非競合アーティファクト。CLAUDE.md）。
- **レビュー記録**: 未実施（Codex レビューは eval で `gate.pass` を確認してから昇格前に実施。meta.json の
  `review` は意図的に absent＝未実施を捏造しない）。**逸脱（小麦 3 枚転用・+1 hand）と tuned 定数
  （GOOSE_START=14 / hands_bump=1 / COOP x=8）はレビュー観点に含める**。
- **却下した小手先案**（c3 §3・IDEA_POLICY）: 乳の店条件付き売却＝§禁止（競合で剥がれる上に denial を壊す）／
  乳の売却ロット微調整・SELL_FLOORS[MILK]±＝§禁止 1,3 ／ carrot last_plant_day +1＝§禁止 1 ／
  終盤 hands+1 単体で PASS 埋め＝§禁止 2（本世代の +1 は動物追加に束ねた発火限定なので別物）。
- 学び（eval 後・2026-09-13 c2 追記）: **仮説の核（競合プールでは premium が床値に潰れるので卵への
  振り替えが正へ反転する）は refute された。** money −3307・margin −2826 で、競合プールでも卵は
  ガチョウ導入コスト（NE 自給小麦 3 枚転用＋発火 +1 hand＋ガチョウ資本 $900＋毎日 FEED の hand-hour）を
  回収できなかった。**卵市場は非競合だが「小さすぎる」**（上位 B でも卵は $4-5k どまり＝
  2026-09-13 Majkel 解剖 `knowledge/analysis/2026-09-13_majkel-new-type.md` と一致。上位 #1 はガチョウを
  完全に捨てて共有市場で勝つ）。**構造知見の訂正: 「唯一の非 denial 出口＝卵」は正しいが、その出口の
  総額が導入コストを下回るので additive として負ける。** 自資金を上げる正しい経路は「非競合の小市場に出る」
  ではなく「**相手の型に production を適応させる（denial-positive で共有市場を取りに行く）**」だった
  （gen0056 = 相手適応の乳エクスポージャ・Majkel の shop-conditional 動物適応）。
  → CLOSED.md に 1 行。逸脱（小麦 3 枚転用・+1 hand）は台帳に残さない（gen0055 は非昇格・不変世代で
  親 gen0051 は無傷。gen0056 は gen0051 から作る＝逸脱は伝播しない）。
