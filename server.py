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

APP_VERSION = "1.11.3"  # 機能変更時にここを更新（画面右上に表示される）

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
LOCK = threading.Lock()


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


CFG = load_config()

try:
    from google_drive import DriveClient, GasDriveClient
except ImportError:
    DriveClient = GasDriveClient = None


def make_drive():
    s = CFG.get("storage", {})
    backend = s.get("backend")
    if backend == "drive_gas" and GasDriveClient:
        return GasDriveClient(s.get("drive_gas", {}), BASE_DIR)
    if backend == "drive_api" and DriveClient:
        return DriveClient(s.get("drive", {}), BASE_DIR)
    return None


DRIVE = make_drive()
DATA_FILES = ["sentences.json", "words.json", "sentences.md", "words.md"]


# ---------------------------------------------------------------- storage
def resolve_data_dir():
    """Return the local data folder (working copy; Drive API pushes from here)."""
    conf = CFG.get("storage", {}).get("data_dir", "AUTO")
    if conf and conf != "AUTO":
        path = os.path.expanduser(conf)
    elif CFG.get("storage", {}).get("backend") in ("drive_api", "drive_gas"):
        path = os.path.join(BASE_DIR, "data")  # local cache; pushed via API
    else:
        candidates = glob.glob(os.path.expanduser(
            "~/Library/CloudStorage/GoogleDrive-*/My Drive"))
        if candidates:
            path = os.path.join(candidates[0], "EnglishLearningApp")
        else:
            path = os.path.join(BASE_DIR, "data")  # fallback: local folder
    os.makedirs(path, exist_ok=True)
    return path


def drive_push_async():
    """Upload all data files to the Drive folder in the background."""
    if not (DRIVE and DRIVE.configured()):
        return
    def _run():
        for name in DATA_FILES:
            p = _file(name)
            if not os.path.exists(p):
                continue
            try:
                mime = "text/markdown" if name.endswith(".md") else "application/json"
                with open(p, "rb") as f:
                    DRIVE.upsert(name, f.read(), mime)
            except Exception as e:
                print(f"[drive] push {name} failed: {e}")
    threading.Thread(target=_run, daemon=True).start()


def drive_pull_initial():
    """On startup, fetch data files from Drive if we have no local copy."""
    if not (DRIVE and DRIVE.configured()):
        return
    for name in ("sentences.json", "words.json"):
        p = _file(name)
        if os.path.exists(p):
            continue
        try:
            data = DRIVE.download(name)
            if data:
                with open(p, "wb") as f:
                    f.write(data)
                print(f"[drive] pulled {name}")
        except Exception as e:
            print(f"[drive] pull {name} failed: {e}")


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
        practices = s.get("practices", [])
        last = practices[-1] if practices else "未実施"
        lines.append(f"- 登録日: {s['created']}  /  実施: {len(practices)}回（最終: {last}）  /  fail: {len(s.get('fails', []))}")
        for fl in s.get("fails", []):
            lines.append(f"  - ❌ {fl['label']} ({fl['time']})")
        if practices:
            lines.append(f"  - 🗣 実施日: {', '.join(p[:10] for p in practices)}")
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
    drive_push_async()  # 変更のたびにDriveフォルダへAPIで反映


def save_sentence(japanese, english, memo="", marked=""):
    with LOCK:
        items = _load("sentences.json")
        rec = {"id": uuid.uuid4().hex, "japanese": japanese, "english": english,
               "marked": marked or english,  # 「/」区切り位置付きの原文
               "memo": memo, "created": now(), "fails": []}
        items.append(rec)
        _save("sentences.json", items)
        regen_markdown()
    return {"id": rec["id"]}, None


def list_sentences(limit=200):
    items = _load("sentences.json")
    out = []
    for s in reversed(items[-200:]):
        practices = s.get("practices", [])
        out.append({"id": s["id"], "english": s["english"], "japanese": s["japanese"],
                    "marked": s.get("marked") or s["english"],
                    "created": s.get("created", "")[:10],
                    "fail_count": len(s.get("fails", [])),
                    "practice_count": len(practices),
                    "last_practiced": practices[-1][:10] if practices else ""})
    return out[:limit], None


def record_practice(sentence_id):
    """Auto-log the date/time a sentence was practiced (spoken)."""
    with LOCK:
        items = _load("sentences.json")
        for s in items:
            if s["id"] == sentence_id:
                s.setdefault("practices", []).append(now())
                _save("sentences.json", items)
                regen_markdown()
                return {"practice_count": len(s["practices"]),
                        "last_practiced": s["practices"][-1][:10]}, None
    return None, "sentence not found"


def delete_sentence(sentence_id):
    with LOCK:
        items = _load("sentences.json")
        remaining = [s for s in items if s["id"] != sentence_id]
        if len(remaining) == len(items):
            return None, "sentence not found"
        _save("sentences.json", remaining)
        regen_markdown()
    return {"deleted": sentence_id}, None


def list_words(limit=500):
    words = _load("words.json")
    sentences = {s["id"]: s for s in _load("sentences.json")}
    out = []
    for w in reversed(words[-500:]):
        src = sentences.get(w.get("source_id"), {})
        out.append({"id": w["id"], "word": w["word"], "meaning": w.get("meaning", ""),
                    "example": w.get("example") or src.get("english", ""),
                    "created": w.get("created", "")[:10]})
    return out[:limit], None


def delete_word(word_id):
    with LOCK:
        items = _load("words.json")
        remaining = [w for w in items if w["id"] != word_id]
        if len(remaining) == len(items):
            return None, "word not found"
        _save("words.json", remaining)
        regen_markdown()
    return {"deleted": word_id}, None


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


TRANSLATE_PROMPT = """Translate the Japanese text into natural, conversational English.
Output ONLY the English translation. No explanations, no quotes.

Japanese text:
"""

KEYWORDS_PROMPT = """From the English sentence below, pick up to 3 keywords/phrases
worth memorizing for a Japanese learner.
For each keyword, "meaning" MUST be the corresponding expression copied from the
original Japanese text below. Use the exact wording that appears in the Japanese
text. Do NOT invent a new translation of the English word.
Respond ONLY with JSON: {"keywords": [{"word": "...", "meaning": "..."}]}
"""


def chat(prompt, model=None, json_mode=False, num_predict=None, think=None):
    o = CFG["ollama"]
    payload = {
        "model": model or o["model"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "keep_alive": o.get("keep_alive", "24h"),  # keep model in memory
        "options": {"temperature": 0.3},
    }
    if json_mode:
        payload["format"] = "json"
    if num_predict:
        payload["options"]["num_predict"] = num_predict
    if think is not None:
        payload["think"] = think  # reasoning models: skip thinking phase
    res, err = http_json(f"{o['base_url']}/api/chat", payload)
    if err:
        return None, f"Ollama error: {err}"
    msg = res.get("message") or {}
    if not (msg.get("content") or "").strip():
        print(f"[ollama] empty content. raw message: {json.dumps(msg, ensure_ascii=False)[:400]}")
    return msg.get("content", ""), None


def _clean(text):
    """Strip <think> blocks (reasoning models) and surrounding quotes."""
    text = re.sub(r"<think>.*?(</think>|$)", "", text or "", flags=re.S)
    return text.strip().strip('"').strip()


def translate(japanese, model=None):
    """Fast path: translation only (short plain-text output)."""
    prompt = TRANSLATE_PROMPT + japanese
    content, err = chat(prompt, model, num_predict=512)
    if err:
        return None, err
    english = _clean(content)
    if not english:  # reasoning model? retry with thinking disabled
        content, err2 = chat(prompt, model, think=False)
        if not err2:
            english = _clean(content)
    if not english:  # last resort: no token cap, no extras
        content, err3 = chat(prompt, model)
        if not err3:
            english = _clean(content)
    if not english:
        used = model or CFG["ollama"]["model"]
        return None, (f"モデル '{used}' から英文が得られませんでした。"
                      "思考型モデル（qwen3, deepseek-r1等）の場合は "
                      "qwen2.5:1.5b など通常モデルに切り替えてください "
                      "（詳細は logs/server.log）")
    return {"english": english}, None


def extract_keywords(english, japanese="", model=None):
    """Slow path: fetched by the UI in the background after translation."""
    prompt = (KEYWORDS_PROMPT
              + f"\nEnglish sentence:\n{english}\n"
              + f"\nOriginal Japanese text:\n{japanese}\n")
    content, err = chat(prompt, model, json_mode=True,
                        num_predict=400)
    if err:
        return None, err
    content = _clean(content)
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.S)
        if not m:
            return {"keywords": []}, None
        parsed = json.loads(m.group(0))
    keywords = [
        {"word": str(k.get("word", "")).strip(), "meaning": str(k.get("meaning", "")).strip()}
        for k in parsed.get("keywords", []) if isinstance(k, dict) and k.get("word")
    ]
    return {"keywords": keywords[:3]}, None


def warm_up():
    """Load the model into memory so the first request is fast."""
    def _run():
        chat("Hi", num_predict=1)
    threading.Thread(target=_run, daemon=True).start()


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
            global DRIVE
            CFG = load_config()  # allow editing config.json without restart
            DRIVE = make_drive()
            models, ollama_err = list_models()
            if not ollama_err:
                warm_up()  # preload model while the user is typing
            data_dir = resolve_data_dir()
            if CFG.get("storage", {}).get("backend") in ("drive_api", "drive_gas"):
                mode = "drive_api"
            elif "CloudStorage/GoogleDrive" in data_dir:
                mode = "sync"
            else:
                mode = "local"
            drive_err = None
            drive_ready = bool(DRIVE and DRIVE.configured())
            if drive_ready and hasattr(DRIVE, "ping"):
                drive_err = DRIVE.ping()  # 実通信で確認（設定値だけで✅にしない）
                drive_ready = drive_err is None
            self._ok({"version": APP_VERSION,
                      "ollama_ok": ollama_err is None, "ollama_error": ollama_err,
                      "models": models, "default_model": CFG["ollama"]["model"],
                      "storage_path": data_dir, "storage_mode": mode,
                      "drive_ready": drive_ready, "drive_error": drive_err,
                      "fail_labels": CFG.get("fail_labels", ["Fail"])})
        elif self.path.startswith("/api/sentences"):
            data, err = list_sentences()
            self._ok(data) if not err else self._fail(err)
        elif self.path.startswith("/api/words"):
            data, err = list_words()
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
        elif self.path == "/api/keywords":
            english = (body.get("english") or "").strip()
            if not english:
                return self._fail("english is required", 400)
            data, err = extract_keywords(english, body.get("japanese", ""),
                                         body.get("model"))
        elif self.path == "/api/sentences":
            if not body.get("english"):
                return self._fail("english is required", 400)
            data, err = save_sentence(body.get("japanese", ""), body["english"],
                                      body.get("memo", ""), body.get("marked", ""))
        elif self.path == "/api/words/delete":
            if not body.get("id"):
                return self._fail("id is required", 400)
            data, err = delete_word(body["id"])
        elif self.path == "/api/words":
            if not body.get("word"):
                return self._fail("word is required", 400)
            data, err = save_word(body["word"], body.get("meaning", ""),
                                  body.get("example", ""), body.get("source_id"))
        elif self.path == "/api/fail":
            if not body.get("id"):
                return self._fail("id is required", 400)
            data, err = record_fail(body["id"], body.get("label", "Fail"))
        elif self.path == "/api/practice":
            if not body.get("id"):
                return self._fail("id is required", 400)
            data, err = record_practice(body["id"])
        elif self.path == "/api/delete":
            if not body.get("id"):
                return self._fail("id is required", 400)
            data, err = delete_sentence(body["id"])
        else:
            return self._send(404, {"ok": False, "error": "not found"})

        self._ok(data) if not err else self._fail(err)

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")


def main():
    host = CFG["server"].get("host", "0.0.0.0")
    port = CFG["server"].get("port", 8765)
    print(f"English Learning App v{APP_VERSION}: http://localhost:{port}")
    print(f"Data folder: {resolve_data_dir()}")
    if DRIVE:
        print(f"Drive: {'ready' if DRIVE.configured() else 'NOT configured - see README (GAS deploy)'}")
        drive_pull_initial()
    warm_up()  # preload the model at startup
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
