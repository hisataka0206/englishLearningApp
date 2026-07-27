#!/usr/bin/env python3
"""L1〜L3 をまとめて実行し、テスト結果報告書用のデータを出力する。

  python3 tests/run_all.py           # 実行して結果を表示
  python3 tests/run_all.py --json    # 機械可読な結果を stdout に出す
"""
import io
import json
import os
import subprocess
import sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

LAYERS = [
    ("L1", "サーバー内部ロジック", "test_l1_server.py"),
    ("L1", "算用数字の中国語読み", "test_l1_numbers.py"),
    ("L2", "クライアント分割ロジック", "test_l2_client.py"),
    ("L3", "HTTP API 契約", "test_l3_api.py"),
]


def run_layer(mod_name):
    """各層を別プロセスで実行し、結果を JSON で受け取る。"""
    script = f"""
import json, sys, io
from contextlib import redirect_stdout
sys.path.insert(0, {HERE!r})
import harness as H
buf = io.StringIO()
with redirect_stdout(buf):
    import {mod_name[:-3]} as m
    m.main()
print("@@RESULTS@@" + json.dumps(H.RESULTS, ensure_ascii=False))
"""
    p = subprocess.run([sys.executable, "-c", script],
                       capture_output=True, text=True, timeout=600)
    for line in p.stdout.splitlines():
        if line.startswith("@@RESULTS@@"):
            return json.loads(line[len("@@RESULTS@@"):]), None
    return [], (p.stderr or p.stdout)[-2000:]


def main():
    all_results = []
    errors = []
    for code, name, mod in LAYERS:
        res, err = run_layer(mod)
        if err:
            errors.append((code, err))
        all_results.extend(res)
        ng = [r for r in res if not r["ok"]]
        mark = "✅" if res and not ng and not err else "❌"
        print(f"{mark} {code} {name}: {len(res) - len(ng)}/{len(res)} 合格"
              + (f"  ★実行エラー" if err else ""))

    total = len(all_results)
    ng = [r for r in all_results if not r["ok"]]
    print("\n" + "=" * 72)
    print(f"合計: {total - len(ng)}/{total} 合格" + ("" if not ng else f"（不合格 {len(ng)}）"))
    print("=" * 72)
    for r in ng:
        print(f"\n[{r['id']}] {r['desc']}\n  期待: {r['expected']}\n  実際: {r['actual']}")
    for code, err in errors:
        print(f"\n★{code} 実行エラー:\n{err}")

    if "--json" in sys.argv:
        with open(os.path.join(HERE, "last_results.json"), "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n結果を tests/last_results.json に保存しました（{total}件）")

    return 0 if (not ng and not errors) else 1


if __name__ == "__main__":
    sys.exit(main())
