# -*- coding: utf-8 -*-
"""通过 GitHub Git Data API 推送文件（git push 在本机被代理阻断时的替代通道）。

用法: python push_gh.py <相对路径> [...]
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

OWNER = "cuijiaweiyy"
REPO = "uptrend-board"
BRANCH = "main"
TOKEN = os.environ.get("GH_TOKEN", "").strip()
API = "https://api.github.com"


def req(method, path, payload=None, raw=False):
    data = None
    headers = {
        "Authorization": "token " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "uptrend-push",
    }
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    r = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=180) as resp:
            txt = resp.read().decode("utf-8", "ignore")
            return json.loads(txt) if not raw else txt
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        print("[ERR] %s %s -> %s\n%s" % (method, path, e.code, body[:600]))
        raise


def main(paths):
    if not TOKEN:
        print("需要 GH_TOKEN 环境变量")
        return 2
    ref = req("GET", "/repos/%s/%s/git/ref/heads/%s" % (OWNER, REPO, BRANCH))
    base_sha = ref["object"]["sha"]
    commit = req("GET", "/repos/%s/%s/git/commits/%s" % (OWNER, REPO, base_sha))
    base_tree = commit["tree"]["sha"]
    print("base tree:", base_tree[:10])

    tree = []
    for p in paths:
        if not os.path.exists(p):
            print("跳过（不存在）:", p)
            continue
        with open(p, "rb") as f:
            content = f.read()
        b64 = base64.b64encode(content).decode("ascii")
        rel = p.replace("\\", "/")
        blob = req("POST", "/repos/%s/%s/git/blobs" % (OWNER, REPO),
                   {"content": b64, "encoding": "base64"})
        tree.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        print("  blob %-40s %8.1f KB" % (rel, len(content) / 1024.0))

    if not tree:
        print("无文件可提交")
        return 1
    new_tree = req("POST", "/repos/%s/%s/git/trees" % (OWNER, REPO),
                   {"base_tree": base_tree, "tree": tree})
    msg = "feat: 双策略(上升途中/均线多头排列) + 今日变动子tab(新进入/退出)；Worker 输出合并 board"
    new_commit = req("POST", "/repos/%s/%s/git/commits" % (OWNER, REPO),
                     {"message": msg, "tree": new_tree["sha"], "parents": [base_sha]})
    req("PATCH", "/repos/%s/%s/git/refs/heads/%s" % (OWNER, REPO, BRANCH),
        {"sha": new_commit["sha"], "force": False})
    print("已推送 commit:", new_commit["sha"][:10])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
