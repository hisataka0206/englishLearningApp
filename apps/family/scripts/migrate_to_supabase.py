#!/usr/bin/env python3
"""現行アプリのJSONデータを家族版（Supabase）へ移行する。

family-edition-spec.md §8 の規則に従う。冪等（on conflict do nothing 相当）。

使い方:
  # 1. まずドライラン（DBに書かずに変換結果と検証だけ表示）
  python3 migrate_to_supabase.py --data ../../local/data --dry-run

  # 2. 問題なければ本実行（要 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / USER_ID）
  export SUPABASE_URL=https://xxxx.supabase.co     # ★末尾に「/」を付けない
  export SUPABASE_SERVICE_ROLE_KEY=sb_secret_...   # Secret（旧service_role）キー
  export USER_ID=<移行先ユーザーのUUID>
  python3 migrate_to_supabase.py --data ../../local/data
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


def normalize_url(raw: str) -> str:
    """SUPABASE_URL を正規化する。

    末尾に「/」が付いていると `.../rest/v1/x` が `...//rest/v1/x` になり、
    PostgREST が **PGRST125 Invalid path specified in request URL** を返す。
    ダッシュボードからコピーすると末尾スラッシュが付くことがあるので必ず落とす。
    """
    u = (raw or "").strip().rstrip("/")
    if u.endswith("/rest/v1"):          # 丸ごと貼られた場合
        u = u[: -len("/rest/v1")]
    return u


def check_env(url: str, key: str) -> list:
    """設定ミスを投入前に検出する（原因が分かるメッセージで返す）"""
    errs = []
    if not url.startswith("https://"):
        errs.append(f"SUPABASE_URL が https:// で始まっていない → {url!r}")
    if "supabase.co" not in url and "localhost" not in url:
        errs.append(f"SUPABASE_URL がSupabaseのURLに見えない → {url!r}")
    if key.startswith("sb_publishable_") or (key.startswith("eyJ") and "anon" in key):
        errs.append("Publishable（旧anon）キーが指定されている。**Secret（旧service_role）キー**が必要")
    return errs


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
            body = e.read()[:300].decode("utf-8", "ignore")
            print(f"  !! {table} {i}-{i+len(chunk)}: HTTP {e.code}")
            print(f"     URL  : {endpoint}")
            print(f"     応答 : {body}")
            if "PGRST125" in body:
                print("     → URLのパスが不正。SUPABASE_URL の末尾に「/」が付いていないか確認")
            elif e.code == 401:
                print("     → キーが違う。**Secret（旧service_role）キー**を使うこと")
            elif e.code == 404:
                print("     → テーブルが無い可能性。マイグレーション3本を適用したか確認")
            elif "violates foreign key" in body:
                print("     → USER_ID が実在しない。Authentication → Users のUIDを使うこと")
            raise
    return sent


def count_rows(table: str, url: str, key: str, user_id: str) -> int:
    """移行先に既に何行あるか（再実行の二重投入を防ぐため）"""
    ep = f"{url}/rest/v1/{table}?user_id=eq.{user_id}&select=*"
    req = urllib.request.Request(ep, method="HEAD")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Prefer", "count=exact")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            rng = r.headers.get("Content-Range", "*/0")   # 例 "0-9/10"
            return int(rng.split("/")[-1])
    except Exception:
        return -1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="../../local/data", help="現行データのディレクトリ")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="fails/practices が既にあっても続行する（二重投入を承知のうえで）")
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

    url = normalize_url(os.environ.get("SUPABASE_URL", ""))
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not url or not key or user_id.startswith("00000000"):
        print("\n!! SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY / USER_ID を設定してください")
        return 1

    errs = check_env(url, key)
    if errs:
        print("\n!! 設定を確認してください")
        for e in errs:
            print(f"   - {e}")
        return 1

    print(f"\n=== 投入先 ===\n  {url}/rest/v1/  (user_id={user_id})")

    # ---- 二重投入の防止（fails / practices は自然キーが無く冪等にできない）
    for t in ("fails", "practices"):
        n = count_rows(t, url, key, user_id)
        if n > 0:
            print(f"\n!! {t} に既に {n} 行あります。**このまま流すと二重に入ります**。")
            print(f"   やり直すなら SQL Editor で先に消してください:")
            print(f"     delete from {t} where user_id = '{user_id}';")
            print(f"   （--force を付ければ承知のうえで続行します）")
            if not args.force:
                return 1

    print("\n=== 投入 ===")
    print(f"  sentences : {post('sentences', sentences, url, key, 'id')}")
    print(f"  words     : {post('words', words, url, key, 'id')}")
    print(f"  fails     : {post('fails', fails, url, key)}")
    print(f"  practices : {post('practices', practices, url, key)}")

    # ---- 事後確認（spec §8.4）
    print("\n=== 投入後の件数 ===")
    for t in ("sentences", "words", "fails", "practices"):
        print(f"  {t:10s}: {count_rows(t, url, key, user_id)}")
    print("完了")
    return 0


if __name__ == "__main__":
    sys.exit(main())
