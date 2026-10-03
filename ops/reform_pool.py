#!/usr/bin/env python
"""相手プールの改編を 1 コマンドで行う（計画 §1-C Phase 2）。

プールを変えると **レーティングの尺度そのものが変わる**ので、
  (1) プール JSON の enabled 変更 → (2) 総当たりでレーティング取り直し → (3) 王者ベースライン取り直し
の 3 つを必ずセットで行う必要がある。1 つでも欠けると evaluate.py の gate が
`baseline_compatible=false` になり、preflight は全ての提出を拒否する（fail-closed）。
このスクリプトは 3 つを順に実行する。**生きた control/sparring_pool.json には最後まで触れず、
改編は作業用コピーに対して行い、全ての完了条件を満たしたときだけ os.replace で原子的に本番へ
差し替える。** こうすると途中で（clean な例外でなく SIGKILL 等で）落ちても本番プールは元の正常
状態のまま残る（2026-09-10 に 2 度、kill で半端な中間状態が本番に残る事故が起きたのを塞いだ）。

usage（1 夜まるごと使う想定。既定の改編内容は計画 §1-C Phase 2）:
  .venv/bin/python ops/reform_pool.py --champion gen0022 --plan default          # dry-run（--do 無し）
  .venv/bin/python ops/reform_pool.py --champion gen0022 --plan default --do     # 実行（rate_pool + 王者ベースライン）

完了条件（計画 Phase 2）:
  - 新プールの各相手の rating が付き、王者評価の pool.rating_se < 60
  - records/eval_<王者>.json の pool_sha256 が新しい control/sparring_pool.json と一致
  - STATUS.md のプール表を更新（これは人/夜間セッションが行う）
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY_BIN = str(ROOT / ".venv/bin/python")
POOL = ROOT / "control/sparring_pool.json"

# 計画 §1-C Phase 2 の改編内容。
#   自系統は 3 体 → 1 体（gen0018 のみ残す。王者直前の集中型＝別の型の対照として有用）
#   強帯を 5 体 → 8 体（公開上位型に対する解像度を上げる。上位10% への proxy はここでしか測れない）
#   yhay81_router は macOS arm64 専用 dylib のため据置き（無効のまま）
PLANS = {
    "default": {
        "disable": ["gen0003", "gen0013"],
        "enable": ["boatlee_v29", "sokolovsky", "pilkwang"],
        "why": "自系統 3→1（ミラー戦バイアスの縮小）／強帯 5→8（上位10% への解像度）",
    },
    # 2026-09-10 指標監査（knowledge/analysis/2026-09-10_metric-audit.md）:
    # 旧プールは 1,100 戦で勝率が 0/100% 以外の相手が 1 体も無く、**LB が実際に測っている量
    # （勝敗の反転）を測れていなかった**。実戦でラダーを動かすのは相手レート 700-800 帯。
    # 追試（2026-09-10_midband-verification.md）で、この 3 体の平均勝率が
    # gen0048(王者) 40-48% > gen0052(非昇格) 26% > gen0053(棄却) 5-6% > gen0036(旧型) 3% と
    # 既知の評価どおりの順序で並ぶこと（＝識別力があること）を確認した。
    # gen0018 は旧プールで 100% 勝ちで starter / georgy と役割が重複するので外す。
    "midband": {
        "disable": ["gen0018"],
        "enable": ["gen0044", "gen0045", "gen0051"],
        "why": "中間帯の新設（2026-09-10 指標監査）: 勝率 0/100% しかないプールでは"
               "margin は測れても win の反転が測れず、LB の目的関数と対象がずれていた",
    },
    # 2026-09-10 夜: 王者交代 gen0048→gen0051 で gen0051 がプール(mid)と王者を兼ねた。
    # evaluate.py が自己対戦を除くため、王者評価は 12 体・新候補は 13 体になり、
    # 候補 vs 王者 の直接対戦がゲートの対応付けから落ちて rating_delta が約 +5.7 甘くなる
    # （DIRECTIVES 2026-09-10 ★2。案 2 を採用）。**王者はプールに入れない**を恒久規約にする
    # ので、王者を外して mid 帯を gen0044/gen0045 の 2 体に戻す。
    "champion_out": {
        "disable": ["gen0051"],
        "enable": [],  # gen0044/gen0045 は既に enabled（midband で追加済み）
        "why": "王者 gen0051 の二重籍を解消（案 2・恒久規約「王者はプールに入れない」）: "
               "自己対戦除外による 12/13 の非対称と rating_delta の甘さを消す",
    },
    # 2026-09-19: 強帯の天井が実勢と違う。現行の強帯 8 体は公開 Notebook 由来だが、
    # 我々の系譜と同じ LB 720-760 帯の型で、上位10%（2397）や実勢の公開 SOTA を代表していない。
    # dmitriigluzdov_7turn は本アカウントの手動提出そのもの（route-lookup B 系譜・凍結で
    # LB 1561-1934）で、強帯の上端を実勢まで引き上げる。同系譜の親 yhay81_router は
    # 「同じテープ 2 体」で強帯の重み付けが歪むので有効化しない。
    "public_sota": {
        "disable": [],
        "enable": ["dmitriigluzdov_7turn"],
        "why": "強帯の上端を実勢の公開 SOTA まで引き上げる（2026-09-19）: 既存強帯 8 体は "
               "LB 720-760 帯で上位10%(2397)への proxy になっていなかった",
    },
}


def load_pool():
    return json.loads(POOL.read_text())


def apply_plan(pool, plan, ts):
    names = {e["name"]: e for e in pool["opponents"]}
    missing = [n for n in plan["disable"] + plan["enable"] if n not in names]
    if missing:
        sys.exit(f"NO-GO: プールに存在しない相手: {missing}")
    for n in plan["disable"]:
        e = names[n]
        e["enabled"] = False
        e["why_disabled"] = f"プール改編 {ts[:10]}: {plan['why']}"
    for n in plan["enable"]:
        e = names[n]
        e["enabled"] = True
        e.pop("why_disabled", None)
    pool["_reformed_at"] = ts
    pool["_reform_note"] = plan["why"]
    # 旧レーティングは尺度が変わるので消す（rate_pool.py --write が入れ直す）。
    # 消しておかないと、取り直しに失敗した時に古い値で評価してしまう。
    for e in pool["opponents"]:
        if e.get("enabled", True):
            e.pop("rating", None)
            e.pop("rated_games", None)
    return pool


def run(cmd, label):
    print(f"\n=== {label}\n$ {' '.join(cmd)}", flush=True)
    rc = subprocess.run(cmd, cwd=ROOT).returncode
    if rc != 0:
        raise RuntimeError(f"{label} が失敗 (rc={rc})")


def main():
    ap = argparse.ArgumentParser()
    champ_default = None
    cp = ROOT / "control/champion.json"
    if cp.exists():
        champ_default = json.loads(cp.read_text()).get("gen")
    ap.add_argument("--champion", default=champ_default,
                    help="現王者の世代名 (既定: control/champion.json の gen)")
    ap.add_argument("--plan", default="default", choices=sorted(PLANS))
    ap.add_argument("--rate-seeds", type=int, default=12, help="総当たりのシード数")
    ap.add_argument("--eval-seeds", type=int, default=50, help="王者ベースラインのシード数")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--also-eval", default="",
                    help="ベースライン取り直し後に参考再評価する世代(カンマ区切り。例 gen0023)")
    ap.add_argument("--do", action="store_true", help="実際に実行する(既定は dry-run)")
    args = ap.parse_args()

    if not args.champion:
        sys.exit("NO-GO: --champion を指定するか control/champion.json に gen を書くこと")
    plan = PLANS[args.plan]
    ts = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    champ_main = ROOT / "agents" / args.champion / "main.py"
    if not champ_main.exists():
        sys.exit(f"NO-GO: {champ_main} がない")

    before = load_pool()
    enabled_before = [e["name"] for e in before["opponents"] if e.get("enabled", True)]
    # 本番プールが既に半端な改編状態でないかの検査（防御。新設計では本番は原子的にしか
    # 更新されないのでここに来ないはずだが、以前の版が kill で残した状態を拾えるように）:
    # enabled な相手が居るのに rating が 1 つも無い＝rate_pool 前に止まった痕跡。
    if enabled_before and not any(
            e.get("rating") is not None
            for e in before["opponents"] if e.get("enabled", True)):
        sys.exit("NO-GO: 本番プールの enabled な相手に rating が 1 つも無い"
                 "（前回の reform が rate_pool 前に kill された半端状態の疑い）。"
                 "`git checkout HEAD -- control/sparring_pool.json` で正常状態に戻してから再実行すること。")
    after = apply_plan(json.loads(json.dumps(before)), plan, ts)
    enabled_after = [e["name"] for e in after["opponents"] if e.get("enabled", True)]
    print(f"改編案 [{args.plan}]: {plan['why']}")
    print(f"  無効化: {plan['disable']}")
    print(f"  有効化: {plan['enable']}")
    print(f"  enabled: {len(enabled_before)} 体 {enabled_before}")
    print(f"        → {len(enabled_after)} 体 {enabled_after}")
    print(f"  王者ベースライン: {args.champion} を seeds={args.eval_seeds} で取り直す")
    if not args.do:
        print("\n(dry-run: --do で実行。総当たり + ベースラインで 1 夜ぶんの時間がかかる)")
        return

    backup = ROOT / f"control/sparring_pool.{ts[:10]}.bak.json"
    shutil.copy(POOL, backup)
    print(f"\nバックアップ: {backup.relative_to(ROOT)}")

    # 生きた本番プールには最後まで触れない。改編は作業用コピーに書き、rate_pool / evaluate を
    # それに対して走らせ、完了条件を満たしたときだけ最後に os.replace で本番へ差し替える。
    #   保証: 各ファイル（プール・王者ベースライン）は決して途中書きの半端な状態にならない。
    #     途中で kill されても本番プールは元の正常値のまま（孤児になるのは作業ファイルだけ）。
    #   限界: プールとベースラインの 2 つの os.replace の「間」で kill されると新プール＋旧
    #     ベースラインになりうる（窓は数マイクロ秒）。この不一致は pool_sha256 検査で
    #     evaluate.py / preflight が fail-closed 拒否するので誤提出にはならない（旧コードの
    #     「40 分ずっと本番プールが壊れる」窓とは別物）。
    work = ROOT / "control/sparring_pool.reform_work.json"
    work_rel = str(work.relative_to(ROOT))
    out = f"records/eval_{args.champion}.json"
    eval_tmp = ROOT / f"records/eval_{args.champion}.reform_tmp.json"

    def _discard():
        for p in (work, eval_tmp):
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    try:
        work.write_text(json.dumps(after, indent=1, ensure_ascii=False) + "\n")
        # 2. 総当たりでレーティング取り直し（作業コピーに --write。尺度を合わせるため必須）
        run([PY_BIN, "harness/rate_pool.py", "--pool", work_rel,
             "--seeds", str(args.rate_seeds), "--jobs", str(args.jobs), "--write"],
            "総当たりレーティング (rate_pool.py --write)")
        rated = json.loads(work.read_text())
        unrated = [e["name"] for e in rated["opponents"]
                   if e.get("enabled", True) and e.get("rating") is None]
        if unrated:
            raise RuntimeError(f"レーティングが付かなかった相手がある: {unrated}")

        # 3. 王者ベースラインを作業コピーで取り直す
        run([PY_BIN, "harness/evaluate.py", "--candidate", f"agents/{args.champion}/main.py",
             "--pool", work_rel, "--seeds", str(args.eval_seeds),
             "--jobs", str(args.jobs), "--out", str(eval_tmp.relative_to(ROOT))],
            f"王者ベースライン再取得 ({out})")

        ev = json.loads(eval_tmp.read_text())
        pool_sha = hashlib.sha256(work.read_bytes()).hexdigest()
        se = (ev.get("pool") or {}).get("rating_se")
        problems = []
        if ev.get("pool_sha256") != pool_sha:
            problems.append("王者評価の pool_sha256 が作業コピーと不一致")
        if se is None or se >= 60:
            problems.append(f"pool.rating_se={se} が 60 未満でない（プールの強さ帯が合っていない）")
        print("\n=== 完了条件")
        print(f"  pool_sha256 一致: {ev.get('pool_sha256') == pool_sha}")
        print(f"  rating_se: {se} (< 60 が条件)")
        print(f"  強帯: {(ev.get('pool') or {}).get('strong_opponents')} 体 / "
              f"強帯資金 {(ev.get('pool') or {}).get('strong_money_mean')} "
              f"(相手 {(ev.get('pool') or {}).get('strong_opp_money_mean')})")
        if problems:
            # 未達なら本番に反映しない（半端に良いプールを live にするより、既知の正常な旧プールを残す）。
            raise RuntimeError("完了条件 未達: " + " / ".join(problems))

        # 評価は作業コピー(work_rel)に対して走ったので pool_file に一時パスが残る。正典名に
        # 直してから反映する（pool_sha256 は変えない。ベースラインも正典名で持つのが正しい）。
        if ev.get("pool_file") != "control/sparring_pool.json":
            ev["pool_file"] = "control/sparring_pool.json"
            eval_tmp.write_text(json.dumps(ev, indent=1, ensure_ascii=False))

        # 全ての完了条件をクリアしたときだけ、ここで初めて原子的に本番へ反映する。
        os.replace(work, POOL)
        os.replace(eval_tmp, ROOT / out)
        print(f"\n本番へ原子的に反映: {POOL.relative_to(ROOT)} / {out}")
    except RuntimeError as e:
        # ここに来るのは本番反映(os.replace)より前の失敗だけ＝本番プールは未変更。
        sys.exit(f"\nNO-GO: {e}\n  本番プール control/sparring_pool.json は元のまま"
                 "（作業ファイルを破棄した）。王者ベースラインも旧プールのままなので"
                 "そのまま夜間運転を続けてよい。差し戻し用バックアップ: "
                 f"{backup.relative_to(ROOT)}")
    finally:
        # 成功時は os.replace で消えている（FileNotFoundError は握りつぶす）。RuntimeError 以外の
        # 例外・Ctrl-C で抜けるときも作業ファイルを残さない。
        _discard()

    # 参考再評価は本番反映が成功したあとにだけ、本番プールに対して行う。
    for g in [x.strip() for x in args.also_eval.split(",") if x.strip()]:
        run([PY_BIN, "harness/evaluate.py", "--candidate", f"agents/{g}/main.py",
             "--pool", "control/sparring_pool.json", "--seeds", str(args.eval_seeds),
             "--jobs", str(args.jobs), "--baseline", out,
             "--out", f"records/eval_{g}.json"],
            f"参考再評価 {g}")

    print("\n次にやること: STATUS.md のプール表を新レーティングで更新し、"
          "state/HANDOFF.md の『王者ベースライン』行を書き換える")


if __name__ == "__main__":
    main()
