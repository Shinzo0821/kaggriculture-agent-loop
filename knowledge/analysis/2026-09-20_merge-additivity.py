#!/usr/bin/env python3
"""機構の合流は加算か —— 保存済み eval の per-game セルから対応付きの差分の差分を出す。

`harness/evaluate.py` の gate 要約（`margin_delta_paired.mean`）だけを足し引きすると、
telescope する量（M_b − M_a）を「機構 a 単体の値」と取り違える。ここでは 5 本の eval
（gen0051 / gen0058 / gen0059 / gen0060 / gen0062。すべて同じ pool_sha・seed_base・
50 シード・両席 = 1,300 セル）の **games 配列を (相手, シード, 側) で突き合わせ**、
`evaluate.py::paired_delta` と同じ推定量（セルの重み付き和 → シードごとに平均 →
50 シードで正規 CI）で任意の線形コントラストを出す。

**検算の範囲（Codex gpt-5.6-sol/high レビュー 2026-09-20 で訂正）**:
- `margin` / `money` の A-D は保存 gate（`margin_delta_paired` / `money_delta_paired`）を
  0.1 の桁まで再現する ＝ 推定量の実装検算になっている。
- `slope` は違う。`evaluate.py:332` の `slope_delta` は**丸めた平均の差**で CI を持たない。
  本稿の slope は同じセルから新たに対応付き CI を付けた**診断値**である（シードあたりの
  セル数が均等なので点推定は一致するが、由来が別）。
- F（59 − 58）はどの eval の gate にも無い**代数的な検算値**。

使い方: .venv/bin/python knowledge/analysis/2026-09-20_merge-additivity.py
"""
import json, math, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENS = ['gen0051', 'gen0058', 'gen0059', 'gen0060', 'gen0062']


def die(msg):
    # assert は python -O で消えるので使わない（前提が崩れたら必ず止める）。
    raise SystemExit(f'比較不能: {msg}')


pool = json.loads((ROOT / 'control/sparring_pool.json').read_text())
ents = pool['opponents'] if isinstance(pool, dict) and 'opponents' in pool else pool
# evaluate.py:162-165 / :276 と同じ規則: enabled な相手だけ、キーは path のみ。
STRONG = {e['path'] for e in ents
          if e.get('enabled', True) and e.get('tier') == 'strong'}

META, G = {}, {}
for n in GENS:
    d = json.loads((ROOT / f'records/eval_{n}.json').read_text())
    idx = {(g['opponent'], g['seed'], g['cand_side']): g for g in d['games']}
    if len(idx) != len(d['games']):
        die(f'{n}: games に重複セル（{len(d["games"])} 件 → 一意 {len(idx)} 件）')
    META[n], G[n] = d, idx

# 前提の検査。1 つでも崩れたら線形コントラストの恒等式が壊れるので黙って続けない。
for key in ('pool_sha256', 'seeds', 'seed_base', 'steps'):
    vals = {META[n].get(key) for n in GENS}
    if len(vals) != 1:
        die(f'{key} が一致しない: ' + ', '.join(f'{n}={META[n].get(key)!r}' for n in GENS))
ref = set(G[GENS[0]])
for n in GENS[1:]:
    if set(G[n]) != ref:
        d1, d2 = set(G[n]) - ref, ref - set(G[n])
        die(f'{n} のセル集合が gen0051 と違う（片側のみ {len(d1)} / {len(d2)} 件）')
KEYS = ref
SK = {k for k in KEYS if k[0] in STRONG}
# paired_delta は「シード平均の平均」なので、シードあたりのセル数が不揃いだと
# コントラストの線形性（F = C − A 等）が厳密には成り立たない。
for name, cells in (('全プール', KEYS), ('強帯', SK)):
    cnt = defaultdict(int)
    for k in cells:
        cnt[k[1]] += 1
    if len(set(cnt.values())) != 1:
        die(f'{name}: シードあたりのセル数が不揃い {sorted(set(cnt.values()))}')

FIELDS = {
    'margin': lambda g: g['cand_final'] - g['opp_final'],   # 昇格の判定量
    'money':  lambda g: g['cand_final'],                    # 自分の資金（診断用）
    'slope':  lambda g: g['cand_slope'],                    # 後半傾き（診断用）
}


def contrast(coefs, cells, field):
    f = FIELDS[field]
    by_seed = defaultdict(list)
    for k in cells:
        by_seed[k[1]].append(sum(w * f(G[n][k]) for n, w in coefs.items()))
    sd = [statistics.mean(xs) for xs in by_seed.values()]
    m = statistics.mean(sd)
    se = statistics.stdev(sd) / math.sqrt(len(sd))
    return m, m - 1.96 * se, m + 1.96 * se, se, len(sd)


ROWS = [
    ('A  到達可能性ゲート @gen0051 : 58 − 51', {'gen0058': 1, 'gen0051': -1}),
    ('B  バックログ解除   @gen0058 : 60 − 58', {'gen0060': 1, 'gen0058': -1}),
    ('C  farmer ゾーン    @gen0051 : 59 − 51', {'gen0059': 1, 'gen0051': -1}),
    ('D  farmer ゾーン    @gen0060 : 62 − 60', {'gen0062': 1, 'gen0060': -1}),
    ('E  累積             : 62 − 51',         {'gen0062': 1, 'gen0051': -1}),
    ('I  交互作用 D − C  (= E − (A+B+C))',    {'gen0062': 1, 'gen0060': -1,
                                               'gen0059': -1, 'gen0051': 1}),
    ('F  参考: 59 − 58 (機構差。単体値ではない)', {'gen0059': 1, 'gen0058': -1}),
]

m0 = META['gen0051']
print(f'共通セル {len(KEYS)}（うち強帯 {len(SK)}／有効な strong 相手 {len(STRONG)}）'
      f'／ pool_sha {m0["pool_sha256"][:8]} ／ seeds {m0["seeds"]} '
      f'seed_base {m0["seed_base"]} steps {m0["steps"]}')
for name, cells in (('全プール', KEYS), ('強帯のみ', SK)):
    for field in FIELDS:
        print(f'\n=== {name} / {field} ===')
        for lab, co in ROWS:
            m, lo, hi, se, n = contrast(co, cells, field)
            tag = '有意' if (lo > 0 or hi < 0) else 'CI が 0 をまたぐ'
            print(f'{lab:44s} {m:+9.1f}  [{lo:+8.1f}, {hi:+8.1f}]  se={se:6.1f}  {tag}')
        s = sum(contrast(co, cells, field)[0] for lab, co in ROWS[:3])
        e = contrast(ROWS[4][1], cells, field)[0]
        print(f'{"加算予測 A+B+C":44s} {s:+9.1f}   実測 E {e:+9.1f}   超過 {e - s:+.1f}')
