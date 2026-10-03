#!/bin/bash
# 夜間自律ループのランチャー。寝る前にターミナルで実行する:
#   ops/overnight.sh [--auto-cap N]
#   OVERNIGHT_MAX_CYCLES=4 ops/overnight.sh   # サイクル数を一時的に上書き(policy は書き換えない)
#   OVERNIGHT_RESUME_AFTER_LIMIT=0 ops/overnight.sh   # セッション上限で待たずに締めへ
#   ops/overnight.sh --auto-cap 5             # 今夜だけ [auto] 提出上限を引き上げる
#     (既定は control/submission_policy.json の auto_daily_cap。policy は書き換えない。
#      環境変数 OVERNIGHT_AUTO_DAILY_CAP でも同じ。Kaggle の 5 本/日は超えられず、
#      個人の手動提出も同じ枠を食うので、5 を指定すると自動提出が枠を使い切りうる)
#
# - caffeinate でスリープを抑止(このスクリプトの生存中のみ)
# - control/submission_policy.json の max_cycles_per_night 回まで、
#   各サイクルを独立した claude セッション(-p)として起動する
# - 各サイクルの状態はリポジトリのファイルが正(途中でMacが落ちても翌晩そのまま継続)
# - 停止したいとき: Ctrl-C、または別ターミナルで touch control/SUBMIT.lock(提出のみ停止)
#
# 2026-09-09 の改修: 終了時刻(END_HOUR)を廃止し、ブレーキを 2 本に置き換えた。
#   (1) 夜間コスト上限 OVERNIGHT_MAX_COST_USD (既定 120, USD 整数)
#       起動以降に ops/token_log.jsonl へ積まれた cost_usd の合計がこれを超えたら
#       新しいサイクルを始めない。実績は最大 $74/夜・平均 $48/夜 なので通常は当たらない。
#       この cost_usd は API 換算の総額(サブスク枠内の分も含む)で、実課金の上界。
#   (2) 総稼働上限 OVERNIGHT_MAX_RUNTIME_MIN (既定 600 分 = 10 時間)
#       起動からの経過時間。旧 END_HOUR が持っていた「上限リセットを待ちすぎない」
#       仕事もこちらが引き継ぐ。
#   締めセッション(日次レポート)は**どちらの上限に当たっても必ず1回走る**。
#
# 2026-09-05 の改修(計画 §6):
#  §6-A 評価は LLM サイクルから切り離す。サイクルは ops/eval_queue.py submit でジョブを置いて
#       すぐ終わり、**ランチャー**がそれを実行する。LLM を完了待ちのポーリングに使わない。
#  §6-B 並列上限は「評価1本 + LLM 1本」。評価の直後の1サイクルだけ並走させ、
#       その次のサイクルの前には評価の完了を待つ(結果が要る作業をさせるため)。
#  §6-C セッション上限(record_usage.py が exit 4)を検出したら、**リセット時刻まで待って
#       同じサイクルをやり直す**(2026-09-07 改訂。以前は残りを諦めて締めに進んでいた)。
#       リセット時刻は record_usage.py が上限メッセージから読んで受け渡しファイル
#       ($LOGDIR/<RUN_ID>_limit_reset。KAGG_LIMIT_RESET_FILE で渡す)に書く。
#       読めなければ OVERNIGHT_LIMIT_FALLBACK_WAIT 秒待つ。リセットが稼働上限
#       (稼働上限 = 起動から OVERNIGHT_MAX_RUNTIME_MIN 分)より後、または待機が
#       OVERNIGHT_MAX_LIMIT_WAITS 回を超えたら締めに進む。
#       OVERNIGHT_RESUME_AFTER_LIMIT=0 で従来どおり即締め。
#  §6-D 回収スクリプト(純Python)はランチャーが先に実行する。cycle1(fable)は
#       「回収結果の読解と今夜の計画」だけに使う。
set -u
cd "$(dirname "$0")/.."

PYBIN=.venv/bin/python

# --check: 夜間運転の前提(claude認証・venv・kaggle CLI)だけ検証して終了。
# 就寝前の起動時にも同じ検証を自動実行し、失敗したら寝る前に気づけるよう即異常終了する。
run_precheck() {
  local ok=0
  echo "[check] claude -p ヘッドレス起動..."
  if ! out=$(claude -p "ツールを使わず OK とだけ答えて" --permission-mode bypassPermissions 2>&1); then ok=1; fi
  case "$out" in *"Not logged in"*) ok=1;; esac
  [ "$ok" -ne 0 ] && echo "[check] NG: claude が使えません: $out" && return 1
  echo "[check] venv..."
  [ -x "$PYBIN" ] || { echo "[check] NG: .venv がない"; return 1; }
  echo "[check] kaggle CLI..."
  uvx --from 'kaggle==2.2.4' kaggle competitions submissions kaggriculture >/dev/null 2>&1 \
    || { echo "[check] NG: kaggle CLI/認証"; return 1; }
  echo "[check] すべてOK"
}

# 引数: --auto-cap N=今夜の [auto] 提出上限、--check=前提チェックのみ
# (位置引数の終了時刻HH は 2026-09-09 に廃止。旧習慣で渡されても止めずに警告だけ出す)
DO_CHECK=0
AUTO_CAP="${OVERNIGHT_AUTO_DAILY_CAP:-}"
while [ $# -gt 0 ]; do
  case "$1" in
    --check) DO_CHECK=1; shift;;
    --auto-cap) shift; [ $# -gt 0 ] || { echo "--auto-cap に値がない"; exit 2; }
               AUTO_CAP="$1"; shift;;
    --auto-cap=*) AUTO_CAP="${1#*=}"
                  [ -n "$AUTO_CAP" ] || { echo "--auto-cap= に値がない"; exit 2; }
                  shift;;
    -*) echo "不明なオプション: $1"; echo "usage: ops/overnight.sh [--auto-cap N] [--check]"; exit 2;;
    # 旧 HH(0-23) だけ後方互換で受け流す。それ以外の位置引数はオプションの打ち間違い
    # (例: `--auto-cap` を `auto-cap` と書いた)なので、無人運転に入る前に止める。
    [0-9]|0[0-9]|1[0-9]|2[0-3])
       echo "[overnight] 警告: 位置引数 '$1' は無視します(終了時刻HH は廃止。稼働上限は OVERNIGHT_MAX_RUNTIME_MIN、コスト上限は OVERNIGHT_MAX_COST_USD)"; shift;;
    *) echo "不明な位置引数: $1"; echo "usage: ops/overnight.sh [--auto-cap N] [--check]"; exit 2;;
  esac
done

if [ "$DO_CHECK" = "1" ]; then
  run_precheck; exit $?
fi

# --auto-cap: 今夜だけ [auto] 提出上限を上書きする(policy ファイルは書き換えない)。
# preflight_submit.py が KAGG_AUTO_DAILY_CAP を読む。claude -p の子プロセスまで届くよう export する。
POLICY_CAP=$(python3 -c "import json; print(json.load(open('control/submission_policy.json'))['auto_daily_cap'])")
KAGGLE_LIMIT=$(python3 -c "import json; print(json.load(open('control/submission_policy.json'))['kaggle_daily_limit'])")
CAP_NOTE=""
# 親シェルから継承した KAGG_AUTO_DAILY_CAP は捨てる。残っていると「表示は既定 3 なのに
# preflight は 5 で動く」ずれが起きる(2026-09-07 codex P1-2)。入口は --auto-cap と
# OVERNIGHT_AUTO_DAILY_CAP の 2 つだけ、どちらもここで検証してから export する。
unset KAGG_AUTO_DAILY_CAP
if [ -n "$AUTO_CAP" ]; then
  # 桁数も縛る: 巨大な数字列は下の -gt がシェルの整数範囲を溢れて比較に失敗する
  case "$AUTO_CAP" in
    [0-9]|[0-9][0-9]) ;;
    *) echo "--auto-cap は 0-99 の整数で指定: $AUTO_CAP"; exit 2;;
  esac
  if [ "$AUTO_CAP" -gt "$KAGGLE_LIMIT" ]; then
    echo "--auto-cap=$AUTO_CAP は Kaggle の実制限 ${KAGGLE_LIMIT} 本/日を超えている"; exit 2
  fi
  export KAGG_AUTO_DAILY_CAP="$AUTO_CAP"
  CAP_NOTE="  auto_daily_cap=${AUTO_CAP} (policy 既定 ${POLICY_CAP} を今夜だけ上書き)"
  EFFECTIVE_CAP="$AUTO_CAP"
else
  EFFECTIVE_CAP="$POLICY_CAP"
fi
# 既定は control/submission_policy.json の max_cycles_per_night。
# 一時的に減らす/増やすときは env で上書きする(policy は書き換えない):
#   OVERNIGHT_MAX_CYCLES=4 ops/overnight.sh
MAX_CYCLES="${OVERNIGHT_MAX_CYCLES:-$(python3 -c "import json; print(json.load(open('control/submission_policy.json'))['max_cycles_per_night'])")}"
case "$MAX_CYCLES" in
  ''|*[!0-9]*|0) echo "OVERNIGHT_MAX_CYCLES は 1 以上の整数で指定: $MAX_CYCLES"; exit 2;;
esac
# 評価1本の上限時間(秒)。これを超えたら評価を殺して次に進む(無限待ち防止)。
EVAL_TIMEOUT="${OVERNIGHT_EVAL_TIMEOUT:-4800}"
# セッション上限に当たったときの再開設定(§6-C 2026-09-07 改訂)
RESUME_AFTER_LIMIT="${OVERNIGHT_RESUME_AFTER_LIMIT:-1}"   # 0 なら待たずに締めへ
MAX_LIMIT_WAITS="${OVERNIGHT_MAX_LIMIT_WAITS:-3}"         # 一晩に待つ回数の上限
LIMIT_FALLBACK_WAIT="${OVERNIGHT_LIMIT_FALLBACK_WAIT:-3600}"  # リセット時刻が読めない時の待ち(秒)
LIMIT_BUFFER="${OVERNIGHT_LIMIT_BUFFER:-120}"             # リセット直後を避ける余裕(秒)
LIMIT_WAITS=0
# 夜のブレーキ(2026-09-09。旧 END_HOUR の置き換え)
MAX_COST_USD="${OVERNIGHT_MAX_COST_USD:-120}"             # 起動以降の cost_usd 合計の上限(USD 整数)
MAX_RUNTIME_MIN="${OVERNIGHT_MAX_RUNTIME_MIN:-600}"       # 起動からの総稼働上限(分)
# 数値 env は起動時に検証する。不正値のまま算術展開/[ -ge ] に渡すと、bash 3.2 では
# "08" が 8進数エラーになったり、文字列が黙って偽と評価されて上限が効かなくなる。
for _v in EVAL_TIMEOUT MAX_LIMIT_WAITS LIMIT_FALLBACK_WAIT LIMIT_BUFFER MAX_COST_USD MAX_RUNTIME_MIN; do
  eval "_x=\$$_v"
  case "$_x" in
    ''|*[!0-9]*) echo "$_v は 0 以上の整数で指定: $_x"; exit 2;;
  esac
  # 桁数を制限してから算術展開に渡す。bash 3.2 では 64bit を超える数字列が
  # $((10#...)) で黙って別の値に化ける(例: 18446744073709551617 -> 1)ため、
  # 巨大な上限を指定したつもりが 1 分/1 ドルで動く事故になる。
  [ "${#_x}" -le 9 ] || { echo "$_v の桁数が多すぎる(9 桁まで): $_x"; exit 2; }
  eval "$_v=\$((10#\$_x))"   # "08" のような 0 埋めを 10 進に正規化
done
[ "$MAX_RUNTIME_MIN" -ge 1 ] || { echo "OVERNIGHT_MAX_RUNTIME_MIN は 1 以上で指定: $MAX_RUNTIME_MIN"; exit 2; }
[ "$MAX_COST_USD" -ge 1 ] || { echo "OVERNIGHT_MAX_COST_USD は 1 以上で指定: $MAX_COST_USD"; exit 2; }
case "$RESUME_AFTER_LIMIT" in
  0|1) ;;
  *) echo "OVERNIGHT_RESUME_AFTER_LIMIT は 0 か 1 で指定: $RESUME_AFTER_LIMIT"; exit 2;;
esac
LIMIT_RETRY_NOTE=""
LIMIT_WAIT_START_EVAL=1   # 待機中に評価ジョブを起こしてよいか(締めセッションの待機では 0)
LOGDIR="state/overnight_logs"
mkdir -p "$LOGDIR" state/eval_queue
# 実行ごとに一意(同じ日に2回起動しても前回のログを上書きしない)
RUN_ID=$(date +%Y%m%d_%H%M)
EVAL_LOG="$LOGDIR/${RUN_ID}_eval.log"
# record_usage.py が上限のリセット時刻を書く受け渡し先。実行ごとに分ける
# (同じリポジトリで2本走っても混ざらない。LOGDIR は gitignore 済み)
LIMIT_RESET_FILE="$LOGDIR/${RUN_ID}_limit_reset"
export KAGG_LIMIT_RESET_FILE="$LIMIT_RESET_FILE"
FAILS=0
LIMIT_HIT=0

# 稼働上限を絶対エポックで確定(起動から MAX_RUNTIME_MIN 分)。
# ops/token_log.jsonl から「この実行ぶんのコスト」だけを拾うための起点も同時に固定する。
START_EPOCH=$(date +%s)
DEADLINE_EPOCH=$((START_EPOCH + MAX_RUNTIME_MIN * 60))
RUN_START_UTC=$(date -u +%Y-%m-%dT%H:%M:%S)
COST_SO_FAR="0.00"

run_precheck || { echo "[overnight] 前提チェック失敗。中止します(寝る前に修正を)"; exit 1; }

echo "[overnight] start $(date '+%F %T')  max_cycles=$MAX_CYCLES${OVERNIGHT_MAX_CYCLES:+ (env上書き)}  稼働上限=${MAX_RUNTIME_MIN}分(→ $(date -r "$DEADLINE_EPOCH" '+%F %T'))  コスト上限=\$${MAX_COST_USD}${CAP_NOTE}"

# スリープ抑止(スクリプト終了で自動解除)
caffeinate -i -w $$ &

# 評価は「プロセスグループごと」殺す。eval_queue.py の子(evaluate.py)と、その
# ProcessPoolExecutor のワーカーまで確実に落とすため(codex レビュー指摘4)。
# そのために job control を有効にして、バックグラウンドジョブに独自の PGID を持たせる。
set -m

kill_eval() {
  [ -z "${EVAL_PID:-}" ] && return 0
  kill -0 "$EVAL_PID" 2>/dev/null || return 0
  echo "[overnight] 評価を停止します ($(basename "${EVAL_JOB:-?}"))"
  # -PGID でグループ全体に送る。グループが取れない環境では PID 単体にフォールバック。
  kill -TERM -"$EVAL_PID" 2>/dev/null || kill -TERM "$EVAL_PID" 2>/dev/null
  local i=0
  while kill -0 "$EVAL_PID" 2>/dev/null && [ "$i" -lt 10 ]; do sleep 1; i=$((i + 1)); done
  if kill -0 "$EVAL_PID" 2>/dev/null; then
    kill -KILL -"$EVAL_PID" 2>/dev/null || kill -KILL "$EVAL_PID" 2>/dev/null
  fi
  wait "$EVAL_PID" 2>/dev/null
  EVAL_PID=""; EVAL_JOB=""
}

# Ctrl-C や異常終了でも、走らせている評価の子プロセスを残さない
cleanup() { kill_eval; }
trap cleanup EXIT
# INT/TERM は片付けてから**確実に終了する**(cleanup 後に本編が続かないように)
trap 'cleanup; exit 130' INT
trap 'cleanup; exit 143' TERM

# 稼働上限は「新しいサイクルを始めない / 待機を打ち切る」ゲートであって、**実行中の
# claude -p や評価を強制終了するものではない**(旧 END_HOUR も同じ挙動だった)。
# したがって最後の 1 サイクルは上限を跨いで走りきる。止めたいときは Ctrl-C。
past_end() {
  [ "$(date +%s)" -ge "$DEADLINE_EPOCH" ]
}

# この実行が積んだ cost_usd の合計(USD)。record_usage.py が ops/token_log.jsonl へ
# 追記した行のうち **run_id がこの実行のもの** だけを足す(時刻だけで絞ると、同じ夜に
# 2 本走ったときに他方のコストを拾って早すぎる停止になる)。
# 集計自体に失敗したら "ERR" を返す。呼び出し側は fail-closed で止める(安全弁の入力が
# 取れないのに「予算未使用」と見なすと、上限が黙って無効になるため)。
# 個別行の JSON が壊れている場合(書き込み中のクラッシュ等)はその行だけ飛ばし、
# 飛ばした本数を stderr に出す。合計は**過小**になりうる。record_usage.py が失敗した回も同様。
cost_so_far() {
  python3 - "$RUN_ID" <<'PY' || echo "ERR"
import json, pathlib, sys
run_id = sys.argv[1]
total, skipped = 0.0, 0
path = pathlib.Path("ops/token_log.jsonl")
if path.exists():
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("run_id") != run_id:
                continue
            total += float(row.get("cost_usd") or 0)
        except Exception:
            skipped += 1
if skipped:
    print("[overnight] 警告: token_log.jsonl の %d 行を読めず合計から除外した" % skipped,
          file=sys.stderr)
print("%.2f" % total)
PY
}

# 戻り値 0 = 予算を使い切った / 集計できなかった(どちらも新しいサイクルを始めない)
over_cost_budget() {
  COST_SO_FAR=$(cost_so_far)
  case "$COST_SO_FAR" in
    ''|ERR|*[!0-9.]*)
      echo "[overnight] 警告: 夜間コストを集計できませんでした($COST_SO_FAR)。安全側に倒して停止します"
      COST_SO_FAR="?"
      return 0;;
  esac
  awk -v c="$COST_SO_FAR" -v m="$MAX_COST_USD" 'BEGIN{exit !(c + 0 >= m + 0)}'
}

# ---- 評価スロット(同時に1本だけ) --------------------------------------------
EVAL_PID=""
EVAL_JOB=""
EVAL_START_RUN=0     # 評価を起動した時点の LLM 起動通番
EVAL_START_EPOCH=0
LLM_RUNS=0           # claude -p を起動した回数。**上限でやり直した分も数える**
                     # (サイクル番号で数えると、やり直しが並走判定をすり抜ける)

reap_eval() {   # 終わっていたらスロットを空ける
  if [ -n "$EVAL_PID" ] && ! kill -0 "$EVAL_PID" 2>/dev/null; then
    local ec name
    wait "$EVAL_PID" 2>/dev/null; ec=$?
    name=$(basename "$EVAL_JOB")
    echo "[overnight] 評価ジョブ完了: $name (exit=$ec)"
    EVAL_PID=""; EVAL_JOB=""
  fi
}

start_eval_if_pending() {   # キューに pending があり、スロットが空いていれば起動
  # 注意: 起動したジョブを直後に kill すると、キューの status が running のまま残り
  # (eval_queue.py は正常終了時にしか done/failed を書かない)二度と拾われない。
  # 「すぐ殺すかもしれない場面」では呼ばないこと。
  [ -n "$EVAL_PID" ] && return 0
  local job
  job=$($PYBIN ops/eval_queue.py next 2>/dev/null)
  [ -z "$job" ] && return 0
  echo "[overnight] 評価ジョブ開始: $(basename "$job") -> $EVAL_LOG"
  $PYBIN ops/eval_queue.py run "$job" >> "$EVAL_LOG" 2>&1 &
  EVAL_PID=$!; EVAL_JOB="$job"; EVAL_START_RUN=$LLM_RUNS
  EVAL_START_EPOCH=$(date +%s)   # 上限は「評価の開始」から測る(並走サイクルの時間も含める)
}

wait_eval() {   # 完了 or タイムアウト or 稼働上限まで待つ(LLM は使わない)
  [ -z "$EVAL_PID" ] && return 0
  echo "[overnight] 評価の完了を待機中: $(basename "$EVAL_JOB")"
  while kill -0 "$EVAL_PID" 2>/dev/null; do
    # 上限は「評価の開始」からの経過で測る(並走した LLM サイクルの時間も含める)
    if [ $(( $(date +%s) - EVAL_START_EPOCH )) -ge "$EVAL_TIMEOUT" ]; then
      echo "[overnight] 評価が開始から $EVAL_TIMEOUT 秒を超えたので中止する(無限待ち防止)"
      kill_eval
      return 0
    fi
    if past_end; then
      echo "[overnight] 稼働上限。評価を中止する"
      kill_eval
      return 0
    fi
    sleep 15
  done
  reap_eval
  EVAL_PID=""; EVAL_JOB=""
}

# ---- セッション上限のリセット待ち(§6-C) --------------------------------------
# 戻り値 0 = リセット済みなので再開してよい / 1 = 待てないので締めに進む
wait_for_limit_reset() {
  local now target human=""
  now=$(date +%s)
  target=""
  if [ -f "$LIMIT_RESET_FILE" ]; then
    target=$(sed -n 1p "$LIMIT_RESET_FILE" 2>/dev/null | tr -d '[:space:]')
    human=$(sed -n 2p "$LIMIT_RESET_FILE" 2>/dev/null)
  fi
  case "$target" in ''|*[!0-9]*|0) target="";; esac
  if [ -z "$target" ]; then
    target=$((now + LIMIT_FALLBACK_WAIT))
    echo "[overnight] リセット時刻を読み取れませんでした。$LIMIT_FALLBACK_WAIT 秒待ちます"
  else
    target=$((target + LIMIT_BUFFER))
    # 上限メッセージの時刻が既に過ぎている/おかしい場合も、最低限の間隔は空ける
    [ "$target" -le "$now" ] && target=$((now + LIMIT_BUFFER))
    echo "[overnight] 上限メッセージのリセット: ${human:-?}"
  fi
  echo "[overnight] $(date -r "$target" '+%F %T') まで待って再開します(稼働上限 $(date -r "$DEADLINE_EPOCH" '+%F %T'))"
  if [ "$target" -ge "$DEADLINE_EPOCH" ]; then
    echo "[overnight] リセットが稼働上限より後なので待たずに締めに進みます"
    return 1
  fi
  while [ "$(date +%s)" -lt "$target" ]; do
    # 待っている間も評価スロットは回す(上限はモデルの話で、評価は動く)。
    # ただし締めセッションの待機では新規に起こさない(直後にスクリプトが終わって殺すだけなので)
    reap_eval
    # 待ち時間も評価の経過に含める(wait_eval と同じ上限を効かせる。無限待ち防止)
    if [ -n "$EVAL_PID" ] && [ $(( $(date +%s) - EVAL_START_EPOCH )) -ge "$EVAL_TIMEOUT" ]; then
      echo "[overnight] 評価が開始から $EVAL_TIMEOUT 秒を超えたので中止する(上限待機中)"
      kill_eval
    fi
    [ "$LIMIT_WAIT_START_EVAL" = "1" ] && start_eval_if_pending
    past_end && { echo "[overnight] 待機中に稼働上限を過ぎたので停止"; return 1; }
    sleep 60
  done
  # sleep 60 で稼働上限を跨いで起きることがある(締めセッションの再試行は外側で
  # past_end を見ないので、ここで止めないと稼働上限後に走ってしまう)
  past_end && { echo "[overnight] 待機中に稼働上限を過ぎたので停止"; return 1; }
  return 0
}

# ---- §6-D 回収はランチャー(純Python)が先に済ませる ---------------------------
COLLECT_LOG="$LOGDIR/${RUN_ID}_collect.log"
if [ "${OVERNIGHT_SKIP_COLLECT:-0}" = "1" ]; then
  echo "[overnight] OVERNIGHT_SKIP_COLLECT=1 のため回収をスキップ(夜の途中で再起動した時用)"
  COLLECT_LOG="(スキップ)"
else
echo "[overnight] 回収スクリプトを実行 -> $COLLECT_LOG"
# 各スクリプトは独立に走らせ(1 つ失敗しても残りは続ける)、失敗を collect_rc に集約して最後に 1 回だけ警告する
# (以前はブロック末尾のコマンドの終了状態しか見ておらず、途中の失敗が黙って通っていた。2026-09-07 codex P1)。
collect_rc=0
{
  echo "=== collect_feedback ==="; $PYBIN ops/collect_feedback.py || { collect_rc=1; echo "NG: collect_feedback rc=$?"; }
  echo "=== fetch_top_replays ==="; $PYBIN ops/fetch_top_replays.py || { collect_rc=1; echo "NG: fetch_top_replays rc=$?"; }
  echo "=== lb_calibration ==="; $PYBIN ops/lb_calibration.py || { collect_rc=1; echo "NG: lb_calibration rc=$?"; }
  echo "=== fetch_discussions (差分) ==="; $PYBIN ops/fetch_discussions.py sync || { collect_rc=1; echo "NG: fetch_discussions rc=$?"; }
  # 上位メタ(../shared/top_meta、22:00 更新)と王者の骨格・市場ギャップ。純 Python、~30 秒。
  # shared には書かない。出力は state/top_meta/gap_LATEST.md(.json)。失敗すると前夜の gap_LATEST が残る
  # (daily_report.py は JSON の date が 1 日以上古ければ「前夜データ」と警告する)。
  echo "=== top_meta_gap ==="; $PYBIN ops/top_meta_gap.py || { collect_rc=1; echo "NG: top_meta_gap rc=$?(前夜の gap_LATEST が残る)"; }
} >> "$COLLECT_LOG" 2>&1
[ "$collect_rc" -ne 0 ] && echo "[overnight] 回収の一部が失敗(ログ: $COLLECT_LOG の NG: 行)。サイクル1が読んで判断する"
fi

# サイクルは while で回す。**セッション上限で潰れたサイクルは消費しない**(§6-C)ため、
# カウンタを自分で進める必要がある。CYCLE_NO は「今やっているサイクル番号」。
CYCLE_NO=0
CYCLE_ATTEMPT=0        # 同じサイクル番号を上限で何度やり直したか(ログ名の識別に使う)
while [ "$CYCLE_NO" -lt "$MAX_CYCLES" ] || [ "$CYCLE_ATTEMPT" -gt 0 ]; do
  [ "$CYCLE_ATTEMPT" -eq 0 ] && CYCLE_NO=$((CYCLE_NO + 1))
  if past_end; then echo "[overnight] 稼働上限(${MAX_RUNTIME_MIN}分)を過ぎたので停止"; break; fi
  # 夜間コスト上限。締めセッションはこの先で必ず走るので、ここではサイクルだけ止める。
  if over_cost_budget; then
    echo "[overnight] 夜間コスト \$${COST_SO_FAR} が上限 \$${MAX_COST_USD} に達したので停止(締めは走る)"
    break
  fi

  # §6-B: 評価の直後の1サイクルは並走させ、その次のサイクルの前には完了を待つ
  reap_eval
  if [ -n "$EVAL_PID" ] && [ $((LLM_RUNS + 1 - EVAL_START_RUN)) -ge 2 ]; then
    wait_eval
    # 待っている間に稼働上限を過ぎている場合があるので、次サイクルを始める前に再確認する
    if past_end; then echo "[overnight] 待機中に稼働上限を過ぎたので停止"; break; fi
  fi

  # やり直しのログは別名にする(上限で落ちた回の記録を残すため)
  if [ "$CYCLE_ATTEMPT" -gt 0 ]; then
    LOG="$LOGDIR/${RUN_ID}_cycle${CYCLE_NO}_r${CYCLE_ATTEMPT}.log"
    ATTEMPT_NOTE=" (上限後のやり直し $CYCLE_ATTEMPT 回目)"
  else
    LOG="$LOGDIR/${RUN_ID}_cycle${CYCLE_NO}.log"
    ATTEMPT_NOTE=""
  fi

  # モデル割当: サイクル1=fable(夜全体の計画・分析), 以降=opus(実装・実行)。
  # 環境変数 OVERNIGHT_MODEL_FIRST / OVERNIGHT_MODEL_REST で上書き可。
  if [ "$CYCLE_NO" -eq 1 ]; then
    MODEL="${OVERNIGHT_MODEL_FIRST:-fable}"
  else
    MODEL="${OVERNIGHT_MODEL_REST:-opus}"
  fi
  echo "[overnight] cycle $CYCLE_NO/$MAX_CYCLES$ATTEMPT_NOTE start $(date '+%T') model=$MODEL -> $LOG"

  if [ -n "$EVAL_PID" ]; then
    EVAL_STATE="評価ジョブ $(basename "$EVAL_JOB") が**実行中**。結果に依存しない作業(実装・分析・記録)だけ進めること。"
  else
    EVAL_STATE="実行中の評価ジョブは無い。"
  fi
  COLLECT_NOTE="回収(collect_feedback / fetch_top_replays / lb_calibration / fetch_discussions sync / top_meta_gap)はランチャーが実行済み。出力は ${COLLECT_LOG}。再実行はしないこと。上位メタとの差は state/top_meta/gap_LATEST.md(上位側の元表は ../shared/top_meta/LATEST.md)。Discussion は \`ops/fetch_discussions.py search '<語>'\` で引ける(コーパス knowledge/discussions/)。"

  PROMPT="$(cat ops/NIGHTLY.md)

CYCLE=${CYCLE_NO} / MAX_CYCLES=${MAX_CYCLES} (日次レポートはループ終了後の締めセッションが書くので、このサイクルでは書かない)
${COLLECT_NOTE}
${EVAL_STATE}${LIMIT_RETRY_NOTE}
今夜の [auto] 提出上限(UTC日あたり): ${EFFECTIVE_CAP}${CAP_NOTE:+ ※policy 既定 ${POLICY_CAP} をランチャーが今夜だけ上書きしている}。Kaggle の実制限 ${KAGGLE_LIMIT} 本/日(個人の手動提出込み)は変わらない。
評価キューの状態:
$($PYBIN ops/eval_queue.py status 2>/dev/null)"
  LIMIT_RETRY_NOTE=""   # 注意書きは1回使ったら消す

  # 出力は JSON(usage/cost 付き)で受け、record_usage.py が要約テキストを $LOG に、
  # トークン/コストを ops/token_log.jsonl に記録する。生 JSON は $LOG.json に残す。
  RAW="$LOG.json"
  rm -f "$LIMIT_RESET_FILE"   # 前回のリセット時刻を読まないよう毎回消す
  LLM_RUNS=$((LLM_RUNS + 1))
  KAGG_NIGHTLY=1 claude -p "$PROMPT" \
    --model "$MODEL" \
    --effort "${OVERNIGHT_EFFORT:-high}" \
    --output-format json \
    --permission-mode bypassPermissions \
    --add-dir "$(pwd)" \
    > "$RAW" 2>"$LOG.stderr"
  rc=$?
  $PYBIN ops/record_usage.py "$RAW" "$CYCLE_NO" "$MODEL" "$rc" "$LOG"
  urc=$?
  if [ "$urc" -eq 4 ]; then
    # §6-C セッション上限。上限中にサイクルを回しても全部無駄に失敗するので、
    # リセット時刻まで待ってから**同じサイクルをやり直す**(2026-09-07 改訂)。
    echo "[overnight] セッション上限を検出 (state/ops_alerts.jsonl)"
    # ここでは pending を起動しない。待たずに締めへ進む場合、起動した直後に kill_eval で
    # 殺すことになり、キューに status=running のジョブが残って二度と拾われなくなる。
    # 実際に待つと決まったら wait_for_limit_reset の中で起動する。
    reap_eval
    if [ "$RESUME_AFTER_LIMIT" != "1" ]; then
      echo "[overnight] OVERNIGHT_RESUME_AFTER_LIMIT=0 のため締めに進みます"
    elif [ "$LIMIT_WAITS" -ge "$MAX_LIMIT_WAITS" ]; then
      echo "[overnight] 上限待機が既に $LIMIT_WAITS 回。これ以上待たずに締めに進みます"
    else
      LIMIT_WAITS=$((LIMIT_WAITS + 1))
      if wait_for_limit_reset; then
        CYCLE_ATTEMPT=$((CYCLE_ATTEMPT + 1))
        FAILS=0   # 上限は「エージェントの失敗」ではないので連続失敗に数えない
        LIMIT_RETRY_NOTE="
【再開】直前の cycle ${CYCLE_NO} はセッション上限で中断した(${LIMIT_WAITS}回目)。作業途中の未コミット変更が残っている可能性がある。まず \`git status\` と \`git diff\` を見て、中途半端な変更を仕上げるか捨てるかを決めてから今夜の作業に入ること。"
        echo "[overnight] リセット済み。cycle $CYCLE_NO をやり直します(やり直し $CYCLE_ATTEMPT 回目 / 待機 $LIMIT_WAITS/$MAX_LIMIT_WAITS)"
        continue
      fi
    fi
    LIMIT_HIT=1
    break
  elif [ "$urc" -eq 3 ]; then
    # セッション自体がエラー終了(認証切れ等) → 連続失敗カウントに乗せる
    echo "[overnight] cycle $CYCLE_NO はエラー終了(is_error)。$LOG.stderr / $RAW を確認"
    [ "$rc" -eq 0 ] && rc=1
  elif [ "$urc" -ne 0 ]; then
    echo "[overnight] record_usage 失敗。生出力: $RAW"; cp "$RAW" "$LOG"
  fi
  CYCLE_ATTEMPT=0   # このサイクルは(成否はともかく)完走した。次はサイクル番号を進める
  echo "[overnight] cycle $CYCLE_NO exit=$rc $(date '+%T')"

  # §6-A サイクルが積んだ評価ジョブをランチャーが引き受ける
  reap_eval
  start_eval_if_pending

  if [ "$rc" -ne 0 ]; then
    FAILS=$((FAILS + 1))
    # 暴走停止: 連続2回失敗したら人間に委ねて停止(§7)
    if [ "$FAILS" -ge 2 ]; then
      echo "[overnight] 連続 $FAILS 回失敗。停止します。ログ: $LOGDIR/" | tee -a "$LOG"
      break
    fi
    sleep 60
  else
    FAILS=0
  fi
done

# 走っている評価の後始末。上限検出時は待たずに止める(待つと最大 EVAL_TIMEOUT 秒無駄になる)。
if [ "$LIMIT_HIT" -eq 1 ]; then
  kill_eval
else
  wait_eval
fi

# 締めセッション: ループがどう終わっても(サイクル数到達・稼働上限・コスト上限・連続失敗・セッション上限)必ず1回、
# 日次レポート+所感を書かせる。実験サイクルと切り離すことで「最終サイクルに届かず所感が空」を防ぐ。
# 締めセッション自体が失敗(上限到達など)したら骨格だけ残す。
TODAY_UTC=$(date -u +%F)
WLOG="$LOGDIR/${RUN_ID}_wrapup.log"
WMODEL="${OVERNIGHT_MODEL_WRAPUP:-opus}"
if [ "$LIMIT_HIT" -eq 1 ]; then
  echo "[overnight] 上限が明けないまま終わったので締めセッションは骨格レポートのみにします"
  $PYBIN ops/daily_report.py || echo "[overnight] daily_report 生成失敗"
  git add state/reports 2>/dev/null && git commit -q -m "report: ${TODAY_UTC} (skeleton, session limit)" 2>/dev/null
else
  # 締めセッションが上限に当たった場合も、待てるならリセット後にやり直す(§6-C)。
  # 稼働上限を過ぎている/待機回数を使い切っているときは待たずに骨格レポートに落とす。
  LIMIT_WAIT_START_EVAL=0
  while :; do
    echo "[overnight] wrap-up start $(date '+%T') model=$WMODEL -> $WLOG"
    rm -f "$LIMIT_RESET_FILE"
    LLM_RUNS=$((LLM_RUNS + 1))
    KAGG_NIGHTLY=1 claude -p "$(cat ops/WRAPUP.md)

今回の実行のサイクルログ: ${LOGDIR}/${RUN_ID}_cycle*.log (RUN_ID=${RUN_ID})
今夜の [auto] 提出上限: ${EFFECTIVE_CAP}${CAP_NOTE:+ (policy 既定 ${POLICY_CAP} をランチャーが今夜だけ上書きした)}
評価ジョブのログ: ${EVAL_LOG} ／ 回収ログ: ${COLLECT_LOG}" \
      --model "$WMODEL" \
      --effort "${OVERNIGHT_EFFORT:-high}" \
      --output-format json \
      --permission-mode bypassPermissions \
      --add-dir "$(pwd)" \
      > "$WLOG.json" 2>"$WLOG.stderr"
    wrc=$?
    $PYBIN ops/record_usage.py "$WLOG.json" 0 "$WMODEL" "$wrc" "$WLOG"
    wurc=$?
    if [ "$wurc" -eq 4 ] && [ "$RESUME_AFTER_LIMIT" = "1" ] && [ "$LIMIT_WAITS" -lt "$MAX_LIMIT_WAITS" ]; then
      LIMIT_WAITS=$((LIMIT_WAITS + 1))
      echo "[overnight] 締めセッションがセッション上限に当たりました"
      WLOG="$LOGDIR/${RUN_ID}_wrapup_r${LIMIT_WAITS}.log"
      if wait_for_limit_reset; then continue; fi
    fi
    [ "$wurc" -ne 0 ] && wrc=1
    break
  done
  if [ "$wrc" -ne 0 ] || [ ! -f "state/reports/${TODAY_UTC}.md" ]; then
    if [ "$wrc" -ne 0 ]; then
      echo "[overnight] 締めセッション失敗(rc=$wrc)。骨格レポートを残します"
    else
      echo "[overnight] 締めセッションは正常終了したが state/reports/${TODAY_UTC}.md が無い。骨格レポートを残します"
    fi
    $PYBIN ops/daily_report.py || echo "[overnight] daily_report 生成失敗"
    git add state/reports 2>/dev/null && git commit -q -m "report: ${TODAY_UTC} (skeleton, wrap-up failed)" 2>/dev/null
  fi
fi

# 最終サイクル/締めセッション自身の usage 行は、締めのコミット後に書かれるため
# 毎朝 token_log.jsonl だけが未コミットで残る。ここで拾ってコミットする。
if ! git diff --quiet -- ops/token_log.jsonl 2>/dev/null; then
  git add ops/token_log.jsonl && git commit -q -m "ops: token_log ${RUN_ID}" 2>/dev/null \
    && echo "[overnight] token_log をコミットしました"
fi

echo "[overnight] done $(date '+%F %T')"
