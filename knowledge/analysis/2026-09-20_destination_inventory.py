#!/usr/bin/env python
"""行き先の在庫（destination inventory）: 遊休 1 unit-hour あたり、同時刻・到達圏内に
**誰も手を付けていない生産行動**が何件あったかを数える。

背景（2026-09-19 夜の 3 実験。`state/STATUS.md` cycle7 / cycle8）:
  - futile MOVE を消すと 100% が PASS に化ける
  - PASS を消すと 2/3 が通勤 MOVE に化ける
  - 一括 PICKUP を消すと fallback 先が元より悪くなりうる
→ 仮説「律速は『無駄の量』ではなく『浮いた時間の行き先に価値ある仕事があるか』」。
本スクリプトはその「行き先の在庫」を盤面から数える。`2026-09-19_move-budget.py` の
board_work / busy / 到達可能性の式をそのまま引き継ぐ（元ファイルは変更しない）。

--------------------------------------------------------------------------
定義（すべて observation から曖昧さなく決まる。エージェントの自己申告に依存しない）
--------------------------------------------------------------------------
* 1 unit-hour = 1 ユニット(farmer + hands)の 1 時間の行動。
  「d 日 h 時の行動」は steps[d*24+h+1]["action"]、盤面は steps[d*24+h]["observation"]。
* **遊休 unit-hour** = 行動が PASS または MOVE(NORTH/SOUTH/EAST/WEST) の unit-hour。
  すべての MOVE は `2026-09-19_move-budget.py` の「MOVE 区間」に属する（区間 = 同じ
  ユニットの同じ日の連続 MOVE）ので、「PASS の unit-hour ＋ 通勤 MOVE の unit-hour」
  ＝「生産行動でない unit-hour」と一致する。内訳は PASS / MOVE 別にも出す。
* **到達圏内** = manhattan 距離 d の仕事について `d + 1 <= 24 - hour`。
  時刻 hour のユニットは h..23 の 24-hour 手打てるので、歩いて d 手 + 実行 1 手が収まる。
  （`2026-09-19_move-budget.py` の cycle6 修正と同じ式。agent 側の `_owner_can_come` /
  到達可能性ゲートと同じ。）
* **誰も手を付けていない** = その (day, hour) に、そのタイル上で非 MOVE・非 PASS の
  行動が打たれていない（`busy` セット。元スクリプトと同じ定義）。
* **持ち物の実行可能性**: FEED は WHEAT を、FERTILIZE は FERTILIZER を、PLACE は動物を
  そのユニットが持っていなければ「そのユニットにできる仕事」ではないので数えない。
* **行き先の帰属（fate）**: 数えた仕事は、その日のうちに誰の手で実行されたかで 3 つに割る。
  - `self`  … **その遊休ユニット自身**が同じ日のうちに同じ op を実行した ＝ 今まさに歩いて
              向かっている先。「浮いた時間の行き先」としては**新規の仕事ではない**。
  - `other` … 同じ日のうちに**別のユニット**が実行した ＝ 割当・時刻の問題（9/19 §5 と同じ現象）。
  - `never` … その日は誰も実行しなかった ＝ 純粋な余剰容量。
  `strict` 系の数え方は `self` を除く（= 自分の目的地を「行き先の在庫」に数えない）。
* **(i) / (ii) の切り分け**: その (day, hour) にエージェントが実際に生成した todo 一覧を
  取り、盤面仕事 (kind, x, y) に対応する op が todo に **在る** なら (i)（＝ todo には
  載っているのに、この遊休ユニットには割り当たらなかった ＝ 割当の問題）、**無い** なら
  (ii)（＝ そもそも候補に挙がらない ＝ 骨格の問題）。
  todo 一覧は**エージェント本体を実際に走らせて取る**（再実装しない）:
  `agents/genNNNN/main.py` の `_agent()` 内、`    claimed = set()`（gen0058:1062 /
  gen0059:1120）の直前に `globals()['_TODO_SNAP'] = list(todos)` を差し込んだコピーを
  メモリ上に作り、`_agent(obs)` を呼ぶ。todo への append はすべてこの行より上で終わる
  （gen0058 最終 append は 917 行、gen0059 は 936 行）ので、この時点の `todos` が
  そのターンの完全な候補集合である。`--verify` で、再実行した行動がリプレイの行動と
  一致するか（= 決定論と観測の完全性）を確認できる。

盤面仕事の列挙 `board_work()`:
  base（2026-09-19 スクリプトと同一）
    PLANTABLE(空きタイル・種在庫>0) / FEEDABLE / CAREABLE / HARVEST_ANIMAL /
    WATERABLE / HARVEST_PLANT / DIGGABLE(雑草) / PLACEABLE(空きパスチャ・動物所持)
  ext（本スクリプトの追加。2026-09-20。集計では base と分けて出せる）
    FERTILIZABLE(イチゴで `fertilized_until_day < day`・day<29) /
    COLLECTABLE(動物タイルの `fertilizer_available`)

使い方:
  .venv/bin/python knowledge/analysis/2026-09-20_destination_inventory.py \
      --replay records/di58_7turn_s7_replay.json --agent agents/gen0058/main.py \
      --gen gen0058 --opp 7turn --seed 7 --out records/di_inv_58_7turn_s7.json
  # 12 本まとめて:
  .venv/bin/python knowledge/analysis/2026-09-20_destination_inventory.py --all
  # 集計だけ:
  .venv/bin/python knowledge/analysis/2026-09-20_destination_inventory.py --report records/di_inv_*.json
"""
import argparse
import collections
import glob
import json
import os
import sys
import types

MOVES = {"NORTH", "SOUTH", "EAST", "WEST"}
SHED = {(4, 4), (5, 4), (4, 5), (5, 5)}
CROPS_FIRST_YIELD = {"WHEAT": 2, "CARROT": 2, "TOMATO": 8, "STRAWBERRY": 10, "MELON": 10}
ANIMAL_ITEMS = ("COW", "SHEEP", "GOOSE")
FINAL_DAY = 29

# 盤面仕事の kind -> エージェントの todo の op[0]
KIND_OP = {
    "PLANTABLE": "PLANT",
    "FEEDABLE": "FEED",
    "CAREABLE": "CARE",
    "HARVEST_ANIMAL": "HARVEST",
    "WATERABLE": "WATER",
    "HARVEST_PLANT": "HARVEST",
    "DIGGABLE": "DIG",
    "PLACEABLE": "PLACE",
    "FERTILIZABLE": "FERTILIZE",
    "COLLECTABLE": "COLLECT_FERTILIZER",
}
BASE_KINDS = {"PLANTABLE", "FEEDABLE", "CAREABLE", "HARVEST_ANIMAL", "WATERABLE",
              "HARVEST_PLANT", "DIGGABLE", "PLACEABLE"}
EXT_KINDS = {"FERTILIZABLE", "COLLECTABLE"}

BANDS = [("d0-9", 0, 9), ("d10-19", 10, 19), ("d20-27", 20, 27), ("d28-29", 28, 29)]
WINDOW = ("d10-27", 10, 27)   # 事前登録の判定窓


# ---------------------------------------------------------------- agent loader
ANCHOR = "\n    claimed = set()\n"
PATCH = "\n    globals()['_TODO_SNAP'] = list(todos)\n    claimed = set()\n"


def load_patched_agent(path):
    """todo 一覧をスナップショットするパッチを当てた agent モジュールをメモリ上に作る。"""
    src = open(path, encoding="utf-8").read()
    if src.count(ANCHOR) != 1:
        raise SystemExit("anchor '    claimed = set()' が %d 個（1 個でない）: %s"
                         % (src.count(ANCHOR), path))
    # todo への append がアンカーより後ろに無いことを機械的に確かめる
    a_at = src.index(ANCHOR)
    if "todos.append" in src[a_at:]:
        raise SystemExit("アンカーより後ろに todos.append がある: %s" % path)
    mod = types.ModuleType("patched_" + os.path.basename(os.path.dirname(path)))
    mod.__dict__["__file__"] = path
    exec(compile(src.replace(ANCHOR, PATCH), path, "exec"), mod.__dict__)
    return mod


# ---------------------------------------------------------------- board work
def board_work(farm, day, seeds_total, ext=True):
    """盤面から「今できる仕事」を列挙する。[(kind, x, y), ...]

    エージェントの todo 生成には依存しない（依存すると設計の自己弁護になる）。
    base 部分は `2026-09-19_move-budget.py` の board_work と同一。
    """
    out = []
    for y, row in enumerate(farm["tiles"]):
        for x, t in enumerate(row):
            if t == "LOCKED":
                continue
            if t is None:
                if seeds_total > 0:
                    out.append(("PLANTABLE", x, y))
                continue
            if not isinstance(t, dict):
                continue
            if t.get("animal"):
                if not t.get("fed_today"):
                    out.append(("FEEDABLE", x, y))
                if not t.get("cared_today"):
                    out.append(("CAREABLE", x, y))
                if t.get("yield_units", 0) > 0:
                    out.append(("HARVEST_ANIMAL", x, y))
                if ext and t.get("fertilizer_available"):
                    out.append(("COLLECTABLE", x, y))
            elif t.get("kind") == "PLANT":
                if not t.get("watered_today"):
                    out.append(("WATERABLE", x, y))
                age = day - t.get("planted_day", day)
                if t.get("yield_units", 0) > 0 and age >= CROPS_FIRST_YIELD.get(t.get("crop"), 99):
                    out.append(("HARVEST_PLANT", x, y))
                if (ext and t.get("crop") == "STRAWBERRY" and day < FINAL_DAY
                        and t.get("fertilized_until_day", -1) < day):
                    out.append(("FERTILIZABLE", x, y))
            elif t.get("kind") == "WEED":
                out.append(("DIGGABLE", x, y))
            elif t.get("kind") in ("PASTURE", "COOP") and not t.get("animal"):
                out.append(("PLACEABLE", x, y))
    return out


def reason_ii(kind, tile, x, y, day, hour, mod):
    """(ii)（todo に載らなかった仕事）の理由ラベル。

    gen0058/main.py の todo 生成条件をそのまま鏡写しにする（該当行は成果物 §1 に file:line）。
    エージェントのモジュール定数を直接読むので、定数の写し間違いは起きない。
    """
    if kind == "HARVEST_PLANT":
        crop = tile.get("crop")
        age = day - tile.get("planted_day", day)
        if crop == "MELON":
            ripe = age >= 10
        elif crop == "STRAWBERRY":
            ripe = True
        elif crop == "CARROT":
            ripe = age >= 3 or (day >= mod.FINAL_DAY - 1 and age >= 2)
        else:
            ripe = age >= 4 or (day >= mod.DUMP_DAY and age >= 2)
        if not ripe:
            return "未成熟（今刈ると最大収量に届かない: %s age%d）" % (crop, age)
        # ripe なのに HARVEST todo が無い = water_first（同じ訪問で水やりを先に出す）
        return "water_first（増収の水やりを優先 / %s）" % crop
    if kind == "PLANTABLE":
        if hour > mod.LAST_PLANT_HOUR:
            return "植付締切後（h>%d: 当日の水やりが間に合わず確定枯れ）" % mod.LAST_PLANT_HOUR
        if day > mod.LAST_PLANT_DAY:
            return "植付期限後（d>%d: d29 までに収穫が間に合わない）" % mod.LAST_PLANT_DAY
        if (x, y) in set(mod.PASTURE_TILES):
            return "パスチャ予定地（植えない）"
        return "★計画が予約中 / 窓が閉じている（fallback からも除外）"
    if kind == "WATERABLE":
        if day >= mod.FINAL_DAY:
            return "最終日（EOD 生産が無く水やりは無価値）"
        if tile.get("crop") == "STRAWBERRY" and (day - tile.get("planted_day", day)) >= 16:
            return "イチゴ生産終了（age>=16）"
        # 収穫可（ripe）で増収窓の外 → agent は WATER を出さず HARVEST を出す
        # （gen0058 main.py 691-702 の `elif not (yu > 0 and ripe)`）
        return "収穫可の株（水をやらず刈る。窓外の水やりは枯死防止にしか効かない）"
    if kind == "FERTILIZABLE":
        age = day - tile.get("planted_day", day)
        if age not in mod.STRAW_PROD_AGES:
            return "生産日でない（age%d ∉ %s。撒いても 3 日で切れる）" % (age, mod.STRAW_PROD_AGES)
        return "その他"
    if kind == "HARVEST_ANIMAL":
        return "★価格床の収穫バンク（SELL_FLOORS / β 判定で意図的に据え置き）"
    if kind == "DIGGABLE":
        if day > mod.LAST_PLANT_DAY:
            return "植付期限後（除草しても植えられない）"
        return "★計画地でもゾーン対象でもない雑草"
    if kind == "CAREABLE":
        if day > mod.LAST_FEED_DAY:
            return "給餌・世話の期限後（d>%d）" % mod.LAST_FEED_DAY
        return "その他"
    if kind == "FEEDABLE":
        if day > mod.LAST_FEED_DAY:
            return "給餌期限後（d>%d）" % mod.LAST_FEED_DAY
        return "その他"
    if kind == "COLLECTABLE":
        return "最終行動ターン（FIX0011: 回収しても売る手番が無い）"
    return "その他"


def feasible(kind, inv):
    """そのユニットの持ち物で実行できる仕事か（元スクリプトの PASS 分析と同じ filter）。"""
    if kind == "FEEDABLE":
        return inv.get("WHEAT", 0) > 0
    if kind == "FERTILIZABLE":
        return inv.get("FERTILIZER", 0) > 0
    if kind == "PLACEABLE":
        return any(inv.get(a, 0) > 0 for a in ANIMAL_ITEMS)
    return True


# ---------------------------------------------------------------- matching
def max_matching(adj, n_right):
    """二部マッチングの最大数（Kuhn 法）。adj[u] = 右側インデックスのリスト。"""
    match_r = [-1] * n_right
    res = 0

    def try_k(u, seen):
        for v in adj[u]:
            if seen[v]:
                continue
            seen[v] = True
            if match_r[v] == -1 or try_k(match_r[v], seen):
                match_r[v] = u
                return True
        return False

    for u in range(len(adj)):
        if try_k(u, [False] * n_right):
            res += 1
    return res


# ---------------------------------------------------------------- core
def build_did(steps, player):
    """(day, (x, y)) -> [(hour, unit_idx, op0)] — その日そのタイルで実際に打たれた生産行動。"""
    did = collections.defaultdict(list)
    for t in range(1, len(steps)):
        pre = steps[t - 1][player]["observation"]
        act = steps[t][player].get("action") or {}
        day, hour = pre["day"], pre["hour"]
        farm = pre["farms"][player]
        units = [tuple(farm["farmer"])] + [tuple(h) for h in (farm.get("hands") or [])]
        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        for ui, pos in enumerate(units):
            op = (ops[ui] if ui < len(ops) else None) or ["PASS"]
            if op[0] not in MOVES and op[0] != "PASS":
                did[(day, pos)].append((hour, ui, op[0]))
    return did


def analyse(replay_path, agent_path, player=0, verify=False, ext=True, progress=None):
    mod = load_patched_agent(agent_path)
    steps = json.load(open(replay_path))["steps"]
    total = len(steps)
    did = build_did(steps, player)

    rows = []          # 1 遊休 unit-hour = 1 行
    cap = []           # (day, hour, n_idle, matched_i, matched_ii, matched_all, matched_i_strict)
    fate_i = collections.Counter()
    fate_ii = collections.Counter()
    # 「異なり数」= 同じ (day, hour, タイル) の仕事を遊休ユニットの数だけ重複して数えない版
    dist_i = collections.Counter()
    dist_ii = collections.Counter()
    reason_ii_c = collections.Counter()
    reason_ii_w = collections.Counter()   # d10-27 窓だけ
    # 日単位の余剰: 「todo に載っていて、遊休ユニットの到達圏内に在って、その日誰も
    # やらなかった」仕事の **異なり数**（(day, x, y, op) で一意化）
    never_i = set()
    never_ii = set()
    idle_by_day = collections.Counter()
    kind_i = collections.Counter()
    kind_ii = collections.Counter()
    kind_i_band = collections.defaultdict(collections.Counter)
    kind_ii_band = collections.defaultdict(collections.Counter)
    n_verify = n_mismatch = 0

    for t in range(1, total):
        pre = steps[t - 1][player]["observation"]
        act = steps[t][player].get("action") or {}
        day, hour = pre["day"], pre["hour"]
        farm = pre["farms"][player]
        priv = pre.get("private") or {}
        invs = priv.get("inventories") or []
        seeds_total = sum((priv.get("seeds") or {}).values())

        units = [tuple(farm["farmer"])] + [tuple(h) for h in (farm.get("hands") or [])]
        ops = [act.get("farmer") or ["PASS"]] + list(act.get("hands") or [])
        ops = [(o or ["PASS"]) for o in ops]
        while len(ops) < len(units):
            ops.append(["PASS"])

        # その時間に実際に手が付いたタイル（非 MOVE・非 PASS）
        busy = set()
        for ui, pos in enumerate(units):
            if ops[ui][0] not in MOVES and ops[ui][0] != "PASS":
                busy.add(pos)

        idle = [ui for ui, pos in enumerate(units)
                if ops[ui][0] in MOVES or ops[ui][0] == "PASS"]
        if not idle:
            continue

        work = [w for w in board_work(farm, day, seeds_total, ext=ext)
                if (w[1], w[2]) not in busy]
        if not work:
            for ui in idle:
                rows.append(dict(day=day, hour=hour, unit=ui, is_farmer=(ui == 0),
                                 idle_kind=("PASS" if ops[ui][0] == "PASS" else "MOVE"),
                                 n_i=0, n_ii=0, n_i_base=0, n_ii_base=0,
                                 n_i_strict=0, n_ii_strict=0, n_i_never=0))
            cap.append((day, hour, len(idle), 0, 0, 0, 0))
            continue

        # ---- エージェントが今このターン生成した todo 一覧（実走で取得） ----
        mod.__dict__.pop("_TODO_SNAP", None)
        out = mod.agent(pre)
        snap = mod.__dict__.get("_TODO_SNAP")
        if snap is None:
            raise SystemExit("todo スナップショットが取れない（_agent が例外）: d%d h%d" % (day, hour))
        todo_xyop = set()
        for _pri, x, y, op, _need in snap:
            todo_xyop.add((x, y, op[0]))
        if verify:
            n_verify += 1
            got = [list(out.get("farmer") or ["PASS"])] + [list(o) for o in (out.get("hands") or [])]
            want = [list(o) for o in ops]
            if got[:len(want)] != want:
                n_mismatch += 1

        # ---- 遊休 unit-hour ごとに、到達圏内・未着手・実行可能な仕事を数える ----
        left = 24 - hour
        adj_i, adj_ii, adj_all, adj_i_strict = [], [], [], []
        for ui in idle:
            pos = units[ui]
            inv = invs[ui] if ui < len(invs) else {}
            n_i = n_ii = n_i_base = n_ii_base = 0
            n_i_strict = n_ii_strict = n_i_never = 0
            li, lii, li_s = [], [], []
            for wi, (kind, x, y) in enumerate(work):
                if abs(pos[0] - x) + abs(pos[1] - y) + 1 > left:
                    continue
                if not feasible(kind, inv):
                    continue
                op0 = KIND_OP[kind]
                ev = [(h, u) for h, u, o in did.get((day, (x, y)), [])
                      if h > hour and o == op0]
                if any(u == ui for _h, u in ev):
                    fate = "self"
                elif ev:
                    fate = "other"
                else:
                    fate = "never"
                if (x, y, op0) in todo_xyop:
                    if fate == "never":
                        never_i.add((day, x, y, op0))
                    n_i += 1
                    li.append(wi)
                    kind_i[kind] += 1
                    kind_i_band[band_of(day)][kind] += 1
                    fate_i[fate] += 1
                    if kind in BASE_KINDS:
                        n_i_base += 1
                    if fate != "self":
                        n_i_strict += 1
                        li_s.append(wi)
                    if fate == "never":
                        n_i_never += 1
                else:
                    if fate == "never":
                        never_ii.add((day, x, y, op0))
                    n_ii += 1
                    lii.append(wi)
                    kind_ii[kind] += 1
                    kind_ii_band[band_of(day)][kind] += 1
                    fate_ii[fate] += 1
                    if kind in BASE_KINDS:
                        n_ii_base += 1
                    if fate != "self":
                        n_ii_strict += 1
            rows.append(dict(day=day, hour=hour, unit=ui, is_farmer=(ui == 0),
                             idle_kind=("PASS" if ops[ui][0] == "PASS" else "MOVE"),
                             n_i=n_i, n_ii=n_ii, n_i_base=n_i_base, n_ii_base=n_ii_base,
                             n_i_strict=n_i_strict, n_ii_strict=n_ii_strict,
                             n_i_never=n_i_never))
            adj_i.append(li)
            adj_ii.append(lii)
            adj_all.append(li + lii)
            adj_i_strict.append(li_s)
        idle_by_day[day] += len(idle)
        # 異なり数と (ii) の理由（遊休ユニットの誰か 1 人でも届いた仕事を 1 件と数える）
        seen_i = set(w for l in adj_i for w in l)
        seen_ii = set(w for l in adj_ii for w in l)
        for wi in seen_i:
            dist_i[work[wi][0]] += 1
        for wi in seen_ii:
            kind, x, y = work[wi]
            dist_ii[kind] += 1
            tl = farm["tiles"][y][x]
            r = reason_ii(kind, tl if isinstance(tl, dict) else {}, x, y, day, hour, mod)
            reason_ii_c[(kind, r)] += 1
            if WINDOW[1] <= day <= WINDOW[2]:
                reason_ii_w[(kind, r)] += 1
        cap.append((day, hour, len(idle),
                    max_matching(adj_i, len(work)),
                    max_matching(adj_ii, len(work)),
                    max_matching(adj_all, len(work)),
                    max_matching(adj_i_strict, len(work))))
        if progress and t % 120 == 0:
            print("    ... step %d/%d" % (t, total), file=sys.stderr)

    return dict(rows=rows, cap=cap,
                fate_i=dict(fate_i), fate_ii=dict(fate_ii),
                dist_i=dict(dist_i), dist_ii=dict(dist_ii),
                never_i_day=dict(collections.Counter(d for d, _x, _y, _o in never_i)),
                never_ii_day=dict(collections.Counter(d for d, _x, _y, _o in never_ii)),
                never_i_kind=dict(collections.Counter(o for _d, _x, _y, o in never_i)),
                idle_by_day={str(k): v for k, v in idle_by_day.items()},
                reason_ii=[[list(k), v] for k, v in reason_ii_c.items()],
                reason_ii_w=[[list(k), v] for k, v in reason_ii_w.items()],
                kind_i=dict(kind_i), kind_ii=dict(kind_ii),
                kind_i_band={k: dict(v) for k, v in kind_i_band.items()},
                kind_ii_band={k: dict(v) for k, v in kind_ii_band.items()},
                verify=dict(n=n_verify, mismatch=n_mismatch))


def band_of(day):
    for name, lo, hi in BANDS:
        if lo <= day <= hi:
            return name
    return "?"


# ---------------------------------------------------------------- report
def agg(rows, lo, hi, idle_kind=None, base_only=False, strict=False):
    n = ni = nii = 0
    for r in rows:
        if not (lo <= r["day"] <= hi):
            continue
        if idle_kind and r["idle_kind"] != idle_kind:
            continue
        n += 1
        if strict:
            ni += r["n_i_strict"]
            nii += r["n_ii_strict"]
        elif base_only:
            ni += r["n_i_base"]
            nii += r["n_ii_base"]
        else:
            ni += r["n_i"]
            nii += r["n_ii"]
    return n, ni, nii


def agg_never(rows, lo, hi):
    n = nv = 0
    for r in rows:
        if lo <= r["day"] <= hi:
            n += 1
            nv += r["n_i_never"]
    return n, nv


def fmt_ratio(n, v):
    return "%.2f" % (v / n) if n else "-"


def report(results):
    """results: [(label, gen, opp, seed, res), ...]"""
    allrows = [r for _l, _g, _o, _s, res in results for r in res["rows"]]

    print("=" * 96)
    print("■ 日帯別（12 戦合計 / ext 含む / 事前登録どおりの数え方）")
    print("%-8s %10s %9s %9s %9s %9s" % ("帯", "遊休uh", "(i)件", "(ii)件", "(i)/遊休", "(ii)/遊休"))
    for name, lo, hi in BANDS:
        n, ni, nii = agg(allrows, lo, hi)
        print("%-8s %10d %9d %9d %9s %9s" % (name, n, ni, nii, fmt_ratio(n, ni), fmt_ratio(n, nii)))
    n, ni, nii = agg(allrows, 0, 29)
    print("%-8s %10d %9d %9d %9s %9s" % ("全期間", n, ni, nii, fmt_ratio(n, ni), fmt_ratio(n, nii)))
    wn, wi, wii = agg(allrows, WINDOW[1], WINDOW[2])
    print("★%-7s %10d %9d %9d %9s %9s  <- 事前登録の判定窓"
          % (WINDOW[0], wn, wi, wii, fmt_ratio(wn, wi), fmt_ratio(wn, wii)))
    bn, bi, bii = agg(allrows, WINDOW[1], WINDOW[2], base_only=True)
    print("  （base kind のみ: 遊休 %d / (i) %d / (ii) %d / (i)/遊休 %s）"
          % (bn, bi, bii, fmt_ratio(bn, bi)))

    print()
    print("■ 日帯別（strict = 自分の目的地 fate:self を除く）")
    print("%-8s %10s %9s %9s %9s %9s"
          % ("帯", "遊休uh", "(i)件", "(ii)件", "(i)/遊休", "(ii)/遊休"))
    for name, lo, hi in BANDS + [WINDOW]:
        n, ni, nii = agg(allrows, lo, hi, strict=True)
        print("%-8s %10d %9d %9d %9s %9s" % (name, n, ni, nii, fmt_ratio(n, ni), fmt_ratio(n, nii)))
    print("■ 日帯別（(i) のうち fate:never = その日誰もやらなかった仕事だけ）")
    for name, lo, hi in BANDS + [WINDOW]:
        n, nv = agg_never(allrows, lo, hi)
        print("%-8s 遊休uh %6d  (i)&never %8d  比 %s" % (name, n, nv, fmt_ratio(n, nv)))

    print()
    print("■ 遊休の種類別（PASS / 通勤 MOVE）")
    print("%-8s %-6s %10s %9s %9s %9s" % ("帯", "種類", "遊休uh", "(i)件", "(ii)件", "(i)/遊休"))
    for name, lo, hi in BANDS + [WINDOW]:
        for k in ("PASS", "MOVE"):
            n, ni, nii = agg(allrows, lo, hi, idle_kind=k)
            print("%-8s %-6s %10d %9d %9d %9s" % (name, k, n, ni, nii, fmt_ratio(n, ni)))

    print()
    print("■ seed 別・世代別・相手別（d10-27 の窓）")
    hdr = ("%-9s %-8s %6s %9s %8s %9s %8s %9s %11s"
           % ("gen", "opp", "seed", "遊休uh", "(i)件", "(i)/遊休", "(ii)件", "(ii)/遊休", "strict(i)/遊休"))
    print(hdr)

    def line(gen, opp, seed, rr):
        n, ni, nii = agg(rr, WINDOW[1], WINDOW[2])
        _n2, nis, _ = agg(rr, WINDOW[1], WINDOW[2], strict=True)
        print("%-9s %-8s %6s %9d %8d %9s %8d %9s %11s"
              % (gen, opp, seed, n, ni, fmt_ratio(n, ni), nii, fmt_ratio(n, nii),
                 fmt_ratio(n, nis)))

    for _label, gen, opp, seed, res in results:
        line(gen, opp, seed, res["rows"])
    for gen in ("gen0058", "gen0059"):
        line(gen, "(小計)", "-",
             [r for _l, g, _o, _s, res in results if g == gen for r in res["rows"]])
    for opp in ("7turn", "gen0045"):
        line("(小計)", opp, "-",
             [r for _l, _g, o, _s, res in results if o == opp for r in res["rows"]])

    print()
    ki = collections.Counter()
    kii = collections.Counter()
    kiw = collections.Counter()
    kiiw = collections.Counter()
    for _l, _g, _o, _s, res in results:
        ki.update(res["kind_i"])
        kii.update(res["kind_ii"])
        for b in ("d10-19", "d20-27"):
            kiw.update(res["kind_i_band"].get(b) or {})
            kiiw.update(res["kind_ii_band"].get(b) or {})
    for tag, c, cw in (("(i)", ki, kiw), ("(ii)", kii, kiiw)):
        tot = sum(c.values()) or 1
        totw = sum(cw.values()) or 1
        print("■ %s の kind 内訳（12 戦合計・件数の多い順。右は d10-27 窓だけの再集計）" % tag)
        print("   %-18s %10s %8s %10s %8s" % ("kind", "全期間", "%", "d10-27", "%"))
        for k, v in c.most_common():
            print("   %-18s %10d %7.1f%% %10d %7.1f%%%s"
                  % (k, v, 100 * v / tot, cw.get(k, 0), 100 * cw.get(k, 0) / totw,
                     "  [ext]" if k in EXT_KINDS else ""))

    print()
    di = collections.Counter()
    dii = collections.Counter()
    ri = collections.Counter()
    riw = collections.Counter()
    for _l, _g, _o, _s, res in results:
        di.update(res.get("dist_i") or {})
        dii.update(res.get("dist_ii") or {})
        for k, v in (res.get("reason_ii") or []):
            ri[tuple(k)] += v
        for k, v in (res.get("reason_ii_w") or []):
            riw[tuple(k)] += v
    print("■ 異なり数（同じ (day, hour, タイル) を遊休ユニットの数だけ重複計上しない版・12 戦合計）")
    print("   %-18s %10s %10s" % ("kind", "(i)", "(ii)"))
    for k in sorted(set(di) | set(dii), key=lambda k: -(di.get(k, 0) + dii.get(k, 0))):
        print("   %-18s %10d %10d%s" % (k, di.get(k, 0), dii.get(k, 0),
                                        "  [ext]" if k in EXT_KINDS else ""))
    print("   %-18s %10d %10d" % ("合計", sum(di.values()), sum(dii.values())))
    print()
    print("■ (ii) の理由内訳（異なり数・12 戦合計 / 右は d10-27 窓）")
    tot = sum(ri.values()) or 1
    totw = sum(riw.values()) or 1
    for (k, r), v in ri.most_common():
        print("   %-14s %-52s %8d %5.1f%% | %8d %5.1f%%"
              % (k, r[:52], v, 100 * v / tot, riw.get((k, r), 0),
                 100 * riw.get((k, r), 0) / totw))

    print()
    print("■ 補助指標: 容量マッチ（同じ仕事を複数の遊休ユニットで重複して数えない版）")
    print("   各 (day, hour) で「遊休ユニット ↔ 到達圏内・未着手・実行可能な仕事」の最大二部マッチを取り、")
    print("   matched / 遊休ユニット数 = 『その時間に実際に別々の仕事を割り振れた遊休ユニットの割合』。")
    print("%-8s %10s %10s %10s %10s %12s"
          % ("帯", "遊休uh", "matched(i)", "matched(全)", "(i)充足率", "strict充足率"))
    for name, lo, hi in BANDS + [WINDOW]:
        n = mi = ma = ms = 0
        for _l, _g, _o, _s, res in results:
            for row in res["cap"]:
                day, _h, nidle, m_i, _m_ii, m_all = row[:6]
                m_s = row[6] if len(row) > 6 else 0
                if lo <= day <= hi:
                    n += nidle
                    mi += m_i
                    ma += m_all
                    ms += m_s
        print("%-8s %10d %10d %10d %10s %12s"
              % (name, n, mi, ma, fmt_ratio(n, mi), fmt_ratio(n, ms)))

    print()
    print("■ ★日単位の余剰（異なり数）: 『todo に載り・遊休ユニットの到達圏内に在り・その日は誰も")
    print("   やらなかった』仕事を (day, x, y, op) で一意化して数える。12 戦合計。")
    print("%-8s %10s %14s %14s %16s" % ("帯", "遊休uh", "(i)&never件", "(ii)&never件", "(i)&never/遊休uh"))
    for name, lo, hi in BANDS + [WINDOW]:
        n = ni = nii = 0
        for _l, _g, _o, _s, res in results:
            for d, v in (res.get("idle_by_day") or {}).items():
                if lo <= int(d) <= hi:
                    n += v
            for d, v in (res.get("never_i_day") or {}).items():
                if lo <= int(d) <= hi:
                    ni += v
            for d, v in (res.get("never_ii_day") or {}).items():
                if lo <= int(d) <= hi:
                    nii += v
        print("%-8s %10d %14d %14d %16s" % (name, n, ni, nii, fmt_ratio(n, ni)))
    nk = collections.Counter()
    for _l, _g, _o, _s, res in results:
        nk.update(res.get("never_i_kind") or {})
    print("   (i)&never の op 内訳: %s" % dict(nk.most_common()))

    print()
    print("■ 行き先の帰属（fate）— 数えた仕事はその日誰の手で実行されたか")
    for tag, key in (("(i)", "fate_i"), ("(ii)", "fate_ii")):
        c = collections.Counter()
        for _l, _g, _o, _s, res in results:
            c.update(res.get(key) or {})
        tt = sum(c.values()) or 1
        print("   %-5s self(自分の目的地) %8d (%.1f%%) / other(同日に他ユニット) %8d (%.1f%%) / "
              "never(その日は誰もやらず) %8d (%.1f%%)"
              % (tag, c["self"], 100 * c["self"] / tt, c["other"], 100 * c["other"] / tt,
                 c["never"], 100 * c["never"] / tt))

    print()
    v = collections.Counter()
    for _l, _g, _o, _s, res in results:
        v["n"] += res["verify"]["n"]
        v["mismatch"] += res["verify"]["mismatch"]
    if v["n"]:
        print("■ 検証: エージェント再実行 %d ターン中、リプレイと行動が違ったターン %d"
              % (v["n"], v["mismatch"]))


# ---------------------------------------------------------------- cli
JOBS = [("gen0058", "agents/gen0058/main.py"), ("gen0059", "agents/gen0059/main.py")]
OPPS = ["7turn", "gen0045"]
SEEDS = [7, 42, 5000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay")
    ap.add_argument("--agent")
    ap.add_argument("--gen", default="?")
    ap.add_argument("--opp", default="?")
    ap.add_argument("--seed", default="?")
    ap.add_argument("--out")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--report", nargs="*")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--no-ext", action="store_true")
    args = ap.parse_args()

    results = []
    if args.report:
        for f in sorted(sum([glob.glob(p) for p in args.report], [])):
            d = json.load(open(f))
            results.append((f, d["gen"], d["opp"], str(d["seed"]), d["res"]))
        report(results)
        return

    jobs = []
    if args.all:
        for gen, apath in JOBS:
            for opp in OPPS:
                for s in SEEDS:
                    rp = "records/di%s_%s_s%d_replay.json" % (gen[-2:], opp, s)
                    jobs.append((rp, apath, gen, opp, s,
                                 "records/di_inv_%s_%s_s%d.json" % (gen[-2:], opp, s)))
    else:
        jobs.append((args.replay, args.agent, args.gen, args.opp, args.seed, args.out))

    for rp, apath, gen, opp, seed, out in jobs:
        print("[run] %s (%s)" % (rp, apath), file=sys.stderr)
        res = analyse(rp, apath, verify=args.verify, ext=not args.no_ext)
        if out:
            json.dump(dict(gen=gen, opp=opp, seed=seed, replay=rp, agent=apath, res=res),
                      open(out, "w"))
        results.append((rp, gen, opp, str(seed), res))
    report(results)


if __name__ == "__main__":
    sys.setrecursionlimit(10000)
    main()
