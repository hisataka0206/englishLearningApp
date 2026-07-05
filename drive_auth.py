#!/usr/bin/env python3
"""One-time Google Drive authorization (run on the Mac: python3 drive_auth.py).

Prerequisite (once, in Google Cloud Console https://console.cloud.google.com):
 1. Create a project (any name)
 2. APIs & Services > Library > enable "Google Drive API"
 3. APIs & Services > OAuth consent screen > External > add yourself as test user
 4. APIs & Services > Credentials > Create Credentials > OAuth client ID
    > Application type: "Desktop app"
 5. Copy the client ID / client secret into config.json (storage.drive)

This script opens a browser for consent and saves drive_token.json.
The server then uploads data files to the configured Drive folder automatically.
"""

import json
import os
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(BASE_DIR, "config.json"), encoding="utf-8"))
DRIVE = CFG["storage"]["drive"]
PORT = 8767
REDIRECT = f"http://localhost:{PORT}/"
SCOPE = "https://www.googleapis.com/auth/drive"

if "PUT_YOUR" in DRIVE.get("client_id", ""):
    raise SystemExit("先に config.json の storage.drive.client_id / client_secret を設定してください"
                     "（手順はこのファイル冒頭のコメント参照）")

auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": DRIVE["client_id"],
    "redirect_uri": REDIRECT,
    "response_type": "code",
    "scope": SCOPE,
    "access_type": "offline",
    "prompt": "consent",
})

code_holder = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code_holder["code"] = (qs.get("code") or [None])[0]
        ok = code_holder["code"] is not None
        msg = "認証OK。このタブは閉じてください。" if ok else "認証に失敗しました。"
        body = f"<meta charset='utf-8'><h2>{msg}</h2>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


print("ブラウザで認証画面を開きます...")
print(f"開かない場合はこのURLを開いてください:\n{auth_url}\n")
webbrowser.open(auth_url)
srv = HTTPServer(("localhost", PORT), Handler)
while "code" not in code_holder:
    srv.handle_request()
if not code_holder["code"]:
    raise SystemExit("認証コードを取得できませんでした")

data = urllib.parse.urlencode({
    "client_id": DRIVE["client_id"],
    "client_secret": DRIVE["client_secret"],
    "code": code_holder["code"],
    "redirect_uri": REDIRECT,
    "grant_type": "authorization_code",
}).encode()
with urllib.request.urlopen(urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data), timeout=30) as r:
    tok = json.load(r)

if "refresh_token" not in tok:
    raise SystemExit(f"refresh_tokenが返りませんでした: {tok}")

token_path = os.path.join(BASE_DIR, DRIVE.get("token_file", "drive_token.json"))
with open(token_path, "w", encoding="utf-8") as f:
    json.dump({"refresh_token": tok["refresh_token"]}, f)
print(f"保存しました: {token_path}")
print("完了。サーバーを再起動すればDriveへの保存が有効になります。")
