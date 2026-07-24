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

APP_VERSION = "1.30.0"  # 機能変更時にここを更新（画面右上に表示される）

# 記事モードの失敗ラベル（Notion運用ルール準拠）: label, 意味
ARTICLE_FAIL_LABELS = [
    {"code": "F", "name": "Fail(基本)"},
    {"code": "R", "name": "声母・翘舌(zh/ch/sh↔z/c/s)"},
    {"code": "V", "name": "韻母(母音・鼻音)"},
    {"code": "T", "name": "声調"},
    {"code": "N", "name": "数字2(两/二)"},
]

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
DATA_FILES = ["sentences.json", "words.json", "sentences.md", "words.md",
              "sentences_zh.json", "words_zh.json", "sentences_zh.md", "words_zh.md",
              "articles_zh.json"]

try:
    from notion_client import NotionClient
except ImportError:
    NotionClient = None

try:
    from azure_speech import AzureSpeech, summarize as azure_summarize
except ImportError:
    AzureSpeech = None
    azure_summarize = None


def make_azure():
    if AzureSpeech is None:
        return None
    return AzureSpeech(CFG.get("azure") or {})


AZURE = None


def make_notion():
    n = CFG.get("notion")
    if not n or NotionClient is None:
        return None
    return NotionClient(n)


NOTION = make_notion()
AZURE = make_azure()


def sname(lang):
    return "sentences_zh.json" if lang == "zh" else "sentences.json"


def wname(lang):
    return "words_zh.json" if lang == "zh" else "words.json"


SENT_FILES = ["sentences.json", "sentences_zh.json"]
WORD_FILES = ["words.json", "words_zh.json"]


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


PUSH_LOCK = threading.Lock()  # Drive書き込みを直列化（同名ファイル二重作成の競合を防ぐ）


def drive_push_async():
    """Upload all data files to the Drive folder in the background."""
    if not (DRIVE and DRIVE.configured()):
        return
    def _run():
        with PUSH_LOCK:  # 複数の保存が同時でも1つずつ順番に送る
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
    # 英語・中国語の文/単語に加え、記事データも起動時に復元する
    for name in SENT_FILES + WORD_FILES + ["articles_zh.json"]:
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
    for lang, label in (("en", "English"), ("zh", "Chinese")):
        suffix = "_zh" if lang == "zh" else ""
        sentences = _load(sname(lang))
        words = _load(wname(lang))

        lines = [f"# {label} Sentences", ""]
        for s in reversed(sentences):
            lines.append(f"## {s['english']}")
            if s.get("pinyin"):
                lines.append(f"- 拼音: {s['pinyin']}")
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
        with open(_file(f"sentences{suffix}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        by_id = {s["id"]: s for s in sentences}
        lines = [f"# {label} Words", "", "| Word | 意味 | 例文 | 登録日 |",
                 "|---|---|---|---|"]
        for w in reversed(words):
            src = by_id.get(w.get("source_id"), {})
            example = w.get("example") or src.get("english", "")
            wcell = f"**{w['word']}**" + (f" ({w['pinyin']})" if w.get("pinyin") else "")
            lines.append(f"| {wcell} | {w.get('meaning','')} | {example} | {w['created']} |")
        with open(_file(f"words{suffix}.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
    drive_push_async()  # 変更のたびにDriveフォルダへAPIで反映


def migrate_ids():
    """既存データにIDが無いレコードがあれば固有IDを付与する。"""
    with LOCK:
        changed = False
        for name in SENT_FILES + WORD_FILES:
            items = _load(name)
            fixed = False
            for it in items:
                if not it.get("id"):
                    it["id"] = uuid.uuid4().hex
                    fixed = True
            if fixed:
                _save(name, items)
                changed = True
                print(f"[migrate] assigned ids in {name}")
        if changed:
            regen_markdown()


def update_sentence(sentence_id, japanese, english, memo="", marked=""):
    """既存の文を上書き（実施履歴・fail履歴・登録日は保持）。IDで両言語から検索。"""
    with LOCK:
        for fname in SENT_FILES:
            items = _load(fname)
            for s in items:
                if s["id"] == sentence_id:
                    s["japanese"] = japanese or s.get("japanese", "")
                    s["english"] = english
                    s["marked"] = marked or english
                    if memo:
                        s["memo"] = memo
                    if fname == "sentences_zh.json":
                        s["pinyin"] = to_pinyin(english)
                    _save(fname, items)
                    regen_markdown()
                    return {"id": sentence_id, "updated": True}, None
    return None, "sentence not found"


def save_sentence(japanese, english, memo="", marked="", lang="en"):
    with LOCK:
        items = _load(sname(lang))
        rec = {"id": uuid.uuid4().hex, "japanese": japanese, "english": english,
               "marked": marked or english,  # 「/」区切り位置付きの原文
               "memo": memo, "created": now(), "fails": []}
        if lang == "zh":
            rec["pinyin"] = to_pinyin(english)
        items.append(rec)
        _save(sname(lang), items)
        regen_markdown()
    return {"id": rec["id"]}, None


def list_sentences(limit=200, lang="en"):
    items = _load(sname(lang))
    out = []
    for s in reversed(items[-200:]):
        practices = s.get("practices", [])
        out.append({"id": s["id"], "english": s["english"], "japanese": s["japanese"],
                    "marked": s.get("marked") or s["english"],
                    "pinyin": s.get("pinyin", ""),
                    "created": s.get("created", "")[:10],
                    "fail_count": len(s.get("fails", [])),
                    "practice_count": len(practices),
                    "last_practiced": practices[-1][:10] if practices else ""})
    return out[:limit], None


def record_practice(sentence_id):
    """Auto-log the date/time a sentence was practiced (spoken)."""
    with LOCK:
        for fname in SENT_FILES:
            items = _load(fname)
            for s in items:
                if s["id"] == sentence_id:
                    s.setdefault("practices", []).append(now())
                    _save(fname, items)
                    regen_markdown()
                    return {"practice_count": len(s["practices"]),
                            "last_practiced": s["practices"][-1][:10]}, None
    return None, "sentence not found"


def delete_sentence(sentence_id):
    with LOCK:
        for fname in SENT_FILES:
            items = _load(fname)
            remaining = [s for s in items if s["id"] != sentence_id]
            if len(remaining) != len(items):
                _save(fname, remaining)
                regen_markdown()
                return {"deleted": sentence_id}, None
    return None, "sentence not found"


def list_words(limit=500, lang="en"):
    words = _load(wname(lang))
    sentences = {s["id"]: s for s in _load(sname(lang))}
    out = []
    for w in reversed(words[-500:]):
        src = sentences.get(w.get("source_id"), {})
        out.append({"id": w["id"], "word": w["word"], "meaning": w.get("meaning", ""),
                    "example": w.get("example") or src.get("english", ""),
                    "pinyin": w.get("pinyin", ""),
                    "created": w.get("created", "")[:10]})
    return out[:limit], None


def delete_word(word_id):
    with LOCK:
        for fname in WORD_FILES:
            items = _load(fname)
            remaining = [w for w in items if w["id"] != word_id]
            if len(remaining) != len(items):
                _save(fname, remaining)
                regen_markdown()
                return {"deleted": word_id}, None
    return None, "word not found"


def save_word(word, meaning, example="", source_id=None, lang="en"):
    with LOCK:
        items = _load(wname(lang))
        rec = {"id": uuid.uuid4().hex, "word": word, "meaning": meaning,
               "example": example, "source_id": source_id, "created": now()}
        if lang == "zh":
            rec["pinyin"] = to_pinyin(word)
        items.append(rec)
        _save(wname(lang), items)
        regen_markdown()
    return {"id": rec["id"]}, None


# ---------------------------------------------------------------- articles
def _articles():
    return _load("articles_zh.json")


def articles_refresh(limit=4):
    """未取り込みの新規記事を最大limit件だけ取り込み、残数を返す（UIが繰り返す）。"""
    if not (NOTION and NOTION.configured()):
        return None, "Notion未設定（config.jsonのnotion.tokenを確認）"
    remote, err = NOTION.list_articles()
    if err:
        return None, f"Notion一覧取得エラー: {err}"
    have = {a["notion_page_id"] for a in _articles()}
    todo = [r for r in remote if r["id"] not in have]
    imported = []
    for r in todo[:limit]:
        art, perr = NOTION.parse_article(r["id"])  # ネットワークはロック外で
        if perr:
            print(f"[articles] parse {r['title']} failed: {perr}")
            continue
        art["id"] = uuid.uuid4().hex
        art["imported_at"] = now()
        art["fails"] = []  # [{idx, ci, char, syllable, label, time, pushed, sessioned}]
        art["sessions"] = []  # [{date, misses, total, nomiss}]
        total = 0
        for s in art["sentences"]:
            s["pairs"] = to_pinyin_pairs(s["zh"])  # [文字, 拼音]の列（1文字表示用）
            s["breaks"] = []  # 節区切り位置（文字indexの後で区切る）
            total += count_hanzi(s["zh"])
        art["total_chars"] = total
        with LOCK:
            local = _articles()
            if art["notion_page_id"] not in {a["notion_page_id"] for a in local}:
                local.append(art)
                _save("articles_zh.json", local)
        imported.append(art["title"])
    if imported:
        drive_push_async()
    remaining = max(0, len(todo) - len(imported))
    return {"imported": imported, "remaining": remaining,
            "total": len(_articles())}, None


def articles_list():
    out = []
    for a in _articles():
        pending = sum(1 for f in a.get("fails", []) if not f.get("pushed"))
        sessions = a.get("sessions", [])
        last = sessions[-1] if sessions else None
        out.append({"id": a["id"], "title": a["title"], "date": a.get("date", ""),
                    "jp_title": a.get("jp_title", ""), "zh_title": a.get("zh_title", ""),
                    "studied": bool(sessions),
                    "last_studied": last["date"] if last else "",
                    "nomiss": last["nomiss"] if last else None,
                    "study_count": len(sessions),
                    "pending_fails": pending,
                    "notion_page_id": a.get("notion_page_id", "")})
    out.sort(key=lambda x: x["date"], reverse=True)
    return out, None


def articles_get(article_id):
    for a in _articles():
        if a["id"] == article_id:
            # 拼音ペアは常に最新ロジックで再計算（数字の拼音などを反映）
            for s in a.get("sentences", []):
                s["pairs"] = to_pinyin_pairs(s["zh"])
            for v in a.get("vocab", []):
                v["pairs"] = to_pinyin_pairs(v["zh"])
            return a, None
    return None, "article not found"


def article_fail(article_id, idx, ci, char="", syllable="", label="F"):
    """記事の1文字に対するFailを記録/更新（同じ文字は上書き）。ci=文字index。"""
    if not article_id or idx is None or ci is None:
        return None, "article_id, idx, ci are required"
    with LOCK:
        arts = _articles()
        for a in arts:
            if a["id"] != article_id:
                continue
            fails = a.setdefault("fails", [])
            # 同じ(句,文字)が既にあればラベル更新、無ければ追加
            for f in fails:
                if f["idx"] == idx and f.get("ci") == ci:
                    f["label"] = label
                    f["time"] = now()
                    f["pushed"] = False
                    break
            else:
                fails.append({"idx": idx, "ci": ci, "char": char,
                              "syllable": syllable, "label": label,
                              "time": now(), "pushed": False, "sessioned": False})
            _save("articles_zh.json", arts)
            drive_push_async()
            pending = sum(1 for f in fails if not f.get("pushed"))
            return {"pending_fails": pending}, None
    return None, "article not found"


def article_unfail(article_id, idx, ci):
    with LOCK:
        arts = _articles()
        for a in arts:
            if a["id"] != article_id:
                continue
            fails = a.get("fails", [])
            a["fails"] = [f for f in fails if not (f["idx"] == idx and f.get("ci") == ci)]
            _save("articles_zh.json", arts)
            drive_push_async()
            return {"pending_fails": sum(1 for f in a["fails"] if not f.get("pushed"))}, None
    return None, "article not found"


def article_set_breaks(article_id, idx, breaks):
    """節区切り位置（文字indexの後で区切る）を保存。"""
    with LOCK:
        arts = _articles()
        for a in arts:
            if a["id"] != article_id:
                continue
            for s in a.get("sentences", []):
                if s["idx"] == idx:
                    s["breaks"] = sorted(set(int(b) for b in breaks))
                    _save("articles_zh.json", arts)
                    drive_push_async()
                    return {"ok": True}, None
    return None, "sentence not found"


def article_session(article_id):
    """勉強完了：今回のミス数からNomiss率を計算しセッション記録。"""
    with LOCK:
        arts = _articles()
        for a in arts:
            if a["id"] != article_id:
                continue
            total = a.get("total_chars", 0) or 1
            new = [f for f in a.get("fails", []) if not f.get("sessioned")]
            misses = len(new)
            for f in new:
                f["sessioned"] = True
            nomiss = round(100 * (total - misses) / total, 1)
            sess = {"date": now()[:10], "misses": misses,
                    "total": total, "nomiss": nomiss}
            a.setdefault("sessions", []).append(sess)
            _save("articles_zh.json", arts)
            drive_push_async()
            return sess, None
    return None, "article not found"


def article_push_fails(article_id):
    """未反映のFailを、Notion記事末尾の失敗履歴テーブルへ書き戻す。"""
    if not (NOTION and NOTION.configured()):
        return None, "Notion未設定"
    with LOCK:
        arts = _articles()
        art = next((a for a in arts if a["id"] == article_id), None)
        if not art:
            return None, "article not found"
        pending = [f for f in art.get("fails", []) if not f.get("pushed")]
        if not pending:
            return {"pushed": 0}, None
        rows = [[f["time"][:10], f"第{f['idx']}句", f.get("char", ""),
                 f.get("syllable", ""), f.get("label", "F")] for f in pending]
        page_id = art["notion_page_id"]
        table_id = art.get("notion_fail_table_id")
        if not table_id:
            table_id, err = NOTION.find_fail_table(page_id)
            if err:
                return None, f"Notion確認エラー: {err}"
        if table_id:
            err = NOTION.append_fail_rows(table_id, rows)
            if err:
                return None, f"Notion追記エラー: {err}"
        else:
            table_id, err = NOTION.create_fail_table(page_id, rows)
            if err:
                return None, f"Notion作成エラー: {err}"
            art["notion_fail_table_id"] = table_id
        for f in pending:
            f["pushed"] = True
        _save("articles_zh.json", arts)
        drive_push_async()
    return {"pushed": len(rows)}, None


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


TRANSLATE_PROMPTS = {
    "en": """Translate the Japanese text into natural, conversational English.
The learner is an elementary-school child, so use simple, friendly words
that a kid would actually say. Keep it short and natural.
Output ONLY the English translation. No explanations, no quotes.

Japanese text:
""",
    "zh": """Translate the Japanese text into natural, conversational Chinese
(Simplified characters). The learner is an elementary-school child, so use
simple, friendly words that a kid would actually say. Keep it short and natural.
Output ONLY the Chinese translation. No explanations, no quotes, no pinyin.

Japanese text:
""",
}

KEYWORDS_PROMPTS = {
    "en": """From the English sentence below, pick up to 3 keywords/phrases
worth memorizing for a Japanese learner.
Rules:
- "word" MUST be English, copied exactly from the English sentence.
- "meaning" MUST be Japanese, copied from the original Japanese text below
  (the expression that corresponds to the word). Do NOT invent a new translation.
Respond ONLY with JSON: {"keywords": [{"word": "...", "meaning": "..."}]}
""",
    "zh": """From the Chinese sentence below, pick up to 3 keywords/phrases
worth memorizing for a Japanese learner.
Rules:
- "word" MUST be Chinese, copied exactly from the Chinese sentence.
- "meaning" MUST be Japanese, copied from the original Japanese text below
  (the expression that corresponds to the word). Do NOT invent a new translation.
Respond ONLY with JSON: {"keywords": [{"word": "...", "meaning": "..."}]}
""",
}


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


# ---------------------------------------------------------------- pinyin
_pypinyin_tried = False


def _ensure_pypinyin():
    global _pypinyin_tried
    try:
        import pypinyin  # noqa: F401
        return True
    except ImportError:
        if _pypinyin_tried:
            return False
        _pypinyin_tried = True
        import subprocess
        import sys
        for args in (["-m", "pip", "install", "--user", "pypinyin"],
                     ["-m", "pip", "install", "--break-system-packages", "pypinyin"]):
            try:
                subprocess.run([sys.executable] + args, capture_output=True, timeout=180)
                import importlib
                importlib.invalidate_caches()
                import pypinyin  # noqa: F401
                print("[pinyin] pypinyin installed")
                return True
            except Exception:
                continue
        print("[pinyin] pypinyin unavailable (pip install pypinyin を手動実行してください)")
        return False


def to_pinyin(text):
    if not text or not _ensure_pypinyin():
        return ""
    from pypinyin import lazy_pinyin, Style
    return " ".join(lazy_pinyin(text, style=Style.TONE))


DIGIT_PY = {"0": "líng", "1": "yī", "2": "èr", "3": "sān", "4": "sì",
            "5": "wǔ", "6": "liù", "7": "qī", "8": "bā", "9": "jiǔ"}


def to_pinyin_pairs(text):
    """各文字を [文字, その字の拼音] に対応付ける（1文字ずつ表示・選択用）。
    漢字は拼音、算用数字は1文字ずつの読み（2→èr 等）、句読点・英字・空白は空。"""
    if not text:
        return []
    ok = _ensure_pypinyin()
    from pypinyin import pinyin, Style
    pairs = []
    for ch in text:
        if ok and "一" <= ch <= "鿿":
            py = pinyin(ch, style=Style.TONE, errors="default")
            pairs.append([ch, py[0][0] if py and py[0] else ""])
        elif ch in DIGIT_PY:
            pairs.append([ch, DIGIT_PY[ch]])
        else:
            pairs.append([ch, ""])
    return pairs


def count_hanzi(text):
    return sum(1 for ch in (text or "") if "一" <= ch <= "鿿")


_jieba_tried = False


def _ensure_jieba():
    global _jieba_tried
    try:
        import jieba  # noqa: F401
        return True
    except ImportError:
        if _jieba_tried:
            return False
        _jieba_tried = True
        import subprocess
        import sys
        for args in (["-m", "pip", "install", "--user", "jieba"],
                     ["-m", "pip", "install", "--break-system-packages", "jieba"]):
            try:
                subprocess.run([sys.executable] + args, capture_output=True, timeout=180)
                import importlib
                importlib.invalidate_caches()
                import jieba  # noqa: F401
                print("[jieba] installed")
                return True
            except Exception:
                continue
        print("[jieba] unavailable (中国語の単語分割は句読点区切りにフォールバック)")
        return False


def to_wav16k(audio_bytes):
    """webm/opus等を16kHz mono WAVへ変換（ffmpegがあれば）。失敗時はNone。"""
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return None
    try:
        p = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000",
             "-f", "wav", "pipe:1"],
            input=audio_bytes, capture_output=True, timeout=60)
        return p.stdout if p.returncode == 0 and p.stdout else None
    except Exception as e:
        print(f"[audio] convert failed: {e}")
        return None


def segment_zh(text):
    """中国語を単語（词）に分割。jieba不可なら空リスト（クライアントは句読点区切りに）。"""
    if not text or not _ensure_jieba():
        return []
    import jieba
    return [w for w in jieba.lcut(text) if w.strip()]


def _has_japanese(s):
    return bool(re.search(r"[぀-ヿ㐀-鿿]", s or ""))


def _has_kana(s):
    """ひらがな・カタカナを含むか（中国語モードでの日本語判定用。漢字は除外）"""
    return bool(re.search(r"[぀-ゟ゠-ヿ]", s or ""))


def _clean(text):
    """Strip <think> blocks (reasoning models) and surrounding quotes."""
    text = re.sub(r"<think>.*?(</think>|$)", "", text or "", flags=re.S)
    return text.strip().strip('"').strip()


def translate(japanese, model=None, lang="en"):
    """Fast path: translation only (short plain-text output)."""
    prompt = TRANSLATE_PROMPTS.get(lang, TRANSLATE_PROMPTS["en"]) + japanese
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
        return None, (f"モデル '{used}' から訳文が得られませんでした。"
                      "思考型モデル（qwen3, deepseek-r1等）の場合は "
                      "qwen2.5:1.5b など通常モデルに切り替えてください "
                      "（詳細は logs/server.log）")
    result = {"english": english}
    if lang == "zh":
        result["pinyin"] = to_pinyin(english)
    return result, None


def extract_keywords(english, japanese="", model=None, lang="en"):
    """Slow path: fetched by the UI in the background after translation."""
    label = "Chinese" if lang == "zh" else "English"
    prompt = (KEYWORDS_PROMPTS.get(lang, KEYWORDS_PROMPTS["en"])
              + f"\n{label} sentence:\n{english}\n"
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
    keywords = []
    for k in parsed.get("keywords", []):
        if not (isinstance(k, dict) and k.get("word")):
            continue
        w = str(k.get("word", "")).strip()
        m = str(k.get("meaning", "")).strip()
        # LLMがword/meaningを取り違えた場合の補正（逆なら入れ替え、不正なら除外）
        bad = _has_kana if lang == "zh" else _has_japanese  # zhは漢字OK・かなNG
        if bad(w) and not bad(m):
            w, m = m, w
        if bad(w) or not w:
            continue
        rec = {"word": w, "meaning": m}
        if lang == "zh":
            rec["pinyin"] = to_pinyin(w)
        keywords.append(rec)
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

    def _lang(self):
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        return (q.get("lang") or ["en"])[0]

    def _handle_assess(self):
        """録音音声（生バイト）＋正解テキストを受けて発音評価を返す。"""
        global AZURE
        from urllib.parse import urlparse, parse_qs, unquote
        q = parse_qs(urlparse(self.path).query)
        text = unquote((q.get("text") or [""])[0])
        lang = (q.get("lang") or ["zh"])[0]
        length = int(self.headers.get("Content-Length") or 0)
        audio = self.rfile.read(length) if length else b""
        if not text:
            return self._fail("text is required", 400)
        if not audio:
            return self._fail("audio is empty", 400)
        # 解析用に録音を保存（recordings/ 配下・最新20件）
        try:
            rec_dir = os.path.join(BASE_DIR, "recordings")
            os.makedirs(rec_dir, exist_ok=True)
            ext = ".webm" if "webm" in (self.headers.get("X-Audio-Type") or "") else ".bin"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            with open(os.path.join(rec_dir, f"{ts}{ext}"), "wb") as f:
                f.write(audio)
            with open(os.path.join(rec_dir, f"{ts}.txt"), "w", encoding="utf-8") as f:
                f.write(text)
            olds = sorted(os.listdir(rec_dir))
            for old in olds[:-40]:
                try:
                    os.remove(os.path.join(rec_dir, old))
                except OSError:
                    pass
        except Exception as e:
            print(f"[rec] save failed: {e}")

        AZURE = make_azure()
        if not (AZURE and AZURE.configured()):
            return self._fail("Azure未設定（config.jsonのazure.keyを設定してください）")
        locale = "zh-CN" if lang == "zh" else "en-US"
        ctype = self.headers.get("X-Audio-Type") or "audio/webm; codecs=opus"
        # AzureはWAV(PCM16k)で最も正確。WAV以外はffmpegがあれば変換して送る
        if "wav" not in ctype.lower():
            conv = to_wav16k(audio)
            if conv:
                audio, ctype = conv, "audio/wav; codecs=audio/pcm; samplerate=16000"
        raw, err = AZURE.assess(audio, text, locale, ctype)
        if err:
            return self._fail(err)
        pairs = to_pinyin_pairs(text) if lang == "zh" else None
        data = azure_summarize(raw, pairs)
        if not data.get("ok"):
            return self._fail(data.get("error", "評価できませんでした"))
        self._ok(data)

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
            global NOTION
            NOTION = make_notion()
            self._ok({"version": APP_VERSION,
                      "ollama_ok": ollama_err is None, "ollama_error": ollama_err,
                      "models": models, "default_model": CFG["ollama"]["model"],
                      "storage_path": data_dir, "storage_mode": mode,
                      "drive_ready": drive_ready, "drive_error": drive_err,
                      "notion_ready": bool(NOTION and NOTION.configured()),
                      "azure_ready": bool(make_azure() and make_azure().configured()),
                      "fail_labels": CFG.get("fail_labels", ["Fail"]),
                      "article_fail_labels": ARTICLE_FAIL_LABELS})
        elif self.path.startswith("/api/sentences"):
            data, err = list_sentences(lang=self._lang())
            self._ok(data) if not err else self._fail(err)
        elif self.path.startswith("/api/words"):
            data, err = list_words(lang=self._lang())
            self._ok(data) if not err else self._fail(err)
        elif self.path == "/api/articles":
            data, err = articles_list()
            self._ok(data) if not err else self._fail(err)
        elif self.path.startswith("/api/article?"):
            from urllib.parse import urlparse, parse_qs
            aid = (parse_qs(urlparse(self.path).query).get("id") or [""])[0]
            data, err = articles_get(aid)
            self._ok(data) if not err else self._fail(err, 404)
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path.startswith("/api/assess"):
            return self._handle_assess()
        try:
            body = self._json_body()
        except Exception as e:
            return self._fail(f"bad json: {e}", 400)

        lang = body.get("lang", "en") if isinstance(body, dict) else "en"
        if self.path == "/api/translate":
            japanese = (body.get("japanese") or "").strip()
            if not japanese:
                return self._fail("japanese is required", 400)
            data, err = translate(japanese, body.get("model"), lang)
        elif self.path == "/api/pinyin":
            texts = body.get("texts") or []
            data, err = {"pinyins": [to_pinyin(t) for t in texts],
                         "pairs": [to_pinyin_pairs(t) for t in texts],
                         "words": [segment_zh(t) for t in texts]}, None
        elif self.path == "/api/keywords":
            english = (body.get("english") or "").strip()
            if not english:
                return self._fail("english is required", 400)
            data, err = extract_keywords(english, body.get("japanese", ""),
                                         body.get("model"), lang)
        elif self.path == "/api/sentences":
            if not body.get("english"):
                return self._fail("english is required", 400)
            if body.get("id"):  # ID指定なら上書き
                data, err = update_sentence(body["id"], body.get("japanese", ""),
                                            body["english"], body.get("memo", ""),
                                            body.get("marked", ""))
            else:
                data, err = save_sentence(body.get("japanese", ""), body["english"],
                                          body.get("memo", ""), body.get("marked", ""),
                                          lang)
        elif self.path == "/api/words/delete":
            if not body.get("id"):
                return self._fail("id is required", 400)
            data, err = delete_word(body["id"])
        elif self.path == "/api/words":
            if not body.get("word"):
                return self._fail("word is required", 400)
            data, err = save_word(body["word"], body.get("meaning", ""),
                                  body.get("example", ""), body.get("source_id"),
                                  lang)
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
        elif self.path == "/api/articles/refresh":
            data, err = articles_refresh(int(body.get("limit", 4)))
        elif self.path == "/api/articles/fail":
            data, err = article_fail(body.get("article_id"), body.get("idx"),
                                     body.get("ci"), body.get("char", ""),
                                     body.get("syllable", ""), body.get("label", "F"))
        elif self.path == "/api/articles/unfail":
            data, err = article_unfail(body.get("article_id"), body.get("idx"),
                                       body.get("ci"))
        elif self.path == "/api/articles/breaks":
            data, err = article_set_breaks(body.get("article_id"), body.get("idx"),
                                           body.get("breaks", []))
        elif self.path == "/api/articles/session":
            data, err = article_session(body.get("article_id"))
        elif self.path == "/api/articles/push":
            data, err = article_push_fails(body.get("article_id"))
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
    migrate_ids()  # 既存データへの固有ID付与（無いものだけ）
    warm_up()  # preload the model at startup

    srv = ThreadingHTTPServer((host, port), Handler)
    # 録音（マイク）はHTTPSまたはlocalhostでのみ許可されるため、証明書があればTLS化
    cert = CFG["server"].get("certfile")
    key = CFG["server"].get("keyfile")
    if cert and key and os.path.exists(os.path.join(BASE_DIR, cert)) \
            and os.path.exists(os.path.join(BASE_DIR, key)):
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(os.path.join(BASE_DIR, cert), os.path.join(BASE_DIR, key))
        srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
        print(f"HTTPS 有効: https://<このMacの名前>:{port}  （マイク録音が使えます）")
    srv.serve_forever()


if __name__ == "__main__":
    main()
