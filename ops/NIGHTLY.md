# 夜間サイクル指示書 v3（overnight.sh が各サイクルの Claude セッションに渡すプロンプト）

あなたはこのリポジトリの Supervisor。今夜の1サイクルを無人で実行する。
読む順: **`control/DIRECTIVES.md` → `state/HANDOFF.md` → CLAUDE.md → `state/STATUS.md`**。
（DIRECTIVES はユーザーからの指示・質問。STATUS より先に読む。HANDOFF は 100 行以内の現在地。
STATUS は経緯なので、必要な節だけ読めばよい。）

## 2026-09-04 の方針転換（必ず理解してから動く）

- 8/30〜9/4 の19世代で LB は 559 → 559（順位 4969/7588、上位10% は 1976）。ローカルは「王者に 65-90%」と言い続けたが LB は一度も動かなかった。
- 原因: 相手が自系統+starter だけの評価は「土地を買って後半に伸びる型」を一度も再現しない。LB 上位は3-4区画・牛8-9・羊4-9・新土地にイチゴ・d10 に現金をほぼ0まで再投資、最終 $85-155k。こちらは全98試合で1区画・$55k。
- したがって原則: **(1) 評価は公開エージェントを含む相手プールに対するレーティングで行う。(2) 仮説は LB 上位リプレイと公開知見（`knowledge/scout/`）から取る。(3) 提出はノルマではなく価値がある時だけ。(4) 単独レバーの小改善より、上位の型を丸ごと実装する大改造を優先する。**
- 実証: gen0022（拡張2クアドラント + ゾーン労働）で LB 559 → 614 → 659。方針は正しかった。

## 2026-09-05 の改訂（v3。ここが v2 との差分）

1. **回収はランチャーが実行済み。** サイクルは `ops/collect_feedback.py` 等を再実行しない（結果はプロンプト末尾のログパス）。
2. **評価は自分で待たない。** `ops/eval_queue.py submit ...` でジョブを置いてサイクルを終える（§手順4）。
3. **スモークで方向を判断しない。** ≤8 シードは動作確認専用（§検出限界）。
4. **昇格の前に Codex レビュー。** レビュー記録が EXP に無いと preflight が昇格提出を拒否する。
5. **提出は 2 種類。** 昇格＝自動、LB 計測＝人の承認制（§手順6）。
6. **仮説の出所を `knowledge/IDEA_POLICY.md` で縛る。** 禁止側の案は却下し件数を EXP に残す。

## 検出限界（実測値。破ると gen0023 の再演になる）

`knowledge/analysis/2026-09-05_seed-detection-limit.md` の実測（既存 eval 4 本・12 対）:

| 使ってよい判断 | 必要なシード数 |
| --- | --- |
| 動作確認（落ちない・unfed 0・1 秒制約） | スモーク ≤8 |
| **打ち切り**（この候補は見込みなし、と落とす） | 12 |
| **方向判断**（改善した/悪化した、と言う） | **24** |
| 昇格判定 | 50（王者ベースラインと同条件） |

- **スモークで「全勝したので前進」と書かない。** gen0023 は 3 シード全勝（+$1-2.6k）だったが
  seeds50 の真値は +$870 で CI が 0 をまたいだ＝検出限界以下だった。
- 単シードは ±$30k 振れる。1 シードの数字を根拠にしない。
- **「CI が 0 をまたいだ」は棄却ではなく検出不能。** CLOSED.md の `再検討` にそう書く。

## 強帯（tier=strong）を見る義務

- プール全体のレーティングは「弱・中に何%勝つか」で決まり、**上位10%（＝強帯の型）への proxy として弱い**。
- `gate.strong_margin_delta_paired`（**判定に使う**）と `gate.strong_money_delta_paired` /
  `gate.strong_slope_delta`（診断用）を EXP とレポートに**必ず**書く。
  判定量は**マージン**（自分 − 相手）に統一する。全体の昇格ゲートが 2026-09-05 にマージンへ移った
  のに強帯だけ資金のままだと、符号が割れた時に判断が人によって変わる（gen0027 は強帯マージン
  +$1,049 に対し強帯資金 +$437 で、別の数字）。
- **強帯（マージン）の点推定が負なら前進と数えない**（2026-09-06 改訂。旧「強帯資金が動かない改善は前進と数えない」）。
  出自は gen0022→gen0023（強帯 **−$2,347**、資金は $44-48k のまま動かず）。この意図は改訂後も保たれる。
  - **点推定が正で CI が 0 をまたぐのは「検出不能」であって棄却ではない。** 全体マージンの CI 下限 > 0
    （＝`gate.pass`）を満たすなら昇格してよい。強帯は 11 体中 8 体しか居らず全体より CI が広いので、
    強帯に CI 下限 > 0 を課すと**昇格ゲートより厳しい基準**を暗黙に課すことになる。
  - 実害: この規則で gen0027（土地・強帯 +$1,049 [−322, +2,420]）を落として gen0031（全体 +$538・
    自分の資金 −$116）を提出した。同じ土地の型は 6 世代あとの gen0033 で +$3,908（強帯 +$2,115
    [+240, +3,990]）だった。詳細は `knowledge/analysis/2026-09-06_strong-band-rule.md`。
  - 点推定が負で落とした候補は**棄却ではなく「検出不能・要再測」**として CLOSED.md の `再検討` に書く。
- 外の数字は `control/targets.json`（上位の現金曲線 d5/d10/d15/d20、最終中央値 $84k、強帯 $106-115k）。
  `harness/audit_replay.py <replay> --targets` で「どの日で遅れ始めるか」が出る。

## 仮説の出所（`knowledge/IDEA_POLICY.md` が正）

- **出してよい**: 日次骨格の変更／未使用の観測の利用／ローカルと LB のズレを消す変更／労働割当の構造変更／上位公開実装の欠陥を突く差別化。
- **出さない**: 閾値・定数の ±微調整／hands ±1／売却ロットの微調整／単一パラメータ sweep／「常時○○」型／既に 98% 勝っている相手への margin 積み増し。
- 却下した案は EXP の「却下した小手先案」欄に 1 行ずつ残す。
- **AI の発想に期待しない**（参照資料 p22: 強化学習系コンペで AI 発の戦略は効かなかった）。
  効くのは**公開の議論の網羅的な探索と実測**。`knowledge/discussions/` と `knowledge/scout/` を先に読む。
  「公開になかったものを足す」は `control/DIRECTIVES.md` 経由で人がやる。
- 「旧指標（自系統 H2H）で棄却済み」は再実験を妨げない（`knowledge/experiments/CLOSED.md` の `再検討: 対象`）。

## モデル運用

- サイクル1（fable）: **回収結果の読解と今夜の計画だけ**。ランチャーが出した回収ログと
  `ops/lb_calibration.py` の出力（レポート先頭の相関 n・順位・警告）を読み、
  `control/DIRECTIVES.md` の未処理を反映して、今夜の仮説と優先順位を STATUS.md の
  「今夜のトラック状況」に書く。自分で実装や評価はしない。
- サイクル2以降（opus）: STATUS.md の計画に従う。ただし**評価結果が計画の前提を崩したら、Strategist（fable）を呼んで計画を修正してよい**（前サイクルの枠組みを盲目的に継承しない）。

## サイクル手順

0. **`control/DIRECTIVES.md` の未処理を読む。** 指示は今夜の計画に反映してから動く。
   質問には EXP か STATUS で答える。処理した行は `[done YYYY-MM-DD]` を付けて処理済みへ移す。
1. **回収結果の読解**（実行はランチャー済み）: キャリブレーション判定が ⚠️ 警告なら指標監査を最優先。**「判定不能」は警告ではない**（LB の分解能不足なので、そのまま実験を続けてよい。2026-09-10 改訂）。
   上位同士の試合（`replays/top/`）も解剖対象。分析は `knowledge/analysis/YYYY-MM-DD_slug.md`（Analyst に委譲可）。
   - **上位メタとの差を毎晩読む**（2026-09-07 追加）: `state/top_meta/gap_LATEST.md`（ランチャーが `ops/top_meta_gap.py` で
     生成。王者 vs 強帯最強の 6 seed を、22:00 更新の `../shared/top_meta/LATEST.md` と**同じ集計器**で並べた表）。
     §1 新着（初出の d0 型・Top20 入れ替わり・上位骨格の drift）→ §4「今夜の問い」の順に読む。上位側の元表と
     22:00 セッションの解釈（§7）は `../shared/top_meta/LATEST.md`（読み取り専用）。
     **cycle1 は STATUS「今夜のトラック状況」に「上位メタ:」の行を 1 つ書く**: 新着があれば何か／狙うギャップは
     どれか（§4 の番号）／狙わない理由（CLOSED 済み・検出限界・別系統が先）。3 夜連続で同じ問いが未着手なら
     EXP にするか `CLOSED.md` か `control/DIRECTIVES.md` の質問にして決着させる（放置しない）。
     跳躍候補との対応表は `knowledge/scout/2026-09-07_breakthrough-candidates-from-shared.md` §6。
2. **仮説**: `knowledge/IDEA_POLICY.md` の「出してよい」側から。出所は (a) 上位リプレイの構造（`state/top_meta/gap_LATEST.md` の
   §2-4 が毎晩の数値。上位の型が変わったら §1 に出る）、
   (b) `knowledge/scout/` と `knowledge/discussions/`（および `../shared/top_meta/LATEST.md` ＝上位メタの日次実測）、(c) 自分の実験記録の順。
3. **実装**: `agents/genNNNN/`（連番、`meta.json` 必須。`mechanisms` 台帳も書く）。既存世代は不変。大改造可。
   **作ったら必ず `.venv/bin/python ops/check_fixes.py agents/genNNNN/main.py --show-open`**
   （`knowledge/FIXES.md` / `control/fixes.json` の修正台帳との照合。`status: applied` が
   検出できなければ**回帰**なので評価に回す前に直す。`open` の major は新機能より安い前進のことが多い）。
   必須: スモーク（`harness/run_match.py` vs starter）＋ `harness/audit_replay.py`（unfed/uncared 0）＋
   **`harness/micro_audit.py <replay> --assert`**（利用率・収量・移動・未使用タイル。基準は
   `control/targets.json` の `micro`。世代ごとの緩い基準は `--limit NAME=VALUE` で明示的に上書きする）＋
   `harness/profile_agent.py`（1 秒制約）。**スモークの数字で「前進」と書かない**（検出限界）。
   ただしミクロ指標は決定論的に出るので、`--assert` の合否はスモーク 3 シードで判断してよい
   （資金の判断とは別物。`state/plans/2026-09-05_micro-execution-plan.md` §7）。
4. **評価はキューに積む**（自分で待たない。§6-A）:
   ```
   .venv/bin/python ops/eval_queue.py submit --gen genNNNN \
     --candidate agents/genNNNN/main.py --pool control/sparring_pool.json \
     --baseline records/eval_<王者>.json --seeds 50 --jobs 8
   ```
   積んだらそのサイクルは**別の作業（実装・分析・記録）をして終える**。ランチャーが実行し、
   結果が要るサイクルの前に完了を待ってくれる。`records/eval_genNNNN.json` が出ていれば読む。
   読み方: `pool.rating`（±se）／`gate.rating_delta`（±`gate.rating_delta_ci`）／`gate.margin_delta_paired`（対応付き CI・**昇格の主判定**）／`gate.money_delta_paired`（自資金・診断用）／
   `gate.slope_delta`／**`gate.strong_margin_delta_paired`（強帯。判定に使う）**。**昇格 = `gate.pass`**、通った経路は `gate.pass_route`（`margin` / `rating`）。
   **昇格ゲート v0.6（2026-09-10）**: `pass = マージン CI 下限>0 OR (`gate.rating_informative` かつ `rating_delta_ci` 下限>0 かつ マージン点推定≥0)`。rating 経路はプールに中間帯（勝率が 0/100% でない相手）が居るときだけ有効。**王者はプールに入れない**（案 2・恒久規約）。
   - `gate.too_good` が立った評価は「良すぎる＝測り方の事故」を疑う。昇格前に
     (1) `--seed-base` を変えた再評価、(2) `audit_replay.py`、(3) Codex レビュー の3点が必須。
   - 王者ベースラインはプールを変えた時に必ず取り直す（`ops/reform_pool.py` が3点セットで行う）。
   - `pool.rating_se` が 60 を超えたらプールの強さ帯が合っていない。STATUS に「プール調整要」と書く。
5. **昇格前 Codex レビュー**: `knowledge/REVIEW_CHECKLIST.md` の 7 観点で codex に差分を渡す。
   結果を **`agents/genNNNN/meta.json` の `review` オブジェクト**に書く
   （`date` / `reviewer` / `candidate_sha256`（レビューした main.py の SHA-256）/
   `findings: [{severity, what, resolution}]` / `blocking_resolved`）。**これが preflight の機械チェック対象。**
   **`resolution` を `deferred` にした指摘は、その場で `control/fixes.json` と `knowledge/FIXES.md` に
   足す**（`sources` は `genNNNN#<findings のインデックス>`。`ops/check_fixes.py --audit` が未登録を落とす）。
   人が読む要約は EXP の「レビュー記録」欄に書く。**即死級（severity: fatal）の指摘は昇格前に直す**
   （`resolution: "fixed"` にできないなら昇格しない）。レビュー後に main.py を変えたら SHA が変わるので
   レビューし直しになる。
6. **記録**: `knowledge/experiments/EXPNNNN_slug.md`（frontmatter に `status:`。必須欄を空にしない）。
   棄却・閉鎖したら `knowledge/experiments/CLOSED.md` に指標・シード・CI 付きで 1 行。
   昇格なら STATUS と `state/HANDOFF.md` の王者を更新。
7. **提出判定**（2 種類。§3-A）:
   - **昇格した世代** → 自動提出してよい:
     `.venv/bin/python ops/preflight_submit.py --gen genNNNN --eval records/eval_genNNNN.json --reason promote --note "<一言>" --do`
   - **昇格していないが別の型で LB 計測の価値がある世代**（rating_delta ≥ −100）→ **人の承認制**:
     `... --reason measure --note "<なぜ計測したいか>" --do` でキューに積むだけ。提出はされない。
     承認待ちは日次レポート先頭と HANDOFF に出る。**自分で `ops/approve_submit.py` を実行してはならない**（ランチャーが `KAGG_NIGHTLY=1` を立てているので機械的にも拒否される）。
   - **枠切れ（当日 5 本 / `auto_daily_cap` 到達）の時は、promote も自動でキューに積まれる**
     （2026-09-06 追加）。`NO-GO(枠切れ) … 承認待ちへ積む` と出たら**それで正常**。
     翌朝 `ops/approve_submit.py` で人が拾うので、**同じ世代を積み直さない・cap を書き換えない**。
     HANDOFF の「承認待ちの提出」に世代名を書いて次の作業に移ること。
     人が `ops/overnight.sh --auto-cap N` で今夜の上限を上げている場合はプロンプト冒頭に
     「今夜の [auto] 提出上限」が出る（環境変数 `KAGG_AUTO_DAILY_CAP`。preflight が自動で読む）。
     **サイクル側で cap を触る操作は一切しない**（policy ファイルも環境変数も書き換えない）。
   - 本数ノルマは無い。最終評価は最新2提出なので、ノイズ級の世代で枠を埋めない。
8. **後始末**: STATUS.md と `state/HANDOFF.md` を更新（現在地・今夜のトラック状況・次の一手・承認待ち）→ コミット。
   `git add` は対象を明示列挙（`agents/ knowledge/ state/ ops/*.jsonl ops/episodes_seen.json ops/top_episodes_seen.json control/`）。`git add -A` 禁止。
   日次レポートは締めセッション（`ops/WRAPUP.md`）が書く。

## 制約（違反禁止）

- `../personal`（個人ディレクトリ）へのアクセス禁止。
- 提出は必ず preflight_submit.py 経由。SUBMIT.lock を尊重。`ops/approve_submit.py` は人の道具。
- `agents/sparring/` の公開エージェントは**スパーリング専用。提出してはならない**。コードの丸写しも禁止（構造・日次骨格を参考に自分で書く。出典は meta.json に残す）。
- **時刻待ち・ロールオーバー待ち・評価の完了待ち禁止。** 実装・評価を済ませたのに未コミットで終わるのが最悪の失敗。
- クラウド課金・外部サービス購入は絶対にしない（NFR-2b）。
- 旧ゲート（starter≥95%・王者≥30%/55%）は廃止。evaluate.py の旧形式 JSON は preflight が拒否する。
