# 評価を 2 台目のマシンに逃がす（2026-09-05 設定）

> 公開版の注記: ホスト名・パスは一般化してある（`remote` は ssh のホスト別名、`~/work/` は作業ディレクトリの例）。

評価は 1,100 戦 × 720 step で CPU バウンド。ローカル（Apple Silicon / 10 コア）1 台だと
50 シード 1 本に約 14 分かかり、その間ほかの評価が回せない。Mac Pro を
**2 台目の評価機**として使えるようにした。

## 前提: 結果はビット一致する

`agents/gen0026 vs gen0024` を seed 42 / 7 で両機で走らせ、`final_money` が
**完全一致**することを確認済み（53361/38767・74205/54592）。
したがって**両機の結果は同じプールに混ぜてよい**。

ただしこれは「エージェントがターン 1 秒の制限に余裕がある」間だけ成り立つ。
Mac Pro は 1 コアが遅い（下表）ので、上限ぎりぎりの実装を入れたら
**Mac Pro 側だけ TIMEOUT して結果が分岐しうる**。
`statuses` に TIMEOUT が出たら、まず機械差を疑うこと。

## 性能

| | ローカル | Mac Pro |
| --- | --- | --- |
| CPU | Apple Silicon / 10 コア | Xeon E5-2697 v2 2.70GHz / 12 コア 24 スレッド（2013年） |
| メモリ | 16 GB | 64 GB |
| 1 コア（同じ純 Python ループ） | 0.104 s | 0.199 s（**約 1.9 倍遅い**） |
| 1 戦（720 step・単独実行） | 6.0-7.2 s | 9.6-10.2 s |
| 使う `--jobs` | 8 | 20 |
| **並列スループット（実測）** | **79 戦/分**（1,100 戦 838 s） | **59 戦/分**（528 戦 535 s） |

**Mac Pro は 1 コアが約 1.9 倍遅く、並列スループットもローカルの約 0.75 倍**。
スレッド数（24 vs 10）では埋まりきらない。ただし**独立した 2 台目**なので、
2 台同時に回せば合計スループットは **約 1.75 倍**になる。
長い方（50 シード）をローカル、短い方（24 シード・スモーク・リプレイ生成）を
Mac Pro に振ると待ちが減る。

（`--jobs` を 20 より増やしても HT の 12 論理コアぶんは実効 1.25 倍程度にしかならないので、
共用機であることも考えて 20 で止めている。）

## セットアップ（済み。作り直すとき用）

macOS 12.7.6 の system python は 3.9 で、`kaggle-environments>=1.26` は 3.11 以上を要求する。
`cryptography` が x86 macOS でソースビルドに落ちて失敗するので、**依存を入れない**のが要点。

```bash
ssh remote 'curl -LsSf https://astral.sh/uv/install.sh | sh'   # uv をユーザー領域に
rsync -az --exclude .venv --exclude records --exclude replays --exclude .git ./ remote:~/work/kaggri-micro/
ssh remote 'export PATH=$HOME/.local/bin:$PATH; cd ~/work/kaggri-micro
  uv venv --python 3.11 .venv
  uv pip install --python .venv/bin/python --no-deps kaggle-environments==1.32.7
  uv pip install --python .venv/bin/python jsonschema requests httpx'
```

`--no-deps` にしているので `litellm` / `google-auth` / `numpy` は入らない。起動時に
他の env（cabt / halite / lux_ai_s3 …）の読み込み失敗が stderr に出るが、
**kaggriculture には無関係**なので無視してよい。

## 使い方

```bash
# 1) コードと、比較に使うベースライン eval JSON を送る（records は rsync 対象外なので個別に）
rsync -az --exclude .venv --exclude records --exclude replays --exclude .git ./ remote:~/work/kaggri-micro/
rsync -az records/eval_gen0026_s24.json remote:~/work/kaggri-micro/records/

# 2) 走らせる（ssh は繋ぎっぱなしにせず nohup で切り離す）
ssh remote 'cd ~/work/kaggri-micro && nohup .venv/bin/python -u harness/evaluate.py \
  --candidate agents/gen0027/main.py --pool control/sparring_pool.json \
  --seeds 24 --seed-base 1000 --jobs 20 \
  --baseline records/eval_gen0026_s24.json --out records/eval_gen0027_s24.json \
  > logs/g27.log 2>&1 < /dev/null &'

# 3) 進捗と回収
ssh remote 'tail -1 ~/work/kaggri-micro/logs/g27.log'
rsync -az remote:~/work/kaggri-micro/records/eval_gen0027_s24.json records/
```

## 注意

- **置き場は決めた作業ディレクトリ（例では `~/work/`）配下だけ**。ホーム直下に作らない。
  2026-09-05 にこの手順が `~/kaggri-micro/` を作ってしまい、2026-09-06 に退避のうえ削除した
  （中身は `feat/micro-execution` のスナップショットで、固有の成果物は無かった）。
  ログ・一時ファイル・キャッシュも含めて `~/work/` の外に置かない。
- **共用機**。`--jobs` は 20 まで（24 スレッド中 4 は空けておく）。
- 送るのはコードとプールだけ。`records/` と `replays/` は rsync から外してある
  （容量が大きく、正は手元）。
- **提出はローカルからだけ行う。** Mac Pro に Kaggle 認証情報は置かない。
