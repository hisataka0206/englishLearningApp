"""Google Drive API client (standard library only).

Uploads the app's data files into a specific Drive folder using OAuth2
refresh tokens. Run drive_auth.py once to authorize and create the token
file, then the server pushes changes automatically.
"""

import json
import os
import threading
import time
import urllib.parse
import urllib.request


class DriveClient:
    def __init__(self, cfg, base_dir):
        self.client_id = cfg.get("client_id", "")
        self.client_secret = cfg.get("client_secret", "")
        self.folder_id = cfg.get("folder_id", "")
        self.token_file = os.path.join(base_dir, cfg.get("token_file", "drive_token.json"))
        self.api_base = cfg.get("api_base", "https://www.googleapis.com")
        self.token_url = cfg.get("token_url", "https://oauth2.googleapis.com/token")
        self._access = None
        self._expiry = 0
        self._lock = threading.Lock()
        self._ids = {}  # filename -> Drive file id cache

    def configured(self):
        return bool(self.client_id and "PUT_YOUR" not in self.client_id
                    and self.folder_id and os.path.exists(self.token_file))

    # ------------------------------------------------------------ auth
    def _refresh_access_token(self):
        with open(self.token_file, encoding="utf-8") as f:
            tok = json.load(f)
        data = urllib.parse.urlencode({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": tok["refresh_token"],
            "grant_type": "refresh_token",
        }).encode()
        req = urllib.request.Request(self.token_url, data=data)
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.load(r)
        self._access = res["access_token"]
        self._expiry = time.time() + res.get("expires_in", 3600) - 60

    def _token(self):
        with self._lock:
            if not self._access or time.time() > self._expiry:
                self._refresh_access_token()
            return self._access

    def _request(self, method, url, data=None, headers=None):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._token()}")
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
        return json.loads(body) if body else {}

    # ------------------------------------------------------------ files
    def find(self, name):
        """Return the file id of `name` inside the target folder, or None."""
        if name in self._ids:
            return self._ids[name]
        q = urllib.parse.quote(
            f"name = '{name}' and '{self.folder_id}' in parents and trashed = false")
        res = self._request("GET", f"{self.api_base}/drive/v3/files?q={q}&fields=files(id,name)")
        files = res.get("files", [])
        if files:
            self._ids[name] = files[0]["id"]
            return files[0]["id"]
        return None

    def upsert(self, name, content, mime="application/json"):
        """Create or update `name` in the folder with `content` (bytes)."""
        fid = self.find(name)
        if fid:
            url = f"{self.api_base}/upload/drive/v3/files/{fid}?uploadType=media"
            self._request("PATCH", url, data=content, headers={"Content-Type": mime})
            return fid
        boundary = "englishLearningAppBoundary"
        meta = json.dumps({"name": name, "parents": [self.folder_id]})
        body = ((f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                 f"{meta}\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode()
                + content + f"\r\n--{boundary}--".encode())
        url = f"{self.api_base}/upload/drive/v3/files?uploadType=multipart"
        res = self._request("POST", url, data=body,
                            headers={"Content-Type": f"multipart/related; boundary={boundary}"})
        if res.get("id"):
            self._ids[name] = res["id"]
        return res.get("id")

    def download(self, name):
        """Return bytes of `name` from the folder, or None if absent."""
        fid = self.find(name)
        if not fid:
            return None
        req = urllib.request.Request(f"{self.api_base}/drive/v3/files/{fid}?alt=media")
        req.add_header("Authorization", f"Bearer {self._token()}")
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read()
