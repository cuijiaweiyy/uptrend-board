// 上升途中看板 —— 批量实时行情代理（列表卡片价格/涨跌幅/成交额盘中实时刷新）
//
// 为什么需要它：浏览器直连东财 push2 ulist 在部分网络（尤其移动网络/iPhone）下会被
// CORS / GFW / 代理拦截，导致列表卡片的实时价/涨跌幅一直停在问财 15 分钟快照。
// 由 CF 边缘服务端抓取、带 CORS 头回传，与 /api/quote、/api/kline 同源代理同一思路。
//
// 路由：/api/quotes?secids=1.600519,0.000001&fields=f2,f3,f6,f12
// 返回：原样透传东财 { data:{ diff:[ {f2,f3,f6,f12} ] } }（前端解析逻辑不变）
//       字段口径：f2=最新价 f3=涨跌幅% f6=成交额(元) f12=代码

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
export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}
export async function onRequestGet({ request }) {
  const url = new URL(request.url);
  const secids = (url.searchParams.get('secids') || '').trim();
  const fields = (url.searchParams.get('fields') || 'f2,f3,f6,f12').trim();
  const arr = secids.split(',').map((s) => s.trim()).filter(Boolean);
  if (!arr.length) return jsonResp({ data: { diff: [] } }, 400);
  // 校验每段为 `市场.代码` 形如 1.600519 / 0.000001
  if (!arr.every((s) => /^\d\.\d{6}$/.test(s))) return jsonResp({ data: { diff: [] } }, 400);
  if (arr.length > 300) return jsonResp({ data: { diff: [] } }, 400);
  const em =
    'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=' +
    encodeURIComponent(arr.join(',')) + '&fields=' + encodeURIComponent(fields);
  try {
    const r = await fetch(em, { cf: { cacheTtl: 30 } });
    if (!r.ok) return jsonResp({ data: { diff: [] } }, 502);
    const j = await r.json();
    // 原样透传东财结构，前端只读 j.data.diff
    return jsonResp(j, 200, { 'Cache-Control': 'public, max-age=30' });
  } catch (e) {
    return jsonResp({ data: { diff: [] } }, 502);
  }
}
