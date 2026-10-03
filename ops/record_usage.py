#!/usr/bin/env python
"""夜間サイクルのトークン/コスト記録。

overnight.sh が `claude -p --output-format json` の出力(JSON 1件)を渡す。
- 人間が読む要約テキスト(result)を <log>.log に書き出す(従来のログ互換)
- usage / modelUsage / cost / turns / duration を ops/token_log.jsonl に1行追記
JSON が壊れていても(セッションがクラッシュした場合など)raw 先頭を残して必ず1行追記する。

2026-09-05 追加(計画 §6-C): セッション上限(session limit / usage limit)に当たった場合を
文言で検出し、`state/ops_alerts.jsonl` に記録して **exit 4** を返す。
日次レポートの「運用上の問題」節はこのファイルから自動生成される。

2026-09-07 追加: 上限メッセージ("... resets 6:50pm (Asia/Tokyo)")から**リセット時刻**を
読み取り、`state/session_limit_reset` に「1行目=epoch秒(読めなければ 0) / 2行目=原文」で書く。
overnight.sh はこれを読んでリセットまで待ち、潰れたサイクルをやり直す(消費しない)。
読めなかった場合は overnight.sh 側の既定待ち時間にフォールバックする。

exit code: 0=正常 / 3=セッションがエラー終了 / 4=セッション上限

usage: record_usage.py <raw_json_path> <cycle> <model> <rc> <text_log_path>
"""
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ROOT = Path(__file__).resolve().parent.parent
TOKEN_LOG = ROOT / "ops/token_log.jsonl"
ALERTS = ROOT / "state/ops_alerts.jsonl"
# 上限のリセット時刻の受け渡し先(overnight.sh が読む。実行時の一時ファイル)。
# 同じリポジトリで夜間ループを2本走らせても混ざらないよう、ランチャーは
# KAGG_LIMIT_RESET_FILE で実行ごとのパスを渡す。
RESET_FILE = Path(os.environ.get("KAGG_LIMIT_RESET_FILE") or ROOT / "state/session_limit_reset")
# セッション上限の文言(Claude Code / API のどちらの出方でも拾えるよう小文字で部分一致)
LIMIT_PATTERNS = ("session limit", "usage limit", "rate limit", "5-hour limit",
                  "weekly limit", "limit reached", "上限に達し", "利用上限")


def detect_limit(text):
    t = (text or "").lower()
    return [w for w in LIMIT_PATTERNS if w.lower() in t]


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
# "resets 6:50pm (Asia/Tokyo)" / "resets at 18:50" / "resets Sep 8 at 9am (UTC)"
RESET_RE = re.compile(r"resets?\s+(?:on\s+|at\s+)?(?P<rest>.{0,60})", re.I)
DATE_RE = re.compile(r"\b(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+"
                     r"(?P<day>\d{1,2})\b", re.I)
# 時刻は「:分がある」か「am/pm が付く」ものだけ拾う(日付の数字を時刻と誤読しないため)
TIME_RE = re.compile(r"(?P<h>\d{1,2}):(?P<m>\d{2})\s*(?P<ap>am|pm)?"
                     r"|(?P<h2>\d{1,2})\s*(?P<ap2>am|pm)", re.I)
TZ_RE = re.compile(r"\(([A-Za-z]+(?:/[A-Za-z0-9_+\-]+)+|UTC|GMT)\)")


def parse_reset(text, now=None):
    """上限メッセージからリセット時刻を読む。→ (epoch or None, 読み取った原文 or None)

    タイムゾーンは括弧内の IANA 名(例 "(Asia/Tokyo)")を優先し、無ければローカル。
    日付が無い場合は「次に来るその時刻」とみなす(過ぎていれば翌日)。
    """
    m = RESET_RE.search(text or "")
    if not m:
        return None, None
    rest = m.group("rest").strip()
    tz = None
    mtz = TZ_RE.search(rest)
    if mtz:
        name = mtz.group(1)
        try:
            tz = ZoneInfo("UTC" if name == "GMT" else name)   # "Etc/GMT+9" 等は置換しない
        except (ZoneInfoNotFoundError, ValueError):
            # TZ が明示されているのに解決できないなら、ローカル時刻と読み替えず解析失敗にする
            # (勝手にローカルとみなすと何時間もずれた時刻を待つことになる)
            return None, rest
    base = now or dt.datetime.now(dt.timezone.utc)
    if base.tzinfo is None:
        base = base.astimezone()
    local = base.astimezone(tz) if tz else base.astimezone()

    dm = DATE_RE.search(rest)
    rest_t = (rest[:dm.start()] + rest[dm.end():]) if dm else rest
    tm = TIME_RE.search(rest_t)
    if not tm:
        return None, rest
    if tm.group("h"):
        hour, minute, ap = int(tm.group("h")), int(tm.group("m")), tm.group("ap")
    else:
        hour, minute, ap = int(tm.group("h2")), 0, tm.group("ap2")
    if ap:
        ap = ap.lower()
        if ap == "pm" and hour != 12:
            hour += 12
        elif ap == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None, rest
    try:
        cand = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if dm:
            cand = cand.replace(month=MONTHS[dm.group("mon").lower()[:3]], day=int(dm.group("day")))
            if cand < local:            # 年をまたぐ指定(12月に「Jan 3」等)
                cand = cand.replace(year=cand.year + 1)
        elif cand <= local:             # 日付が無く、その時刻が過ぎていれば翌日
            cand += dt.timedelta(days=1)
    except ValueError:                  # 2/30 のような無効な日付
        return None, rest
    return int(cand.timestamp()), rest


def alert(kind, cycle, model, detail):
    """日次レポートの「運用上の問題」に自動転記される警報を残す。"""
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS.open("a") as f:
        f.write(json.dumps({
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "kind": kind, "cycle": cycle, "model": model, "detail": detail[:300],
        }, ensure_ascii=False) + "\n")


def main():
    raw_path, cycle, model, rc, text_log = sys.argv[1:6]
    raw = Path(raw_path).read_text(errors="replace")
    msg = raw            # 上限メッセージの探索対象(JSON が読めたら result 本文に差し替える)
    rec = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "night": Path(raw_path).name.split("_")[0],  # YYYYMMDD
        # ランチャーの実行 ID(=ログ名の先頭 "YYYYMMDD_HHMM")。overnight.sh の夜間コスト上限が
        # 「この実行ぶんだけ」を合算するのに使う。時刻だけで絞ると同じ夜に 2 本走った時に混ざる。
        "run_id": "_".join(Path(raw_path).name.split("_")[:2]),
        "cycle": int(cycle), "model_requested": model, "rc": int(rc),
    }
    try:
        d = json.loads(raw)
        u = d.get("usage", {})
        rec.update({
            "session_id": d.get("session_id"),
            "is_error": d.get("is_error"), "subtype": d.get("subtype"),
            "duration_min": round(d.get("duration_ms", 0) / 60000, 1),
            "num_turns": d.get("num_turns"),
            "cost_usd": round(d.get("total_cost_usd", 0), 3),
            "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"),
            "cache_read": u.get("cache_read_input_tokens"),
            "cache_create": u.get("cache_creation_input_tokens"),
            # モデル別内訳(サブエージェント/haiku 補助分も含む)
            "model_usage": {m: {k: v for k, v in mu.items()
                                if k in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                                         "cacheCreationInputTokens", "costUSD")}
                            for m, mu in d.get("modelUsage", {}).items()},
        })
        msg = str(d.get("result", "")) or raw
        Path(text_log).write_text(str(d.get("result", "")) + "\n")
    except (json.JSONDecodeError, AttributeError) as e:
        rec.update({"parse_error": str(e)[:100], "raw_head": raw[:300]})
        Path(text_log).write_text(raw)  # そのまま残す
    # セッション上限の検出(計画 §6-C)。
    # **異常終了した時だけ**文言を見る。正常終了したサイクルの要約文に "rate limit" 等が
    # たまたま含まれていても夜を打ち切らないようにするため(誤検知で夜が全滅するのを避ける)。
    abnormal = bool(rec.get("is_error")) or "parse_error" in rec or int(rc) != 0
    hits = detect_limit(raw) if abnormal else []
    reset_epoch = reset_text = None
    if hits:
        rec["session_limit"] = hits
        reset_epoch, reset_text = parse_reset(msg)
        if reset_epoch:
            rec["session_limit_reset"] = dt.datetime.fromtimestamp(
                reset_epoch, dt.timezone.utc).astimezone().isoformat(timespec="seconds")
        # overnight.sh への受け渡し(1行目=epoch or 0 / 2行目=原文)。
        # ここで失敗しても token_log 追記と exit 4 は必ず行う(ランチャーが上限を知れなくなるため)。
        try:
            RESET_FILE.parent.mkdir(parents=True, exist_ok=True)
            RESET_FILE.write_text(
                f"{reset_epoch or 0}\n{(reset_text or msg[:200]).replace(chr(10), ' ')}\n")
        except OSError as e:
            print(f"[usage] ⚠ リセット時刻を {RESET_FILE} に書けませんでした: {e}")

    with TOKEN_LOG.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[usage] cycle={cycle} cost=${rec.get('cost_usd','?')} turns={rec.get('num_turns','?')} "
          f"dur={rec.get('duration_min','?')}min out_tok={rec.get('output_tokens','?')}")

    if hits:
        when = rec.get("session_limit_reset", "不明")
        alert("session_limit", cycle, model, f"検出語 {hits} / rc={rc} / リセット {when}")
        print(f"[usage] ⚠ セッション上限を検出: {hits} / リセット {when} → ランチャーに委ねる(exit 4)")
        sys.exit(4)
    # セッションがエラー終了(レート制限・認証切れ等)なら rc=3 で overnight.sh に伝える
    if rec.get("is_error") or "parse_error" in rec:
        alert("session_error", cycle, model,
              f"is_error={rec.get('is_error')} subtype={rec.get('subtype')} "
              f"parse_error={rec.get('parse_error', '')}")
        sys.exit(3)


if __name__ == "__main__":
    main()
