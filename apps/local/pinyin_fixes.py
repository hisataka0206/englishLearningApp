"""pypinyin の読み間違いを補正する辞書。

漢字を「連なりごと」に渡すようにして多音字の大半は直ったが、
pypinyin の語彙辞書に無い語はまだ誤る。ここに1行足せば直る。

**使い方**
    誤りを見つけたら FIXES に1行足すだけ。形式は
        "語": [["1字目の読み"], ["2字目の読み"], ...]
    声調は TONE 表記（ā á ǎ à、軽声は記号なし）。字数と要素数を必ず合わせる。
    `python3 -m pinyin_fixes` で自己チェックできる。

**注意**
    ここに書くのは「その語なら常にこう読む」ものだけにする。
    文脈で変わる語（为了 wèi / 作为 wéi のように語ごとに決まるものは可）を
    無理に押し込むと、別の文脈を壊す。
"""

# 実データ（記事29本）で誤りを確認したもの
FIXES = {
    # 为：「〜とする / 〜とみなす」の意味は wéi。pypinyin が wèi を返す語
    "视为": [["shì"], ["wéi"]],      # 〜とみなす
    "列为": [["liè"], ["wéi"]],      # 〜に列せられる
    "身为": [["shēn"], ["wéi"]],     # 〜の身として
    "华为": [["huá"], ["wéi"]],      # ファーウェイ（社名）
    "designed_placeholder": None,    # ← 削除しないこと（下で除去する目印）
}
FIXES.pop("designed_placeholder", None)


def apply():
    """pypinyin に補正を読み込ませる。読み込めなくても本体は動かす。"""
    if not FIXES:
        return 0
    try:
        from pypinyin import load_phrases_dict
    except ImportError:
        return 0
    try:
        load_phrases_dict({k: v for k, v in FIXES.items() if v})
        return len(FIXES)
    except Exception as e:
        print(f"[pinyin_fixes] load failed: {e}")
        return 0


def self_check():
    """字数と要素数が合っているか、実際にその読みになるかを確認する。"""
    from pypinyin import pinyin, Style
    apply()
    ng = 0
    for word, reading in FIXES.items():
        if not reading:
            continue
        if len(word) != len(reading):
            print(f"  ✗ {word}: 字数{len(word)} ≠ 要素数{len(reading)}")
            ng += 1
            continue
        got = [x[0] for x in pinyin(word, style=Style.TONE)]
        want = [r[0] for r in reading]
        mark = "✓" if got == want else "✗"
        if got != want:
            ng += 1
        print(f"  {mark} {word}: {' '.join(got)}（期待 {' '.join(want)}）")
    print(f"\n{len(FIXES) - ng}/{len(FIXES)} OK")
    return ng == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_check() else 1)
