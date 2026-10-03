---
status: done   # eval 完了（2026-09-07 cycle8）。50seed で margin/money/strong 全て 0.0（gen0045 とバイト同一を確認）＝回帰なし。単独昇格せず FIX0018 applied 繰り越し
gen: gen0046
parent: gen0045
---

# EXP0046: FIX0018 — 市場予算 reconcile の残存精度（latent 修正）
- 日付: 2026-09-07 ／ 世代: gen0046（親: gen0045）
- 仮説: gen0045 のコピー + **FIX0018 のみ**。FIX0014 の市場予算 reconcile が「実約定可能性」を保証しない
  3 つの穴を塞ぐ。SELL が 10 スロットで truncation される重い購入ターンで、正当な
  BUY_LAND/BUY_ANIMAL の取りこぼし（穴1: kept SELL の 0.7 掛け過小評価による誤 drop、穴2: RESERVE
  未再確認、穴3: 数量注文の全落ち）を防ぐ。出所は gen0045 昇格前 Codex レビュー（P1-2 deferred = FIX0018）。
  IDEA_POLICY: 修正台帳 open 項目の解消（新機能より安い前進）。
- 変更（reconcile ＝ main.py 旧1382-1406 → 新1416-1490。**FIX0018 以外は一切触らない**）:
  - 穴1: `_proceeds` を BETA 品目（WOOL/MELON）でエンジンの glut 価格式 `base − amp·(inv−I0)²` を
    1 個ずつ積算する近似に置換（scarcity 側は base で頭打ち＝保守、glut 側は逓減＝大量 SELL の
    スリッページ保険が残る）。全体に `SELL_REALIZE_SAFETY=0.9`（共有市場の同時売却 FIX0017 の hedge）。
    旧の 0.7 掛け一律の過小評価が消え、engine 単独 realized 上限を超えないので over-buy も誘発しない。
  - 穴2: `_required_reserve`（feed=0／land・animal・seed=RESERVE(400)／hire=20）で末尾 buy を残すのに
    要る残置まで満たすか判定（`realized >= sum(buy_costs[:nb]) + _required_reserve(buys[nb-1])`）。
  - 穴3: 末尾が数量注文なら丸落とし前に RESERVE を残して買える数量へ縮小（SHEEP 4→3 等）。atomic
    （BUY_LAND/HIRE）と数量 1 でも賄えない場合だけ従来どおり `nb-=1`。
  - 発火ゲート `no_trunc`: SELL が全数収まる通常ターンは reconcile を丸ごとスキップ→**親とバイト同一**。
- **判定**: 検出不能（by construction）＝回帰なし確定 — `指標: pool(v0.5・マージン) ／ シード: 50 ／
  CI: margin/money/strong 全て mean 0.0・CI [0.0, 0.0]`（2026-09-07 cycle8 で eval_gen0046.json 確認）。
  **observed play では FIX0018 が発火しない**（後述）ので eval のマージン差は 0 になるのが正しい挙動。
  eval は全 50 seed で「差 0（回帰なし）」を確認する回帰テスト。**単独昇格・提出はしない**
  （王者 gen0045 とバイト同一＝LB 価値 0・最終2提出枠を消費するだけ）。FIX0018 は applied として
  次の実レバー世代（gen0047）に載せて繰り越す。
- **説明（この分野を知らない人向け 3 行）**: 「売って得た金で同じターンに土地/家畜を買う」会計の見積が
  粗く、高値の売りを残した忙しい日にエンジンなら買えたはずの土地/家畜を「金が足りない」と誤って
  取り下げていた穴を精緻化した。ただし今の王者の実戦では市場注文が 10 枠に収まっていてこの精緻化が
  一度も発火せず、出力は親と 1 バイトも変わらない＝将来の忙しい局面に備えた「潜在的な堅牢化」。
- **改善幅は seed ブレより大きいか**: いいえ。observed play で親とバイト同一なので対応付き差分は
  厳密に 0（seed ブレ以前に差そのものが無い）。合成シナリオ（>10 注文）でのみ差が出る。
- **目標曲線との差**: 変化なし（親と同一挙動）。d5/d10/d15/d20 とも gen0045 に同じ。
- **ミクロ指標**: seed7 の `micro_audit --json` が gen0045 と全項目バイト一致（final_money 150974 も一致）。
  noop_total=0 / unfed_days=0 / uncared_days=0（3 つとも OK）。利用率・収量・再訪も親と同値
  （＝強帯到達目標に対する既知の NG は gen0045 譲りで本世代の回帰ではない）。
- **leak 検証（重要）**: gen0045 の obs 軌跡を gen0045.agent と gen0046.agent の両方に流し市場注文列を
  diff。vs starter seed 7/10/14/0/3/5・vs kaito_v48/prvsiyan seed 7/14/42（**funded wool 発火 seed7 含む**）
  で全 719 ターン **diffs=0**。truncation branch 突入回数を instrumented probe で計測＝全試合 **0 回**
  （市場注文の最大 9 件＜10 スロット）。差が出る合成シナリオ（11 SELL × 2 番目土地 $2000）では旧が
  kept MELON を 0.7 掛けで realized $1925<$2000 と誤判定し土地を drop、新が glut+0.9 で $2475≥$2000+400 と
  判定し土地を救済（末尾 SHEEP 4 は旧全落ち・新 3 頭縮小）。→ FIX0018 は狙いどおり truncation ターン
  だけを変える。
- **レビュー記録**: 未（eval 完了後に Codex。observed でバイト同一なので eval 差 0 を確認してから）。
  実装時の 1 点の副作用: FIX0014 の detect 正規表現がコメントだけにマッチする脆い状態になっていたため
  `control/fixes.json` の FIX0014 require を実コードアンカー（`sum(buy_costs[:nb])`・`buys = buys[:nb]`。
  両世代に実コードで残る）へ緩めた。FIX0014 の機構自体は不変。check_fixes --audit OK。
- **却下した小手先案**: なし（FIX0018 の修正案 3 点をそのまま実装。realized 係数の sweep はしない
  ＝エンジン価格式から導いた 0.9 固定）。
- 学び（暫定）: **台帳の open 修正でも「observed play で発火するか」を先に測るべき**だった。FIX0018 は
  正しい修正だが truncation は現王者の実戦で一度も起きず、単独では LB を動かせない latent 堅牢化。
  掃除だけの世代は昇格候補にならない（gen0045 とバイト同一）。次の実レバー（gen0047 fast-carrot）に
  applied 状態で載せて繰り越すのが正しい扱い。cycle6 が「FIX0014-0016 の寄与分離は判定に不要＝
  knowledge の宿題」と格下げしたのと同じ構図で、reconcile 系の修正は observed で発火しないと分離不能。
</content>
</invoke>
