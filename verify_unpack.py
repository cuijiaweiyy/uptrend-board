# -*- coding: utf-8 -*-
"""校验 docs/index.html 的 DATA 字典化解包是否正确。"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
H = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "docs", "index.html")
NODE = r"C:\Users\mayn\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"

html = open(H, encoding="utf-8").read()
i = html.find("var DATA = ")
j = html.find("/* 数据字典还原", i)
if i < 0 or j < 0:
    print("FAIL: 未找到 DATA 或解包脚本")
    sys.exit(1)
body = html[i:j]
# 取到解包 IIFE 结束（靠 "})();" 后的换行）
k = html.find("})();", j)
body += html[j:k + len("})();")]

CHECK = r"""
var b = DATA.boards.concept[0];
var s = b.stocks[0];
console.log("board:", b.name || b.board || b.title);
console.log("code/name:", s.code, s.name);
console.log("concepts:", JSON.stringify(s.concepts));
console.log("industry:", s.industry);
console.log("leftover c/i:", ("c" in s), ("i" in s));
var dn = (DATA.diff || {}).new || [];
console.log("diff.new n=", dn.length, "sample:", dn.length ? JSON.stringify(dn[0].concepts) : "n/a");
var miss = 0, tot = 0, nocon = 0;
["industry_l1", "industry_l2", "industry_l3", "concept"].forEach(function (k) {
  (DATA.boards[k] || []).forEach(function (bd) {
    (bd.stocks || []).forEach(function (st) {
      tot++;
      if (!Array.isArray(st.concepts)) miss++;
      else if (st.concepts.length && typeof st.concepts[0] !== "string") miss++;
      else if (!st.concepts.length) nocon++;
    });
  });
});
console.log("stocks=", tot, "bad=", miss, "empty-concepts=", nocon);
if (miss > 0) { console.log("FAIL"); process.exit(1); }
console.log("OK");
"""

tmp = os.path.join(HERE, "_verify.js")
open(tmp, "w", encoding="utf-8").write(body + CHECK)
r = subprocess.run([NODE, tmp], capture_output=True, text=True)
print(r.stdout)
if r.stderr:
    print("STDERR:", r.stderr[:800])
os.path.exists(tmp) and os.remove(tmp)
sys.exit(r.returncode)
