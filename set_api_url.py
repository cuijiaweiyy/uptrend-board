# -*- coding: utf-8 -*-
"""把 Worker 地址写入 docs/index.html（供实时拉取代码块使用）。

用法: python set_api_url.py https://uptrend-board-api.xxx.workers.dev
会同时改 build_html.py，保证下次 rebuild 仍带该地址。
"""
import re
import sys

URL = (sys.argv[1] if len(sys.argv) > 1 else "").strip().rstrip("/")
if not URL:
    print("用法: python set_api_url.py <worker 地址>")
    sys.exit(2)

SNIPPET = "<script>window.UPTREND_API='%s';</script>" % URL
ANCHOR = "/* ===== 实时数据：打开页面即拉当下最新名单 ===== */"


def patch(path):
    s = open(path, "r", encoding="utf-8").read()
    # 已有旧地址则先移除
    s2 = re.sub(r"<script>window\.UPTREND_API='[^']*';</script>\s*", "", s)
    if ANCHOR not in s2:
        print("  ! 未找到锚点，跳过:", path)
        return
    assert s2.count(ANCHOR) == 1, "锚点不唯一: " + path
    s2 = s2.replace(ANCHOR, SNIPPET + "\n" + ANCHOR)
    open(path, "w", encoding="utf-8").write(s2)
    print("  ✓ 已写入", path, "->", URL)


for p in ("docs/index.html", "build_html.py"):
    try:
        patch(p)
    except FileNotFoundError:
        print("  ! 文件不存在:", p)
