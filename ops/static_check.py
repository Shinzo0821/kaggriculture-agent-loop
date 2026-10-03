#!/usr/bin/env python
"""FR-5 追加（2026-09-05, 計画 §7-A）: 提出物 main.py の静的検査。

提出前に「提出形式として壊れていないか」を AST で機械検査する。
実行はしない（import 副作用を踏まないため）。

検査項目（`.venv/.../envs/kaggriculture/README.md` と CLAUDE.md の提出規約）:
  1. トップレベルに `agent` が束縛され、最後の束縛が callable（def / lambda / 別名）であること
  2. import が標準ライブラリのみであること
  3. ファイル I/O・ネットワーク・サブプロセスの呼び出しが無いこと（No Ingress/Egress）

usage:
  .venv/bin/python ops/static_check.py agents/gen0023/main.py
  → 問題なしなら exit 0 で "static OK"、問題があれば exit 1 で理由を列挙
"""
import argparse
import ast
import sys
from pathlib import Path

# ネットワーク / プロセス / ファイル操作を持ち込むモジュール（import 自体を禁止）
FORBIDDEN_MODULES = {
    "socket", "ssl", "urllib", "urllib2", "http", "httplib", "ftplib", "smtplib",
    "poplib", "imaplib", "telnetlib", "xmlrpc", "asyncio", "requests", "httpx",
    "aiohttp", "subprocess", "multiprocessing", "shutil", "tempfile", "ctypes",
    "pickle", "shelve", "dbm", "sqlite3", "webbrowser", "importlib", "runpy",
}
# 呼ぶと I/O が発生する名前（属性名 or 組み込み名）
FORBIDDEN_CALLS = {
    "open", "eval", "exec", "compile", "__import__", "input",
    "write_text", "write_bytes", "read_text", "read_bytes",
    "system", "popen", "remove", "unlink", "rmdir", "mkdir", "makedirs", "rename",
}


def _module_root(name):
    return (name or "").split(".")[0]


def _stdlib_names():
    names = getattr(sys, "stdlib_module_names", None)
    if names:
        return set(names)
    # 3.9 以前のフォールバック（本プロジェクトの venv は 3.11 なので通常使わない）
    import distutils.sysconfig as sc  # noqa: PLC0415
    return set(sys.builtin_module_names) | {p.stem for p in Path(sc.get_python_lib(standard_lib=True)).glob("*.py")}


def check_source(src, filename="<agent>", extra_allowed=()):
    """問題のリスト（空なら合格）を返す。

    extra_allowed: 標準ライブラリ外でも許可するモジュール名（control/submission_policy.json の
    static_check.allowed_nonstdlib。本番環境に存在する numpy 等を使う場合のみ足す）。
    """
    problems = []
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError as e:
        return [f"構文エラー: {e}"]

    stdlib = _stdlib_names() | set(extra_allowed)

    # --- 1. agent の束縛 ---
    agent_bindings = []  # (lineno, kind)
    for node in tree.body:  # トップレベルのみ
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "agent":
            agent_bindings.append((node.lineno, "def"))
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "agent":
                    kind = "callable" if isinstance(node.value, (ast.Lambda, ast.Name, ast.Attribute)) else "value"
                    agent_bindings.append((node.lineno, kind))
        elif isinstance(node, ast.AnnAssign):
            t = node.target
            if isinstance(t, ast.Name) and t.id == "agent":
                kind = "callable" if isinstance(node.value, (ast.Lambda, ast.Name, ast.Attribute)) else "value"
                agent_bindings.append((node.lineno, kind))
    if not agent_bindings:
        problems.append("トップレベルに agent が定義されていない（提出形式違反）")
    elif agent_bindings[-1][1] == "value":
        problems.append(f"最後の agent 束縛(L{agent_bindings[-1][0]})が callable でない値になっている")

    # --- 2/3. import と呼び出し ---
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = _module_root(a.name)
                if root in FORBIDDEN_MODULES:
                    problems.append(f"L{node.lineno}: 禁止モジュール import {a.name}")
                elif root not in stdlib:
                    problems.append(f"L{node.lineno}: 標準ライブラリ外の import {a.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # 相対 import = main.py 単体提出では解決不能
                problems.append(f"L{node.lineno}: 相対 import（単体提出では解決できない）")
                continue
            root = _module_root(node.module)
            if root in FORBIDDEN_MODULES:
                problems.append(f"L{node.lineno}: 禁止モジュール from {node.module}")
            elif root and root not in stdlib:
                problems.append(f"L{node.lineno}: 標準ライブラリ外の from {node.module}")
        elif isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else None)
            if name in FORBIDDEN_CALLS:
                problems.append(f"L{node.lineno}: 禁止呼び出し {name}()（ファイルI/O・動的実行）")
    return problems


def check_file(path, extra_allowed=()):
    p = Path(path)
    if not p.exists():
        return [f"ファイルがない: {path}"]
    return check_source(p.read_text(), str(p), extra_allowed)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_file")
    ap.add_argument("--allow", default="", help="標準ライブラリ外で許可するモジュール(カンマ区切り)")
    args = ap.parse_args()
    problems = check_file(args.agent_file, [x.strip() for x in args.allow.split(",") if x.strip()])
    if problems:
        print(f"static NG: {args.agent_file}")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print(f"static OK: {args.agent_file}")


if __name__ == "__main__":
    main()
