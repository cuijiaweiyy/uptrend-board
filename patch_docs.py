# -*- coding: utf-8 -*-
"""从 GitHub 拉取最新 docs/index.html，打上样式补丁后推回。

用于只需改动页面（不动数据）的小调整，避免重跑 10 分钟的抓取流水线。
补丁内容需与 build_html.py 中的 CSS 保持一致。
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error

OWNER, REPO, BRANCH = "cuijiaweiyy", "uptrend-board", "main"
TOKEN = os.environ.get("GH_TOKEN", "").strip()
API = "https://api.github.com"
HERE = os.path.dirname(os.path.abspath(__file__))

OLD_DESKTOP = ".diffcard .drank { font-size:10px; color:#cbd5e1; min-width:18px; text-align:right; }"
NEW_DESKTOP = (
    "/* 序号：定宽右对齐，避免位数不同（1位/3位）导致名称起始位置参差 */\n"
    "  .diffcard .drank { flex:0 0 auto; width:20px; min-width:20px; font-size:10px;\n"
    "                    color:#b0b8c4; text-align:right; font-variant-numeric:tabular-nums; }"
)
OLD_MOBILE = ".diffcard .drank { display:none; }"
NEW_MOBILE = (
    "/* 移动端也保留序号，但压到最窄，尽量不占名称空间 */\n"
    "    .diffcard .drank { width:15px; min-width:15px; font-size:9px; color:#b8c0cb; }"
)


def req(method, path, payload=None):
    headers = {"Authorization": "token " + TOKEN,
               "Accept": "application/vnd.github+json", "User-Agent": "uptrend-patch"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    if data:
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def download(rel):
    """大文件用 curl 拉（urllib 在代理环境下易 IncompleteRead）。"""
    meta = req("GET", "/repos/%s/%s/contents/%s" % (OWNER, REPO, rel))
    url = "%s/repos/%s/%s/git/blobs/%s" % (API, OWNER, REPO, meta["sha"])
    for attempt in range(3):
        r = subprocess.run(
            ["curl", "-sS", "-m", "180", "--compressed",
             "-H", "Authorization: token " + TOKEN,
             "-H", "Accept: application/vnd.github+json", url],
            capture_output=True)
        try:
            d = json.loads(r.stdout.decode("utf-8", "ignore"))
            return base64.b64decode(d["content"]).decode("utf-8")
        except Exception as e:  # noqa: BLE001
            print("  下载重试 %d: %s" % (attempt + 1, e))
    raise RuntimeError("下载 %s 失败" % rel)


def push(files, message):
    base = req("GET", "/repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH))["object"]["sha"]
    tree = req("GET", "/repos/%s/%s/git/commits/%s" % (OWNER, REPO, base))["tree"]["sha"]
    items = []
    for rel, content in files.items():
        b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")
        items.append({"path": rel, "mode": "100644", "type": "blob",
                      "sha": req("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO),
                                 {"content": b64, "encoding": "base64"})["sha"]})
    nt = req("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO),
             {"base_tree": tree, "tree": items})["sha"]
    nc = req("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO),
             {"message": message, "tree": nt, "parents": [base]})["sha"]
    req("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH), {"sha": nc})
    return nc


def main():
    if not TOKEN:
        print("需要 GH_TOKEN")
        return 2
    html = download("docs/index.html")
    print("线上页面 %.0f KB" % (len(html.encode("utf-8")) / 1024))
    n1, n2 = html.count(OLD_DESKTOP), html.count(OLD_MOBILE)
    if n1 != 1 or n2 != 1:
        print("补丁锚点不匹配: desktop=%d mobile=%d（可能已打过）" % (n1, n2))
        if n1 == 0 and n2 == 0:
            print("跳过")
            return 0
        return 1
    html = html.replace(OLD_DESKTOP, NEW_DESKTOP).replace(OLD_MOBILE, NEW_MOBILE)
    sha = push({"docs/index.html": html}, "feat: 股票序号在移动端也显示（小号定宽，不影响布局）")
    print("已推送", sha[:10], " 新大小 %.0f KB" % (len(html.encode("utf-8")) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
