# Kaggriculture 自律攻略ループ — プロジェクト運用ルール

**このリポジトリが記憶の正。** セッション開始時は必ず次の順で読むこと:
1. `control/DIRECTIVES.md` — 人からの指示・質問（**STATUS より先**）
2. `state/HANDOFF.md` — 現在地の要約（≤100 行。王者・数字・次の一手・承認待ち）
3. `REQUIREMENTS.md` — 要件定義（正）
4. `knowledge/COMPETITION.md` — コンペ確定情報
5. `knowledge/experiments/` の最新数件と `CLOSED.md` — 直近の学びと閉じた系統
6. `state/STATUS.md` — 経緯（必要な節だけ）

## 絶対ルール

- **`../personal`（ユーザー個人の作業ディレクトリ）には絶対にアクセスしない。** 読むことも参考にすることも禁止。
- 親ディレクトリ直下の共通知見 `../shared/` は読んでよい（コンペをまたいで効く知見の置き場。`shared/README.md` 参照）。このリポジトリの現在地はそこに書かず `state/` に書く。
  - 特に **`shared/top_meta/LATEST.md`（LB 上位メタの日次レポート、毎日 10:00 と 22:00 に更新）** は Scout / Strategist が `knowledge/scout/` と並べて読む。上位の開幕の型・日次骨格・ミラー戦の勝敗要因・店抽選と動物分岐が表で出ている。仕組みと限界は `shared/top_meta/README.md`。読み取り専用（そこへは書かない）。
  - その日次レポートを**自分の王者との差**に変換したものが `state/top_meta/gap_LATEST.md`（`ops/top_meta_gap.py`。`ops/overnight.sh` の回収ステップが毎晩生成。王者 vs 強帯最強を 6 seed 走らせ、shared と同じ集計器で骨格・市場・「今夜の問い」を出す）。夜間サイクルは `ops/NIGHTLY.md` 手順 1 のとおりこれを読み、cycle1 が STATUS に「上位メタ:」の行を書く。
- **提出は必ず `ops/preflight_submit.py` 経由**（直接 `kaggle submit` を叩かない）。このスクリプトが提出前チェックを機械化している:
  1. `control/SUBMIT.lock` が存在したら**絶対に提出しない**（候補はキューに積んで待機）
  2. 当日(UTC)の実提出数（個人の手動提出含む）5回/日の残枠と `control/submission_policy.json` の `auto_daily_cap` を確認
  3. 提出メッセージは必ず `[auto]` で始める。**`--reason` が必須**: `promote`（昇格＝`gate.pass=True` かつ EXP にレビュー記録あり → 自動提出）／ `measure`（別の型の LB 計測 → `control/submit_queue.jsonl` に積むだけで提出しない。人が `ops/approve_submit.py <gen>` で承認して初めて提出される）
  4. **提出ゲート = 破滅回避ゲート（v0.5）**: エラー0 かつ 相手プール・レーティングが王者比 −100 以上。**昇格ゲート v0.6（2026-09-10。`gate.pass` ＝ エラー0 かつ次のどちらか）**: **(A) マージン経路** = 対応付き「マージン差（自分−相手）」の CI 下限 > 0（v0.5 のゲートそのまま）／ **(B) rating 経路** = `gate.rating_informative`（勝敗が拮抗する相手が居る）かつ `gate.rating_delta_ci` の下限 > 0 かつ **マージン点推定 ≥ 0**（非負ガード）。どちらで通ったかは `gate.pass_route`。2026-09-05 のマージン一本化は二極プールで rating が無力だったからで、プール改編（中間帯の新設）で rating が情報を持つように戻った（実例: gen0051 は rating 4σ・マージン検出不能で、v0.5 では人が `pass=False` を上書きしないと昇格できなかった。v0.6 の rating 経路で通る）。`harness/evaluate.py --pool control/sparring_pool.json --baseline records/eval_<王者>.json` の `gate`。旧ゲート（starter≥95%・王者H2H）は廃止
     - **マージン = `cand_final − opp_final`**（`harness/run_match.py` の勝敗の定義そのもの）。2026-09-05 に「自分の資金の差」から変更した。旧基準は自分の資金しか見ておらず、**相手の稼ぎを削る改善を $0 と評価して却下していた**（`knowledge/analysis/2026-09-05_denial-vs-production.md`）。**相手の稼ぎを削るのは正当かつ有効な手段**で、生産と同じだけ勝ちに効く
     - `money_delta_paired`（自分の資金）は**診断用に残す**。マージンで勝っていても**自分の絶対額が下がる型は避ける**（再投資が回らず翌日以降の生産能力が落ちる）
     - rating は「大きく劣化していないこと」の確認に回す。2026-09-05 に `> 0` から `≥ 0` に緩和（現プールは勝率が 0/100% に二極化していて rating の解像度が数試合しかない: `knowledge/analysis/2026-09-05_pool-bimodality.md`）
  5. 提出ログは `ops/submissions_log.jsonl`（preflight が自動追記）
  6. `too_good` が立った候補をキューに積むと、**検証済みの再評価 JSON がキューに記録される**（2026-09-06）。承認は `ops/approve_submit.py <gen>` だけでよく `--recheck` の再指定は要らない（記録が欠けている・SHA が変わっている場合は **fail-closed** で止まる）。非対話なら `--force-no-tty`。**必要な引数は `--list` がそのまま実行できる 1 行で出す。**
- **提出ポリシー（v0.5 §7b + 2026-09-05 の 2 段階化）**: 提出は価値がある時だけ。**昇格は自動、LB 計測は人の承認制**。本数ノルマ・Track A/B 交互は廃止。9/24 以降は自動提出停止、最終2本はユーザーと相談。
- **昇格の前に Codex レビュー**（`knowledge/REVIEW_CHECKLIST.md` の 7 観点）。依頼の手順はスキル `codex-review` に従う。指摘は実コードで検証してから採否を決め、修正は Implementer が行う。結果は `agents/genNNNN/meta.json` の `review` オブジェクト（`date` / `candidate_sha256` / `findings` / `blocking_resolved`）に書く。**これが無い・SHA が今の main.py と違う・即死級が未修正なら preflight が昇格提出を拒否する。** 提出後レビューは廃止。
- **ミクロ監査を必ず通す**: 新世代のスモークは `harness/micro_audit.py <replay> --assert`（利用率・収量・未使用タイル等。基準は `control/targets.json` の `micro`）。緩めた項目は `--limit` で明示し EXP に書く。マクロ指標（unfed/uncared/move%）が綺麗でも資金が半分だった gen0022 の教訓。
  - **`unfed_days` / `uncared_days` / `noop_total` は 0 が必須**（2026-09-06 追加）。**これが NG のまま評価に回さない。** gen0040 を unfed 3 日のまま 24 シード回してしまった（`knowledge/experiments/EXP0040_more-sheep.md`）。この 3 つは運用の合格ラインであってエンジンが強制する 0 ではない（`control/targets.json` の各 `_` 付き説明を参照）。
- **修正台帳と照合する**: 新世代を作ったら `ops/check_fixes.py agents/genNNNN/main.py --show-open`（台帳は `knowledge/FIXES.md` ＋ `control/fixes.json`）。**世代は不変で新世代は親のコピーなので、非昇格世代に入れた修正は親が変わると消える**（gen0023 の fix2 が 13 世代あとに同じ指摘で戻ってきた）。レビューで `deferred` にした指摘はその場で台帳に足す（`--audit` が未登録を落とす）。
- **検出限界**（`knowledge/analysis/2026-09-05_seed-detection-limit.md`）: スモーク ≤8 は動作確認専用。**打ち切り 12 ／ 方向判断 24 ／ 昇格 50 シード**。スモークの数字で「改善した」と書かない。
- **強帯（tier=strong）を必ず見る**: 判定量は `gate.strong_margin_delta_paired`（マージン。全体ゲートと同じ定義に統一。`strong_money_delta_paired` と `strong_slope_delta` は診断用）。**点推定が負なら前進と数えない**（2026-09-06 改訂）。**点推定が正で CI が 0 をまたぐのは「検出不能」で、棄却しない**（`gate.pass` を満たすなら昇格してよい）。強帯は 8 体しか居ないので CI が広く、CI 下限 > 0 を課すと昇格ゲートより厳しくなる（`knowledge/analysis/2026-09-06_strong-band-rule.md`）。
- **評価の相手プール**: `control/sparring_pool.json`（`agents/sparring/` の公開エージェント + starter + 中間帯の自系統世代）。**王者はプールに入れない**（恒久規約・2026-09-10 案 2）。`evaluate.py` は自己対戦を除くので、王者がプールに居ると王者交代のたびに候補（13 体）と王者評価（12 体）で対応付けが割れ `rating_delta` が甘くなる。`agents/sparring/` は**スパーリング専用・提出禁止・丸写し禁止**。プールを変えたら `harness/rate_pool.py --write` と王者ベースラインの取り直しが必須。
- **毎晩の回収**: `ops/collect_feedback.py`（自分の試合）＋ `ops/fetch_top_replays.py`（LB 上位同士の試合）＋ `ops/lb_calibration.py`（順位・相関 n・キャリブレーション判定）＋ `ops/top_meta_gap.py`（上位メタとの差）。**これは `ops/overnight.sh` が先に実行する**ので、サイクルは再実行しない。**キャリブレーション判定は「ローカル vs 実戦の勝率差」**（2026-09-10 改訂。LB スコアの大小では判定しない）。CI が 0 をまたげば「判定不能」で警告は出ない。警告が出たら指標監査を最優先（`knowledge/analysis/2026-09-10_metric-audit.md`）。
- **評価は自分で待たない**: `ops/eval_queue.py submit ...` で積んでサイクルを終える。ランチャーが実行し、結果が要るサイクルの前に完了を待つ。
- **最終評価は最新2提出のみ。** 提出は個人のアクティブ提出を押し出しうる。終盤（9月下旬）は特に慎重に。
- Kaggle トークン・認証情報はコミットしない。
- kaggle CLI の `config set competition` を使ったら必ず `config unset` で戻す（個人利用と設定共有のため）。

## 環境

- Python: `.venv/bin/python`（3.11、kaggle-environments 1.32.7）
- kaggle CLI: `uvx --from 'kaggle==2.2.4' kaggle ...`
- ゲーム仕様の一次情報: `.venv/.../envs/kaggriculture/README.md` と `AGENTS.md`

## 構成

**エージェントと評価**
- `agents/genNNNN/main.py` — 本番エージェント世代（L2）。`meta.json` に親世代・仮説・ゲート結果・**`mechanisms` 台帳**
- `harness/run_match.py` — FR-1 単戦（シード指定・時系列JSON保存）
- `harness/evaluate.py` — FR-2 評価 v2（プール・レーティング／対応付き絶対資金／後半傾き／**強帯差分**／**too_good フラグ**）
- `harness/rate_pool.py` — 相手プールの固定レーティング（総当たり Bradley-Terry）
- `harness/audit_replay.py` — 労働監査（unfed/uncared/move%）。`--targets` で上位の現金曲線との差
- `records/` — 対戦結果JSON（gitignore、ローカルのみ）

**運用（夜間ループ）**
- `ops/overnight.sh` — ランチャー（ユーザーが就寝前に起動）。回収を先に実行し、評価ジョブを引き受け、**セッション上限に当たったらリセット時刻まで待って同じサイクルをやり直す**（`OVERNIGHT_RESUME_AFTER_LIMIT=0` で旧挙動）
- `ops/NIGHTLY.md` / `ops/WRAPUP.md` — 各サイクル／締めセッションの指示書
- `ops/eval_queue.py` — **評価ジョブのキュー**。サイクルは submit して終える（LLM をポーリングに使わない）
- `ops/collect_feedback.py` — FR-6 回収（レーティング推移 → `ops/ratings_log.jsonl`、リプレイDL）
- `ops/lb_calibration.py` — LB 順位・上位10%距離・**ローカル指標 vs LB の相関 n**
- `ops/fetch_top_replays.py` — LB 上位同士のリプレイ回収 → `replays/top/`
- `ops/top_meta_gap.py` — 上位メタ（`../shared/top_meta`）と王者の骨格・市場ギャップ → `state/top_meta/gap_LATEST.md`（毎晩。回収ステップ）
- `ops/fetch_discussions.py` — Discussion 原文コーパス（`knowledge/discussions/`。grep 用）
- `ops/daily_report.py` — FR-8 日次レポート → `state/reports/YYYY-MM-DD.md`（先頭が採用判断シート）
- `ops/record_usage.py` — トークン/コスト記録 + セッション上限検知（→ `state/ops_alerts.jsonl`）とリセット時刻の抽出（→ `KAGG_LIMIT_RESET_FILE` が指す受け渡しファイル）

**提出**
- `ops/preflight_submit.py` — 提出前チェック。`--reason promote`（昇格＝自動）/ `measure`（LB計測＝承認制）
- `ops/approve_submit.py` — **人が**承認キューを承認・却下する（夜間セッションからは実行不可）
- `ops/static_check.py` — 提出物の AST 検査（agent 束縛・標準ライブラリのみ・I/O 無し）
- `ops/verify_submission.py` — 提出後の一致検査（実戦分布 vs ローカル分布）
- `ops/reform_pool.py` — プール改編の 3 点セット（enabled 変更 → rate_pool → 王者ベースライン取り直し）
- `ops/audit_sparring.py` — 公開実装の欠陥 audit（差別化の候補を探す）

**規約と記録**
- `control/DIRECTIVES.md` — **人からの指示・質問**（サイクルは STATUS より先に読む）
- `control/targets.json` — 外の数字（上位の現金曲線・最終中央値・強帯資金）
- `control/champion.json` — 現王者（機械可読）
- `control/submit_queue.jsonl` — 承認待ちの提出（append-only）
- `knowledge/IDEA_POLICY.md` — 出してよい仮説 / 出さない仮説
- `knowledge/REVIEW_CHECKLIST.md` — 昇格前クロスレビューの 7 観点
- `knowledge/FIXES.md` ＋ `control/fixes.json` — **世代から独立した修正台帳**（検査は `ops/check_fixes.py`）
- `knowledge/experiments/EXPNNNN_*.md` — FR-4 実験記録 ／ `CLOSED.md` — 閉じた系統の台帳
- `knowledge/analysis/` — 実測メモ（検出限界・sparring audit・上位試合の解剖）
- `state/HANDOFF.md` — **現在地の要約（≤100 行）。サイクルの必読**
- `state/STATUS.md` — 経緯。毎晩の更新は「次の一手」節のみ
- `state/retro/` — 3 夜ごとの振り返り（`TEMPLATE.md`）

## 実験記録フォーマット（FR-4）

`knowledge/experiments/EXP0001_short-slug.md`。**必須欄を空のまま昇格させない**（2026-09-05 改訂）:

```markdown
---
status: in_progress   # in_progress | done。評価を回し始めたら in_progress で先にコミットする
gen: genNNNN
parent: genNNNN
---

# EXP0001: タイトル
- 日付: YYYY-MM-DD ／ 世代: genNNNN（親: genNNNN）
- 仮説: なぜこの変更が勝率を上げるか（`knowledge/IDEA_POLICY.md` の「出してよい」側のどれか）
- 変更: 何をどう変えたか
- 結果: evaluate.py の数値（pool.rating ±se ／ 対応付きマージン差と CI ／ 対応付き資金差 ／ slope ／ **強帯マージン差と CI**）
- **判定**: 昇格 / 棄却 / 検出不能 — `指標: pool(v0.5) ／ シード: NN ／ CI: [lo, hi]` を必ず併記
- **説明（この分野を知らない人向け 3 行）**: 何を変え、何が起き、なぜそうなったか
- **改善幅は seed ブレより大きいか**: 対応付き資金差の CI 下限が 0 を超えているか（数値で）
- **目標曲線との差**: `control/targets.json` の d5/d10/d15/d20 現金に対してどの日で遅れるか
- **ミクロ指標**: 利用率 / 未使用タイル / 収量(小麦・メロン・イチゴ) / 3歩以上% / 最終WATER時刻
  （`harness/micro_audit.py <replay> --json`。基準は `control/targets.json` の `micro`）
- **レビュー記録**: Codex レビューの日付・指摘・対応（人が読む要約。機械チェックは `meta.json` の `review`）
- **却下した小手先案**: `案 / 該当する IDEA_POLICY 禁止項目`（無ければ「なし」）
- 学び: 次に活きる知見（ゲーム構造への還元）
```

- 棄却・閉鎖したら `knowledge/experiments/CLOSED.md` に 1 行足す（指標・シード・CI 付き）。
- 「CI が 0 をまたいだ」は**棄却ではなく検出不能**。CLOSED.md の `再検討` に反映する。

## 判断の規約（2026-09-05 追加）

- 仮説の出所は `knowledge/IDEA_POLICY.md`。禁止側の案は却下し、件数を EXP に残す。
- 人からの指示・質問は `control/DIRECTIVES.md`。夜間サイクルは STATUS より先に読む。
- 昇格前レビューの観点は `knowledge/REVIEW_CHECKLIST.md`。
- 外の数字（上位の現金曲線）は `control/targets.json`。
- 引き継ぎは `state/HANDOFF.md`（≤100 行。2026-09-06 に 60 → 100。**上限は「読む前に諦めない長さ」の
  ためであって、圧縮そのものが目的ではない**。溢れたら今夜の詳細から STATUS へ移す。王者・次の一手・
  承認待ち・人への質問は削らない）。STATUS.md は経緯の置き場。

## サブエージェント

`.claude/agents/` に Strategist / Implementer / Evaluator / Analyst / Operator / Scout を定義済み。Supervisor（メインセッション）が委譲する。

## 並行セッションと worktree（このリポジトリ固有の差分。共通ルールはグローバル CLAUDE.md とスキル `worktree-flow`）

- 運用区分: **個人プロジェクト**。
- **worktree セッションでは提出も承認もしない。** `ops/preflight_submit.py` / `ops/approve_submit.py` と `control/SUBMIT.lock` の確認は main checkout のセッション（チェック無しで開いたもの）からだけ行う。`SUBMIT.lock` は git 管理外なので worktree からは存在しないように見える。ロックが無いように見えても提出してはならない。
- worktree セッション開始直後のセットアップ（git 管理外の実体を共有する。cwd は worktree ルート、`../../../` がリポジトリルート。`.gitignore` はこのリンク形も無視する）:
  ```bash
  for d in .venv records; do [ -e $d ] || ln -s ../../../$d $d; done   # replays logs も必要なら同様に
  ```
- `state/` と `control/` は「記憶の正」なので分岐を長く持たない。1 実験系統ごとにセッションを切り、評価が終わったら当日中にマージする。並行セッションも `state/HANDOFF.md` を触っている可能性が高いので、rebase 時の競合は両方の節を残す方向で解決する。
