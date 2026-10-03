#!/usr/bin/env python
"""上位メタ（shared/top_meta の日次実測）と王者の「骨格・市場」ギャップを毎晩機械生成する。

目的: 22:00 に更新される `../shared/top_meta/LATEST.md`（LB 上位同士のリプレイ集計）を、夜間ループが
**自分の王者との差**として読めるようにする。人が読む表（LATEST.md）と同じ集計器（shared の
`extract_top.extract`）を王者のローカル対戦リプレイに当て、同じ物差しで並べる。

入力（すべて読み取り専用。shared には書かない）:
  ../shared/top_meta/state/features.json     上位リプレイの特徴量（extract_top.py の出力）
  ../shared/top_meta/state/lb_history/*.json  日ごとの LB 上位 50
  ../shared/top_meta/state/signatures.json    観測済みの d0 の型（初出日付き）
  ../shared/top_meta/LATEST.md                §7「解釈」が追記済みかの確認だけに使う
  replays/top/index.jsonl                     features.json に無い新着リプレイの補完用
  control/champion.json                       王者
出力:
  state/top_meta/gap_LATEST.md / gap_YYYY-MM-DD.md   人と夜間サイクルが読む表（80 行前後）
  state/top_meta/gap_LATEST.json                     ops/daily_report.py と翌夜の drift 判定が読む
  state/top_meta/gap_history.jsonl                   1 夜 1 行の推移
  records/top_meta/                                  王者の対戦リプレイと新着分の特徴量キャッシュ（gitignore）

usage:
  ops/top_meta_gap.py                      # 王者 vs 強帯最強（sparring_pool の rating 最大）を 6 seed で走らせて比較（~15 秒）
  ops/top_meta_gap.py --fresh              # 既存の王者リプレイを捨てて走らせ直す（王者が替わった夜は自動で走る）
  ops/top_meta_gap.py --replay a.json b.json --seat 0   # 手持ちのリプレイで比較（対戦は走らせない）
  ops/top_meta_gap.py --date 2026-09-08 --window-days 3
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import statistics as st
import subprocess
import sys
from collections import Counter, defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_shared():
    env = os.environ.get("KAGG_SHARED")
    if env:
        return Path(env)
    for p in [ROOT, *ROOT.parents]:
        cand = p / "shared" / "top_meta"
        if cand.is_dir():
            return p / "shared"
    return None


SHARED = find_shared()
TOP_META = SHARED / "top_meta" if SHARED else None
OUT_DIR = ROOT / "state" / "top_meta"
CACHE = ROOT / "records" / "top_meta"
INDEX = ROOT / "replays" / "top" / "index.jsonl"

ITEMS = ["MILK", "WOOL", "STRAWBERRY", "MELON", "FERTILIZER", "WHEAT", "CARROT", "EGG", "TOMATO"]
AB = {"FERTILIZER": "肥料", "WHEAT": "小麦", "WOOL": "羊毛", "MILK": "乳", "MELON": "メロン",
      "STRAWBERRY": "イチゴ", "EGG": "卵", "CARROT": "ニンジン", "TOMATO": "トマト"}
MILK_SHOPS = {"ICE_CREAM_SHOP", "PIZZA_SHOP", "SMOOTHIE_SHOP"}
EGG_SHOPS = {"BAKERY", "BRUNCH_SPOT"}
FAMB = "H5 C2 S2 G0 ME12"
FAMILY_LABEL = {FAMB: "B（主流）", "H4 C3 S2 G0 ME5": "A（Crop Dusta系）", "H7 C5 S1 G0 ME1": "H（牛5先行）",
                "H6 C2 S3 G0 ME2": "F（早期ニンジン）", "H6 C2 S3 G0 ME0": "F（早期ニンジン）",
                "H6 C3 S2 G0 ME0": "M（小麦大量）"}


# ---------------------------------------------------------------- helpers
def g(d, k, default=0):
    return d.get(str(k), d.get(k, default)) if isinstance(d, dict) else default


def med(xs):
    xs = [x for x in xs if x is not None]
    return st.median(xs) if xs else None


def fam(r):
    d0 = r["d0"]; a = d0["animals"]; s = d0["seeds"]
    return f"H{d0['hires']} C{a.get('COW',0)} S{a.get('SHEEP',0)} G{a.get('GOOSE',0)} ME{s.get('MELON',0)}"


def fam_label(f):
    return FAMILY_LABEL.get(f, f"新型 {f}")


def d0sig(r):
    d0 = r["d0"]; a = d0["animals"]; s = d0["seeds"]
    return (f"H{d0['hires']} C{a.get('COW',0)} S{a.get('SHEEP',0)} G{a.get('GOOSE',0)} | "
            f"ME{s.get('MELON',0)} WH{s.get('WHEAT',0)} ST{s.get('STRAWBERRY',0)} CA{s.get('CARROT',0)} TO{s.get('TOMATO',0)}")


def parse_day(s):
    return (s or "")[:10]


def import_extract():
    # shared には一切書かない: import で __pycache__ を作らせない（Pool の子プロセスにも環境変数で継承）
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.path.insert(0, str(TOP_META / "scripts"))
    os.environ.setdefault("KAGG_AGENT_LOOP", str(ROOT))
    from extract_top import extract  # noqa: E402
    return extract


# ---------------------------------------------------------------- inputs
def load_lb_history():
    """(latest_rows, latest_date, prev_rows, prev_date)。rows は rank 順。"""
    d = TOP_META / "state" / "lb_history"
    files = sorted(d.glob("*.json")) if d.is_dir() else []
    if not files:
        return [], None, [], None
    latest = json.loads(files[-1].read_text())
    prev = json.loads(files[-2].read_text()) if len(files) > 1 else []
    return latest, files[-1].stem, prev, (files[-2].stem if len(files) > 1 else None)


def enrich(rec, meta, lb_rows):
    m = meta.get(str(rec["episode"]))
    rec["team_id"] = None
    if m:
        rec["create_time"] = m.get("create_time")
        for tm in m["teams"]:
            if tm["index"] == rec["player"]:
                rec["lb_rank_at_fetch"] = tm.get("lb_rank")
                rec["submission_id"] = tm.get("submission_id")
                rec["team_id"] = tm.get("team_id")
    by_id = {r["team_id"]: r for r in lb_rows}
    by_name = {r["team"]: r for r in lb_rows}
    cur = by_id.get(rec["team_id"]) or by_name.get(rec["team"])
    rec["lb_rank_now"] = cur["rank"] if cur else None
    rec["team_now"] = cur["team"] if cur else rec["team"]
    return rec


def load_top_features(lb_rows, extract, jobs):
    """shared の features.json ＋ そこに無い新着リプレイ（ローカル抽出・キャッシュ）。"""
    feats = json.loads((TOP_META / "state" / "features.json").read_text())
    have = {r["file"] for r in feats}
    files = sorted((ROOT / "replays" / "top").glob("episode-*-replay.json"))
    missing = [p for p in files if p.name not in have]
    notes = []
    if not missing:
        return feats, notes
    # キャッシュはファイル名 → その試合の 2 レコード（両プレイヤー）
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_p = CACHE / "features_delta.json"
    cached = {}
    if cache_p.exists():
        try:
            for r in json.loads(cache_p.read_text()):
                cached.setdefault(r["file"], []).append(r)
        except (json.JSONDecodeError, KeyError):
            cached = {}
    todo = [str(p) for p in missing if p.name not in cached]
    if todo:
        with Pool(max(1, jobs)) as pool:
            results = pool.map(extract, todo)
        for recs in results:
            for r in recs:
                cached.setdefault(r["file"], []).append(r)
        cache_p.write_text(json.dumps([r for rs in cached.values() for r in rs], ensure_ascii=False))
    meta = {}
    if INDEX.exists():
        for line in INDEX.read_text().splitlines():
            try:
                m = json.loads(line)
                meta[str(m["episode_id"])] = m
            except (json.JSONDecodeError, KeyError):
                continue
    extra = [enrich(dict(r), meta, lb_rows) for p in missing for r in cached.get(p.name, [])]
    notes.append(f"shared の features.json に無い新着 {len(missing)} 試合をローカル抽出で補完（records/top_meta/）")
    return feats + extra, notes


def champion():
    c = json.loads((ROOT / "control" / "champion.json").read_text())
    return c["gen"]


def strongest_opponent():
    pool = json.loads((ROOT / "control" / "sparring_pool.json").read_text())
    cands = [o for o in pool["opponents"] if o.get("enabled") and o.get("tier") == "strong"]
    if not cands:
        cands = [o for o in pool["opponents"] if o.get("enabled") and o["name"] != "starter"]
    best = max(cands, key=lambda o: o.get("rating", 0))
    return best["name"], best["path"]


def own_replays(gen, opp_name, opp_path, seeds, fresh, seats=(0,)):
    """王者 vs 相手を seeds × seats で走らせ、(replay_path, my_index) のリストを返す（1 試合 ~2 秒）。
    ファイル名に main.py の SHA を含めるので、王者が替わると自動で走り直す。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256((ROOT / "agents" / gen / "main.py").read_bytes()).hexdigest()[:12]
    osha = hashlib.sha256((ROOT / opp_path).read_bytes()).hexdigest()[:8]  # 相手が更新されても古い対戦を再利用しない
    out = []
    for seed in seeds:
        for seat in seats:
            p = CACHE / f"{gen}_{sha}_vs_{opp_name}_{osha}_s{seed}_p{seat}.json"
            if fresh or not p.exists():
                a, b = (f"agents/{gen}/main.py", opp_path) if seat == 0 else (opp_path, f"agents/{gen}/main.py")
                r = subprocess.run([str(ROOT / ".venv/bin/python"), "harness/run_match.py", a, b, "--seed", str(seed),
                                    "--replay", str(p), "--quiet"], cwd=ROOT, capture_output=True, text=True, timeout=600)
                if r.returncode != 0 or not p.exists():
                    print(f"WARN: run_match failed seed={seed} seat={seat}: {r.stderr[-300:]}", file=sys.stderr)
                    continue
            out.append((p, seat))
    return out


# ---------------------------------------------------------------- metrics
def metrics(r):
    m = {}
    d0 = r["d0"]
    m["d0_hires"] = d0["hires"]
    m["d0_cow"] = d0["animals"].get("COW", 0)
    m["d0_sheep"] = d0["animals"].get("SHEEP", 0)
    m["d0_melon"] = d0["seeds"].get("MELON", 0)
    m["d0_wheat"] = d0["seeds"].get("WHEAT", 0)
    m["d0_feed"] = d0["products"].get("WHEAT", 0)
    m["money_d0"] = g(r["money_curve"], 0, None)
    for q in ("NE", "SW", "SE"):
        m[f"land_{q}"] = r["land"].get(q)
    for d in (6, 9, 12, 20):
        m[f"hires_d{d}"] = g(r["hires_by_day"], d)
    m["hires_max"] = max(r["hires_by_day"].values()) if r["hires_by_day"] else 0
    for a in ("COW", "SHEEP", "GOOSE"):
        for d in (5, 10):
            m[f"{a.lower()}_d{d}"] = g(r["animals_cum"], d, {}).get(a, 0)
        m[f"{a.lower()}_peak"] = r["peak_animals"].get(a, 0)
    for c, k in (("WHEAT", "WH"), ("MELON", "ME"), ("STRAWBERRY", "ST"), ("CARROT", "CA"), ("TOMATO", "TO")):
        m[f"seed_{k}"] = r["seed_total"].get(c, 0)
    for d in (10, 20, 27):
        t = g(r["tiles_eod"], d, {})
        m[f"tiles_ST_d{d}"] = t.get("STRAWBERRY", 0)
        m[f"tiles_WH_d{d}"] = t.get("WHEAT", 0)
    m["tiles_ME_d5"] = g(r["tiles_eod"], 5, {}).get("MELON", 0)
    m["tiles_CA_d27"] = g(r["tiles_eod"], 27, {}).get("CARROT", 0)
    m["weed_d28"] = g(r["tiles_eod"], 28, {}).get("WEED", 0)
    for it in ITEMS:
        m[f"first_{it}"] = r["first_sell"].get(it)
        q = r["sell_total_qty"].get(it, 0)
        m[f"qty_{it}"] = q
        m[f"rev_{it}"] = r["sell_total_rev"].get(it, 0)
        m[f"avg_{it}"] = (r["sell_total_rev"].get(it, 0) / q) if q else None
        m[f"floor_{it}"] = r["sell_floor_qty"].get(it, 0)
    m["rev_total"] = sum(r["sell_total_rev"].values())
    for d in (10, 15, 20, 25, 29):
        m[f"money_d{d}"] = g(r["money_curve"], d, None)
    m["final"] = r.get("final")
    wb = sum(v.get("WHEAT", 0) for v in r["buy_product_by_day"].values())
    wc = sum(v.get("WHEAT", 0) for v in r.get("buy_product_cost_by_day", {}).values())
    m["wheat_buy"] = wb
    m["wheat_buy_avg"] = (wc / wb) if wb and wc else None
    m["fertilizer_buy"] = sum(v.get("FERTILIZER", 0) for v in r["buy_product_by_day"].values())
    ut = max(1, r.get("unit_turns", 1))
    m["fertilize"] = r["verbs"].get("FERTILIZE", 0)
    m["pass_pct"] = 100.0 * r["verbs"].get("PASS", 0) / ut
    m["move_pct"] = 100.0 * r["verbs"].get("MOVE", 0) / ut
    m["unit_turns"] = ut
    m["shops3"] = [s for _, s in r["shops"]][:3]
    return m


def med_metrics(recs):
    ms = [metrics(r) for r in recs]
    out = {}
    keys = set(k for m in ms for k in m)
    for k in keys:
        if k == "shops3":
            continue
        out[k] = med([m.get(k) for m in ms])
    return out


ROWS = [  # (label, key, fmt, higher_is_better or None)
    ("d0 雇用", "d0_hires", "d", None), ("d0 牛", "d0_cow", "d", None), ("d0 羊", "d0_sheep", "d", None),
    ("d0 メロン種", "d0_melon", "d", None), ("d0 小麦種", "d0_wheat", "d", None), ("d0 飼料小麦", "d0_feed", "d", None),
    ("d0 日末資金", "money_d0", "$", False),
    ("NE 購入日", "land_NE", "d", False), ("SW 購入日", "land_SW", "d", False), ("SE 購入日", "land_SE", "d", None),
    ("雇用 d6/d9/d12/d20", ("hires_d6", "hires_d9", "hires_d12", "hires_d20"), "d", None),
    ("牛 d5/d10/ピーク", ("cow_d5", "cow_d10", "cow_peak"), "d", None),
    ("羊 d5/d10/ピーク", ("sheep_d5", "sheep_d10", "sheep_peak"), "d", None),
    ("ガチョウ ピーク", "goose_peak", "d", None),
    ("種 WH/ME/ST/CA/TO", ("seed_WH", "seed_ME", "seed_ST", "seed_CA", "seed_TO"), "d", None),
    ("メロン枚 d5", "tiles_ME_d5", "d", None),
    ("イチゴ枚 d10/d20/d27", ("tiles_ST_d10", "tiles_ST_d20", "tiles_ST_d27"), "d", None),
    ("小麦枚 d10/d20/d27", ("tiles_WH_d10", "tiles_WH_d20", "tiles_WH_d27"), "d", None),
    ("ニンジン枚 d27", "tiles_CA_d27", "d", True), ("雑草 d28", "weed_d28", "d", False),
    ("肥料 買戻し / FERTILIZE 回", ("fertilizer_buy", "fertilize"), "d", None),
    ("小麦 買 / 買値", ("wheat_buy", "wheat_buy_avg"), "d", None),
    ("PASS% / MOVE%", ("pass_pct", "move_pct"), ".0f", False),
    ("資金 d10/d15/d20/d25/d29", ("money_d10", "money_d15", "money_d20", "money_d25", "money_d29"), "$", True),
]


def fmt(v, f):
    if v is None:
        return "-"
    if f == "$":
        return f"${v:,.0f}"
    if f == "d":
        return f"{v:.0f}" if isinstance(v, float) else str(v)
    return format(v, f)


def cell(m, key, f):
    if isinstance(key, tuple):
        return "/".join(fmt(m.get(k), f) for k in key)
    return fmt(m.get(key), f)


def delta_cell(ours, top, key, f):
    if isinstance(key, tuple):
        parts = []
        for k in key:
            a, b = ours.get(k), top.get(k)
            parts.append("-" if a is None or b is None else fmt(a - b, f if f != "d" else "+.0f") if f != "$" else f"{a-b:+,.0f}")
        return "/".join(parts)
    a, b = ours.get(key), top.get(key)
    if a is None or b is None:
        return "-"
    return f"{a-b:+,.0f}" if f == "$" else f"{a-b:+.0f}"


# ---------------------------------------------------------------- report
def shop_counts(recs):
    """自分の各 seed の最初の 3 軒を YARN/乳店/卵店の件数に落とし、件数ごとの最頻値を返す（店列そのものの最頻は seed 順依存）。"""
    ys, ms, es = [], [], []
    for r in recs:
        s3 = [x for _, x in r["shops"]][:3]
        ys.append(s3.count("YARN_STORE")); ms.append(sum(x in MILK_SHOPS for x in s3)); es.append(sum(x in EGG_SHOPS for x in s3))
    if not ys:
        return None
    mode = lambda xs: Counter(xs).most_common(1)[0][0]
    return {"yarn": mode(ys), "milk": mode(ms), "egg": mode(es), "n": len(ys),
            "dist": {"yarn": dict(Counter(ys)), "milk": dict(Counter(ms)), "egg": dict(Counter(es))}}


def questions(ours, top, ours_shops, allB):
    """今夜の問い（$ 換算で大きい順）。表からの機械的な抽出で、解釈はしない。"""
    qs = []
    # 1. 品目別の売上ギャップ（量 × 単価に分解）
    gaps = []
    for it in ITEMS:
        a, b = ours.get(f"rev_{it}") or 0, top.get(f"rev_{it}") or 0
        if b - a > 500:
            gaps.append((b - a, it))
    for gap, it in sorted(gaps, reverse=True)[:3]:
        qs.append((gap, f"{AB[it]}の売上が上位中央値より ${gap:,.0f} 少ない"
                        f"（個数 {fmt(ours.get(f'qty_{it}'),'d')} vs {fmt(top.get(f'qty_{it}'),'d')}・"
                        f"平均単価 {fmt(ours.get(f'avg_{it}'),'$')} vs {fmt(top.get(f'avg_{it}'),'$')}・"
                        f"初売り d{fmt(ours.get(f'first_{it}'),'d')} vs d{fmt(top.get(f'first_{it}'),'d')}）。量と単価のどちらか"))
    # 2. 資金曲線の遅れ始め
    for d in (10, 15, 20, 25):
        a, b = ours.get(f"money_d{d}"), top.get(f"money_d{d}")
        if a is not None and b:
            if a / b < 0.8:
                qs.append((b - a, f"資金が d{d} で上位の {a/b:.0%}（${a:,.0f} vs ${b:,.0f}）。ここで何が違うか"))
                break
            if a / b > 1.5 and d <= 10:
                qs.append((a - b, f"d{d} の現金が上位の {a/b:.1f} 倍（${a:,.0f} vs ${b:,.0f}）＝再投資が遅い疑い"))
    # 3. 初売りの遅れ
    for it in ("MILK", "WOOL", "STRAWBERRY", "FERTILIZER"):
        a, b = ours.get(f"first_{it}"), top.get(f"first_{it}")
        if a is not None and b is not None and a - b >= 2:
            qs.append((300 * (a - b), f"{AB[it]}の初売りが d{a:.0f}（上位 d{b:.0f}）。{a-b:.0f} 日遅い"))
    # 4. 床値売り
    for it in ("MILK", "WOOL", "STRAWBERRY"):
        a, b = ours.get(f"floor_{it}") or 0, top.get(f"floor_{it}") or 0
        if a - b >= 10:
            qs.append((50 * (a - b), f"{AB[it]}を床値（≤$5）で {a:.0f} 個売っている（上位中央値 {b:.0f}）"))
    # 5. 店分岐（我々の最初の 3 軒で上位 B 型が取った頭数）
    if ours_shops and allB:
        y, mk, eg = ours_shops["yarn"], ours_shops["milk"], ours_shops["egg"]
        def cond_med(cond, animal):
            xs = [r["peak_animals"].get(animal, 0) for r in allB if cond([s for _, s in r["shops"]][:3])]
            return med(xs), len(xs)
        sh, n1 = cond_med(lambda s: s.count("YARN_STORE") == y, "SHEEP")
        co, n2 = cond_med(lambda s: sum(x in MILK_SHOPS for x in s) == mk, "COW")
        go, n3 = cond_med(lambda s: sum(x in EGG_SHOPS for x in s) == eg, "GOOSE")
        qs.append((0, f"店分岐: 我々の {ours_shops['n']} seed の最初の 3 軒の最頻（YARN {y}・乳店 {mk}・卵店 {eg}。分布 {ours_shops['dist']}）で上位 B 型は "
                      f"羊 {fmt(sh,'d')}（n={n1}）/ 牛 {fmt(co,'d')}（n={n2}）/ ガチョウ {fmt(go,'d')}（n={n3}）。"
                      f"我々は羊 {fmt(ours.get('sheep_peak'),'d')} / 牛 {fmt(ours.get('cow_peak'),'d')} / ガチョウ {fmt(ours.get('goose_peak'),'d')}"))
    qs.sort(key=lambda x: -x[0])
    ranked = [q for w, q in qs if w > 0]
    shop = [q for w, q in qs if w == 0]
    return ranked[:5] + shop


def drift(top, prev_top):
    """前夜の gap_LATEST.json の上位中央値からの変化（骨格が動いたか）。"""
    if not prev_top:
        return []
    rules = [("land_NE", 1, "NE 購入日"), ("land_SW", 1, "SW 購入日"), ("cow_peak", 1, "牛ピーク"), ("sheep_peak", 1, "羊ピーク"),
             ("goose_peak", 1, "ガチョウピーク"), ("seed_ST", 5, "イチゴ種"), ("seed_CA", 10, "ニンジン種"), ("hires_max", 1, "雇用上限"),
             ("first_STRAWBERRY", 1, "イチゴ初売り"), ("first_MILK", 1, "乳初売り"), ("d0_melon", 2, "d0 メロン種"),
             ("tiles_CA_d27", 4, "d27 ニンジン枚")]
    out = []
    for k, tol, label in rules:
        a, b = top.get(k), prev_top.get(k)
        if a is None or b is None:
            continue
        if abs(a - b) > tol:
            out.append(f"{label} {b:.0f} → {a:.0f}")
    for d in (20, 29):
        a, b = top.get(f"money_d{d}"), prev_top.get(f"money_d{d}")
        if a and b and abs(a / b - 1) > 0.10:
            out.append(f"資金 d{d} ${b:,.0f} → ${a:,.0f}")
    return out


def build(date, window_days, feats, lb, lb_date, prev_lb, prev_lb_date, own_recs, gen, opp_name, notes, prev_json):
    cutoff = (dt.date.fromisoformat(date) - dt.timedelta(days=window_days)).isoformat()
    recent = [r for r in feats if parse_day(r.get("create_time")) >= cutoff]
    if len(recent) < 20:
        recent = feats
    top20 = {r["team_id"] for r in lb[:20]}
    top_all = [r for r in recent if r.get("team_id") in top20] or recent
    famB_top = [r for r in top_all if fam(r) == FAMB] or [r for r in recent if fam(r) == FAMB]
    winners = [r for r in top_all if r.get("win")]
    allB = [r for r in feats if fam(r) == FAMB]
    topB = med_metrics(famB_top)
    topW = med_metrics(winners) if winners else {}
    ours = med_metrics(own_recs)
    ours_shops = shop_counts(own_recs)

    # 新着
    sigs = json.loads((TOP_META / "state" / "signatures.json").read_text()) if (TOP_META / "state" / "signatures.json").exists() else {}
    new_sigs = [(s, v) for s, v in sigs.items() if v.get("first_seen") == date]
    bydate = defaultdict(Counter)
    for r in feats:
        bydate[parse_day(r.get("create_time"))][fam_label(fam(r))] += 1
    prev_ids = {r["team_id"] for r in prev_lb[:20]} if prev_lb else set()
    entrants = [r for r in lb[:20] if prev_lb and r["team_id"] not in prev_ids]
    dropped = [r for r in (prev_lb[:20] if prev_lb else []) if r["team_id"] not in top20]
    nonB = defaultdict(list)
    for r in top_all:
        if fam(r) != FAMB:
            nonB[(r.get("team_now"), fam_label(fam(r)))].append(r)
    latest_md = (TOP_META / "LATEST.md").read_text() if (TOP_META / "LATEST.md").exists() else ""
    interp = "追記済み" if latest_md and "（未追記）" not in latest_md else "未追記"
    drifts = drift(topB, (prev_json or {}).get("top_B"))

    L = []
    L.append(f"# 上位メタとの差 {date}（王者 {gen} vs {opp_name}、上位 B 型 {len(famB_top)} 記録の中央値）")
    L.append("")
    L.append(f"- 生成: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} ／ LB: {lb_date or '不明'}（前回 {prev_lb_date or 'なし'}）／ "
             f"集計窓 {window_days} 日・Top20 の記録 {len(top_all)}（勝者 {len(winners)}）／ shared LATEST.md §7 解釈: **{interp}**")
    L.append(f"- 王者側: `records/top_meta/` の {len(own_recs)} 記録（seed ごと）の中央値。**相手が強帯 1 体なので上位同士の共有市場より甘い。"
             f"骨格（日付・枚数・頭数）は比較してよいが、資金・単価は参考値**。集計器は shared の `extract_top.extract`（同じ物差し）。")
    for n in notes:
        L.append(f"- {n}")
    L.append("")
    L.append("## 1. 新着（今夜だけ見ればよい変化）")
    L.append("")
    L.append(f"- 初めて観測した d0 の型: " + ("、".join(f"`{s}`（{', '.join(v.get('teams', [])[:4])}）" for s, v in new_sigs) if new_sigs else "なし"))
    L.append(f"- Top20 入り: " + ("、".join(f"#{r['rank']} {r['team']}" for r in entrants) if entrants else "なし")
             + " ／ Top20 落ち: " + ("、".join(f"{r['team']}（前 #{r['rank']}）" for r in dropped) if dropped else "なし"))
    L.append("- 型シェア（記録数・直近 3 日）: " + " ／ ".join(f"{d}: " + ", ".join(f"{k} {v}" for k, v in c.most_common(4)) for d, c in sorted(bydate.items())[-3:]))
    if nonB:
        L.append("- Top20 の非主流型: " + "、".join(f"{t}〔{f}〕{sum(1 for r in rs if r.get('win'))}/{len(rs)} 勝・${med([r['final'] for r in rs]):,.0f}"
                                          for (t, f), rs in sorted(nonB.items(), key=lambda kv: -len(kv[1]))[:6]))
    L.append("- 上位 B 型骨格の前夜からの drift: " + ("、".join(drifts) if drifts else ("なし" if prev_json else "（初回）")))
    L.append("")
    L.append("## 2. 骨格ギャップ（我々 − 上位 B 型中央値）")
    L.append("")
    L.append("| 項目 | 我々（王者） | 上位 B 型 | 上位の勝者 | Δ 我々−B |")
    L.append("| --- | --- | --- | --- | --- |")
    for label, key, f, _ in ROWS:
        L.append(f"| {label} | {cell(ours, key, f)} | {cell(topB, key, f)} | {cell(topW, key, f)} | {delta_cell(ours, topB, key, f)} |")
    L.append("")
    L.append("## 3. 市場ギャップ（品目別: 個数 / 平均単価 / 初売り / 床値売り）")
    L.append("")
    L.append("| 品目 | 我々 個数/単価/初売/床値 | 上位 B 型 | 上位の勝者 | 売上 Δ 我々−B |")
    L.append("| --- | --- | --- | --- | --- |")
    for it in ITEMS:
        def c4(m):
            return f"{fmt(m.get(f'qty_{it}'),'d')} / {fmt(m.get(f'avg_{it}'),'$')} / d{fmt(m.get(f'first_{it}'),'d')} / {fmt(m.get(f'floor_{it}'),'d')}"
        a, b = ours.get(f"rev_{it}"), topB.get(f"rev_{it}")
        dl = f"{a-b:+,.0f}" if a is not None and b is not None else "-"
        L.append(f"| {AB[it]} | {c4(ours)} | {c4(topB)} | {c4(topW)} | {dl} |")
    L.append(f"| **合計売上** | {fmt(ours.get('rev_total'),'$')} | {fmt(topB.get('rev_total'),'$')} | {fmt(topW.get('rev_total'),'$')} | "
             f"{(ours.get('rev_total') or 0)-(topB.get('rev_total') or 0):+,.0f} |")
    L.append("")
    L.append("## 4. 今夜の問い（表からの機械抽出。$ の大きい順。解釈は cycle1 が STATUS に書く）")
    L.append("")
    qs = questions(ours, topB, ours_shops, allB)
    for i, q in enumerate(qs, 1):
        L.append(f"{i}. {q}")
    if not qs:
        L.append("（差が閾値未満）")
    L.append("")
    L.append("読み方: 上位の数字は `../shared/top_meta/LATEST.md`（§3 骨格・§5 ミラー戦の勝敗要因・§6 店分岐）と同じ集計。"
             "跳躍候補との対応は `knowledge/scout/2026-09-07_breakthrough-candidates-from-shared.md` §6。")
    text = "\n".join(L) + "\n"
    js = {"date": date, "champion": gen, "opponent": opp_name, "n_topB": len(famB_top), "n_top": len(top_all),
          "n_own": len(own_recs), "ours": ours, "top_B": topB, "top_winners": topW, "questions": qs,
          "new_signatures": [s for s, _ in new_sigs], "entrants": [r["team"] for r in entrants],
          "drift": drifts, "interpretation": interp, "own_shops": ours_shops}
    return text, js


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--date", default=dt.date.today().isoformat())
    ap.add_argument("--window-days", type=int, default=3)
    ap.add_argument("--seeds", default="7,14,42,100,2024,4200", help="王者の対戦シード")
    ap.add_argument("--both-seats", action="store_true",
                    help="両席で走らせる。既定は席 0 だけ（エンジンは両者を同じ pre-commit 在庫で清算するので席を入れ替えても"
                         "資金は 1 ドルも動かない。2026-09-07 に 3 seed で実測、公開報告 #731152 とも一致）")
    ap.add_argument("--opp", help="相手（sparring_pool の name）。既定は強帯の rating 最大")
    ap.add_argument("--replay", nargs="*", help="手持ちのリプレイで比較（対戦しない）。--seat で自分の席")
    ap.add_argument("--seat", type=int, default=0)
    ap.add_argument("--fresh", action="store_true", help="王者リプレイを走らせ直す")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--no-write", action="store_true", help="標準出力に出すだけ")
    args = ap.parse_args()

    if TOP_META is None or not (TOP_META / "state" / "features.json").exists():
        print("NG: ../shared/top_meta/state/features.json が見つからない（shared/top_meta の run_daily.sh が未実行）", file=sys.stderr)
        return 2
    extract = import_extract()
    lb, lb_date, prev_lb, prev_lb_date = load_lb_history()
    feats, notes = load_top_features(lb, extract, args.jobs)
    gen = champion()
    if args.replay:
        pairs = [(Path(p), args.seat) for p in args.replay]
        opp_name = "manual"
    else:
        if args.opp:
            pool = json.loads((ROOT / "control" / "sparring_pool.json").read_text())
            o = next(o for o in pool["opponents"] if o["name"] == args.opp)
            opp_name, opp_path = o["name"], o["path"]
        else:
            opp_name, opp_path = strongest_opponent()
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        pairs = own_replays(gen, opp_name, opp_path, seeds, args.fresh, (0, 1) if args.both_seats else (0,))
    own_recs = []
    for p, seat in pairs:
        try:
            recs = extract(str(p))
        except Exception as e:  # noqa: BLE001
            print(f"WARN: extract failed {p.name}: {type(e).__name__}: {e}", file=sys.stderr)
            continue
        own_recs.extend(r for r in recs if r["player"] == seat)
    if not own_recs:
        print("NG: 王者のリプレイが 1 件も読めない", file=sys.stderr)
        return 2
    prev_json = None
    if (OUT_DIR / "gap_LATEST.json").exists():
        try:
            prev_json = json.loads((OUT_DIR / "gap_LATEST.json").read_text())
            if prev_json.get("date") == args.date:
                # 同じ日の再実行では前夜の値を drift の基準にする
                prev_json = prev_json.get("prev_for_drift") or None
        except json.JSONDecodeError:
            prev_json = None
    text, js = build(args.date, args.window_days, feats, lb, lb_date, prev_lb, prev_lb_date, own_recs, gen, opp_name, notes, prev_json)
    if args.no_write:
        print(text)
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"gap_{args.date}.md").write_text(text)
    (OUT_DIR / "gap_LATEST.md").write_text(text)
    js["prev_for_drift"] = {"date": prev_json.get("date"), "top_B": prev_json.get("top_B")} if prev_json else None
    (OUT_DIR / "gap_LATEST.json").write_text(json.dumps(js, ensure_ascii=False, indent=1))
    hist = {"date": args.date, "champion": gen, "opponent": opp_name, "n_topB": js["n_topB"],
            **{f"ours_{k}": js["ours"].get(k) for k in ("money_d10", "money_d20", "money_d29", "rev_total", "first_STRAWBERRY", "first_MILK")},
            **{f"top_{k}": js["top_B"].get(k) for k in ("money_d10", "money_d20", "money_d29", "rev_total", "first_STRAWBERRY", "first_MILK", "seed_ST", "cow_peak", "sheep_peak")},
            "new_signatures": js["new_signatures"], "drift": js["drift"]}
    hp = OUT_DIR / "gap_history.jsonl"   # 1 夜 1 行: 同じ日付の行があれば置換（同日再実行で重複させない）
    rows = [l for l in hp.read_text().splitlines() if l.strip()] if hp.exists() else []
    rows = [l for l in rows if json.loads(l).get("date") != args.date]
    rows.append(json.dumps(hist, ensure_ascii=False))
    hp.write_text("\n".join(rows) + "\n")
    print(f"wrote {OUT_DIR / f'gap_{args.date}.md'} ({len(text.splitlines())} lines), gap_LATEST.md/json, gap_history.jsonl")
    for q in js["questions"][:3]:
        print("  - " + q)
    return 0


if __name__ == "__main__":
    sys.exit(main())
