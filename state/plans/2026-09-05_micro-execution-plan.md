# ミクロ実行改善プラン（2026-09-05）— 「計画を最後まで実行する」世代群

- 作成: 2026-09-05（Fable、ユーザー対話から）／ 状態: **未着手。次セッション（Opus）が実装する**
- 根拠: `knowledge/analysis/2026-09-05_micro-audit-gen0022.md`（3 試合の unit-hour 監査。数字は全部そこ）
- 試作スクリプト: `knowledge/analysis/2026-09-05_micro_audit_prototype.py`（P0 で `harness/` に本実装する）
- 守る規約: `CLAUDE.md`（検出限界 12/24/50、強帯必読、昇格前 Codex レビュー、1 世代 1 構造変更）、
  `knowledge/IDEA_POLICY.md`（該当カテゴリを各項目に明記）、`.claude/agents/implementer.md`（mechanisms 台帳）

## 0. 結論（30 秒版）

ユーザー仮説 3 つは全部正しかった。ただし損失の主因は「移動」そのものではなく、**移動のせいで植付が
最下位優先度のまま締め切られて土地が空く**ことと、**収穫前に水をやらない（小麦 3/4・メロン 5/6）**、
**肥料をイチゴに使わない（1 回収量 1 vs 強帯 2）** の 3 つ。いずれも**ゲーム規則から導ける修正**で、
チューニングではない。まず計測を足し（P0）、次に実行の正しさ（gen0024）、肥料（gen0025）、労働（gen0026）、
その上で 3 クアドラント再挑戦（gen0027）。**順序を入れ替えない**（労働効率が無いまま土地を増やすと gen0023 の再演）。

| 世代 | 変えるもの | 主 KPI（決定論的・スモークで判定可） | 金 KPI（24→50 シード） |
| --- | --- | --- | --- |
| P0 | `harness/micro_audit.py` + `control/targets.json` の `micro` | 3 リプレイで今日の数字を再現 | — |
| gen0024 | 収穫前水やり／PLANT 朝一／空きタイル fallback／死に種禁止 | 小麦 ≥3.9・メロン 6.0・利用率 ≥78%・未使用タイル 0 | 対応付き資金差 CI 下限 >0、強帯資金 >0 |
| gen0025 | 肥料をイチゴ（→メロン）へ | イチゴ 1 回収量 ≥1.9 | 同上 |
| gen0026 | ゾーンの空間コンパクト化・越境 claim 禁止 | 3 歩以上 ≤12%・最終 WATER ≤h14 | 同上（資金は動かなくてもよい。次の前提） |
| gen0027 | SW 解禁（hands 12 のまま） | 75 タイルで利用率 ≥80%・unfed/uncared 0 | 強帯資金 >0 が必須 |

## 1. 何が起きているか（コード行つき）

`agents/gen0022/main.py` を読む順:

| 症状（監査の数字） | 原因 | 行 |
| --- | --- | --- |
| 小麦 2.88/4・メロン 4.91/6。収穫時 `watered_today=False` が 45/45 | ripe になった瞬間 HARVEST（2.2）を出し、ripe タイルの WATER を抑止 | 229-237 |
| 空きタイル 8-17/50（d10-24）、PLANT が h14-20 に 1-3 回 | PLANT 優先度 3.30-3.40 が全 todo の最下位。WATER が h21 まで続くので順番が来ず `LAST_PLANT_HOUR=20` で締め切り | 63/76/90（plant_pri）, 301, 314 |
| 未植付の種 5-15 個が毎日残り、窓が閉じて死に種（$440/試合） | 種は「空き計画タイル − 所持種」で買うが、その日に植えられるかを見ない | 615-624 |
| (6,1)(9,1)(8,1)(4,0) が試合終了まで空く | 計画表がタイル→作物→窓の固定表で、窓を逃したタイルの代替作物が無い | 56-92 |
| (4,3)(4,4)(5,4) を 30 日使わない | (4,3) は計画に無い。シェッド 4 タイルは「常に空ける」設計。エンジンは移動を塞がない（`kaggriculture.py` 322-330）ので不要 | 51-53 |
| 3 歩以上歩いてから行動 29%（強帯 11%）、最終 WATER h20-23 | (a) ゾーンがクアドラント内 row-major の連続ブロック＝行末で折り返すと 5 タイル離れる。(b) ゾーンが片付いた hand が global fallback で他ゾーンの todo を先に claim（unit 順）し、所有者が弾かれて別の todo へ歩く。(c) CARE/FEED の「最寄りだけ claim」規則で通りすがりの hand が所有者を弾く（gen0023 fix1 と同じ穴、王者には未適用） | 378-386, 429-453, 500-501 |
| 肥料を全部売る（FERTILIZE 0） | 肥料の使い道が無い。`ALWAYS_SELL` に FERTILIZER | 105, 538-542 |

## 2. P0: 計測を先に足す（IDEA_POLICY 3 番＝最優先。半日）

**やること**

1. `knowledge/analysis/2026-09-05_micro_audit_prototype.py` を `harness/micro_audit.py` に移す。出力は現状のまま＋
   `--json`（EXP に貼る用）と `--assert`（合格基準の機械判定。失敗で exit 1）。両プレイヤーを 1 コマンドで並べる `--both`。
2. `control/targets.json` に `micro` 節を足す（出所: 上の監査の強帯 3 体）:
   `tile_util ≥ 0.83` ／ `moves3plus_share ≤ 0.12` ／ `wheat_yield 4.0` ／ `melon_yield 6.0` ／ `strawberry_yield 2.0` ／
   `last_water_hour ≤ 14`（強帯は h18-23 だが、こちらの植付飢餓を止める目標として置く。**derived ではなく目標値**と明記）。
3. `CLAUDE.md` の EXP テンプレに欄を 1 行足す: `- ミクロ指標: 利用率 / 未使用タイル / 収量(小麦・メロン・イチゴ) / 3歩以上% / 最終WATER時刻`。
4. `ops/NIGHTLY.md` の実装後手順（`audit_replay.py` の隣）に `micro_audit.py --assert` を足す。
   `.claude/agents/implementer.md` の「実装後は必ず」にも同じ 1 行。
5. `ops/daily_report.py` の採用判断シートに王者のミクロ 5 指標を 1 行出す（王者リプレイは毎晩の `collect_feedback` の DL 分でよい）。

**テスト**: `harness/run_match.py agents/gen0022/main.py agents/sparring/kaito_v48/main.py --seed 42 --replay /tmp/x.json`
→ `micro_audit.py /tmp/x.json --player 0` が利用率 66%・小麦 2.88・メロン 4.91・イチゴ 1.00・未使用 [(4,3),(4,4),(5,4),(6,1)] を再現すること。
`--assert` は gen0022 で**落ちる**こと（回帰テストの意味を持つ）。

## 3. gen0024: 計画実行の正しさ（IDEA_POLICY 1 番「日次骨格」＋ 4 番「割当構造」。1 日）

4 点とも「今の計画を書いてある通りに実行する」修正で、互いにトレードオフが無い（全部が単調に得）。
だから 1 世代に束ねてよい。**ただし労働割当（ゾーン）は触らない**＝gen0026 と分離する。

### 3-A 収穫前に水をやる（derived）

- `main.py:229-237`: 一時作物（WHEAT/MELON）が ripe かつ `not watered_today` かつボーナス窓内（小麦 age ≤4、メロン age ≤12）なら
  **WATER を HARVEST より先に**出す（同じタイルの HARVEST todo はその時間は出さない）。窓を過ぎた ripe（小麦 age ≥5）は
  従来通り即収穫（decay 開始）。イチゴ（ongoing）は関係ない。
- 期待: 小麦 3→4（+33%）、メロン 5→6。s42 換算で小麦 70 回・メロン 11 回。

### 3-B PLANT を朝の日課に入れる（derived: 植付日は `consecutive_unwatered=1` で始まるので、当日中の水やりが必須＝朝に植える方が安全）

- 日課の固定順を **FEED → CARE → PLANT → WATER → HARVEST** にする。実装は `plant_pri` を WATER より小さい値に
  置き換える（例 1.5 帯）。**数値は順序を表すだけ**なので mechanisms では `task_priorities` の constants に
  `plant: "< water"` と順序で書き、tuned にしない。
- `LAST_PLANT_HOUR` は残す（夕方植えは枯れる）。

### 3-C 空きタイルのフォールバック作付け（derived）

- 「解放済み・空（None）・どの計画窓も今開いていない・パスチャ予定でもない」タイルに **WHEAT を植える**
  （種 $10・4 日回転・飼料にも売りにも使える唯一の作物）。d25 以降は植えない（`LAST_PLANT_DAY`）。
- これで (4,3)(6,1)(9,1)(8,1)(4,0) と、計画窓を逃した全タイルが自動で埋まる。**計画表に個別タイルを足す必要はない。**
- シェッド 4 タイル (4,4)(5,4)(4,5)(5,5) も対象に含める（`main.py:51` のコメントを更新）。エンジン確認済み:
  移動は塞がれず、PICKUP/DROP/PLACE-into-shed はタイル演算より先に解決（`kaggriculture.py` 322-330, 345-400）。
  **パスチャはシェッドタイルに建てない**（PLACE の分岐が紛らわしいだけで壊れはしないが、避ける）。
- 種の購入（`main.py:615-624`）は fallback 分の小麦も数える。

### 3-D 死に種を買わない（derived）

- 種の購入数 = 「今この時刻から窓の閉鎖までに植えられる空きタイル数」− 所持種。
  `hour > LAST_PLANT_HOUR` の日は翌日が窓内の時だけ買う。窓の最終日は h ≤ LAST_PLANT_HOUR の時だけ買う。
- イチゴ・メロンの死に種は $100/$80 なので、これは損失防止であって収益ではない。

### gen0024 の手順

1. `agents/gen0024/` を gen0022 から作る（gen0023 は非昇格なので親にしない。gen0023 の codex fix 2 件は gen0026 で扱う）。
2. `meta.json`: parent gen0022、mechanisms に `water_before_harvest`（derived）／`fallback_wheat`（derived）／
   `seed_purchase_window`（derived）を追加、`task_priorities` の constants に plant の順序を追記。
3. スモーク 3 シード（42/7/100）vs kaito_v48 で **`micro_audit.py --assert`**:
   小麦 ≥3.9・メロン 6.0・イチゴは変化なし・利用率 ≥78%（2 クアドラント。強帯の 83% は 3 クアドラントなので目標を下げる）・
   一度も使わなかったタイル 0・d15 の未植付種 ≤2・unfed/uncared 0・no-op 0。
   `harness/profile_agent.py` で最悪 <1s。
4. **24 シードで方向判断**（`ops/eval_queue.py submit --gen gen0024 --seeds 24 ...`）: 対応付き資金差の符号と
   `gate.strong_money_delta_paired` を見る。両方正なら 50 シードへ。
5. 50 シード → `gate.pass` → Codex レビュー（`knowledge/REVIEW_CHECKLIST.md` 7 観点。特に 3-A の
   「窓を過ぎた ripe を水やりで止めない」と 3-C の「パスチャ予定タイルに小麦を植えない」）→ `review` を meta.json → preflight promote。
6. EXP0024 を書く。`却下した小手先案` に「RESERVE 400→300（d0 メロン 8 粒のため）／ 禁止 1 番」「hands 12→10／禁止 2 番」を残す
   （どちらも監査で誘惑される案だが禁止側）。

## 4. gen0025: 肥料をイチゴに使う（IDEA_POLICY 2 番「未使用の行動」＋ 5 番「強帯の型」。半日）

- エンジン: イチゴの EOD 生産は `was_watered and fertilized_until_day >= current_day` で +2（`kaggriculture.py` 799-801）。
  FERTILIZE は `fertilized_until_day = day+2`（481 行）。生産は planted+9, +11, +13, +15 の EOD。
  → **planted+9 と planted+13 に 1 個ずつ撒けば 4 回全部が 2 倍**（1 株 2 個で +4 個）。
- 実装: 動物の `COLLECT_FERTILIZER`（4.0）で拾った肥料を売らず、当日が撒き日（age 9 または 13、かつ未肥料）の
  イチゴタイルに `FERTILIZE` todo（優先度は WATER の直前。撒く前に水やりしても順序は関係ない: EOD 判定）。
  余った肥料だけ従来通り SELL。物流は「肥料を持つ hand だけが FERTILIZE を取れる」（FEED の小麦と同じ `need`）。
- 需要: イチゴ 11 株（2 クアドラント）×2 = 22 個/波、供給 12 個/日 → 足りる。gen0027 で 27 株になっても 54 個/10 日で足りる。
- メロンへの拡張（任意・同世代に入れない）: age 6-8 に撒くと +2/日で age 8 に 6 到達＝2 日早く収穫。IPO 日程が変わるので別世代。
- KPI: イチゴ 1 回収量 ≥1.9（決定論的）。肥料の SELL 個数が減り、イチゴの SELL 個数が倍になること。
  金は 24→50 シード。イチゴは床落ちしやすい（`SELL_FLOORS`）ので**強帯資金**で読む。

## 5. gen0026: 労働割当の空間化（IDEA_POLICY 4 番。1-2 日。gen0027 の前提）

**目的は資金ではなく「同じ 12 hands で 75 タイルを回せる労働効率」**。KPI は決定論的なものを主にする。

1. **ゾーンを空間で切る**: 今の「クアドラント内 row-major の連続ブロック」（378-386 行）を、**2 列 × 数行のタイル束**
   （例: x を 2 列ずつ、y を上下）に変える。ゾーン内の最遠 2 点の距離 ≤4 を保証する。負荷（動物 4・作物 1）の均等は維持。
2. **越境 claim の禁止**: global fallback（500-501 行）は「所有者のいないタイル」か「所有者が今日もう来られない
   （残り時間 < 距離）」だけを拾う。所有者の todo を先に claim してはいけない（unit 順で fallback が先に走る穴）。
3. **最寄り規則を所有者優先に**: CARE/FEED の dmin（444-453 行）は「所有者 ＋ 救済時間帯の hand」に限定
   （gen0023 codex fix1 をここで単独評価する。fix2 の幽霊予約も同世代でよい: 同じ割当機構の修正）。
4. **一筆書き**: ゾーン内の todo を優先度順ではなく「優先度の層（FEED/CARE → PLANT → WATER/HARVEST）ごとに最近傍巡回」にする。
   層の中では距離だけで選ぶ。
- KPI（スモークで判定可）: 3 歩以上 ≤12%、連続行動タイル間距離 ≤0.9、最終 WATER ≤h14、最終 FEED ≤h10、unfed/uncared 0。
  資金は 24 シードで**悪化していない**ことだけ確認（CI が 0 をまたいでよい。前提整備の世代）。
  昇格させるか: `gate.pass` なら昇格、検出不能なら **gen0027 の親として採用**（CLOSED には書かない。前提世代として EXP に明記）。

## 6. gen0027: SW 解禁の再挑戦（EXP0023 の分離実験。IDEA_POLICY 1 番）

- gen0026 の上で `land_target` に d11 SW を足す。**hands は 12 のまま**（gen0023 の 13 人目を入れない）。
- 合格: 75 タイルで利用率 ≥80%、unfed/uncared 0、最終 WATER ≤h16。金は 50 シードで強帯資金 >0 が必須
  （gen0023 は −$2,347 だった。ここが変わらなければ土地ではなく動物 12→14-16 に行く: HANDOFF 次の一手 2）。

## 7. テストを挟む場所（まとめ）

| いつ | 何を | 合格 |
| --- | --- | --- |
| P0 直後 | 3 リプレイで監査の再現 | 数字一致、gen0022 で `--assert` が落ちる |
| 各世代のスモーク（3 シード） | `micro_audit.py --assert` ＋ `audit_replay.py` ＋ `profile_agent.py` | 各節の決定論 KPI |
| スモーク後 | `ops/eval_queue.py submit --seeds 24` | 資金差の符号・強帯資金の符号 |
| 24 が正 | `--seeds 50 --baseline records/eval_<王者>.json` | `gate.pass` ＋ 強帯資金 >0 |
| 昇格前 | Codex レビュー（`mcp codex`、REVIEW_CHECKLIST 7 観点） | `meta.json.review.blocking_resolved=true` |

- プール改編（`ops/reform_pool.py --do`）が走ると王者ベースラインが変わる。**改編の前後で候補とベースラインを混ぜない**。
- 各世代は `status: in_progress` の EXP を評価開始前にコミットする（CLAUDE.md）。

## 8. リスクと注意

- **3-A の副作用**: 水やりが 1 時間入るぶん melon IPO（d10）の売却が 1 時間遅れる。土地購入は同ターンの後続スロットなので影響なし。
  ただし `SHED_DUMP`/`DROP_VALUE` の DROP タイミングは監査で確認する。
- **3-C の副作用**: 小麦が増えると `feed_buffer` 超過分が SELL に回り小麦価格を下げる（log 型で −20% が上限、崩れない）。
  終盤 d25-28 の小麦一括売りが増える。強帯も同じことをしているので許容。
- **3-B の副作用**: 植付波の日（d10: メロン 12 + イチゴ 16）に PLANT が WATER より先になる。既存作物の水やりは
  同日中に終わればよい（枯れ判定は EOD）。ただし最終 WATER が h23 を超えないことを監査で見る。
- **1 秒制約**: gen0026 の最近傍巡回は todo 数 × units の二重ループ（今と同じ）。`profile_agent.py` の最悪値で確認。
- **hands 数**: 監査上は 12 hands が過剰（productive 80-95/288 hand-hour）だが、hands ±1 は禁止側。
  gen0026 後に「必要 hands = ceil(必要行動数 ÷ (稼働時間 × 実効率))」として**導出式**に置き換えるのが正道（別世代、任意）。
- **`--assert` の基準を当てにいかない**: 基準は強帯の実測（targets.json `micro`）か、規則から出る最大値（小麦 4・メロン 6・イチゴ 2）だけ。

## 9. 次セッション（Opus）の最初の 30 分

1. `control/DIRECTIVES.md` → `state/HANDOFF.md` → このファイル → `knowledge/analysis/2026-09-05_micro-audit-gen0022.md` の順に読む。
2. P0 を実装し、§2 のテストで数字が再現することを確認してからコミット（`harness/micro_audit.py` と targets の `micro`）。
3. gen0024 を §3 の 4 点で実装。スモーク 3 シードの `--assert` が通ったら 24 シードをキューに積んで終える。
4. `state/HANDOFF.md` の「次の一手」をこの表（§0）に置き換える。
