#!/usr/bin/env python
"""Discussion 全件コーパス（計画 §4-B）。**grep できる状態にすることが目的。**

なぜ要るか: 参照資料の教訓は「AI は新しい戦略を発明しない。効くのは公開議論の
網羅的な探索と実測」。そのためには Discussion が**手元で grep できる**必要がある。

取得方法（2026-09-05 修正）: **kaggle CLI で全部取れる。**
  kaggle competitions topics list <comp>          → トピック一覧（20 件/ページ）
  kaggle competitions topic-messages <comp> <id>  → 本文＋コメント（HTML）
当初 Browser が要ると書いていたのは誤りで、discussion **ページ**の HTML が
JS シェルなだけだった（CLI は API を叩くので中身が返る）。Browser は不要。

usage:
  .venv/bin/python ops/fetch_discussions.py sync            # 差分だけ取得(毎晩これ)
  .venv/bin/python ops/fetch_discussions.py sync --full     # 全件取り直し
  .venv/bin/python ops/fetch_discussions.py search "melon"  # コーパスを全文検索
  .venv/bin/python ops/fetch_discussions.py list            # 索引の一覧(votes 順)
  .venv/bin/python ops/fetch_discussions.py show 738079     # 1 件を読む
"""
import argparse
import datetime as dt
import html
import json
import re
import subprocess
import sys
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIR = ROOT / "knowledge/discussions"
INDEX = DIR / "index.jsonl"
KAGGLE = ["uvx", "--from", "kaggle==2.2.4", "kaggle"]
COMP = "kaggriculture"
TOPIC_URL = "https://www.kaggle.com/competitions/kaggriculture/discussion/{}"
REQUEST_SLEEP = 0.7   # Kaggle API は連投すると 429 を返す(実測)。1 リクエストごとに待つ
MAX_RETRIES = 4


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class _Text(HTMLParser):
    """HTML を素朴にテキスト化する（grep できればよいので整形は最低限）。

    リンクは `テキスト <URL>` にして URL を残す（公開ノートブックへの参照が多いため）。
    コードブロックは ``` で囲って、本文と区別できるようにする。
    """

    BLOCK = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "blockquote"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._href = None
        self._in_pre = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
        elif tag == "pre":
            self._in_pre = True
            self.parts.append("\n```\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            if self._href not in "".join(self.parts[-3:]):
                self.parts.append(f" <{self._href}>")
            self._href = None
        elif tag == "pre":
            self._in_pre = False
            self.parts.append("\n```\n")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        self.parts.append(data if self._in_pre else re.sub(r"[ \t]+", " ", data))


def to_text(s):
    p = _Text()
    p.feed(html.unescape(s or ""))
    txt = "".join(p.parts)
    return re.sub(r"\n{3,}", "\n\n", txt).strip()


def kaggle_json(args, what):
    """kaggle CLI を JSON で叩く。429(Too Many Requests) は指数バックオフで再試行する。"""
    out = None
    for attempt in range(MAX_RETRIES):
        time.sleep(REQUEST_SLEEP)
        out = subprocess.run(KAGGLE + args, capture_output=True, text=True, timeout=180)
        if out.returncode == 0:
            break
        blob = (out.stderr or "") + (out.stdout or "")
        if "429" in blob or "Too Many Requests" in blob:
            wait = 5 * (2 ** attempt)
            print(f"  429(レート制限)。{wait} 秒待って再試行 [{what}]", file=sys.stderr)
            time.sleep(wait)
            continue
        break
    if out is None or out.returncode != 0:
        print(f"⚠ {what} の取得に失敗: {(out.stderr if out else '').strip()[:200]}", file=sys.stderr)
        return None
    t = out.stdout
    # CLI は JSON の前に警告行、後ろに "Next Page Token = N" を出すことがあるので、
    # 先頭の JSON 値だけを raw_decode で取り出す。
    i = min([x for x in (t.find("["), t.find("{")) if x >= 0], default=-1)
    if i < 0:
        return []
    try:
        value, _ = json.JSONDecoder().raw_decode(t[i:])
        return value
    except json.JSONDecodeError as e:
        print(f"⚠ {what} の JSON を読めない: {e}", file=sys.stderr)
        return None


def list_topics(max_pages=50):
    """全ページのトピック一覧。20 件/ページ固定（--page-size は無視される）。"""
    topics, seen = [], set()
    for page in range(1, max_pages + 1):
        rows = kaggle_json(["competitions", "topics", "list", COMP, "-p", str(page),
                            "--format", "json"], f"topics page {page}")
        if not rows:
            break
        new = [r for r in rows if r.get("id") not in seen]
        if not new:
            break
        for r in new:
            seen.add(r["id"])
        topics += new
        if len(rows) < 20:
            break
    return topics


def fetch_messages(topic_id):
    """本文＋コメントを**時系列**で取る。

    既定の並びは hot（票順）なので、先頭が原文とは限らない（実測で確認）。
    `-s old` を付け、さらに postDate で並べ直して「本文＝最初の投稿」を保証する。
    """
    msgs = kaggle_json(["competitions", "topic-messages", COMP, str(topic_id),
                        "-n", "-1", "-s", "old", "--format", "json"], f"topic {topic_id}")
    if not msgs:
        return msgs
    return sorted(msgs, key=lambda m: str(m.get("postDate") or ""))


def read_index():
    if not INDEX.exists():
        return {}
    out = {}
    for line in INDEX.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            out[str(r["id"])] = r
    return out


def write_index(idx):
    DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                             for r in sorted(idx.values(), key=lambda r: -int(r["id"]))))


def save_topic(topic, messages):
    tid = str(topic["id"])
    lines = [f"# [{tid}] {topic.get('title') or '(無題)'}", "",
             f"- URL: {TOPIC_URL.format(tid)}",
             f"- 投稿: {str(topic.get('postDate') or '')[:19]}"
             f" ／ votes: {topic.get('votes')} ／ コメント: {topic.get('commentCount')}",
             f"- 取得: {now()}", ""]
    for i, m in enumerate(messages or []):
        head = "## 本文" if i == 0 else f"## コメント {i}"
        lines += [f"{head}（{m.get('authorName') or '(著者不明)'} / "
                  f"{str(m.get('postDate') or '')[:19]} / votes {m.get('votes')}）", "",
                  to_text(m.get("content")), ""]
    text = "\n".join(lines)
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / f"{tid}.md").write_text(text)
    return len(text)


def cmd_sync(args):
    topics = list_topics()
    if not topics:
        sys.exit("NO-GO: トピックを1件も取得できなかった（kaggle CLI の認証を確認）")
    idx = read_index()
    print(f"トピック {len(topics)} 件")
    fetched = skipped = 0
    for t in topics:
        tid = str(t["id"])
        prev = idx.get(tid)
        # 差分判定: コメント数・votes・本文の有無が変わっていなければ取り直さない
        fresh = (prev and not args.full
                 and prev.get("comment_count") == t.get("commentCount")
                 and prev.get("votes") == t.get("votes")
                 and (DIR / f"{tid}.md").exists())
        if fresh:
            skipped += 1
            idx[tid]["last_seen"] = now()
            continue
        msgs = fetch_messages(tid)
        if msgs is None:
            continue
        chars = save_topic(t, msgs)
        fetched += 1
        idx[tid] = {
            "id": tid, "title": t.get("title"), "url": TOPIC_URL.format(tid),
            "author": t.get("authorName") or None, "votes": t.get("votes"),
            "comment_count": t.get("commentCount"), "post_date": t.get("postDate"),
            "messages": len(msgs), "chars": chars,
            "file": f"knowledge/discussions/{tid}.md",
            "first_seen": (prev or {}).get("first_seen") or now(), "last_seen": now(),
        }
        print(f"  取得 [{tid}] {(t.get('title') or '')[:60]} "
              f"({len(msgs)} メッセージ / {chars} 文字)")
    write_index(idx)
    print(f"\n新規・更新 {fetched} 件 / 変更なし {skipped} 件 / コーパス計 {len(idx)} 件")
    print(f"  検索: .venv/bin/python ops/fetch_discussions.py search '<語>'")


def cmd_list(_args):
    idx = read_index()
    if not idx:
        print("コーパスは空。`fetch_discussions.py sync` を実行すること")
        return
    print(f"{len(idx)} 件（{INDEX.relative_to(ROOT)}）")
    for r in sorted(idx.values(), key=lambda r: -(r.get("votes") or 0)):
        print(f"  [{r['id']}] votes={r.get('votes'):>3} comments={r.get('comment_count'):>2} "
              f"{(r.get('title') or '')[:72]}")


def cmd_search(args):
    idx = read_index()
    pat = re.compile(args.query, re.IGNORECASE)
    hits = 0
    for r in sorted(idx.values(), key=lambda r: -(r.get("votes") or 0)):
        p = ROOT / r["file"]
        if not p.exists():
            continue
        matched = [(i, l.strip()) for i, l in enumerate(p.read_text().splitlines(), 1)
                   if pat.search(l)]
        if matched:
            print(f"\n[{r['id']}] {(r.get('title') or '')[:70]}  (votes {r.get('votes')})")
            print(f"  {r.get('url')}")
            for i, l in matched[:args.max_lines]:
                print(f"  {i}: {l[:170]}")
            if len(matched) > args.max_lines:
                print(f"  … 他 {len(matched) - args.max_lines} 行")
            hits += len(matched)
    if not hits:
        print(f"'{args.query}' に一致なし（コーパス {len(idx)} 件）")


def cmd_show(args):
    p = DIR / f"{args.topic_id}.md"
    if not p.exists():
        sys.exit(f"NO-GO: {p} が無い（sync を実行するか id を確認）")
    print(p.read_text())


def cmd_stale(args):
    idx = read_index()
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.days)
    old = [r for r in idx.values()
           if dt.datetime.fromisoformat(r.get("last_seen", "1970-01-01T00:00:00+00:00")) < cutoff]
    if not old:
        print(f"{args.days} 日以内に全件確認済み（{len(idx)} 件）")
        return
    print(f"{len(old)} 件が {args.days} 日以上未確認:")
    for r in sorted(old, key=lambda r: r.get("last_seen", "")):
        print(f"  [{r['id']}] {(r.get('title') or '')[:60]}  last_seen {r.get('last_seen', '')[:10]}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    y = sub.add_parser("sync", help="kaggle CLI で取得(差分のみ)")
    y.add_argument("--full", action="store_true", help="変更が無いトピックも取り直す")
    y.set_defaults(func=cmd_sync)
    s = sub.add_parser("search", help="コーパスを全文検索")
    s.add_argument("query")
    s.add_argument("--max-lines", type=int, default=6, help="1 トピックあたりの表示行数")
    s.set_defaults(func=cmd_search)
    w = sub.add_parser("show", help="1 トピックを表示")
    w.add_argument("topic_id")
    w.set_defaults(func=cmd_show)
    st = sub.add_parser("stale", help="再確認が要るトピック")
    st.add_argument("--days", type=int, default=3)
    st.set_defaults(func=cmd_stale)
    q = sub.add_parser("list", help="索引の一覧")
    q.set_defaults(func=cmd_list)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
