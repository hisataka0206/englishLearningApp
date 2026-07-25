"""発音ミスの種類を判定する（Notionの運用ルール R/V/T/N/F に対応）。

正解テキストと「実際に聞こえたテキスト」の拼音を音節単位で突き合わせ、
声母（子音）・韻母（母音）・声調のどこが違うかを判定する。

  F : 基本（分類できない/大きく違う）
  R : 声母・翘舌（zh/ch/sh/r ↔ z/c/s の取り違え含む）
  V : 韻母（母音・鼻音）
  T : 声調
  N : 数字2の読み分け（两 liǎng ↔ 二 èr）
"""

import difflib
import re

RETROFLEX = {"zh", "ch", "sh", "r"}
FLAT = {"z", "c", "s"}
KIND_LABEL = {
    "F": "発音", "R": "声母(子音)", "V": "韻母(母音)", "T": "声調", "N": "数字2",
}


def _split(py):
    """拼音(TONE3表記, 例 zhong3)を 声母/韻母/声調 に分解する。"""
    m = re.match(r"^([a-zü]+?)([1-5]?)$", py or "", re.I)
    if not m:
        return "", "", ""
    body, tone = m.group(1).lower(), m.group(2)
    for ini in ("zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k",
                "h", "j", "q", "x", "r", "z", "c", "s", "y", "w"):
        if body.startswith(ini):
            return ini, body[len(ini):], tone
    return "", body, tone


def _pinyin_list(text):
    """漢字テキスト → 音節ごとの (文字, 拼音TONE3) のリスト。"""
    try:
        from pypinyin import lazy_pinyin, Style
    except ImportError:
        return []
    chars = [c for c in text if "一" <= c <= "鿿"]
    if not chars:
        return []
    pys = lazy_pinyin("".join(chars), style=Style.TONE3, neutral_tone_with_five=True)
    return list(zip(chars, pys))


def classify(expected_text, heard_text):
    """正解と実際の発音を比べ、{文字index: {kind, label, expected, heard}} を返す。"""
    exp = _pinyin_list(expected_text)
    heard = _pinyin_list(heard_text)
    if not exp or not heard:
        return {}
    sm = difflib.SequenceMatcher(a=[p[1] for p in exp], b=[p[1] for p in heard])
    out = {}
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        if tag != "replace":
            continue  # 挿入/欠落は種類を断定しない
        for k in range(min(i2 - i1, j2 - j1)):
            ei, hj = i1 + k, j1 + k
            e_ch, e_py = exp[ei]
            h_ch, h_py = heard[hj]
            ei_i, ei_f, ei_t = _split(e_py)
            hi_i, hi_f, hi_t = _split(h_py)
            if {e_ch, h_ch} & {"两", "二"} and e_ch != h_ch:
                kind = "N"
            elif ei_i == hi_i and ei_f == hi_f and ei_t != hi_t:
                kind = "T"
            elif ei_i != hi_i and ei_f == hi_f:
                kind = "R"
            elif ei_i == hi_i and ei_f != hi_f:
                kind = "V"
            else:
                kind = "F"
            out[ei] = {"kind": kind, "label": KIND_LABEL[kind],
                       "expected": e_py, "heard": h_py, "heard_char": h_ch,
                       "retroflex": bool(kind == "R" and (
                           (ei_i in RETROFLEX and hi_i in FLAT)
                           or (ei_i in FLAT and hi_i in RETROFLEX)))}
    return out


def attach_to_words(words, expected_text, heard_text):
    """summarize()のwordsに、文字単位の判定結果を割り当てる。"""
    marks = classify(expected_text, heard_text)
    if not marks:
        return words
    idx = 0
    for w in words:
        n = sum(1 for ch in w.get("word", "") if "一" <= ch <= "鿿")
        found = [marks[i] for i in range(idx, idx + n) if i in marks]
        idx += n
        if found and w.get("error") != "Omission":
            w["kind"] = found[0]["kind"]
            w["kind_label"] = found[0]["label"]
            w["heard"] = found[0]["heard"]
            w["expected_py"] = found[0]["expected"]
    return words
