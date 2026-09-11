# -*- coding: utf-8 -*-
"""云端流水线入口（GitHub Actions 专用）。

串起三步：fetch_pool（抓股票池）→ analyze（算板块渗透率）→ build_html（生成看板）。

保底原则（最重要）：
  任何一步失败，都**不覆盖**已发布的 docs/index.html。
  页面始终保持上一次成功的结果，绝不会出现空白页或半截数据。
  退出码 0 = 成功并已更新；非 0 = 失败但页面不受影响。
"""
import datetime as dt
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "output")
DOCS_DIR = os.path.join(HERE, "docs")
BOARD = os.path.join(OUT_DIR, "uptrend_board.html")
PUBLISH = os.path.join(DOCS_DIR, "index.html")

PY = sys.executable


def log(msg):
    print(msg, flush=True)


def run(script, *args, timeout=1800):
    cmd = [PY, os.path.join(HERE, script)] + [str(a) for a in args]
    log("\n$ " + " ".join(cmd))
    r = subprocess.run(cmd, cwd=HERE, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("%s 退出码 %s" % (script, r.returncode))


def read_latest_date():
    p = os.path.join(DATA_DIR, "latest_date.txt")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    return None


def main():
    for d in (DATA_DIR, OUT_DIR, DOCS_DIR):
        os.makedirs(d, exist_ok=True)

    had_publish = os.path.exists(PUBLISH)
    log("流水线开始  系统时间 %s" % dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log("已有发布页面: %s" % ("是" if had_publish else "否（首次运行）"))

    # ---- 1) 抓取股票池 ----
    try:
        run("fetch_pool.py", timeout=2400)
    except Exception as e:  # noqa: BLE001
        log("[FATAL] 抓取失败：%s" % e)
        log("[FATAL] 保留上一次看板，不覆盖发布内容。")
        return 2

    date_str = read_latest_date()
    if not date_str:
        log("[FATAL] 未取到交易日，终止。")
        return 3
    log("交易日: %s" % date_str)

    # ---- 2) 统计 ----
    try:
        run("analyze.py", date_str, timeout=3600)
    except Exception as e:  # noqa: BLE001
        log("[FATAL] 统计失败：%s" % e)
        log("[FATAL] 保留上一次看板，不覆盖发布内容。")
        return 4

    # ---- 3) 生成看板 ----
    try:
        run("build_html.py", timeout=1200)
    except Exception as e:  # noqa: BLE001
        log("[FATAL] 生成看板失败：%s" % e)
        log("[FATAL] 保留上一次看板，不覆盖发布内容。")
        return 5

    if not os.path.exists(BOARD):
        log("[FATAL] 看板文件未生成。")
        return 6

    size_kb = os.path.getsize(BOARD) / 1024.0
    if size_kb < 200:  # 正常在 1MB 以上，过小说明异常
        log("[FATAL] 看板文件异常偏小（%.0f KB），疑似生成失败。" % size_kb)
        return 7

    # ---- 4) 发布：只有全部成功才覆盖 ----
    shutil.copyfile(BOARD, PUBLISH)

    # 同时产出 board.json：前端实时代码块读它做「打开即最新」。
    # 这样即使 Worker 的 cron 没跑（新账号未激活），现有的 Actions 定时任务
    # 也能让实时数据源保持更新，不至于永远停在某个快照上。
    try:
        import json
        stats_path = os.path.join(DATA_DIR, "stats_%s.json" % date_str)
        if os.path.exists(stats_path):
            with open(stats_path, "r", encoding="utf-8") as f:
                stats = json.load(f)
            with open(os.path.join(DOCS_DIR, "board.json"), "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, separators=(",", ":"))
            log("board.json 已更新 -> docs/board.json (%.0f KB)"
                % (os.path.getsize(os.path.join(DOCS_DIR, "board.json")) / 1024.0))
    except Exception as e:  # noqa: BLE001
        log("[warn] board.json 生成失败（不影响主看板）：%s" % e)

    # 外链模式下图表库在同目录，需一并发布（缺了图表会空白）
    ec = os.path.join(OUT_DIR, "echarts.min.js")
    if os.path.exists(ec):
        shutil.copyfile(ec, os.path.join(DOCS_DIR, "echarts.min.js"))
    log("\n发布成功 -> %s (%.0f KB)" % (PUBLISH, size_kb))
    log("数据交易日: %s" % date_str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
