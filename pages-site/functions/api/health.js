// 轻量探活端点（供前端判断 pages.dev 是否可达，避免被墙时长时间挂起）
import { getHexinV } from '../../../worker/index.js';

export async function onRequestGet() {
  try {
    const tk = getHexinV();
    return new Response(JSON.stringify({ ok: !!tk, token_len: tk ? tk.length : 0 }), {
      headers: { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' },
    });
  } catch (e) {
    return new Response(JSON.stringify({ ok: false, error: String(e && e.message ? e.message : e) }), {
      status: 500,
      headers: { 'Content-Type': 'application/json; charset=utf-8', 'Access-Control-Allow-Origin': '*' },
    });
  }
}
