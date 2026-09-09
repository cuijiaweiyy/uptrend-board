"""把新版 K 线弹层（直连腾讯、无后端）精准替换进线上 docs/index.html，保留现有数据。

流程：
1) 从 kline_modal.py 取新版 KLINE_MODAL_HTML（以 <style> 开头、</script> 结尾的整块）
2) curl 下载线上 docs/index.html（绕开 urllib 在代理下的 IncompleteRead）
3) 用稳定锚点定位旧弹层块并替换：
   - 起点：modal 的 <style>，即 indexOf('弹层容器（移动端真全屏') 之前的最后一个 <style>
   - 终点：<script src="echarts.min.js"></script> 之前的最后一个 </script>
4) 严格校验：DATA / __cd / 数据时间 不变，新弹层含 txMinuteDirect，旧 /kline 后端消失
5) 写回 docs/index.html（不在此处推送，交给 push_gh.py）
"""
import os, re, subprocess, sys, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
OWNER, REPO = "cuijiaweiyy", "uptrend-board"
TOKEN = os.environ.get("GH_TOKEN", "")

def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

# 1) 新版弹层
spec = importlib.util.spec_from_file_location("km", os.path.join(HERE, "kline_modal.py"))
km = importlib.util.module_from_spec(spec); spec.loader.exec_module(km)
new_modal = km.KLINE_MODAL_HTML
assert new_modal.startswith("<style>") and new_modal.rstrip().endswith("</script>"), "modal 头尾异常"
assert "function txMinuteDirect" in new_modal, "新弹层缺少 txMinuteDirect"
print("[ok] 新弹层 %d 字符" % len(new_modal))

# 2) 下载线上页
live = os.path.join(HERE, "docs", "_live_index.html")
r = sh('curl -sS -m 120 --compressed -o "%s" "https://cuijiaweiyy.github.io/uptrend-board/"' % live)
if not os.path.exists(live) or os.path.getsize(live) < 100000:
    print("[FAIL] 下载线上页失败"); sys.exit(1)
h = open(live, encoding="utf-8").read()
print("[ok] 下载线上页 %d KB" % (len(h) // 1024))

# 数据时间（替换前后对比）
def data_time(s):
    m = re.search(r"数据时间：([^<]+)", s)
    return m.group(1) if m else None
dt_before = data_time(h)

# 3) 锚点
anchor_style = "弹层容器（移动端真全屏"
anchor_echarts = '<script src="echarts.min.js"></script">'.replace('"></script">', '"></script>')  # 防止误读
anchor_echarts = '<script src="echarts.min.js"></script>'
if anchor_style not in h:
    print("[FAIL] 找不到弹层 style 锚点"); sys.exit(1)
i_style = h.index(anchor_style)
idx_start = h.rfind("<style>", 0, i_style)
if idx_start < 0:
    print("[FAIL] 找不到弹层 <style> 起点"); sys.exit(1)
if anchor_echarts not in h:
    print("[FAIL] 找不到 echarts 外链锚点"); sys.exit(1)
i_echarts = h.index(anchor_echarts)
idx_end = h.rfind("</script>", 0, i_echarts) + len("</script>")
if idx_end <= idx_start:
    print("[FAIL] 弹层块边界非法"); sys.exit(1)

old_block = h[idx_start:idx_end]
print("[ok] 旧弹层块 %d 字符，起点 %d 终点 %d" % (len(old_block), idx_start, idx_end))
assert 'id="klineModal"' in old_block, "旧块不含弹层标记"
assert "</script>" in old_block, "旧块格式异常"

# 4) 替换
new_h = h[:idx_start] + new_modal + h[idx_end:]
print("[ok] 替换后 %d KB" % (len(new_h) // 1024))

# 5) 校验
assert "var DATA =" in new_h, "数据段丢失"
assert '"__cd"' in new_h, "__cd 字典丢失"
assert "function txMinuteDirect" in new_h, "新弹层未写入"
assert "/kline?code" not in new_h, "死后端 /kline 仍在"
assert "网络抖动，第" not in new_h, "旧重试文案仍在"
dt_after = data_time(new_h)
assert dt_after == dt_before, "数据时间被改：%s -> %s" % (dt_before, dt_after)
assert new_h.rstrip().endswith("</html>"), "结尾损坏"
print("[ok] 校验通过，数据时间仍为 %s" % dt_after)

out = os.path.join(HERE, "docs", "index.html")
open(out, "w", encoding="utf-8").write(new_h)
print("[ok] 已写回 docs/index.html (%d KB)" % (len(new_h) // 1024))
