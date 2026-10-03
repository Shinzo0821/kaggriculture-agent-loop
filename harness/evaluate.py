#!/usr/bin/env python
"""FR-2 (v2, 2026-09-04): 候補を「多様な相手プール」と複数シードで並列対戦させ、
プール・レーティング / 絶対資金 / 後半傾き を出し、王者(ベースライン)との差分でゲート判定する。

usage:
  evaluate.py --candidate agents/genNNNN/main.py --pool control/sparring_pool.json \
      [--opponents starter,agents/x/main.py] [--champion agents/genNNNN/main.py] \
      [--baseline records/eval_genNNNN.json] [--seeds 100] [--jobs 8] [--out records/eval_genNNNN.json]

設計（なぜこの指標か）:
- LB は勝敗のみのスキルレーティング。目的関数は「LB 母集団に対する勝率」。
- しかし単一の相手に対する勝率は、その相手が強すぎ/弱すぎると 0/100% に張り付いて情報がない。
  → プール各相手の固定レーティング(harness/rate_pool.py が総当たりで算出)に対して
    候補のレーティングを最尤推定する(Bradley-Terry / Elo 尺度 400)。情報量のある相手が自然に効く。
- 自系統(王者)とのミラー戦は市場共有の歪みがあるので、ゲートには使わず参考値にする。
- 絶対資金(プール全試合の候補最終資金)と後半傾き((最終資金 − d23資金)/7日)は
  「なぜ強く/弱くなったか」の診断用。資金は同一シード・同一相手でベースラインと**対応付き**比較する。

ゲート(--baseline 指定時。ベースライン＝現行王者を同じプール・同じシードで評価した JSON):
  promotion(昇格) v0.6 (2026-09-10。DIRECTIVES 2026-09-10 ★1) = エラー0 かつ次のどちらか:
    (A) マージン経路: 対応付きマージン差の95%CI下限 > 0（v0.5 のゲートそのまま）
    (B) rating 経路: rating が情報を持つ(gate.rating_informative) かつ
        rating_delta の95%CI下限 > 0(gate.rating_delta_ci) かつ **マージン点推定 ≥ 0**
    2026-09-05 にマージン一本化したのは二極プールで rating が無力だったからで、
    プール改編(中間帯の新設)で rating_informative=True に戻ったため rating 経路を足した。
    マージンは勝敗の定義(run_match.py の winner)なのでマージン経路には rating 条件を課さない。
    rating 経路にはマージン点推定 ≥ 0 の非負ガードを付ける(勝ち数は増えるがドルで負ける型を弾く)。
    どちらで通ったかは gate.pass_route に記録する。実例: gen0051 は rating 4σ・マージン検出不能で
    v0.5 では人が手で pass を上書きしないと昇格できなかった(v0.6 の rating 経路で通る)。
    gate.rating_informative は勝敗が拮抗する相手(勝率 0/100% でない)がプールに居るかを記録する
    (2026-09-10 監査: 全相手が 0/100% に張り付くと rating は候補を変えても動かない)。
    2026-09-05 改訂その2: 資金の基準を「自分の最終資金の差」から
    **「マージン(自分 − 相手)の差」**に変えた。勝敗は cand_final > opp_final で決まる
    （harness/run_match.py）のに、旧基準は cand_final しか見ておらず、
    「相手の資金を削るが自分は横ばい」の変更を $0 と評価して却下していた。
    実測(gen0026 vs gen0025, 50シード)では 自分 +$8,974 / 相手 −$5,095 / マージン +$14,069 で、
    旧基準は改善を 1.6 倍過小評価していた。マージンは CI も狭い($4,499 vs $5,644)
    ——同一シードのノイズが両者に共通に乗るので差を取ると打ち消えるため。
    money_delta_paired（自分の資金）は診断用に残す:
    **自分の絶対額が下がる型は、マージンで勝っていても再投資が回らず翌日以降の生産能力が落ちる**
    （knowledge/analysis/2026-09-05_denial-vs-production.md）。
    2026-09-05 改訂: rating_delta の条件を > 0 から >= 0 に緩めた。現プールは相手別の勝率が
    完全に二極化していて(弱 3 体に 100% / 強帯 8 体に 0%、資金差は全強帯に対し −$58k〜−$71k)、
    資金が $6k 動いても勝敗がほとんど入れ替わらない。gen0022→gen0024 の rating_delta +6.2 は
    1,100 戦のうち 3 勝の差で、符号が数試合で決まる。この解像度の指標を「前進した」の必要条件に
    置くと、資金で明確に前進した世代を落としうる。**前進の判定は対応付き資金差の CI 下限**が担い、
    rating は「大きく劣化していないこと」の確認に回す。中間帯(たまに勝てる相手)を足せば
    解像度は戻るが、2026-09-05 時点で手元の公開実装にも自系統にも該当する強さの相手がいない
    (knowledge/analysis/2026-09-05_pool-bimodality.md)。
  submit(破滅回避) = エラー0 かつ rating_delta > -100（大幅劣化でない）
--baseline なしの場合は gate.pass=None（判定不能）。submit_ok は starter がいれば starter>=95% で代用。

2026-09-05 追加(計画 §1-C / §2-B。昇格条件そのものは据置き):
- gate.strong_money_delta_paired / gate.strong_slope_delta: tier=strong の相手だけに絞った
  対応付き資金差と後半傾き差。**プール全体のレーティングは「弱・中に何%勝つか」で決まるため、
  上位10%(=強帯の型)への proxy として弱い**。強帯資金が動かない改善は前進と数えない
  (`ops/NIGHTLY.md`)。昇格条件に組み込むかはプール改編後に判断する。
- gate.too_good: 改善が大きすぎる(既定 rating_delta>150 / 資金差平均>$8,000)時に立つフラグ。
  「良すぎる = 測り方の事故」を疑い、preflight は別 seed-base の再評価(--recheck)を要求する。
  閾値は control/submission_policy.json の too_good_flag。
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from run_match import run_match  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LATE_DAY = 23  # 後半傾きの起点(LB 敗戦の逆転日 d22-25 の直前)


def one_game(candidate, opponent, seed, cand_side, steps):
    a, b = (candidate, opponent) if cand_side == 0 else (opponent, candidate)
    result, _ = run_match(a, b, seed, steps)
    w = result["winner"]
    score = 0.5 if w is None else (1.0 if w == cand_side else 0.0)
    diff = result["money_diff"]
    cand_diff = diff if cand_side == 0 else (-diff if diff is not None else None)
    fm = result["final_money"]
    mbd = result["timeseries"].get("money_by_day", {})
    late = mbd.get(LATE_DAY) or mbd.get(str(LATE_DAY))
    c, o = cand_side, 1 - cand_side
    cand_final = fm[c]
    opp_final = fm[o]
    days_left = 30 - LATE_DAY
    ok = bool(late) and None not in (late[c], late[o])
    cand_slope = (cand_final - late[c]) / days_left if (ok and cand_final is not None) else None
    opp_slope = (opp_final - late[o]) / days_left if (ok and opp_final is not None) else None
    return {
        "opponent": opponent,
        "seed": seed,
        "cand_side": cand_side,
        "score": score,
        "money_diff": cand_diff,
        "cand_final": cand_final,
        "opp_final": opp_final,
        "cand_slope": cand_slope,
        "opp_slope": opp_slope,
        "statuses": result["statuses"],
    }


def wilson(wins, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def fit_rating(results, lo=-2000.0, hi=2000.0):
    """results: list of (opp_rating, score∈{0,0.5,1}). Elo尺度(400)で候補レーティングを最尤推定。
    対数尤度は r に関して凹なので二分法で勾配=0 を解く。"""
    if not results:
        return None

    def grad(r):
        g = 0.0
        for R, s in results:
            p = 1.0 / (1.0 + 10 ** ((R - r) / 400.0))
            g += s - p
        return g

    g_lo, g_hi = grad(lo), grad(hi)
    if not (math.isfinite(g_lo) and math.isfinite(g_hi)) or g_lo <= 0 or g_hi >= 0:
        return None  # 全勝/全敗など有限の MLE が無い(判定不能として扱う)
    for _ in range(80):
        mid = (lo + hi) / 2
        if grad(mid) > 0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 1)


def rating_se(results, r):
    """Fisher情報量からレーティングの標準誤差(Elo尺度)。"""
    if r is None or not results:
        return None
    k = math.log(10) / 400.0
    info = 0.0
    for R, _ in results:
        p = 1.0 / (1.0 + 10 ** ((R - r) / 400.0))
        info += k * k * p * (1 - p)
    return round(1 / math.sqrt(info), 1) if info > 0 else None


def load_pool(path):
    d = json.loads(Path(path).read_text())
    entries = d["opponents"] if isinstance(d, dict) else d
    return [e for e in entries if e.get("enabled", True)]


def _own(g):
    """自分の最終資金（診断用）。"""
    return g.get("cand_final")


def _margin(g):
    """マージン = 自分 − 相手。**勝敗を決める量**（run_match.py の winner の定義）。"""
    if g.get("cand_final") is None or g.get("opp_final") is None:
        return None
    return g["cand_final"] - g["opp_final"]


def paired_delta(cand_games, base_games, field=_own):
    """同一(相手, シード, 側)で候補とベースラインを対応付き比較。
    field は _own（自分の資金）か _margin（自分 − 相手 = 勝敗を決める量）。
    乱数の独立単位はシード(同一シードの全相手・両席はショップ抽選等を共有)なので、
    シードごとに平均してからシード数で CI を取る(擬似反復を避ける)。対応が欠けたら判定不能。"""
    from collections import defaultdict
    idx = {(g["opponent"], g["seed"], g["cand_side"]): g for g in base_games}
    by_seed = defaultdict(list)
    for g in cand_games:
        b = idx.get((g["opponent"], g["seed"], g["cand_side"]))
        if b is None:
            return None
        cv, bv = field(g), field(b)
        if cv is None or bv is None:
            return None
        by_seed[g["seed"]].append(cv - bv)
    seed_deltas = [statistics.mean(xs) for xs in by_seed.values()]
    if len(seed_deltas) < 2:
        return None
    m = statistics.mean(seed_deltas)
    se = statistics.stdev(seed_deltas) / math.sqrt(len(seed_deltas))
    return {"n_pairs": len(cand_games), "n_seeds": len(seed_deltas), "mean": round(m, 1),
            "ci95": [round(m - 1.96 * se, 1), round(m + 1.96 * se, 1)]}


def _pos_se(x):
    """rating_se として使える値か = bool でない有限の正数。0/負/NaN/文字列は
    誤差ゼロや例外になるので rating 経路を fail-closed で閉じる(Codex 指摘 2026-09-10)。"""
    return type(x) in (int, float) and math.isfinite(x) and x > 0


def too_good_flag(gate):
    """計画 §2-B: 改善が大きすぎる評価に立てるフラグ(理由のリスト。無ければ None)。

    閾値は control/submission_policy.json の too_good_flag。preflight_submit.py は
    フラグ付きの評価に対して別 seed-base の再評価(--recheck)を要求する。
    """
    try:
        pol = json.loads((ROOT / "control/submission_policy.json").read_text()).get("too_good_flag")
    except (OSError, json.JSONDecodeError) as e:
        # 閾値が読めない時に「異常なし」にすると、設定を壊すだけで検査を無効化できてしまう。
        # 検査不能として理由を立て、preflight に再評価(--recheck)を要求させる(fail-closed)。
        return [f"too_good の閾値を読めなかった(検査不能): {str(e)[:60]}"]
    if not isinstance(pol, dict):
        return ["control/submission_policy.json に too_good_flag が無い(検査不能)"]
    reasons = []
    for key, label, val, fmt in (
            ("rating_delta_max", "rating_delta", gate.get("rating_delta"), "{:+.1f}"),
            ("money_delta_mean_max", "money_delta_paired.mean",
             (gate.get("money_delta_paired") or {}).get("mean"), "{:+.0f}"),
            ("margin_delta_mean_max", "margin_delta_paired.mean",
             (gate.get("margin_delta_paired") or {}).get("mean"), "{:+.0f}")):
        thr = pol.get(key)
        if not (type(thr) in (int, float) and math.isfinite(thr)):
            reasons.append(f"too_good_flag.{key} が有限数でない(検査不能): {thr!r}")
            continue
        if isinstance(val, (int, float)) and math.isfinite(val) and val > thr:
            reasons.append(f"{label} {fmt.format(val)} > {thr}")
    return reasons or None


def summarize(games, opponents, pool, pool_by_path, pool_sha256, args, wall_seconds,
              self_matches=()):
    """games から集計・ゲート判定を行い、出力 dict を返す（試合の実行を含まない）。

    実行と切り離してあるのは --regate のため。ゲートの定義を変えたとき、保存済みの
    games に対して**この同じコード**で再判定できる。
    """
    summary = {}
    rating_inputs = []
    for opp in opponents:
        gs = [g for g in games if g["opponent"] == opp]
        n = len(gs)
        wins = sum(g["score"] for g in gs)
        errors = sum(1 for g in gs if "ERROR" in g["statuses"] or "TIMEOUT" in g["statuses"])
        lo, hi = wilson(wins, n)
        entry = pool_by_path.get(opp, {})
        summary[opp] = {
            "name": entry.get("name", opp),
            "tier": entry.get("tier"),
            "rating": entry.get("rating"),
            "games": n,
            "win_rate": round(wins / n, 4) if n else None,
            "wilson95": [round(lo, 4), round(hi, 4)],
            "avg_money_diff": mean([g["money_diff"] for g in gs]),
            "cand_money_mean": mean([g["cand_final"] for g in gs]),
            "opp_money_mean": mean([g["opp_final"] for g in gs]),
            "cand_slope_mean": mean([g["cand_slope"] for g in gs]),
            "opp_slope_mean": mean([g["opp_slope"] for g in gs]),
            "error_or_timeout_games": errors,
        }
        if entry.get("rating") is not None:
            rating_inputs += [(entry["rating"], g["score"]) for g in gs]

    pool_games = [g for g in games if g["opponent"] in pool_by_path]
    # 強帯(公開上位型)だけの部分集合。LB 上位10% への距離はここでしか測れない(計画 §1-C)。
    strong_paths = {e["path"] for e in pool if e.get("tier") == "strong"}
    strong_games = [g for g in pool_games if g["opponent"] in strong_paths]
    pool_rating = fit_rating(rating_inputs)
    pool_stats = {
        "rating": pool_rating,
        "rating_se": rating_se(rating_inputs, pool_rating),
        "rated_opponents": sum(1 for e in pool if e.get("rating") is not None),
        "money_mean": mean([g["cand_final"] for g in pool_games]),
        "slope_mean": mean([g["cand_slope"] for g in pool_games]),
        "win_rate": round(sum(g["score"] for g in pool_games) / len(pool_games), 4) if pool_games else None,
        "strong_opponents": len(strong_paths),
        "strong_money_mean": mean([g["cand_final"] for g in strong_games]),
        "strong_slope_mean": mean([g["cand_slope"] for g in strong_games]),
        "strong_win_rate": (round(sum(g["score"] for g in strong_games) / len(strong_games), 4)
                            if strong_games else None),
        "strong_opp_money_mean": mean([g["opp_final"] for g in strong_games]),
    }

    total_errors = sum(v["error_or_timeout_games"] for v in summary.values())
    gate = {
        "errors_zero": total_errors == 0,
        "baseline": args.baseline,
        "baseline_compatible": None,
        "rating_delta": None,
        "rating_delta_ci": None,             # rating_delta の 95%CI(se 伝播。v0.6 の rating 経路)
        "rating_informative": None,          # プールに勝敗が拮抗する相手が居るか(2026-09-10 監査)
        "margin_delta_paired": None,         # 自分 − 相手。**昇格の判定に使う**
        "money_delta_paired": None,          # 自分の資金のみ。診断用(絶対額が下がる型の検出)
        "slope_delta": None,
        "strong_margin_delta_paired": None,  # tier=strong のみ
        "strong_money_delta_paired": None,   # tier=strong のみ(計画 §1-C)
        "strong_slope_delta": None,
        "too_good": None,                    # 良すぎる=測り方の事故を疑う(計画 §2-B)
        "pass": None,        # 昇格
        "pass_route": None,  # 昇格した経路(margin / rating。v0.6)
        "submit_ok": None,   # 破滅回避
        "note": None,
    }
    if args.baseline:
        base = json.loads((ROOT / args.baseline).read_text() if not Path(args.baseline).is_absolute()
                          else Path(args.baseline).read_text())
        bp = base.get("pool") or {}
        compatible = (base.get("pool_sha256") == pool_sha256 and pool_sha256 is not None
                      and base.get("seeds") == args.seeds and base.get("seed_base") == args.seed_base
                      and base.get("steps") == args.steps and bool(base.get("games")))
        gate["baseline_compatible"] = compatible
        if not compatible:
            gate["note"] = "ベースラインのプール(SHA)/シード/steps が一致しない → 判定不可。王者を同条件で再評価すること"
            gate["pass"] = False
            gate["submit_ok"] = False
        else:
            if pool_rating is not None and bp.get("rating") is not None:
                gate["rating_delta"] = round(pool_rating - bp["rating"], 1)
            base_games = base.get("games", [])
            gate["margin_delta_paired"] = paired_delta(pool_games, base_games, _margin)
            gate["money_delta_paired"] = paired_delta(pool_games, base_games, _own)
            if pool_stats["slope_mean"] is not None and bp.get("slope_mean") is not None:
                gate["slope_delta"] = round(pool_stats["slope_mean"] - bp["slope_mean"], 1)
            # 強帯だけの対応付き差分(ベースライン側も同じ相手集合に絞る)
            if strong_games:
                base_strong = [g for g in base_games if g["opponent"] in strong_paths]
                gate["strong_margin_delta_paired"] = paired_delta(strong_games, base_strong, _margin)
                gate["strong_money_delta_paired"] = paired_delta(strong_games, base_strong, _own)
                if pool_stats["strong_slope_mean"] is not None and bp.get("strong_slope_mean") is not None:
                    gate["strong_slope_delta"] = round(
                        pool_stats["strong_slope_mean"] - bp["strong_slope_mean"], 1)
                elif bp.get("strong_slope_mean") is None:
                    gate["note"] = ((gate["note"] or "")
                                    + " ベースラインに strong_slope_mean が無い(旧形式)。強帯傾き差は判定不能")
            else:
                gate["note"] = (gate["note"] or "") + " プールに tier=strong が居ない(強帯指標なし)"
            rd = gate["rating_delta"]
            gd = gate["margin_delta_paired"]
            # rating が情報を持つ = **レーティング計算に寄与する相手（rating 付き）**のうち
            # 勝率が 0/100% に張り付いていない（勝敗が拮抗する）相手が 1 体でも居ること。
            # 全相手が 0/100% だと rating は候補を変えても動かない（2026-09-10 監査:
            # gen0024 以降 9 世代連続で pool.rating=631.6, rating_delta=0.0）。中間帯が入れば
            # 自動で有効になる。rating 入力に入らない相手（--opponents/--champion 等の未 rating
            # 相手）は rating_delta を動かさないので decisive に数えない（Codex 指摘 2026-09-10）。
            # knowledge/analysis/2026-09-10_metric-audit.md
            decisive = [v for v in summary.values()
                        if v.get("rating") is not None and v.get("games")
                        and 0.0 < v.get("win_rate", 0.0) < 1.0]
            gate["rating_informative"] = bool(decisive)
            # rating_delta の 95%CI: 候補とベースラインの rating_se を独立と見て伝播
            # （√(se_cand² + se_base²)×1.96）。2026-09-10 v0.6 でゲートに rating 経路を復活。
            cand_se = pool_stats.get("rating_se")
            base_se = bp.get("rating_se")
            if rd is not None and _pos_se(cand_se) and _pos_se(base_se):
                rd_se = math.sqrt(cand_se ** 2 + base_se ** 2)
                gate["rating_delta_ci"] = [round(rd - 1.96 * rd_se, 1),
                                           round(rd + 1.96 * rd_se, 1)]
            rd_ci = gate["rating_delta_ci"]
            # 昇格ゲート v0.6（2026-09-10。DIRECTIVES 2026-09-10 ★1）:
            #   pass = マージン経路 OR rating 経路
            #   マージン経路 = マージン（自分 − 相手）の CI 下限 > 0 … v0.5 のゲートそのまま。
            #     マージンは勝敗の定義（run_match.py の winner）なので原則 rating 条件を課さない。
            #     ただし rating が情報を持ち、かつ rating_delta の CI 上限 < 0（＝有意にレーティングが
            #     劣化）なら通さない。平均マージンは勝数と単調でなく、大敗を縮める代わりに僅差勝ちを
            #     複数落とす型は平均マージンが上がっても LB のスキルレートは下がるため（Codex 指摘
            #     2026-09-10。DIRECTIVES ★1 の素の OR に足した非対称ガード。異議は DIRECTIVES で veto）。
            #   rating 経路 = rating が情報を持つ かつ rating_delta の CI 下限 > 0
            #     かつ **マージン点推定 ≥ 0**（勝ち数は増えるがドルで負ける型を弾く非負ガード）。
            # 2026-09-05 にマージン一本化したのは二極プールで rating が無力だったからで、
            # プール改編（中間帯の新設）で rating_informative=True に戻ったため rating 経路を足した。
            # 実例: gen0051 は rating 4σ・マージン検出不能で、人が手で pass を上書きしないと
            # 昇格できなかった（knowledge/analysis/2026-09-10_metric-audit.md）。
            rating_degraded = bool(decisive and rd_ci is not None and rd_ci[1] < 0)
            margin_path = (gd is not None and gd["ci95"][0] > 0 and not rating_degraded)
            rating_path = bool(decisive and rd_ci is not None and rd_ci[0] > 0
                               and gd is not None and gd["mean"] >= 0)
            if not decisive:
                gate["note"] = ((gate["note"] or "")
                                + " プールの全相手が勝率 0/100% に張り付いており rating は情報を持たない"
                                  " → 昇格は rating 経路が無効（マージン経路のみ・診断値としては残す）")
            gate["pass"] = bool(gate["errors_zero"] and (margin_path or rating_path))
            gate["pass_route"] = (("margin" if margin_path else
                                   "rating" if rating_path else None)
                                  if gate["pass"] else None)
            gate["submit_ok"] = bool(gate["errors_zero"] and rd is not None and rd > -100)
            gate["too_good"] = too_good_flag(gate)
    else:
        st = summary.get("starter")
        gate["submit_ok"] = bool(gate["errors_zero"] and st and st["win_rate"] >= 0.95) if st else None
        gate["note"] = (gate["note"] or "") + " --baseline 未指定: 昇格判定不能"

    cand_path = Path(args.candidate)
    out = {
        "candidate": args.candidate,
        "candidate_sha256": hashlib.sha256(cand_path.read_bytes()).hexdigest()
        if cand_path.exists() else None,
        "pool_file": args.pool,
        "self_matches_excluded": list(self_matches),
        "pool_sha256": pool_sha256,
        "opponents": summary,
        "pool": pool_stats,
        "gate": gate,
        "seeds": args.seeds,
        "seed_base": args.seed_base,
        "steps": args.steps,
        "wall_seconds": wall_seconds,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "games": sorted(games, key=lambda g: (g["opponent"], g["seed"], g["cand_side"])),
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--pool", help="control/sparring_pool.json(相手と固定レーティング)")
    ap.add_argument("--opponents", default="", help="追加の相手(カンマ区切り, 組み込み名かパス)")
    ap.add_argument("--champion", help="現行王者のパス(参考値として対戦。ゲートには使わない)")
    ap.add_argument("--baseline", help="王者を同じプール・シードで評価した eval JSON(ゲートの比較対象)")
    ap.add_argument("--seeds", type=int, default=100, help="相手ごとのシード数(両側で2倍の試合数)")
    ap.add_argument("--seed-base", type=int, default=1000)
    ap.add_argument("--steps", type=int, default=720)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--out")
    ap.add_argument("--regate", metavar="EVAL_JSON",
                    help="試合を回さず、保存済み eval JSON の games からゲートだけ再計算する。"
                         "ゲートの定義を変えたときに過去の評価を測り直すための入口。"
                         "候補とプールの SHA が保存時と一致しなければ中止する(fail-closed)。")
    args = ap.parse_args()

    pool = load_pool(args.pool) if args.pool else []
    pool_sha256 = hashlib.sha256(Path(args.pool).read_bytes()).hexdigest() if args.pool else None
    pool_by_path = {e["path"]: e for e in pool}
    opponents = []
    for e in pool:
        opponents.append(e["path"])
    for o in args.opponents.split(","):
        o = o.strip()
        if o and o not in opponents:
            opponents.append(o)
    if args.champion and args.champion not in opponents:
        opponents.append(args.champion)
    if not opponents:
        sys.exit("相手がいない: --pool か --opponents を指定")

    # 自己対戦を外す（2026-09-10）。プールに自系統の世代を入れると、その世代自身を候補として
    # 評価したときにミラー戦が混ざる。**同一コードの対戦は勝率が構造上 ~50%・マージン ~0 に
    # なる**ので、その相手に負けているベースラインと比べると候補だけが不当に有利になり、
    # 昇格ゲートが壊れる（プールに gen0044/0045/0051 を入れる改編で実際に起きる）。
    # paired_delta は (相手, シード, 席) で対応付けるので、片方に無い相手は自然に対から落ちる
    # ＝ 比較は共通の相手集合の上で行われる。
    cand_resolved = str(Path(args.candidate))
    self_matches = [o for o in opponents if str(Path(o)) == cand_resolved]
    if self_matches:
        opponents = [o for o in opponents if str(Path(o)) != cand_resolved]
        print(f"  自己対戦を除外: {self_matches}（ミラー戦は勝率 ~50%/マージン ~0 で"
              f"ゲートを歪めるため）", file=sys.stderr)
        if not opponents:
            sys.exit("相手が自分だけになった: プールか --opponents を見直すこと")

    if args.regate:
        prev = json.loads(Path(args.regate).read_text())
        # fail-closed: 保存時と条件が違うなら再計算しない。games だけ流用して
        # 今の候補・今のプールの SHA を貼ると、中身と札が食い違った JSON ができる。
        cand_now = (hashlib.sha256(Path(args.candidate).read_bytes()).hexdigest()
                    if Path(args.candidate).exists() else None)
        if prev.get("candidate_sha256") != cand_now:
            sys.exit(f"--regate 中止: 候補の SHA が保存時と違う "
                     f"({prev.get('candidate_sha256')} != {cand_now})")
        if prev.get("pool_sha256") != pool_sha256:
            sys.exit(f"--regate 中止: プールの SHA が保存時と違う "
                     f"({prev.get('pool_sha256')} != {pool_sha256})")
        games = prev.get("games") or []
        if not games:
            sys.exit("--regate 中止: 保存済み JSON に games が無い")
        # シード条件は保存時のものを使う(CLI の既定値で上書きしない)。
        args.seeds, args.seed_base, args.steps = prev["seeds"], prev["seed_base"], prev["steps"]
        # baseline も保存時のものを復元する(CLI で明示指定が無ければ)。v0.6 の rating 経路は
        # baseline が無いと pass=None になるので、ゲート定義を変えて保存 games から同じ判定を
        # 再現する --regate の目的が baseline 抜けで壊れる(Codex 指摘 2026-09-10)。
        if not args.baseline:
            args.baseline = (prev.get("gate") or {}).get("baseline")
        opponents = [o for o in opponents if any(g["opponent"] == o for g in games)]
        wall_seconds = prev.get("wall_seconds")
        print(f"  regate: {args.regate} の {len(games)} 戦からゲートを再計算", file=sys.stderr)
    else:
        tasks = [
            (args.candidate, opp, args.seed_base + s, side, args.steps)
            for opp in opponents
            for s in range(args.seeds)
            for side in (0, 1)
        ]

        t0 = time.time()
        games = []
        with cf.ProcessPoolExecutor(max_workers=args.jobs) as ex:
            futs = [ex.submit(one_game, *t) for t in tasks]
            for i, fut in enumerate(cf.as_completed(futs), 1):
                games.append(fut.result())
                if i % 20 == 0 or i == len(futs):
                    print(f"  {i}/{len(futs)} games done", file=sys.stderr)
        wall_seconds = round(time.time() - t0, 1)

    out = summarize(games, opponents, pool, pool_by_path, pool_sha256, args, wall_seconds,
                    self_matches)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    view = {k: v for k, v in out.items() if k != "games"}
    print(json.dumps(view, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
