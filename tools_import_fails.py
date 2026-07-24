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
    """[(block_id_nodash, syllable, label)] を返す。"""
    res = []
    for dm in re.finditer(r'<discussion\s+id="discussion://[^/]+/([0-9a-f-]+)/[^"]+"[^>]*?text-context="([^"]*)"[^>]*>(.*?)</discussion>', xml, re.S):
        block = dm.group(1).replace("-", "")
        syl = dm.group(2)
        cm = re.search(r"<comment[^>]*>([^<]*)</comment>", dm.group(3))
        label = (cm.group(1).strip() if cm else "").lower()[:1] or "f"
        res.append((block, syl, label))
    return res


def main():
    page = sys.argv[1].replace("-", "")
    xml = open(sys.argv[2], encoding="utf-8").read()
    comments = parse_comments(xml)

    bs = all_blocks(page)
    b2s, b2p, pin_idx = {}, {}, 0
    for b in bs:
        t = btext(b)
        if t.startswith("拼音："):
            pin_idx += 1
            bid = b["id"].replace("-", "")
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

    # ブロックごとにまとめる
    byblock = {}
    for block, syl, label in comments:
        byblock.setdefault(block, []).append((syl, label))

    added, unmatched, skipped_vocab = 0, [], 0
    for block, fl in byblock.items():
        idx = b2s.get(block)
        if not idx:
            skipped_vocab += len(fl)  # 語彙表など拼音行以外は対象外
            continue
        zh = sent[idx]["zh"]; prs = pairs_of(zh); pyt = b2p[block]
        fl_sorted = sorted(fl, key=lambda x: pyt.find(x[0]) if pyt.find(x[0]) >= 0 else 999)
        used = set()
        for syl, lab in fl_sorted:
            ci = None
            for i, (ch, py) in enumerate(prs):
                if i in used:
                    continue
                if (py and py == syl) or ch == syl:
                    ci = i; break
            if ci is None:
                for i, (ch, py) in enumerate(prs):
                    if i in used:
                        continue
                    if syl and syl in (py or ""):
                        ci = i; break
            if ci is None:
                unmatched.append((idx, syl)); continue
            used.add(ci)
            art["fails"].append({"idx": idx, "ci": ci, "char": prs[ci][0],
                                 "syllable": prs[ci][1] or syl, "label": LAB.get(lab, "F"),
                                 "time": "2026-07-16 08:00:00", "pushed": True, "sessioned": True})
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
