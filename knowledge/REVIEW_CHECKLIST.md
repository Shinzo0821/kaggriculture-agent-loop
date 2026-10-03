# REVIEW_CHECKLIST — 昇格前クロスレビューの観点

- 作成: 2026-09-05（計画 §2-A）
- 使い方: **昇格の直前**に codex MCP へ差分を渡し、この観点で見てもらう。
  結果（日付・指摘・対応）を EXP の「レビュー記録」欄に書く。
  書いていないと `ops/preflight_submit.py --reason promote` が NO-GO になる（機械チェック）。
- 提出**後**のレビュー（旧 NIGHTLY 手順 7）は廃止。出してから直しても LB は取り返せない。

## なぜ昇格前なのか

同じ AI の自己チェックでは自分の盲点に気づけない。gen0022 のレビューでは
codex が「最寄りユニットブロック」「未実行 PICKUP の在庫予約」の 2 件を見つけたが、
**それは提出後だった**ため、その世代のまま LB に出ている。
gen0023 ではこの 2 件を直したが、直した効果は seeds50 の CI が 0 をまたいで検出できなかった。
早い段階で潰していれば 1 世代ぶん節約できていた。

## 渡すもの

```
git diff agents/<親世代>/main.py agents/<新世代>/main.py
```
と、`agents/<新世代>/meta.json` の hypothesis / changes / mechanisms。

## 観点（この 7 つは必ず見てもらう）

1. **例外パス** — 全コードパスが dict を返すか。`.get()` / 範囲チェックの漏れ。
   観測に想定外の値（空リスト、None、未知の enum）が来た時に例外で即敗北しないか。
2. **1 ターン 1 秒制約** — 最悪ケース（動物・タイル・hands が最大、全ゾーン稼働）で
   ループが何重になるか。`harness/profile_agent.py` の平均だけでなく最悪値を見る。
3. **観測フォーマットの誤読** — フィールド名・単位・0/1 起点・日と時の取り違え。
   一次情報は `.venv/.../envs/kaggriculture/AGENTS.md` と `README.md`。
4. **在庫予約と claim の取りこぼし** — 「予約したが実行しない」「実行するが予約しない」の非対称。
   gen0022 で実際に出た欠陥（移動中の hand が小麦を幽霊予約し、シェッド上の hand が積めない）。
5. **ゾーン境界** — ゾーンに属さないタイル、ゾーンをまたぐユニット、
   ゾーン所有者が居ない時間帯（救済パス）。土地が増えた時に境界条件が変わらないか。
6. **終盤清算（step 718 前後）** — 最終日の売り切り、収穫の取りこぼし、
   最終ターンに間に合わない行動を出していないか。1 ターンずれると全額落とす。
7. **定数の出所** — 新しく入った定数は**ゲーム構造から導けるか**、それとも当てにいったチューニングか。
   後者なら `knowledge/IDEA_POLICY.md` の禁止側に該当しないか確認する。

## 出力の受け取り方（**ここが機械チェックの対象**）

レビューを通したら、`agents/<gen>/meta.json` に **構造化された `review`** を書く。
preflight はこの散文ではなく**このオブジェクト**を見る（`--reason promote` の必須条件）:

```json
"review": {
  "date": "2026-09-06",
  "reviewer": "codex",
  "candidate_sha256": "<レビューした main.py の SHA-256>",
  "checklist": "knowledge/REVIEW_CHECKLIST.md",
  "diff_range": "agents/gen0022/main.py..agents/gen0024/main.py",
  "findings": [
    {"severity": "fatal", "what": "h18 救済で claim 済みユニットを二重に拾う", "resolution": "fixed"},
    {"severity": "minor", "what": "ゾーン境界の移動が 1 タイル無駄", "resolution": "deferred"}
  ],
  "blocking_resolved": true
}
```

SHA-256 は `shasum -a 256 agents/<gen>/main.py` で取る。

preflight が拒否する条件（`ops/preflight_submit.py` の `find_review_record`）:

- `review` が無い / `candidate_sha256` が今の `main.py` と不一致（＝**レビュー後にコードを変えた**）
- `date` が `YYYY-MM-DD` でない、または未来日
- `blocking_resolved` が `True` でない
- `findings` が配列でない（**指摘なしなら `[]`** と書く。書かないのは不可）
- `severity` が `fatal` の指摘に `resolution: "fixed"` が無い
- `meta.exp` が指す EXP が存在しない、またはその frontmatter の `gen` がこの世代でない

**即死級（例外・制約違反）は昇格前に必ず直す**（`fixed` にできないなら昇格しない）。
静かな非効率は `deferred` で次世代の候補にしてよい（gen0022 の 2 件はこの扱いだった）。

**`deferred` にしたら、その場で修正台帳に足す**（`control/fixes.json` ＋ `knowledge/FIXES.md`）。
`sources` は `genNNNN#<findings のインデックス>`。足さないと `ops/check_fixes.py --audit` が
未登録として落とす。**世代は不変で新世代は親のコピーなので、台帳に載せない限り指摘は世代交代で消える**
（gen0023 の fix2 が 13 世代あとに同じ指摘で戻ってきた）。直した世代が昇格したら `status: applied` と
`detect` を書き、以後は `ops/check_fixes.py agents/genNNNN/main.py` が回帰を検出する。
EXP の「レビュー記録」欄には人が読む要約（日付・指摘・対応）を書く。こちらは機械判定に使わない
——**散文の長さで昇格を通さない**ため（「未実施。後で依頼する予定」が 20 文字を超えて通ってしまう穴があった）。
