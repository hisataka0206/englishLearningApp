"""L3: HTTP API 契約のテスト（test-spec.md §4）。

実際の Handler を一時データディレクトリで起動し、HTTPで叩いて契約を検証する。
Ollama / Azure / Notion / Drive を使う経路は対象外。
"""
import json
import os
import re
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "apps", "local")
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import harness as H  # noqa: E402

TMP = tempfile.mkdtemp(prefix="elapp_api_")
BASE = None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def start_server():
    """実サーバーを一時領域で起動する（★実データには触らない）。"""
    global BASE
    import server
    from http.server import ThreadingHTTPServer

    server.CFG.setdefault("storage", {})
    server.CFG["storage"]["data_dir"] = TMP
    server.CFG["storage"]["backend"] = "local"

    # ★ do_GET /api/health は `global CFG; CFG = load_config()` で設定を再読込する。
    #   これを塞がないと、health を叩いた瞬間に隔離が外れて実データを書き換えてしまう。
    server.load_config = lambda: server.CFG
    server.make_drive = lambda: None
    server.make_notion = lambda: None
    server.make_azure = lambda: None
    server.DRIVE = None
    server.NOTION = None
    server.AZURE = None

    real = os.path.join(APP, "data")
    assert server.resolve_data_dir() == TMP, "データ領域の隔離に失敗"
    assert not os.path.abspath(server.resolve_data_dir()).startswith(
        os.path.abspath(real)), "実データ領域を指している"

    port = free_port()
    BASE = f"http://127.0.0.1:{port}"
    srv = ThreadingHTTPServer(("127.0.0.1", port), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def req(method, path, body=None, raw=None):
    """(status, parsed_json_or_text) を返す。"""
    url = BASE + path
    data = raw if raw is not None else (
        json.dumps(body).encode() if body is not None else None)
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as res:
            txt = res.read().decode("utf-8", "replace")
            code = res.status
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        code = e.code
    try:
        return code, json.loads(txt)
    except json.JSONDecodeError:
        return code, txt


def main():
    srv = start_server()
    H.layer("L3")

    # ---------- 共通エンベロープ ----------
    H.group("4. API契約")
    code, body = req("GET", "/api/health")
    import server as _srv
    H.check("A-00", "★health のconfig再読込後もデータ領域が隔離されている（実データ保護）",
            _srv.resolve_data_dir(), TMP)
    H.check("A-01a", "成功時のエンベロープが {ok:true, data:{...}}",
            isinstance(body, dict) and body.get("ok") is True
            and isinstance(body.get("data"), dict), True)
    H.check("A-02", "health が仕様書 §6 のキーを揃えて返す",
            [k for k in ("version", "models", "fail_labels", "article_fail_labels",
                         "default_model", "drive_ready", "notion_ready", "azure_ready")
             if k not in body.get("data", {})], [])
    import server as _s2
    H.check("A-02b", "health の version が APP_VERSION と一致",
            body["data"]["version"], _s2.APP_VERSION)

    # ---------- 文の保存・取得 ----------
    code, body = req("POST", "/api/sentences",
                     {"japanese": "テスト", "english": "Test sentence",
                      "marked": "Test / sentence", "lang": "en"})
    sid = body.get("data", {}).get("id")
    H.check("A-03a", "POST /api/sentences が {id} を返す", bool(sid), True)
    H.check("A-03b", "IDが32桁のhex（§10）",
            bool(sid and re.fullmatch(r"[0-9a-f]{32}", sid)), True)

    code, body = req("POST", "/api/sentences",
                     {"japanese": "テスト2", "english": "Updated", "marked": "Updated",
                      "lang": "en", "id": sid})
    H.check("A-04a", "id 付きPOSTは {id, updated:true} を返す",
            body.get("data", {}).get("updated"), True)

    code, body = req("GET", "/api/sentences?lang=en")
    rows = body.get("data", [])
    H.check("A-04b", "上書きなので件数が増えていない（新規作成されない）", len(rows), 1)
    H.check("A-04c", "上書き後の内容が反映されている",
            rows[0].get("english"), "Updated")

    req("POST", "/api/sentences",
        {"japanese": "中国語テスト", "english": "你好", "marked": "你好", "lang": "zh"})
    _, zbody = req("GET", "/api/sentences?lang=zh")
    _, ebody = req("GET", "/api/sentences?lang=en")
    H.check("A-05a", "zh の文が zh 側から取得できる",
            [r["english"] for r in zbody.get("data", [])], ["你好"])
    H.check("A-05b", "zh の文が en 側に混ざらない（§7 #33 言語別ファイル分割）",
            any(r["english"] == "你好" for r in ebody.get("data", [])), False)
    H.check("A-05c", "zh の文には拼音が付く",
            bool(zbody["data"][0].get("pinyin")), True)

    # ---------- 単語 ----------
    code, body = req("POST", "/api/words",
                     {"word": "apple", "meaning": "りんご", "example": "I ate an apple.",
                      "source_id": sid, "lang": "en"})
    wid = body.get("data", {}).get("id")
    H.check("A-06a", "POST /api/words が {id} を返す", bool(wid), True)
    _, body = req("GET", "/api/words?lang=en")
    H.check("A-06b", "保存した単語が取得できる",
            [w["word"] for w in body.get("data", [])], ["apple"])
    H.check("A-06c", "単語レコードが §10 のフィールドを持つ",
            [k for k in ("id", "word", "meaning", "example", "created")
             if k not in body["data"][0]], [])

    # ---------- 実施記録 ----------
    _, body = req("POST", "/api/practice", {"id": sid})
    d = body.get("data", {})
    H.check("A-07a", "practice が {practice_count, last_practiced} を返す",
            sorted(d.keys()), ["last_practiced", "practice_count"])
    H.check("A-07b", "1回目の実施回数は1", d.get("practice_count"), 1)
    _, body = req("POST", "/api/practice", {"id": sid})
    H.check("A-07c", "2回目で回数が増える",
            body["data"]["practice_count"], 2)

    # ---------- 削除 ----------
    # ---------- 保存レコードの構造（§10）※削除する前に確認する ----------
    raw = json.load(open(os.path.join(TMP, "sentences.json"), encoding="utf-8"))
    rec = raw[0] if raw else {}
    H.check("A-15", "sentence レコードが §10 のフィールドを持つ",
            [k for k in ("id", "japanese", "english", "marked", "memo",
                         "created", "fails") if k not in rec], [])
    H.check("A-14", "created が %Y-%m-%d %H:%M:%S（タイムゾーンなし）",
            bool(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}",
                              rec.get("created", ""))), True)

    _, body = req("POST", "/api/words/delete", {"id": wid})
    H.check("A-08a", "単語削除が {deleted: 削除したID} を返す",
            body["data"].get("deleted"), wid)
    _, body = req("GET", "/api/words?lang=en")
    H.check("A-08b", "削除した単語が一覧から消える", body["data"], [])

    _, body = req("POST", "/api/delete", {"id": sid})
    H.check("A-08c", "文の削除が {deleted: 削除したID} を返す",
            body["data"].get("deleted"), sid)
    _, body = req("GET", "/api/sentences?lang=en")
    H.check("A-08d", "削除した文が一覧から消える", body["data"], [])

    # ---------- 拼音 ----------
    _, body = req("POST", "/api/pinyin", {"texts": ["我很好"]})
    d = body.get("data", {})
    H.check("A-09a", "pinyin が3キー {pinyins, pairs, words} を返す",
            sorted(d.keys()), ["pairs", "pinyins", "words"])
    H.check("A-09b", "pairs は [文字, 拼音] の列", len(d["pairs"][0]), 3)
    H.check("A-09c", "words は jieba の分かち書き（連結すると原文）",
            "".join(d["words"][0]), "我很好")

    # ---------- 発音評価の記録 ----------
    _, body = req("GET", "/api/assessments?lang=zh&mode=weak")
    H.check("A-11", "assessments?mode=weak が配列を返す",
            isinstance(body.get("data"), list), True)
    # ★ /api/assess の前方一致に飲み込まれていた不具合の回帰テスト
    code, body = req("POST", "/api/assessments/clear", {"lang": "zh"})
    H.check("A-10a", "assessments/clear が /api/assess に飲み込まれない（回帰）", code, 200)
    H.check("A-10b", "assessments/clear が {deleted} を返す",
            "deleted" in body.get("data", {}), True)

    # ---------- エラー処理 ----------
    code, body = req("GET", "/api/no_such_endpoint")
    H.check("A-12", "未知のパスは404", code, 404)

    code, body = req("POST", "/api/sentences", raw=b"{not valid json")
    H.check("A-13a", "不正JSONでもプロセスが落ちない（応答が返る）", code is not None, True)
    H.check("A-13b", "不正JSONの応答が {ok:false, error:...}",
            isinstance(body, dict) and body.get("ok") is False
            and "error" in body, True)

    code, body = req("GET", "/api/health")
    H.check("A-13c", "不正リクエストの後もサーバーが健全", body.get("ok"), True)

    code, body = req("POST", "/api/practice", {"id": "nonexistent"})
    H.check("A-01b", "失敗時のエンベロープが {ok:false, error:...}",
            isinstance(body, dict) and body.get("ok") is False
            and isinstance(body.get("error"), str), True)

    # ---------- 実データが汚れていないことの最終確認 ----------
    real = os.path.join(APP, "data", "sentences.json")
    if os.path.exists(real):
        txt = open(real, encoding="utf-8").read()
        H.check("A-99", "★実データにテストレコードが混入していない",
                [s for s in ("Test sentence", "Updated", "中国語テスト") if s in txt],
                [])

    srv.shutdown()
    return H.RESULTS


if __name__ == "__main__":
    main()
    ok = H.summary("L3: HTTP API 契約")
    sys.exit(0 if ok else 1)
