"""L1: サーバー内部ロジックのテスト（test-spec.md §2）。

server.py を一時データディレクトリで import し、純粋関数を直接検証する。
Ollama / Azure / Notion / Drive には一切アクセスしない。
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "apps", "local")
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

# 実データを触らないよう、config を一時ディレクトリに向ける
TMP = tempfile.mkdtemp(prefix="elapp_test_")
os.environ["ELAPP_DATA_DIR"] = TMP

import harness as H  # noqa: E402


def _isolate(server):
    """server のデータ領域をテンポラリに差し替える（★実データを絶対に触らない）。"""
    server.CFG.setdefault("storage", {})
    server.CFG["storage"]["data_dir"] = TMP
    server.CFG["storage"]["backend"] = "local"
    server.DRIVE = None            # Driveへのpushを無効化
    server.NOTION = None
    server.AZURE = None
    assert server.resolve_data_dir() == TMP, "データ領域の隔離に失敗"
    for name in server.DATA_FILES:
        if name.endswith(".json"):
            with open(os.path.join(TMP, name), "w") as f:
                json.dump([], f)


def main():
    import server
    _isolate(server)
    from error_kind import classify, KIND_LABEL

    H.layer("L1")

    # ---------- 2.1 バージョンと定数 ----------
    H.group("2.1 バージョンと定数")
    # 版数はテストに直書きせず、仕様書から読み取って突き合わせる
    # （どちらか片方だけ更新されたら必ず落ちるようにするため）
    spec_path = os.path.join(os.path.dirname(HERE), "docs", "10-specs",
                             "current-app-spec.md")
    import re
    m = re.search(r"現行バージョン: v([\d.]+)",
                  open(spec_path, encoding="utf-8").read())
    H.check("S-01", "APP_VERSION が仕様書の記載バージョンと一致",
            server.APP_VERSION, m.group(1) if m else "<仕様書に記載なし>")
    H.check("S-02a", "Drive push 対象は10ファイル",
            len(server.DATA_FILES), 10)
    H.check("S-02b", "push 対象に assessments.json を含む",
            "assessments.json" in server.DATA_FILES, True)

    pull = server.SENT_FILES + server.WORD_FILES + ["articles_zh.json"]
    H.check("S-03a", "Drive pull 対象は5ファイル", len(pull), 5)
    H.check("S-03b", "pull 対象に assessments.json を含まない（§11.3の不具合が現存）",
            "assessments.json" in pull, False)

    H.check("S-04a", "記事Failラベルの code 集合が {F,R,V,T,N}",
            sorted(x["code"] for x in server.ARTICLE_FAIL_LABELS),
            ["F", "N", "R", "T", "V"])
    H.check("S-04b", "各ラベルが code と name を持つ",
            all("code" in x and "name" in x for x in server.ARTICLE_FAIL_LABELS), True)

    H.check("S-05", "言語別ファイル名の決定",
            [server.sname("en"), server.sname("zh"),
             server.wname("en"), server.wname("zh")],
            ["sentences.json", "sentences_zh.json", "words.json", "words_zh.json"])

    # ---------- 2.2 word/meaning 入替補正 ----------
    H.group("2.2 word/meaning 入替補正")

    def fix(lang, w, m):
        """server.extract_keywords 内の補正ロジックと同一の判定を再現する。"""
        bad = server._has_kana if lang == "zh" else server._has_japanese
        if bad(w) and not bad(m):
            w, m = m, w
        if bad(w) or not w:
            return None          # 除外
        return [w, m]

    cases = [
        ("S-10", "en", "apple", "りんご", ["apple", "りんご"], "正常はそのまま"),
        ("S-11", "en", "りんご", "apple", ["apple", "りんご"], "en: wordが日本語なら入替"),
        ("S-12", "zh", "苹果", "りんご", ["苹果", "りんご"], "zh: 漢字は正常"),
        ("S-13", "zh", "りんご", "苹果", ["苹果", "りんご"], "zh: かなは誤り→入替"),
        ("S-14", "en", "りんご", "ぶどう", None, "入替しても不正なら除外"),
        ("S-15", "zh", "カタカナ", "苹果", ["苹果", "カタカナ"], "カタカナも かな 扱い"),
    ]
    for tid, lang, w, m, exp, desc in cases:
        H.check(tid, f"{desc}（{lang}: {w}/{m}）", fix(lang, w, m), exp)

    # ---------- 2.3 判定関数の単体 ----------
    H.group("2.3 日本語判定")
    H.check("S-20", "_has_japanese（ひらがな/カタカナ/漢字/英語）",
            [server._has_japanese(x) for x in ("りんご", "リンゴ", "苹果", "apple")],
            [True, True, True, False])
    H.check("S-21", "_has_kana は漢字を False にする（zhで漢字を弾かないため）",
            [server._has_kana(x) for x in ("りんご", "リンゴ", "苹果", "apple")],
            [True, True, False, False])

    # ---------- 2.4 拼音・分かち書き ----------
    H.group("2.4 拼音・分かち書き")
    py = server.to_pinyin("到")
    H.check("S-30a", "to_pinyin が声調記号つき（TONEスタイル）",
            "dào" in py, True)
    H.check("S-30b", "数字表記（dao4）ではない", any(c.isdigit() for c in py), False)

    pairs = server.to_pinyin_pairs("我很好")
    H.check("S-31a", "to_pinyin_pairs の要素数", len(pairs), 3)
    H.check("S-31b", "各要素が [文字, 拼音] の2要素",
            all(len(p) == 2 and p[0] and p[1] for p in pairs), True)

    pairs2 = server.to_pinyin_pairs("我好。")
    punct = [p for p in pairs2 if p[0] == "。"]
    H.check("S-32", "句読点の要素は拼音が空（整列に使わないため）",
            bool(punct) and not punct[0][1], True)

    seg = server.segment_zh("这是一个测试句子")
    H.check("S-33a", "segment_zh が2要素以上に分割", len(seg) >= 2, True)
    H.check("S-33b", "分割結果を連結すると原文に戻る",
            "".join(seg), "这是一个测试句子")

    H.check("S-34", "count_hanzi は漢字のみ数える",
            server.count_hanzi("我好，abc123。"), 2)

    # ---------- 2.5 誤り分類 ----------
    H.group("2.5 誤り分類 R/V/T/N")

    def kind_of(expected, heard):
        r = classify(expected, heard)
        return sorted({v["kind"] for v in r.values()}) or None

    H.check("S-40", "声調のみ違う → T（想 xiang3 → xiang1）",
            kind_of("我想去", "我香去"), ["T"])
    H.check("S-41", "そり舌の取り違え → R（资 zi1 → zhi1）",
            kind_of("资金", "知金"), ["R"])
    H.check("S-42", "韻母の違い → V（生 sheng1 → shen1）",
            kind_of("生活", "深活"), ["V"])
    H.check("S-43", "数字2の読み分け → N（两 → 二）",
            kind_of("两个", "二个"), ["N"])
    H.check("S-44", "一致していれば分類しない（誤検出しない）",
            kind_of("我很好", "我很好"), None)
    H.check("S-45", "KIND_LABEL に R/V/T/N/F すべて存在",
            sorted(KIND_LABEL.keys()), ["F", "N", "R", "T", "V"])

    # ---------- 2.6 苦手語の集計 ----------
    H.group("2.6 苦手語の集計 weak_words")
    import inspect
    sig = inspect.signature(server.weak_words)
    H.check("S-50", "集計期間の既定が30日",
            sig.parameters["days"].default, 30)

    def ts(days_ago):
        return (datetime.now() - timedelta(days=days_ago)).strftime("%Y-%m-%d %H:%M:%S")

    def word(w, score, err="Mispronunciation", ph=None, kind=None):
        d = {"w": w, "s": score, "e": err}
        if ph:
            d["wp"] = ph
            d["ws"] = 30
        if kind:
            d["k"] = kind
        return d

    server._save("assessments.json", [
        # 31日前 = 期間外
        {"lang": "zh", "time": ts(31), "words": [word("旧", 10)]},
        # 29日前 = 期間内
        {"lang": "zh", "time": ts(29), "words": [word("新", 10, ph="x", kind="T")]},
        # Omission は除外
        {"lang": "zh", "time": ts(1), "words": [word("欠", 0, err="Omission")]},
        # ミス率50%: 1回ミス+1回成功
        {"lang": "zh", "time": ts(2), "words": [word("半", 10, ph="y", kind="R")]},
        {"lang": "zh", "time": ts(1), "words": [word("半", 95, err="None")]},
        # 常に成功 = 出力されない
        {"lang": "zh", "time": ts(1), "words": [word("良", 98, err="None")]},
        # 別言語は混ざらない
        {"lang": "en", "time": ts(1), "words": [word("bad", 10)]},
    ])

    rows, _ = server.weak_words(lang="zh")
    byw = {r["word"]: r for r in rows}

    H.check("S-51a", "31日前の記録は集計対象外", "旧" in byw, False)
    H.check("S-51b", "29日前の記録は集計対象内", "新" in byw, True)
    H.check("S-52", "Omission（読まれなかった語）は除外", "欠" in byw, False)
    H.check("S-53", "2回中1回ミス → rate=50", byw.get("半", {}).get("rate"), 50)
    H.check("S-54", "ミスゼロの語は出力されない", "良" in byw, False)
    H.check("S-55", "zh は拼音ルビ pairs を持つ",
            all("pairs" in r for r in rows), True)
    H.check("S-56", "ミスの種類 kind.code が返る",
            byw.get("半", {}).get("kind", {}).get("code"), "R")
    H.check("S-57", "ミス数の降順に並ぶ",
            [r["miss"] for r in rows] == sorted((r["miss"] for r in rows), reverse=True),
            True)
    rows2, _ = server.weak_words(lang="zh", limit=1)
    H.check("S-58", "limit を超えない", len(rows2) <= 1, True)
    H.check("S-59", "言語が混ざらない（en の語が zh に出ない）", "bad" in byw, False)

    # ---------- 2.7 記事：Nomiss率 ----------
    H.group("2.7 記事 Nomiss率とセッション")

    def make_article(aid, total, nfails):
        return {
            "id": aid, "notion_page_id": "p" + aid, "title": "t", "date": "2026-07-01",
            "total_chars": total, "sentences": [], "vocab": [], "sessions": [],
            "fails": [{"idx": 1, "ci": i, "char": "字", "syllable": "zi4",
                       "label": "F", "time": "2026-07-01 00:00:00"}
                      for i in range(nfails)],
        }

    server._save("articles_zh.json", [
        make_article("a1", 100, 3), make_article("a2", 3, 1),
        make_article("a3", 0, 0), make_article("a4", 100, 0),
        make_article("a5", 100, 2),
    ])

    s1, _ = server.article_session("a1")
    H.check("S-60", "total=100 / miss=3 → 97.0（百分率・小数1桁）", s1["nomiss"], 97.0)
    s2, _ = server.article_session("a2")
    H.check("S-61", "total=3 / miss=1 → 66.7（小数1桁に丸め）", s2["nomiss"], 66.7)
    s3, _ = server.article_session("a3")
    H.check("S-62", "total_chars=0 は 1 として計算 → 100.0", s3["nomiss"], 100.0)
    s4, _ = server.article_session("a4")
    H.check("S-63", "ミスなし → 100.0", s4["nomiss"], 100.0)

    server.article_session("a5")
    s5b, _ = server.article_session("a5")
    H.check("S-64", "2回目は sessioned により二重計上されない", s5b["misses"], 0)
    H.check("S-65", "戻り値のキーが {date, misses, total, nomiss}",
            sorted(s1.keys()), ["date", "misses", "nomiss", "total"])

    _, err = server.article_session("nonexistent")
    H.check("S-66", "存在しない記事IDはエラーを返す", err, "article not found")

    # ---------- 2.8 既知の不具合が現存すること ----------
    H.group("2.8 既知の不具合（§11）")
    zres, _ = server.save_sentence("こんにちは", "你好", lang="zh")
    _, ferr = server.record_fail(zres["id"], "Fail")
    H.check("S-70", "§11.1: record_fail は中国語文を見つけられない（不具合が現存）",
            ferr, "sentence not found")

    eres, _ = server.save_sentence("hello", "Hello", lang="en")
    fres, _ = server.record_fail(eres["id"], "Fail")
    H.check("S-70b", "英語文へのfailは正常に記録される（対照）",
            fres.get("fail_count"), 1)

    return H.RESULTS


if __name__ == "__main__":
    main()
    ok = H.summary("L1: サーバー内部ロジック")
    sys.exit(0 if ok else 1)
