#!/usr/bin/env python3
"""English Learning App - mini server.

- Serves the browser UI (index.html)
- /api/translate : Japanese -> English + keywords via local Ollama
- /api/sentences : save / list sentences (JSON files in Google Drive sync folder)
- /api/words     : register keywords (relation to source sentence by id)
- /api/fail      : record a fail (label + timestamp) on a sentence

Storage: JSON files (source of truth) + auto-generated Markdown views,
written into the Google Drive desktop-app sync folder so everything is
backed up to Drive automatically. No Google API / auth required.

Config lives in config.json next to this file.
Standard library only - no pip install required.
"""

import glob
import json
import os
import re
import threading
import urllib.request
import urllib.error
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOCK = threading.Lock()


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()


# ---------------------------------------------------------------- storage
def resolve_data_dir():
    """Return the data folder. "AUTO" finds the Google Drive sync folder."""
    conf = CFG.get("storage", {}).get("data_dir", "AUTO")
    if conf and conf != "AUTO":
        path = os.path.expanduser(conf)
    else:
        candidates = glob.glob(os.path.expanduser(
            "~/Library/CloudStorage/GoogleDrive-*/My Drive"))
        if candidates:
            path = os.path.join(candidates[0], "EnglishLearningApp")
        else:
            path = os.path.join(BASE_DIR, "data")  # fallback: local folder
    os.makedirs(path, exist_ok=True)
    return path


def _file(name):
    return os.path.join(resolve_data_dir(), name)


def _load(name):
    try:
        with open(_file(name), encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(name, items):
    tmp = _file(name) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _file(name))


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def regen_markdown():
    """Human-readable views for browsing in the Drive app."""
    sentences = _load("sentences.json")
    words = _load("words.json")

    lines = ["# English Sentences", ""]
    for s in reversed(sentences):
        lines.append(f"## {s['english']}")
        lines.append(f"- 日本語: {s['japanese']}")
        lines.append(f"- 登録日: {s['created']}  /  fail: {len(s.get('fails', []))}")
        for fl in s.get("fails", []):
            lines.append(f"  - ❌ {fl['label']} ({fl['time']})")
        if s.get("memo"):
            lines.append(f"- メモ: {s['memo']}")
        lines.append("")
    with open(_file("sentences.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    by_id = {s["id"]: s for s in sentences}
    lines = ["# English Words", "", "| Word | 意味 | 例文 | 登録日 |",
             "|---|---|---|---|"]
    for w in reversed(words):
        src = by_id.get(w.get("source_id"), {})
        example = w.get("example") or src.get("english", "")
        lines.append(f"| **{w['word']}** | {w.get('meaning','')} | {example} | {w['created']} |")
    with open(_file("words.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_sentence(japanese, english, memo=""):
    with LOCK:
        items = _load("sentences.json")
        rec = {"id": uuid.uuid4().hex, "japanese": japanese, "english": english,
               "memo": memo, "created": now(), "fails": []}
        items.append(rec)
        _save("sentences.json", items)
        regen_markdown()
    return {"id": rec["id"]}, None


def list_sentences(limit=20):
    items = _load("sentences.json")
    out = [{"id": s["id"], "english": s["english"], "japanese": s["japanese"],
            "fail_count": len(s.get("fails", []))}
           for s in reversed(items[-200:])]
    return out[:limit], None


def save_word(word, meaning, example="", source_id=None):
    with LOCK:
        items = _load("words.json")
        rec = {"id": uuid.uuid4().hex, "word": word, "meaning": meaning,
               "example": example, "source_id": source_id, "created": now()}
        items.append(rec)
        _save("words.json", items)
        regen_markdown()
    return {"id": rec["id"]}, None


def record_fail(sentence_id, label="Fail"):
    with LOCK:
        items = _load("sentences.json")
        for s in items:
            if s["id"] == sentence_id:
                s.setdefault("fails", []).append({"label": label, "time": now()})
                _save("sentences.json", items)
                regen_markdown()
                return {"fail_count": len(s["fails"])}, None
    return None, "sentence not found"


# ---------------------------------------------------------------- ollama
def http_json(url, payload=None, timeout=120):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data)
    req.add_header("Content-Type", "application/json")
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
            data_dir = resolve_data_dir()
            drive = "CloudStorage/GoogleDrive" in data_dir
            self._ok({"ollama_ok": ollama_err is None, "ollama_error": ollama_err,
                      "models": models, "default_model": CFG["ollama"]["model"],
                      "storage_path": data_dir, "storage_is_drive": drive,
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
                                  body.get("example", ""), body.get("source_id"))
        elif self.path == "/api/fail":
            if not body.get("id"):
                return self._fail("id is required", 400)
            data, err = record_fail(body["id"], body.get("label", "Fail"))
        else:
            return self._send(404, {"ok": False, "error": "not found"})

        self._ok(data) if not err else self._fail(err)

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


def main():
    host = CFG["server"].get("host", "0.0.0.0")
    port = CFG["server"].get("port", 8765)
    print(f"English Learning App server: http://localhost:{port}")
    print(f"Data folder: {resolve_data_dir()}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
