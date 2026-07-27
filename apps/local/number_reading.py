"""算用数字を中国語の数詞として読む。

なぜ必要か
----------
以前は数字を1桁ずつ読んでいた（15000 → yī wǔ líng líng líng）。
これは**年号や型番では正しいが、数量・日付では誤り**で、そのまま覚えると
誤った中国語になる。15000台 は 一万五千台（yī wàn wǔ qiān tái）。

設計の要点
----------
中国語の数詞は**位取り**なので、桁ごとに音節を割り当てられる。
    250  → 2:二百  5:五十  0:（なし）
    15   → 1:十    5:五
    105  → 1:一百  0:零    5:五
これにより `[文字, 拼音]` の **1対1の対応を保ったまま**正しく読める。
記事モードの1文字単位の失敗記録（`ci`＝文字index）がズレないため、
既存の失敗履歴に影響しない。

読み方の切り替え（記事29本・287件の実データから決めた）
----------
| 文脈 | 読み | 実データの件数 |
|---|---|---|
| 直後が「年」 | 1桁ずつ（2026 → èr líng èr liù） | 54 |
| 直後が「%」 | **百分之**を前に付けて数として読む | 29 |
| 直後が「）」で5桁以上（証券コード） | 1桁ずつ | 4 |
| 直前がラテン文字（GR00T, G2） | 1桁ずつ | 5 |
| それ以外（月日・台・万・亿・个…） | 数として読む | 195 |

小数は「整数部を数として読む → 点 → 小数部は1桁ずつ」。
    1.5万  → yī diǎn wǔ wàn
    99.99% → bǎi fēn zhī jiǔ shí jiǔ diǎn jiǔ jiǔ

記号（±・×・℃ など）
----------
数字に付く記号も中国語では読む。`SYMBOLS` を参照。
    ±0.1毫米 → zhèng fù líng diǎn yī háo mǐ
文脈で読みが変わる記号（× ~ など）は**数字に挟まれているときだけ**読む。
そうしないと「视觉-语言」のようなラテン文脈の記号まで読んでしまう。
"""

import re

# 数字そのものの読み
DIGIT = ["líng", "yī", "èr", "sān", "sì", "wǔ", "liù", "qī", "bā", "jiǔ"]
# 4桁ぶんの位（一・十・百・千）
UNIT4 = ["", "shí", "bǎi", "qiān"]
# 4桁ごとの大きな位（〜・万・亿・兆）
BIG = ["", "wàn", "yì", "zhào"]

PERCENT = "bǎi fēn zhī"
POINT = "diǎn"

NUM_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?")
LATIN = re.compile(r"[A-Za-z]")

# 記号の読み。near_digit=True は「数字に挟まれているときだけ読む」。
#   常に読む記号は、その字が出たら読みが一意に決まるものだけを入れる。
SYMBOLS = {
    "±": ("zhèng fù", False),      # 正负
    "℃": ("shè shì dù", False),    # 摄氏度
    "°": ("dù", False),            # 度
    "≈": ("yuē děng yú", False),   # 约等于
    "×": ("chéng", True),          # 乘（3×4）。品番の x とは別なので数字挟みに限る
    "~": ("dào", True),            # 到（10~20）
    "〜": ("dào", True),
    "～": ("dào", True),
}


def _digitwise(digits):
    """1桁ずつ読む（年号・型番・証券コード・小数部）"""
    return [DIGIT[int(c)] for c in digits]


def read_integer(digits):
    """整数を中国語の数詞として読み、**桁ごとの読み**の配列を返す。

    返り値の長さは digits の長さと一致する（読まない桁は空文字）。
        "250"   → ["èr bǎi", "wǔ shí", ""]
        "15"    → ["shí", "wǔ"]
        "15000" → ["yī wàn", "wǔ qiān", "", "", ""]
        "105"   → ["yī bǎi", "líng", "wǔ"]
    """
    digits = digits.lstrip("0") or "0"
    n = len(digits)
    if n == 1:
        return [DIGIT[int(digits)]]
    if n > 16:                       # 兆を超える桁は扱わない（1桁ずつに退避）
        return _digitwise(digits)

    out = [""] * n
    for i, ch in enumerate(digits):
        d = int(ch)
        if d == 0:
            continue
        pos = n - 1 - i              # 右から数えた位置
        unit = UNIT4[pos % 4]
        big = BIG[pos // 4]
        name = DIGIT[d]
        # 「一十」は先頭に来るとき 十 と読む（15 → 十五、115 → 一百一十五）
        if d == 1 and unit == "shí" and i == 0:
            name = ""
        out[i] = " ".join(x for x in (name, unit) if x)

    # 万・亿は、その4桁グループの**最後の非ゼロ桁**に付ける（十二万・一万）
    for g in range(1, (n + 3) // 4):
        lo, hi = n - 4 * (g + 1), n - 4 * g      # digits[lo:hi] がそのグループ
        lo = max(lo, 0)
        last = None
        for i in range(lo, hi):
            if digits[i] != "0":
                last = i
        if last is not None:
            out[last] = (out[last] + " " + BIG[g]).strip()

    # 零：非ゼロに挟まれた「ゼロの連なり」の先頭にだけ入れる（一百零五・十万零五百）
    i = 0
    while i < n:
        if digits[i] == "0":
            j = i
            while j < n and digits[j] == "0":
                j += 1
            before = any(c != "0" for c in digits[:i])
            after = any(c != "0" for c in digits[j:])
            if before and after:
                out[i] = "líng"
            i = j
        else:
            i += 1
    return out


def read_token(token, digitwise=False, percent=False):
    """数値トークン（"250" / "1.5" / "99.99"）→ 文字ごとの読みの配列。

    返り値の長さは token の長さと一致する（'.' も1要素）。
    """
    if "." in token:
        head, tail = token.split(".", 1)
        parts = (_digitwise(head) if digitwise else read_integer(head))
        parts = list(parts) + [POINT] + _digitwise(tail)
    else:
        parts = list(_digitwise(token) if digitwise else read_integer(token))

    if percent:
        # 中国語は「百分之」が数の**前**に来る。読み上げ順が正しくなるよう先頭に付ける
        for i, p in enumerate(parts):
            if p:
                parts[i] = f"{PERCENT} {p}"
                break
        else:
            parts[0] = PERCENT
    return parts


def annotate(text):
    """文中の算用数字に読みを付ける。

    返り値: {文字index: 読み}。読まない桁は空文字で入る。
    文字indexは元テキストの位置そのままなので、`ci`（1文字単位の失敗記録）に影響しない。
    """
    out = {}
    for m in NUM_RE.finditer(text):
        tok = m.group()
        start, end = m.start(), m.end()

        # 直後の文字（空白は読み飛ばす）
        k = end
        while k < len(text) and text[k] in " 　":
            k += 1
        nxt = text[k] if k < len(text) else ""
        prev = text[start - 1] if start > 0 else ""

        digits_only = tok.replace(".", "")
        # ★ Python では "" in "%％" が True になる。文末（nxt が空）で
        #   パーセント扱いされてしまうため、必ず空でないことを先に見る。
        percent = bool(nxt) and nxt in "%％"
        digitwise = (
            nxt == "年"                                              # 年号
            or (bool(nxt) and nxt in "）)" and len(digits_only) >= 5)  # 証券コード
            or bool(LATIN.match(prev))                               # 型番（GR00T, G2, HR2026）
        )

        parts = read_token(tok, digitwise=digitwise, percent=percent)
        for i, p in enumerate(parts):
            out[start + i] = p
        if percent:
            out[k] = ""            # 「%」自体は読まない（百分之を前に付けたため）

    # 記号（±・℃ など）。数字の読みとは独立に付ける
    for i, ch in enumerate(text):
        if ch not in SYMBOLS:
            continue
        reading, near_digit = SYMBOLS[ch]
        if near_digit and not _between_digits(text, i):
            continue
        out[i] = reading
    return out


def _between_digits(text, i):
    """記号 text[i] の前後が（空白を挟んで）数字かどうか。"""
    j = i - 1
    while j >= 0 and text[j] in " 　":
        j -= 1
    k = i + 1
    while k < len(text) and text[k] in " 　":
        k += 1
    return (j >= 0 and text[j].isdigit()
            and k < len(text) and text[k].isdigit())
