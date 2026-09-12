# -*- coding: utf-8 -*-
"""把统计结果渲染为单页 HTML 看板（ECharts + 原生 JS）。

输出前会自动做一次内联 JS 语法自检（node --check），避免括号失配导致整页图表空白。
"""
import datetime as dt
import glob
import json
import os
import shutil
import subprocess
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
OUT_DIR = os.path.join(HERE, "output")
ECHARTS_JS_PATH = os.path.join(OUT_DIR, "echarts.min.js")

TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>上升途中 · 板块统计看板 __DATE__</title>
__ECHARTS_LIB__
<style>
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html { -webkit-text-size-adjust: 100%; }
  body { margin:0; padding:24px; background:#f5f6f8; color:#1c1e21;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif;
         font-size:14px; line-height:1.6; }
  .wrap { max-width:1240px; margin:0 auto; }
  h1 { font-size:22px; margin:0 0 6px; font-weight:600; }
  .sub { color:#6b7280; font-size:13px; margin-bottom:20px; }
  .card { background:#fff; border:1px solid #e5e7eb; border-radius:10px;
          padding:18px 20px; margin-bottom:16px; }
  .cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px;
           margin-bottom:16px; }
  .kpi { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:14px 16px; }
  .kpi .v { font-size:26px; font-weight:600; color:#c0392b; line-height:1.2; }
  .kpi .l { font-size:12px; color:#6b7280; margin-top:2px; }
  .concl { background:#fff8f7; border:1px solid #f3c9c2; border-radius:10px;
           padding:16px 20px; margin-bottom:16px; }
  .concl b { color:#c0392b; }
  .concl ul { margin:8px 0 0; padding-left:20px; }
  .concl li { margin:4px 0; }
  .ctrl { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-bottom:14px; }
  .seg { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .tab { padding:7px 14px; border:1px solid #d1d5db; background:#fff; border-radius:7px;
         cursor:pointer; font-size:13px; color:#374151; white-space:nowrap; }
  .tab.on { background:#c0392b; border-color:#c0392b; color:#fff; }
  /* 顶层分屏 tab（概览 / 板块 / 剔除），移动端 sticky 常驻顶部 */
  .toptabs { position:sticky; top:0; z-index:20; display:flex; gap:8px;
             background:#f5f6f8; padding:10px 0; margin-bottom:10px; }
  .toptabs .ttab { flex:1; text-align:center; padding:10px 0; border-radius:9px;
             background:#fff; border:1px solid #e5e7eb; font-size:14px; font-weight:500;
             color:#374151; cursor:pointer; white-space:nowrap; }
  .toptabs .ttab.on { background:#c0392b; border-color:#c0392b; color:#fff; }
  .diffcard.dhidden { display:none; }
  .diffmore { display:inline-block; margin-top:10px; font-size:12px; color:#c0392b;
             background:#fff; border:1px solid #f0c4bd; padding:6px 14px; border-radius:6px; cursor:pointer; }
  .diffmore:active { background:#fff5f3; }

  .spacer { flex:1; }
  .chk { font-size:13px; color:#374151; display:flex; align-items:center; gap:6px; cursor:pointer; }
  .hint { font-size:12px; color:#9ca3af; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th { text-align:left; padding:9px 10px; border-bottom:2px solid #e5e7eb;
       color:#6b7280; font-weight:600; font-size:12px; white-space:nowrap; }
  td { padding:9px 10px; border-bottom:1px solid #f1f2f4; }
  tr.row:hover { background:#fafafa; cursor:pointer; }
  .num { text-align:right; font-variant-numeric:tabular-nums; }
  .rk { color:#9ca3af; width:38px; }
  .nm { font-weight:500; white-space:nowrap; }
  .bar { height:6px; background:#f1f2f4; border-radius:3px; overflow:hidden; min-width:70px; }
  .bar i { display:block; height:100%; background:#c0392b; }
  .ratio { font-weight:600; }
  .r-hi { color:#c0392b; } .r-mid { color:#e08a1e; } .r-lo { color:#9ca3af; }
  .st { display:inline-block; font-size:11px; padding:1px 5px; border-radius:4px;
        background:#fef3c7; color:#92400e; margin-left:6px; }
  /* === 今日新进入 / 板块展开 · 卡片化（两行：上行主信息，下行概念） === */
  .diffcards { display:flex; flex-direction:column; gap:2px; }
  .diffcard {
    display:flex; flex-direction:column; gap:5px;
    padding:8px 10px; border:1px solid #eef0f3; border-radius:8px;
    background:#fff; cursor:pointer; transition:background .12s;
  }
  .diffcard:hover { background:#fafbfc; }
  .diffcard .dmain { display:flex; align-items:flex-start; gap:8px; flex-wrap:nowrap; }
  .diffcard .dleft { display:flex; flex-direction:column; flex:0 0 auto; min-width:0; }
  .diffcard .dname { font-weight:600; font-size:13px; color:#1f2937; display:flex; align-items:center; gap:4px; white-space:nowrap; overflow:hidden; }
  .diffcard .dname .st { flex:0 0 auto; }
  .diffcard .dcode { font-size:11px; color:#9ca3af; margin-top:1px; font-variant-numeric:tabular-nums; white-space:nowrap; }
  .diffcard .dprice { font-weight:700; font-size:13px; color:#1f2937; min-width:62px; text-align:right; font-variant-numeric:tabular-nums; }
  /* 题材：位于「涨幅」与「成交额」之间，小字固定两行 + 限宽，避免挤动价格/涨幅位置 */
  .diffcard .dconcepts { flex:1 1 auto; min-width:0;
    display:flex; align-items:flex-start; gap:3px; }
  .diffcard .dconcepts .ctext {
    flex:1 1 auto; min-width:0;
    font-size:10.5px; line-height:1.35; color:#475569;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  }
  .diffcard .dconcepts .ctext .chip { display:inline; color:#475569; }
  .diffcard .dconcepts .empty { color:#cbd5e1; font-size:10.5px; }
  .diffcard .dconcepts .chip.extra { display:none; }
  .diffcard.expanded .dconcepts .chip.extra { display:inline; }
  .diffcard.expanded .dconcepts .ctext { display:block; -webkit-line-clamp:unset; overflow:visible; }
  .diffcard .dmore {
    background:#fff; border:1px solid #d1d5db; color:#374151;
    font-size:11px; padding:2px 8px; border-radius:4px; cursor:pointer;
    white-space:nowrap; line-height:1.4; margin-left:2px;
  }
  .diffcard .dmore:active { background:#f1f5f9; }
  .diffcard .drate { font-weight:700; font-size:12.5px; min-width:58px; text-align:right; font-variant-numeric:tabular-nums; }
  .diffcard .drate.up   { color:#c0392b; }
  .diffcard .drate.down { color:#16a34a; }
  .diffcard .drate.flat { color:#9ca3af; }
  .diffcard .damt { font-size:11.5px; color:#6b7280; min-width:58px; text-align:right; font-variant-numeric:tabular-nums; }
  /* 序号：定宽右对齐，避免位数不同（1位/3位）导致名称起始位置参差 */
  .diffcard .drank { flex:0 0 auto; width:20px; min-width:20px; font-size:10px;
                    color:#b0b8c4; text-align:right; font-variant-numeric:tabular-nums; }
  .up { color:#c0392b; } .down { color:#16a34a; }
  .det td { background:#fafbfc; padding:4px 6px 8px 6px; color:#4b5563; font-size:12px; }
  .det .chip { display:inline-block; border:1px solid #e5e7eb; border-radius:5px;
               padding:2px 7px; margin:3px 5px 3px 0; background:#fff;
               cursor:pointer; transition: all .12s; }
  .det .chip:hover { background:#fff5f3; border-color:#c0392b; }
  .noise td { color:#9ca3af; }
  .foot { color:#9ca3af; font-size:12px; line-height:1.8; padding:6px 4px 20px; }
  .warn { color:#92400e; font-size:12px; background:#fffbeb; border:1px solid #fde68a;
          padding:8px 12px; border-radius:7px; margin-top:10px; }
  .chart-status { position:absolute; inset:0; display:flex; align-items:center;
                  justify-content:center; color:#9ca3af; font-size:13px;
                  background:repeating-linear-gradient(45deg,#fafbfc,#fafbfc 8px,#f5f6f8 8px,#f5f6f8 16px); }
  .chart-status.hidden { display:none; }
  .chart-status.empty { background:#fafbfc; color:#6b7280; }
  #chart-wrap.tight #chart { min-height:120px; }
  /* ===== 移动端适配（iPhone / 窄屏 ≤600px） ===== */
  @media (max-width: 600px) {
    body { padding: 12px;
           padding-left: max(12px, env(safe-area-inset-left));
           padding-right: max(12px, env(safe-area-inset-right));
           padding-bottom: max(12px, env(safe-area-inset-bottom));
           font-size: 13px; }
    .wrap { max-width: 100%; }
    h1 { font-size: 19px; }
    .sub { font-size: 12px; margin-bottom: 14px; }
    .toptabs .ttab { font-size: 13px; padding: 10px 2px; }
    .card { padding: 12px; border-radius: 9px; }
    .cards { grid-template-columns: repeat(2, 1fr); gap: 8px; }
    .kpi { padding: 12px; }
    .kpi .v { font-size: 21px; }
    .kpi .l { font-size: 11px; }
    .concl { padding: 12px; }
    .concl li { font-size: 12px; }
    .ctrl { flex-direction: column; align-items: stretch; gap: 10px; }
    .seg { gap: 6px; flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch;
           padding-bottom: 4px; }
    .seg .tab { flex: 0 0 auto; font-size: 12px; padding: 8px 12px; }
    .chk { white-space: nowrap; font-size: 12px; flex: 0 0 auto; }
    .hint { font-size: 11px; }
    table { font-size: 12px; }
    th, td { padding: 5px 4px; }
    .rk { width: 30px; }
    .bar { min-width: 48px; }
    .scroll { overflow-x: auto; max-height: 540px; overflow-y: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; }
    .diffcard { padding:7px 8px; gap:6px; }
    .diffcard .dname { font-size:12px; }
    .diffcard .dcode { font-size:10px; }
    .diffcard .dprice { font-size:12px; min-width:52px; }
    .diffcard .dconcepts .ctext { font-size:10px; }
    .diffcard .dconcepts .chip { font-size:10px; padding:0; }
    .diffcard .drate { font-size:11.5px; min-width:50px; }
    .diffcard .damt { font-size:10.5px; min-width:48px; }
    /* 移动端也保留序号，但压到最窄，尽量不占名称空间 */
    .diffcard .drank { width:15px; min-width:15px; font-size:9px; color:#b8c0cb; }
  #diffTable thead th { position: sticky; top: -1px; background: #fff; z-index: 2; box-shadow: 0 1px 0 #e5e7eb; }
    #chart-wrap.tight #chart, #chart { min-height: 140px; }
  }
</style>
</head>
<body>
<div class="wrap">

  <div class="toptabs" id="toptabs">
    <div class="ttab on" data-t="overview">概览</div>
    <div class="ttab" data-t="new">今日新进入</div>
    <div class="ttab" data-t="boards">板块</div>
  </div>

  <div id="tab-overview" class="tpane">
  <h1>上升途中 · 板块统计看板</h1>
  <div class="sub">
    口径：同花顺问财「上升途中」（实际解析为技术形态 <b>上升通道</b>） ·
    数据时间 __DATETIME__<span id="liveTag" style="margin-left:8px;padding:1px 7px;border-radius:4px;background:#eef2ff;color:#4338ca;font-size:11px;font-weight:600;white-space:nowrap;">行情刷新中…</span>
  </div>

  <div class="cards">
    <div class="kpi"><div class="v" id="k1">-</div><div class="l">上升途中股票数</div></div>
    <div class="kpi"><div class="v" id="k2" style="color:#e08a1e">-</div><div class="l">其中 ST 股</div></div>
    <div class="kpi"><div class="v" id="k3" style="color:#374151">-</div><div class="l">涉及一级行业</div></div>
    <div class="kpi"><div class="v" id="k4" style="color:#374151">-</div><div class="l">涉及概念题材</div></div>
    <div class="kpi"><div class="v" id="k5" style="color:#c0392b">-</div><div class="l">今日新进入</div></div>
  </div>

  <div class="concl" id="concl"></div>

  <div class="card">
    <div style="font-weight:600;margin-bottom:6px;">已剔除的无区分度标签</div>
    <div class="hint" style="margin-bottom:10px;">
      以下属于交易通道 / 指数成分 / 风格估值 / 持仓属性类标签，几乎覆盖大量个股，
      计入会掩盖真实题材，故不进入概念榜。
    </div>
    <div class="scroll"><table>
      <thead><tr><th class="rk">#</th><th>标签</th><th class="num">命中数</th><th>性质</th></tr></thead>
      <tbody id="nbody"></tbody>
    </table></div>
  </div>
  </div><!-- /tab-overview -->

  <div id="tab-new" class="tpane" style="display:none">
  <div class="card" id="diffCard">
    <div style="font-weight:600;margin-bottom:4px;">今日新进入「上升通道」</div>
    <div class="hint" id="diffHint"></div>
    <div class="diffcards" id="diffbody" style="margin-top:4px;"></div>
    <div id="diffMore"></div>
  </div>
  </div><!-- /tab-new -->

  <div id="tab-boards" class="tpane" style="display:none">

  <div class="card">
  <div class="ctrl">
    <div class="seg" id="segBoard">
      <div class="tab on" data-b="industry_l1">一级行业</div>
      <div class="tab" data-b="industry_l2">二级行业</div>
      <div class="tab" data-b="industry_l3">三级行业</div>
      <div class="tab" data-b="concept">概念题材</div>
    </div>
    <div class="seg" id="segSort">
      <div class="tab on" data-s="hit">按命中数</div>
      <div class="tab" data-s="ratio">按渗透率</div>
      <label class="chk"><input type="checkbox" id="exst"> 剔除 ST 股</label>
    </div>
  </div>

  <div class="card" style="padding:10px 12px;">
    <div style="display:flex;gap:8px;align-items:center;">
      <input id="kSearch" type="text" inputmode="numeric"
        placeholder="输入代码 / 名称 / 拼音首字母查 K 线"
        style="flex:1;padding:9px 11px;border:1px solid #d1d5db;border-radius:7px;font-size:13px;outline:none;">
      <button id="kSearchBtn" type="button"
        style="background:#c0392b;color:#fff;border:0;padding:9px 14px;border-radius:7px;font-size:13px;font-weight:500;cursor:pointer;flex-shrink:0;">看 K 线</button>
    </div>
    <div id="kSearchHint" style="font-size:11px;color:#9ca3af;margin-top:6px;min-height:14px;"></div>
  </div>
  </div>

  <div class="card">
    <div class="scroll"><table>
      <thead><tr>
        <th class="rk">#</th><th>板块</th><th class="num">命中数</th>
        <th class="num">总股数</th>
        <th class="num">渗透率</th><th style="width:80px">命中强度</th>
      </tr></thead>
      <tbody id="tbody"></tbody>
    </table></div>
  </div>

  <div class="card">
    <div class="hint">渗透率 = 该板块内处于「上升途中」的股票数 ÷ 该板块全市场股票总数。点击任意行可展开命中个股。</div>
    <div id="chart-wrap" style="position:relative;margin-top:10px;">
      <div id="chart" style="width:100%;height:auto;min-height:160px;max-height:520px;"></div>
      <div id="chart-status" class="chart-status">图表初始化中…</div>
    </div>
  </div>
  </div><!-- /tab-boards -->

  <div class="foot">
    数据来源：__SOURCE__ ｜ 查询语句：<code>__QUERY__</code> ｜ 数据时间：__DATETIME__<br>
    口径说明：「上升途中」为技术形态判定，不代表当日上涨；入选个股当日可能为下跌。
    渗透率分母取自问财该板块的全市场成分股数，与分子为同一数据源口径。<br>
    __DISCLAIMER__
  </div>
</div>

__KLINE_MODAL__
__ECHARTS_BOOT__

<script>
var DATA = __DATA__;
__DATA_UNPACK__
var state = { board: 'industry_l1', sortBy: 'hit', exst: false, open: {} };
var chart = null;

function pct(v) { return v === null || v === undefined ? '—' : (v * 100).toFixed(1) + '%'; }

/* HTML 属性转义：行业/概念/形态里可能含引号，直接拼进属性会截断标签 */
function escAttr(v) {
  return String(v === null || v === undefined ? '' : v)
    .replace(/&/g, '&amp;').replace(/"/g, '&quot;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function fmtPrice(v) {
  if (v === null || v === undefined) return '—';
  return Number(v).toFixed(2);
}
function fmtAmt(v) {
  if (v == null) return '—';
  if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
  if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
  return Math.round(v) + '';
}
function escHtml(s) {
  return String(s).replace(/[&<>"']/g, function (c) {
    return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
  });
}

function getRows() {
  var raw = DATA.boards[state.board] || [];
  var rows = [];
  for (var i = 0; i < raw.length; i++) {
    var b = raw[i];
    var st = b.stocks || [];
    if (state.exst) {
      st = st.filter(function (s) { return !s.is_st; });
    }
    if (st.length === 0) continue;
    var total = b.total || 0;
    rows.push({
      name: b.name, hit: st.length, total: total,
      ratio: total ? st.length / total : null, stocks: st
    });
  }
  if (state.sortBy === 'hit') {
    rows.sort(function (a, b) { return b.hit - a.hit || a.name.localeCompare(b.name); });
  } else {
    rows.sort(function (a, b) {
      var ra = a.ratio === null ? -1 : a.ratio;
      var rb = b.ratio === null ? -1 : b.ratio;
      return rb - ra || b.hit - a.hit;
    });
  }
  return rows;
}

function ratioCls(r) {
  if (r === null) return 'r-lo';
  if (r >= 0.15) return 'r-hi';
  if (r >= 0.05) return 'r-mid';
  return 'r-lo';
}

function setStatus(text, kind) {
  var s = document.getElementById('chart-status');
  s.textContent = text;
  s.classList.remove('hidden', 'empty');
  if (kind === 'hidden') s.classList.add('hidden');
  if (kind === 'empty') s.classList.add('empty');
}

function renderChart(rows) {
  var wrap = document.getElementById('chart-wrap');
  var chartEl = document.getElementById('chart');
  if (!rows.length) {
    if (chart) { chart.dispose(); chart = null; }
    wrap.classList.add('tight');
    chartEl.style.height = '120px';
    setStatus('当前筛选条件下无可绘制数据', 'empty');
    return;
  }
  wrap.classList.remove('tight');
  var isSmall = (window.innerWidth || document.documentElement.clientWidth || 430) <= 600;
  var top = rows.slice(0, isSmall ? 8 : 15);
  var topN = top.length;
  // ratio 字段缺失或非有限数都规整成 null（line series 才能安全断开）
  var ratios = top.map(function (r) {
    var x = r.ratio;
    return (x === null || x === undefined || !isFinite(x)) ? null : x;
  });
  // 若当前榜单无任何渗透率数据，禁用渗透率系列与右轴，避免 ECharts 报错
  var hasRatio = ratios.some(function (x) { return x !== null; });
  var names = top.map(function (r) { return r.name; });
  var hits = top.map(function (r) { return r.hit; });

  var opt;
  if (isSmall) {
    // ===== 移动端：竖向柱状图（类别在 X 轴，命中数在 Y 轴） =====
    // 横向柱状图在窄屏上双轴布局（'50%' 给右轴）会把柱子挤成细线；切换为竖向更自然。
    var hM = Math.max(195, Math.min(315, topN * 27 + 60));  // 高度减半
    chartEl.style.height = hM + 'px';
    opt = {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, confine: true },
      legend: {
        data: hasRatio ? ['命中数', '渗透率'] : ['命中数'],
        top: 4, left: 8, textStyle: { fontSize: 11 }
      },
      grid: { left: 36, right: hasRatio ? 42 : 14, top: 36, bottom: 64 },
      xAxis: {
        type: 'category', data: names,
        axisLabel: { interval: 0, rotate: 30, fontSize: 10, color: '#6b7280' },
        axisLine: { lineStyle: { color: '#d1d5db' } },
        axisTick: { show: false }
      },
      yAxis: hasRatio ? [
        { type: 'value', name: '命中数', minInterval: 1,
          axisLabel: { fontSize: 10, color: '#6b7280' },
          splitLine: { lineStyle: { color: '#f1f2f4' } },
          nameTextStyle: { fontSize: 10, color: '#6b7280' } },
        { type: 'value', max: 1, position: 'right',
          axisLabel: { fontSize: 10, color: '#6b7280',
            formatter: function (v) { return (v * 100).toFixed(0) + '%'; } },
          splitLine: { show: false }, axisLine: { show: false },
          nameTextStyle: { fontSize: 10, color: '#6b7280' } }
      ] : [
        { type: 'value', name: '命中数', minInterval: 1,
          axisLabel: { fontSize: 10, color: '#6b7280' },
          splitLine: { lineStyle: { color: '#f1f2f4' } },
          nameTextStyle: { fontSize: 10, color: '#6b7280' } }
      ],
      series: [
        { name: '命中数', type: 'bar', data: hits, barMaxWidth: 28,
          itemStyle: { color: '#c0392b' } }
      ].concat(hasRatio ? [
        { name: '渗透率', type: 'line', yAxisIndex: 1, data: ratios,
          symbolSize: 6, lineStyle: { color: '#e08a1e', type: 'dashed', width: 1.5 },
          itemStyle: { color: '#e08a1e' }, connectNulls: false }
      ] : [])
    };
  } else {
    // ===== 桌面端：横向柱状图（命中数）+ 渗透率折线（双轴） =====
    top.reverse();
    var hD = Math.max(165, Math.min(390, topN * 21 + 52));  // 高度减半
    chartEl.style.height = hD + 'px';
    var xAxis = [
      { type: 'value', name: '命中数', minInterval: 1, position: 'bottom' }
    ];
    var yAxis = [
      { type: 'category', data: names, axisLabel: { fontSize: 12 } }
    ];
    var series = [
      { name: '命中数', type: 'bar', data: hits, barMaxWidth: 16,
        itemStyle: { color: '#c0392b' } }
    ];
    var legend = ['命中数'];
    if (hasRatio) {
      yAxis.push({ type: 'value', max: 1, position: 'right',
        axisLabel: { formatter: function (v) { return (v * 100).toFixed(0) + '%'; } },
        splitLine: { show: false } });
      xAxis.push({ type: 'value', max: 1, show: false });
      series.push({ name: '渗透率', type: 'line', xAxisIndex: 1, yAxisIndex: 1,
        data: ratios, symbolSize: 7,
        lineStyle: { color: '#e08a1e', type: 'dashed' },
        itemStyle: { color: '#e08a1e' }, connectNulls: false });
      legend.push('渗透率');
    }
    opt = {
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      legend: { data: legend, top: 0 },
      grid: hasRatio
        ? [
            { left: 110, right: '52%', top: 34, bottom: 30, containLabel: true },
            { left: '52%', right: 24, top: 34, bottom: 30, containLabel: true }
          ]
        : { left: 110, right: 24, top: 34, bottom: 30, containLabel: true },
      xAxis: xAxis,
      yAxis: yAxis,
      series: series
    };
  }
  try {
    if (!chart) { chart = echarts.init(chartEl); }
    chart.setOption(opt, true);
    chart.resize();
    setStatus('', 'hidden');
  } catch (e) {
    var stack = (e && e.stack) ? String(e.stack).split('\\n').slice(0, 4).join(' | ') : '';
    setStatus('图表渲染失败：' + (e && e.message ? e.message : e) + (stack ? ' || ' + stack : ''), 'empty');
  }
}

function renderTable(rows) {
  var maxHit = 1;
  for (var i = 0; i < rows.length; i++) { if (rows[i].hit > maxHit) maxHit = rows[i].hit; }
  var html = '';
  for (var j = 0; j < rows.length; j++) {
    var r = rows[j];
    var w = Math.round(r.hit / maxHit * 100);
    var key = state.board + '|' + r.name;
    var isOpen = !!state.open[key];
    html += '<tr class="row" data-k="' + key + '">' +
      '<td class="rk">' + (j + 1) + '</td>' +
      '<td class="nm">' + r.name + '</td>' +
      '<td class="num">' + r.hit + '</td>' +
      '<td class="num">' + (r.total || '—') + '</td>' +
      '<td class="num ratio ' + ratioCls(r.ratio) + '">' + pct(r.ratio) + '</td>' +
      '<td><div class="bar"><i style="width:' + w + '%"></i></div></td>' +
      '</tr>';
    if (isOpen) {
      var cards = '';
      var slist = r.stocks.slice().sort(function (a, b) { return (b.amount || 0) - (a.amount || 0); });
      for (var k = 0; k < slist.length; k++) {
        var s = slist[k];
        var cls = (s.chg === null || s.chg === undefined) ? 'flat' : (s.chg >= 0 ? 'up' : 'down');
        var chg = (s.chg === null || s.chg === undefined) ? '—' : (s.chg >= 0 ? '+' : '') + s.chg.toFixed(2) + '%';
        var consSrc = (s.concepts && s.concepts.length) ? s.concepts
          : String(s.industry || '').split(/[，,、/\\-]+/).filter(Boolean);
        var allCons = consSrc.slice(0, 8);
        var shown = allCons.slice(0, 3);
        var extra = allCons.slice(3);
        var consHtml = '';
        var moreBtn = '';
        var ci;
        for (ci = 0; ci < shown.length; ci++) { if (ci) consHtml += '; '; consHtml += '<span class="chip">' + escHtml(shown[ci]) + '</span>'; }
        if (extra.length) {
          for (ci = 0; ci < extra.length; ci++) { if (ci) consHtml += '; '; consHtml += '<span class="chip extra">' + escHtml(extra[ci]) + '</span>'; }
          moreBtn = '<button type="button" class="dmore">详情›</button>';
        } else if (!allCons.length) {
          consHtml = '<span class="empty">—</span>';
        }
        var stTag = s.is_st ? '<span class="st">ST</span>' : '';
        cards += '<div class="diffcard kline-trigger" data-code="' + s.code + '"' +
          ' data-ind="' + escAttr(s.ind_l1 || '') + '"' +
          ' data-con="' + escAttr((consSrc || []).join(',')) + '"' +
          ' data-pat="' + escAttr(s.tech_pattern || '') + '"' +
          ' data-sig="' + escAttr(s.buy_signal || '') + '"' +
          ' data-st="' + (s.is_st ? '1' : '0') + '">' +
          '<div class="dmain">' +
            '<span class="drank">' + (k + 1) + '</span>' +
            '<div class="dleft">' +
              '<div class="dname">' + escHtml(s.name) + '</div>' +
              '<div class="dcode">' + s.code + '</div>' +
            '</div>' +
            '<div class="dprice">' + fmtPrice(s.price) + '</div>' +
            '<div class="drate ' + cls + '">' + chg + '</div>' +
            '<div class="dconcepts"><span class="ctext">' + consHtml + '</span>' + moreBtn + '</div>' +
            '<div class="damt">' + fmtAmt(s.amount) + '</div>' +
          '</div>' +
          '</div>';
      }
      html += '<tr class="det"><td colspan="6"><div class="diffcards">' + cards + '</div></td></tr>';
    }
  }
  document.getElementById('tbody').innerHTML = html;
  var trs = document.querySelectorAll('tr.row');
  for (var m = 0; m < trs.length; m++) {
    trs[m].onclick = function () {
      var k = this.getAttribute('data-k');
      if (state.open[k]) { delete state.open[k]; } else { state.open[k] = 1; }
      render();
    };
  }
}

function renderNoise() {
  var n = DATA.noise || [];
  var html = '';
  for (var i = 0; i < n.length; i++) {
    html += '<tr class="noise"><td class="rk">' + (i + 1) + '</td><td>' + n[i].name +
      '</td><td class="num">' + n[i].hit + '</td><td>属性/通道类</td></tr>';
  }
  document.getElementById('nbody').innerHTML = html;
}

function renderConclusion() {
  var rows = getRows();
  var withRatio = rows.filter(function (r) { return r.ratio !== null && r.total >= 10; });
  withRatio.sort(function (a, b) { return b.ratio - a.ratio; });
  var top = withRatio.slice(0, 10);
  var lis = top.map(function (r) {
    var clean = r.stocks.filter(function (s) { return !s.is_st; }).length;
    return '<li><b>' + r.name + '</b>：命中 ' + r.hit + ' 只 / 全市场 ' + r.total +
      ' 只，渗透率 <b>' + pct(r.ratio) + '</b>' +
      (r.stocks.length !== clean ? '（其中 ST ' + (r.stocks.length - clean) + ' 只）' : '') + '</li>';
  }).join('');
  var topHit = rows.slice(0, 3).map(function (r) { return r.name + '(' + r.hit + '只)'; }).join('、');
  document.getElementById('concl').innerHTML =
    '<div>本榜按<b>渗透率</b>排序更能反映板块真实启动强度 —— 命中数第一的往往是成分股多的大板块，而非真热点。</div>' +
    '<ul>' + lis + '</ul>' +
    '<div style="margin-top:8px;font-size:12px;color:#92400e;">参考：按命中数排序的前三为 ' + topHit +
    '，但大板块渗透率通常偏低，需结合渗透率一起看。</div>';
}

function renderDiff() {
  var d = DATA.diff;
  var hint = document.getElementById('diffHint');
  var body = document.getElementById('diffbody');
  if (!d || !d.has_baseline) {
    hint.innerHTML = '首次统计，暂无上一交易日对比基准；下一交易日运行后将自动出现。';
    body.innerHTML = '';
    return;
  }
  hint.innerHTML = '对比上一交易日 <b>' + d.prev_date + '</b>：今日新进入 ' +
    '<b style="color:#c0392b">' + d.new_count + '</b> 只，退出 ' +
    '<b style="color:#16a34a">' + d.exited_count + '</b> 只。';
  var rows = (d.new || []).slice();
  rows.sort(function (a, b) { return (b.amount || 0) - (a.amount || 0); });  // 按当日成交额从大到小
  if (!rows.length) {
    body.innerHTML = '<div style="color:#9ca3af;text-align:center;padding:14px;">今日无新进入个股</div>';
    return;
  }
  function fmtAmt(v) {
    if (v == null) return '—';
    if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
    return Math.round(v) + '';
  }
  function escHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c];
    });
  }
  var html = '';
  for (var i = 0; i < rows.length; i++) {
    var s = rows[i];
    var chg = (s.chg === null || s.chg === undefined) ? '—' : (s.chg >= 0 ? '+' : '') + s.chg.toFixed(2) + '%';
    var cls = (s.chg === null || s.chg === undefined) ? 'flat' : (s.chg >= 0 ? 'up' : 'down');
    var allCons = (s.concepts && s.concepts.length) ? s.concepts
      : String(s.industry || s.ind_l3 || s.ind_l2 || s.ind_l1 || '').split(/[，,、/\\-]+/).filter(Boolean);
    var MAXC = 3;
    var shown = allCons.slice(0, MAXC);
    var extra = allCons.slice(MAXC);
    var consHtml = '';
    var moreBtn = '';
    var ci;
    for (ci = 0; ci < shown.length; ci++) { if (ci) consHtml += '; '; consHtml += '<span class="chip">' + escHtml(shown[ci]) + '</span>'; }
    if (extra.length) {
      for (ci = 0; ci < extra.length; ci++) { if (ci) consHtml += '; '; consHtml += '<span class="chip extra">' + escHtml(extra[ci]) + '</span>'; }
      moreBtn = '<button type="button" class="dmore">详情›</button>';
    } else if (!allCons.length) {
      consHtml = '<span class="empty">—</span>';
    }
    var stTag = s.is_st ? '<span class="st">ST</span>' : '';
    html += '<div class="diffcard kline-trigger" data-code="' + s.code + '"' +
      ' data-ind="' + escAttr(s.ind_l1 || '') + '"' +
      ' data-con="' + escAttr((s.concepts || []).join(',')) + '"' +
      ' data-pat="' + escAttr(s.tech_pattern || '') + '"' +
      ' data-sig="' + escAttr(s.buy_signal || '') + '"' +
      ' data-st="' + (s.is_st ? '1' : '0') + '"' +
      '>' +
      '<div class="dmain">' +
        '<span class="drank">' + (i + 1) + '</span>' +
        '<div class="dleft">' +
          '<div class="dname">' + escHtml(s.name) + '</div>' +
          '<div class="dcode">' + s.code + '</div>' +
        '</div>' +
        '<div class="dprice">' + fmtPrice(s.price) + '</div>' +
        '<div class="drate ' + cls + '">' + chg + '</div>' +
        '<div class="dconcepts"><span class="ctext">' + consHtml + '</span>' + moreBtn + '</div>' +
        '<div class="damt">' + fmtAmt(s.amount) + '</div>' +
      '</div>' +
      '</div>';
  }
  body.innerHTML = html;
  /* 新进入：默认只显示前 N 只，提供「展开全部 / 收起」 */
  var _cards = body.querySelectorAll('.diffcard');
  var _total = _cards.length;
  var _DEF = 10;
  for (var _ci = 0; _ci < _total; _ci++) {
    _cards[_ci].classList.toggle('dhidden', _ci >= _DEF);
  }
  var _more = document.getElementById('diffMore');
  if (_total > _DEF) {
    _more.innerHTML = '<span class="diffmore" id="diffMoreBtn">展开全部 ' + _total + ' 只 ›</span>';
    var _btn = document.getElementById('diffMoreBtn');
    _btn.onclick = function () {
      var _next = body.getAttribute('data-expanded') !== '1';
      for (var _k = 0; _k < _total; _k++) {
        _cards[_k].classList.toggle('dhidden', !_next && _k >= _DEF);
      }
      body.setAttribute('data-expanded', _next ? '1' : '0');
      _btn.textContent = _next ? '收起 ‹' : ('展开全部 ' + _total + ' 只 ›');
    };
  } else {
    _more.innerHTML = '';
  }
}

function render() {
  var rows = getRows();
  renderChart(rows);
  renderTable(rows);
  document.getElementById('k1').textContent = DATA.pool.total;
  document.getElementById('k2').textContent = DATA.pool.st;
  document.getElementById('k3').textContent = DATA.coverage.ind_l1;
  document.getElementById('k4').textContent = DATA.coverage.concept_kept;
  document.getElementById('k5').textContent = (DATA.diff && DATA.diff.has_baseline) ? DATA.diff.new_count : '—';
  renderDiff();
}

var btns = document.querySelectorAll('.tab[data-b]');
for (var i = 0; i < btns.length; i++) {
  btns[i].onclick = function () {
    var b = this.getAttribute('data-b');
    var all = document.querySelectorAll('.tab[data-b]');
    for (var j = 0; j < all.length; j++) { all[j].classList.remove('on'); }
    this.classList.add('on');
    state.board = b;
    state.open = {};
    render();
  };
}
var sbtns = document.querySelectorAll('.tab[data-s]');
for (var s = 0; s < sbtns.length; s++) {
  sbtns[s].onclick = function () {
    var v = this.getAttribute('data-s');
    var all = document.querySelectorAll('.tab[data-s]');
    for (var t = 0; t < all.length; t++) { all[t].classList.remove('on'); }
    this.classList.add('on');
    state.sortBy = v;
    render();
  };
}
document.getElementById('exst').onchange = function () {
  state.exst = this.checked;
  state.open = {};
  render();
};

/* 顶层分屏 tab：概览 / 板块 / 剔除 */
var _ttabs = document.querySelectorAll('#toptabs .ttab');
for (var _ti = 0; _ti < _ttabs.length; _ti++) {
  _ttabs[_ti].onclick = function () {
    var t = this.getAttribute('data-t');
    var _all = document.querySelectorAll('#toptabs .ttab');
    for (var _j = 0; _j < _all.length; _j++) { _all[_j].classList.remove('on'); }
    this.classList.add('on');
    document.getElementById('tab-overview').style.display = (t === 'overview') ? '' : 'none';
    document.getElementById('tab-new').style.display = (t === 'new') ? '' : 'none';
    document.getElementById('tab-boards').style.display = (t === 'boards') ? '' : 'none';
    if (t === 'boards') { renderChart(getRows()); }  // 隐藏容器初始化后需重绘
  };
}

render();
renderNoise();
renderConclusion();

/* ===== 实时数据：打开页面即拉当下最新名单 ===== */
(function(){
  var SRC = window.UPTREND_BOARD || 'board.json';
  var el = document.createElement('div');
  el.id = 'rtStatus';
  el.style.cssText = 'position:fixed;right:10px;bottom:10px;z-index:9999;padding:6px 10px;' +
    'border-radius:999px;font-size:12px;line-height:1.2;color:#fff;' +
    'background:rgba(0,0,0,.55);box-shadow:0 2px 8px rgba(0,0,0,.25);' +
    'pointer-events:none;transition:opacity .3s,background .3s;max-width:70vw';
  document.body.appendChild(el);
  function set(txt, bg){ if(!el) return; el.textContent = txt; if(bg) el.style.background = bg; }

  set('正在获取最新名单…', 'rgba(0,0,0,.55)');
  var slow = setTimeout(function(){ set('实时数据较慢，先显示快照', 'rgba(180,120,0,.9)'); }, 8000);

  fetch(SRC, { cache: 'no-store' })
    .then(function(r){
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    })
    .then(function(d){
      if (!d || !d.boards || !d.pool) throw new Error('数据格式异常');
      clearTimeout(slow);
      window.DATA = d;
      try {
        render();
        renderNoise();
        renderConclusion();
        var t = String(d.generated_at || '').slice(11, 16);
        set('实时 · ' + (t || '刚刚') + ' · ' + d.pool.total + ' 只', 'rgba(0,140,70,.92)');
        setTimeout(function(){ if (el && el.style) el.style.opacity = '0.35'; }, 4000);
      } catch (e) {
        location.reload();  // 结构变化导致渲染异常时，重载用新数据重跑
      }
    })
    .catch(function(e){
      clearTimeout(slow);
      set('实时失败，显示 ' + (DATA.date || '') + ' 快照', 'rgba(170,40,40,.92)');
      setTimeout(function(){ if (el && el.style) el.style.opacity = '0.4'; }, 3000);
    });
})();


// ===== K 线触发：事件委托（chip / diffrow）=====
document.addEventListener('click', function(e){
  if (e.target.closest && e.target.closest('.dmore')) return;  // 详情按钮不触发 K 线
  var el = e.target.closest && e.target.closest('.kline-trigger');
  if (el && el.getAttribute('data-code')) {
    e.stopPropagation();
    openKline(el.getAttribute('data-code'));
  }
});

// ===== 详情按钮：展开/收起概念（事件委托，覆盖新进入与板块展开两类卡片）=====
document.addEventListener('click', function(e){
  var btn = e.target.closest && e.target.closest('.dmore');
  if (!btn) return;
  e.stopPropagation();
  var card = btn.closest('.diffcard');
  if (!card) return;
  var on = card.classList.toggle('expanded');
  btn.textContent = on ? '收起‹' : '详情›';
});

// ===== 搜索框：脱离股票池也能查任意股票 =====
(function(){
  function getPool(){ return (DATA.pool && DATA.pool.stocks) || []; }
  // 常用汉字 → 拼音首字母（覆盖 A 股常见字）
  var PY = {"长":"C","创":"C","超":"C","成":"C","重":"C","传":"C","城":"C","川":"C","驰":"C","春":"C","楚":"C","辰":"C","崇":"C","淳":"C","慈":"C","赐":"C",
            "东":"D","大":"D","电":"D","地":"D","德":"D","道":"D","达":"D","多":"D","迪":"D","典":"D","鼎":"D","都":"D","端":"D","敦":"D",
            "中":"Z","周":"Z","振":"Z","浙":"Z","之":"Z","正":"Z","珠":"Z","智":"Z","纵":"Z","众":"Z","招":"Z","找":"Z","照":"Z","折":"Z","哲":"Z","者":"Z","这":"Z","针":"Z","珍":"Z","真":"Z","诊":"Z","阵":"Z","振":"Z","镇":"Z","震":"Z","争":"Z","征":"Z","蒸":"Z","整":"Z","证":"Z","郑":"Z","政":"Z","症":"Z","芝":"Z","枝":"Z","知":"Z","织":"Z","指":"Z","止":"Z","纸":"Z","志":"Z","至":"Z","制":"Z","治":"Z","质":"Z","致":"Z","秩":"Z","掷":"Z","置":"Z","忠":"Z","终":"Z","钟":"Z","种":"Z","州":"Z","舟":"Z","洲":"Z","轴":"Z","昼":"Z","诸":"Z","猪":"Z","竹":"Z","逐":"Z","主":"Z","助":"Z","住":"Z","注":"Z","驻":"Z","柱":"Z","祝":"Z","著":"Z","抓":"Z","专":"Z","转":"Z","庄":"Z","装":"Z","壮":"Z","状":"Z","追":"Z","准":"Z","卓":"Z","桌":"Z","着":"Z","仔":"Z","资":"Z","子":"Z","紫":"Z","字":"Z","自":"Z","总":"Z","走":"Z","奏":"Z","族":"Z","阻":"Z","组":"Z","醉":"Z","尊":"Z","最":"Z","昨":"Z","左":"Z","作":"Z","坐":"Z","座":"Z",
            "国":"G","高":"G","光":"G","广":"G","桂":"G","格":"G","贵":"G","钢":"G","冠":"G","工":"G","港":"G","甘":"G","功":"G","公":"G","故":"G","古":"G","固":"G","官":"G","管":"G","规":"G","归":"G",
            "科":"K","开":"K","凯":"K","康":"K","坤":"K","矿":"K","跨":"K","卡":"K","可":"K","克":"K","空":"K","孔":"K","口":"K","库":"K","快":"K","奎":"K","昆":"K",
            "南":"N","能":"N","宁":"N","农":"N","奈":"N","那":"N","纳":"N","楠":"N","尼":"N","泥":"N","霓":"N","年":"N","念":"N","酿":"N","鸟":"N","牛":"N","努":"N","怒":"N","女":"N","暖":"N","挪":"N",
            "福":"F","风":"F","富":"F","方":"F","分":"F","峰":"F","复":"F","飞":"F","凡":"F","菲":"F","凤":"F","佛":"F","发":"F","非":"F","丰":"F","封":"F","锋":"F","冯":"F","奉":"F","父":"F","负":"F","妇":"F",
            "北":"B","保":"B","百":"B","宝":"B","波":"B","邦":"B","白":"B","滨":"B","博":"B","步":"B","铂":"B","包":"B","抱":"B","报":"B","贝":"B","倍":"B","本":"B","奔":"B","笔":"B","币":"B","必":"B","毕":"B","避":"B","边":"B","编":"B","便":"B","变":"B","标":"B","表":"B","别":"B","宾":"B","冰":"B","兵":"B","并":"B","病":"B","拨":"B","伯":"B","薄":"B","补":"B","布":"B","部":"B",
            "上":"S","山":"S","深":"S","盛":"S","顺":"S","双":"S","三":"S","苏":"S","松":"S","石":"S","沈":"S","生":"S","狮":"S","撒":"S","洒":"S","萨":"S","塞":"S","赛":"S","伞":"S","散":"S","桑":"S","扫":"S","色":"S","森":"S","杀":"S","沙":"S","砂":"S","筛":"S","晒":"S","删":"S","闪":"S","陕":"S","善":"S","扇":"S","商":"S","赏":"S","尚":"S","烧":"S","稍":"S","勺":"S","少":"S","绍":"S","奢":"S","蛇":"S","舍":"S","设":"S","社":"S","射":"S","涉":"S","摄":"S","申":"S","伸":"S","身":"S","神":"S","审":"S","升":"S","声":"S","省":"S","圣":"S","胜":"S","剩":"S","师":"S","诗":"S","施":"S","湿":"S","十":"S","时":"S","识":"S","实":"S","拾":"S","食":"S","史":"S","使":"S","始":"S","驶":"S","士":"S","氏":"S","示":"S","世":"S","市":"S","式":"S","事":"S","势":"S","视":"S","试":"S","收":"S","手":"S","守":"S","首":"S","寿":"S","受":"S","售":"S","兽":"S","书":"S","枢":"S","叔":"S","殊":"S","输":"S","舒":"S","疏":"S","熟":"S","暑":"S","署":"S","鼠":"S","术":"S","束":"S","树":"S","竖":"S","数":"S","爽":"S","税":"S","瞬":"S","硕":"S","丝":"S","司":"S","私":"S","思":"S","斯":"S","寺":"S","送":"S","宋":"S","颂":"S","搜":"S","素":"S","速":"S","宿":"S","粟":"S","塑":"S","算":"S","虽":"S","随":"S","岁":"S","孙":"S","损":"S","笋":"S","缩":"S","锁":"S","所":"S",
            "金":"J","京":"J","九":"J","晶":"J","精":"J","江":"J","建":"J","锦":"J","晋":"J","吉":"J","集":"J","机":"J","济":"J","纪":"J","季":"J","加":"J","佳":"J","家":"J","嘉":"J","剑":"J","交":"J","教":"J","杰":"J","捷":"J","今":"J","景":"J","警":"J","竞":"J","敬":"J","靖":"J","酒":"J","居":"J","菊":"J","橘":"J","巨":"J","聚":"J","军":"J","君":"J","钧":"J",
            "海":"H","杭":"H","华":"H","河":"H","汉":"H","宏":"H","鸿":"H","弘":"H","浩":"H","厚":"H","红":"H","恒":"H","亨":"H","含":"H","翰":"H","豪":"H","和":"H","核":"H","辉":"H","汇":"H","会":"H","化":"H","怀":"H","欢":"H","环":"H","皇":"H","户":"H","互":"H","护":"H","花":"H","划":"H","画":"H","话":"H","淮":"H","换":"H","唤":"H","荒":"H","黄":"H","灰":"H","回":"H","惠":"H","毁":"H","悔":"H","混":"H","活":"H","火":"H","获":"H","或":"H","惑":"H","货":"H",
            "天":"T","同":"T","通":"T","泰":"T","台":"T","太":"T","腾":"T","图":"T","投":"T","统":"T","他":"T","它":"T","她":"T","塔":"T","踏":"T","胎":"T","抬":"T","态":"T","摊":"T","滩":"T","坛":"T","潭":"T","坦":"T","叹":"T","炭":"T","探":"T","汤":"T","唐":"T","糖":"T","躺":"T","涛":"T","逃":"T","桃":"T","淘":"T","陶":"T","特":"T","梯":"T","踢":"T","提":"T","题":"T","体":"T","替":"T","田":"T","甜":"T","填":"T","挑":"T","条":"T","跳":"T","贴":"T","铁":"T","厅":"T","听":"T","亭":"T","停":"T","挺":"T","桐":"T","铜":"T","童":"T","痛":"T","偷":"T","头":"T","透":"T","突":"T","徒":"T","土":"T","团":"T","推":"T","腿":"T","退":"T","吞":"T","托":"T","脱":"T","驼":"T",
            "龙":"L","联":"L","蓝":"L","乐":"L","六":"L","理":"L","鲁":"L","利":"L","朗":"L","莱":"L","临":"L","拉":"L","来":"L","兰":"L","浪":"L","劳":"L","雷":"L","磊":"L","冷":"L","黎":"L","力":"L","立":"L","连":"L","莲":"L","链":"L","良":"L","亮":"L","林":"L","灵":"L","凌":"L","岭":"L","令":"L","隆":"L","楼":"L","路":"L","麓":"L","旅":"L","绿":"L","律":"L","伦":"L","洛":"L","络":"L","落":"L",
            "四":"S","盛":"S",
            "亿":"Y","一":"Y","银":"Y","永":"Y","扬":"Y","耀":"Y","元":"Y","远":"Y","云":"Y","宇":"Y","英":"Y","悦":"Y","优":"Y","亚":"Y","咽":"Y","烟":"Y","严":"Y","岩":"Y","延":"Y","言":"Y","颜":"Y","沿":"Y","演":"Y","验":"Y","央":"Y","杨":"Y","羊":"Y","阳":"Y","仰":"Y","养":"Y","样":"Y","腰":"Y","摇":"Y","遥":"Y","咬":"Y","药":"Y","要":"Y","爷":"Y","也":"Y","冶":"Y","野":"Y","业":"Y","叶":"Y","页":"Y","夜":"Y","液":"Y","伊":"Y","衣":"Y","依":"Y","仪":"Y","宜":"Y","姨":"Y","移":"Y","遗":"Y","已":"Y","以":"Y","矣":"Y","蚁":"Y","椅":"Y","义":"Y","忆":"Y","艺":"Y","议":"Y","异":"Y","译":"Y","易":"Y","益":"Y","意":"Y","翼":"Y","因":"Y","引":"Y","隐":"Y","印":"Y","应":"Y","影":"Y","映":"Y","硬":"Y","拥":"Y","勇":"Y","用":"Y","忧":"Y","幽":"Y","悠":"Y","尤":"Y","由":"Y","邮":"Y","犹":"Y","油":"Y","游":"Y","友":"Y","有":"Y","右":"Y","幼":"Y","于":"Y","余":"Y","鱼":"Y","娱":"Y","渔":"Y","与":"Y","羽":"Y","雨":"Y","玉":"Y","育":"Y","郁":"Y","预":"Y","域":"Y","欲":"Y","遇":"Y","御":"Y","裕":"Y","园":"Y","原":"Y","圆":"Y","源":"Y","缘":"Y","愿":"Y","院":"Y","约":"Y","月":"Y","阅":"Y","允":"Y","运":"Y","韵":"Y",
            "万":"W","王":"W","五":"W","文":"W","网":"W","维":"W","微":"W","外":"W","威":"W","沃":"W","挖":"W","哇":"W","娃":"W","瓦":"W","湾":"W","丸":"W","完":"W","玩":"W","往":"W","忘":"W","旺":"W","危":"W","为":"W","围":"W","违":"W","唯":"W","伟":"W","尾":"W","纬":"W","卫":"W","未":"W","味":"W","位":"W","温":"W","纹":"W","闻":"W","稳":"W","问":"W","翁":"W","我":"W","卧":"W","握":"W","乌":"W","污":"W","屋":"W","无":"W","午":"W","武":"W","舞":"W","务":"W","物":"W","雾":"W","误":"W","悟":"W",
            "奇":"Q","千":"Q","青":"Q","全":"Q","泉":"Q","乾":"Q","勤":"Q","期":"Q","七":"Q","齐":"Q","棋":"Q","旗":"Q","祈":"Q","骑":"Q","琪":"Q","祺":"Q","麒":"Q","启":"Q","企":"Q","岂":"Q","气":"Q","器":"Q","迁":"Q","签":"Q","前":"Q","潜":"Q","钱":"Q","浅":"Q","欠":"Q","枪":"Q","强":"Q","墙":"Q","桥":"Q","巧":"Q","切":"Q","茄":"Q","亲":"Q","侵":"Q","琴":"Q","清":"Q","晴":"Q","情":"Q","请":"Q","庆":"Q","穷":"Q","秋":"Q","丘":"Q","求":"Q","球":"Q","区":"Q","曲":"Q","驱":"Q","趣":"Q","圈":"Q","拳":"Q","犬":"Q","劝":"Q","券":"Q","缺":"Q","却":"Q","确":"Q","群":"Q","裙":"Q",
            "徐":"X","兴":"X","新":"X","希":"X","先":"X","西":"X","翔":"X","夏":"X","协":"X","信":"X","祥":"X","夕":"X","吸":"X","昔":"X","析":"X","息":"X","悉":"X","惜":"X","稀":"X","溪":"X","锡":"X","熙":"X","嘻":"X","嬉":"X","膝":"X","习":"X","席":"X","袭":"X","洗":"X","喜":"X","系":"X","细":"X","虾":"X","瞎":"X","侠":"X","峡":"X","狭":"X","霞":"X","下":"X","吓":"X","鲜":"X","纤":"X","弦":"X","咸":"X","显":"X","现":"X","限":"X","线":"X","相":"X","香":"X","湘":"X","想":"X","响":"X","享":"X","项":"X","像":"X","橡":"X","消":"X","萧":"X","硝":"X","销":"X","小":"X","晓":"X","孝":"X","肖":"X","校":"X","笑":"X","效":"X","斜":"X","谐":"X","携":"X","鞋":"X","写":"X","泄":"X","泻":"X","谢":"X","心":"X","辛":"X","欣":"X","星":"X","行":"X","形":"X","醒":"X","幸":"X","性":"X","姓":"X","兄":"X","熊":"X","休":"X","修":"X","秀":"X","袖":"X","绣":"X","锈":"X","嗅":"X","需":"X","许":"X","序":"X","续":"X","絮":"X","蓄":"X","宣":"X","悬":"X","旋":"X","选":"X","穴":"X","雪":"X","血":"X","勋":"X","寻":"X","巡":"X","训":"X","迅":"X",
            "民":"M","名":"M","明":"M","闽":"M","沐":"M","牧":"M","蒙":"M","迈":"M","玛":"M","码":"M","麦":"M","曼":"M","毛":"M","茂":"M","美":"M","孟":"M","梦":"M","米":"M","秘":"M","密":"M","棉":"M","免":"M","面":"M","苗":"M","鸣":"M","命":"M","模":"M","摩":"M","莫":"M","墨":"M","漠":"M","默":"M","谋":"M","牡":"M","木":"M","幕":"M",
            "安":"A","爱":"A","奥":"A",
            "瑞":"R","荣":"R","融":"R","锐":"R","如":"R","然":"R","燃":"R","染":"R","壤":"R","让":"R","饶":"R","扰":"R","绕":"R","热":"R","人":"R","仁":"R","忍":"R","认":"R","任":"R","日":"R","容":"R","溶":"R","熔":"R","柔":"R","肉":"R","乳":"R","软":"R","润":"R","若":"R","弱":"R"};
  function pyInitial(name) {
    if (!name) return '';
    var s = '';
    for (var i = 0; i < name.length; i++) {
      var c = name.charAt(i);
      s += PY[c] || c;
    }
    return s.toLowerCase();
  }
  function search() {
    var q = (document.getElementById('kSearch').value || '').trim();
    var hint = document.getElementById('kSearchHint');
    if (!q) { hint.textContent = '提示：输入 6 位代码（如 600519）或名称（如 茅台）'; return; }
    if (/^\\d{6}$/.test(q)) { openKline(q); hint.textContent=''; return; }
    var codeHit = getPool().find(function(s){ return s.code.indexOf(q) === 0; });
    if (codeHit) { openKline(codeHit.code); hint.textContent = codeHit.code + ' ' + codeHit.name; return; }
    var nameHit = getPool().find(function(s){ return s.name && s.name.indexOf(q) >= 0; });
    if (nameHit) { openKline(nameHit.name ? nameHit.code : ''); hint.textContent = nameHit.code + ' ' + nameHit.name; return; }
    var qLow = q.toLowerCase();
    var pyHit = getPool().find(function(s){ return pyInitial(s.name) === qLow; });
    if (pyHit) { openKline(pyHit.code); hint.textContent = pyHit.code + ' ' + pyHit.name + ' (拼音首字母)'; return; }
    if (/^\\d{4,6}$/.test(q)) {
      openKline(String(q).padStart(6, '0'));
      hint.textContent = '股票池未匹配，按代码直接拉取';
      return;
    }
    hint.textContent = '股票池未匹配，请输入 6 位代码（如 600519）';
  }
  document.getElementById('kSearchBtn').onclick = search;
  document.getElementById('kSearch').addEventListener('keydown', function(e){
    if (e.key === 'Enter') { e.preventDefault(); search(); }
  });
})();

var _lastIsSmall = (window.innerWidth || document.documentElement.clientWidth || 430) <= 600;
window.addEventListener('resize', function () {
  var now = (window.innerWidth || document.documentElement.clientWidth || 430) <= 600;
  if (now !== _lastIsSmall) {
    _lastIsSmall = now;
    // 跨过断点：图表配置不同，需重建实例后重渲染
    if (chart) { chart.dispose(); chart = null; }
    render();
  } else if (chart) {
    chart.resize();
  }
});

/* ============ 实时行情刷新（静态托管也能盘中实时） ============ */
(function () {
  function toSecid(c) {
    c = String(c || '').replace(/[^0-9]/g, '');
    if (!c) return '';
    var h = c.charAt(0);
    if (h === '6' || h === '9') return '1.' + c;
    return '0.' + c;
  }
  function fmtAmtLive(v) {
    if (v == null || isNaN(v)) return null;
    v = Number(v);
    if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿';
    if (v >= 1e4) return (v / 1e4).toFixed(0) + '万';
    return String(v);
  }
  function applyQuote(code, price, pct, amt) {
    if (!code) return;
    var els = document.querySelectorAll('.diffcard[data-code="' + code + '"]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (price != null && price !== '-' && !isNaN(price)) {
        var pe = el.querySelector('.dprice');
        if (pe) pe.textContent = Number(price).toFixed(2);
      }
      if (pct != null && pct !== '-' && !isNaN(pct)) {
        var re = el.querySelector('.drate');
        if (re) {
          re.textContent = (Number(pct) > 0 ? '+' : '') + Number(pct).toFixed(2) + '%';
          re.className = 'drate ' + (Number(pct) > 0 ? 'up' : (Number(pct) < 0 ? 'down' : 'flat'));
        }
      }
      var s = fmtAmtLive(amt);
      if (s) {
        var ae = el.querySelector('.damt');
        if (ae) ae.textContent = s;
      }
    }
  }
  function tick() {
    var tag = document.getElementById('liveTag');
    if (!tag) return;
    var t = new Date();
    function p(n) { return (n < 10 ? '0' : '') + n; }
    tag.textContent = '行情实时 ' + p(t.getHours()) + ':' + p(t.getMinutes()) + ':' + p(t.getSeconds());
  }
  function refreshQuotes() {
    var cards = document.querySelectorAll('.diffcard[data-code]');
    var codes = [];
    for (var i = 0; i < cards.length; i++) {
      var c = cards[i].getAttribute('data-code');
      if (c && codes.indexOf(c) < 0) codes.push(c);
    }
    if (!codes.length) return;
    var BATCH = 80;
    for (var b = 0; b < codes.length; b += BATCH) {
      (function (batch) {
        var secids = [];
        for (var k = 0; k < batch.length; k++) {
          var s = toSecid(batch[k]);
          if (s) secids.push(s);
        }
        if (!secids.length) return;
        var url = 'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=' +
                  secids.join(',') + '&fields=f2,f3,f6,f12';
        fetch(url, { cache: 'no-store' })
          .then(function (r) { return r.json(); })
          .then(function (j) {
            var diff = (j && j.data && j.data.diff) || [];
            var got = 0;
            for (var i = 0; i < diff.length; i++) {
              var d = diff[i];
              if (!d) continue;
              applyQuote(d.f12, d.f2, d.f3, d.f6);
              got++;
            }
            if (got) tick();
          })
          .catch(function () {});
      })(codes.slice(b, b + BATCH));
    }
  }
  window.refreshQuotes = refreshQuotes;
  setTimeout(refreshQuotes, 400);
  setInterval(refreshQuotes, 60000);

  /* 新渲染出的卡片（切tab / 展开板块 / 展开全部）立即补刷实时价 */
  var _rqTimer = null;
  function scheduleRefresh() {
    if (_rqTimer) clearTimeout(_rqTimer);
    _rqTimer = setTimeout(function () { _rqTimer = null; refreshQuotes(); }, 120);
  }
  if (window.MutationObserver) {
    var _mo = new MutationObserver(function (mutations) {
      var hit = false;
      for (var i = 0; i < mutations.length; i++) {
        var added = mutations[i].addedNodes || [];
        for (var k = 0; k < added.length; k++) {
          var n = added[k];
          if (!n || n.nodeType !== 1) continue;
          if (n.classList && n.classList.contains('diffcard')) { hit = true; break; }
          if (n.querySelectorAll && n.querySelectorAll('.diffcard').length) { hit = true; break; }
        }
        if (hit) break;
      }
      if (hit) scheduleRefresh();
    });
    _mo.observe(document.body, { childList: true, subtree: true });
  }
  /* 手机从后台切回前台立即刷新 */
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) refreshQuotes();
  });
  /* 点顶部标记手动刷新 */
  var _lt = document.getElementById('liveTag');
  if (_lt) {
    _lt.style.cursor = 'pointer';
    _lt.title = '点击立即刷新行情';
    _lt.addEventListener('click', function () { refreshQuotes(); });
  }
})();
</script>
</body>
</html>
"""

DISCLAIMER = ("免责声明：以上内容基于公开数据和量化分析，仅供参考，不构成投资建议。"
              "市场有风险，投资需谨慎。任何投资决策应结合个人风险承受能力、资金状况和投资目标独立判断，"
              "必要时咨询持牌专业机构。过往表现不预示未来收益。")


def js_check(html):
    """抽出内联 <script> 体做 node --check 语法自检。"""
    import re as _re
    blocks = _re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, _re.S)
    if not blocks:
        return True, "无内联脚本"
    tmp = os.path.join(HERE, "_js_check.js")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n;\n".join(blocks))
    exe = None
    for cand in (
        os.path.join(os.path.dirname(sys.executable), "node.exe"),
        r"C:\Users\mayn\.workbuddy\binaries\node\versions\22.22.2-2\node.exe",
        "node",
    ):
        if cand == "node" or os.path.exists(cand):
            exe = cand
            break
    if not exe:
        return True, "未找到 node，跳过自检"
    try:
        r = subprocess.run([exe, "--check", tmp], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return True, "JS 语法自检通过"
        return False, r.stderr[:900]
    except Exception as e:  # noqa: BLE001
        return True, f"自检跳过：{e}"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def load_kline_modal():
    """注入 K 线弹层组件（kline_modal.py）。"""
    try:
        import kline_modal
        return kline_modal.KLINE_MODAL_HTML
    except Exception as e:  # noqa: BLE001
        return "<!-- K-line modal load failed: " + str(e) + " -->"


def _echarts_file():
    """返回本地 echarts.min.js 路径（output/ 或 应用根目录），不存在返回 None。"""
    for p in (ECHARTS_JS_PATH, os.path.join(HERE, "echarts.min.js")):
        if os.path.exists(p):
            return p
    return None


def _inline_echarts():
    """是否把 echarts 内联进 HTML。

    默认外链（首屏快、可缓存）。设置环境变量 INLINE_ECHARTS=1 时内联，
    用于生成可单独双击打开、不依赖同目录文件的离线单文件版。
    """
    return os.environ.get("INLINE_ECHARTS", "").strip() in ("1", "true", "yes")


def load_echarts_lib():
    """head 区域内容。

    默认：仅输出 preload 提示，真正的加载放到 body 末尾（见 load_echarts_boot），
    避免 1MB 的 echarts 阻塞首屏渲染（iOS Safari 上表现为长时间白屏/转圈）。
    """
    p = _echarts_file()
    if p and not _inline_echarts():
        return '<link rel="preload" as="script" href="echarts.min.js">'
    if p:
        with open(p, encoding="utf-8") as f:
            return ("<script>// ECharts 本地内联（离线单文件版）\n"
                    + f.read() + "\n</script>")
    # 无本地文件：回退 CDN（动态注入，顺序可控）
    cdn = "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"
    return ("<script>(function(){var s=document.createElement('script');"
            f"s.src='{cdn}';s.async=false;"
            "s.onerror=function(){var el=document.getElementById('chart-status');"
            "if(el){el.classList.remove('hidden');el.classList.add('empty');"
            "el.textContent='ECharts 加载失败（CDN 不通 + 本地无 echarts.min.js）。"
            "请将 echarts.min.js 放到 output/ 目录。';}};"
            "document.head.appendChild(s);})();</script>")


# 数据解包：把 pack_data 字典化后的索引还原成字符串，放在 var DATA 之后立即执行。
# 这样下游所有渲染代码看到的仍是原始的 concepts/industry 结构，无需任何改动。
UNPACK_JS = """
/* 数据字典还原：concepts/industry 在生成时已编码为索引，这里解回字符串 */
(function () {
  var cd = DATA.__cd || [], id = DATA.__id || [];
  if (!cd.length && !id.length) { return; }
  function fix(s) {
    if (!s || typeof s !== 'object') { return; }
    if (s.c && cd.length) {
      s.concepts = s.c.map(function (i) { return cd[i]; });
      delete s.c;
    }
    if (typeof s.i === 'number' && id.length) {
      s.industry = id[s.i];
      delete s.i;
    }
  }
  var ks = ['industry_l1', 'industry_l2', 'industry_l3', 'concept'];
  for (var a = 0; a < ks.length; a++) {
    var arr = (DATA.boards || {})[ks[a]] || [];
    for (var b = 0; b < arr.length; b++) {
      var sts = arr[b].stocks || [];
      for (var c = 0; c < sts.length; c++) { fix(sts[c]); }
    }
  }
  var d = DATA.diff || {};
  ['new', 'gone'].forEach(function (k) { (d[k] || []).forEach(fix); });
  if (Array.isArray(DATA.pool)) { DATA.pool.forEach(fix); }
})();
"""


def pack_data(data):
    """字典化压缩 DATA（不改语义，前端 UNPACK_JS 还原）。

    背景：同一批股票在 300+ 个概念板块里被重复携带，concepts/industry 字符串
    反复出现，是页面体积的主要来源。编码为索引后可显著缩小；同时去掉前端已
    不再展示的 is_st 字段。
    """
    cdict, clist = {}, []
    idict, ilist = {}, []

    def enc(st):
        if not isinstance(st, dict):
            return
        cs = st.get("concepts") or []
        if cs:
            idxs = []
            for c in cs:
                if c not in cdict:
                    cdict[c] = len(clist)
                    clist.append(c)
                idxs.append(cdict[c])
            st["c"] = idxs
            del st["concepts"]
        ind = st.get("industry")
        if ind:
            if ind not in idict:
                idict[ind] = len(ilist)
                ilist.append(ind)
            st["i"] = idict[ind]
            del st["industry"]
        st.pop("is_st", None)

    boards = data.get("boards") or {}
    for key in ("industry_l1", "industry_l2", "industry_l3", "concept"):
        for b in (boards.get(key) or []):
            for st in (b.get("stocks") or []):
                enc(st)
    diff = data.get("diff") or {}
    for key in ("new", "gone"):
        for st in (diff.get(key) or []):
            enc(st)
    pool = data.get("pool")
    if isinstance(pool, list):
        for st in pool:
            enc(st)
    if clist:
        data["__cd"] = clist
    if ilist:
        data["__id"] = ilist
    return data


def load_echarts_boot():
    """body 末尾内容：真正加载 echarts，且在业务脚本之前，保证调用时序。"""
    p = _echarts_file()
    if p and not _inline_echarts():
        # 同步外链：浏览器可缓存，二次访问不再重复下载 1MB
        return '<script src="echarts.min.js"></script>'
    return ""


def enrich_amounts(data, date_str):
    """为 diff.new 每只个股补齐当日成交额（元），来源腾讯快照 qt.gtimg.cn，带本地缓存。"""
    rows = []
    diff = data.get("diff")
    if diff and diff.get("has_baseline"):
        rows += (diff.get("new") or [])
    for key in ("industry_l1", "industry_l2", "industry_l3", "concept"):
        for b in (data.get("boards", {}).get(key) or []):
            rows += (b.get("stocks") or [])
    if not rows:
        return
    cache_path = os.path.join(DATA_DIR, "amount_cache_%s.json" % date_str)
    cache = {}
    if os.path.exists(cache_path):
        try:
            cache = json.load(open(cache_path, encoding="utf-8"))
        except Exception:
            cache = {}
    need = [r["code"] for r in rows if r.get("code") and r["code"] not in cache]

    def prefix(code):
        if code.startswith("6"):
            return "sh" + code
        if code.startswith(("4", "8")):
            return "bj" + code
        return "sz" + code

    if need:
        try:
            for _i in range(0, len(need), 200):
                batch = need[_i:_i + 200]
                url = "https://qt.gtimg.cn/q=" + ",".join(prefix(c) for c in batch)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=25) as resp:
                    txt = resp.read().decode("gbk", "ignore")
                for line in txt.split(";"):
                    line = line.strip()
                    if "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.replace("v_", "").strip()
                    val = val.strip().strip('"')
                    if not val:
                        continue
                    f = val.split("~")
                    amt = None
                    if len(f) > 35 and "/" in f[35]:
                        try:
                            amt = float(f[35].split("/")[2])
                        except Exception:
                            amt = None
                    six = key[2:] if len(key) > 2 else key
                    cache[six] = amt
            with open(cache_path, "w", encoding="utf-8") as fp:
                json.dump(cache, fp, ensure_ascii=False)
        except Exception as e:
            print("  [warn] 当日成交额获取失败，成交额列将显示 — ：", e)
    for r in rows:
        r["amount"] = cache.get(r.get("code"))


def main(date_str=None):
    date_str = date_str or dt.date.today().strftime("%Y%m%d")
    # 首屏嵌入「上升途中」单策略数据（运行时再拉取 combined board.json 覆盖）
    stats_path = os.path.join(DATA_DIR, f"stats_uptrend_{date_str}.json")
    if not os.path.exists(stats_path):
        stats_path = os.path.join(DATA_DIR, f"stats_{date_str}.json")
    if not os.path.exists(stats_path):
        # 当年所在日期无 stats 时，回退到 data 目录中最新的 stats_*.json，
        # 保证看板始终能用真实历史数据生成（而非崩溃/空板）
        cands = sorted(glob.glob(os.path.join(DATA_DIR, "stats_*.json")))
        if cands:
            stats_path = cands[-1]
            date_str = os.path.basename(stats_path)[len("stats_"):-len(".json")]
            print(f"  [info] stats_{{date}} 不存在，回退使用 {os.path.basename(stats_path)}")
    with open(stats_path, encoding="utf-8") as f:
        data = json.load(f)
    enrich_amounts(data, date_str)

    data = pack_data(data)
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    # 模板优先用 template.html（保留所有手工调校的 K 线样式 / 双策略 tab），
    # 缺失时回退到代码内联 TPL 常量。
    tpl_path = os.path.join(HERE, "template.html")
    tpl = TPL
    if os.path.exists(tpl_path):
        with open(tpl_path, encoding="utf-8") as tf:
            tpl = tf.read()
    html = (tpl
            .replace("__DATA__", data_json)
            .replace("__DATE__", date_str)
            .replace("__GEN__", data.get("generated_at", ""))
            .replace("__DATETIME__", data.get("generated_at") or dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            .replace("__SOURCE__", data.get("source", "同花顺问财"))
            .replace("__QUERY__", data.get("query", ""))
            .replace("__DISCLAIMER__", DISCLAIMER)
            .replace("__DATA_UNPACK__", UNPACK_JS)
            .replace("__ECHARTS_LIB__", load_echarts_lib())
            .replace("__ECHARTS_BOOT__", load_echarts_boot())
            .replace("__KLINE_MODAL__", load_kline_modal()))

    ok, msg = js_check(html)
    print(("  [JS] " + msg) if ok else ("  [JS 错误]\n" + msg))
    if not ok:
        raise SystemExit("内联 JS 语法错误，已中止输出")

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "uptrend_board.html")  # 固定文件名，避免日期命名歧义
    # 外链模式下把 echarts.min.js 拷到同目录，保证 index.html 能加载图表库
    src = _echarts_file()
    if src and not _inline_echarts():
        dst = os.path.join(OUT_DIR, "echarts.min.js")
        if os.path.abspath(src) != os.path.abspath(dst):
            shutil.copyfile(src, dst)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"看板生成 -> {out}  ({len(html.encode('utf-8'))/1024:.0f} KB)")
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
