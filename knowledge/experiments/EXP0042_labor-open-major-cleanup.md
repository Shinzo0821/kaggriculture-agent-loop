---
status: done   # in_progress | done
gen: gen0042
parent: gen0036
---

# EXP0042: 労働の質の open major 掃除（FIX0004 幽霊予約 + FIX0005 相互停止）
- 日付: 2026-09-06 ／ 世代: gen0042（親: gen0036）
- 仮説: 修正台帳の open major 2 件は、どちらも**投入を増やさず unit-hour の取りこぼしを回収する**
  （`knowledge/IDEA_POLICY.md`「労働割当の構造変更」側。原理 1「労働は量ではなく質」と整合）。
  - **FIX0004**（gen0022 から継承・FIX0001 の種版）: 植付タイルへ**移動中**の hand が `planned_seed` を
    予約するため、`planned_seed >= seeds` で種切れと誤判定し、現地に立って**今すぐ植える** hand が弾かれる。
  - **FIX0005**: 所有者保護 `_owner_can_come` は farmer を弾くのに、FEED/CARE の最寄り判定（dmin）には
    farmer が残るため、farmer が近いだけで所有者の claim を潰し、farmer 自身も保護で降りて両者が
    譲り合い**両方 PASS** になる（unit-hour の全損）。
- 変更:
  - FIX0004: 種数の予約（`planned_seed` の加算）を `(ux, uy) == (x, y)`（今ターン実際に植える hand）に限定。
    タイルの `claimed` は歩行中も維持（同じ苗床を二重取りしない）。種購入は `plant_slots` で数えるので
    予約を絞っても過剰購入にはならない。
  - FIX0005: dmin の候補から farmer を「所有者が今日まだ来られる間（`_owner_can_come` が True）」は外す。
    rescue 時・所有者不在時は `_owner_can_come` が False を返すので farmer は従来どおり候補に残る。
  - **FIX0003 / FIX0011 を gen0041 から移植**（Track A のイチゴ価格床ロジック `LIVING_EXITS` は移植しない）。
    gen0042 の親は gen0036 で、これらは gen0041 でしか入っていないため、移植しないと `check_fixes` が
    回帰として落とす（＝gen0023 の再演）。どちらも**最終行動ターンだけ**の会計修正なので Track B の
    日中労働効果への交絡は限定的。
- 結果（`records/eval_gen0042.json`・seeds 50・baseline gen0036）:
  - pool.rating 631.6 ±18.9 ／ rating_delta **0.0** ／ win_rate 0.273（strong 0.0）
  - 全体マージン差 **−24.2 [−460.9, +412.6]**（n=1100・0またぎ＝検出不能）
  - 自分の資金差 **+51.9 [−779.7, +883.5]**（0またぎ）／ slope_delta +43.3
  - **強帯マージン差 −204.1 [−519.5, +111.3]**（点推定が負）／ 強帯資金差 −113.8 [−1034.8, +807.1]
  - `gate.pass = false`（全体マージン CI 下限 < 0）。`too_good` null。`submit_ok = true`（rating_delta ≥ −100）。
- **判定**: 非昇格（検出不能）— `指標: pool(v0.5) ／ シード: 50 ／ CI: 全体 [−460.9, +412.6]`。
  全体マージンは 0またぎで**改善も劣化も検出できない**。強帯マージンは**点推定が負**（−204.1）なので
  改訂ルールで前進とは数えない（CI は 0またぎなので棄却ではなく検出不能）。**cycle3 Analyst の見立てどおり**、
  これらの open major 修正（FIX0004 種の幽霊予約・FIX0005 farmer 相互停止）は**王者 gen0036 では症状が
  ほぼ解消済み**（訪問完了 gen0032 以降）で、資金に効く余地が小さかった。バグ修正自体は正当（micro 全指標
  非回帰・unfed/uncared/noop=0）なので、**gen0043 の親を gen0042 にして修正を系統に載せたまま H1 を測る**
  （棄却ではないので破棄しない。CLOSED.md の再検討へ）。
- **説明（この分野を知らない人向け 3 行）**: 農場の働き手が「植えに行く途中」なだけで種を予約済み扱いにして
  しまい、今すぐ植えられる別の働き手が空振りしていた。もう一つ、農場主（farmer）が「一番近い」と数えられる
  のに実際にはその仕事を取れず、担当者もそれに遠慮して**両方が何もしない**穴があった。この 2 つを塞いだ。
- **改善幅は seed ブレより大きいか**: eval 待ち（対応付き資金差の CI 下限で判定）。
- **目標曲線との差**: eval 後に `harness/audit_replay.py --targets` で d5/d10/d15/d20 を確認。
- **ミクロ指標**（gen0042 s42、括弧内は親 gen0036 s42）:
  - inplace_share **0.4116**（0.4097）／ tile_revisit_share **0.0128**（0.0121）／ tile_util **0.7019**（0.6975）
    ／ moves3plus_share **0.1291**（0.1351）／ mean_hop_distance **0.959**（0.962）
  - 収量: MELON **5.812**（5.75）／ STRAWBERRY **1.685**（1.626）／ WHEAT **3.88**（3.864）
  - **unfed_days 0 ／ uncared_days 0 ／ noop_total 0**（合格ライン、必須）
  - **どの指標も親 gen0036 から回帰していない**（すべて同等〜わずかに改善）。`--assert` が NG を出す
    inplace_share(≥0.44)・tile_util(≥0.83)・last_water_hour(≤14)・各収量は**強帯の実測から採った到達目標
    （FIX0013）で、王者 gen0036 自身も満たしていない**。gen0042 で緩めた項目ではなく親から継承。
  - profile: mean 0.0002s / p99 0.00033s / **max 0.0183s**（1 秒制約 OK）。static_check OK。
- **レビュー記録**: 昇格前に Codex（gpt-5.6-sol / reasoning high）に差分を渡す（eval で `gate.pass` を
  確認してから。`review.date` は UTC）。未実施。
- **却下した小手先案**:
  - **FIX0006（窓の中 WATER が HARVEST より前）／ 該当禁止項目なし（措置理由により延期）**:
    gen0032 の訪問完了（`visit_ok` かつ `d == 0` の `DAILY_TILE_OPS` を `VISIT_LAYER` に持ち上げ）で
    「立っているタイルの ripe を先に収穫」は既に成立し、gen0036 の micro（inplace 0.410 / revisit 0.012）で
    症状はほぼ消えている。残る `visit_ok=False`（最終日・植付締切）の帯で in-place HARVEST を持ち上げると
    植付締切と競合する（その帯を除外しているのは意図的）。窓の `bonus_water` の優先度配置は EXP0024 で
    A/B 済みの敏感な設計。FIX0004/0005 と混ぜると帰属が濁るので、独立した measurement 世代で careful に
    測る（`knowledge/experiments/CLOSED.md` ではなく FIXES.md の FIX0006 に「要再検討」として残す）。
- 学び:
  - **幽霊予約は「在庫」だけでなく「種数」でも起きる**（FIX0001 と FIX0004 は同型）。予約は「今ターン
    実際に消費する主体」だけが行う、が原則。次に予約を導入する時（動物・肥料・土地）も同じ穴を疑う。
  - **保護の対象集合と最寄り判定の対象集合は必ず一致させる**（FIX0005）。片方だけに farmer が居ると
    「近いのに取れない」主体が生まれ、譲り合いで両方 PASS になる。
- 関連分析（今夜の Analyst 2 本。gen0042 とは独立だが今夜の記録として）:
  - `knowledge/analysis/2026-09-06_loss-vs-extremely-sus.md`: 実戦の $30k 下振れは seed でも counter でもなく
    **構造（タイル利用率 68% vs 93%・動物 12 vs 17・プレミアム作物の売り時）**。
  - `knowledge/analysis/2026-09-06_top-endgame-sell-rates.md`: **イチゴは良い店舗構成では需要律速で床に落ちない
    （$150-220 維持）**。床に崩れるのは MILK/WOOL/FERTILIZER だが上位はそれらを保護せず全処分する。
    → **Track A（gen0041 のイチゴ価格床）の前提を崩す可能性がある。cycle4 で eval_gen0041 を読むとき突き合わせる。**
