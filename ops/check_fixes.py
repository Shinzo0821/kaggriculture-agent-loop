#!/usr/bin/env python
"""修正台帳（`control/fixes.json`）の機械チェック（DIRECTIVES Q2 / 2026-09-06）。

**なぜ要るか**: 世代は不変で、新世代は親の `main.py` をコピーして作る。非昇格に終わった
世代に入れた修正は、次の世代の親がその世代でなければ**消える**。実際 gen0023 の codex fix2
（移動中 hand による在庫の幽霊予約）は gen0023 が非昇格だったため王者系統に伝わらず、
13 世代あとの gen0034 レビューで同じ指摘を受けた。世代から独立した台帳を置き、
新世代を作るたびに機械的に照合する。

usage:
  # 新世代を作ったら必ず（status=applied が落ちていないかの回帰検査）
  .venv/bin/python ops/check_fixes.py agents/gen0041/main.py
  # 未適用（status=open）も一覧したい
  .venv/bin/python ops/check_fixes.py agents/gen0041/main.py --show-open
  # 台帳の網羅検査: meta.json の deferred な指摘が台帳に載っているか
  .venv/bin/python ops/check_fixes.py --audit
  # 機械処理用
  .venv/bin/python ops/check_fixes.py agents/gen0041/main.py --json

exit code:
  0 = status=applied がすべて検出できた（open の残件は 0 のまま）
  1 = 回帰（applied なのに検出できない）／台帳の不備／--audit の未登録
判定:
  detect.marker      … main.py の中に FIX ID の文字列（コメントで可）があれば適用済み
  detect.require[]   … すべての正規表現が本文にマッチすれば適用済み
  detect.forbid[]    … どれか 1 つでもマッチしたら未適用（require と併用可）
  detect: null       … 機械判定できない。applied なら「目視確認済み」として通すが警告を出す
  判定の順序（**偽陰性＝回帰の見逃しを作らないことを最優先**にする。2026-09-06 codex レビュー P1-1）:
    (1) forbid のどれかにマッチしたら未適用（marker があっても覆せない）
    (2) require があるなら、すべてマッチして初めて適用済み（**marker だけでは通さない**。
        コメントを写して実装を戻した世代を通してしまうため。リファクタで正規表現が外れたら
        台帳の正規表現も同時に直す）
    (3) require が無い場合だけ marker の有無で判定する
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "control" / "fixes.json"
HUMAN_LEDGER = ROOT / "knowledge" / "FIXES.md"
VALID_STATUS = {"applied", "open", "wontfix"}


def load_ledger(path=LEDGER):
    """台帳を読んで構造を検証する。壊れていたら黙って通さずここで落とす（fail-closed）。"""
    try:
        data = json.loads(path.read_text())
    except FileNotFoundError:
        sys.exit(f"NG: 台帳が無い: {path}")
    except json.JSONDecodeError as e:
        sys.exit(f"NG: 台帳が JSON として壊れている: {path} ({e})")
    if not isinstance(data, dict):
        sys.exit(f"NG: {path} のトップレベルがオブジェクトでない")
    fixes = data.get("fixes")
    if not isinstance(fixes, list) or not fixes:
        sys.exit(f"NG: {path} の fixes が空か配列でない")
    seen = set()
    for f in fixes:
        if not isinstance(f, dict):
            sys.exit(f"NG: fixes の要素がオブジェクトでない: {str(f)[:60]}")
        fid = f.get("id")
        if not isinstance(fid, str) or not re.fullmatch(r"FIX\d{4}", fid):
            sys.exit(f"NG: id が FIXNNNN 形式でない: {fid!r}")
        if fid in seen:
            sys.exit(f"NG: id が重複している: {fid}")
        seen.add(fid)
        if f.get("status") not in VALID_STATUS:
            sys.exit(f"NG: {fid} の status が不正: {f.get('status')!r}（{sorted(VALID_STATUS)}）")
        for s in f.get("sources") or []:
            if not isinstance(s, str):
                sys.exit(f"NG: {fid} の sources に文字列でない要素がある: {str(s)[:40]}")
        d = f.get("detect")
        if d is None:
            # detect が無い項目は機械判定できない。applied では回帰を検出できないので禁止
            # （2026-09-06 codex レビュー P1-2: 静かに exit 0 を返す経路を残さない）。
            # ただし kind=ops の修正は対象が ops/ や control/ のファイルで、agent の main.py には
            # 痕跡が出ない（2026-09-20 FIX0037/FIX0038）。回帰検査の対象外なので detect を課さない。
            if f["status"] == "applied" and f.get("kind") != "ops":
                sys.exit(f"NG: {fid} は status=applied なのに detect が無い。"
                         "marker（例 \"FIX0001\"）か require の正規表現を書くこと")
            continue
        if not isinstance(d, dict):
            sys.exit(f"NG: {fid} の detect がオブジェクトでも null でもない")
        marker = d.get("marker")
        if marker is not None and not isinstance(marker, str):
            sys.exit(f"NG: {fid} の detect.marker が文字列でない")
        for key in ("require", "forbid"):
            pats = d.get(key)
            if pats is None:
                continue
            if not isinstance(pats, list):
                sys.exit(f"NG: {fid} の detect.{key} が配列でない")
            for p in pats:
                if not isinstance(p, str):
                    sys.exit(f"NG: {fid} の detect.{key} に文字列でない要素がある")
                try:
                    re.compile(p)
                except re.error as e:
                    sys.exit(f"NG: {fid} の detect.{key} の正規表現が不正: {p!r} ({e})")
        if f["status"] == "applied" and not (marker or d.get("require") or d.get("forbid")):
            sys.exit(f"NG: {fid} は status=applied なのに detect が空（marker も require も無い）")
    return fixes


def detect(fix, src):
    """(適用済みか, 理由) を返す。判定不能なら (None, 理由)。"""
    d = fix.get("detect")
    if not d:
        return None, "detect が無い（目視のみ）"
    marker = d.get("marker")
    req = d.get("require") or []
    forbid = d.get("forbid") or []
    # (1) forbid が最優先。marker で覆せない（コメントだけ残して実装を戻す穴を塞ぐ）
    for pat in forbid:
        if re.search(pat, src):
            return False, f"forbid にマッチ: {pat}"
    # (2) require があるなら本文で判定する。marker は補助情報にすぎない
    if req:
        missing = [p for p in req if not re.search(p, src)]
        if missing:
            note = "" if not marker else f"（marker {marker} は{'あり' if marker in src else '無し'}）"
            return False, f"require が {len(missing)}/{len(req)} 件マッチしない: {missing[0]}{note}"
        return True, f"require {len(req)} 件すべてマッチ"
    # (3) require が無い場合だけ marker で判定する
    if marker:
        return (True, f"marker {marker} あり") if marker in src else (False, f"marker {marker} が無い")
    if forbid:
        return True, "forbid にマッチせず"
    return None, "detect に marker も require/forbid も無い"


def check_candidate(fixes, target: Path):
    src = target.read_text(errors="replace")
    results = []
    for f in fixes:
        st = f["status"]
        if st == "wontfix":
            continue
        ok, why = detect(f, src)
        if f.get("kind") == "ops":
            # ops の修正は main.py を見ても判定できない。一覧には出すが回帰検査には載せない。
            ok, why = None, "ops の修正（main.py では判定しない）"
        results.append({"id": f["id"], "title": f.get("title"), "status": st,
                        "severity": f.get("severity"), "kind": f.get("kind", "agent"),
                        "detected": ok, "why": why, "fix": f.get("fix")})
    regressions = [r for r in results if r["status"] == "applied" and r["detected"] is False]
    unverifiable = [r for r in results if r["status"] == "applied" and r["detected"] is None
                    and r["kind"] != "ops"]
    reappeared = [r for r in results if r["status"] == "open" and r["detected"] is True]
    open_items = [r for r in results if r["status"] == "open" and r["detected"] is not True]
    return results, regressions, unverifiable, reappeared, open_items


def audit(fixes):
    """`agents/*/meta.json` の未解決（resolution が fixed で始まらない）指摘が
    台帳の sources に載っているかを検査する。載っていなければ未登録として報告。"""
    registered = set()
    for f in fixes:
        for s in f.get("sources") or []:
            registered.add(s)
    unregistered = []
    errors = []   # 読めない meta.json を黙って飛ばさない（2026-09-06 codex レビュー P1-3）
    for meta_p in sorted(ROOT.glob("agents/gen*/meta.json")):
        gen = meta_p.parent.name
        try:
            meta = json.loads(meta_p.read_text())
        except (json.JSONDecodeError, OSError) as e:
            errors.append((gen, f"meta.json が読めない: {e}"))
            continue
        if not isinstance(meta, dict):
            errors.append((gen, "meta.json のトップレベルがオブジェクトでない"))
            continue
        rv = meta.get("review")
        if rv is None:
            continue          # レビュー前の世代（既存世代との互換）
        if not isinstance(rv, dict):
            errors.append((gen, "review がオブジェクトでない"))
            continue
        findings = rv.get("findings")
        if findings is None:
            continue
        if not isinstance(findings, list):
            errors.append((gen, "review.findings が配列でない"))
            continue
        for i, fnd in enumerate(findings):
            if not isinstance(fnd, dict):
                errors.append((gen, f"review.findings[{i}] がオブジェクトでない"))
                continue
            res = str(fnd.get("resolution") or "")
            if res.startswith("fixed"):
                continue
            key = f"{gen}#{i}"
            if key not in registered:
                unregistered.append((key, fnd.get("severity"), str(fnd.get("what") or "")[:70]))
    # 台帳側から見た逆方向（存在しない出所を指している）も見る
    dangling = []
    for f in fixes:
        for s in f.get("sources") or []:
            m = re.fullmatch(r"(gen\d{4})#(\d+)", s)
            if not m:
                dangling.append((f["id"], s, "書式が genNNNN#N でない"))
                continue
            meta_p = ROOT / "agents" / m.group(1) / "meta.json"
            if not meta_p.exists():
                dangling.append((f["id"], s, "meta.json が無い"))
                continue
            try:
                findings = (json.loads(meta_p.read_text()).get("review") or {}).get("findings") or []
            except (json.JSONDecodeError, OSError):
                dangling.append((f["id"], s, "meta.json が読めない"))
                continue
            if not isinstance(findings, list):
                dangling.append((f["id"], s, "review.findings が配列でない"))
                continue
            if int(m.group(2)) >= len(findings):
                dangling.append((f["id"], s, f"findings が {len(findings)} 件しかない"))
    return unregistered, dangling, errors


def check_human_ledger(fixes):
    """人が読む台帳（knowledge/FIXES.md）と `control/fixes.json` の ID 集合を**双方向**で突き合わせる
    （片方だけ更新される事故の防止。2026-09-06 codex レビュー P2-1）。"""
    rel = HUMAN_LEDGER.relative_to(ROOT)
    if not HUMAN_LEDGER.exists():
        return [f"{rel} が無い"]
    text = HUMAN_LEDGER.read_text()
    in_md = set(re.findall(r"FIX\d{4}", text))
    in_json = {f["id"] for f in fixes}
    problems = [f"{fid} の節が {rel} に無い" for fid in sorted(in_json - in_md)]
    problems += [f"{fid} が {rel} にあるが control/fixes.json に無い" for fid in sorted(in_md - in_json)]
    return problems


def main():
    ap = argparse.ArgumentParser(description="修正台帳 control/fixes.json の機械チェック")
    ap.add_argument("candidate", nargs="?", help="検査する main.py（例: agents/gen0041/main.py）")
    ap.add_argument("--audit", action="store_true",
                    help="meta.json の未解決指摘が台帳に載っているかを検査する")
    ap.add_argument("--show-open", action="store_true", help="未適用（status=open）も一覧する")
    ap.add_argument("--strict-open", action="store_true",
                    help="status=open が 1 件でも残っていたら exit 1（既定は警告のみ）")
    ap.add_argument("--json", action="store_true", help="機械処理用に JSON で出す")
    args = ap.parse_args()
    if not args.candidate and not args.audit:
        ap.error("candidate か --audit のどちらかが要る")

    fixes = load_ledger()
    failed = False
    out = {"ledger": str(LEDGER.relative_to(ROOT)), "fixes_total": len(fixes)}

    doc_problems = check_human_ledger(fixes)
    out["ledger_doc_problems"] = doc_problems

    if args.candidate:
        target = Path(args.candidate)
        if not target.is_absolute():
            target = ROOT / args.candidate
        if not target.exists():
            sys.exit(f"NG: 候補が無い: {args.candidate}")
        results, regressions, unverifiable, reappeared, open_items = check_candidate(fixes, target)
        out["candidate"] = args.candidate
        out["results"] = results
        if not args.json:
            print(f"== {args.candidate} vs {out['ledger']}（{len(fixes)} 件）")
            for r in regressions:
                print(f"  NG 回帰 {r['id']} [{r['severity']}] {r['title']}")
                print(f"         {r['why']} / 直し方: {r['fix']}")
            for r in unverifiable:
                print(f"  NG 判定不能 {r['id']} {r['title']}"
                      f"（status=applied なのに detect が無い。marker か require を書くこと）")
            for r in reappeared:
                print(f"  NG {r['id']} は status=open だが候補では検出された（{r['why']}）。"
                      f"直っているなら台帳を applied にし、applied_since を書くこと")
            if args.show_open or open_items:
                print(f"  -- 未適用の既知修正 {len(open_items)} 件"
                      f"{'' if args.show_open else '（--show-open で詳細）'}")
                if args.show_open:
                    for r in open_items:
                        print(f"     {r['id']} [{r['severity']}/{r['kind']}] {r['title']}")
                        print(f"       直し方: {r['fix']}")
            applied_ok = [r for r in results if r["status"] == "applied" and r["detected"] is True]
            print(f"  applied {len(applied_ok)}/{len([r for r in results if r['status']=='applied'])} 検出"
                  f" ／ open {len(open_items)} 件")
        # 回帰・判定不能・台帳の取り残し（open なのに入っている）はすべて失敗にする。
        # 「静かに exit 0」を作らないため（2026-09-06 codex レビュー P1-2）。
        if regressions or unverifiable or reappeared:
            failed = True
        if args.strict_open and open_items:
            failed = True

    if args.audit:
        unregistered, dangling, audit_errors = audit(fixes)
        out["unregistered"] = [{"source": k, "severity": s, "what": w} for k, s, w in unregistered]
        out["dangling_sources"] = [{"id": i, "source": s, "why": w} for i, s, w in dangling]
        out["audit_errors"] = [{"gen": g, "why": w} for g, w in audit_errors]
        if not args.json:
            print("== 台帳の網羅検査（agents/*/meta.json の未解決指摘）")
            for k, s, w in unregistered:
                print(f"  NG 未登録 {k} [{s}] {w}")
            for i, s, w in dangling:
                print(f"  NG 出所が壊れている {i} → {s}: {w}")
            for g, w in audit_errors:
                print(f"  NG {g} の meta.json を検査できない: {w}")
            if not unregistered and not dangling and not audit_errors:
                print("  OK 未解決の指摘はすべて台帳に載っている")
        if unregistered or dangling or audit_errors:
            failed = True

    if doc_problems:
        failed = True
        if not args.json:
            for p in doc_problems:
                print(f"  NG 台帳の不整合: {p}")

    if args.json:
        out["ok"] = not failed
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("NG: 上の項目を直すこと" if failed else "OK: 修正台帳の照合に問題なし")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
