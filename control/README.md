# control/

- `SUBMIT.lock` — **このファイルが存在する間、システムは絶対に提出しない。** 停止するには `touch control/SUBMIT.lock`、再開するには削除。
- `submission_policy.json` — [auto] 提出の自主上限などのポリシー。
  今夜だけ上限を変えたいときはファイルを書き換えず `ops/overnight.sh --auto-cap N`
  （= 環境変数 `KAGG_AUTO_DAILY_CAP`。`kaggle_daily_limit` は超えられない）。
