#!/usr/bin/env python3
"""Notionのインライン失敗コメントを記事データに取り込む汎用インポーター。

使い方: python3 tools_import_fails.py <page_id> <comments_xml_file>
 - comments_xml_file = notion-get-comments(include_all_blocks=true) の出力を保存したもの
Notion通常APIは音節アンカーを返さないため、get-comments(MCP)の出力を渡す設計。
冪等: 同じ記事のnotion由来fail/sessionを消してから再登録する。
"""
import json, re, sys, urllib.request

CFG = json.load(open("config.json"))
TOK = CFG["notion"]["token"]
DATA = "data/articles_zh.json"
LAB = {"t": "T", "f": "F", "v": "V", "r": "R", "n": "N",
       "s": "F", "w": "F", "c": "F", "a": "F"}
DIG = {"0": "líng", "1": "yī", "2": "èr", "3": "sān", "4": "sì",
       "5": "wǔ", "6": "liù", "7": "qī", "8": "bā", "9": "jiǔ"}


def rest(path):
    req = urllib.request.Request("https://api.notion.com/v1/" + path)
    req.add_header("Authorization", "Bearer " + TOK)
    req.add_header("Notion-Version", "2022-06-28")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def all_blocks(pid):
    out, cur = [], None
    while True:
        q = f"blocks/{pid}/children?page_size=100" + (f"&start_cursor={cur}" if cur else "")
        r = rest(q); out += r["results"]
        if not r.get("has_more"):
            break
        cur = r["next_cursor"]
    return out


def btext(b):
    t = b["type"]
    return "".join(x.get("plain_text", "") for x in b.get(t, {}).get("rich_text", []))


def pairs_of(zh):
    from pypinyin import pinyin, Style
    out = []
    for ch in zh:
        if "一" <= ch <= "鿿":
            p = pinyin(ch, style=Style.TONE, errors="default")
            out.append([ch, p[0][0] if p and p[0] else ""])
        elif ch in DIG:
            out.append([ch, DIG[ch]])
        else:
            out.append([ch, ""])
    return out


def parse_comments(xml):
    """[(block_id_nodash, syllable, label, datetime)] を返す。"""
    res = []
    for dm in re.finditer(r'<discussion\s+id="discussion://[^/]+/([0-9a-f-]+)/[^"]+"[^>]*?text-context="([^"]*)"[^>]*>(.*?)</discussion>', xml, re.S):
        block = dm.group(1).replace("-", "")[:8]  # 先頭8文字で照合
        syl = dm.group(2)
        cm = re.search(r'<comment[^>]*?datetime="([^"]*)"[^>]*>([^<]*)</comment>', dm.group(3))
        dt = cm.group(1) if cm else ""
        label = (cm.group(2).strip() if cm else "").lower()[:1] or "f"
        res.append((block, syl, label, dt))
    return res


def main():
    page = sys.argv[1].replace("-", "")
    xml = open(sys.argv[2], encoding="utf-8").read()
    comments = parse_comments(xml)
    if not comments:
        print(f"{page}: コメント0件（未学習と判断しスキップ）")
        return

    bs = all_blocks(page)
    b2s, b2p, pin_idx = {}, {}, 0
    for b in bs:
        t = btext(b)
        if t.startswith("拼音："):
            pin_idx += 1
            bid = b["id"].replace("-", "")[:8]  # 先頭8文字で照合
            b2s[bid] = pin_idx
            b2p[bid] = t[len("拼音："):]

    arts = json.load(open(DATA))
    art = next((a for a in arts if a["notion_page_id"] == page), None)
    if not art:
        print("記事がローカルに無い:", page); return
    # 冪等化：notion由来を除去
    art["fails"] = [f for f in art.get("fails", []) if not f.get("sessioned")]
    art["sessions"] = [x for x in art.get("sessions", []) if x.get("source") != "notion"]
    sent = {s["idx"]: s for s in art["sentences"]}

    # ブロックごとにまとめ、コメント日時（＝読み順）でソート
    byblock = {}
    for block, syl, label, dt in comments:
        byblock.setdefault(block, []).append((syl, label, dt))

    added, unmatched, skipped_vocab = 0, [], 0
    for block, fl in byblock.items():
        idx = b2s.get(block)
        if not idx:
            skipped_vocab += len(fl)  # 語彙表など拼音行以外は対象外
            continue
        zh = sent[idx]["zh"]; prs = pairs_of(zh)
        fl = [x for x in fl if x[1] != "a"]  # 「add」(単語追加)は発音ミスではないので除外
        fl_sorted = sorted(fl, key=lambda x: x[2])  # datetime昇順＝読み順
        pin_re = re.compile(r"[a-zāáǎàēéěèīíǐìōóǒòūúǔùüǘǚǜ]", re.I)

        import unicodedata
        def detone(s):
            return "".join(c for c in unicodedata.normalize("NFD", s)
                           if unicodedata.category(c) != "Mn")

        def find_ranges(target, is_pin, loose=False):
            """target(拼音連結 or 文字列)に一致する連続文字範囲[start,end)を全て返す。
            loose=Trueで声調を無視（多音字の声調差を救済）。"""
            tg = detone(target) if loose else target
            out = []
            for start in range(len(prs)):
                acc = ""; end = start
                while end < len(prs):
                    ch, py = prs[end]
                    unit = (py if is_pin else ch)
                    if is_pin and not py:
                        break
                    acc += (detone(unit) if loose else unit); end += 1
                    if acc == tg:
                        out.append((start, end)); break
                    if not tg.startswith(acc):
                        break
            return out

        used = set(); ptr = 0
        for syl, lab, dt in fl_sorted:
            target = re.sub(r"[ '’·\-–]", "", syl); is_pin = bool(pin_re.search(target))
            allr = find_ranges(target, is_pin)  # 文中の全候補
            if not allr and is_pin:
                allr = find_ranges(target, is_pin, loose=True)  # 声調無視で救済
            avail = [r for r in allr if not any(i in used for i in range(r[0], r[1]))]
            if len(allr) == 1:              # 文中で一意→順序に関わらず確定
                pick = allr[0]
            elif avail:                     # 複数出現→読み順ポインタで前方優先
                pick = next((r for r in avail if r[0] >= ptr), avail[0])
                ptr = pick[1]
            else:                           # 部分一致で1文字だけ救済
                pick = None
                for i in range(len(prs)):
                    if i in used:
                        continue
                    ch, py = prs[i]
                    if (is_pin and py and target.startswith(py)) or (not is_pin and ch and ch in target):
                        pick = (i, i + 1); break
            if not pick:
                unmatched.append((idx, syl)); continue
            for i in range(*pick):
                used.add(i)
                art["fails"].append({"idx": idx, "ci": i, "char": prs[i][0],
                                     "syllable": prs[i][1] or (target if pick[1] - pick[0] == 1 else ""),
                                     "label": LAB.get(lab, "F"),
                                     "time": (dt or "2026-07-16")[:10] + " 08:00:00",
                                     "pushed": True, "sessioned": True})
                added += 1

    total = art.get("total_chars", 0) or 1
    misses = len(art["fails"])
    art.setdefault("sessions", []).append({"date": "2026-07-16", "misses": misses,
                                           "total": total,
                                           "nomiss": round(100 * (total - misses) / total, 1),
                                           "source": "notion"})
    json.dump(arts, open(DATA, "w"), ensure_ascii=False, indent=2)
    print(f"{art['title'][:30]} | 拼音行:{pin_idx} コメント:{len(comments)} 追加fail:{added} "
          f"語彙除外:{skipped_vocab} 未マッチ:{len(unmatched)} Nomiss:{art['sessions'][-1]['nomiss']}%")
    if unmatched:
        print("  未マッチ:", unmatched)


if __name__ == "__main__":
    main()
