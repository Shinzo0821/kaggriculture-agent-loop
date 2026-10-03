# agents/sparring — 公開 Notebook 由来のスパーリング相手プール

> **公開版の注記**: このディレクトリにあった公開 Notebook 由来のエージェント本体（`<slug>/main.py` ほか 10 体ぶん）は
> **他者の著作物なので公開リポジトリには含めていない**。残してあるのは、自分で書いた出典一覧と強さプローブの記録だけ。
> 再現するには下表の出典 Notebook から各自取得し、`agents/sparring/<slug>/main.py` として置く
> （`control/sparring_pool.json` がこのパスを参照する）。プールを作り直したら `harness/rate_pool.py --write` と
> 王者ベースラインの取り直しが必要（`ops/reform_pool.py`）。

**役割: ローカル評価の対戦相手専用。提出には絶対に使わない**（他者のコード。`ops/preflight_submit.py` の候補にしないこと）。

各ディレクトリは `main.py`（単一ファイル自己完結、トップレベル `agent(obs)`）と `meta.json`（出典URL・著者・ライセンス・戦略要約）。抽出日 2026-09-04。ライセンスは kaggle CLI の kernel-metadata に項目が無いため、ソース内に明記のある pilkwang（Apache-2.0）以外は「unknown (Kaggle notebook default Apache-2.0 assumed)」。

## 一覧（強さプローブ: `harness/evaluate.py --opponents starter,agents/gen0018/main.py --seeds 10 --jobs 8`、各相手 20 試合＝10シード×両席、seed_base 1000）

| slug | 出典 | 戦略（一行） | vs starter 勝率 / 平均$差 | vs gen0018 勝率 [Wilson95] / 平均$差 | 候補 平均終盤$ / gen0018 平均$ | 1試合 秒（単走, seed7 vs starter） | probe 40試合 秒（jobs8） |
|---|---|---|---|---|---|---|---|
| `boatlee_v16` | [boatlee/v16-rc5-high-score-8c-4s-premium-market-lead](https://www.kaggle.com/code/boatlee/v16-rc5-high-score-8c-4s-premium-market-lead) | Fixed 719-action tape reconstructed from N.Lugovoy's replays (8 COW/4 SHEEP, 3 quadrants, WHEAT+STRAWBERRY+MELON) + 1-turn front-run of MELON/MILK/STRAWBERRY/WOOL sales + weed repair overlay. | 1.00 / +154,188 | **1.00** [0.84, 1.00] / +86,223 | 132,510 / 46,287 | 2.03 | 14.0 |
| `boatlee_v29` | [boatlee/v29-r1-adaptive-market-hysteresis](https://www.kaggle.com/code/boatlee/v29-r1-adaptive-market-hysteresis) | Fixed production tape (RngRng replay, 3 quadrants) + stateful market controller: price-gated tranche sales of MILK/WOOL/STRAWBERRY/MELON with hysteresis, public-flow estimator, mirror guard, tail liquidation. | 1.00 / +133,328 | **1.00** [0.84, 1.00] / +78,416 | 115,028 / 36,612 | 2.08 | 14.7 |
| `georgy` | [georgymamarin/kaggriculture-visualized-what-every-crop-pays](https://www.kaggle.com/code/georgymamarin/kaggriculture-visualized-what-every-crop-pays) | 'Carrot Crew' beginner bot: 6 carrot tiles around shed, water daily, sell on harvest. Weak; a sanity floor just above starter. | 1.00 / +4,110 | **0.00** [0.00, 0.16] / -65,049 | 8,043 / 73,091 | 0.98 | 7.3 |
| `kaito_v48` | [kaitofukami/40-40-early-floor-39-46-top-10-v48-fast-routes](https://www.kaggle.com/code/kaitofukami/40-40-early-floor-39-46-top-10-v48-fast-routes) | v48 Fast-Climber Sparse Route Hybrid: v43/v44 public backbone tape + first-shop fast-route continuations + BAKERY capital recovery; one child policy call per turn (bundled sub-packages v23/v44/v48). | 1.00 / +142,180 | **1.00** [0.84, 1.00] / +89,532 | 133,734 / 44,202 | 2.34 | 17.2 |
| `pilkwang` | [pilkwang/kaggriculture-structured-economic-policy](https://www.kaggle.com/code/pilkwang/kaggriculture-structured-economic-policy) | Fork of Kaito Fukami v58 minimax closed-loop agent (public-state branching over known action streams, v49 residual controller + v50 route/value hybrid), unchanged except loader shim. Last def agent() in file is the entrypoint. | 1.00 / +148,697 | **1.00** [0.84, 1.00] / +75,046 | 110,433 / 35,387 | 3.66 | 46.4 |
| `prvsiyan_v189c` | [prvsiyan/kaggriculture-frontier-the-moon-counts-melons](https://www.kaggle.com/code/prvsiyan/kaggriculture-frontier-the-moon-counts-melons) | Moon V189C: PASS at step 0 (delay capital until first shop reveal at step 72), then delayed farm schedule; on first-shop YARN_STORE converts up to 5 cow slots into sheep/wool. | 1.00 / +148,782 | **1.00** [0.84, 1.00] / +80,146 | 119,676 / 39,530 | 2.13 | 15.3 |
| `rayk_c95` | [raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta](https://www.kaggle.com/code/raykkretzschmar/kaggriculture-findings-from-zero-to-top-meta) | C95: distilled trajectory of Lev Neganov episode 91587143 + c17/c27 controller (1-turn front-run of MELON/STRAWBERRY/MILK/WOOL, glut weights, mirror-clone detection, weed recovery, opening feed denial). | 1.00 / +151,812 | **1.00** [0.84, 1.00] / +81,775 | 124,380 / 42,605 | 2.04 | 15.0 |
| `sokolovsky` | [andrewsokolovsky/kaggriculture-breaking-the-tie](https://www.kaggle.com/code/andrewsokolovsky/kaggriculture-breaking-the-tie) | V21-R1 TEACHER only (the notebook's learned DAgger student needs torch training and is not embedded): public-state multi-route agent that bundles Moon/Mutoy/Munib agents and routes between them at checkpoints. | 1.00 / +140,776 | **1.00** [0.84, 1.00] / +76,377 | 116,322 / 39,944 | 2.94 | 24.3 |
| `tetsutani_adaptive` | [tetsutani/adaptive-farming-strategy-for-kaggriculture](https://www.kaggle.com/code/tetsutani/adaptive-farming-strategy-for-kaggriculture) | Adaptive multi-route controller: picks among 4 fixed tapes (10C4S/8C6S/6C8S 3-quadrant, 6C12S 4-quadrant on first-shop YARN) by early shop unlocks, with execution guards. | 1.00 / +145,814 | **1.00** [0.84, 1.00] / +78,519 | 116,414 / 37,895 | 2.21 | 15.6 |
| `yhay81_router` | [yhay81/three-day-shop-router](https://www.kaggle.com/code/yhay81/three-day-shop-router) | hybrid_shopforge_3day_frontier_state_router_r5 (C++): base action tape in 72-turn blocks; at turn 360 swaps block on first-shop BAKERY/PET_CAFE public-state rules; 6-day budget guard sells surplus only if block cannot afford purchases. Native policy compiled locally (macOS dylib embedded, extracted to tmp). | 1.00 / +148,783 | **1.00** [0.84, 1.00] / +81,870 | 118,115 / 36,245 | 1.38 | 28.4 |

プローブ結果 JSON: `records/sparring_probe_<slug>.json`（gitignore）。スモーク: `records/sparring_smoke/<slug>.txt`。

## 所要時間の目安

- 純Python勢は 1試合 2〜4 秒（starter 相手, 720ステップ, M-series Mac）。pilkwang（317KB, v58 minimax closed-loop）が最も重く 1試合 ~3.7s / 40試合 46s。sokolovsky（3エージェント同梱ルータ）が次点 ~3s。georgy は ~1s。
- 8並列で 1相手 20試合（10シード両席）あたり 7〜25 秒。10相手 × 20試合 = 200試合 で約 3〜4 分。100シード両席（2000試合）なら 30〜40 分程度。

## 除外したもの

- `tetsutani_shape-the-shop-work-the-pasture`: main.py に Linux 用 ELF `.so`（C++ ポリシー）を base64 同梱。C++ ソースは Notebook に無く macOS では実行不可。
- `yhay81_six-day-public-state-fieldbook`: エージェントソースが Kaggle Dataset (`/kaggle/input/six-day-public-state-agent-source`) 参照で Notebook 内に無い。
- `cjlcjlcjl_what-the-top-farms-do`: リプレイ解析のみでエージェント無し。
- `andrewsokolovsky` の学習済み DAgger 学生ポリシー: torch 学習を Notebook 内で実行しないと生成されない。代わりに同梱の教師 **V21-R1** を `sokolovsky` として採用。
- `raykkretzschmar` は C92/C94/C95 の3版を同梱。最終版 C95 のみ採用（`rayk_c95`）。`pilkwang` は同一ファイル内に `def agent` が5つ（旧版の残骸）; kaggle_environments と同じく最後の定義が入口。

## 注意

- `yhay81_router` は C++ ポリシーを Apple clang で `agent.dylib` にビルドし gzip+base64 で main.py に同梱、初回ロード時に一時ディレクトリへ展開する（ファイルI/O あり、**macOS arm64 専用**）。Linux で使う場合は Notebook の `source/*.cpp` を g++ で再ビルドして差し替える。C++ ソースは scratchpad にのみ展開しており本リポジトリには含めていない。
- 多くの相手は「固定アクションテープ＋公開状態で分岐」型（boatlee/kaito/prvsiyan/tetsutani/rayk/yhay81）。テープは seed に依存しない固定スケジュールなので、同じ相手に対しシード間の分散は小さい。ミラー検知（rayk_c95, boatlee_v29）を持つものがあり、自陣と相手が似た構成だと売り方を変える。
- **gen0018 は全相手に 0/20（georgy 以外）**。終盤資金は gen0018 ~$36-46k に対し公開勢 $110-134k。
