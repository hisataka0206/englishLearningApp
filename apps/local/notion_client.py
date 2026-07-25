"""Minimal Notion REST client + Chinese-article parser (stdlib only).

Used by server.py for the article (記事) mode:
- list child articles under the hub page
- import an article: parse per-sentence 中文/拼音/日本語 + vocabulary table
- write back a "失敗履歴" table at the end of an article page
"""

import json
import re
import urllib.request
import urllib.error

API = "https://api.notion.com/v1"


class NotionClient:
    def __init__(self, cfg):
        self.token = cfg.get("token", "")
        self.version = cfg.get("api_version", "2022-06-28")
        self.parent_id = cfg.get("articles_parent_page_id", "")

    def configured(self):
        return bool(self.token and "PUT_YOUR" not in self.token and self.parent_id)

    # ------------------------------------------------------------ REST
    def _req(self, method, path, payload=None):
        url = f"{API}/{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self.token}")
        req.add_header("Notion-Version", self.version)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode()), None
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode())
                msg = f"{body.get('code')}: {body.get('message', '')[:120]}"
            except Exception:
                msg = f"HTTP {e.code}"
            return None, msg
        except Exception as e:
            return None, str(e)

    def _children(self, block_id):
        """All child blocks (handles pagination)."""
        out = []
        cursor = None
        while True:
            q = f"blocks/{block_id}/children?page_size=100"
            if cursor:
                q += f"&start_cursor={cursor}"
            res, err = self._req("GET", q)
            if err:
                return None, err
            out.extend(res.get("results", []))
            if not res.get("has_more"):
                break
            cursor = res.get("next_cursor")
        return out, None

    def ping(self):
        _, err = self._req("GET", "users/me")
        return err

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _text(block):
        t = block.get("type")
        rt = block.get(t, {}).get("rich_text", [])
        return "".join(x.get("plain_text", "") for x in rt).strip()

    # ------------------------------------------------------------ articles
    def list_articles(self):
        """Return [{id, title}] for child pages under the hub (date-titled)."""
        blocks, err = self._children(self.parent_id)
        if err:
            return None, err
        out = []
        for b in blocks:
            if b.get("type") == "child_page":
                title = b["child_page"]["title"]
                # 日付タイトルの記事だけ（ドリル等の補助ページは除外）
                if len(title) >= 10 and title[:4].isdigit() and title[4] == "-":
                    out.append({"id": b["id"].replace("-", ""), "title": title})
        return out, None

    @staticmethod
    def _hrefs(block):
        t = block.get("type")
        return [x.get("href") for x in block.get(t, {}).get("rich_text", []) if x.get("href")]

    def extract_meta(self, blocks):
        """出典情報から原文URLと日本語タイトルを抽出する。"""
        source_url, jp_title = "", ""
        for b in blocks:
            txt = self._text(b)
            # 「中文要约/要約」見出し以降は本文なのでメタ領域終了
            if b["type"].startswith("heading") and "中文要" in txt:
                break
            if b["type"] == "table":
                rows, _ = self._children(b["id"])
                for r in (rows or []):
                    if r.get("type") != "table_row":
                        continue
                    cells = r["table_row"]["cells"]
                    label = "".join(x.get("plain_text", "") for x in cells[0]) if cells else ""
                    val = "".join(x.get("plain_text", "") for x in cells[1]) if len(cells) > 1 else ""
                    hrefs = [x.get("href") for c in cells for x in c if x.get("href")]
                    if label in ("原タイトル", "日本語訳", "日本語タイトル") and val and not jp_title:
                        jp_title = val.strip()
                    if "原文URL" in label or "原文" in label:
                        for h in hrefs:
                            if h and "notion.so" not in h and not source_url:
                                source_url = h
                        if not source_url:
                            m = re.search(r"https?://\S+", val)
                            if m and "notion.so" not in m.group(0):
                                source_url = m.group(0)
            else:
                for h in self._hrefs(b):
                    if h and "notion.so" not in h and not source_url:
                        source_url = h
                if not source_url:
                    m = re.search(r"https?://[^\s）)]+", txt)
                    if m and "notion.so" not in m.group(0):
                        source_url = m.group(0)
        return source_url, jp_title

    def parse_article(self, page_id):
        """Parse one article page into structured data."""
        page, err = self._req("GET", f"pages/{page_id}")
        if err:
            return None, err
        title = ""
        for prop in (page.get("properties") or {}).values():
            if prop.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in prop["title"])
                break
        blocks, err = self._children(page_id)
        if err:
            return None, err

        import re
        sent_re = re.compile(r"^第\s*\d+\s*句")
        num_re = re.compile(r"^\d{1,2}[.．、]\s*(.+)")  # 「1. 中文…」番号付き

        sentences = []
        cur = None
        vocab = []
        for b in blocks:
            t = b["type"]
            txt = self._text(b)
            # 「第N句」は記事により paragraph / heading_2 / heading_3 のいずれか
            if sent_re.match(txt):
                if cur and cur.get("zh"):
                    sentences.append(cur)
                cur = {"idx": len(sentences) + 1, "zh": "", "pinyin": "", "ja": ""}
            elif txt.startswith("中文："):
                # 「第N句」ラベルが無いフォーマットでは「中文：」自体が文の区切り
                if cur and cur.get("zh"):
                    sentences.append(cur)
                    cur = None
                if cur is None:
                    cur = {"idx": len(sentences) + 1, "zh": "", "pinyin": "", "ja": ""}
                cur["zh"] = txt[len("中文："):].strip()
            elif txt.startswith("拼音："):
                if cur is not None:
                    cur["pinyin"] = txt[len("拼音："):].strip()
            elif num_re.match(txt) and any("一" <= c <= "鿿" for c in txt):
                # 「1. 中文…」番号付きフォーマット（中文：接頭辞なし）
                if cur and cur.get("zh"):
                    sentences.append(cur)
                cur = {"idx": len(sentences) + 1, "zh": num_re.match(txt).group(1).strip(),
                       "pinyin": "", "ja": ""}
            elif txt.startswith("日本語："):
                if cur is not None:
                    cur["ja"] = txt[len("日本語："):].strip()
            elif t == "toggle":
                # 日本語訳はトグルの子ブロックに入っている（新フォーマット）
                kids, _ = self._children(b["id"])
                ja = " ".join(self._text(k) for k in (kids or []) if self._text(k))
                if cur is not None and not cur.get("ja"):
                    cur["ja"] = ja.strip()
            elif t == "table":
                v = self._parse_table(b["id"])
                if v:  # 出典情報テーブル等は空になるので、語彙が取れた表だけ採用
                    vocab = v
        if cur and cur.get("zh"):
            sentences.append(cur)

        source_url, jp_title = self.extract_meta(blocks)
        date = title[:10] if re.match(r"\d{4}-\d\d-\d\d", title) else ""
        zh_title = title[10:].strip() if date else title
        return {"notion_page_id": page_id.replace("-", ""), "title": title,
                "date": date, "zh_title": zh_title, "jp_title": jp_title,
                "source_url": source_url, "sentences": sentences, "vocab": vocab}, None

    # ------------------------------------------------------------ write-back
    @staticmethod
    def _row(cells):
        def rt(s):
            return [{"type": "text", "text": {"content": str(s)[:200]}}]
        return {"type": "table_row", "table_row": {"cells": [rt(c) for c in cells]}}

    FAIL_HEADER = ["日付", "句", "漢字", "拼音", "ラベル"]

    def find_fail_table(self, page_id):
        """末尾の「失敗履歴」テーブルのblock idを返す（無ければNone）。"""
        blocks, err = self._children(page_id)
        if err:
            return None, err
        seen_heading = False
        for b in blocks:
            if b["type"] in ("heading_2", "heading_3") and "失敗履歴" in self._text(b):
                seen_heading = True
            elif seen_heading and b["type"] == "table":
                return b["id"], None
        return None, None

    def create_fail_table(self, page_id, rows):
        """見出し＋失敗履歴テーブルを新規作成。テーブルblock idを返す。"""
        table_rows = [self._row(self.FAIL_HEADER)] + [self._row(r) for r in rows]
        children = [
            {"object": "block", "type": "heading_2",
             "heading_2": {"rich_text": [{"type": "text",
                          "text": {"content": "失敗履歴（アプリ記録）"}}]}},
            {"object": "block", "type": "table",
             "table": {"table_width": len(self.FAIL_HEADER),
                       "has_column_header": True, "has_row_header": False,
                       "children": table_rows}},
        ]
        res, err = self._req("PATCH", f"blocks/{page_id}/children",
                             {"children": children})
        if err:
            return None, err
        for b in res.get("results", []):
            if b["type"] == "table":
                return b["id"], None
        # 稀にresultsにtableが無い場合は探し直す
        return self.find_fail_table(page_id)

    def append_fail_rows(self, table_id, rows):
        children = [self._row(r) for r in rows]
        _, err = self._req("PATCH", f"blocks/{table_id}/children",
                           {"children": children})
        return err

    def _parse_table(self, table_id):
        rows, err = self._children(table_id)
        if err:
            return []
        out = []
        for i, r in enumerate(rows):
            if r.get("type") != "table_row":
                continue
            cells = r["table_row"]["cells"]
            vals = ["".join(x.get("plain_text", "") for x in c).strip() for c in cells]
            if i == 0:
                continue  # header (中文/拼音/日本語)
            if len(vals) >= 3 and vals[0]:
                out.append({"zh": vals[0], "pinyin": vals[1], "ja": vals[2]})
        return out
