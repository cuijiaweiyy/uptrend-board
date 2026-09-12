#!/usr/bin/env bash
# 部署 Cloudflare Worker（需已通过 wrangler login 或设置 CLOUDFLARE_API_TOKEN）
# 用法: bash deploy.sh
set -e
cd "$(dirname "$0")/worker"

WRANGLER="C:/Users/mayn/.workbuddy/binaries/node/versions/22.22.2-2/node.exe C:/Users/mayn/.workbuddy/binaries/node/workspace/node_modules/wrangler/bin/wrangler.js"
export WRANGLER_SEND_METRICS=false

echo "==> 1/3 创建 KV 命名空间（存昨日快照，用于「今日新进入 / 退出」）"
KV_OUT=$($WRANGLER kv namespace create UPTREND_KV 2>&1 || true)
echo "$KV_OUT"
KV_ID=$(echo "$KV_OUT" | grep -oE 'id = "[0-9a-f]{32}"' | head -1 | grep -oE '[0-9a-f]{32}')

if [ -n "$KV_ID" ]; then
  echo "    KV id = $KV_ID"
  python - <<PY
import re, pathlib
p = pathlib.Path("wrangler.toml")
s = p.read_text(encoding="utf-8")
s = re.sub(r'#?\s*\[\[kv_namespaces\]\]\n#?\s*binding = "UPTREND_KV"\n#?\s*id = "[^"]*"',
           '[[kv_namespaces]]\nbinding = "UPTREND_KV"\nid = "$KV_ID"', s)
if '[[kv_namespaces]]' not in s or '$KV_ID' in s and 'binding' not in s:
    pass
p.write_text(s, encoding="utf-8")
print("    wrangler.toml 已写入 KV 绑定")
PY
else
  echo "    (未取到 KV id，跳过；日环比功能会显示「—」，不影响主功能)"
fi

echo "==> 2/3 部署"
$WRANGLER deploy 2>&1 | tail -20

echo "==> 3/3 完成"
