"""テスト用の最小ハーネス（外部依存なし）。"""
import sys
import traceback

RESULTS = []
_CUR = {"layer": "", "group": ""}


def layer(name):
    _CUR["layer"] = name


def group(name):
    _CUR["group"] = name


def check(tid, desc, actual, expected, cmp=None):
    """期待値と実際を比べて記録する。cmp を渡すと真偽判定に使う。"""
    try:
        ok = cmp(actual, expected) if cmp else (actual == expected)
    except Exception as e:
        ok = False
        actual = f"<例外: {e}>"
    RESULTS.append({"id": tid, "layer": _CUR["layer"], "group": _CUR["group"],
                    "desc": desc, "ok": bool(ok),
                    "expected": repr(expected), "actual": repr(actual)})
    return ok


def check_true(tid, desc, actual):
    return check(tid, desc, bool(actual), True)


def run(tid, desc, fn, expected, cmp=None):
    """例外を握って失敗として記録する。"""
    try:
        actual = fn()
    except Exception:
        RESULTS.append({"id": tid, "layer": _CUR["layer"], "group": _CUR["group"],
                        "desc": desc, "ok": False, "expected": repr(expected),
                        "actual": "<例外>\n" + traceback.format_exc(limit=3)})
        return False
    return check(tid, desc, actual, expected, cmp)


def summary(title="テスト結果"):
    total = len(RESULTS)
    ng = [r for r in RESULTS if not r["ok"]]
    print(f"\n{'=' * 72}\n{title}: {total - len(ng)}/{total} 合格")
    if ng:
        print(f"{'-' * 72}\n不合格 {len(ng)} 件:")
        for r in ng:
            print(f"\n  [{r['id']}] {r['desc']}")
            print(f"    期待: {r['expected']}")
            print(f"    実際: {r['actual']}")
    print("=" * 72)
    return len(ng) == 0


def exit_code():
    return 0 if all(r["ok"] for r in RESULTS) else 1
