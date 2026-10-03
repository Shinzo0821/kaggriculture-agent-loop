#!/usr/bin/env python
"""LB 上位チームが戦った試合(上位同士を優先)のリプレイを replays/top/ に回収する。

usage:
  .venv/bin/python ops/fetch_top_replays.py [--top 20] [--per-team 2] [--max 10] [--days 3] [--dry-run]
                                            [--timeout 300] [--replay-timeout 900] [--deadline-min 90]

時間切れの扱い:
  kaggle CLI の 1 回ごと(--timeout / --replay-timeout)と全体(--deadline-min)に上限がある。
  時間切れは例外にせず、取れた分で index を書いて終了する(LB 取得だけは失敗で exit)。
  呼び出し側(shared/top_meta/scripts/run_daily.sh)は非0終了なら既存リプレイで集計を続ける。

データ源(2段構え):
  1. 公式デイリーデータセット kaggle/kaggriculture-episodes-YYYY-MM-DD の manifest.csv
     (列: episode_id, create_time, avg_score, min_score, sum_score, agent_count, size_bytes)。
     → チーム情報は含まれないので、ここで得た episode_id を 2. で名寄せする。
     デイリーデータセットの一覧は kaggle/kaggriculture-episodes-index (manifest.csv:
     date, daily_dataset_slug, episode_count, top_avg_score, ...)。
  2. Kaggle の公開 episode API (認証不要)
       POST https://www.kaggle.com/api/i/competitions.EpisodeService/ListEpisodes
       {"ids":[episode_id,...]} または {"submissionId": N}
     → episodes[].agents[] に teamId/submissionId/reward(最終資金)/updatedScore(ladder)、
       teams[] に teamName と publicLeaderboardSubmissionId が入る。
     上位チームの publicLeaderboardSubmissionId が分かれば submissionId 指定で
     当日分(データセット未公開)のエピソードも取れる。

出力:
  replays/top/episode-<ID>-replay.json  (kaggle competitions replay でDL)
  replays/top/index.jsonl               (両者の名前・LB順位/スコア・最終資金・ladder)
  ops/top_episodes_seen.json            (取得済み episode_id)
  stdout                                (上位同士 / 上位 vs 中位 の候補一覧)
"""
import argparse
import csv
import datetime as dt
import io
import json
import os
import signal
import subprocess
import sys
import time
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KAGGLE = ["uvx", "--from", "kaggle==2.2.4", "kaggle"]
COMP = "kaggriculture"
DS_OWNER = "kaggle"
API_URL = "https://www.kaggle.com/api/i/competitions.EpisodeService/ListEpisodes"
DEFAULT_DS_DIR = os.environ.get(
    "KAGG_EPISODES_DS",
    str(Path(tempfile.gettempdir()) / "kaggriculture-agent-loop" / "episodes_ds"),
)
OUT_DIR = ROOT / "replays" / "top"
SEEN_PATH = ROOT / "ops" / "top_episodes_seen.json"
INDEX_PATH = OUT_DIR / "index.jsonl"
API_BATCH = 100
API_SLEEP = 1.0  # 公開APIへの礼儀
API_RETRY_WAITS = (5, 15, 30)  # 429/5xx/接続タイムアウト時のバックオフ(秒)
API_TIMEOUT = 60  # 公開 API 1 リクエストの上限(秒)
KAGGLE_TIMEOUT = 300  # kaggle CLI 1 回の上限(秒)。LB/manifest など軽い呼び出し向け
REPLAY_TIMEOUT = 900  # replay は 1 件 32MB あるので長めに取る
DEADLINE_MIN = 90  # スクリプト全体の上限(分)
RC_TIMEOUT = 124  # timeout(1) にならい、時間切れは 124 を返す


_ACTIVE = []  # 実行中の子(外側から TERM されたときに道連れにする)


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill_group(proc):
    """プロセスグループごと止める(孫が残るとパイプが閉じない)。

    直下の子が死んでも TERM を無視する孫が同じグループに残ることがあるので、
    子を回収したうえでグループの生存を見て SIGKILL まで上げる。
    """
    pgid = proc.pid
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.wait(timeout=5)  # 子を回収してからでないとゾンビが生存判定に混ざる
        except subprocess.TimeoutExpired:
            continue  # まだ死なない → SIGKILL へ
        if not _group_alive(pgid):
            return


def _on_terminate(signum, _frame):
    """外側の番人に殺されるとき、走らせている kaggle CLI を道連れにする。"""
    for proc in list(_ACTIVE):
        _kill_group(proc)
    sys.exit(128 + signum)


def remaining(deadline):
    return None if deadline is None else max(0.0, deadline - time.monotonic())


def timeout_for(base, deadline):
    """残り時間を超えない上限を返す(全体の締切を個別呼び出しが食い破らないように)。"""
    left = remaining(deadline)
    return base if left is None else max(30, min(base, int(left)))


def run_kaggle(args, timeout=KAGGLE_TIMEOUT):
    """kaggle CLI を実行する。時間切れは例外にせず returncode=124 で返す。

    subprocess.run(timeout=) との違いは 2 つ:
      - 時間切れで TimeoutExpired を投げないので、replay 1 件が遅くても残りを続けられる
        (run() のままだと 1 件の時間切れで回収全体が落ちる)。
      - kill するのがプロセスグループ全体。run() は直下の子(uvx)しか止めないため、
        uvx が起こした uv/python の孫が居残って DL を続ける。start_new_session で
        グループを分けておき、killpg でまとめて止める。
    """
    proc = subprocess.Popen(
        KAGGLE + args, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True)
    _ACTIVE.append(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        try:
            out, err = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:  # 孫がパイプを握ったまま: 諦めて先へ進む
            out, err = "", ""
        msg = f"timeout: {timeout}s を超えたので停止した ({' '.join(args[:3])})"
        return subprocess.CompletedProcess(proc.args, RC_TIMEOUT, out or "",
                                           ((err or "") + "\n" + msg).strip())
    finally:
        if proc in _ACTIVE:
            _ACTIVE.remove(proc)


def expired(deadline):
    return deadline is not None and time.monotonic() > deadline


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- leaderboard
def fetch_leaderboard(ds_dir, timeout=KAGGLE_TIMEOUT):
    """LB の CSV を落として [{rank, team_id, team_name, score}] を返す。"""
    lb_dir = Path(ds_dir) / "lb"
    lb_dir.mkdir(parents=True, exist_ok=True)
    for f in list(lb_dir.glob("*.zip")) + list(lb_dir.glob("*.csv")):  # 自分が作った LB ファイルだけ消す
        f.unlink()
    out = run_kaggle(["competitions", "leaderboard", COMP, "-d", "-p", str(lb_dir)], timeout=timeout)
    if out.returncode != 0:
        sys.exit(f"leaderboard 取得失敗(rc={out.returncode}): {out.stderr.strip()[:300]}")
    zips = list(lb_dir.glob("*.zip"))
    if not zips:
        sys.exit(f"leaderboard zip が見つからない: {lb_dir}")
    with zipfile.ZipFile(zips[0]) as z:
        name = next(n for n in z.namelist() if n.endswith(".csv"))
        text = z.read(name).decode("utf-8-sig")
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        try:
            rows.append({"rank": int(r["Rank"]), "team_id": int(r["TeamId"]),
                         "team_name": r["TeamName"], "score": float(r["Score"])})
        except (KeyError, ValueError):
            continue
    rows.sort(key=lambda x: x["rank"])
    return rows


# ---------------------------------------------------------------- dataset manifests
def fetch_daily_manifests(ds_dir, days, timeout=KAGGLE_TIMEOUT, deadline=None):
    """直近 days 日分(昨日まで)のデイリーデータセットの manifest.csv を落として行を返す。"""
    today = dt.datetime.now(dt.timezone.utc).date()
    rows = []
    for back in range(1, days + 1):
        if expired(deadline):
            log("  制限時間に達したので manifest 取得を打ち切る")
            break
        date = (today - dt.timedelta(days=back)).isoformat()
        slug = f"{DS_OWNER}/{COMP}-episodes-{date}"
        d = Path(ds_dir) / date
        mf = d / "manifest.csv"
        if not mf.exists():
            d.mkdir(parents=True, exist_ok=True)
            out = run_kaggle(["datasets", "download", "-d", slug, "-f", "manifest.csv",
                              "-p", str(d), "--unzip", "-q"],
                             timeout=timeout_for(timeout, deadline))
            if out.returncode != 0 or not mf.exists():
                # 単ファイルDLは zip で来ることがある
                zips = list(d.glob("*.zip"))
                if zips:
                    with zipfile.ZipFile(zips[0]) as z:
                        z.extractall(d)
                if not mf.exists():
                    log(f"  dataset {slug}: manifest 取得失敗(未公開?) "
                        f"{(out.stderr or out.stdout).strip()[:120]}")
                    continue
        n = 0
        with open(mf, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if str(r.get("episode_id", "")).isdigit():
                    rows.append({"episode_id": int(r["episode_id"]), "date": date,
                                 "avg_score": float(r.get("avg_score") or 0)})
                    n += 1
        log(f"  dataset {slug}: {n} episodes")
    return rows


# ---------------------------------------------------------------- episode API
def list_episodes(body):
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "user-agent": "kaggriculture-agent-loop"})
    for attempt in range(len(API_RETRY_WAITS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=API_TIMEOUT) as resp:
                data = json.load(resp)
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < len(API_RETRY_WAITS):
                time.sleep(API_RETRY_WAITS[attempt])
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:  # 接続断・読み取りタイムアウト
            if attempt < len(API_RETRY_WAITS):
                time.sleep(API_RETRY_WAITS[attempt])
                continue
            raise RuntimeError(f"episode API 応答なし({API_TIMEOUT}s x {attempt + 1} 回): {e}")
    if "error" in data:
        raise RuntimeError(str(data["error"])[:200])
    return data


def merge_response(data, episodes, teams, submissions):
    for ep in data.get("episodes", []):
        if ep.get("state") not in (None, "COMPLETED"):
            continue
        agents = ep.get("agents") or []
        if len(agents) != 2:
            continue
        episodes[int(ep["id"])] = {
            "id": int(ep["id"]), "create_time": ep.get("createTime"),
            "agents": [{"team_id": a.get("teamId"), "submission_id": a.get("submissionId"),
                        "reward": a.get("reward"), "ladder_before": a.get("initialScore"),
                        "ladder_after": a.get("updatedScore")}
                       for a in sorted(agents, key=lambda a: a.get("index", 0))],
        }
    for t in data.get("teams", []):
        teams[int(t["id"])] = {"team_name": t.get("teamName"),
                               "lb_submission_id": t.get("publicLeaderboardSubmissionId")}
    for s in data.get("submissions", []):
        submissions[int(s["id"])] = {"team_id": s.get("teamId"),
                                     "date": s.get("dateSubmitted")}


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=20, help="LB 上位 N チームを対象")
    ap.add_argument("--per-team", type=int, default=2, help="1チームあたりの新規DL上限")
    ap.add_argument("--max", type=int, default=10, help="今回DLする新規リプレイの上限")
    ap.add_argument("--days", type=int, default=3, help="直近 days 日のエピソードを対象")
    ap.add_argument("--ds-dir", default=DEFAULT_DS_DIR, help="データセット/LB の置き場(リポ外)")
    ap.add_argument("--dry-run", action="store_true", help="候補一覧のみ、DLしない")
    ap.add_argument("--no-live", action="store_true",
                    help="submissionId 指定の当日分取得をしない(データセットの範囲のみ)")
    ap.add_argument("--timeout", type=int, default=KAGGLE_TIMEOUT,
                    help=f"kaggle CLI 1 回あたりの上限秒 (既定 {KAGGLE_TIMEOUT})")
    ap.add_argument("--replay-timeout", type=int, default=REPLAY_TIMEOUT,
                    help=f"replay DL 1 件あたりの上限秒 (既定 {REPLAY_TIMEOUT})")
    ap.add_argument("--deadline-min", type=int, default=DEADLINE_MIN,
                    help=f"スクリプト全体の上限分。0 で無効 (既定 {DEADLINE_MIN})")
    args = ap.parse_args()

    for name in ("timeout", "replay_timeout"):
        if getattr(args, name) < 1:
            ap.error(f"--{name.replace('_', '-')} は 1 以上にする")
    if args.deadline_min < 0:
        ap.error("--deadline-min は 0(無効) 以上にする")

    # 外側の番人に殺されるとき、走らせている kaggle CLI を残さない
    signal.signal(signal.SIGTERM, _on_terminate)
    signal.signal(signal.SIGINT, _on_terminate)

    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=args.days)
    deadline = time.monotonic() + args.deadline_min * 60 if args.deadline_min > 0 else None
    Path(args.ds_dir).mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. LB
    lb = fetch_leaderboard(args.ds_dir, timeout=args.timeout)
    top = {r["team_id"]: r for r in lb[:args.top]}
    lb_by_id = {r["team_id"]: r for r in lb}
    log(f"LB: {len(lb)} teams, 上位 {len(top)} を対象 "
        f"(#1 {lb[0]['team_name']} {lb[0]['score']})")

    # 2. デイリーデータセット manifest → episode_id
    log(f"デイリーデータセット manifest (直近 {args.days} 日):")
    manifest_rows = fetch_daily_manifests(args.ds_dir, args.days,
                                          timeout=args.timeout, deadline=deadline)
    manifest_ids = [r["episode_id"] for r in manifest_rows]
    log(f"  manifest 合計 {len(manifest_ids)} episodes")

    # 3. episode API で名寄せ(ids バッチ)
    episodes, teams, submissions = {}, {}, {}
    api_ok = True
    # ladder が高い順に問い合わせると上位チームが早く見つかる
    manifest_rows.sort(key=lambda r: -r["avg_score"])
    ordered_ids = [r["episode_id"] for r in manifest_rows]
    for i in range(0, len(ordered_ids), API_BATCH):
        if expired(deadline):
            log("  制限時間に達したので名寄せを打ち切る(取れた分で続行)")
            break
        batch = ordered_ids[i:i + API_BATCH]
        try:
            merge_response(list_episodes({"ids": batch}), episodes, teams, submissions)
        except Exception as e:
            log(f"  episode API (ids batch {i // API_BATCH}) 失敗: {str(e)[:150]}")
            if not episodes:
                api_ok = False
                break
            continue
        time.sleep(API_SLEEP)
    log(f"episode API: {len(episodes)} episodes / {len(teams)} teams を名寄せ")

    # 4. 上位チームの LB 提出 → submissionId 指定で当日分も取得
    if api_ok and not args.no_live:
        missing = []
        for tid in top:
            if expired(deadline):
                log("  制限時間に達したので当日分の追跡を打ち切る")
                break
            sub = (teams.get(tid) or {}).get("lb_submission_id")
            if not sub:
                missing.append(tid)
                continue
            try:
                merge_response(list_episodes({"submissionId": int(sub)}),
                               episodes, teams, submissions)
            except Exception as e:
                log(f"  episode API (submissionId={sub}) 失敗: {str(e)[:150]}")
            time.sleep(API_SLEEP * 2)  # 1件あたり数百エピソードの重い応答なので間隔を広めに
        if missing:
            log("  LB提出IDが判明せず(データセット内に出現なし): "
                + ", ".join(f"#{top[t]['rank']} {top[t]['team_name']}" for t in missing))
        log(f"submissionId 追跡後: {len(episodes)} episodes")

    if not episodes:
        if expired(deadline):  # 時間切れは「取れた分で終了」なので正常扱い
            log(f"エピソード情報が取れないまま制限時間({args.deadline_min}分)に達した。"
                " 今回は回収なしで終了する。")
            return
        sys.exit("エピソード情報が取れなかった(データセットも API も不可)。"
                 " 代替: kaggle competitions episodes <自分の提出ID> のみで回収する。")

    # 5. 候補選定
    seen = set(json.loads(SEEN_PATH.read_text())) if SEEN_PATH.exists() else set()
    seen |= {p.name.split("-")[1] for p in OUT_DIR.glob("episode-*-replay.json")}

    def parse_ts(s):
        if not s:
            return None
        s = s.rstrip("Z")
        if "." in s:  # ナノ秒を落とす
            head, frac = s.split(".", 1)
            s = f"{head}.{frac[:6]}"
        return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)

    cands = []
    for ep in episodes.values():
        ts = parse_ts(ep["create_time"])
        if ts is None or ts < since:
            continue
        tids = [a["team_id"] for a in ep["agents"]]
        if tids[0] == tids[1]:  # 提出直後の自己対戦(検証エピソード)は除外
            continue
        n_top = sum(1 for t in tids if t in top)
        if n_top == 0:
            continue
        ranks = [lb_by_id[t]["rank"] if t in lb_by_id else 10 ** 6 for t in tids]
        cands.append({"ep": ep, "ts": ts, "n_top": n_top, "rank_sum": sum(ranks)})
    cands.sort(key=lambda c: (-c["n_top"], c["rank_sum"], -c["ts"].timestamp()))

    def team_label(tid):
        r = lb_by_id.get(tid)
        name = (teams.get(tid) or {}).get("team_name") or (r or {}).get("team_name") or str(tid)
        return f"#{r['rank']} {name}({r['score']:.0f})" if r else f"LB外 {name}"

    def describe(c):
        ep = c["ep"]
        a, b = ep["agents"]
        flag = "済" if str(ep["id"]) in seen else "新"
        return (f"  [{flag}] ep {ep['id']} {c['ts'].strftime('%m-%d %H:%M')}Z  "
                f"{team_label(a['team_id'])} ${a['reward']}  vs  "
                f"{team_label(b['team_id'])} ${b['reward']}")

    both = [c for c in cands if c["n_top"] == 2]
    mixed = [c for c in cands if c["n_top"] == 1]
    log(f"\n== 上位同士 (直近 {args.days} 日, {len(both)} 件, 新規 "
        f"{sum(1 for c in both if str(c['ep']['id']) not in seen)}) ==")
    for c in both[:40]:
        log(describe(c))
    log(f"\n== 上位 vs 中位 ({len(mixed)} 件, 上位20件のみ表示) ==")
    for c in mixed[:20]:
        log(describe(c))

    # 6. DL(上位同士を優先、per-team 上限)
    per_team = {t: 0 for t in top}
    picked = []
    for c in cands:
        if len(picked) >= args.max:
            break
        ep = c["ep"]
        if str(ep["id"]) in seen:
            continue
        tids = [a["team_id"] for a in ep["agents"] if a["team_id"] in top]
        if any(per_team[t] >= args.per_team for t in tids):
            continue
        for t in tids:
            per_team[t] += 1
        picked.append(c)

    log(f"\nDL 対象 {len(picked)} 件 (--max {args.max}, --per-team {args.per_team})"
        + (" [dry-run]" if args.dry_run else ""))
    if args.dry_run:
        for c in picked:
            log(describe(c))
        return

    # 一旦 .partial/ に落として、完全に取れたものだけを本来の名前へ移す。
    # 直に OUT_DIR へ書くと、時間切れや外側からの kill で切れたファイルが残り、
    # 次回は seen 扱いで取り直されないうえ、集計側(extract_top.py)の json.load が
    # 落ちて日次レポート全体が作られなくなる。glob("episode-*") は .partial/ を見ない。
    stage = OUT_DIR / ".partial"
    stage.mkdir(exist_ok=True)
    for stale in stage.glob("*"):  # 前回の kill で残った分を掃除
        stale.unlink()

    def looks_complete(p):
        """末尾まで書けているか(切れた JSON を弾く。32MB を毎回全部読まない)。"""
        try:
            if p.stat().st_size < 1024:
                return False
            with open(p, "rb") as f:
                f.seek(-64, os.SEEK_END)
                return f.read().rstrip().endswith(b"}")
        except OSError:
            return False

    downloaded = 0
    timed_out = 0
    with open(INDEX_PATH, "a") as idx:
        for c in picked:
            if expired(deadline):
                log(f"  制限時間({args.deadline_min}分)に達したのでDLを打ち切る"
                    f"({downloaded}/{len(picked)} 件で終了)")
                break
            ep = c["ep"]
            eid = str(ep["id"])
            rp = run_kaggle(["competitions", "replay", eid, "-p", str(stage)],
                            timeout=timeout_for(args.replay_timeout, deadline))
            tmp = stage / f"episode-{eid}-replay.json"
            path = OUT_DIR / f"episode-{eid}-replay.json"
            if rp.returncode != 0 or not tmp.exists() or not looks_complete(tmp):
                if rp.returncode == RC_TIMEOUT:
                    timed_out += 1
                tmp.unlink(missing_ok=True)  # 途中まで書けたファイルを残さない
                log(f"  replay {eid} DL失敗: {(rp.stderr or rp.stdout).strip()[:150]}")
                continue
            os.replace(tmp, path)  # ここで初めて本来の名前になる(同一FS内なので原子的)
            line = describe(c).strip()
            seen.add(eid)
            downloaded += 1
            rec = {
                "ts": now.isoformat(timespec="seconds"), "episode_id": ep["id"],
                "create_time": ep["create_time"], "both_top": c["n_top"] == 2,
                "file": str(path.relative_to(ROOT)),
                "teams": [{
                    "index": i, "team_id": a["team_id"],
                    "team_name": (teams.get(a["team_id"]) or {}).get("team_name")
                    or (lb_by_id.get(a["team_id"]) or {}).get("team_name"),
                    "lb_rank": (lb_by_id.get(a["team_id"]) or {}).get("rank"),
                    "lb_score": (lb_by_id.get(a["team_id"]) or {}).get("score"),
                    "submission_id": a["submission_id"],
                    "final_money": a["reward"],
                    "ladder_after": a["ladder_after"],
                } for i, a in enumerate(ep["agents"])],
            }
            idx.write(json.dumps(rec, ensure_ascii=False) + "\n")
            log(f"  DL {line}")
    SEEN_PATH.write_text(json.dumps(sorted(seen, key=int)))
    log(f"replays/top: 新規 {downloaded} 件DL, index → {INDEX_PATH.relative_to(ROOT)}, "
        f"seen {len(seen)} 件" + (f", timeout {timed_out} 件" if timed_out else ""))


if __name__ == "__main__":
    main()
