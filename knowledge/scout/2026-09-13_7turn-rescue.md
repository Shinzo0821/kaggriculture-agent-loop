# 2026-09-13 Scout: 公開 SOTA「7-Turn Rescue」(dmitriigluzdov) の回収と audit

Track S。我々のアカウントの手動提出 sub-21「7-Turn Rescue (dmitriigluzdov fork)」= LB 1939.5
（「Historical LB 2800+」）の**元ネタ実装を回収**した。**提出禁止・丸写し禁止**（sparring 専用）。

## 回収できたもの（runnable）

- kernel: `dmitriigluzdov/kaggriculture-7-turn-rescue-historical-lb-2800`（id_no 133691142・最終実行 2026-09-09・64 votes・public）。
- `uvx kaggle kernels pull` で .ipynb を取得 → `%%writefile` セル 5 本を分解 → 5.1 MB のルートデータ（base64+gzip、
  セル 15）を復号（sha256 `17d503f2...5495ef` を検証一致）。
- `agents/sparring/dmitriigluzdov_7turn/` に保存（main.py / policy.py / router_parent.py / terminal_planner.py /
  unit_model.py / settings.json / actions.json / LICENSE.txt / NOTICE.txt / meta.json）。出典・出所チェーンは meta.json。
- **runnable 検証済み**: `run_match vs starter`（seed 4200）で最終 $170,310 vs $3,648、d29 資金 $151,374。
- Discussion コーパスには無かった（`fetch_discussions.py search '7-Turn'/'dmitriigluzdov'/'Rescue'` 全て 0 件）。回収は kernels list 経由。

## 型分類（H/C/S/G/ME）

- **主流 B（shop-router 系）の系譜**であり、Majkel1337 のような**新型ではない**。
- 中身は **13 本の事前録画アクションテープの lookup**。開幕 2 軒の店の観測順をキーに 1 本を選ぶ（`router_parent.py`）。
  したがって畜産/メロン構成は**店抽選に条件付き**で seed ごとに変わる。
- seed 4200 実測の骨格: **H0 C6 S4 G2、メロン植付 12（同時 ~6）**。牛(乳)中心・ガチョウ入り・鶏 0。
  dmitriigluzdov の他作（Two Coins One Sheep / Herd-Safe Sale Window / Goose Portfolio）と整合。

## 出所チェーン（NOTICE.txt より。ここが重要）

Thomas Tschinkel「93.8% Win Rate Public State Router」v3（特徴量ツリー＋13 テープ = actions.json の実体）
→ aurax7「Reactive Router」（reactive な売り時・shed 予測）
→ **yhay81「Shop Router 0909」v3（= live parent、行動 0-711）**
→ dmitriigluzdov の**終盤 7 手回収プランナ**（行動 712-718）。

**作者自身の言明**: 競争力の**ほぼ全部は parent（yhay81 0909）由来**で、7 手回収の寄与は
+6 コイン（開発）/ +10 コイン（held-out）に過ぎない。つまり LB 1939.5 の中身は
**yhay81 Shop Router 0909 の route-lookup ポリシー**であって「7-Turn Rescue」の新規性ではない。
（既存 sparring の `yhay81_router` は同系統の**旧 3-day 版**で macOS dylib 依存。今回のは純 Python + データで
クロスプラットフォームに動く点が新しい。）

## 突ける欠陥（IDEA_POLICY「上位公開実装の欠陥を突く差別化」候補）

`ops/audit_sparring.py`（vs starter・3 seed・上振れ前提）:
最終 $187,243（プール 2 位・kaito_v48 に次ぐ）、d10 $17,514 / d15 $40,847 / d20 $87,251（**プール最速の序中盤ランプ**）、
動物 17（プール最多の畜産）、hands 11、move% 43%。

1. **【本命】unfed>0 が 9 日**。プール最多の 17 頭を抱えながら 9 日も餌を切らしている＝**1 頭あたりの
   産出（乳/毛/卵）を落としている**。我々の王者系（gen0051 系）は unfed=0 を強制。同規模の畜産で
   **餌を切らさなければ単価×頭数で上回る**余地。ただし route-lookup の録画テープなので、unfed は
   「餌コスト vs 限界産出」を織り込んだ意図的トレードオフの可能性もある（別テープでは違う挙動）。
2. **route-lookup の硬直性**。挙動は録画テープ（13 本）の再生で、適応は「開幕 2 軒の店」の分岐のみ。
   相手の市場圧（先回り販売＝denial）に**テープ再生中は値付けを変えられない**（aurax7 の reactive 売りが
   効く範囲を超えると崩れる）。原理 3「供給を減らす＝相手への贈り物」の裏返しで、**相手の売りに先回りして
   乳/毛の単価を潰す**動きにテープは反応しきれない。
3. uncared>0 は 2 日だけ（CARE はほぼ維持）＝**世話落ちでは差別化できない**。move% 43% もプール中位で狙い所ではない。
   → 差別化は **(1) 餌切れ × 大畜産の産出ロス** に一本化するのが筋。

## Deliverable 2: プール改編の是非（今夜はやらない・単独夜へ）

**一行**: 追加する価値はある（実勢 ~1900 LB の主流 B を head-to-head で当てられる強帯アンカーになる）が、
**単独 reform 夜**で `reform_pool.py`（rate_pool --write ＋王者ベースライン取り直し）を回すこと。留意点:
(a) **actions.json 5.1 MB が現状 .gitignore 対象外＝コミットに載る**（`git check-ignore` 未ヒットを確認）。
コミット前に gitignore するか（セル 15 の blob から再生成可）ディレクトリごとコミット対象外にするか要判断。
(b) vs starter の生産量では kaito_v48（$189k）と拮抗＝**素の産出では既存プールに近い**。真の付加価値は
**head-to-head の競争力（reactive 売り・denial 耐性）**で、それは rate_pool を回して初めて分かる。
(c) これは**主流 B の最強公開版**であって**新型（Majkel H4C2S3G0ME6 等）はカバーしない**。新型の強帯化は別途。

## 参照

- 保存先: `agents/sparring/dmitriigluzdov_7turn/`（meta.json に出典・sha256・骨格・欠陥）
- audit 表: `ops/audit_sparring.py --also agents/sparring/dmitriigluzdov_7turn/main.py`（vs starter 3 seed）
