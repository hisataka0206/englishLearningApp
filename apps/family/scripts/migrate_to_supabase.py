#!/usr/bin/env python3
"""現行アプリのJSONデータを家族版（Supabase）へ移行する。

family-edition-spec.md §8 の規則に従う。冪等（on conflict do nothing 相当）。

使い方:
  # 1. まずドライラン（DBに書かずに変換結果と検証だけ表示）
  python3 migrate_to_supabase.py --data ../../data --dry-run

  # 2. 問題なければ本実行（要 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / USER_ID）
  export SUPABASE_URL=https://xxxx.supabase.co
  export SUPABASE_SERVICE_ROLE_KEY=eyJ...
  export USER_ID=<移行先ユーザーのUUID>
  python3 migrate_to_supabase.py --data ../../data
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
FILES = [
    ("sentences.json", "en"), ("sentences_zh.json", "zh"),
]
WORD_FILES = [("words.json", "en"), ("words_zh.json", "zh")]


def to_uuid(hex32: str) -> str:
    """hex32 → 8-4-4-4-12 のUUID形式（元IDを保持して source_id を解決可能にする）"""
    h = (hex32 or "").replace("-", "")
    if len(h) != 32:
        return ""
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def to_ts(s: str) -> str:
    """'%Y-%m-%d %H:%M:%S' のナイーブ時刻を JST として解釈し ISO8601 に"""
    if not s:
        return datetime.now(JST).isoformat()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt).replace(tzinfo=JST).isoformat()
        except ValueError:
            continue
    return datetime.now(JST).isoformat()


def load(data_dir: str, name: str):
    p = os.path.join(data_dir, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def build(data_dir: str, user_id: str):
    sentences, fails, practices, words = [], [], [], []
    for fname, lang in FILES:
        for s in load(data_dir, fname):
            sid = to_uuid(s.get("id", ""))
            if not sid:
                continue
            target = s.get("english", "")
            sentences.append({
                "id": sid, "user_id": user_id, "lang": lang,
                "japanese": s.get("japanese", ""), "target": target,
                "marked": s.get("marked") or target,
                "pinyin": s.get("pinyin") or None,
                "memo": s.get("memo", "") or "",
                "created_at": to_ts(s.get("created", "")),
            })
            for f in s.get("fails", []) or []:
                fails.append({"user_id": user_id, "sentence_id": sid,
                              "label": f.get("label", "Fail"),
                              "occurred_at": to_ts(f.get("time", ""))})
            for p in s.get("practices", []) or []:
                practices.append({"user_id": user_id, "sentence_id": sid,
                                  "occurred_at": to_ts(p)})
    sent_ids = {s["id"] for s in sentences}
    for fname, lang in WORD_FILES:
        for w in load(data_dir, fname):
            wid = to_uuid(w.get("id", ""))
            if not wid:
                continue
            src = to_uuid(w.get("source_id", "") or "")
            words.append({
                "id": wid, "user_id": user_id, "lang": lang,
                "word": w.get("word", ""), "meaning": w.get("meaning", "") or "",
                "example": w.get("example", "") or "",
                "pinyin": w.get("pinyin") or None,
                "source_id": src if src in sent_ids else None,
                "created_at": to_ts(w.get("created", "")),
            })
    return sentences, words, fails, practices


def post(table: str, rows: list, url: str, key: str, on_conflict: str = None):
    if not rows:
        return 0
    endpoint = f"{url}/rest/v1/{table}"
    if on_conflict:
        endpoint += f"?on_conflict={on_conflict}"
    sent = 0
    for i in range(0, len(rows), 200):     # 200件ずつ
        chunk = rows[i:i + 200]
        req = urllib.request.Request(endpoint, data=json.dumps(chunk).encode(), method="POST")
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        req.add_header("Content-Type", "application/json")
        req.add_header("Prefer", "resolution=ignore-duplicates,return=minimal")
        try:
            urllib.request.urlopen(req, timeout=60)
            sent += len(chunk)
        except urllib.error.HTTPError as e:
            print(f"  !! {table} {i}-{i+len(chunk)}: HTTP {e.code} {e.read()[:200].decode('utf-8','ignore')}")
            raise
    return sent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../../data", help="現行データのディレクトリ")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    user_id = os.environ.get("USER_ID", "00000000-0000-0000-0000-000000000000")
    sentences, words, fails, practices = build(args.data, user_id)

    # ---- 検証（spec §8.4）
    raw_sent = sum(len(load(args.data, f)) for f, _ in FILES)
    raw_word = sum(len(load(args.data, f)) for f, _ in WORD_FILES)
    print("=== 変換結果 ===")
    print(f"  sentences : {len(sentences):5d}  (元データ {raw_sent})")
    print(f"  words     : {len(words):5d}  (元データ {raw_word})")
    print(f"  fails     : {len(fails):5d}")
    print(f"  practices : {len(practices):5d}")
    print(f"  words.source_id 有り: {sum(1 for w in words if w['source_id'])}")
    ok = len(sentences) == raw_sent and len(words) == raw_word
    print(f"  件数一致  : {'OK' if ok else 'NG'}")
    if sentences:
        s = sentences[0]
        print(f"  サンプル  : [{s['lang']}] {s['japanese'][:20]} / {s['target'][:28]} / {s['created_at']}")

    if args.dry_run:
        print("\n（ドライラン。DBには書き込んでいません）")
        return 0 if ok else 1

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key or user_id.startswith("00000000"):
        print("\n!! SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / USER_ID を設定してください")
        return 1

    print("\n=== 投入 ===")
    print(f"  sentences : {post('sentences', sentences, url, key, 'id')}")
    print(f"  words     : {post('words', words, url, key, 'id')}")
    print(f"  fails     : {post('fails', fails, url, key)}")
    print(f"  practices : {post('practices', practices, url, key)}")
    print("完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
