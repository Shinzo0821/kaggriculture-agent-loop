# EXP0021: 現金リザーブ + 土地2枚キャップで gen0020 の starvation を是正（gen0021）

- 日付: 2026-09-05 ／ 世代: gen0021（親: gen0020）
- 仮説: gen0020 の破綻(EXP0020)は「維持力を超えた拡張＝メロン proceeds 全額再投資 → 現金$20 → feed 買えず動物 escape」。全 discretionary buy(土地/動物/種)に現金リザーブ $400 を課し、土地を2枚(NE)までに抑えれば proceeds が運転資金として残り、動物 escape が止まって資金曲線が立ち上がる。
- 変更:
  1. `RESERVE=400` 新設。`BUY_LAND`/`BUY_ANIMAL`/`BUY_SEED` は RESERVE を残す額までしか買わない（feed 小麦の `BUY_PRODUCT` は維持最優先で例外扱い、リザーブを課さない）。
  2. `land_target` を最大2(NE d6)に変更。SW(3枚目)を買わない → SW の2波メロン/イチゴ/小麦タイルは locked のまま自動スキップ。

## 結果

- スモーク vs gen0018: seed42 **$29.8k**(相手$48.4k) / seed7 **$42.9k**($74.4k) / seed100 **$28.7k**($42.0k)。profile max 0.016s(<1s OK)。3戦とも敗北。
- プール評価（`records/eval_gen0021.json`、seeds 24・両席・9体・432試合、9分）:
  - `pool.rating` = **426.8 ±31.2**（win_rate 0.20、money_mean **$27.8k**、slope_mean 1,984）
  - gate deltas は `baseline_compatible=false`（王者ベースラインは 50 シード、本評価は 24 シード）で None。ただし **pool.rating は固定相手レーティング尺度なので王者と直接比較可能**: gen0018=905 に対し gen0021=427 で **約 −478**。money_mean も $52.1k vs $27.8k。
- リプレイ実測(seed42): 動物は **COW8 SHEEP4 が d11-27 安定**（gen0020 は d14 に3頭へescape）＝ starvation は解消。資金は d10 IPO で $24 に落ちた後 d11 $2.0k → d24 $17k → 最終 $29.8k と単調増加。
- 判定: **改善だが非昇格・非提出**（gen0020 の $2.6-11k → $28k で 4-5倍。しかし王者 gen0018 の約半分）。

## 学び（次世代の設計方針を決める重要な分岐）

1. **リザーブ規律は over-reinvestment 破綻を確実に止める**。「現金 buffer を0にする再投資」は禁忌。拡張の各購入は feed を賄える現金を残す前提でしか実行してはいけない。これは以後の全世代の恒久ルールにする価値がある。
2. **しかし、拡張自体が現状の labor 効率では割に合わない**。gen0021 は 2クアドラント・12頭・12hands で $27.8k、gen0018 は 1クアドラント・~7hands で $52.1k。**拡張の追加コスト(feed/water/hire/移動)が追加収益を上回っている**。残る症状は chronic partial under-feeding（h12 で unfed 7-11/日）＝12頭を毎日 feed しきれず milk/wool が絞られる。
3. **ボトルネックは「日次骨格」ではなく「labor 割当効率」に移った**。上位LBが3クアドラントを回せるのは feed/water のユニット割当が緊密だから。丸ごと骨格を写しても、割当効率が追いつかないと拡張は負債になる。
4. **戦略の分岐点**: (a) 拡張路線を続けるなら labor 割当効率（feed スループット・移動最小化・動物の適正数化）を詰める、(b) それが重いなら、実証済みの集中型 gen0018 を土台に小改善へ戻る。次サイクルは Strategist を呼んで上位リプレイの「12hands でどう12頭を毎日 feed し切っているか」の keystone を突き合わせるのが有効。
