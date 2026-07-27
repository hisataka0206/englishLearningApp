"""L1: 算用数字の中国語読み と 多音字（`to_pinyin_pairs`）のテスト。

期待値は「記事29本の実データに出てくる287件のパターン」から作った。
数字を1桁ずつ読む実装は、年号・型番では正しいが数量・日付では誤りだったため、
その切り替えが正しく効いているかを見る。
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(os.path.dirname(HERE), "apps", "local")
sys.path.insert(0, APP)
sys.path.insert(0, HERE)

import harness as H  # noqa: E402


def main():
    import number_reading as nr
    H.layer("L1")

    # ---------- 整数（桁ごとの割り当て） ----------
    H.group("数詞：整数")
    cases = [
        ("N-01", "1", "yī", "一"),
        ("N-02", "15", "shí wǔ", "十五 ← 一十五 とは読まない"),
        ("N-03", "28", "èr shí bā", "二十八"),
        ("N-04", "30", "sān shí", "三十"),
        ("N-05", "99", "jiǔ shí jiǔ", "九十九"),
        ("N-06", "105", "yī bǎi líng wǔ", "一百零五 ← 零が入る"),
        ("N-07", "115", "yī bǎi yī shí wǔ", "一百一十五 ← 先頭でない一十は「一」を読む"),
        ("N-08", "250", "èr bǎi wǔ shí", "二百五十"),
        ("N-09", "2800", "èr qiān bā bǎi", "二千八百"),
        ("N-10", "5000", "wǔ qiān", "五千"),
        ("N-11", "10000", "yī wàn", "一万"),
        ("N-12", "15000", "yī wàn wǔ qiān", "一万五千"),
        ("N-13", "100000", "shí wàn", "十万"),
        ("N-14", "100500", "shí wàn líng wǔ bǎi", "十万零五百"),
        ("N-15", "0", "líng", "零"),
    ]
    for tid, digits, expect, note in cases:
        got = " ".join(x for x in nr.read_integer(digits) if x)
        H.check(tid, f"{digits} → {note}", got, expect)

    # ★ 桁ごとの割り当てが崩れていないこと（ci が保たれる前提）
    H.check("N-20", "read_integer の返り値の長さが桁数と一致",
            [len(nr.read_integer(d)) == len(d)
             for d in ("1", "15", "250", "10000", "100500")],
            [True] * 5)

    # ---------- 小数・パーセント ----------
    H.group("数詞：小数・パーセント")
    H.check("N-30", "1.5 → 一点五（小数部は1桁ずつ）",
            " ".join(x for x in nr.read_token("1.5") if x), "yī diǎn wǔ")
    H.check("N-31", "0.1525 → 零点一五二五",
            " ".join(x for x in nr.read_token("0.1525") if x),
            "líng diǎn yī wǔ èr wǔ")
    H.check("N-32", "27.5% → 百分之二十七点五（百分之は数の前）",
            " ".join(x for x in nr.read_token("27.5", percent=True) if x),
            "bǎi fēn zhī èr shí qī diǎn wǔ")
    H.check("N-33", "99.99% → 百分之九十九点九九",
            " ".join(x for x in nr.read_token("99.99", percent=True) if x),
            "bǎi fēn zhī jiǔ shí jiǔ diǎn jiǔ jiǔ")
    H.check("N-34", "30% → 百分之三十",
            " ".join(x for x in nr.read_token("30", percent=True) if x),
            "bǎi fēn zhī sān shí")

    # ---------- 文脈による切り替え ----------
    H.group("数詞：文脈の判定")

    def read(text):
        d = nr.annotate(text)
        return " ".join(d[i] for i in sorted(d) if d[i])

    ctx = [
        ("N-40", "2026年", "èr líng èr liù", "★年号は1桁ずつ"),
        ("N-41", "2027年", "èr líng èr qī", "年号"),
        ("N-42", "6月28日", "liù èr shí bā", "日付は数として読む"),
        ("N-43", "5月15日", "wǔ shí wǔ", "15日 → 十五日"),
        ("N-44", "250亿美元", "èr bǎi wǔ shí", "亿の前は数として"),
        ("N-45", "2800万台", "èr qiān bā bǎi", "万の前は数として"),
        ("N-46", "28台", "èr shí bā", "台（数量）"),
        ("N-47", "18个月", "shí bā", "个（数量）"),
        ("N-48", "（688160）", "liù bā bā yī liù líng", "★証券コードは1桁ずつ"),
        ("N-49", "GR00T", "líng líng", "★型番は1桁ずつ（直前がラテン文字）"),
        ("N-50", "G2", "èr", "型番（★文末。Pythonの '' in '%' が真になる罠）"),
        ("N-51", "在 2025 年", "èr líng èr wǔ", "年の前に空白があっても年号扱い"),
        ("N-52", "1.5万件", "yī diǎn wǔ", "小数＋万"),
        ("N-53", "高达99.99%。", "bǎi fēn zhī jiǔ shí jiǔ diǎn jiǔ jiǔ", "パーセント"),
    ]
    for tid, text, expect, note in ctx:
        H.check(tid, f"{text} … {note}", read(text), expect)

    # ---------- to_pinyin_pairs との統合 ----------
    H.group("数詞：pairs への統合（ci を壊さない）")
    import server
    tmp = tempfile.mkdtemp(prefix="numtest_")
    server.CFG.setdefault("storage", {})["data_dir"] = tmp
    server.CFG["storage"]["backend"] = "local"
    server.DRIVE = None

    samples = [
        "6月28日，智元机器人宣布第15000台正式下线。",
        "距离今年3月30日第10000台下线。",
        "成功率高达99.99%。",
        "2026年5月15日，超过250亿美元。",
    ]
    H.check("N-60", "★pairs の長さが原文の文字数と一致（ci が保たれる）",
            [len(server.to_pinyin_pairs(s)) == len(s) for s in samples],
            [True] * len(samples))

    got = " ".join(p[1] for p in server.to_pinyin_pairs(samples[0]) if p[1])
    H.check("N-61", "文全体：15000台 が 一万五千台 と読まれる",
            "yī wàn wǔ qiān tái" in got, True)
    H.check("N-62", "文全体：28日 が 二十八日 と読まれる",
            "èr shí bā rì" in got, True)

    # ---------- 多音字（語彙の文脈） ----------
    H.group("多音字：語彙の文脈が効いているか")

    def ruby(text):
        return " ".join(p[1] for p in server.to_pinyin_pairs(text) if p[1])

    poly = [
        ("P-01", "行业", "háng yè", "行＝háng（xíng ではない）"),
        ("P-02", "银行", "yín háng", "行＝háng"),
        ("P-03", "供应链", "gōng yìng liàn", "应＝yìng（実データ最多の誤り42件）"),
        ("P-04", "被视为人形机器人", "bèi shì wéi rén xíng jī qì rén", "为＝wéi（実データ40件）"),
        ("P-05", "重新", "chóng xīn", "重＝chóng"),
        ("P-06", "长期", "cháng qī", "长＝cháng"),
        ("P-07", "觉得", "jué de", "得＝de（軽声）"),
        ("P-08", "一个", "yí gè", "★変調：一＝yí"),
        ("P-09", "一百", "yì bǎi", "★変調：一＝yì"),
        ("P-10", "不是", "bú shì", "★変調：不＝bú"),
        ("P-11", "重要", "zhòng yào", "こちらは zhòng のまま（誤変換しない）"),
        ("P-12", "中国", "zhōng guó", "変えるべきでないものを変えない"),
    ]
    for tid, text, expect, note in poly:
        H.check(tid, f"{text} → {note}", ruby(text), expect)

    # 「视为」は pypinyin 標準では誤るが、補正辞書（pinyin_fixes.py）で直している
    H.check("P-13", "「视为」は単独でも正しい（補正辞書で解決済み）",
            [ruby("视为"), ruby("被视为人形")],
            ["shì wéi", "bèi shì wéi rén xíng"])

    # ---------- 補正辞書（pinyin_fixes.py） ----------
    H.group("多音字：補正辞書")
    import pinyin_fixes
    H.check("P-30", "補正辞書の各語で、字数と要素数が一致している",
            [w for w, r in pinyin_fixes.FIXES.items() if r and len(w) != len(r)], [])
    fixed = [
        ("P-31", "认为2026年", "rèn wéi èr líng èr liù nián", "为＝wéi（pypinyin標準で正しい）"),
        ("P-32", "列为核心", "liè wéi hé xīn", "★補正辞書。標準では wèi になる"),
        ("P-33", "华为主导", "huá wéi zhǔ dǎo", "★補正辞書。社名"),
        ("P-34", "身为工程师", "shēn wéi gōng chéng shī", "★補正辞書"),
        ("P-35", "因为车企", "yīn wèi chē qǐ", "因为は wèi のまま（壊していない）"),
        ("P-36", "为了把", "wèi le bǎ", "为了は wèi のまま"),
    ]
    for tid, text, expect, note in fixed:
        H.check(tid, f"{text} → {note}", ruby(text), expect)

    H.check("P-20", "数字と多音字が混ざっても長さが一致",
            len(server.to_pinyin_pairs("2026年，行业迈入15000台规模。")) == len("2026年，行业迈入15000台规模。"),
            True)

    # ---------- 実データ全件で落ちないこと ----------
    H.group("数詞：実データ全件")
    path = os.path.join(APP, "data", "articles_zh.json")
    if os.path.exists(path):
        arts = json.load(open(path, encoding="utf-8"))
        bad, n = [], 0
        for a in arts:
            for s in a.get("sentences", []):
                t = s.get("zh", "")
                if not t:
                    continue
                n += 1
                if len(server.to_pinyin_pairs(t)) != len(t):
                    bad.append(t[:20])
        H.check("N-70", f"記事{len(arts)}本・{n}句すべてで pairs の長さが原文と一致",
                bad, [])
    else:
        H.check("N-70", "実データが無いので省略", True, True)

    return H.RESULTS


if __name__ == "__main__":
    main()
    ok = H.summary("L1: 算用数字の中国語読み・多音字")
    sys.exit(0 if ok else 1)
