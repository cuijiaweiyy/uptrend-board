# -*- coding: utf-8 -*-
"""同花顺问财抓取核心模块。

核心结论（2026-09-04 实测）：
  - 接口 https://www.iwencai.com/unifiedwap/unified-wap/v2/result/get-robot-data
  - 参数必须以 form 表单提交（data=），用 json= 会返回 -302 缺少必要参数
  - 必须带 hexin-v 反爬头（pywencai.headers.get_token 用 node 生成）
  - 数据路径 data.answer[0].txt[0].content.components[0].data.datas
"""
import re
import threading
import time

import requests as rq

from pywencai.headers import get_token

URL = "https://www.iwencai.com/unifiedwap/unified-wap/v2/result/get-robot-data"
UA_PC = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
ADD_INFO = (
    '{"urp":{"scene":1,"company":1,"business":1},'
    '"contentType":"json","searchInfo":true}'
)

# market_code -> 交易所
MARKET_MAP = {"17": "SH", "33": "SZ", "151": "BJ"}

# ---- 全局限速：问财对短时间高频请求会限流（返回非 JSON 触发 JSONDecodeError） ----
# 实测 5 并发连续 149 次请求会导致大面积失败，故用令牌间隔把全局速率压到 ~1.4 req/s。
_MIN_INTERVAL = 0.45
_last_req = [0.0]
_lock = threading.Lock()


def _throttle():
    with _lock:
        now = time.time()
        gap = now - _last_req[0]
        if 0 < gap < _MIN_INTERVAL:
            time.sleep(_MIN_INTERVAL - gap)
        _last_req[0] = time.time()


def _shape_meta(meta, rows=None):
    """把问财 meta 规整为 {'row_count': int, 'trade_date': 'YYYYMMDD'}。"""
    out = {"row_count": 0, "trade_date": ""}
    if isinstance(meta, dict):
        extra = meta.get("extra") or {}
        for src in (meta, extra):
            if not isinstance(src, dict):
                continue
            for key in ("row_count", "code_count"):
                v = src.get(key)
                if v:
                    try:
                        out["row_count"] = max(out["row_count"], int(v))
                    except (TypeError, ValueError):
                        pass
        # 交易日期：condition 里形如 "交易日期 20260904"
        cond = extra.get("condition") or meta.get("condition") or ""
        m = re.search(r"交易日期[^\d]{0,4}(\d{8})", str(cond))
        if m:
            out["trade_date"] = m.group(1)
    # 兜底：从带日期后缀的列名里取，如「技术形态[20260904]」
    if not out["trade_date"] and rows:
        for row in rows[:3]:
            if not isinstance(row, dict):
                continue
            for k in row.keys():
                m = re.search(r"(\d{8})", str(k))
                if m:
                    out["trade_date"] = m.group(1)
                    break
            if out["trade_date"]:
                break
    return out


def _extract_datas(payload_json):
    """从问财响应中稳健取出股票行列表。"""
    try:
        answers = payload_json["data"]["answer"]
    except (KeyError, TypeError):
        return [], None
    if not isinstance(answers, list):
        return [], None
    for ans in answers:
        if not isinstance(ans, dict):
            continue
        txts = ans.get("txt") or []
        if not isinstance(txts, list):
            continue
        for txt in txts:
            if not isinstance(txt, dict):
                continue
            content = txt.get("content")
            if not isinstance(content, dict):
                continue
            comps = content.get("components") or []
            if not isinstance(comps, list):
                continue
            for comp in comps:
                if not isinstance(comp, dict):
                    continue
                data = comp.get("data") or {}
                if not isinstance(data, dict):
                    continue
                rows = data.get("datas")
                if rows:
                    meta = data.get("meta")
                    return rows, meta if isinstance(meta, dict) else {}
    return [], None


def query(question, page=1, perpage=100, retry=4, sleep=1.5,
          sort_index=None, sort_way=None, timeout=(8, 30)):
    """查询问财，返回 (rows, meta)。失败返回 ([], None)。

    已知限制（2026-09-04 实测）：问财 v2 接口的 page 分页无效，
    page=1/2/3 返回完全相同的 100 条。单次上限 100 条。
    突破方式：用 sort_index + sort_way 双向排序各取一次再合并。
    """
    payload = {
        "question": question,
        "perpage": perpage,
        "page": page,
        "secondary_intent": "stock",
        "log_info": '{"input_type":"typewrite"}',
        "source": "Ths_iwencai_Xuangu",
        "version": "2.0",
        "query_area": "",
        "block_list": "",
        "add_info": ADD_INFO,
    }
    if sort_index:
        payload["urp_sort_index"] = sort_index
    if sort_way:
        payload["urp_sort_way"] = sort_way
    last_err = None
    for attempt in range(retry):
        try:
            _throttle()
            headers = {"hexin-v": get_token(), "User-Agent": UA_PC}
            res = rq.post(URL, data=payload, headers=headers, timeout=timeout)
            j = res.json()
            if j.get("status_code") == 0:
                rows, meta = _extract_datas(j)
                if rows:
                    return rows, _shape_meta(meta, rows)
                last_err = "响应正常但无数据行"
            else:
                last_err = f'status_code={j.get("status_code")} msg={j.get("status_msg")}'
        except Exception as e:  # noqa: BLE001
            last_err = f"{type(e).__name__}: {e}"
        time.sleep(sleep * (attempt + 1))
    print(f"[warn] 查询失败 question={question!r} page={page} -> {last_err}")
    return [], None


def query_all(question, perpage=100, max_pages=6, sleep=1.2):
    """取全量，返回 (rows, meta)。

    注意：问财 v2 的 page 分页实际无效（page=1/2/3 返回同一批 100 条），
    因此本函数不再依赖翻页，单次最多返回 100 条。
    需要超过 100 条时请改用 fetch_segment 的分段策略。
    """
    rows, meta = query(question, page=1, perpage=perpage)
    return rows, meta


def query_count(question, retry=3, fast=False):
    """只问数量：perpage=1 轻量请求，从 meta 读 row_count。

    fast=True 用于云端分母查询：云端 IP 易被问财风控导致连接挂起，
    缩短超时+单次重试，被封就快速失败（命中数排名不受影响）。
    """
    to = (5, 8) if fast else (8, 30)
    rt = 1 if fast else retry
    _, meta = query(question, page=1, perpage=1, retry=rt, timeout=to)
    return (meta or {}).get("row_count", 0)
