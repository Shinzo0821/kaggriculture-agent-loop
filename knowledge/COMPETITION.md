# Kaggriculture コンペ確定情報

取得日: 2026-08-30 ／ 取得方法: `kaggle competitions pages list kaggriculture --content`（kaggle CLI 2.2.4、デフォルトコンペを一時設定して取得）
原文キャッシュ: このリポジトリでは保持しない（必要なら再取得）。要約の一次情報は Kaggle コンペページ。

## スケジュール（すべて 11:59 PM UTC）

| 日付 | イベント |
| --- | --- |
| 2026-07-29 | 開始 |
| 2026-09-30 | **最終提出締切** |
| 2026-10-01 〜 約 10-15 | 追加対戦期間（LB収束まで）。終了時点で最終LB確定 |

## 賞金

- **1位〜10位: 各 $5,000**（傾斜なし・均等配分）。賞金圏 = **トップ10**。

## 提出ルール（重要）

- **1日5提出まで**（チーム単位、UTC日区切りと推定）。
- **最新2提出のみ**がラダーで追跡され、**最終評価も最新2提出**が対象。
  - ⚠️ 含意: 提出のたびに古い提出が評価対象から外れる。ユーザー個人の提出と共有のため、**[auto]提出は個人のアクティブ提出を押し出す**リスクがある。終盤は特に注意。
- 提出時に Validation Episode（自己対戦）が走り、エラーなら `Error` 扱い。ログDL可。
- 評価はスキルレーティング（勝敗のみ反映、点差は無関係）。最終はエピソード群に対する Bradley-Terry トーナメント。
- チーム最大5人。No Ingress/Egress（対戦中の外部通信禁止）。
- AMLT（自動MLツール）の利用は明示的に許可されている。
- リプレイは公開されうる（他者のリプレイも取得・分析可）。

## 実行環境

- `actTimeout = 1`（1ターン1秒）。累積猶予は environment 仕様準拠（remainingOverageTime、既定60秒）。
- 提出物: `main.py`（root、`agent` 関数）単体 or tar.gz。ファイルは `/kaggle_simulations/agent/` に展開される。
- RAM/CPU/サイズ上限: コンペページはテンプレ変数未展開で**数値未確認**。Docker イメージは kaggle-environments リポジトリの docker/Dockerfile 参照。Phase 3 でモデル同梱する際に要実測。

## ゲーム仕様の一次情報

- `.venv/lib/python3.11/site-packages/kaggle_environments/envs/kaggriculture/README.md`（ルール・数値テーブル・価格関数）
- 同 `AGENTS.md`（観測・行動フォーマット、CLIワークフロー）
- kaggle-environments **1.32.7** で確認。バージョン更新は Scout が定期チェック。

## 要点（ゲーム仕様、README より抜粋）

- 720ターン（24t/日 × 30日）、最終所持金勝負。初期 $3,000、NWクアドラント25タイルのみ解放。
- 土地: NE/SW/SE を $1k/$2k/$4k で購入可。
- starter ベースラインは「farmer 1体・1タイルのニンジンループ」で極めて弱い。
- 市場価格: 資源ごとに形状関数（linear/sq/sqrt/log/hinge）で在庫依存。プレミアム品（イチゴ・メロン・ミルク・ウール）は売り崩すと $1 床に張り付く。
- 町の店舗が3日ごとにランダム解禁（重複あり、最大8）→ 需要が段階的に増える。

## CLI 運用メモ

- kaggle CLI は `uvx --from 'kaggle==2.2.4' kaggle ...` で実行（グローバル未インストール）。
- 認証: `~/.kaggle/kaggle.json`（LEGACY_API_KEY）。
- `kaggle competitions pages list <comp>` は位置引数がバグっぽい: **`kaggle config set -n competition -v kaggriculture` で一時設定してから `pages list --content` を実行し、終わったら `kaggle config unset -n competition` で戻す**こと（個人利用と設定を共有しているため必ず戻す）。
- エピソード/リプレイ/ログ: `kaggle competitions episodes <SUBMISSION_ID>` / `replay <EPISODE_ID>` / `logs <EPISODE_ID> <agent_idx>`。
