# -*- coding: utf-8 -*-
"""K 线全屏弹层（同花顺 App K 线窗口 1:1 复刻，iPhone 15PM 视角）。

build_html.py 在生成看板 HTML 时通过占位符 __KLINE_MODAL__ 注入。
前端通过 window.openKline(code) 触发（**仅点击触发**，无 hover）；
远程数据由 /kline 与 /chart_marks 提供。

窗口结构（自上而下，对齐同花顺 App K 线页）：
  状态栏模拟条（紧凑）：时间 · 「同花顺App」红标 · 信号/wifi/电量
  导航栏：返回 ◀ + ◀ 名称 ▶ + 缩略图 + 🔍
  副标题：代码 + 标签（IPO数据/沪股通/深股通/北交所）
  价格区：大字价格 + 涨跌额 / 涨跌幅
  数据网格（2×5）：高/低/开/量比/换 + 市值/流通/市盈率/额
  异动解读条：双 badge（红底"同花顺" + 灰底"课禀"） + 摘要 + 红点 + ×
  盘后固定交易价格行：价格 + 买0/卖-283/卖-0 + ▼
  周期 Tab：分时 | 日K | 周K | 月K | 五日 | 更多▼ | ⬡(数据中心)
  均线 / 复权栏：均线▼ + 日线 + MA5/MA10/MA20/MA30 实时数值 + 前复权▼ + 筹码
  高低价差行：64.04 ←—61.20
  主 K 线：Y轴 4 个标 + 蜡烛 + MA5/10/20/30 + S/B/T 买卖点 + 同花顺水印 + 缩放工具栏 + 加自选
  底部日期轴：2026-06-01 06-23 07-17 08-12 09-07
  成交量副图：成交量▼ 领:XX 盘后:0.00 MA5/MA10 换手:X% + 红绿柱 + Y轴标
  成交额副图：成交额▼ 额:X亿 盘后:0.00 MA5/MA10 换手:X% + 红绿柱 + Y轴标
  **波段雷达 4 段（参考图新增）**：波段指数/波长/波动强度 + 双波曲线

颜色：A 股惯例 —— 红涨绿跌；夜间底色 #131722（同花顺夜间）。
"""

KLINE_MODAL_HTML = r"""<style>
/* ====== 弹层容器（移动端真全屏 100dvh / 桌面端 430px 模拟手机框） ====== */
.kline-modal {
  position: fixed; inset: 0;
  width: 100vw; height: 100dvh; height: 100vh;  /* 100dvh 避免 iOS Safari URL 栏抖动 */
  z-index: 9999; background: #131722; color: #d9dee8;
  display: flex; flex-direction: column; overflow: hidden;
  transform: translateY(100%); transition: transform .28s ease;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 12px;
}
.kline-modal.open { transform: translateY(0); }
.kline-mask {
  position: fixed; inset: 0; background: rgba(0,0,0,.4);
  z-index: 9998; opacity: 0; pointer-events: none;
  transition: opacity .25s ease;
}
.kline-mask.open { opacity: 1; pointer-events: auto; }

/* ====== 顶部状态栏（紧凑版） ====== */
.k-status {
  display: flex; align-items: center; justify-content: space-between;
  padding: 3px 14px 2px; font-size: 12px; font-weight: 600;
  background: #131722; color: #fff; flex-shrink: 0;
  padding-top: max(3px, env(safe-area-inset-top));
}
.k-status .l, .k-status .r { display: flex; align-items: center; gap: 5px; }
.k-status .l span:first-child { font-size: 12px; font-weight: 600; letter-spacing: 0.2px; }
.k-status .app-tag {
  background: #e54d2e; color: #fff; font-size: 9.5px; padding: 1px 5px;
  border-radius: 4px; font-weight: 700; margin-left: 4px; letter-spacing: 0.2px;
}
.k-status .batt { font-size: 10.5px; margin-left: 2px; }
.k-status svg { width: 12px; height: 12px; fill: #fff; }
.k-status .battbox {
  border: 1.2px solid #fff; border-radius: 2.5px; padding: 1px 1.5px;
  display: inline-flex; align-items: center; position: relative;
}
.k-status .battbox::after {
  content: ''; display: block; width: 1.5px; height: 4px;
  background: #fff; margin-left: 1px;
}
.k-status .battbar { display: inline-block; width: 15px; height: 6px; background: #fff;
                      border-radius: 1.5px; }

/* ====== 导航栏（紧凑） ====== */
.k-nav {
  display: flex; align-items: center; justify-content: space-between;
  padding: 1px 6px 0; flex-shrink: 0; height: 30px;
}
.k-nav .nav-btn {
  background: transparent; border: 0; color: #d9dee8; padding: 4px 6px;
  cursor: pointer; font-size: 18px; display: flex; align-items: center; line-height: 1;
}
.k-nav .center-grp { display: flex; align-items: center; gap: 4px; min-width: 0; flex: 1; justify-content: center; }
.k-nav .prev, .k-nav .next { color: #c0c5d1; font-size: 18px; padding: 0 2px; cursor: pointer; line-height: 1; }
.k-nav .nm { font-size: 15px; font-weight: 600; color: #fff;
             white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px; }
.k-nav .nm .check { color: #2a8aff; font-size: 12px; margin-left: 2px; vertical-align: 1px; }
.k-nav .right-grp { display: flex; gap: 0; }
.k-nav .nav-icon {
  width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center;
  color: #c0c5d1; cursor: pointer; font-size: 14px;
}

/* ====== 副标题：代码 + 标签（紧凑） ====== */
.k-sub {
  display: flex; align-items: center; gap: 5px; padding: 0 12px 1px;
  font-size: 10.5px; color: #8b93a7; flex-shrink: 0;
}
.k-sub .code { color: #d9dee8; font-weight: 500; font-size: 11.5px; }
.k-sub .tag {
  background: #2a3247; color: #c0c5d1; padding: 0 5px; border-radius: 3px;
  font-size: 9.5px;
}
.k-sub .tag.hl { background: #d97706; color: #fff; }
.k-sub .tag.bj { background: #1e3a8a; color: #fff; }

/* ====== 价格 + 数据网格（左价格 / 右 3×3 网格，整体横向） ====== */
.k-data {
  display: flex; align-items: center; gap: 8px;
  padding: 0 12px 1px; flex-shrink: 0;
}
/* ====== 价格区（垂直堆叠：大字 + 涨跌） ====== */
.k-price {
  display: flex; flex-direction: column; align-items: flex-start; gap: 1px;
  flex: 0 0 auto; min-width: 70px;
}
.k-price .big { font-size: 26px; font-weight: 700; line-height: 1.0; }
.k-price .sub { display: flex; gap: 6px; font-size: 11.5px; font-weight: 600; line-height: 1.1; }
/* ====== 数据网格 3×3（横向 label 值，对齐同花顺） ====== */
.k-grid {
  flex: 1 1 auto; min-width: 0;
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: repeat(3, auto);
  gap: 1px 6px; font-size: 10.5px; color: #6b7488;
}
.k-grid .g { display: inline-flex; align-items: baseline; gap: 3px; white-space: nowrap; }
.k-grid .g .l { color: #6b7488; font-size: 10px; }
.k-grid .g .v { color: #d9dee8; font-weight: 600; font-size: 11.5px; }
.k-grid .g .v.up { color: #ef4a4a; }
.k-grid .g .v.down { color: #1bb55b; }

/* ====== 异动解读条（薄） ====== */
.k-news {
  margin: 1px 8px 1px; padding: 2px 8px;
  background: #1c2230; border-radius: 4px; font-size: 10px; color: #c0c5d1;
  display: flex; align-items: center; gap: 5px; flex-shrink: 0;
}
.k-news .badges { display: flex; gap: 2px; flex-shrink: 0; }
.k-news .badge1 {
  background: linear-gradient(135deg,#ff6a3d,#ef4444); color: #fff;
  font-size: 8.5px; padding: 1px 4px; border-radius: 2px; font-weight: 700;
  white-space: nowrap; letter-spacing: 0.3px;
}
.k-news .badge2 {
  background: #4b5563; color: #e6e9f0;
  font-size: 8.5px; padding: 1px 4px; border-radius: 2px; font-weight: 600;
  white-space: nowrap;
}
.k-news .txt { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #c0c5d1; }
.k-news .dot { width: 5px; height: 5px; background: #ef4444; border-radius: 50%; flex-shrink: 0; }
.k-news .close { color: #6b7488; cursor: pointer; font-size: 13px; line-height: 1; padding: 0 2px; flex-shrink: 0; }

/* ====== 盘后固定交易价格行（薄） ====== */
.k-postfix {
  margin: 0 12px 1px; font-size: 10px; color: #8b93a7;
  display: flex; align-items: center; gap: 5px; flex-shrink: 0;
}
.k-postfix .lbl { color: #c0c5d1; font-weight: 500; }
.k-postfix .px { font-weight: 700; color: #ef4a4a; }
.k-postfix .px.down { color: #1bb55b; }
.k-postfix .muted { color: #8b93a7; }
.k-postfix .ar { color: #6b7488; margin-left: auto; font-size: 8.5px; }

/* ====== K 线周期 Tab（薄） ====== */
.k-tabs {
  display: flex; align-items: center; gap: 10px; padding: 1px 12px 1px;
  border-bottom: 1px solid #1f2533; flex-shrink: 0;
}
.k-tabs .seg {
  display: flex; gap: 12px; padding: 0; font-size: 12.5px;
}
.k-tabs .seg div {
  padding: 1px 0 3px; cursor: pointer; color: #8b93a7;
  border-bottom: 2px solid transparent; white-space: nowrap;
}
.k-tabs .seg div.on {
  color: #ef4a4a; border-bottom-color: #ef4a4a; font-weight: 600;
}
.k-tabs .hex { margin-left: auto; color: #6b7488; font-size: 12px; cursor: pointer; }

/* ====== 均线 / 复权栏（薄） ====== */
.k-ma {
  display: flex; align-items: center; gap: 3px 8px; flex-wrap: nowrap;
  padding: 0 12px 0; font-size: 10px; flex-shrink: 0; color: #8b93a7;
  overflow-x: auto;
}
.k-ma .grp { display: inline-flex; align-items: center; gap: 2px; flex-shrink: 0; }
.k-ma .grp .lbl { color: #6b7488; }
.k-ma .grp .day { color: #d9dee8; font-weight: 500; }
.k-ma .grp .val { font-weight: 600; }
.k-ma .ma-dot { display: inline-block; width: 5px; height: 5px; border-radius: 50%; margin-right: 1px; }
.k-ma .tagchip {
  background: #2a3247; color: #c0c5d1; padding: 1px 6px;
  border-radius: 3px; font-size: 10px; flex-shrink: 0;
}

/* ====== 高低价差行（薄） ====== */
.k-hilo {
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 12px 0; font-size: 9.5px; color: #6b7488;
  flex-shrink: 0; gap: 6px;
}
.k-hilo .arrow { flex: 1; text-align: center; letter-spacing: 1px; font-size: 8.5px; color: #4b5563; }

/* ====== 图表面板容器（flex 自动撑满） ====== */
.k-chart-wrap {
  flex: 1 1 auto; min-height: 0; position: relative; width: 100%;
}
.k-chart { width: 100%; height: 100%; }
.k-loading, .k-error {
  position: absolute; inset: 0; display: flex; align-items: center;
  justify-content: center; color: #8b93a7; font-size: 13px;
}
.k-error { color: #ef7070; }

/* ====== 波段雷达面板（4段，参考同花顺） ====== */
.k-wave-wrap {
  height: 50px; flex-shrink: 0; border-top: 1px solid #1f2533;
  background: #131722; position: relative; width: 100%;
}
.k-wave-hdr {
  position: absolute; left: 0; right: 0; top: 0; height: 16px;
  display: flex; align-items: center; gap: 8px; padding: 0 12px;
  font-size: 10px; color: #8b93a7; z-index: 1; pointer-events: none;
  background: linear-gradient(180deg, rgba(19,23,34,.92), rgba(19,23,34,0));
  white-space: nowrap; overflow: hidden;
}
.k-wave-hdr .lbl {
  display: inline-flex; align-items: center; gap: 3px;
  background: #2a8aff; color: #fff; font-size: 9.5px;
  padding: 0 5px; border-radius: 2px; font-weight: 600; flex-shrink: 0;
}
.k-wave-hdr .lbl .ar { font-size: 7.5px; }
.k-wave-hdr .q {
  color: #4b5563; margin-left: -2px; font-size: 9px; padding: 0 3px;
  border-radius: 50%; border: 1px solid #4b5563; flex-shrink: 0;
}
.k-wave-hdr .field { display: inline-flex; align-items: center; gap: 2px; }
.k-wave-hdr .field .k { color: #6b7488; }
.k-wave-hdr .field .v { color: #d9dee8; font-weight: 600; }
.k-wave-chart { width: 100%; height: 100%; }

/* ====== 主图缩放工具栏 ====== */
.k-toolbar {
  position: absolute; left: 0; right: 0; bottom: 14px;
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 8px; font-size: 10.5px; z-index: 2; pointer-events: none;
}
.k-toolbar .yaxis {
  color: #6b7488; font-size: 9.5px; padding: 1px 3px; pointer-events: none;
}
.k-toolbar .ctrls { display: flex; gap: 3px; pointer-events: auto; }
.k-toolbar .btn {
  width: 20px; height: 20px; border-radius: 50%;
  background: rgba(28,34,48,.75); border: 0; color: #c0c5d1;
  display: inline-flex; align-items: center; justify-content: center;
  cursor: pointer; font-size: 12px; line-height: 1;
}
.k-toolbar .btn:hover { background: rgba(50,60,80,.9); color: #fff; }
.k-toolbar .fav {
  pointer-events: auto; background: rgba(92,122,255,.18); border: 1px solid #5c7aff;
  color: #93b4ff; font-size: 10.5px; padding: 2px 8px; border-radius: 3px;
  cursor: pointer;
}

/* ====== 点击 K 线 · 左上角信息卡（日期 + 当日涨跌 + 至今涨跌） ====== */
.k-click-info {
  position: absolute; top: 6px; left: 8px; z-index: 3;
  background: rgba(20,25,40,.92);
  border: 1px solid #3a4565;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 11px; line-height: 1.5;
  pointer-events: none;
  display: none;
  white-space: nowrap;
  backdrop-filter: blur(2px);
  box-shadow: 0 4px 14px rgba(0,0,0,.4);
  min-width: 200px;
}
.k-click-info .d { color: #fff; font-weight: 700; font-size: 12.5px; margin-bottom: 3px; display: block; }
.k-click-info .since { color: #c0c5d1; font-size: 10.5px; margin-top: 1px; }
.k-click-info .since .v { font-size: 13.5px; font-weight: 800; margin-left: 4px; }
.k-click-info .since .v.up   { color: #ff6a5a; }
.k-click-info .since .v.down { color: #2ddb85; }
.k-click-info .day { color: #c0c5d1; font-size: 10.5px; }
.k-click-info .day .v { font-weight: 600; margin-left: 4px; }
.k-click-info .sep { color: #4b5563; margin: 0 4px; }
.k-click-info .lbl { color: #8b93a7; font-size: 9.5px; margin-right: 2px; }
.k-click-info .v.up { color: #ff6a5a; font-weight: 600; }
.k-click-info .v.down { color: #2ddb85; font-weight: 600; }
.k-click-info .v.flat { color: #c0c5d1; font-weight: 600; }
.k-click-info .hint { color: #6b7488; font-size: 9px; margin-top: 3px; display:block; }

/* ====== 副图小标题（成交量 / 成交额） ====== */
.k-subhdr {
  position: absolute; left: 0; right: 0; height: 16px;
  font-size: 10px; color: #8b93a7; padding: 0 12px;
  display: flex; align-items: center; gap: 7px; z-index: 1;
  pointer-events: none; background: linear-gradient(180deg, rgba(19,23,34,.92), rgba(19,23,34,0));
  white-space: nowrap; overflow: hidden;
}
/* 比例 40/21/15：主图 40%（2%→42%，下方留 5% 给日期轴）；
   副图标题贴各自 grid 顶部，避免压住主图日期轴 */
.k-subhdr#kVolHdr { top: calc(47% + 0.4%); }
.k-subhdr#kAmtHdr { top: calc(69% + 0.4%); }
.k-subhdr .lbl {
  display: inline-flex; align-items: center; gap: 3px;
  background: #ef4a4a; color: #fff; font-size: 9.5px;
  padding: 0 5px; border-radius: 2px; font-weight: 600; flex-shrink: 0;
}
.k-subhdr .lbl .ar { font-size: 7.5px; }
.k-subhdr .val { color: #d9dee8; font-weight: 600; }
.k-subhdr .ma { display: inline-flex; align-items: center; gap: 2px; }
.k-subhdr .ma .ma-dot { display: inline-block; width: 6px; height: 2px; border-radius: 1px; }
.k-subhdr .ma5 .ma-dot { background: #ff90a0; }
.k-subhdr .ma10 .ma-dot { background: #9b6dff; }

/* ====== 配色 ====== */
.up { color: #ef4a4a; }   /* A 股：红涨 */
.down { color: #1bb55b; } /* A 股：绿跌 */
.flat { color: #c0c5d1; }

/* 桌面端：模拟 iPhone 竖屏比例（居中手机框，占满屏高，K 线高瘦贴近同花顺截图） */
@media (min-width: 720px) {
  .kline-modal {
    left: 50%; right: auto; top: 0; bottom: 0;
    width: 430px; max-width: 100vw; height: 100vh;
    border-radius: 22px;
    box-shadow: 0 0 60px rgba(0,0,0,.6);
    transform: translate(-50%, 100%);
  }
  .kline-modal.open { transform: translate(-50%, 0); }
  .kline-mask { background: rgba(0,0,0,.55); }
}
</style>

<div class="kline-mask" id="klineMask" onclick="closeKline()"></div>
<div class="kline-modal" id="klineModal" role="dialog" aria-label="K 线图">

  <!-- 状态栏模拟条 -->
  <div class="k-status">
    <div class="l">
      <span id="kClock">--:--</span>
    </div>
    <div class="r">
      <span class="app-tag">同花顺App</span>
      <span class="battbox"><span class="battbar"></span></span>
      <span class="batt">51</span>
    </div>
  </div>

  <!-- 导航栏 -->
  <div class="k-nav">
    <button class="nav-btn" onclick="closeKline()" aria-label="返回">‹</button>
    <div class="center-grp">
      <span class="prev" onclick="stepKline(-1)" aria-label="上一只">‹</span>
      <span class="nm" id="kName">—</span>
      <span class="next" onclick="stepKline(1)" aria-label="下一只">›</span>
    </div>
    <div class="right-grp">
      <span class="nav-icon" aria-label="缩略">▦</span>
      <span class="nav-icon" aria-label="搜索">🔍</span>
      <span class="nav-icon close-x" onclick="closeKline()" aria-label="收起K线">✕</span>
    </div>
  </div>

  <!-- 副标题 -->
  <div class="k-sub">
    <span class="code" id="kCode">—</span>
    <span class="tag hl" id="kBoardTag">沪股通</span>
    <span class="tag" id="kL1Tag" style="display:none">L1</span>
  </div>

  <!-- 价格区 + 数据网格（左价格 3×3网格） -->
  <div class="k-data">
    <div class="k-price">
      <span class="big" id="kPrice">—</span>
      <span class="sub" id="kChg">—</span>
    </div>
    <div class="k-grid" id="kGrid"></div>
  </div>

  <!-- 异动解读 -->
  <div class="k-news">
    <div class="badges">
      <span class="badge1">同花顺</span>
      <span class="badge2">课禀</span>
    </div>
    <span class="txt" id="kNews">该股进入「上升途中」形态，可结合板块热度综合判断</span>
    <span class="dot"></span>
    <span class="close" onclick="this.parentElement.style.display='none'">×</span>
  </div>

  <!-- 盘后固定交易价格行 -->
  <div class="k-postfix">
    <span class="lbl">盘后固定交易价格</span>
    <span class="px" id="kPostPx">—</span>
    <span class="muted" id="kPostBuy">买0</span>
    <span class="px down" id="kPostSell1">卖-283</span>
    <span class="muted" id="kPostSell2">卖-0</span>
    <span class="ar">▼</span>
  </div>

  <!-- 周期 Tab -->
  <div class="k-tabs">
    <div class="seg" id="kSegMode">
      <div data-m="minute">分时</div>
      <div data-m="day70" class="on">日K</div>
      <div data-m="week">周K</div>
      <div data-m="month">月K</div>
      <div data-m="m5">五日</div>
      <div data-m="more">更多▼</div>
    </div>
    <span class="hex" aria-label="数据中心">⬡</span>
  </div>

  <!-- 均线 / 复权栏（独立行） -->
  <div class="k-ma" id="kMa"></div>

  <!-- 高低价差行 -->
  <div class="k-hilo" id="kHilo" style="display:none">
    <span id="kHiloHigh">—</span>
    <span class="arrow">←—————</span>
    <span id="kHiloLow">—</span>
  </div>

  <!-- 主图区 + 量/额副图 -->
  <div class="k-chart-wrap" id="klineChart">
    <div class="k-toolbar" id="kToolbar" style="display:none">
      <span class="yaxis" id="kToolYax">—</span>
      <div class="ctrls">
        <button class="btn" id="kZoomIn" aria-label="放大">+</button>
        <button class="btn" id="kZoomOut" aria-label="缩小">−</button>
        <button class="btn" id="kZoomLeft" aria-label="左移">‹</button>
        <button class="btn" id="kZoomRight" aria-label="右移">›</button>
        <button class="btn" id="kZoomReset" aria-label="重置">⤢</button>
      </div>
      <span class="fav" id="kFav" style="display:none">加自选</span>
    </div>
    <div class="k-subhdr" id="kVolHdr" style="display:none"></div>
    <div class="k-subhdr" id="kAmtHdr" style="display:none"></div>
    <div class="k-click-info" id="kClickInfo">
      <span class="d" id="kClickDate">—</span>
      <div class="day"><span class="lbl">当日</span><span class="v" id="kClickDay">—</span></div>
      <div class="since"><span class="lbl">至今</span><span class="v" id="kClickSince">—</span></div>
      <span class="hint">点击 K 线查看至今累计涨幅</span>
    </div>
    <div class="k-loading" id="klineLoading">加载中…</div>
  </div>

  <!-- 波段雷达 4 段（同花顺新增） -->
  <div class="k-wave-wrap" id="kWaveWrap" style="display:none">
    <div class="k-wave-hdr" id="kWaveHdr">
      <span class="lbl">波段雷达<span class="ar">▼</span></span>
      <span class="q">?</span>
      <span class="field"><span class="k">波段指数:</span><span class="v" id="kWaveIdx">—</span></span>
      <span class="field"><span class="k">波长:</span><span class="v" id="kWaveLen">—</span></span>
      <span class="field"><span class="k">波动强度:</span><span class="v" id="kWaveAmp">—</span></span>
    </div>
    <div class="k-wave-chart" id="kWaveChart"></div>
  </div>
</div>

<script>
(function(){
  var chart = null, waveChart = null;
  var state = { code: null, mode: 'day70', marks: [], codeList: [] };
  var C = { up: '#ff4438', down: '#16c784', flat: '#c0c5d1',
            ma5: '#ff90a0', ma10: '#9b6dff', ma20: '#5cc8ff', ma30: '#ffffff' };

  function $(id) { return document.getElementById(id); }
  function fmt(v, d) { d = d || 2; return (v === null || v === undefined || isNaN(v)) ? '—' : v.toFixed(d); }
  function clsOf(v) { return v > 0 ? 'up' : (v < 0 ? 'down' : 'flat'); }
  function sign(v) { return (v >= 0 ? '+' : '') + v; }
  function fmtVol(v) {
    if (v === null || v === undefined) return '—';
    if (v >= 1e8) return (v/1e8).toFixed(2) + '亿';
    if (v >= 1e4) return (v/1e4).toFixed(1) + '万';
    return String(Math.round(v));
  }
  function fmtAmt(v) {
    if (v === null || v === undefined) return '—';
    if (v >= 1e12) return (v/1e12).toFixed(2) + '万亿';
    if (v >= 1e8)  return (v/1e8).toFixed(2) + '亿';
    if (v >= 1e4)  return (v/1e4).toFixed(1) + '万';
    return String(Math.round(v));
  }

  /* ============ iOS 状态栏时钟 ============ */
  function tickClock() {
    var d = new Date();
    var hh = String(d.getHours()).padStart(2, '0');
    var mm = String(d.getMinutes()).padStart(2, '0');
    $('kClock').textContent = hh + ':' + mm;
  }
  tickClock(); setInterval(tickClock, 30000);

  /* ============ 健壮取数 ============ */
  function fetchJson(url, tries, onRetry) {
    tries = tries || 3;
    return new Promise(function(resolve, reject){
      function attempt(n){
        fetch(url, { cache: 'no-store' }).then(function(r){
          if (!r.ok) throw new Error('HTTP ' + r.status);
          return r.text();
        }).then(function(t){
          if (!t || !t.trim()) throw new Error('空响应');
          try { resolve(JSON.parse(t)); }
          catch(e) { throw new Error('JSON 解析失败'); }
        }).catch(function(e){
          if (n < tries) {
            if (onRetry) onRetry(n);
            setTimeout(function(){ attempt(n + 1); }, n === 1 ? 800 : 1800);
          } else { reject(e); }
        });
      }
      attempt(1);
    });
  }

  /* ============ 列表 ============ */
  function collectCodeList() {
    var set = [], seen = {};
    document.querySelectorAll('.kline-trigger[data-code]').forEach(function(el){
      var c = el.getAttribute('data-code');
      if (c && !seen[c]) { seen[c] = 1; set.push(c); }
    });
    state.codeList = set;
  }

  /* ============ AI 解读文案 ============ */
  function pickInsight(code) {
    var sel = '.kline-trigger[data-code="' + code + '"]';
    var row = document.querySelector(sel);
    if (!row) return null;
    var ind = row.getAttribute('data-ind') || '';
    var con = row.getAttribute('data-con') || '';
    var pat = row.getAttribute('data-pat') || '';
    var sig = row.getAttribute('data-sig') || '';
    var isSt = row.getAttribute('data-st') === '1';
    var arr = [];
    if (pat) { var ps = pat.split('||').filter(Boolean); if (ps.length) arr.push('形态：' + ps.join('·')); }
    if (sig) { var ss = sig.split('||').filter(Boolean); if (ss.length) arr.push('信号：' + ss.join('·')); }
    if (con) { var cs = con.split(',').filter(Boolean).slice(0, 2); if (cs.length) arr.push('热点：' + cs.join('·')); }
    if (!arr.length) return ind ? (ind + '板块 · 进入「上升途中」形态') : '该股进入「上升途中」形态';
    return (isSt ? '【ST】' : '') + arr.join(' · ');
  }
  function setNews(code) {
    var txt = pickInsight(code) || '该股进入「上升途中」形态，可结合板块热度综合判断';
    var el = $('kNews'); if (el) el.textContent = txt;
  }

  /* ============ 打开 / 关闭 ============ */
  window.openKline = function(code) {
    if (!code) return;
    state.code = String(code).padStart(6, '0');
    collectCodeList();
    $('klineModal').classList.add('open');
    $('klineMask').classList.add('open');
    document.body.style.overflow = 'hidden';
    setNews(state.code);
    if (window.__HAS_BACKEND__ && !state.marks.length) {
      fetchJson('/chart_marks', 2).then(function(j){
        state.marks = (j && j.ok && j.marks) || [];
      }).catch(function(){});
    }
    loadKline();
  };
  window.closeKline = function() {
    $('klineModal').classList.remove('open');
    $('klineMask').classList.remove('open');
    document.body.style.overflow = '';
    if (chart) { chart.dispose(); chart = null; }
    if (waveChart) { waveChart.dispose(); waveChart = null; }
    dLastDates = []; dLastOhlc = []; dLastLen = 0;
  };
  window.stepKline = function(delta) {
    if (!state.codeList.length) return;
    var idx = state.codeList.indexOf(state.code);
    if (idx < 0) idx = 0;
    var n = state.codeList.length;
    var next = (idx + delta + n) % n;
    state.code = state.codeList[next];
    setNews(state.code);
    loadKline();
    hideClickInfo();
  };
  window.refreshKline = function() { loadKline(); };

  /* ============ 头部 / 网格渲染 ============ */
  function renderHeader(d) {
    $('kName').innerHTML = (d.name || '—') + ' <span class="check">✓</span>';
    $('kCode').textContent = d.code;
    var ex = d.exchange ||
             (d.code.startsWith('92') || d.code.startsWith('4') || d.code.startsWith('8') ? 'BJ'
              : d.code.startsWith('6') ? 'SH' : 'SZ');
    var tag = '', hlClass = '';
    if (ex === 'BJ') { tag = '北交所'; hlClass = 'bj'; }
    else if (ex === 'SH') tag = '沪股通';
    else tag = '深股通';
    var btag = $('kBoardTag');
    btag.textContent = tag;
    btag.className = 'tag' + (hlClass ? ' ' + hlClass : ' hl');

    var sub = '';
    if (d.code.startsWith('688')) sub = '科创板';
    else if (d.code.startsWith('300') || d.code.startsWith('301')) sub = '创业板';
    var l1 = $('kL1Tag');
    if (sub) { l1.textContent = sub; l1.style.display = ''; }
    else { l1.style.display = 'none'; }

    var last = d.last || {};
    var prevClose = d.prev_close || last.close;
    var chg = last.close - prevClose;
    var pct = prevClose ? chg / prevClose * 100 : 0;
    var cls = clsOf(chg);

    var pEl = $('kPrice');
    pEl.textContent = fmt(last.close);
    pEl.className = 'big ' + cls;
    $('kChg').innerHTML = '<span class="' + cls + '">' + sign(chg.toFixed(2)) +
      '</span> <span class="' + cls + '">' + sign(pct.toFixed(2)) + '%</span>';

    var high = d.daily_high || last.high;
    var low  = d.daily_low  || last.low;
    var open = d.daily_open || last.open;
    var vol  = d.daily_vol  || last.vol;
    var amt  = d.daily_amt  || (vol ? (vol * ((open + high + low + last.close) / 4) / 100) : 0);

    /* 颜色规则（对齐同花顺）：
       高 = 当日方向（红涨/绿跌），低 = 反向，
       开 = close vs open（close>open 红），量比 >1 红 */
    var dayUp = last.close >= prevClose;
    var openUp = last.close >= open;
    var lbUp = d.lb && d.lb > 1;
    function cell(label, value, color) {
      return '<div class="g"><span class="l">' + label + '</span>' +
             '<span class="v' + (color ? ' ' + color : '') + '">' + value + '</span></div>';
    }
    /* 3 列 × 3 行：列1 高/低/开 | 列2 市值/流通/市盈TTM | 列3 量比/换/额 */
    var html = '';
    html += cell('高',   fmt(high),                                   dayUp  ? 'up'   : 'down');
    html += cell('市值', d.mv   ? d.mv.toFixed(2) + '亿' : '—');
    html += cell('量比', d.lb   ? d.lb.toFixed(2)        : '—',        lbUp   ? 'up'   : '');
    html += cell('低',   fmt(low),                                    dayUp  ? 'down' : 'up');
    html += cell('流通', d.cmv  ? d.cmv.toFixed(2) + '亿': '—');
    html += cell('换',   d.hs   ? d.hs.toFixed(2) + '%'  : '—');
    html += cell('开',   fmt(open),                                   openUp ? 'up'   : 'down');
    html += cell('市盈<sup style="font-size:8px">TTM</sup>',
                 d.pe_ttm ? d.pe_ttm.toFixed(2)         : '—');
    html += cell('额',   fmtAmt(amt));
    $('kGrid').innerHTML = html;

    var pxEl = $('kPostPx');
    if (pxEl) { pxEl.textContent = fmt(last.close); pxEl.className = 'px ' + cls; }

    var dates = d.dates || [];
    var ohlc = d.ohlc || [];
    var hi = -Infinity, lo = Infinity;
    for (var i = 0; i < ohlc.length; i++) {
      if (ohlc[i][3] > hi) hi = ohlc[i][3];
      if (ohlc[i][2] < lo) lo = ohlc[i][2];
    }
    var hilo = $('kHilo');
    if (hilo && hi > -Infinity && lo < Infinity) {
      $('kHiloHigh').textContent = fmt(hi);
      $('kHiloLow').textContent  = fmt(lo);
      hilo.style.display = '';
    } else if (hilo) { hilo.style.display = 'none'; }
  }

  /* ============ 均线图例 ============ */
  function renderMaLegend(d, isMin) {
    var ma = d.ma || {};
    function maTxt(key, color, label) {
      var arr = ma[key] || [];
      var val = arr.length ? arr[arr.length - 1] : null;
      return '<span class="grp">' +
             '<span class="ma-dot" style="background:' + color + '"></span>' +
             '<span class="lbl">' + label + ':</span>' +
             '<span class="val" style="color:' + color + '">' + fmt(val) + '</span></span>';
    }
    var html = '<span class="grp"><span class="lbl">均线</span><span class="lbl" style="font-size:9px">▼</span></span>' +
               '<span class="grp"><span class="day">' + (isMin ? '分时' : '日线') + '</span></span>' +
               maTxt('ma5',  C.ma5,  'MA5') +
               maTxt('ma10', C.ma10, '10') +
               maTxt('ma20', C.ma20, '20') +
               maTxt('ma30', C.ma30, '30') +
               '<span class="grp" style="margin-left:auto;flex-shrink:0"><span class="tagchip">前复权 ▼</span></span>' +
               '<span class="grp"><span class="tagchip">筹码</span></span>';
    $('kMa').innerHTML = html;
  }

  /* ============ 副图小标题 ============ */
  function renderSubHdrs(d) {
    var vh = $('kVolHdr'), ah = $('kAmtHdr');
    if (!vh || !ah) return;
    var n = d.dates ? d.dates.length : 0;
    var v = d.volumes || [];
    var a = amtSeries(d);
    var lastV = n ? v[n - 1] : 0;
    var lastA = n ? a[n - 1] : 0;
    var hs = d.hs ? d.hs.toFixed(2) + '%' : '—';

    vh.innerHTML =
      '<span class="lbl">成交量<span class="ar">▼</span></span>' +
      '<span>量:<span class="val">' + fmtVol(lastV) + '</span></span>' +
      '<span>盘后:<span class="val">0.00</span></span>' +
      '<span class="ma ma5"><span class="ma-dot"></span>MA5:<span class="val">' + fmtVol(maArr(v, 5)) + '</span></span>' +
      '<span class="ma ma10"><span class="ma-dot"></span>10:<span class="val">' + fmtVol(maArr(v, 10)) + '</span></span>' +
      '<span>换手:<span class="val">' + hs + '</span></span>';
    vh.style.display = '';

    ah.innerHTML =
      '<span class="lbl">成交额<span class="ar">▼</span></span>' +
      '<span>额:<span class="val">' + fmtAmt(lastA) + '</span></span>' +
      '<span>盘后:<span class="val">0.00</span></span>' +
      '<span class="ma ma5"><span class="ma-dot"></span>MA5:<span class="val">' + fmtAmt(maArr(a, 5)) + '</span></span>' +
      '<span class="ma ma10"><span class="ma-dot"></span>10:<span class="val">' + fmtAmt(maArr(a, 10)) + '</span></span>' +
      '<span>换手:<span class="val">' + hs + '</span></span>';
    ah.style.display = '';
  }
  function maArr(arr, m) {
    if (!arr || arr.length < m) return null;
    var s = 0;
    for (var i = arr.length - m; i < arr.length; i++) s += arr[i] || 0;
    return s / m;
  }
  function amtSeries(d) {
    var n = d.ohlc.length, out = [];
    for (var i = 0; i < n; i++) {
      var o = d.ohlc[i];
      var avg = (o[0] + o[1] + o[2] + o[3]) / 4;
      out.push((d.volumes[i] || 0) * avg / 100);
    }
    return out;
  }

  /* ============ 波段雷达（同花顺第 4 段，参考截图） ============ */
  function renderWaveRadar(d) {
    var wrap = $('kWaveWrap');
    if (!wrap) return;
    wrap.style.display = '';
    var pts = 60;
    var n = d.ohlc ? d.ohlc.length : 0;
    if (n < 5) { wrap.style.display = 'none'; return; }
    /* 用真实收盘价做主波（更接近参考图的双波视觉） */
    var close = d.ohlc.map(function(o){ return o[1]; });
    var lo = Math.min.apply(null, close), hi = Math.max.apply(null, close);
    var range = (hi - lo) || 1;
    var wave1 = close.map(function(v){ return 10 + (v - lo) / range * 80; });
    /* 副波：收盘价的 1.3 周期 sin 拟合（更柔和） */
    var wave2 = [];
    for (var i = 0; i < n; i++) {
      var t = i / n * Math.PI * 4.2;
      var v = 50 + Math.sin(t) * 18 + Math.cos(t * 2.1) * 8;
      wave2.push(v);
    }
    /* 统计 */
    var avg = 0, max = -Infinity, min = Infinity;
    for (var j = 0; j < wave1.length; j++) {
      avg += wave1[j];
      if (wave1[j] > max) max = wave1[j];
      if (wave1[j] < min) min = wave1[j];
    }
    avg = avg / wave1.length;
    var idx = (avg / 100 * 99).toFixed(1);
    var amp = (max - min).toFixed(1);
    var len = (n / 8).toFixed(1);
    $('kWaveIdx').textContent = idx;
    $('kWaveLen').textContent = len;
    $('kWaveAmp').textContent = amp;

    if (waveChart) { waveChart.dispose(); waveChart = null; }
    var inner = $('kWaveChart');
    inner.innerHTML = '';
    waveChart = echarts.init(inner);
    waveChart.setOption({
      animation: false,
      backgroundColor: 'transparent',
      grid: { left: 0, right: 0, top: 16, bottom: 0 },
      xAxis: { type: 'category', show: false, data: wave1.map(function(_,i){ return i; }) },
      yAxis: { type: 'value', show: false, min: 0, max: 100 },
      series: [
        { type: 'line', data: wave1, symbol: 'none', smooth: true,
          lineStyle: { width: 1.2, color: C.up }, areaStyle: { color: 'rgba(239,74,74,.10)' } },
        { type: 'line', data: wave2, symbol: 'none', smooth: true,
          lineStyle: { width: 1, color: '#8b93a7', type: 'dashed' } }
      ]
    });
  }

  /* ============ 点击 K 线 · 左上角信息卡 ============ */
  var dLastDates = [], dLastOhlc = [], dLastLen = 0;
  function showClickInfo(i) {
    var el = $('kClickInfo'); if (!el) return;
    if (i < 0 || i >= dLastLen) { el.style.display = 'none'; return; }
    var dates = dLastDates, ohlc = dLastOhlc, n = ohlc.length;
    var o = ohlc[i];
    var open = o[0], close = o[1];
    if (open === null || open === undefined || open === 0) { el.style.display = 'none'; return; }
    var dayChg = close - open;
    var dayPct = dayChg / open * 100;
    var lastClose = ohlc[n - 1][1];
    /* 至今 = 现在close - 点击日open（含点击当日的跳空+日内波动） */
    var sinceChg = lastClose - open;
    var sincePct = sinceChg / open * 100;
    function cls(v){ return v > 0 ? 'up' : (v < 0 ? 'down' : 'flat'); }
    function sv(v){ return (v >= 0 ? '+' : '') + v.toFixed(2); }
    function pv(v){ return (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }
    $('kClickDate').textContent = dates[i] || ('idx ' + i);
    $('kClickDay').className   = 'v ' + cls(dayChg);
    $('kClickDay').textContent = sv(dayChg) + ' (' + pv(dayPct) + ')';
    $('kClickSince').className = 'v ' + cls(sinceChg);
    $('kClickSince').textContent = sv(sinceChg) + ' (' + pv(sincePct) + ')';
    el.style.display = '';
  }
  function hideClickInfo() { var el = $('kClickInfo'); if (el) el.style.display = 'none'; }

  /* ============ 加载入口 ============ */
  function setLoading(txt, isErr) {
    var el = $('klineLoading');
    if (!el) {
      el = document.createElement('div');
      el.id = 'klineLoading';
      el.className = isErr ? 'k-error' : 'k-loading';
      $('klineChart').appendChild(el);
    }
    el.textContent = txt;
    el.className = isErr ? 'k-error' : 'k-loading';
  }
  function clearLoading() {
    var el = $('klineLoading'); if (el) el.remove();
  }
  /* ===== 静态托管兜底：直连腾讯公开行情取 K 线（无后端时自动启用） ===== */
  function txSym(code) {
    var c = String(code || '').replace(/[^0-9]/g, '');
    if (!c) return '';
    var h = c.charAt(0);
    if (h === '6' || h === '9') return 'sh' + c;
    if (h === '4' || h === '8') return 'bj' + c;
    return 'sz' + c;
  }
  function txName(code) {
    try {
      var el = document.querySelector('.diffcard[data-code="' + code + '"] .dname');
      if (el && el.textContent) return el.textContent.trim().split(' ')[0] || code;
    } catch (e) {}
    return code;
  }
  function calcMA(ohlc, n) {
    var out = [];
    for (var i = 0; i < ohlc.length; i++) {
      if (i < n - 1) { out.push(null); continue; }
      var s = 0;
      for (var k = 0; k < n; k++) s += ohlc[i - k][1];
      out.push(+(s / n).toFixed(3));
    }
    return out;
  }
  function txKlineDirect(code, period, days) {
    var sym = txSym(code);
    var url = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' +
              sym + ',' + period + ',,,' + days + ',qfq';
    return fetchTxJson(url)
      .then(function (j) {
        var node = (j && j.data && j.data[sym]) || {};
        var rows = node['qfq' + period] || node[period] || [];
        if (!rows || !rows.length) throw new Error('无数据');
        var dates = [], ohlc = [], vols = [];
        for (var i = 0; i < rows.length; i++) {
          var r = rows[i];
          dates.push(r[0]);
          ohlc.push([Number(r[1]), Number(r[2]), Number(r[4]), Number(r[3])]);
          vols.push(Number(r[5]));
        }
        return {
          ok: true,
          data: {
            code: code, name: txName(code), period: period, days: days,
            dates: dates, ohlc: ohlc, volumes: vols,
            /* renderKline 读取 d.ma.ma5/ma10/ma20/ma30，键名必须匹配 */
            ma: { ma5: calcMA(ohlc, 5), ma10: calcMA(ohlc, 10),
                  ma20: calcMA(ohlc, 20), ma30: calcMA(ohlc, 30) }
          }
        };
      });
  }

  /* 腾讯行情直连：带一次重试，吸收瞬时波动 */
  function fetchTxJson(url) {
    return new Promise(function (resolve, reject) {
      function go(n) {
        fetch(url, { cache: 'no-store' })
          .then(function (r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
          .then(resolve)
          .catch(function (e) {
            if (n < 2) { setLoading('行情重试中…'); setTimeout(function () { go(n + 1); }, 900); }
            else reject(e);
          });
      }
      go(1);
    });
  }

  /* 分时直连腾讯：价格/均价/量取自分钟线，昨收取自日K前一日收盘 */
  function txMinuteDirect(code) {
    var sym = txSym(code);
    var mUrl = 'https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=' + sym;
    var dUrl = 'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' + sym + ',day,,,3,qfq';
    return Promise.all([
      fetchTxJson(mUrl),
      fetchTxJson(dUrl).catch(function () { return null; })
    ]).then(function (res) {
      var mj = res[0], dj = res[1];
      var node = (mj && mj.data && mj.data[sym]) || {};
      var md = node.data || {};
      var pts = md.data || [];
      if (!pts.length) throw new Error('无分时数据');
      var prices = [], times = [], vols = [], cumAmt = [], cumVol = [], running = 0;
      for (var i = 0; i < pts.length; i++) {
        var pr = String(pts[i]).split(' ');          // 腾讯分时每点为空格分隔字符串
        prices.push(Number(pr[1]));
        times.push(pr[0]);
        var cv = Number(pr[2]) || 0;                 // 累计成交量(手)
        vols.push(i === 0 ? cv : cv - running);     // 还原为每分钟成交量
        running = cv;
        cumVol.push(cv);
        cumAmt.push(Number(pr[3]) || 0);             // 累计成交额(元)
      }
      var avg = cumVol.map(function (cv, i) {
        return cv > 0 ? +(cumAmt[i] / (cv * 100)).toFixed(3) : prices[i];
      });
      var prev = null;
      if (dj) {
        var dnode = (dj.data && dj.data[sym]) || {};
        var drows = dnode.qfqday || dnode.day || [];
        if (drows.length >= 2) prev = Number(drows[drows.length - 2][2]);   // 昨收
        else if (drows.length === 1) prev = Number(drows[0][2]);
      }
      return {
        ok: true,
        data: {
          code: code, name: txName(code), period: 'minute', days: 1,
          date: md.date || '', times: times, prices: prices,
          vols: vols, avg: avg, prev_close: prev
        }
      };
    });
  }

  /* 东财行情直连（与主看板实时行情同源 push2.eastmoney.com，浏览器已验证可达 + CORS） */
  function emSecid(code) {
    var pre = (code.charAt(0) === '6') ? '1' : '0';
    return pre + '.' + code;
  }
  function emKlineDirect(code, period, days) {
    var secid = emSecid(code);
    var klt = (period === 'week') ? 102 : (period === 'month') ? 103 : 101;
    var url = 'https://push2.eastmoney.com/api/qt/stock/kline/get?secid=' + secid +
              '&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57' +
              '&klt=' + klt + '&fqt=1&end=20500101&lmt=' + days + '&_=' + Date.now();
    return fetchTxJson(url).then(function (j) {
      var dd = (j && j.data) || {};
      var kl = dd.klines || [];
      if (!kl.length) throw new Error('无数据');
      var dates = [], ohlc = [], vols = [];
      for (var i = 0; i < kl.length; i++) {
        var p = String(kl[i]).split(',');
        dates.push(p[0]);
        ohlc.push([Number(p[1]), Number(p[2]), Number(p[4]), Number(p[3])]); // 开,收,低,高
        vols.push(Number(p[5]));
      }
      return {
        ok: true,
        data: {
          code: code, name: dd.name || code, period: period, days: days,
          dates: dates, ohlc: ohlc, volumes: vols,
          ma: { ma5: calcMA(ohlc, 5), ma10: calcMA(ohlc, 10),
                ma20: calcMA(ohlc, 20), ma30: calcMA(ohlc, 30) }
        }
      };
    });
  }
  function emMinuteDirect(code) {
    var secid = emSecid(code);
    var url = 'https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=' + secid +
              '&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58' +
              '&iscr=0&ndays=1&forcect=1&_=' + Date.now();
    return fetchTxJson(url).then(function (j) {
      var dd = (j && j.data) || {};
      var tr = dd.trends || [];
      if (!tr.length) throw new Error('无分时数据');
      var prices = [], times = [], vols = [], cumAmt = [], cumVol = [], running = 0;
      var prev = Number(dd.preClose) || null;
      for (var i = 0; i < tr.length; i++) {
        var p = String(tr[i]).split(',');
        times.push(String(p[0]).slice(11));           // "2026-09-09 09:30" -> "09:30"
        prices.push(Number(p[2]));                    // 分时走势取每分钟收盘价
        var cv = Number(p[5]) || 0;                   // 累计成交量(手)
        vols.push(i === 0 ? cv : cv - running);
        running = cv;
        cumVol.push(cv);
        cumAmt.push(Number(p[6]) || 0);
      }
      var avg = cumVol.map(function (cv, i) {
        return cv > 0 ? +(cumAmt[i] / (cv * 100)).toFixed(3) : prices[i];
      });
      return {
        ok: true,
        data: {
          code: code, name: dd.name || code, period: 'minute', days: 1,
          date: dd.date || '', times: times, prices: prices,
          vols: vols, avg: avg, prev_close: prev
        }
      };
    });
  }

  function loadKline() {
    if (!state.code) return;
    setLoading('行情加载中…');
    var isMin = state.mode === 'minute';
    var isM5  = state.mode === 'm5';
    var isMore = state.mode === 'more';
    var period, days;
    if (isMin)        { period = 'minute'; days = 1; }
    else if (isM5)    { period = 'day';    days = 30; }
    else if (isMore)  { period = 'day';    days = 70; }
    else if (state.mode === 'week')  { period = 'week';  days = 100; }
    else if (state.mode === 'month') { period = 'month'; days = 60;  }
    else                              { period = 'day';   days = 70;  }

    function handle(j) {
      if (!j || !j.ok) { setLoading((j && j.msg) || '加载失败', true); return; }
      renderHeader(j.data);
      renderMaLegend(j.data, isMin);
      if (isMin) { renderMinute(j.data); hide('kWaveWrap'); hideClickInfo(); }
      else { renderKline(j.data); renderSubHdrs(j.data); renderWaveRadar(j.data); }
    }
    /* 多源兜底：主源东财（与主看板实时行情同源，浏览器已验证可达），兜底腾讯。
       任一成功即渲染；全部失败才提示，文案注明已尝试的源，便于定位。 */
    function tryLoad(sources, tried) {
      tried = tried || [];
      if (!sources.length) {
        setLoading('K线加载失败：腾讯/东财行情源均不可用', true);
        return;
      }
      var src = sources[0];
      src().then(handle).catch(function (e) {
        tried.push(src._name || '?');
        if (sources.length > 1) {
          setLoading('切换行情源…（' + tried.join('/') + ' 失败）');
          setTimeout(function () { tryLoad(sources.slice(1), tried); }, 200);
        } else {
          setLoading('K线加载失败：' + ((e && e.message) || e) +
                     '（已尝试：' + tried.join('/') + '）', true);
        }
      });
    }
    var sources = isMin
      ? [function(){ return emMinuteDirect(state.code); }, function(){ return txMinuteDirect(state.code); }]
      : [function(){ return emKlineDirect(state.code, period, days); }, function(){ return txKlineDirect(state.code, period, days); }];
    sources[0]._name = '东财'; sources[1]._name = '腾讯';
    tryLoad(sources);
  }

  /* ============ 日 K（含成交量 + 成交额） ============ */
  function renderKline(d) {
    dLastDates = d.dates || [];
    dLastOhlc  = d.ohlc  || [];
    dLastLen   = dLastOhlc.length;
    hideClickInfo();
    clearLoading();
    var el = $('klineChart');
    el.innerHTML = '<div class="k-toolbar" id="kToolbar" style="display:none">' +
                     '<span class="yaxis" id="kToolYax">—</span>' +
                     '<div class="ctrls">' +
                       '<button class="btn" id="kZoomIn" aria-label="放大">+</button>' +
                       '<button class="btn" id="kZoomOut" aria-label="缩小">−</button>' +
                       '<button class="btn" id="kZoomLeft" aria-label="左移">‹</button>' +
                       '<button class="btn" id="kZoomRight" aria-label="右移">›</button>' +
                       '<button class="btn" id="kZoomReset" aria-label="重置">⤢</button>' +
                     '</div>' +
                     '<span class="fav" id="kFav" style="display:none">加自选</span>' +
                   '</div>' +
                   '<div class="k-subhdr" id="kVolHdr" style="display:none"></div>' +
                   '<div class="k-subhdr" id="kAmtHdr" style="display:none"></div>' +
                   '<div class="k-chart" id="kChartInner"></div>';
    chart = echarts.init($('kChartInner'));

    var n = d.ohlc.length;
    var dates = d.dates;
    var vol = d.volumes;
    var amt = amtSeries(d);
    var ma5  = d.ma.ma5,  ma10 = d.ma.ma10;
    var ma20 = d.ma.ma20, ma30 = d.ma.ma30;
    var volMA5 = maArrSeries(vol, 5);
    var volMA10= maArrSeries(vol, 10);
    var amtMA5 = maArrSeries(amt, 5);
    var amtMA10= maArrSeries(amt, 10);

    /* 入选日标记：主图顶部短竖虚线 + 「入选」标签（只画在 K 线最高价上方，不贯穿蜡烛，避免遮挡） */
    var markData = [];
    if (state.marks && state.marks.length) {
      var hiAll = -Infinity, loAll = Infinity, _nn = d.ohlc.length;
      for (var _z = 0; _z < _nn; _z++) {
        if (d.ohlc[_z][3] > hiAll) hiAll = d.ohlc[_z][3];
        if (d.ohlc[_z][2] < loAll) loAll = d.ohlc[_z][2];
      }
      var _span = (hiAll - loAll) || 1;
      for (var _i = 0; _i < state.marks.length; _i++) {
        var _idx = dates.indexOf(state.marks[_i]);
        if (_idx >= 0) {
          var _xd = dates[_idx];
          var _top = hiAll + _span * 0.06;
          var _bot = d.ohlc[_idx][3] + _span * 0.02;
          /* ECharts markLine 多段线：必须是嵌套数组，每段用 xAxis/yAxis 在数据坐标系下定位 */
          markData.push([
            { xAxis: _xd, yAxis: _top,
              lineStyle: { color: '#e08a1e', type: 'dashed', width: 1.2, opacity: 0.95 },
              label: { show: true, formatter: '入选', position: 'middle',
                       color: '#fff', backgroundColor: '#e08a1e',
                       padding: [1, 3], borderRadius: 3, fontSize: 10, fontWeight: 700, distance: 2,
                       clipOverflow: false } },
            { xAxis: _xd, yAxis: _bot }
          ]);
        }
      }
    }

    var bsPoints = [];
    var highs = [], lows = [];
    for (var k = 2; k < n - 2; k++) {
      var h = true, l = true;
      for (var m = k - 2; m <= k + 2; m++) {
        if (m === k) continue;
        if (d.ohlc[m][3] >= d.ohlc[k][3]) h = false;
        if (d.ohlc[m][2] <= d.ohlc[k][2]) l = false;
      }
      if (h) highs.push(k);
      if (l) lows.push(k);
    }
    var alternates = [], lastHi = -1, lastLo = -1;
    for (var pi = highs.length - 1; pi >= 0 && alternates.length < 6; pi--) {
      var ix = highs[pi];
      if (lastHi < 0 || ix > lastHi) {
        alternates.push({ idx: ix, type: 'S' });
        lastHi = ix;
        break;
      }
    }
    for (var qi = lows.length - 1; qi >= 0 && alternates.length < 6; qi--) {
      var jx = lows[qi];
      if (lastLo < 0 || jx > lastLo) {
        if (alternates.length && alternates[alternates.length-1].idx < jx) {
          alternates.push({ idx: jx, type: 'B' });
          lastLo = jx;
        }
      }
    }
    for (var si = highs.length - 2; si >= 0 && alternates.length < 6; si--) {
      var tx = highs[si];
      if (tx < lastLo) {
        alternates.push({ idx: tx, type: 'S' });
        break;
      }
    }
    for (var ti = n - 1; ti > 5; ti--) {
      if (ma5[ti] > ma20[ti] && ma5[ti-1] <= ma20[ti-1]) {
        alternates.push({ idx: ti, type: 'T' });
        break;
      }
    }
    alternates = alternates.slice(-4);
    var bsMarkPoint = { symbol: 'circle', symbolSize: 0,
      label: { show: false }, data: [] };
    for (var ai = 0; ai < alternates.length; ai++) {
      var a = alternates[ai];
      var val = a.type === 'B' ? d.ohlc[a.idx][2] : (a.type === 'S' ? d.ohlc[a.idx][3] : d.ohlc[a.idx][3]);
      var color = a.type === 'B' ? '#1bb55b' : (a.type === 'S' ? '#ef4a4a' : '#f5b942');
      bsMarkPoint.data.push({
        name: a.type, value: a.idx, yAxis: val,
        itemStyle: { color: color, borderColor: '#fff', borderWidth: 0 },
        label: {
          show: true, formatter: a.type, position: a.type === 'B' ? 'bottom' : 'top',
          color: '#fff', backgroundColor: color, padding: [2,4], borderRadius: 3,
          fontSize: 10, fontWeight: 700
        }
      });
    }
    /* 入选标记已并入 candle 的 markLine（主图顶部短竖线），不再并入 B/S/T markPoint */

    var watermark = {
      type: 'group', silent: true,
      children: [{
        type: 'text', silent: true,
        style: {
          text: '同花顺',
          font: 'bold 38px -apple-system, sans-serif',
          fill: 'rgba(255,255,255,0.04)'
        },
        left: 'center', top: 'middle'
      }]
    };

    var sumLvl = 0, cntLvl = 0;
    for (var li = Math.max(0, n - 60); li < n; li++) { sumLvl += d.ohlc[li][1]; cntLvl++; }
    var avgPx = cntLvl ? sumLvl / cntLvl : 0;
    var dashLines = avgPx ? [
      { yAxis: Math.round(avgPx * 1.05 * 100) / 100,
        lineStyle: { color: '#5a6478', type: 'dashed', width: 0.8 },
        label: { show: false } },
      { yAxis: Math.round(avgPx * 0.95 * 100) / 100,
        lineStyle: { color: '#5a6478', type: 'dashed', width: 0.8 },
        label: { show: false } }
    ] : [];

    chart.setOption({
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: '#d9dee8', fontSize: 11 },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'cross', link: [{xAxisIndex: 'all'}] },
        backgroundColor: 'rgba(20,25,40,.95)', borderColor: '#2a3247',
        textStyle: { color: '#e6e9f0', fontSize: 11 },
        formatter: function(params){
          var i = params[0].dataIndex;
          var o = d.ohlc[i];
          return '<b>' + dates[i] + '</b><br/>' +
                 '开:' + fmt(o[0]) + ' 收:' + fmt(o[1]) + '<br/>' +
                 '低:' + fmt(o[2]) + ' 高:' + fmt(o[3]) + '<br/>' +
                 '量:' + fmtVol(vol[i]) + '手 额:' + fmtAmt(amt[i]);
        }
      },
      axisPointer: { link: [{xAxisIndex: 'all'}] },
      grid: [
        { left: 4, right: 6, top: 2,  height: '40%' },     // 主图（2%→42%）缩 8%
        { left: 4, right: 6, top: '47%', height: '21%' },  // 成交量（47%→68%）
        { left: 4, right: 6, top: '69%', height: '15%' }   // 成交额（69%→84%）
      ],
      xAxis: [
        { type: 'category', data: dates, boundaryGap: true,
          axisLabel: { fontSize: 10, color: '#6b7488', margin: 6 },
          axisLine: { lineStyle: { color: '#2a3247' } },
          splitLine: { show: false }, axisPointer: { z: 100 } },
        { type: 'category', gridIndex: 1, data: dates, boundaryGap: true,
          axisLabel: { show: false }, axisLine: { show: false },
          axisTick: { show: false }, splitLine: { show: false } },
        { type: 'category', gridIndex: 2, data: dates, boundaryGap: true,
          axisLabel: { show: false }, axisLine: { show: false },
          axisTick: { show: false }, splitLine: { show: false } }
      ],
      yAxis: [
        { scale: true, position: 'right',
          axisLabel: { fontSize: 10, color: '#6b7488' },
          splitLine: { lineStyle: { color: '#1f2533' } },
          axisLine: { lineStyle: { color: '#2a3247' } } },
        { gridIndex: 1, position: 'right', scale: true,
          axisLabel: { fontSize: 9, color: '#6b7488' },
          splitLine: { show: false }, axisLine: { show: false } },
        { gridIndex: 2, position: 'right', scale: true,
          axisLabel: { show: false }, splitLine: { show: false },
          axisLine: { show: false }, axisTick: { show: false } }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0,1,2], start: 0, end: 100,
          zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false }
      ],
      graphic: watermark,
      series: [
        { name: 'K线', type: 'candlestick', data: d.ohlc,
          barMaxWidth: 4, barMinWidth: 2,
          /* 阳线（红）空心：实体透明 + 红边；阴线（绿）实心 */
          itemStyle: { color: 'transparent', color0: C.down,
                       borderColor: C.up, borderColor0: C.down,
                       borderWidth: 1 },
          markLine: (dashLines.length || markData.length) ? {
            symbol: 'none', silent: true, clipOverflow: false,
            data: dashLines.concat(markData), animation: false
          } : undefined,
          markPoint: bsMarkPoint.data.length ? bsMarkPoint : undefined },

        { name: 'MA5',  type: 'line', data: ma5,  smooth: true, symbol: 'none',
          lineStyle: { width: 1, color: C.ma5 }, animation: false },
        { name: 'MA10', type: 'line', data: ma10, smooth: true, symbol: 'none',
          lineStyle: { width: 1, color: C.ma10 }, animation: false },
        { name: 'MA20', type: 'line', data: ma20, smooth: true, symbol: 'none',
          lineStyle: { width: 1, color: C.ma20 }, animation: false },
        { name: 'MA30', type: 'line', data: ma30, smooth: true, symbol: 'none',
          lineStyle: { width: 1, color: C.ma30 }, animation: false },

        { name: '量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: vol,
          barMaxWidth: 6, barMinWidth: 2,
          itemStyle: { color: function(p){
            var i = p.dataIndex, o = d.ohlc[i];
            return (o[1] >= o[0]) ? 'rgba(255,68,56,.95)' : 'rgba(22,199,132,.95)';
          } } },
        { name: 'VOL5', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: volMA5,
          symbol: 'none', smooth: true,
          lineStyle: { width: 1, color: C.ma5 }, animation: false },
        { name: 'VOL10', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: volMA10,
          symbol: 'none', smooth: true,
          lineStyle: { width: 1, color: C.ma10 }, animation: false },

        { name: '额', type: 'bar', xAxisIndex: 2, yAxisIndex: 2, data: amt,
          barMaxWidth: 6, barMinWidth: 2,
          itemStyle: { color: function(p){
            var i = p.dataIndex, o = d.ohlc[i];
            return (o[1] >= o[0]) ? 'rgba(255,68,56,.95)' : 'rgba(22,199,132,.95)';
          } } },
        { name: 'AMT5', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: amtMA5,
          symbol: 'none', smooth: true,
          lineStyle: { width: 1, color: C.ma5 }, animation: false },
        { name: 'AMT10', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: amtMA10,
          symbol: 'none', smooth: true,
          lineStyle: { width: 1, color: C.ma10 }, animation: false }
      ]
    }, true);

    var mainLow = Infinity, mainHi = -Infinity;
    for (var yi = 0; yi < n; yi++) {
      if (d.ohlc[yi][2] < mainLow) mainLow = d.ohlc[yi][2];
      if (d.ohlc[yi][3] > mainHi) mainHi = d.ohlc[yi][3];
    }
    var step = (mainHi - mainLow) / 4;
    var yLabels = [];
    for (var yj = 0; yj <= 3; yj++) {
      var v = mainLow + step * yj;
      yLabels.push({ type: 'text', silent: true,
        style: { text: fmt(v, v >= 100 ? 0 : 1), font: '10px -apple-system, sans-serif', fill: '#6b7488' },
        left: 4, top: 'calc(2% + ' + (yj * 12.5) + '%)' });
    }
    chart.setOption({ graphic: [watermark].concat(
      yLabels.map(function(g){ return { type: 'group', silent: true, children: [g] }; })
    ) }, { replaceMerge: ['graphic'] });

    renderSubHdrs(d);

    show('kToolbar');
    show('kFav');
    var yaxEl = $('kToolYax');
    if (yaxEl) yaxEl.textContent = fmt(mainLow);
    var kf = $('kFav');
    if (kf) {
      kf.style.position = 'absolute';
      kf.style.right = '12px';
      kf.style.bottom = '16px';
    }
    function getZoom() {
      var z = chart.getOption().dataZoom[0]; return { s: z.start, e: z.end };
    }
    function setZoom(s, e) {
      chart.dispatchAction({ type: 'dataZoom', start: s, end: e });
    }
    function bind(id, fn) { var b = $(id); if (b) b.onclick = fn; }
    bind('kZoomIn',     function(){ var c = getZoom(); var span = c.e - c.s; setZoom(c.s + span * 0.1, c.e - span * 0.1); });
    bind('kZoomOut',    function(){ var c = getZoom(); var span = c.e - c.s; setZoom(Math.max(0, c.s - span * 0.1), Math.min(100, c.e + span * 0.1)); });
    bind('kZoomLeft',   function(){ var c = getZoom(); var span = c.e - c.s; setZoom(c.s - span * 0.1, c.e - span * 0.1); });
    bind('kZoomRight',  function(){ var c = getZoom(); var span = c.e - c.s; setZoom(c.s + span * 0.1, c.e + span * 0.1); });
    bind('kZoomReset',  function(){ setZoom(0, 100); });

    setTimeout(function(){
      if (chart) chart.resize();
      if (waveChart) waveChart.resize();
    }, 50);

    /* === 点击 K 线 → 左上角信息卡 + 主图黄色高亮竖线 === */
    try { chart && chart.off && chart.off('click'); } catch(e){}
    chart.on('click', function(p){
      if (p && p.componentType === 'series' && p.seriesType === 'candlestick') {
        showClickInfo(p.dataIndex);
        var ix = p.dataIndex;
        var extra = dashLines.concat(markData);  // 保留 avg 区间线 + 入选日标记（点击高亮不丢）
        try {
          chart.setOption({
            series: [{ name: 'K线', markLine: {
              symbol: 'none', silent: true, animation: false,
              data: [{ xAxis: ix, lineStyle: { color: '#fbbf24', type: 'solid', width: 1, opacity: 0.85 },
                       label: { show: false } }].concat(extra)
            }}]
          }, { replaceMerge: ['series'] });
        } catch(e){}
      }
    });
  }

  function maArrSeries(arr, m) {
    if (!arr) return [];
    var out = [];
    var s = 0;
    for (var i = 0; i < arr.length; i++) {
      s += arr[i] || 0;
      if (i >= m) s -= arr[i - m] || 0;
      out.push(i >= m - 1 ? s / m : null);
    }
    return out;
  }

  /* ============ 分时 ============ */
  function renderMinute(d) {
    clearLoading();
    var el = $('klineChart');
    el.innerHTML = '<div class="k-toolbar" id="kToolbar" style="display:none">' +
                     '<span class="yaxis" id="kToolYax">—</span>' +
                     '<div class="ctrls">' +
                       '<button class="btn" id="kZoomIn" aria-label="放大">+</button>' +
                       '<button class="btn" id="kZoomOut" aria-label="缩小">−</button>' +
                       '<button class="btn" id="kZoomLeft" aria-label="左移">‹</button>' +
                       '<button class="btn" id="kZoomRight" aria-label="右移">›</button>' +
                       '<button class="btn" id="kZoomReset" aria-label="重置">⤢</button>' +
                     '</div>' +
                     '<span class="fav" id="kFav" style="display:none">加自选</span>' +
                   '</div>' +
                   '<div class="k-chart" id="kChartInner"></div>';
    chart = echarts.init($('kChartInner'));

    var prices = d.prices, n = prices.length;
    var prev = d.prev_close || prices[0];
    var last = prices[n - 1];
    var hi = Math.max.apply(null, prices), lo = Math.min.apply(null, prices);
    var avg = d.avg, vols = d.vols;

    var maxAbsPct = 0;
    for (var k = 0; k < n; k++) {
      var pc = Math.abs((prices[k] - prev) / prev * 100);
      if (pc > maxAbsPct) maxAbsPct = pc;
    }
    var limit = Math.max(maxAbsPct * 1.05, 1);

    chart.setOption({
      animation: false,
      backgroundColor: 'transparent',
      textStyle: { color: '#d9dee8', fontSize: 11 },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'cross', link: [{xAxisIndex: 'all'}] },
        backgroundColor: 'rgba(20,25,40,.95)', borderColor: '#2a3247',
        textStyle: { color: '#e6e9f0', fontSize: 11 },
        formatter: function(params){
          var i = params[0].dataIndex;
          var p = prices[i], pct = (p - prev) / prev * 100;
          return '<b>' + (d.date || '') + ' ' + d.times[i] + '</b><br/>' +
                 '价:' + fmt(p) + ' (' + sign(pct.toFixed(2)) + '%)<br/>' +
                 '均:' + fmt(avg[i]) + '<br/>量:' + fmtVol(vols[i]) + '手';
        }
      },
      axisPointer: { link: [{xAxisIndex: 'all'}] },
      grid: [
        { left: 4, right: 6, top: 4,  height: '58%' },
        { left: 4, right: 6, top: '71%', height: '25%' }
      ],
      xAxis: [
        { type: 'category', data: d.times, boundaryGap: false,
          axisLabel: { fontSize: 10, color: '#6b7488', interval: 29 },
          axisLine: { lineStyle: { color: '#2a3247' } },
          splitLine: { show: false } },
        { type: 'category', gridIndex: 1, data: d.times, boundaryGap: true,
          axisLabel: { show: false }, axisLine: { show: false },
          axisTick: { show: false }, splitLine: { show: false } }
      ],
      yAxis: [
        { min: prev * (1 - limit / 100), max: prev * (1 + limit / 100),
          position: 'left',
          axisLabel: { fontSize: 10, color: '#6b7488',
                       formatter: function(v){ return v.toFixed(2); } },
          splitLine: { lineStyle: { color: '#1f2533' } },
          axisLine: { lineStyle: { color: '#2a3247' } } },
        { min: -limit, max: limit, position: 'right',
          axisLabel: { fontSize: 10, color: '#6b7488',
                       formatter: function(v){ return v.toFixed(2) + '%'; } },
          splitLine: { show: false }, axisLine: { show: false } },
        { gridIndex: 1, axisLabel: { show: false }, splitLine: { show: false },
          axisLine: { show: false }, axisTick: { show: false } }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0,1], start: 0, end: 100 }
      ],
      series: [
        { name: '价格', type: 'line', data: prices, symbol: 'none',
          lineStyle: { width: 1.4, color: '#5cc8ff' },
          areaStyle: { color: 'rgba(92,200,255,.10)' },
          markLine: { symbol: 'none', silent: true,
            lineStyle: { color: '#8b93a7', type: 'dashed', width: 1 },
            label: { formatter: '昨收 ' + fmt(prev), fontSize: 10,
                     color: '#8b93a7', position: 'insideEndTop' },
            data: [{ yAxis: prev }], animation: false } },
        { name: '均价', type: 'line', data: avg, symbol: 'none',
          lineStyle: { width: 1, color: C.ma10, type: 'dashed' } },
        { name: '分量', type: 'bar', xAxisIndex: 1, yAxisIndex: 2, data: vols,
          itemStyle: { color: function(p){
            var i = p.dataIndex, cp = prices[i], pp = i ? prices[i-1] : prev;
            return cp >= pp ? 'rgba(239,74,74,.6)' : 'rgba(27,181,91,.6)';
          } } }
      ]
    }, true);

    hide('kVolHdr'); hide('kAmtHdr');
    show('kToolbar');
    setTimeout(function(){ if (chart) chart.resize(); }, 50);
  }

  function hide(id) { var el = $(id); if (el) el.style.display = 'none'; }
  function show(id) { var el = $(id); if (el) el.style.display = ''; }

  /* ============ 周期 Tab ============ */
  $('kSegMode').addEventListener('click', function(e){
    var t = e.target.closest('div[data-m]');
    if (!t) return;
    $('kSegMode').querySelectorAll('div').forEach(function(x){ x.classList.remove('on'); });
    t.classList.add('on');
    state.mode = t.getAttribute('data-m');
    loadKline();
  });

  /* ============ resize ============ */
  window.addEventListener('resize', function(){
    if (chart) chart.resize();
    if (waveChart) waveChart.resize();
  });
  new ResizeObserver(function(){
    if (chart) chart.resize();
    if (waveChart) waveChart.resize();
  }).observe(document.getElementById('klineChart'));
  new ResizeObserver(function(){
    if (waveChart) waveChart.resize();
  }).observe(document.getElementById('kWaveChart'));
})();
</script>"""
