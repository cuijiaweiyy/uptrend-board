// 上升途中看板 —— 实时数据后端（Cloudflare Worker）
//
// 为什么需要它：同花顺问财接口无 CORS、且需要 hexin-v 反爬头，浏览器无法直连。
// 本 Worker 自带 token 生成（dom-shim + hexinv-core，无需 jsdom），
// 实时抓取「上升途中」股票池并计算板块统计，返回与 stats_*.json 同构的 JSON。
//
// 接口：
//   GET /api/board  -> 完整看板数据（缓存 5 分钟）
//   GET /api/health -> 自检（token 生成 + 单次问财连通性）
import { createShims } from './dom-shim.js';
import hexinCore from './hexinv-core.js';
import { INDUSTRY_L1, NOISE_KEYWORDS, MARKET_MAP } from './constants.js';

const shims = createShims();
const getHexinV = hexinCore(shims);

const WENCAI_URL =
  'https://www.iwencai.com/unifiedwap/unified-wap/v2/result/get-robot-data';
const ADD_INFO =
  '{"urp":{"scene":1,"company":1,"business":1},"contentType":"json","searchInfo":true}';
const BASE_COND = '上升途中';
const EXTRA_FIELDS = '所属同花顺行业 所属概念';
const CACHE_TTL = 300; // 5 分钟：问财限流很凶，必须缓存

function corsHeaders() {
  return {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Max-Age': '86400',
  };
}

function jsonResp(obj, status = 200, extra = {}) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      ...corsHeaders(),
      ...extra,
    },
  });
}

// ---------- 问财请求 ----------

function extractDatas(j) {
  const answers = j?.data?.answer;
  if (!Array.isArray(answers)) return { rows: [], meta: {} };
  for (const ans of answers) {
    for (const txt of ans?.txt || []) {
      for (const comp of txt?.content?.components || []) {
        const d = comp?.data;
        if (d?.datas?.length) return { rows: d.datas, meta: d.meta || {} };
      }
    }
  }
  return { rows: [], meta: {} };
}

function metaInfo(meta, rows) {
  const extra = meta?.extra || {};
  let rowCount = 0;
  for (const src of [meta, extra]) {
    const v = src?.row_count ?? src?.code_count;
    if (v) rowCount = Math.max(rowCount, Number(v) || 0);
  }
  let tradeDate = '';
  const cond = extra?.condition || meta?.condition || '';
  const m = String(cond).match(/交易日期[^\d]{0,4}(\d{8})/);
  if (m) tradeDate = m[1];
  if (!tradeDate && Array.isArray(rows)) {
    for (const row of rows.slice(0, 3)) {
      if (!row || typeof row !== 'object') continue;
      for (const k of Object.keys(row)) {
        const mm = String(k).match(/(\d{8})/);
        if (mm) {
          tradeDate = mm[1];
          break;
        }
      }
      if (tradeDate) break;
    }
  }
  return { rowCount, tradeDate };
}

async function wencaiQuery(question, token, retry = 2) {
  const body = new URLSearchParams({
    question,
    perpage: '100',
    page: '1',
    secondary_intent: 'stock',
    log_info: '{"input_type":"typewrite"}',
    source: 'Ths_iwencai_Xuangu',
    version: '2.0',
    query_area: '',
    block_list: '',
    add_info: ADD_INFO,
  });
  let lastErr = 'unknown';
  for (let i = 0; i <= retry; i++) {
    try {
      const r = await fetch(WENCAI_URL, {
        method: 'POST',
        headers: {
          'hexin-v': token,
          'User-Agent': shims.navigator.userAgent,
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: body.toString(),
      });
      const text = await r.text();
      let j;
      try {
        j = JSON.parse(text);
      } catch {
        lastErr = '响应非 JSON（可能被限流）: ' + text.slice(0, 60);
        await new Promise((res) => setTimeout(res, 1200 * (i + 1)));
        continue;
      }
      if (j.status_code === 0) {
        const { rows, meta } = extractDatas(j);
        if (rows.length) return { rows, ...metaInfo(meta, rows) };
        lastErr = '响应正常但无数据行';
      } else {
        lastErr = `status_code=${j.status_code} msg=${j.status_msg || ''}`;
      }
    } catch (e) {
      lastErr = String(e && e.message ? e.message : e);
    }
    await new Promise((res) => setTimeout(res, 1200 * (i + 1)));
  }
  return { rows: [], rowCount: 0, tradeDate: '', error: lastErr };
}

// 并发受控 + 全局限速的批量查询。
//
// 限速必须是「全局」的：若每个 runner 各自 sleep，实际速率会变成 limit 倍。
// 间隔取值来自实测（2026-09-10）：
//   450ms(~2.2 req/s) -> 发到第 10 个左右就被问财封（Nginx forbidden），且封禁持续 ~2 分钟
//   1800ms(~0.55 req/s) -> 连续 17 次全部成功
// 因此默认取 1600ms 保守值，可用 env.MIN_GAP 调整。
const DEFAULT_MIN_GAP = 1600;

async function mapLimit(items, limit, worker, minGap = DEFAULT_MIN_GAP) {
  const out = new Array(items.length);
  let cursor = 0;
  let nextSlot = 0; // 下一个允许启动的时间戳
  async function runner() {
    while (cursor < items.length) {
      const idx = cursor++;
      const now = Date.now();
      const slot = Math.max(now, nextSlot);
      nextSlot = slot + minGap;
      const wait = slot - now;
      if (wait > 0) await new Promise((res) => setTimeout(res, wait));
      out[idx] = await worker(items[idx], idx);
    }
  }
  const runners = [];
  for (let i = 0; i < Math.min(limit, items.length); i++) runners.push(runner());
  await Promise.all(runners);
  return out;
}

// ---------- 行归一化 ----------

function normRow(r) {
  const pick = (...keys) => {
    for (const k of keys) {
      if (r[k] !== undefined && r[k] !== null && r[k] !== '' && r[k] !== '--') return r[k];
    }
    return null;
  };
  const dyn = (prefix) => {
    for (const k of Object.keys(r)) if (k.startsWith(prefix)) return r[k];
    return null;
  };
  const fnum = (v) => {
    const n = Number(v);
    return Number.isFinite(n) ? Math.round(n * 10000) / 10000 : null;
  };

  const industryFull = String(pick('所属同花顺行业') ?? dyn('所属同花顺行业') ?? '');
  const parts = industryFull.split('-').map((s) => s.trim()).filter(Boolean);
  const conceptsRaw = String(pick('所属概念') ?? dyn('所属概念') ?? '');
  const concepts = conceptsRaw
    .replace(/;/g, '|')
    .split('|')
    .map((s) => s.trim())
    .filter(Boolean);

  const code6 = String(pick('code') ?? '');
  const fullCode = String(pick('股票代码') ?? code6);
  const name = String(pick('股票简称') ?? '');
  const marketCode = String(pick('market_code') ?? '');
  const exchange =
    MARKET_MAP[marketCode] ||
    (String(fullCode).includes('.') ? String(fullCode).split('.').pop() : '');

  return {
    code: code6,
    full_code: fullCode,
    name,
    exchange,
    price: fnum(pick('最新价')),
    chg_pct: fnum(pick('最新涨跌幅')),
    ind_l1: parts[0] || '',
    ind_l2: parts[1] || '',
    ind_l3: parts[2] || '',
    industry: parts.join('-'),
    concepts,
    concept_count: concepts.length,
    buy_signal: pick('买入信号inter') ?? dyn('买入信号inter'),
    tech_pattern: pick('技术形态') ?? dyn('技术形态'),
    is_st: name.toUpperCase().includes('ST') || name.startsWith('*'),
  };
}

// ---------- 抓取股票池 ----------
// 问财单次上限 100 条且 page 分页无效、sort 双向排序实测也无效，
// 因此按「一级行业」分段：各行业命中数远低于 100，且互不重叠，并集即全量。

async function fetchPool(token, maxPasses = 3, minGap = DEFAULT_MIN_GAP) {
  let todo = [...INDUSTRY_L1];
  const collected = new Map();
  let tradeDate = '';
  let failed = [];

  for (let pass = 0; pass < maxPasses && todo.length; pass++) {
    if (pass > 0) {
      // 上一轮有失败，先退避一段时间再补抓，避开问财风控窗口
      await new Promise((res) => setTimeout(res, 8000 * pass));
    }
    const results = await mapLimit(
      todo,
      2, // 并发压到 2：问财对突发并发很敏感
      async (ind) => {
        const res = await wencaiQuery(`${BASE_COND} ${ind} ${EXTRA_FIELDS}`, token);
        return { ind, ...res };
      },
      minGap
    );

    failed = [];
    for (const r of results) {
      if (!r) continue;
      if (r.tradeDate && !tradeDate) tradeDate = r.tradeDate;
      if (!r.rows || !r.rows.length) {
        failed.push(r.ind); // 无数据：被限流或该行业确实无命中，下一轮重试
        continue;
      }
      for (const row of r.rows) {
        const s = normRow(row);
        if (s.code && !collected.has(s.code)) collected.set(s.code, s);
      }
    }
    todo = failed;
  }

  return { stocks: [...collected.values()], tradeDate, failed };
}

// ---------- 板块统计 ----------

const isNoise = (name) => NOISE_KEYWORDS.some((k) => name.includes(k));

function buildSector(counter, stockMap, totals, level) {
  return Object.entries(counter)
    .map(([name, hit]) => {
      const list = stockMap[name] || [];
      const total = totals[`${level}||${name}`] || 0;
      return {
        name,
        hit,
        st_hit: list.filter((x) => x.is_st).length,
        total,
        ratio: total ? Math.round(Math.min(1, hit / total) * 10000) / 10000 : null,
        stocks: list.map((s) => ({
          code: s.code,
          name: s.name,
          price: s.price,
          chg: s.chg_pct,
          industry: s.industry,
          concepts: s.concepts || [],
          is_st: s.is_st,
          amount: null, // 成交额由前端实时行情接口补全
        })),
      };
    })
    .sort((a, b) => b.hit - a.hit || a.name.localeCompare(b.name));
}

function computeBoards(stocks, totals) {
  const c = { l1: {}, l2: {}, l3: {}, con: {} };
  const m = { l1: {}, l2: {}, l3: {}, con: {} };
  for (const s of stocks) {
    for (const [lvl, key] of [
      [s.ind_l1, 'l1'],
      [s.ind_l2, 'l2'],
      [s.ind_l3, 'l3'],
    ]) {
      if (!lvl) continue;
      c[key][lvl] = (c[key][lvl] || 0) + 1;
      (m[key][lvl] = m[key][lvl] || []).push(s);
    }
    for (const cc of s.concepts) {
      c.con[cc] = (c.con[cc] || 0) + 1;
      (m.con[cc] = m.con[cc] || []).push(s);
    }
  }

  const keepCon = {};
  const noise = [];
  for (const [k, v] of Object.entries(c.con)) {
    if (isNoise(k)) noise.push({ name: k, hit: v });
    else keepCon[k] = v;
  }
  noise.sort((a, b) => b.hit - a.hit);

  return {
    boards: {
      industry_l1: buildSector(c.l1, m.l1, totals, 'industry_l1'),
      industry_l2: buildSector(c.l2, m.l2, totals, 'industry_l2'),
      industry_l3: buildSector(c.l3, m.l3, totals, 'industry_l3'),
      concept: buildSector(keepCon, m.con, totals, 'concept'),
    },
    noise,
    coverage: {
      ind_l1: Object.keys(c.l1).length,
      ind_l2: Object.keys(c.l2).length,
      ind_l3: Object.keys(c.l3).length,
      concept: Object.keys(c.con).length,
      concept_kept: Object.keys(keepCon).length,
      concept_noise: noise.length,
    },
  };
}

// ---------- 分母（板块全市场股票数）----------
// 分母变化缓慢，不需要实时查；从 Pages 上的 totals.json 读取（每日由 Actions 更新）。

async function loadTotals(env) {
  const url = env.TOTALS_URL || 'https://cuijiaweiyy.github.io/uptrend-board/totals.json';
  try {
    const r = await fetch(url, { cf: { cacheTtl: 3600, cacheEverything: true } });
    if (!r.ok) return {};
    const j = await r.json();
    return j && typeof j === 'object' ? j : {};
  } catch {
    return {};
  }
}

// ---------- KV 快照：不让用户请求承担 ~50s 的抓取耗时 ----------
// 冷构建需要 31 次问财请求 + 限速等待（约 50s），让用户干等不可接受。
// 做法：cron 定时预热并把结果写入 KV；用户请求优先读 KV，都没有时才现算。
const BOARD_KEY = 'board:latest';
const STALE_MS = 20 * 60 * 1000; // 20 分钟内视为新鲜

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

async function writeBoardKv(env, data) {
  const kv = env.UPTREND_KV;
  if (!kv) return;
  try {
    await kv.put(BOARD_KEY, JSON.stringify({ ts: Date.now(), data }));
  } catch {
    /* KV 不可用时退化为 Cache API，忽略 */
  }
}

// ---------- 日环比（新进入 / 退出）----------
// 依赖 KV 里存的上一交易日快照；未配置 KV 时优雅降级（前端显示 —）。

async function computeDiff(env, stocks, dateStr) {
  const kv = env.UPTREND_KV;
  if (!kv) {
    return { prev_date: '', new: [], exited: [], new_count: 0, exited_count: 0, has_baseline: false };
  }
  let prev = null;
  try {
    const raw = await kv.get(`snapshot:${dateStr}`);
    if (raw) prev = JSON.parse(raw);
  } catch {
    /* ignore */
  }

  const curMap = {};
  for (const s of stocks) curMap[s.code] = s;

  const brief = (s) => ({
    code: s.code,
    name: s.name,
    price: s.price,
    chg: s.chg_pct,
    ind_l1: s.ind_l1,
    ind_l2: s.ind_l2,
    ind_l3: s.ind_l3,
    concepts: s.concepts || [],
    is_st: s.is_st,
  });

  let diff;
  if (!prev) {
    diff = { prev_date: '', new: [], exited: [], new_count: 0, exited_count: 0, has_baseline: false };
  } else {
    const prevMap = {};
    for (const s of prev.stocks || []) prevMap[s.code] = s;
    const newCodes = Object.keys(curMap).filter((c) => !(c in prevMap));
    const exitedCodes = Object.keys(prevMap).filter((c) => !(c in curMap));
    const newList = newCodes.map((c) => brief(curMap[c]));
    const exitedList = exitedCodes.map((c) => brief(prevMap[c]));
    const byName = (a, b) => (a.ind_l1 || '').localeCompare(b.ind_l1 || '') || (a.name || '').localeCompare(b.name || '');
    newList.sort(byName);
    exitedList.sort(byName);
    diff = {
      prev_date: prev.date || '',
      new: newList,
      exited: exitedList,
      new_count: newList.length,
      exited_count: exitedList.length,
      has_baseline: true,
    };
  }

  // 保存今日快照（供下次对比），短期过期即可
  try {
    await kv.put(`snapshot:${dateStr}`, JSON.stringify({ date: dateStr, stocks }), {
      expirationTtl: 60 * 60 * 24 * 10,
    });
  } catch {
    /* ignore */
  }
  return diff;
}

// ---------- 主流程 ----------

function todayStr() {
  // 北京时间（UTC+8）
  const d = new Date(Date.now() + 8 * 3600 * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}`;
}

async function buildBoard(env) {
  const token = getHexinV();
  const minGap = Number(env.MIN_GAP || DEFAULT_MIN_GAP);
  const [poolRes, totals] = await Promise.all([
    fetchPool(token, 3, minGap),
    loadTotals(env),
  ]);
  const { stocks, tradeDate, failed } = poolRes;
  if (!stocks.length) {
    throw new Error('问财未返回任何数据：' + (failed.length ? `失败行业 ${failed.join('/')}` : '未知原因'));
  }

  const dateStr = tradeDate || todayStr();
  const { boards, noise, coverage } = computeBoards(stocks, totals);
  const diff = await computeDiff(env, stocks, dateStr);

  return {
    date: dateStr,
    generated_at: new Date(Date.now() + 8 * 3600 * 1000).toISOString().slice(0, 19).replace('T', ' '),
    realtime: true,
    source: '同花顺问财 iwencai（口径：上升途中 → 上升通道）',
    query: `${BASE_COND} ${EXTRA_FIELDS}`,
    pool: {
      total: stocks.length,
      st: stocks.filter((s) => s.is_st).length,
      sh: stocks.filter((s) => s.exchange === 'SH').length,
      sz: stocks.filter((s) => s.exchange === 'SZ').length,
      bj: stocks.filter((s) => s.exchange === 'BJ').length,
      // 供搜索框做名称/拼音检索（analyze.py 的 pool 只有汇总，前端搜索池一直是空的）
      stocks: stocks.map((s) => ({
        code: s.code,
        name: s.name,
        industry: s.industry,
        is_st: s.is_st,
        price: s.price,
        chg: s.chg_pct,
      })),
    },
    boards,
    noise,
    coverage,
    diff,
    _diag: { failed_industries: failed },
  };
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }
    const url = new URL(request.url);

    if (url.pathname === '/api/health') {
      try {
        const token = getHexinV();
        const probe = await wencaiQuery(`${BASE_COND} 北交所 ${EXTRA_FIELDS}`, token, 0);
        return jsonResp({
          ok: !!token && !probe.error,
          token_len: token ? token.length : 0,
          wencai_status: probe.error ? 'ERR: ' + probe.error : 'OK',
          probe_rows: probe.rows ? probe.rows.length : 0,
        });
      } catch (e) {
        return jsonResp({ ok: false, error: String(e && e.message ? e.message : e) }, 500);
      }
    }

    if (url.pathname !== '/api/board') {
      return jsonResp({ error: 'not found', hint: 'GET /api/board' }, 404);
    }

    // 缓存：避免每个访客都直打问财（限流很凶）
    const cache = caches.default;
    const cacheKey = new Request(url.toString(), { method: 'GET' });
    const hit = await cache.match(cacheKey);
    if (hit) {
      const resp = new Response(hit.body, hit);
      resp.headers.set('Access-Control-Allow-Origin', '*');
      resp.headers.set('X-Cache', 'HIT');
      return resp;
    }

    // KV 预热快照：命中即秒回，避免用户承担 ~50s 冷构建
    const kvBoard = await readBoardKv(env);
    if (kvBoard && kvBoard.fresh) {
      const resp = jsonResp(kvBoard.data, 200, {
        'Cache-Control': `public, max-age=${Number(env.CACHE_TTL || CACHE_TTL)}`,
        'X-Cache': 'KV',
        'X-Data-Age': String(Math.round((Date.now() - kvBoard.ts) / 1000)),
      });
      ctx.waitUntil(cache.put(cacheKey, resp.clone()));
      return resp;
    }

    try {
      const data = await buildBoard(env);
      // 只有完整结果才写缓存：否则一次限流导致的残缺数据会被缓存 5 分钟
      const complete = !(data._diag && data._diag.failed_industries && data._diag.failed_industries.length);
      const ttl = Number(env.CACHE_TTL || CACHE_TTL);
      const resp = jsonResp(data, 200, {
        'Cache-Control': complete ? `public, max-age=${ttl}` : 'no-store',
        'X-Cache': 'MISS',
        'X-Data-Complete': complete ? '1' : '0',
      });
      if (complete) {
        ctx.waitUntil(cache.put(cacheKey, resp.clone()));
        ctx.waitUntil(writeBoardKv(env, data)); // 供后续请求秒回
      }
      return resp;
    } catch (e) {
      // 现算失败但 KV 里有旧数据时，宁可返回旧数据也不要空白
      if (kvBoard && kvBoard.data) {
        return jsonResp(kvBoard.data, 200, {
          'Cache-Control': 'public, max-age=60',
          'X-Cache': 'KV-STALE',
        });
      }
      return jsonResp(
        { error: 'build_failed', message: String(e && e.message ? e.message : e) },
        502
      );
    }
  },

  // 定时预热：把完整结果提前算好写进 KV，让用户请求秒回（冷构建 ~50s 不能让用户等）
  async scheduled(event, env, ctx) {
    try {
      const data = await buildBoard(env);
      const complete =
        !(data._diag && data._diag.failed_industries && data._diag.failed_industries.length);
      if (complete) await writeBoardKv(env, data);
    } catch (e) {
      // cron 失败不重试：交给下一轮，避免叠加问财压力
      console.error('scheduled build failed:', e && e.message ? e.message : e);
    }
  },
};
