"""index.html から検証対象のJSを切り出して Node で実行できる形にする。

コピペではなく **実物から抜き出す** のが要点。仕様書とテストが実装から乖離しないようにする。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(os.path.dirname(HERE), "apps", "local", "index.html")


def source():
    return open(INDEX, encoding="utf-8").read()


def slice_between(src, start_marker, end_marker):
    """start_marker の行頭から end_marker の直前までを返す。"""
    i = src.index(start_marker)
    j = src.index(end_marker, i)
    return src[i:j]


def split_logic():
    """ENG_BREAK 〜 splitPhrases までのブロックを抜き出す。"""
    src = source()
    block = slice_between(src, "const ENG_BREAK", "function resetMainBreak")
    # splitPhrases は DOM とグローバル lang を参照するので、テスト用に置換する
    block = block.replace(
        'mode = mode || document.getElementById("splitMode").value;',
        'mode = mode || globalThis.__mode;')
    block = block.replace('lang === "zh"', 'globalThis.__lang === "zh"')
    return block


def labels():
    """LABELS 定義を抜き出す。"""
    src = source()
    return slice_between(src, "const LABELS = {", "\nfunction L(")


def eng_break_regex():
    """ENG_BREAK の正規表現リテラルをそのまま返す（仕様書との突合用）。"""
    m = re.search(r"const ENG_BREAK = (/.*/i);", source())
    return m.group(1)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "split"
    print({"split": split_logic, "labels": labels,
           "engbreak": eng_break_regex}[what]())
