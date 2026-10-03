#!/usr/bin/env python
"""Track 2b（トマト）の設計可否のための実測。既存リプレイだけを読む（新規対戦 0 戦）。

出すもの:
  §1 トマト市場の在庫の向き（I0 − inventory）と価格
  §2 **約定量の保存則による確認**: sells = final_inv − I0 + 町の累積消費
     （トマトは `BUY_PRODUCT` できないので買い戻し項が無い: kaggriculture.py:598）
  §3 SE クアドラントの解禁率（= 新しい土地がいつ手に入るか）
  §4 **本当に空いたままのタイル**（トマトの占有に耐える連続空き）と、engine の価格式で見た売上上限

使い方:
  .venv/bin/python knowledge/analysis/2026-09-20_tomato_market.py              # 既定の 30 本
  .venv/bin/python knowledge/analysis/2026-09-20_tomato_market.py records/xx.json ...
"""
import glob
import json
import math
import os
import sys

I0_DEFAULT = 10000
SIZE = 10
SE_ORIGIN = (5, 5)
# kaggriculture.py の SHOPS / TOWN_CENTER_PRODUCTS より（トマトを消費する店だけ）
TOMATO_SHOPS = {"PIZZA_SHOP": 1, "FARMERS_MARKET": 1}  # 単品店なら 2x だがトマトの単品店は無い
# MARKET_PARAMS["TOMATO"]
TOM = {"base": 60, "I0": 10000, "T": 200, "below_target": 0.40, "above_target": 0.60}

DEFAULT_PATTERNS = [
    "records/cal_*.json",
    "records/di58_*_replay.json",
    "records/di59_*_replay.json",
    "records/t2a_6[02]_*_replay.json",
]


def tomato_price(inv):
    """kaggriculture.py の market_price を TOMATO のパラメータで再現（below=hinge / above=sqrt）。"""
    x = TOM["I0"] - inv
    T = TOM["T"]
    if x >= 0:  # 品薄側: hinge
        u = x / T
        f = u + 8.0 * max(0.0, u - 1.0) ** 2
        return max(1.0, round(TOM["base"] * (1.0 + TOM["below_target"] * f)))
    u = -x / T  # 供給過多側: sqrt
    return max(1.0, round(TOM["base"] * (1.0 - TOM["above_target"] * math.sqrt(u))))


def cellkind(c):
    if c is None:
        return "EMPTY"
    if isinstance(c, str):
        return c  # "LOCKED"
    return c.get("crop") or c.get("kind")


def scan(path):
    d = json.load(open(path))
    steps = d["steps"]
    cfg = d.get("configuration", {}) or {}
    shop_interval = max(1, int(cfg.get("townShopSellInterval", 4) or 4))
    center_interval = max(1, int(cfg.get("townCenterSellInterval", 24) or 24))
    params = (cfg.get("marketParams") or {})
    r = {"file": os.path.basename(path), "params_override": bool(params), "day_inv": {}, "day_price": {},
         "se_day": None, "free": {}, "consumed": 0, "orders": {0: {}, 1: {}}, "shops_final": []}
    i0 = int((params.get("TOMATO") or {}).get("I0", I0_DEFAULT))
    r["i0"] = i0
    for step_idx, st in enumerate(steps):
        o = st[0]["observation"]
        day, hour = o["day"], o["hour"]
        inv = o["market"]["inventory"]["TOMATO"]
        r["day_inv"][day] = inv
        r["day_price"][day] = o["market"]["prices"]["TOMATO"]
        shops = o["town"]["unlocked_shops"]
        r["shops_final"] = shops
        # 町の消費（engine: step % interval == 0 のときに、観測時点の店構成で消費する）
        if step_idx % shop_interval == 0:
            r["consumed"] += sum(TOMATO_SHOPS.get(s, 0) for s in shops)
        if step_idx % center_interval == 0:
            r["consumed"] += 1  # town center は全品目 1 個
        farm = o["farms"][0]
        if r["se_day"] is None and "SE" in farm["unlocked_quadrants"]:
            r["se_day"] = day
        if hour == 0:
            t = farm["tiles"]
            for y in range(SIZE):
                for x in range(SIZE):
                    if cellkind(t[y][x]) == "EMPTY":
                        r["free"].setdefault((x, y), set()).add(day)
        for p in (0, 1):
            act = st[p].get("action") or {}
            for order in (act.get("market") or [])[:10]:  # engine は先頭 10 件しか処理しない
                if isinstance(order, (list, tuple)) and len(order) >= 2 and order[1] == "TOMATO":
                    q = order[2] if len(order) > 2 else 1
                    r["orders"][p][order[0]] = r["orders"][p].get(order[0], 0) + q
    r["last_day"] = max(r["day_inv"])
    return r


def tomato_slots(free, last_day=29):
    """トマトを植えても何も押しのけないタイル ＝ 植付日 P から収穫終わりまで一度も塞がらないタイル。

    トマトは age 8-11 に 1 日 1 回（肥料が有効なら 2 個）産む（kaggriculture.py:10 / :789）。
    P+8+k <= last_day となる k の個数が収穫回数。**最も早い P を採る**（＝収穫回数の上限）。
    """
    best = {}
    for (x, y), ds in free.items():
        for P in range(12, 22):
            span = range(P, min(P + 11, last_day) + 1)
            if all(dd in ds for dd in span):
                harv = sum(1 for k in range(4) if P + 8 + k <= last_day)
                if harv:
                    best[(x, y)] = (harv, P)
                break
    return best


def sell_revenue(inv_start, units):
    """在庫 inv_start の市場に units 個を 1 個ずつ流したときの売上（engine と同じ逐次値付け）。"""
    total, inv = 0.0, inv_start
    for _ in range(units):
        total += tomato_price(inv)
        inv += 1
    return total, inv


def main():
    pats = sys.argv[1:] or DEFAULT_PATTERNS
    files = []
    for p in pats:
        files += sorted(glob.glob(p))
    rows = [scan(f) for f in files]
    print(f"# 対象 {len(rows)} 本\n")

    print("## §1 在庫の向き（I0 − inventory。正 = 町が吸った＝品薄側）と価格")
    print("| 試合 | トマト店数(末) | d10 | d20 | 末日 | 価格(末/最安) |")
    print("| --- | --- | --- | --- | --- | --- |")
    for r in rows:
        g = lambda d: (r["i0"] - r["day_inv"][d]) if d in r["day_inv"] else None
        ps = [v for v in r["day_price"].values() if v]
        n = sum(TOMATO_SHOPS.get(s, 0) for s in r["shops_final"])
        print(f"| {r['file'][:33]} | {n} | {g(10)} | {g(20)} | **{g(r['last_day'])}** | ${r['day_price'][r['last_day']]} / ${min(ps)} |")

    print("\n## §2 約定量（保存則）: sells = final_inv − I0 + 町の累積消費")
    print("**トマトは `BUY_PRODUCT` できない**（kaggriculture.py:598）ので買い戻し項が無く、両者の売却合計が一意に決まる。")
    print("| 試合 | 町の累積消費 | I0 − 末日在庫 | **約定合計** | 発注量(P0/P1) |")
    print("| --- | --- | --- | --- | --- |")
    bad = 0
    for r in rows:
        gap = r["i0"] - r["day_inv"][r["last_day"]]
        sells = gap * -1 + r["consumed"]  # = final_inv - I0 + consumed
        bad += sells != 0
        o0 = r["orders"][0].get("SELL", 0)
        o1 = r["orders"][1].get("SELL", 0)
        print(f"| {r['file'][:33]} | {r['consumed']} | {gap} | **{sells}** | {o0} / {o1} |")
    print(f"\n約定が 0 でない試合: **{bad} / {len(rows)}**（発注量は約定量ではない。7turn の `SELL TOMATO 6000` は在庫 0 で 0 個）")

    print("\n## §3 SE クアドラント（新しい土地）の解禁")
    fired = [r for r in rows if r["se_day"] is not None]
    print(f"- 解禁 **{len(fired)} / {len(rows)}**: " + ", ".join(f"{r['file'][:24]}(d{r['se_day']})" for r in fired))

    print("\n## §4 本当に空いたままのタイル（＝何も押しのけずにトマトを植えられる枚数）と売上上限")
    print("| 試合 | 枚数 | 肥料あり個数 | 植付日の内訳 | 売上(末日在庫に流す) |")
    print("| --- | --- | --- | --- | --- |")
    for r in rows:
        best = tomato_slots(r["free"], r["last_day"])
        units = sum(h * 2 for h, _ in best.values())
        byP = {}
        for h, P in best.values():
            byP[P] = byP.get(P, 0) + 1
        rev, _ = sell_revenue(r["day_inv"][r["last_day"]], units)
        print(f"| {r['file'][:33]} | {len(best)} | {units} | {dict(sorted(byP.items()))} | ${rev:,.0f} |")
    print("\n注: §4 の売上は**末日の在庫に全量を流した場合**の上限（実際は d28-29 に分かれるので概ねこの前後）。")
    print("種 $50/枚・肥料 $95 前後/枚（肥料は施肥日を含む 3 日だけ有効: kaggriculture.py:475）を引くこと。")


if __name__ == "__main__":
    main()
