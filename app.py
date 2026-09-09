# -*- coding: utf-8 -*-
"""上升途中板块统计 · 云端 Web 服务。

设计：
  GET  /        首页：统计按钮 + 实时状态/日志 + 看板 iframe
  POST /run     后台线程跑流水线（fetch_pool → analyze → build_html）
  GET  /status  返回当前运行状态（status/msg/date/log）
  GET  /board   返回最新看板 HTML（供 iframe 嵌入）
  GET  /kline?code=&period=&days=  拉单只股票 K 线 JSON（代理腾讯/新浪，避开 CORS）
  GET  /chart_marks               入选「上升途中」日序列（前端作 markLine 用）
  GET  /mkt_index?sym=            大盘指数快照（底部 Tab 用，默认 sh000001）

适配 WorkBuddy「发布为应用」：
  - 监听 $PORT 环境变量，绑定 0.0.0.0
  - 纯 Python + Flask，依赖 pywencai/requests（问财 hexin-v token 由 pywencai 调 node 生成）
  - 若已有当日股票池则跳过抓取，直接重算，避免重复消耗问财额度
"""
import os
import sys
import time
import glob
import threading
import subprocess
from datetime import datetime, date, timedelta

from flask import Flask, request, jsonify, Response

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "output")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

app = Flask(__name__)
PORT = int(os.environ.get("PORT", 3000))
APP_VERSION = "20260909.1-live-quote-gh"

STATE = {
    "status": "idle",   # idle | running | done | error
    "msg": "",
    "date": "",
    "started": 0,
    "finished": 0,
    "log": [],
}
_LOCK = threading.Lock()


def _log(msg):
    with _LOCK:
        STATE["log"].append(msg)
        if len(STATE["log"]) > 300:
            STATE["log"] = STATE["log"][-300:]


def _today():
    return date.today().strftime("%Y%m%d")


def _data_date():
    """已抓取数据的最新日期：扫描 data/pool_*.json 取最大者，无则回退今天。"""
    best = ""
    try:
        for fn in os.listdir(DATA_DIR):
            if fn.startswith("pool_") and fn.endswith(".json"):
                d = fn[len("pool_"):-len(".json")]
                if len(d) == 8 and d > best:
                    best = d
    except Exception:  # noqa: BLE001
        pass
    return best or _today()


def run_pipeline():
    with _LOCK:
        STATE["status"] = "running"
        STATE["msg"] = "开始运行统计流水线…"
        STATE["date"] = _data_date()
        STATE["started"] = time.time()
        STATE["finished"] = 0
        STATE["log"] = []
    fetch_failed = False
    try:
        py = sys.executable
        env = os.environ.copy()
        # 云端走缓存模式：分母复用 totals_cache.json，避免云 IP 风控导致分母查询极慢/限流
        env["SKIP_TOTAL"] = "1"
        today = _data_date()
        had_pool = os.path.exists(os.path.join(DATA_DIR, f"pool_{today}.json"))
        _log(f"开始抓取「上升途中」股票池（支持新进入检测，分母走缓存）…")

        scripts = ["analyze.py", "build_html.py"]
        if not had_pool:
            scripts.insert(0, "fetch_pool.py")
        else:
            _log("当日股票池已存在，跳过抓取，直接重算 analyze+build（更快；强制刷新请删 data/pool_<今日>.json）")
        for script in scripts:
            _log(f">>> {script}")
            cmd = [py, os.path.join(HERE, script)]
            if script != "fetch_pool.py":
                cmd.append(today)
            r = subprocess.run(
                cmd,
                cwd=HERE, env=env, capture_output=True, text=True,
                encoding="utf-8", errors="replace",
            )
            out = (r.stdout or "").strip()
            if out:
                for line in out.splitlines():
                    _log(line)
            if r.returncode != 0:
                if script == "fetch_pool.py" and had_pool:
                    fetch_failed = True
                    _log("[WARN] 抓取失败，沿用已有股票池（当日新进入可能不更新）")
                else:
                    err = (r.stderr or "").strip()[-800:]
                    _log(f"[FAILED] {script} 退出码 {r.returncode}")
                    if err:
                        _log(err)
                    raise RuntimeError(f"{script} 执行失败")
            if script == "fetch_pool.py":
                today = _data_date()
                with _LOCK:
                    STATE["date"] = today

        with _LOCK:
            STATE["status"] = "done"
            STATE["msg"] = ("抓取失败、沿用旧数据，看板已生成（新进入未刷新）"
                            if fetch_failed else "统计完成，看板已生成")
            STATE["finished"] = time.time()
    except Exception as e:  # noqa: BLE001
        with _LOCK:
            STATE["status"] = "error"
            STATE["msg"] = f"运行出错：{e}"
            STATE["finished"] = time.time()


INDEX_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>上升途中 · 板块统计</title>
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { -webkit-text-size-adjust: 100%; }
  body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
         background:#0f1320; color:#e6e9f0; padding:16px; }
  .wrap { max-width: 960px; margin: 0 auto; }
  h1 { font-size:20px; margin:0 0 4px; }
  .sub { color:#8b93a7; font-size:13px; margin-bottom:16px; }
  .bar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  button { background:#c0392b; color:#fff; border:0; padding:11px 22px; border-radius:9px;
           font-size:15px; font-weight:600; cursor:pointer; }
  button:disabled { background:#5a3030; cursor:not-allowed; opacity:.7; }
  .status { font-size:14px; padding:6px 12px; border-radius:7px; background:#1c2333; }
  .status.running { color:#e08a1e; }
  .status.done { color:#3ec47a; }
  .status.error { color:#ff6b6b; }
  .meta { color:#8b93a7; font-size:12px; margin:8px 0; }
  #log { background:#0a0d16; border:1px solid #232c40; border-radius:8px; padding:10px;
         height:160px; overflow:auto; font-family:ui-monospace,Menlo,Consolas,monospace;
         font-size:12px; line-height:1.5; color:#9fb0c8; white-space:pre-wrap; margin-bottom:14px; }
  iframe { width:100%; height:78vh; border:1px solid #232c40; border-radius:8px; background:#fff; }
  .hint { color:#8b93a7; font-size:12px; margin-top:6px; }
  /* ===== 移动端适配（iPhone 等 ≤600px） ===== */
  @media (max-width: 600px) {
    body { padding: 12px;
           padding-left: max(12px, env(safe-area-inset-left));
           padding-right: max(12px, env(safe-area-inset-right));
           padding-bottom: max(12px, env(safe-area-inset-bottom)); }
    h1 { font-size: 18px; }
    .sub { font-size: 12px; margin-bottom: 12px; }
    .bar { flex-direction: column; align-items: stretch; gap: 8px; }
    button { width: 100%; padding: 14px; font-size: 16px; min-height: 46px; }
    .status { text-align: center; }
    #log { height: 110px; }
    /* 看板 iframe 撑满整屏：K 线弹窗（100dvh）随 iframe 视口撑满手机屏幕；
       上方标题/按钮/运行日志随页面滚动移出视野，不占屏幕 */
    iframe { height: 100vh; height: 100dvh; border-radius: 0; }
  }
</style>
</head>
<body>
<div class="wrap">
  <h1>上升途中 · 板块统计看板</h1>
  <div class="sub">同花顺问财口径（"上升途中"→技术形态"上升通道"）· 手机点一下即可统计</div>
  <div class="bar">
    <button id="runBtn" onclick="startRun()">开始统计</button>
    <span id="status" class="status">空闲</span>
  </div>
  <div class="meta" id="meta"></div>
  <div id="log"></div>
  <iframe id="board" src="/board" title="看板"></iframe>
  <div class="hint">看板区域为上次/最新生成的统计结果；点击「开始统计」重新抓取并刷新。</div>
</div>
<script>
function setStatus(s, cls){
  var el = document.getElementById('status');
  el.textContent = s;
  el.className = 'status' + (cls ? ' ' + cls : '');
}
function appendLog(lines){
  var box = document.getElementById('log');
  lines.forEach(function(l){ box.textContent += l + "\\n"; });
  box.scrollTop = box.scrollHeight;
}
function refreshBoard(){
  document.getElementById('board').src = '/board?t=' + Date.now();
}
function poll(){
  fetch('/status').then(function(r){return r.json();}).then(function(st){
    setStatus(st.status === 'running' ? '统计中…' : (st.status === 'done' ? '已完成' : (st.status === 'error' ? '出错' : '空闲')),
              st.status);
    document.getElementById('meta').textContent = st.board_time ? ('数据时间：' + st.board_time) : (st.date ? ('数据日期：' + st.date) : '');
    if (st.log && st.log.length) { appendLog(st.log.slice(window._last||0)); window._last = st.log.length; }
    if (st.status === 'done') { refreshBoard(); setBtn(true); window._timer && clearInterval(window._timer); }
    if (st.status === 'error') { setBtn(true); window._timer && clearInterval(window._timer); }
  }).catch(function(e){ /* ignore */ });
}
function setBtn(enabled){ document.getElementById('runBtn').disabled = !enabled; }
function startRun(){
  setBtn(false);
  window._last = 0;
  document.getElementById('log').textContent = '';
  fetch('/run', {method:'POST'}).then(function(r){return r.json();}).then(function(j){
    if (!j.ok) { setBtn(true); setStatus(j.msg || '无法启动', 'error'); }
  });
  window._timer = setInterval(poll, 2000);
  poll();
}
function maybeAutoRun(){
  fetch('/status').then(function(r){return r.json();}).then(function(st){
    var fresh = st.finished && ((Date.now()/1000) - st.finished) < 1200; // 20分钟内视为新鲜
    if (st.status === 'running') { return; }   // 正在跑就不重复触发
    if (!fresh) { startRun(); }                 // 超过20分钟或从未统计 → 自动开始
  }).catch(function(e){ startRun(); });
}
window.onload = function(){ window._last = 0; refreshBoard(); poll(); maybeAutoRun(); };
</script>
</body>
</html>
"""


# 看板/首页禁止缓存：防止 Safari / 反向代理把旧版 HTML 缓存住，导致改了还显示旧版
_NOCACHE = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.route("/ver")
def ver():
    board = os.path.join(OUT_DIR, "uptrend_board.html")
    mtime = int(os.path.getmtime(board)) if os.path.exists(board) else 0
    return jsonify({
        "version": APP_VERSION,
        "board": os.path.basename(board) if os.path.exists(board) else None,
        "board_mtime": mtime,
        "board_mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S") if mtime else None,
    })


@app.route("/")
def index():
    return Response(INDEX_HTML, mimetype="text/html", headers=_NOCACHE)


@app.route("/run", methods=["POST"])
def run():
    with _LOCK:
        if STATE["status"] == "running":
            return jsonify({"ok": False, "msg": "正在统计中，请稍候"})
    t = threading.Thread(target=run_pipeline, daemon=True)
    t.start()
    return jsonify({"ok": True})


@app.route("/status")
def status():
    board = os.path.join(OUT_DIR, "uptrend_board.html")
    bt = int(os.path.getmtime(board)) if os.path.exists(board) else 0
    board_time = datetime.fromtimestamp(bt).strftime("%Y-%m-%d %H:%M:%S") if bt else None
    with _LOCK:
        return jsonify({
            "status": STATE["status"],
            "msg": STATE["msg"],
            "date": STATE["date"],
            "board_time": board_time,
            "started": STATE["started"],
            "finished": STATE["finished"],
            "log": STATE["log"],
        })


@app.route("/board")
def board():
    with _LOCK:
        d = STATE["date"] or _data_date()
    # 固定文件名，避免服务到沙箱里旧代码生成的日期命名残留文件
    candidates = [os.path.join(OUT_DIR, "uptrend_board.html")]
    for p in candidates:
        if os.path.exists(p):
            return Response(open(p, encoding="utf-8").read(), mimetype="text/html", headers=_NOCACHE)
    # 看板缺失：若空闲则后台生成一次（缓存模式，无需问财实时查询）
    with _LOCK:
        idle = STATE["status"] not in ("running",)
    if idle:
        threading.Thread(target=run_pipeline, daemon=True).start()
    return Response(
        "<p style='padding:24px;font-family:sans-serif;color:#666'>"
        "看板生成中，请稍候点击右上角刷新（或稍后重新打开本页）…</p>",
        mimetype="text/html",
    )


# ---------- K 线接口 ----------
try:
    import kline as _kline_mod  # 同目录部署
except Exception:  # noqa: BLE001
    _kline_mod = None


@app.route("/kline")
def kline_api():
    """代理腾讯/新浪返回单只股票 K 线 JSON，避开浏览器 CORS。

    参数：code (必填，6 位)、period (day/week/month, 默认 day)、
          days (20-500, 默认 70)
    """
    if _kline_mod is None:
        return jsonify({"ok": False, "msg": "kline 模块未加载"}), 500
    code = (request.args.get("code") or "").strip()
    period = (request.args.get("period") or "day").strip()
    try:
        days = int(request.args.get("days") or 70)
    except ValueError:
        days = 70
    if not code or len(code) != 6 or not code.isdigit():
        return jsonify({"ok": False, "msg": "code 必须为 6 位数字"}), 400
    try:
        if period == "minute":
            data = _kline_mod.get_minute(code)
        else:
            data = _kline_mod.get_kline(code, period, days)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "msg": f"取数异常：{e}"}), 500
    if not data:
        return jsonify({"ok": False, "msg": f"未取到 {code} 的 K 线数据"}), 404
    return jsonify({"ok": True, "data": data})


@app.route("/chart_marks")
def chart_marks_api():
    """入选「上升途中」日序列（YYYY-MM-DD），供 ECharts markLine 使用。"""
    if _kline_mod is None:
        return jsonify({"ok": False, "marks": []})
    try:
        marks = _kline_mod.get_in_chart_marks()
    except Exception:  # noqa: BLE001
        marks = []
    return jsonify({"ok": True, "marks": marks})


@app.route("/mkt_index")
def mkt_index_api():
    """底部 Tab 大盘指数（默认上证 sh000001）。"""
    if _kline_mod is None:
        return jsonify({"ok": False, "msg": "kline 模块未加载"}), 500
    sym = (request.args.get("sym") or "sh000001").strip()
    try:
        d = _kline_mod.get_market_index(sym)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "msg": str(e)}), 500
    if not d:
        return jsonify({"ok": False, "msg": "未取到指数数据"}), 404
    return jsonify({"ok": True, "data": d})


def _bootstrap():
    """启动时若固定文件名看板不存在则后台生成一次（缓存模式，秒级完成）。"""
    try:
        board = os.path.join(OUT_DIR, "uptrend_board.html")
        if not os.path.exists(board):
            threading.Thread(target=run_pipeline, daemon=True).start()
    except Exception:  # noqa: BLE001
        pass


def _is_trading_now():
    """是否在 A 股交易时段内（周一至周五 09:30-11:30 / 13:00-15:00）。

    注意：云沙箱系统时钟常为 UTC，必须用北京时间（UTC+8）判断，
    否则盘中会被误判为盘后，导致调度器从不自动刷新。
    """
    now = datetime.utcnow() + timedelta(hours=8)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 60 + now.minute
    return (570 <= hm <= 690) or (780 <= hm <= 900)


_SCHED_LOCK = os.path.join(HERE, ".sched_lock")


def _sched_can_trigger():
    """30 分钟内已有触发则跳过，避免多进程/重复消耗问财额度。"""
    try:
        if time.time() - os.path.getmtime(_SCHED_LOCK) < 1800:
            return False
    except OSError:
        pass
    return True


def _sched_mark():
    try:
        open(_SCHED_LOCK, "w").close()
    except OSError:
        pass


def _scheduler():
    """后台定时调度：交易时段内若距上次统计超过 30 分钟，自动刷新一次。"""
    while True:
        time.sleep(60)
        try:
            with _LOCK:
                running = STATE["status"] == "running"
                last = STATE["finished"]
            if running:
                continue
            fresh = last and (time.time() - last) < 1800
            if _is_trading_now() and not fresh and _sched_can_trigger():
                _sched_mark()
                _log("调度：距上次统计较久，自动刷新看板…")
                threading.Thread(target=run_pipeline, daemon=True).start()
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    _bootstrap()
    threading.Thread(target=_scheduler, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
