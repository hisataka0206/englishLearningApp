"""L2: クライアント分割ロジック・LABELS のテスト（test-spec.md §3）。

index.html から実物のJSを抽出し、Node で実行して検証する。
テスト側にロジックを写経しないことで、テストと実装の乖離を防ぐ。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import harness as H          # noqa: E402
import extract_js            # noqa: E402

SPEC = os.path.join(os.path.dirname(HERE), "docs", "10-specs", "current-app-spec.md")


# 抽出ブロックにはDOM依存の行（selectionchangeリスナー等）が混ざるため、
# 最小限のスタブを与える。分割ロジック自体はDOMに触れない。
DOM_STUB = """
globalThis.document = {
  addEventListener() {}, getElementById() { return { value: "", textContent: "",
    innerHTML: "", classList: { add() {}, remove() {}, toggle() {} }, style: {} }; },
  getSelection() { return { rangeCount: 0 }; },
};
globalThis.window = globalThis;
"""


def node_eval(prelude, script):
    """抽出したJSを読み込ませた上で script を実行し、JSON を受け取る。"""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as f:
        f.write(DOM_STUB + "\n" + prelude + "\n" + script)
        path = f.name
    try:
        p = subprocess.run(["node", path], capture_output=True, text=True, timeout=60)
        if p.returncode != 0:
            raise RuntimeError(p.stderr.strip()[:400])
        return json.loads(p.stdout)
    finally:
        os.unlink(path)


def main():
    H.layer("L2")
    logic = extract_js.split_logic()
    lbl = extract_js.labels()

    def sp(text, mode, lang="en", explicit=False, words_map=None):
        """splitPhrases を実物のまま呼ぶ。"""
        script = f"""
globalThis.__lang = {json.dumps(lang)};
globalThis.__mode = {json.dumps(mode)};
explicitBreaks = {json.dumps(explicit)};
zhWordsMap = {json.dumps(words_map or {})};
console.log(JSON.stringify(splitPhrases({json.dumps(text)}, {json.dumps(mode)})));
"""
        return node_eval(logic, script)

    # ---------- 3.1 英語の自動分割 ----------
    H.group("3.1 英語の自動分割")

    H.run("C-01", "sentence: ピリオドで文単位に分割",
          lambda: sp("I like it. You do too.", "sentence"),
          2, cmp=lambda a, e: len(a) == e)

    H.run("C-02", "normal: 句読点が無ければ分割しない（★語数閾値が存在しないことの証明）",
          lambda: sp("I go to school and I study English", "normal"),
          ["I go to school and I study English"])

    H.run("C-03", "fine: 接続詞 and の前で分割される",
          lambda: sp("I go to school and I study English", "fine"),
          True, cmp=lambda a, e: any(s.startswith("and") for s in a))

    H.run("C-04", "normal: カンマで分割",
          lambda: sp("I like apples, and I like grapes.", "normal"),
          2, cmp=lambda a, e: len(a) == e)

    H.run("C-05", "fine: 前置詞 to / with の前でも分割",
          lambda: sp("I want to go to the park with my friends", "fine"),
          True, cmp=lambda a, e: any(s.startswith("with") for s in a)
          and any(s.startswith("to") for s in a))

    # C-06: 仕様書に転記した正規表現が実物と一致するか
    actual_re = extract_js.eng_break_regex()
    spec_text = open(SPEC, encoding="utf-8").read()
    m = re.search(r"const ENG_BREAK = (/.*?/i);", spec_text)
    H.check("C-06", "仕様書 §3.2 に転記した ENG_BREAK が実物と一字一句一致",
            m.group(1) if m else "<仕様書に見つからない>", actual_re)

    H.run("C-07", "fine 後処理①: 1語だけの断片が前の節に結合される",
          lambda: sp("I go to the store", "fine"),
          True, cmp=lambda a, e: all(len(s.split()) >= 2 for s in a))

    H.run("C-08", "fine 後処理②: 先頭が1語だけなら次の節に結合される",
          lambda: sp("I to go", "fine"),
          True, cmp=lambda a, e: len(a[0].split()) >= 2 or len(a) == 1)

    H.run("C-09", "空文字でも例外を投げない",
          lambda: sp("", "fine"), list, cmp=lambda a, e: isinstance(a, e))

    # ---------- 3.2 中国語の自動分割 ----------
    H.group("3.2 中国語の自動分割")
    ZH = "我很好，你呢？我们去学校。"

    H.run("C-20", "sentence: 。！？ のみで分割（、では分割しない）",
          lambda: sp(ZH, "sentence", lang="zh"),
          True, cmp=lambda a, e: all("，" not in s[:-1] or True for s in a) and len(a) == 2)

    H.run("C-21", "normal: ，。！？、；： で分割",
          lambda: sp(ZH, "normal", lang="zh"),
          3, cmp=lambda a, e: len(a) == e)

    words = ["我", "很", "好", "，", "你", "呢", "？", "我们", "去", "学校", "。"]
    clean = ZH  # zhSplit は空白と区切り記号だけ除去するので、この入力では原文と同じ

    H.run("C-22", "fine: jieba単語列があれば単語レベルに分割（normalより細かい）",
          lambda: len(sp(ZH, "fine", lang="zh", words_map={clean: words})),
          len(sp(ZH, "normal", lang="zh")), cmp=lambda a, e: a > e)

    H.run("C-23", "fine: zhWordsMap が空なら normal と同じ結果（フォールバック）",
          lambda: sp(ZH, "fine", lang="zh", words_map={}),
          sp(ZH, "normal", lang="zh"))

    H.run("C-24", "fine: 句読点トークンが独立した節にならず直前の語に結合",
          lambda: sp(ZH, "fine", lang="zh", words_map={clean: words}),
          True, cmp=lambda a, e: not any(
              s in "，。！？、；：" for s in a))

    # ---------- 3.3 手動区切りと explicitBreaks ----------
    H.group("3.3 手動区切りと explicitBreaks")
    # 手動区切りは2箇所。かつ後半の節は fine の自動分割対象語（to）を含む。
    # → explicitBreaks の真偽で節数が変わることを対比で確認する。
    MANUAL = "I like apples / and I want to go to the park"

    H.run("C-30", "explicitBreaks=false: 手動区切りに加えて自動分割もかかる",
          lambda: len(sp(MANUAL, "fine", explicit=False)),
          2, cmp=lambda a, e: a > e)

    H.run("C-31", "explicitBreaks=true: 手動区切りのみ（自動分割を足さない）",
          lambda: sp(MANUAL, "fine", explicit=True),
          ["I like apples", "and I want to go to the park"])

    H.run("C-32", "区切り記号 / | ｜ ／ の4種すべてが機能する",
          lambda: [len(sp(f"aa {c} bb", "fine", explicit=True))
                   for c in ["/", "|", "｜", "／"]],
          [2, 2, 2, 2])

    # ---------- 3.4 LABELS ----------
    H.group("3.4 LABELS")
    labels = node_eval(lbl, "console.log(JSON.stringify({"
                            "en: Object.keys(LABELS.en), zh: Object.keys(LABELS.zh),"
                            "vEn: LABELS.en, vZh: LABELS.zh}, (k, v) =>"
                            " v instanceof RegExp ? v.toString() : v));")

    H.check("C-40", "en と zh のキー集合が完全に一致（言語追加時の漏れ防止）",
            sorted(labels["en"]), sorted(labels["zh"]))
    H.check("C-41", "transHead が仕様書 §9 と一致",
            [labels["vEn"]["transHead"], labels["vZh"]["transHead"]],
            ["英訳 ✏️", "中国語訳 ✏️"])
    H.check("C-42", "sentTab が仕様書 §9 と一致",
            [labels["vEn"]["sentTab"], labels["vZh"]["sentTab"]],
            ["英文のみ", "中国語のみ"])
    H.check("C-43", "ttsLang が仕様書 §9 と一致",
            [labels["vEn"]["ttsLang"], labels["vZh"]["ttsLang"]],
            ["en-US", "zh-CN"])
    H.check("C-44", "voiceRe が仕様書 §9 と一致",
            [labels["vEn"]["voiceRe"], labels["vZh"]["voiceRe"]],
            ["/Samantha/", "/Ting|Tingting|Meijia|Sinji/"])

    # 仕様書 §9 の表に載るキーがすべて実装に存在するか
    sec = spec_text[spec_text.index("## 9. UIラベル定義"):]
    sec = sec[:sec.index("\n## ")]
    spec_keys = set(re.findall(r"^\|\s*~?~?`(\w+)`~?~?\s*\|", sec, re.M))
    H.check("C-45", "仕様書 §9 の全キーが実装の LABELS に存在",
            sorted(spec_keys - set(labels["en"])), [])
    H.check("C-46", "実装の LABELS に仕様書 §9 未記載のキーが無い",
            sorted(set(labels["en"]) - spec_keys), [])

    return H.RESULTS


if __name__ == "__main__":
    main()
    ok = H.summary("L2: クライアント分割ロジック")
    sys.exit(0 if ok else 1)
