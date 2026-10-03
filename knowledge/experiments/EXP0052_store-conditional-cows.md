---
status: done   # 判定: 非昇格(overall 検出不能)・強帯マージン CI 下限>0 で明確に正 → measure 承認キューへ
gen: gen0052
parent: gen0050
---

# EXP0052: 牛の限界頭数を乳店の早出しで条件付ける（店条件付き cow_target）
- 日付: 2026-09-08（実装）／ 2026-09-09（判定） ／ 世代: gen0052（親: gen0050）
- 仮説: 王者系譜 6seed の実測で乳 258 個を**固定生産**し、実現単価が乳店の早さで $4（乳店 0）〜$197
  （乳店 d3）と **~50 倍**振れ、床値で 148-246 個ダンプしていた（`knowledge/analysis/2026-09-08_milk-value-is-store-conditional.md`）。
  牛の最終目標頭数を「最初の 2 軒（d6 までに開示）に乳店が居るか」（milk_ok）で 8/6 に条件付ければ、
  乳店の無い最頻の町で 7・8 頭目（限界価値最低）を切り、床値ダンプ回避＋牛 2 頭ぶんの資本 $800・飼料・
  CARE/FEED の hand-hour を解放してイチゴ care/収穫へ再配分できる。羊が既に yarn で条件付けられて
  いる（sheep_target）のに牛だけ無条件 8 頭という非対称を消す。上位も牛 6/8/9 を乳店 0/1/2+ で条件付ける
  （`shared/top_meta/LATEST.md §7.2`）。IDEA_POLICY §2（未使用の観測 = 乳店軒数を cow_target に使う）。
- 変更: gen0050（FIX0019+FIX0020）のコピー＋ `cow_target(day)` → `cow_target(day, milk_ok=True)` の
  1 機構のみ（最終 return を `8 if milk_ok else 6`。d0-7 のランプ 0→4→6 は不変）。`MILK_LOOKAHEAD=2`・
  `milk_ok = any(s in MILK_SHOPS for s in shops[:2])` を計画ヘッダで計算し、feed 計画と動物購入 deficit の
  2 箇所に渡す。COW_MAX(=8) 定数は不変（tgt が binding）。milk_ok=True の町では gen0048/gen0050 とバイト同一。
  sheep/expand/carrot/市場売却は 1 行も触っていない。
- **結果**（★2026-09-09 cycle1 読解・cycle2 確定・50seed `records/eval_gen0052.json`・baseline=eval_gen0048）:
  - **gate.pass = False**（overall マージン CI が 0 をまたぐ）。pool rating 631.6 (±18.9)・rating_delta +0.0・
    slope_delta +76.3・errors 0・too_good null。
  - **overall マージン −$204.1 [−702.9, +294.8]**（点推定負・検出不能）／ 自資金 **+$612.0 [+14.4, +1209.6]**（CI 下限 > 0）／ slope +76.3。
  - **★強帯マージン +$596.2 [+125.0, +1067.5]（CI 下限 > 0 で明確に正）**／ 強帯自資金 **+$1,624.5 [+846.5, +2402.5]**（明確に正）／ 強帯 slope +152.7。
  - **相手別 paired 分解**（cycle1 実測・side 込み 100 対/相手・gen0048 比。marginΔ = candΔ − oppΔ）:
    | 相手 | tier | marginΔ | candΔ(自) | oppΔ(相手) |
    | --- | --- | --- | --- | --- |
    | **starter** | anchor_weak | **−2,654** | −2,667 | **−13** |
    | **georgy** | weak | **−3,765** | −3,736 | **+29** |
    | gen0018 | own(mid) | −595 | +139 | +734 |
    | boatlee_v16 | strong | −158 | +1,534 | +1,692 |
    | kaito_v48 | strong | −87 | +1,961 | +2,047 |
    | tetsutani_adaptive | strong | +190 | +2,758 | +2,567 |
    | sokolovsky | strong | +620 | +1,924 | +1,304 |
    | rayk_c95 | strong | +721 | +1,991 | +1,269 |
    | boatlee_v29 | strong | +911 | +945 | +34 |
    | prvsiyan_v189c | strong | +1,201 | −127 | −1,328 |
    | pilkwang | strong | +1,371 | +2,010 | +640 |
  - **overall の負けは弱 2 体（starter・georgy）に全集中**。この 2 体は **oppΔ≈0**（−13・+29）
    ＝相手を持ち上げたのではなく**自分の乳収入の純減**。**principle 3（供給を減らす＝相手への贈り物）違反なし。**
    強帯は **8 体中 6 体でマージン正**（負は boatlee_v16 −158・kaito −87 と小さい）・**7 体で自資金 +$945〜2,758**
    （唯一の負は prvsiyan −127 と小さく、しかも oppΔ −1,328 でマージンは +1,201）。
- **判定**: **非昇格（promote 却下）＝ overall 検出不能** — `指標: pool(v0.5・マージン) ／ シード: 50 ／
  overall マージン CI: [−702.9, +294.8]`（点推定も負）。**ただし measure 承認キューへ積む**
  （強帯マージン CI 下限 +125 > 0 の**強帯ベット**・rating_delta +0.0 で要件 ≥−100 を満たす）。
  cycle2 で `preflight_submit --reason measure --do` 実行 → **人が `ops/approve_submit.py gen0052` で提出可否を判断**。
  **gen0051（Stage B）と競合する強帯ベットなので、人はどちらか一方の承認でよい**（両方は最新 2 提出枠を消費）。
- **説明（この分野を知らない人向け 3 行）**: 牛乳を売る店が町に早く開くかで牛の頭数を 8→6 に減らす変更。
  強い相手（乳の市場を一緒に食い合う相手）には効いた＝安く売る牛乳を減らして自分の稼ぎが $945〜2,758 増えた。
  だが弱い相手（市場が飽和しない相手）には牛乳が普通に高く売れるので、頭数を削ると純粋に売上を失って総合ではマイナスになった。
- **改善幅は seed ブレより大きいか**: overall は No（自資金 CI 下限 +14 は辛うじて正だがマージン CI が 0 をまたぐ）。
  **強帯は Yes**（強帯マージン CI 下限 +125 > 0・強帯自資金 CI 下限 +847 > 0）。
- **目標曲線との差**: gap §4-1（乳 −$12,547）・§4-5（床値 148 個）に対する直接介入。overall で沈むのは
  弱フィールドで乳が高く売れる町では削りすぎるため（「最初の 2 軒の乳店」は相手の飽和行動の proxy として粗い）。
- **ミクロ指標**（micro_audit --assert seed 7/14/42）: critical-three (noop_total/unfed_days/uncared_days) 全 0 = OK。
  残る NG（inplace_share/last_water_hour/melon_yield/strawberry_yield/tile_util/wheat_yield）は親 gen0050 の NG 集合と
  同一＝新規回帰 0（seed7 は tile_revisit_share が OK に改善）。profile max < 1.0s。check_fixes applied 14/14・回帰 0・open 6。
- **メロン寿命の照合**（Discussion 740087・cycle2 で実施）: エンジン `max_lifespan_step = (planted_day + max_yield_day + 1)`
  かつ MELON `max_yield_day=12`（`kaggriculture.py:16,224`）→ **メロン decay 開始は植付 d+13**（README 表の行 "10 days" は
  誤り。README 本文 line 27 の「bonus window ages 6-12・cap は age 10」が正）。**我々の main.py は melon を `age>=10` で収穫**
  （line 659。age 10 で yield cap 6 に到達し ages 11-12 は加算 0）＝**最速の最適点で刈っており、d+13 の decay 余裕には一切依存
  していない**。BONUS_WINDOW MELON=(6,12)・MAX_YIELD=6 もエンジン一致。**誤った寿命定数は無く FIX 不要**（740087 は
  README 表の齟齬でありエージェントのバグではない）。
- **レビュー記録**: Codex レビュー未実施（measure 提出は昇格ではないので preflight の review 機械チェック対象外＝
  rating_delta ≥ −100 のみ確認。将来 promote するなら合成前に Codex 必須）。
- **却下した小手先案**: cow_target を乳店軒数の連続関数にする（6/8 の 2 値で足りる・単一パラメータ sweep 側＝IDEA_POLICY 禁止）
  ／ MILK_LOOKAHEAD を 3 に伸ばす（d9 で牛を積み終えるので 2 軒で十分・sweep 側）。
- 学び: **(1) 「最初の 2 軒の乳店」は相手の乳市場飽和の proxy として粗い。** 強帯（市場を食い合う相手）では
  牛削減が正しく効き自資金 +$945〜2,758／マージン 6-7 勝、が弱相手（市場が飽和しない starter/georgy）では
  乳が床に落ちないので削ると純損（−$2.7〜3.8k）。**恒久対応は opponent-adaptive**（相手の乳供給・quote 崩れを検知した
  時だけ牛を削る）＝候補 B と合流（CLOSED 再検討）。**(2) principle 3 は違反していない。** 弱相手の大敗は oppΔ≈0
  ＝相手を持ち上げたのではなく自分の乳収入の純減。「供給を減らす＝相手への贈り物」は今回は起きず、削ったぶんが
  そのまま自分の売上減として出た（相手が拾えないほど乳が余っている町だから）。**(3) gen0051 と同じ「強帯で正・overall 検出不能」型。**
  強帯ベットとして LB=強相手多数で計測する価値は同格（measure 競合）。
