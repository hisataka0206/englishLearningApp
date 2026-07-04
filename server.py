#!/usr/bin/env python3
"""English Learning App - mini server.

- Serves the browser UI (index.html)
- /api/translate : Japanese -> English + keywords via local Ollama
- /api/sentences : save / list sentences in Notion DB
- /api/words     : register keywords in Notion words DB (relation to sentence)
- /api/fail      : record a fail as a Notion comment (+ FailCount increment)

Config (Notion IDs, Ollama, port) lives in config.json next to this file.
Standard library only - no pip install required.
"""

import json
import os
import re
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()


# ---------------------------------------------------------------- helpers
def http_json(url, payload=None, headers=None, method=None, timeout=120):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
        except Exception:
            body = ""
        return None, f"HTTP {e.code}: {body[:500]}"
    except Exception as e:
        return None, str(e)


def notion_headers():
    n = CFG["notion"]
    return {
        "Authorization": f"Bearer {n['token']}",
        "Notion-Version": n.get("api_version", "2022-06-28"),
    }


def notion(path, payload=None, method=None):
    return http_json(f"https://api.notion.com/v1/{path}", payload,
                     notion_headers(), method, timeout=30)


def rich(text):
    return [{"type": "text", "text": {"content": (text or "")[:2000]}}]


def plain(prop):
    """Extract plain text from a Notion title/rich_text property."""
    return "".join(t.get("plain_text", "") for t in prop or [])


# ---------------------------------------------------------------- ollama
TRANSLATE_PROMPT = """You are an English teacher for a Japanese learner.
Translate the Japanese text into natural, conversational English.
Then pick up to 5 important keywords/phrases from your English translation
that are worth memorizing, with a short Japanese meaning for each.
Respond ONLY with JSON in this exact shape:
{"english": "...", "keywords": [{"word": "...", "meaning": "..."}]}

Japanese text:
"""


def translate(japanese, model=None):
    o = CFG["ollama"]
    payload = {
        "model": model or o["model"],
        "messages": [{"role": "user", "content": TRANSLATE_PROMPT + japanese}],
        "format": "json",
        "stream": False,
        "options": {"temperature": 0.3},
    }
    res, err = http_json(f"{o['base_url']}/api/chat", payload)
    if err:
        return None, f"Ollama error: {err}"
    content = (res.get("message") or {}).get("content", "")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return None, f"LLM returned non-JSON: {content[:200]}"
        parsed = json.loads(m.group(0))
    english = (parsed.get("english") or "").strip()
    if not english:
        return None, "LLM returned empty translation"
    keywords = [
        {"word": str(k.get("word", "")).strip(), "meaning": str(k.get("meaning", "")).strip()}
        for k in parsed.get("keywords", []) if isinstance(k, dict) and k.get("word")
    ]
    return {"english": english, "keywords": keywords[:5]}, None


def list_models():
    res, err = http_json(f"{CFG['ollama']['base_url']}/api/tags", timeout=10)
    if err:
        return [], err
    return [m["name"] for m in res.get("models", [])], None


# ---------------------------------------------------------------- notion ops
def save_sentence(japanese, english, memo=""):
    payload = {
        "parent": {"database_id": CFG["notion"]["sentences_db_id"]},
        "properties": {
            "English": {"title": rich(english)},
            "Japanese": {"rich_text": rich(japanese)},
            "Memo": {"rich_text": rich(memo)},
            "FailCount": {"number": 0},
        },
    }
    res, err = notion("pages", payload)
    if err:
        return None, err
    return {"id": res["id"], "url": res.get("url", "")}, None


def list_sentences(limit=20):
    payload = {
        "page_size": limit,
        "sorts": [{"timestamp": "created_time", "direction": "descending"}],
    }
    res, err = notion(f"databases/{CFG['notion']['sentences_db_id']}/query", payload)
    if err:
        return None, err
    items = []
    for p in res.get("results", []):
        props = p.get("properties", {})
        items.append({
            "id": p["id"],
            "url": p.get("url", ""),
            "english": plain(props.get("English", {}).get("title")),
            "japanese": plain(props.get("Japanese", {}).get("rich_text")),
            "fail_count": props.get("FailCount", {}).get("number") or 0,
        })
    return items, None


def save_word(word, meaning, example="", source_page_id=None):
    props = {
        "Word": {"title": rich(word)},
        "Meaning": {"rich_text": rich(meaning)},
        "Example": {"rich_text": rich(example)},
    }
    if source_page_id:
        props["Source"] = {"relation": [{"id": source_page_id}]}
    payload = {"parent": {"database_id": CFG["notion"]["words_db_id"]},
               "properties": props}
    res, err = notion("pages", payload)
    if err:
        return None, err
    return {"id": res["id"], "url": res.get("url", "")}, None


def record_fail(page_id, label="Fail"):
    # 1) comment on the sentence page (same convention as Chinese articles)
    _, err = notion("comments", {
        "parent": {"page_id": page_id},
        "rich_text": rich(label),
    })
    if err:
        return None, err
    # 2) increment FailCount
    page, err = notion(f"pages/{page_id}", method="GET")
    if err:
        return None, err
    current = page.get("properties", {}).get("FailCount", {}).get("number") or 0
    _, err = notion(f"pages/{page_id}",
                    {"properties": {"FailCount": {"number": current + 1}}},
                    method="PATCH")
    if err:
        return None, err
    return {"fail_count": current + 1}, None


# ---------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj=None, body=None, ctype="application/json"):
        data = body if body is not None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _ok(self, data):
        self._send(200, {"ok": True, "data": data})

    def _fail(self, msg, code=500):
        self._send(code, {"ok": False, "error": msg})

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        global CFG
        if self.path in ("/", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                self._send(200, body=f.read(), ctype="text/html")
        elif self.path == "/api/health":
            CFG = load_config()  # allow editing config.json without restart
            models, ollama_err = list_models()
            token_set = "PUT_YOUR" not in CFG["notion"]["token"]
            self._ok({"ollama_ok": ollama_err is None, "ollama_error": ollama_err,
                      "models": models, "default_model": CFG["ollama"]["model"],
                      "notion_token_set": token_set,
                      "fail_labels": CFG.get("fail_labels", ["Fail"])})
        elif self.path.startswith("/api/sentences"):
            data, err = list_sentences()
            self._ok(data) if not err else self._fail(err)
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        try:
            body = self._json_body()
        except Exception as e:
            return self._fail(f"bad json: {e}", 400)

        if self.path == "/api/translate":
            japanese = (body.get("japanese") or "").strip()
            if not japanese:
                return self._fail("japanese is required", 400)
            data, err = translate(japanese, body.get("model"))
        elif self.path == "/api/sentences":
            if not body.get("english"):
                return self._fail("english is required", 400)
            data, err = save_sentence(body.get("japanese", ""), body["english"],
                                      body.get("memo", ""))
        elif self.path == "/api/words":
            if not body.get("word"):
                return self._fail("word is required", 400)
            data, err = save_word(body["word"], body.get("meaning", ""),
                                  body.get("example", ""), body.get("source_page_id"))
        elif self.path == "/api/fail":
            if not body.get("page_id"):
                return self._fail("page_id is required", 400)
            data, err = record_fail(body["page_id"], body.get("label", "Fail"))
        else:
            return self._send(404, {"ok": False, "error": "not found"})

        self._ok(data) if not err else self._fail(err)

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


def main():
    host = CFG["server"].get("host", "0.0.0.0")
    port = CFG["server"].get("port", 8765)
    print(f"English Learning App server: http://localhost:{port}")
    print("From your phone (same Wi-Fi): http://<Mac-IP>:%d" % port)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
