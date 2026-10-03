#!/usr/bin/env python3
"""勝ちはどちらで作られたか —— マージンを「自分の資金」と「相手の資金」に割る。

昇格の判定量 `margin = cand_final - opp_final` は**セル単位の恒等式**なので、
対応付きの差分もそのまま割れる:

    Δmargin = Δown − Δopp        （Δopp = 相手の最終資金の差。負 = 相手を削った）

`harness/evaluate.py` の gate は `margin_delta_paired` と `money_delta_paired`（= Δown）
しか出さない。**Δopp に対応付き CI が付いたことは一度も無く**、「勝ちの多くは相手資金の
低下」（HANDOFF の王者評）は 2 つの点推定の引き算でしか言えていなかった。
ここでは c7（`2026-09-20_merge-additivity.py`）と同じ推定量
（`evaluate.py::paired_delta`: セル → シード平均 → シード数で正規 CI）で Δopp に直接
CI を付け、**相手の帯ごと**に生産（自分が伸びる）と denial（相手が減る）へ分解する。

検算: 各行で Δown − Δopp が Δmargin に一致すること（恒等式）を機械で確かめる。
`margin` / `own` は保存 gate の値を 0.1 の桁まで再現する（c7 で確認済み）。

使い方:
  .venv/bin/python knowledge/analysis/2026-09-20_production_vs_denial.py
      系譜 5 本（gen0051/58/59/60/62）の段ごと + 累積 + 相手別
  .venv/bin/python knowledge/analysis/2026-09-20_production_vs_denial.py \
      --pair records/eval_gen0051_sb2000.json records/eval_gen0062_sb2000.json
      任意の 2 本だけ（別 seed 帯での追試 = 選抜バイアスの外側で同じ分解をやり直す）
"""
import argparse, hashlib, json, math, statistics
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LINEAGE = ['gen0051', 'gen0058', 'gen0059', 'gen0060', 'gen0062']
LINEAGE_ROWS = [
    ('A  到達可能性ゲート @gen0051 : 58 − 51', {'gen0058': 1, 'gen0051': -1}),
    ('B  バックログ解除   @gen0058 : 60 − 58', {'gen0060': 1, 'gen0058': -1}),
    ('D  farmer ゾーン    @gen0060 : 62 − 60', {'gen0062': 1, 'gen0060': -1}),
    ('C  farmer ゾーン    @gen0051 : 59 − 51', {'gen0059': 1, 'gen0051': -1}),
    ('E  累積             : 62 − 51',         {'gen0062': 1, 'gen0051': -1}),
]
FIELDS = {'margin': lambda g: g['cand_final'] - g['opp_final'],
          'own':    lambda g: g['cand_final'],
          'opp':    lambda g: g['opp_final']}


def die(msg):
    raise SystemExit(f'比較不能: {msg}')


def load(paths):
    """{名前: セル索引} と共通セル集合。前提が崩れたら止める（黙って続けない）。"""
    meta, idx = {}, {}
    for name, p in paths.items():
        d = json.loads((ROOT / p).read_text())
        cells = {(g['opponent'], g['seed'], g['cand_side']): g for g in d['games']}
        if len(cells) != len(d['games']):
            die(f'{name}: games に重複セル')
        meta[name], idx[name] = d, cells
    for key in ('pool_sha256', 'seeds', 'seed_base', 'steps'):
        vals = {n: meta[n].get(key) for n in paths}
        # 全部 None でも「一致」になってしまう経路を塞ぐ（Codex P2-4）。
        if any(v is None for v in vals.values()):
            die(f'{key} が欠けている eval がある: {vals}')
        if len(set(vals.values())) != 1:
            die(f'{key} が一致しない: ' + ', '.join(f'{n}={v!r}' for n, v in vals.items()))
    # 保存された pool_sha が**今の** sparring_pool.json と一致するか。
    # 一致しないと下の STRONG（今のプールから作る帯の定義）が、その eval を取った
    # ときの帯と違いうる ＝ 帯の対比が静かに別物になる。
    cur = hashlib.sha256((ROOT / 'control/sparring_pool.json').read_bytes()).hexdigest()
    saved = meta[list(paths)[0]]['pool_sha256']
    if saved != cur:
        die(f'eval の pool_sha256 {saved[:8]} が現行の control/sparring_pool.json {cur[:8]} と違う'
            '（帯の定義が当時と変わっている。プール改編後は帯を当時の JSON から取ること）')
    names = list(paths)
    ref = set(idx[names[0]])
    for n in names[1:]:
        if set(idx[n]) != ref:
            die(f'{n} のセル集合が {names[0]} と違う')
    return meta, idx, ref


def contrast(G, coefs, cells, field):
    f = FIELDS[field]
    by_seed = defaultdict(list)
    for k in cells:
        by_seed[k[1]].append(sum(w * f(G[n][k]) for n, w in coefs.items()))
    sd = [statistics.mean(xs) for xs in by_seed.values()]
    m = statistics.mean(sd)
    se = statistics.stdev(sd) / math.sqrt(len(sd))
    # 1.96（正規）は `evaluate.py::paired_delta` と同じにするため。n=50 なら t(49)=2.010 で
    # 半幅が 2.5% 広がるだけで、本稿の符号判定はどちらでも変わらない（Codex P2-5 で確認）。
    return m, m - 1.96 * se, m + 1.96 * se


def sig(lo, hi):
    return '有意' if (lo > 0 or hi < 0) else '検出不能'


def split(G, coefs, cells):
    """(Δmargin, Δown, Δopp, denial 寄与%)。恒等式が壊れたら止める。"""
    mm, mlo, mhi = contrast(G, coefs, cells, 'margin')
    ow, olo, ohi = contrast(G, coefs, cells, 'own')
    op, plo, phi = contrast(G, coefs, cells, 'opp')
    vals = (mm, mlo, mhi, ow, olo, ohi, op, plo, phi)
    if not all(math.isfinite(v) for v in vals):
        die(f'有限でない値が出た: {vals}')   # abs(NaN) > 1e-6 は False なので下を素通りする
    if abs((ow - op) - mm) > 1e-6:
        die(f'恒等式が壊れた 残差 {(ow - op) - mm}')
    share = (-op / mm * 100) if abs(mm) > 1e-9 else float('nan')
    return (mm, mlo, mhi), (ow, olo, ohi), (op, plo, phi), share


def report(G, KEYS, STRONG, rows):
    for band, cells in (('全プール', KEYS), ('強帯のみ', {k for k in KEYS if k[0] in STRONG})):
        print(f'\n=== {band}（{len(cells)} セル）===')
        print(f'{"":42s} {"Δmargin":>10s} {"Δown(生産)":>28s} {"Δopp(相手)":>28s}  denial寄与')
        for lab, co in rows:
            (mm, _, _), (ow, olo, ohi), (op, plo, phi), share = split(G, co, cells)
            print(f'{lab:42s} {mm:+10.1f} '
                  f'{ow:+9.1f}[{olo:+9.1f},{ohi:+9.1f}]{sig(olo, ohi):>6s} '
                  f'{op:+9.1f}[{plo:+9.1f},{phi:+9.1f}]{sig(plo, phi):>6s} {share:+6.0f}%')


def by_opponent(G, KEYS, STRONG, coefs, label):
    print(f'\n=== 相手別 / {label} ===')
    print(f'{"相手":32s} {"帯":6s} {"Δmargin":>9s} {"Δown":>9s} {"Δopp":>9s} {"Δopp CI95":>24s}')
    out = []
    for opp in {k[0] for k in KEYS}:
        cells = {k for k in KEYS if k[0] == opp}
        (mm, _, _), (ow, _, _), (op, plo, phi), _ = split(G, coefs, cells)
        out.append((op, opp, mm, ow, plo, phi))
    for op, opp, mm, ow, plo, phi in sorted(out):
        name = opp.replace('agents/', '').replace('/main.py', '')
        tier = 'strong' if opp in STRONG else 'other'
        print(f'{name:32s} {tier:6s} {mm:+9.1f} {ow:+9.1f} {op:+9.1f} '
              f'[{plo:+9.1f},{phi:+9.1f}] {sig(plo, phi)}')


def band_test(G, KEYS, STRONG, coefs, mid):
    """帯によって分解の中身が違うか —— **事後に選んだ探索的な対比**（Codex P1-2）。

    相手別の表を眺めて「強帯だけ Δopp が負だ」と言うのは 13 回の目視検定であって、
    多重比較の統制が無い。それよりはマシ、という位置づけの 1 本。**相手別の表を見た
    あとに帯の切り方を決めているので、これも確証的な検定ではない**（同じデータ上で
    「本命」と呼び直しても事前検定にはならない）。確証は別 seed 帯の追試で取る。
    ここではシードごとに
    「強帯セルの平均 − 中間帯セルの平均」を取り、50 シードで CI を付ける（検定 1 本）。
    中間帯に starter / georgy を入れないのは、相手の最終資金が $3.6k / $7.9k しかなく
    **削る余地が無い（床効果）**ため。gen0044 / gen0045 は $86-88k 稼ぐので床ではない。
    """
    print(f'\n=== 帯の対比（強帯 − 中間帯 {sorted(m.replace("agents/", "").replace("/main.py", "") for m in mid)}）===')
    print('  ※ 相手別の表を見たあとに決めた探索的な対比。名目 95% CI（多重比較 未補正）')
    for field in ('margin', 'own', 'opp'):
        by_seed = defaultdict(dict)
        for band, cells in (('s', {k for k in KEYS if k[0] in STRONG}),
                            ('m', {k for k in KEYS if k[0] in mid})):
            acc = defaultdict(list)
            for k in cells:
                acc[k[1]].append(sum(w * FIELDS[field](G[n][k]) for n, w in coefs.items()))
            for s_, v in acc.items():
                by_seed[s_][band] = statistics.mean(v)
        missing = [s_ for s_, v in by_seed.items() if len(v) != 2]
        if missing:
            die(f'片方の帯にしかセルが無いシード {missing[:5]}（黙って落とさない）')
        d = [v['s'] - v['m'] for v in by_seed.values()]
        m_ = statistics.mean(d)
        se = statistics.stdev(d) / math.sqrt(len(d))
        lo, hi = m_ - 1.96 * se, m_ + 1.96 * se
        print(f'  Δ{field:7s} 強帯 − 中間帯: {m_:+9.1f} [{lo:+9.1f},{hi:+9.1f}] n={len(d)}  {sig(lo, hi)}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pair', nargs=2, metavar=('BASE_EVAL', 'CAND_EVAL'),
                    help='任意の 2 本の eval JSON で累積 + 相手別だけを出す')
    a = ap.parse_args()

    pool = json.loads((ROOT / 'control/sparring_pool.json').read_text())
    ents = pool['opponents'] if isinstance(pool, dict) and 'opponents' in pool else pool
    # evaluate.py:162-165 / :276 と同じ規則: enabled な相手だけ、キーは path のみ。
    STRONG = {e['path'] for e in ents if e.get('enabled', True) and e.get('tier') == 'strong'}

    if a.pair:
        paths = {'base': a.pair[0], 'cand': a.pair[1]}
        rows = [(f'累積: {Path(a.pair[1]).stem} − {Path(a.pair[0]).stem}',
                 {'cand': 1, 'base': -1})]
    else:
        paths = {n: f'records/eval_{n}.json' for n in LINEAGE}
        rows = LINEAGE_ROWS
    meta, G, KEYS = load(paths)

    # シードあたりのセル数が不揃いだと「シード平均の平均」の線形性が崩れる。
    for band, cells in (('全プール', KEYS), ('強帯', {k for k in KEYS if k[0] in STRONG})):
        cnt = defaultdict(int)
        for k in cells:
            cnt[k[1]] += 1
        if len(set(cnt.values())) != 1:
            die(f'{band}: シードあたりのセル数が不揃い {sorted(set(cnt.values()))}')

    m0 = meta[list(paths)[0]]
    print(f'共通セル {len(KEYS)}（うち強帯 {len({k for k in KEYS if k[0] in STRONG})}）'
          f'／ pool_sha {m0["pool_sha256"][:8]} ／ seeds {m0["seeds"]} '
          f'seed_base {m0["seed_base"]}')
    print('Δmargin = Δown − Δopp（セル単位の恒等式）。denial 寄与 = −Δopp / Δmargin')
    report(G, KEYS, STRONG, rows)
    by_opponent(G, KEYS, STRONG, rows[-1][1], rows[-1][0].split(':')[-1].strip())
    want = {'agents/gen0044/main.py', 'agents/gen0045/main.py'}
    mid = want & {k[0] for k in KEYS}
    if mid == want:
        band_test(G, KEYS, STRONG, rows[-1][1], mid)
    else:
        # 1 体だけで走らせると「中間帯」の意味が変わる（対比の相手が別物になる）。
        print(f'\n(帯の対比は省略: 中間帯 {sorted(want - mid)} がプールに居ない)')


if __name__ == '__main__':
    main()
