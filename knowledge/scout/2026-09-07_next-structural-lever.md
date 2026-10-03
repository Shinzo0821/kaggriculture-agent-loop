# Scout 2026-09-07: gen0045 未実装の上位構造 — 終盤 fast-carrot ローテーション

- 取得日: 2026-09-07（サイクル1）／ Scout
- 目的: 広い戦略レバーが枯れつつある中で、gen0045（funded wool）にまだ入っていない**LB #1 の実測挙動**を 1〜2 個言語化する。
- 王者 gen0045 の実装範囲は `meta.json` の `mechanisms` で確認（funded_wool_expansion / feed_buffer / hands_bump / market_reconcile / beta_harvest_gate ＋継承分）。重複は避けた。

## 探索した材料（再現性）
- Discussion 検索語（`ops/fetch_discussions.py search`）: `carrot` / `rotation` / `replant` / `weed` / `endgame` / `switch crop` / `harvest time` / `grow_time`。
  - ヒット: [732902] 「carrot/geese は稀にしか利益が出ない」= carrot を**主力**にする話。[735311] 「carrot hinge は 26% の試合で発火（below_target 0.20→1.00, T=450, $70 まで跳ねる）」。[734000]/[738563] 終盤衛生（endgame hygiene）を LB 上位が指標にしている。
  - `replant` / `switch crop` / `grow_time` / `harvest time` は**コーパスにヒットなし**（＝終盤ローテーションを明示的に論じたスレは無い。実測で取るしかない）。
- リプレイ（LB #1 我都先道歉 vs #2 Mengfei Li、今夜回収の新着）:
  - `replays/top/episode-106191684-replay.json`（#1 勝ち $121,859 vs $110,880）
  - `replays/top/episode-106190768-replay.json`（#1 勝ち $93,393 vs $87,489）
  - 対照: `replays/episode-106190289-replay.json`（王者 gen0036 実戦 $28,812 惨敗。`knowledge/analysis/2026-09-07_ep106190289-blowout.md` 修正候補2「carrot 転作」の裏取り）
- ゲーム機構（`.venv/.../envs/kaggriculture/README.md`）: **CARROT は one-time / 種$20 / base$35 / time-to-max 2 日 / 占有 ~3 日 / max yield 3(無肥料)**。**STRAWBERRY は ongoing で 4 産（age 10/12/14/16）で打ち止め → 翌日 WEED に decay。**

---

## 提案1（本命）: 使い終わったイチゴタイルを終盤 d24-27 に fast-carrot へローテーションする

**(a) 出所・実測数値**（両リプレイとも LB #1 が実行、#2 が取りこぼしている）

per-day タイル数（両プレイヤー、`replays/top/`）:

| | d20 | d24 | d26 | d27 | d28 | d29 |
|---|---|---|---|---|---|---|
| ep106191684 **#1勝(P0)** CARROT | 0 | 3 | **17** | **23** | 11 | 7 |
| ep106191684 #1勝(P0) WEED | 0 | 1 | 0 | 0 | 2 | 2 |
| ep106191684 #2負(P1) CARROT | 0 | 0 | 5 | 11 | 11 | 5 |
| ep106191684 #2負(P1) WEED | 2 | **10** | **12** | 3 | **18** | **18** |
| ep106190768 **#1勝(P1)** CARROT | 0 | 5 | 10 | 11 | 7 | 1 |
| ep106190768 #1勝(P1) WEED | 0 | 0 | 2 | 1 | 1 | 1 |
| ep106190768 #2負(P0) WEED | 0 | 4 | 1 | 0 | **13** | **13** |

読み: **STRAWBERRY は age16(4産)で decay して WEED になる**。勝者は空いた/枯れたイチゴタイルを即 DIG して **CARROT（2-3日で収穫）に差し替え**、終盤 WEED を 0-2 に保つ。敗者は同じタイルを 12-18 枚も WEED のまま放置（純損 $0）。両戦とも「carrot を早く・多く」「WEED≒0」の側が勝っている。粗い金額: carrot 17-23枚 × 3収量 × ~$35 ≈ $1.8-2.4k、対して敗者の 18 WEED = $0。マージンスイング ~$2-4k（#1 の勝ち幅 $6-11k の中で無視できない一枚）。

**(b) gen0045 との差分（未実装の確認）**
- `CROP_PLANS` に **CARROT が無い**（MELON/STRAWBERRY/WHEAT のみ）。gen0045 は carrot を一度も PLANT しない（CARROT は `ALWAYS_SELL` にあるが在庫が来ないので発火しない、L375）。
- 終盤の空きタイル埋めは `FALLBACK_CROP="WHEAT"`（L313）だが **WHEAT は age4 収穫 ＆ `LAST_PLANT_DAY=25`**（L297）。イチゴタイルが空くのは decay 後の **d26-27** なので、wheat では間に合わない（d27+4=d31>29）。**carrot だけが d26-27 植えで d29 収穫に間に合う唯一の作物。**
- gen0045 は WEED を DIG する（L745/777/802）が、DIG 後にそのタイルへ植える計画（carrot 窓）が無いため**空き地のまま放置** = 敗者側の挙動。
- gen0045 の終盤 WHEAT ブロック（from_day 19）はメロン跡地（行0,1,5）だけで、**イチゴタイル（NE 5-9行0-1・SW 0-4行6-8）を一切カバーしない**。

**(c) 該当 IDEA_POLICY「出してよい」項目**
- §1 日次骨格（作物の作付け計画を動かす＝carrot 窓を CROP_PLANS に追加、終盤の型を変える）
- §5 上位公開実装の欠陥を突く差別化（＝「終盤にタイルを遊ばせる/WEED 化する」我々の穴を LB #1 の carrot 転作で塞ぐ。`ep106190289-blowout.md` 修正候補2/3）
- 参考: CLOSED.md L43「相手型の推定で作付けを切り替える案は別系統として可」に沿う。

**(d) 実装の粗い形と効く理由**
- `CROP_PLANS` に `"CARROT"` を追加。tiles = **イチゴタイルと同座標**（NE 5-9行0-1 + SW 0-4行6-8 の一部、~20枚）、`windows=[(24, 27)]`、`plant_pri` は wheat 終盤ブロックより後、`water_pri` 高め（carrot は max yield 3 に daily water 必要）。`LAST_PLANT_DAY` を carrot に限り 27 まで許可（他作物は 25 のまま）。
- 発火条件: そのタイルの STRAWBERRY が decay 済み（WEED or 空き）かつ day∈[24,27]。DIG→PLANT CARROT→WATER の 3 手を既存の todo スケジューラに載せる。
- 効く理由: **decay 済みイチゴタイルは既に 4 産を終えており、carrot 化しても我々のイチゴ供給は 1 個も減らない**（下の落とし穴参照）。$0 の遊休/WEED を carrot base $35（hinge 発火時 $70）に変える純増。LB #1 が両席で再現している実挙動。

**(e) 落とし穴**
- **供給削減の贈り物ワナには当たらない**: 転作するタイルは「4 産を終えて decay したイチゴ」だけ。イチゴ産出はそのタイルでは既にゼロなので、carrot に替えても相手のイチゴ価格を上げる贈り物にならない（HANDOFF 3原理の「供給を削ると相手への贈り物」から外れる）。**まだ産むイチゴ（age<16）を carrot に替えてはいけない** — それは EXP0035/0040 の失敗形。窓を「decay 後のみ」に厳密にゲートすること。
- **carrot も共有市場**: 両農場が終盤 carrot をダンプすると carrot も floor($1)へ。ただし代替が $0(WEED) なので下方リスクは限定的。エッジは (i) carrot hinge が 26% の試合で $70 に跳ねる、(ii) 相手より 1-2 日早く出す（#1 は d24 開始、#2 は d26 開始で負け）＝「1ターン先回り」原理と同じ。
- carrot 種 $20×20=$400 の先行投資。hinge 非発火の平場でも $35×3 でペイするが、**大量の水やり手数**が d26-29 に集中する（羊 8 頭 expand と同居する発火 seed では hand-hour 競合しうる。gen0045 の hands_bump との干渉を micro_audit で要確認）。
- 相手が carrot をやらない seed では floor に落とす前に売り切れるが、やる seed では早出しが効く。**seed で分散が大きい → 24 seed 方向判断 → 50 seed 昇格**（検出限界ドキュメント遵守）。

---

## 提案2（提案1の条件付け。§2）: carrot ローテーション量を carrot 需要ショップで決める

**(a) 出所**: [735311]「carrot hinge は 26% の試合で発火」。README: carrot を消費するのは **PET_CAFE（単品店＝2倍消費）と FARMERS_MARKET**。hinge 発火時 $35→$70、非発火（T=450 未達）なら base 近辺でダンプすると floor へ。

**(b) gen0045 との差分**: gen0045 は `unlocked_shops` を **WOOL(yarn_count) と premium_absorb(milk/wool/straw) にしか使っていない**（L441/495-499）。**carrot 需要ショップ（PET_CAFE/FARMERS_MARKET）は一度も読んでいない** = IDEA_POLICY §2「未使用の観測フィールド」に該当。

**(c) IDEA_POLICY**: §2（未使用観測の利用）＋ §1。

**(d) 粗い形**: `carrot_count(shops) = 2*count(PET_CAFE) + count(FARMERS_MARKET)` を作り、carrot ローテ枚数を `carrot_count>=1` の seed で厚く（~20枚）、`==0` の seed で薄く/停止（floor 覚悟で少量）にする。wool の yarn_count 分岐と同じ構造。

**(e) 落とし穴**: これは提案1の「サイズ決め」であって独立の勝ち筋ではない。**まず提案1（shop 非依存の一律 carrot ローテ）を 24 seed で測り、効いたら §2 で条件化する**順序を守る（先に観測分岐を入れると効果の帰属が割れる）。carrot ショップ有無で町の抽選＝空きタイル依存（`2026-09-06_town-draw-depends-on-empty-tiles.md`）なので、carrot 転作自体が空きタイル数を変えて抽選を動かす二次効果に注意。

---

## 正直な限界
- 本命は提案1 の1本。提案2 はその条件付けで、独立レバーとしては弱い。
- 広いレバーは実際に枯れており、今夜「まったく別系統の新しい型」は discussion にも上位リプレイにも見つからなかった（strawberry 増枚は EXP0035/0043 で CLOSED＝市場律速、土地追加は EXP0023/0027 で検出不能、動物増は EXP0029/0037/0040 で棄却、労働量増は EXP0028/0038/0039 で確定棄却）。**残る前進は「終盤の遊休タイルの回収」= 質のレバー**で、これは gen0026/gen0032/gen0036 が効かせてきたカテゴリ（労働の質）と同じ系譜。
- 数値は 2 戦・2 チームの解析限界。carrot の実収益は相手同時ダンプ・町消費でさらに下振れしうる。実装後は evaluate の強帯マージンと micro_audit（carrot 収量・終盤 WEED 日数）で検証すること。
