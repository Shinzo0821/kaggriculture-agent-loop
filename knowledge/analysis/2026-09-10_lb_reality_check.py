#!/usr/bin/env python
"""2026-09-10 指標監査の再現スクリプト。

Kaggle 公開 episode API から「自分の提出が実戦でどう戦ったか」を取り、
ローカル指標との突き合わせに必要な統計を出す。リプレイ本体(1件 30MB)は落とさない。

usage:
  # 監査時点のスナップショットで再現する（推奨。表が完全に一致する）
  .venv/bin/python knowledge/analysis/2026-09-10_lb_reality_check.py \
      --snapshot knowledge/analysis/2026-09-10_episodes_snapshot.json

  # 今の LB から取り直す（提出が活動中なら試合が増えるので表は変わる）
  .venv/bin/python knowledge/analysis/2026-09-10_lb_reality_check.py \
      --subs sub-15=gen0036,sub-16=gen0044,sub-17=gen0045,\
sub-18=gen0048,sub-19=gen0051,sub-20=gen0052 --out /tmp/snap.json

出るもの:
  0. 標本の完全性チェック（ラダー鎖・始点 600・終点 = LB スコア）
  1. 世代ごとの実戦 W-L-T・マージン平均/sd/se・自資金・平均相手レート
  2. その効果量を実戦で検出するのに要る試合数（power 50% と 80% の両方）
  3. 共通相手の数（LB で対応付き比較ができるか）
  4. 相手レート帯別の勝率（線形性を仮定しない素の表）
  5. 相手強度で調整した勝率 — **3 つのモデル指定を並べる**（順位が指定に依存するため）
  6. LB スコア = 600 + Σ(ラダー更新) の分解と |δ| の減衰

2026-09-10 の Codex クロスレビュー（gpt-5.6-sol/high）で入った修正:
  - 検出力は (1.96σ/δ)² だと power ≈ 50%。80% power は ((1.96+0.84)σ/δ)² で約 2 倍。両方出す。
  - 相手レート単独調整は不十分（マッチメイキングは双方のレートに依存）。自レート込み・レート差の
    3 指定を並べる。**世代の順位はこの指定で入れ替わる**ので、単一指定の順位を結論にしない。
  - 「+100 で 50%→6.4%」は基準勝率 50% でのみ成立。平均限界効果(AME)と帯別の素の表を出す。
  - IRLS の収束・条件数・|β|max を必ず表示する（完全分離の検出）。
  - state は COMPLETED を厳密に要求。引き分けは勝ちにも負けにも数えず別に数える。
  - sd は標本標準偏差(n−1)。
  - ラダーの並びは episode id ではなく createTime。
"""
import argparse, json, math, statistics as st, sys, time, urllib.request

API = "https://www.kaggle.com/api/i/competitions.EpisodeService/ListEpisodes"
TEAM = "Shinzo Takayama"


def call(body, retries=(0, 5, 15, 30)):
    req = urllib.request.Request(
        API, data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "user-agent": "kaggriculture-agent-loop"})
    err = None
    for w in retries:
        if w:
            time.sleep(w)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # 429/5xx/接続断はバックオフして再試行
            err = e
    raise RuntimeError(f"episode API 失敗: {err}")


def fetch(subs):
    """subs: {submission_id: gen名} → {gen: [試合レコード]}

    この API は submissionId 指定だと当該提出の全 episode を 1 応答で返す（ページングキーは無い）。
    完全性は report() の §0 が「始点 600 / 終点 = LB スコア / ラダー鎖に切れ目なし」で検査する。
    """
    teams, out = {}, {}
    for ref, gen in subs.items():
        d = call({"submissionId": int(ref)})
        if set(d) - {"episodes", "submissions", "teams"}:
            print(f"  ! 未知の応答キー {set(d) - {'episodes','submissions','teams'}}"
                  " — ページングが増えていないか確認", file=sys.stderr)
        for t in d.get("teams", []):
            teams[int(t["id"])] = t.get("teamName")
        out[gen] = d.get("episodes", [])
        print(f"  {gen}: {len(out[gen])} episodes", file=sys.stderr)
        time.sleep(1.0)  # 公開 API への礼儀
    me = [k for k, v in teams.items() if v == TEAM]
    if len(me) != 1:
        raise SystemExit(f"自チームを特定できない: {me}")
    my_id = me[0]
    recs, skipped = {}, 0
    for gen, eps in out.items():
        rs = []
        for ep in eps:
            if ep.get("state") != "COMPLETED":   # None も落とす（厳密）
                skipped += 1
                continue
            ags = sorted(ep.get("agents") or [], key=lambda a: a.get("index", 0))
            if len(ags) != 2:
                skipped += 1
                continue
            mi = [i for i, a in enumerate(ags) if a.get("teamId") == my_id]
            if len(mi) != 1:
                skipped += 1
                continue
            m, o = ags[mi[0]], ags[1 - mi[0]]
            if m.get("reward") is None or o.get("reward") is None:
                skipped += 1
                continue
            rs.append({"id": int(ep["id"]), "create": ep.get("createTime"),
                       "my": m["reward"], "opp": o["reward"],
                       "before": m.get("initialScore"), "after": m.get("updatedScore"),
                       "oppbefore": o.get("initialScore"), "oppteam": o.get("teamId")})
        recs[gen] = rs
    if skipped:
        print(f"  除外 {skipped} 件（COMPLETED でない/2 者でない/reward 欠損）", file=sys.stderr)
    return recs


def logit_fit(X, y, ridge=1e-6, iters=300):
    """IRLS。numpy だけで済ませる(statsmodels は .venv に無い)。

    完全分離のとき ridge が有限解を作ってしまうので、収束フラグ・条件数・|β|max を
    呼び出し側に返して必ず表示させる。SE は penalized Hessian 由来なので近似。
    """
    import numpy as np
    k = X.shape[1]
    beta = np.zeros(k)
    conv, it = False, 0
    for it in range(1, iters + 1):
        p = 1 / (1 + np.exp(-X @ beta))
        W = np.diag(p * (1 - p) + 1e-9)
        step = np.linalg.solve(X.T @ W @ X + ridge * np.eye(k), X.T @ (y - p))
        beta = beta + step
        if np.max(np.abs(step)) < 1e-10:
            conv = True
            break
    p = 1 / (1 + np.exp(-X @ beta))
    W = np.diag(p * (1 - p) + 1e-9)
    H = X.T @ W @ X + ridge * np.eye(k)
    ll = float(np.sum(y * np.log(np.clip(p, 1e-12, 1)) + (1 - y) * np.log(np.clip(1 - p, 1e-12, 1))))
    return beta, np.sqrt(np.diag(np.linalg.inv(H))), {
        "conv": conv, "iters": it, "loglik": ll,
        "cond": float(np.linalg.cond(H)), "bmax": float(np.max(np.abs(beta))), "p": p}


def report(recs, effect, lb):
    import numpy as np
    gens = list(recs)
    f = lambda z: 100 / (1 + math.exp(-z))

    print("=== 0. 標本の完全性（API が全試合を返したか）===")
    print("  LB スコア = 600 + Σ(ラダー更新)。始点 600・終点 = 既知の LB スコア・鎖に切れ目なし、")
    print("  が揃えば取りこぼしは無い。切れ目は同時進行の試合による順序ずれでも出るので、終点で判断する。")
    for g in gens:
        rs = sorted([r for r in recs[g] if r["before"] is not None and r["after"] is not None],
                    key=lambda r: (r["create"] or "", r["id"]))
        if not rs:
            continue
        brk = sum(1 for i in range(len(rs) - 1) if abs(rs[i]["after"] - rs[i + 1]["before"]) > 1e-6)
        end = rs[-1]["after"]
        known = lb.get(g)
        ok = "—" if known is None else ("一致" if abs(end - known) < 0.15 else f"★不一致(既知 {known})")
        print(f"  {g}: n={len(rs):3d} 始点={rs[0]['before']:.1f} 終点={end:7.1f} {ok}  鎖の切れ目={brk}")

    print("\n=== 1. 実戦の素の成績 ===")
    print(f"{'gen':8} {'n':>3} {'W-L-T':>9} {'勝率':>7} {'マージン平均':>12} "
          f"{'sd':>9} {'se':>8} {'自資金':>10} {'平均相手レート':>14}")
    for g in gens:
        rs = recs[g]
        m = [r["my"] - r["opp"] for r in rs]
        w = sum(1 for x in m if x > 0); t = sum(1 for x in m if x == 0)
        ob = [r["oppbefore"] for r in rs if r["oppbefore"] is not None]
        sd = st.stdev(m)
        print(f"{g:8} {len(m):3d} {f'{w}-{len(m)-w-t}-{t}':>9} {100*w/len(m):6.1f}% "
              f"{st.mean(m):12,.0f} {sd:9,.0f} {sd/math.sqrt(len(m)):8,.0f} "
              f"{st.mean(r['my'] for r in rs):10,.0f} {(st.mean(ob) if ob else float('nan')):14.1f}")

    allm = [r["my"] - r["opp"] for g in gens for r in recs[g]]
    sd_all = st.stdev(allm)
    n50 = (1.96 * sd_all / effect) ** 2
    n80 = ((1.96 + 0.8416) * sd_all / effect) ** 2
    print(f"\n=== 2. 検出力 ===")
    print(f"実戦マージンの sd = ${sd_all:,.0f}（横断・相手が毎回違う）。効果量 ${effect:,.0f} に対し:")
    print(f"  power 50%（CI 下限がちょうど 0 に届く）: 約 {n50:,.0f} 試合")
    print(f"  power 80%（実用的な検出）              : 約 {n80:,.0f} 試合")
    print(f"  2 世代の差として検出するなら 1 世代あたりさらに約 2 倍: 約 {2*n80:,.0f} 試合")
    print(f"  実際は 1 世代 {min(len(recs[g]) for g in gens)}-{max(len(recs[g]) for g in gens)} 試合。")
    print("  ※ 注意: この sd は『毎回違う相手との横断マージン』。ローカルの効果量は『固定相手・同一シードの")
    print("     対応付き差』で推定対象が違う。だが LB 側には対応付けが存在しない（§3）ので、")
    print("     『LB でこの差を読めるか』という問いにはこの横断 sd が正しい。")

    print("\n=== 3. 共通相手（LB で対応付き比較ができるか）===")
    for i, a in enumerate(gens):
        for b in gens[i+1:]:
            sa = {r["oppteam"] for r in recs[a]}; sb = {r["oppteam"] for r in recs[b]}
            print(f"  {a} ({len(sa)} チーム) ∩ {b} ({len(sb)} チーム) = {len(sa & sb)}")

    bands = [(0, 700, "<700"), (700, 800, "700-800"), (800, 1000, "800-1000"), (1000, 10**9, ">=1000")]
    print("\n=== 4. 相手レート帯別の勝率（線形性を仮定しない素の表）===")
    print(f"{'gen':8} " + " ".join(f"{l:>14}" for _, _, l in bands))
    for g in gens:
        cells = []
        for lo, hi, _ in bands:
            rs = [r for r in recs[g] if r["oppbefore"] is not None and lo <= r["oppbefore"] < hi]
            if not rs:
                cells.append(f"{'-':>14}"); continue
            w = sum(1 for r in rs if r["my"] > r["opp"])
            cells.append(f"{w}/{len(rs)}={100*w/len(rs):3.0f}%".rjust(14))
        print(f"{g:8} " + " ".join(cells))
    print(f"{'合計':8} " + " ".join(
        (lambda w, n: f"{w}/{n}={100*w/n:3.0f}%".rjust(14) if n else f"{'-':>14}")(
            sum(1 for g in gens for r in recs[g]
                if r["oppbefore"] is not None and lo <= r["oppbefore"] < hi and r["my"] > r["opp"]),
            sum(1 for g in gens for r in recs[g]
                if r["oppbefore"] is not None and lo <= r["oppbefore"] < hi))
        for lo, hi, _ in bands))

    print("\n=== 5. 相手強度で調整した勝率 — モデル指定を 3 つ並べる ===")
    print("  マッチメイキングは双方のレートに依存するので相手レート単独の調整は不十分。")
    print("  **世代の順位はこの指定で入れ替わる。単一指定の順位を結論にしないこと。**")
    rows = [(gi, r["oppbefore"], r["before"], 1.0 if r["my"] > r["opp"] else 0.0)
            for gi, g in enumerate(gens) for r in recs[g]
            if r["oppbefore"] is not None and r["before"] is not None]
    specs = [(["opp"], "相手レートのみ"), (["opp", "me"], "相手レート + 自レート"),
             (["diff"], "レート差(相手−自分)のみ")]
    for cols, label in specs:
        k = len(gens) + len(cols)
        X = np.zeros((len(rows), k)); y = np.zeros(len(rows))
        for i, (gi, ob, mb, w) in enumerate(rows):
            X[i, gi] = 1.0; y[i] = w
            for j, c in enumerate(cols):
                X[i, len(gens) + j] = {"opp": (ob - 780) / 100, "me": (mb - 750) / 100,
                                       "diff": (ob - mb) / 100}[c]
        beta, se, dg = logit_fit(X, y)
        ame = float(np.mean(dg["p"] * (1 - dg["p"]) * beta[len(gens)])) * 100
        print(f"\n  --- {label} --- 収束={dg['conv']}(iter={dg['iters']}) "
              f"対数尤度={dg['loglik']:.2f} 条件数={dg['cond']:.1f} |β|max={dg['bmax']:.2f}")
        for gi, g in enumerate(gens):
            b, s = beta[gi], se[gi]
            print(f"    {g}: {f(b):5.1f}% [{f(b-1.96*s):.1f}, {f(b+1.96*s):.1f}]  (β={b:+.3f}±{s:.3f})")
        print(f"    第1共変量 {cols[0]} +100: β={beta[len(gens)]:+.3f}±{se[len(gens)]:.3f} "
              f"／ **平均限界効果 {ame:+.1f}pt**（50% 基準の見かけの値 "
              f"{f(beta[len(gens)])-50:+.1f}pt ではなくこちらを使う）")

    print("\n=== 6. LB スコア = 600 + Σ(ラダー更新) と |δ| の減衰 ===")
    for g in gens:
        rs = sorted([r for r in recs[g] if r["before"] is not None and r["after"] is not None],
                    key=lambda r: (r["create"] or "", r["id"]))
        dl = [r["after"] - r["before"] for r in rs]
        if not dl:
            continue
        print(f"{g}: n={len(dl):3d} Σδ={sum(dl):+7.1f} → LB={600+sum(dl):6.1f}   "
              f"|δ| 最初10試合={st.mean(map(abs, dl[:10])):5.1f} / 最後10試合={st.mean(map(abs, dl[-10:])):5.1f}")
    print("\n→ LB は勝敗の積分。初期の |δ| が最終値に残るので、35-65 試合では収束していない。")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subs", help="submissionId=gen名 のカンマ区切り（LB から取り直す）")
    ap.add_argument("--snapshot", help="保存済みスナップショット JSON から読む（再現用）")
    ap.add_argument("--out", help="取得した試合レコードの保存先 JSON")
    ap.add_argument("--effect", type=float, default=313.0,
                    help="ローカルで判定に使っている効果量(既定=gen0048 のマージン差 $313)")
    a = ap.parse_args()
    if not (a.subs or a.snapshot):
        ap.error("--subs か --snapshot のどちらかが要る")
    if a.snapshot:
        blob = json.load(open(a.snapshot))
        recs, lb = blob["records"], blob.get("lb_scores", {})
        print(f"スナップショット {a.snapshot}（取得 {blob.get('fetched_at')}）を使用\n", file=sys.stderr)
    else:
        recs = fetch(dict(kv.split("=") for kv in a.subs.split(",")))
        lb = {}
        if a.out:
            json.dump({"fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                       "records": recs, "lb_scores": lb}, open(a.out, "w"))
    report(recs, a.effect, lb)


if __name__ == "__main__":
    main()
