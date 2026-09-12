// 上升途中看板 —— 按需计算端点（Cloudflare Pages Function）
//
// 为什么需要它：问财接口无 CORS、需 hexin-v 反爬头，浏览器（尤其国内手机）无法直连。
// 原 Worker（*.workers.dev）在国内被 DNS 投毒，手机连不上；本 Function 部署在
// Cloudflare Pages（*.pages.dev，通常国内可达），由页面打开时触发，做到「看时最新」。
//
// 复用 cloud/worker/index.js 中已验证的计算逻辑（hexin-v 生成 + 问财抓取 + 板块统计）。
import { getHexinV, fetchPool, computeBoardFromStocks, pushBoardToGithub, writeBoardKv } from '../../../worker/index.js';

const BOARD_KEY = 'board:latest';
const STALE_MS = 20 * 60 * 1000; // 与 Worker 共用同一 KV 键，保证缓存互通

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

// 与 Worker 同构的 KV 读取（快照机制）
async function readBoardKv(env) {
  const kv = env.UPTREND_KV;
  if (!kv) return null;
  try {
    const raw = await kv.get(BOARD_KEY);
    if (!raw) return null;
    const wrap = JSON.parse(raw);
    if (!wrap || !wrap.ts || !wrap.data) return null;
    return { data: wrap.data, ts: wrap.ts, fresh: Date.now() - wrap.ts <= STALE_MS };
  } catch {
    return null;
  }
}

// 一次性完整抓取（沪+深分段拉全量）+ 板块统计
async function buildBoard(env, deadline = 0) {
  const token = getHexinV();
  const minGap = Number(env.MIN_GAP || 450);
  const poolRes = await fetchPool(token, 3, minGap, deadline);
  const { stocks, tradeDate, failed } = poolRes;
  if (!stocks.length) throw new Error('问财未返回任何数据');
  return computeBoardFromStocks(stocks, tradeDate, env, failed);
}

export async function onRequestOptions() {
  return new Response(null, { status: 204, headers: corsHeaders() });
}

export async function onRequestGet({ request, env, waitUntil }) {
  const url = new URL(request.url);
  const refresh = url.searchParams.get('refresh') === '1';

  if (url.pathname === '/api/health') {
    try {
      const tk = getHexinV();
      return jsonResp({ ok: !!tk, token_len: tk ? tk.length : 0 });
    } catch (e) {
      return jsonResp({ ok: false, error: String(e && e.message ? e.message : e) }, 500);
    }
  }

  // 打开即算：页面带 refresh=1 调用，现算现回（约 10-25s），并异步写 KV + GitHub
  if (refresh) {
    try {
      const data = await buildBoard(env, Date.now() + 25000);
      const failed = (data._diag && data._diag.failed_industries) || [];
      const complete = !failed.length;
      if (complete || (data.pool && data.pool.total >= 80)) {
        // 响应先返回最新数据；KV / GitHub 写入异步完成后台进行
        waitUntil(
          (async () => {
            try { await writeBoardKv(env, data); } catch (_) {}
            try { await pushBoardToGithub(env, data); } catch (_) {}
          })()
        );
        return jsonResp(data, 200, { 'X-Cache': 'FRESH' });
      }
      return jsonResp({ error: 'incomplete', failed, total: data.pool && data.pool.total }, 502);
    } catch (e) {
      return jsonResp({ error: 'build_failed', message: String(e && e.message ? e.message : e) }, 502);
    }
  }

  // 普通 GET：返回 KV 快照（秒回，供首屏即显）
  const kvBoard = await readBoardKv(env);
  if (kvBoard) {
    return jsonResp(kvBoard.data, 200, {
      'Cache-Control': `public, max-age=${Number(env.CACHE_TTL || 300)}`,
      'X-Cache': kvBoard.fresh ? 'KV' : 'KV-STALE',
      'X-Data-Age': String(Math.round((Date.now() - kvBoard.ts) / 1000)),
    });
  }
  return jsonResp({ error: 'no_fresh_data' }, 503);
}
