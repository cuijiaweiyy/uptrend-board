// 上升途中看板 —— K线/分时 同源代理（Cloudflare Pages Function）
//
// 为什么需要它：浏览器直连东财(push2his)/腾讯(gtimg) 在部分网络下会被 CORS / GFW /
// 代理拦截，导致「K线加载失败」。这里由服务端（Cloudflare 边缘）抓取——东财→腾讯兜底——
// 绕开客户端跨域与网络限制，再带上 CORS 头回给页面。
//
// 路由：/api/kline?kind=kline|minute&code=600519&period=day&days=70
// 返回：{ ok:true, source:'em'|'tx', raw:<上游原始 JSON> } 或 { ok:false, error }
// 页面端按 source 复用既有的 buildEm/buildTx 解析逻辑，单一数据源不变。

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Max-Age': '86400',
  };
}
function jsonResp(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { 'Content-Type': 'application/json; charset=utf-8', ...corsHeaders(), ...extra },
  });
}

function txSym(code) {
  return (/^(60|68|90|11|113|12)/.test(code) ? 'sh' : 'sz') + code;
}
function emSecid(code) {
  return (code.charAt(0) === '6' ? '1' : '0') + '.' + code;
}

async function fetchEmKline(code, period, days) {
  const klt = period === 'week' ? 102 : period === 'month' ? 103 : 101;
  const url =
    'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=' + emSecid(code) +
    '&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57' +
    '&klt=' + klt + '&fqt=1&end=20500101&lmt=' + days + '&_=' + Date.now();
  const r = await fetch(url, { cf: { cacheTtl: 60 } });
  if (!r.ok) throw new Error('em kline HTTP ' + r.status);
  return r.json();
}
async function fetchTxKline(code, period, days) {
  const sym = txSym(code);
  const url =
    'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=' + sym + ',' + period + ',,,' + days + ',qfq';
  const r = await fetch(url);
  if (!r.ok) throw new Error('tx kline HTTP ' + r.status);
  return r.json();
}
async function fetchEmMinute(code) {
  const url =
    'https://push2.eastmoney.com/api/qt/stock/trends2/get?secid=' + emSecid(code) +
    '&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57,f58' +
    '&iscr=0&ndays=1&forcect=1&_=' + Date.now();
  const r = await fetch(url);
  if (!r.ok) throw new Error('em minute HTTP ' + r.status);
  return r.json();
}
async function fetchTxMinute(code) {
  const sym = txSym(code);
  const url = 'https://web.ifzq.gtimg.cn/appstock/app/minute/query?code=' + sym;
  const r = await fetch(url);
  if (!r.ok) throw new Error('tx minute HTTP ' + r.status);
  return r.json();
}

// 轻量「有数据」校验，避免东财返回空 klines 时空欢喜、不兜底腾讯
function hasData(kind, source, raw, code, period) {
  if (!raw || !raw.data) return false;
  if (source === 'em') {
    if (kind === 'minute') return Array.isArray(raw.data.trends) && raw.data.trends.length > 0;
    return Array.isArray(raw.data.klines) && raw.data.klines.length > 0;
  }
  const sym = txSym(code);
  const node = raw.data[sym];
  if (!node) return false;
  if (kind === 'minute') {
    const md = node.data || {};
    return Array.isArray(md.data) && md.data.length > 0;
  }
  // 腾讯按请求 period 返回 qfq<period> 字段（week/month/day）；兜底 qfqday/day
  const rows = node['qfq' + period] || node['qfqday'] || node[period] || node['day'];
  return Array.isArray(rows) && rows.length > 0;
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}

export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const kind = url.searchParams.get('kind') || 'kline';
  const code = (url.searchParams.get('code') || '').trim();
  const period = url.searchParams.get('period') || 'day';
  const days = parseInt(url.searchParams.get('days') || '70', 10) || 70;

  if (!/^\d{6}$/.test(code)) {
    return jsonResp({ ok: false, error: 'bad code' }, 400);
  }

  let raw = null;
  let source = null;
  const errs = [];

  if (kind === 'minute') {
    try {
      const r = await fetchEmMinute(code);
      if (hasData('minute', 'em', r, code)) { raw = r; source = 'em'; }
      else errs.push('em:empty');
    } catch (e) { errs.push('em:' + (e && e.message ? e.message : e)); }
    if (!raw) {
      try {
        const r = await fetchTxMinute(code);
        if (hasData('minute', 'tx', r, code)) { raw = r; source = 'tx'; }
        else errs.push('tx:empty');
      } catch (e) { errs.push('tx:' + (e && e.message ? e.message : e)); }
    }
  } else {
    try {
      const r = await fetchEmKline(code, period, days);
      if (hasData('kline', 'em', r, code)) { raw = r; source = 'em'; }
      else errs.push('em:empty');
    } catch (e) { errs.push('em:' + (e && e.message ? e.message : e)); }
    if (!raw) {
      try {
        const r = await fetchTxKline(code, period, days);
        if (hasData('kline', 'tx', r, code, period)) { raw = r; source = 'tx'; }
        else errs.push('tx:empty');
      } catch (e) { errs.push('tx:' + (e && e.message ? e.message : e)); }
    }
  }

  if (!raw) {
    return jsonResp({ ok: false, error: 'all sources failed: ' + errs.join(' | ') }, 502);
  }
  return jsonResp(
    { ok: true, source, raw },
    200,
    { 'Cache-Control': 'public, max-age=60' }
  );
}
