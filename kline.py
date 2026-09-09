# -*- coding: utf-8 -*-
"""A 股日线/周线/月线取数 + 磁盘缓存。

数据源：
  - 腾讯 https://web.ifzq.gtimg.cn/appstock/app/fqkline/get （主源，前复权）
  - 新浪 https://quotes.sina.cn/.../CN_MarketDataService.getKLineData
    （腾讯失败或北交所自动回退；JSONP）

代码前缀规则：
  6xxxxx -> sh ； 0,3xxxxx -> sz ； 4,8,92xxxxx -> bj

ECharts candlestick 数据顺序：[open, close, low, high]
腾讯返回顺序：           [date, open, close, high, low, volume]
新浪返回顺序：           {day, open, high, low, close, volume}

缓存：data/kline/{sym}_{period}_{days}.json，按 (sym, period, days) 分文件。
盘后（或不足一日交易日内）缓存为长期；盘中缓存 10 分钟过期，避免重复回源。
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import List, Tuple, Optional, Dict

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(HERE, "data", "kline")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

ALLOWED_PERIODS = ("day", "week", "month")
SCALE_MAP = {"day": "240", "week": "w1200", "month": "m600"}


def _sym_for(code: str) -> str:
    c = code.strip().lower()
    if c.startswith("6"):
        return "sh" + c
    if c.startswith(("0", "3")):
        return "sz" + c
    if c.startswith(("4", "8", "92")):
        return "bj" + c
    raise ValueError(f"无法识别市场前缀: {code}")


# ---------- 腾讯 ----------
def _fetch_tx(sym: str, period: str, days: int) -> List[list]:
    """腾讯 fqkline 返回 qfqday / qfqweek / qfqmonth（与 period 一致）。"""
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {"param": f"{sym},{period},,,{days},qfq"}
    r = requests.get(url, params=params, timeout=20, headers=UA)
    j = r.json()
    if j.get("code") != 0 or not j.get("data"):
        return []
    d = j["data"].get(sym) or {}
    rows = d.get("qfq" + period) or d.get(period) or []
    return list(rows)


# ---------- 新浪（JSONP）----------
def _fetch_sina(sym: str, period: str, days: int) -> List[dict]:
    """新浪 getKLineData（JSONP）。scale: 日=240 / 周=w1200 / 月=m600。"""
    url = ("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_="
           "/CN_MarketDataService.getKLineData")
    scale = SCALE_MAP.get(period, "240")
    params = {"symbol": sym, "scale": scale, "ma": "no", "datalen": str(days)}
    t = requests.get(url, params=params, timeout=20, headers=UA).text
    i = t.find("(")
    j = t.rfind(")")
    if i < 0 or j <= i:
        return []
    try:
        arr = json.loads(t[i + 1:j])
    except Exception:
        return []
    return list(arr) if isinstance(arr, list) else []


# ---------- 统一解析 ----------
def _normalize(rows, source: str) -> List[dict]:
    """把腾讯 list 或新浪 dict list 统一为 [{date, open, close, high, low, vol}, ...]"""
    out = []
    for r in rows:
        try:
            if source == "tx" and isinstance(r, list) and len(r) >= 6:
                out.append({
                    "date": str(r[0]),
                    "open": float(r[1]),
                    "close": float(r[2]),
                    "high": float(r[3]),
                    "low": float(r[4]),
                    "vol": float(r[5]) if r[5] not in (None, "") else 0.0,
                })
            elif source == "sina" and isinstance(r, dict):
                out.append({
                    "date": str(r.get("day") or ""),
                    "open": float(r["open"]),
                    "close": float(r["close"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "vol": float(r.get("volume") or 0),
                })
        except (ValueError, KeyError, TypeError):
            continue
    return out


# ---------- 缓存 ----------
def _cache_path(sym: str, period: str, days: int) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, f"{sym}_{period}_{days}.json")


def _is_cache_fresh(p: str, ttl_seconds: int) -> bool:
    if not os.path.exists(p):
        return False
    age = time.time() - os.path.getmtime(p)
    return age < ttl_seconds


def _bj_now():
    """北京时间。云沙箱系统时钟常为 UTC，直接用 datetime.now() 会算出错误时段。"""
    import datetime as dt
    return dt.datetime.utcnow() + dt.timedelta(hours=8)


def _trading_now() -> bool:
    """粗略判断 A 股盘中（北京时间 工作日 09:30-11:30 / 13:00-15:00）。"""
    now = _bj_now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    morning = 9 * 60 + 30 <= t <= 11 * 60 + 30
    afternoon = 13 * 60 <= t <= 15 * 60
    return morning or afternoon


def _expect_date() -> Optional[str]:
    """若已过当日开盘时间，则期望缓存里最后一根的日期就是今天（北京时间）。"""
    now = _bj_now()
    if now.weekday() >= 5:
        return None
    if now.hour * 60 + now.minute < 9 * 60 + 30:
        return None
    return now.strftime("%Y-%m-%d")


def _cache_valid(p: str, ttl_seconds: int, expect_date: Optional[str], date_field: str) -> bool:
    """缓存新鲜且（若要求）末根日期已是当日，才算有效。"""
    if not _is_cache_fresh(p, ttl_seconds):
        return False
    if not expect_date:
        return True
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception:
        return False
    if date_field == "date":            # 分时：payload["date"]
        return j.get("date") == expect_date
    dates = j.get("dates") or []        # K 线：payload["dates"][-1]
    return bool(dates) and dates[-1] == expect_date


# ---------- 主入口 ----------
def get_kline(code: str, period: str = "day", days: int = 70) -> Optional[Dict]:
    """取单只股票 K 线，自动主源+回退+缓存。

    返回 {code, name, period, days, dates, ohlc([o,c,l,h]), volumes, ma{5,10,20,60}}
    字段顺序按 ECharts candlestick 习惯：open, close, low, high。
    """
    period = period if period in ALLOWED_PERIODS else "day"
    days = max(20, min(500, int(days)))
    sym = _sym_for(code)

    cache_file = _cache_path(sym, period, days)
    ttl = 300 if _trading_now() else 3600
    if _cache_valid(cache_file, ttl, _expect_date(), "dates"):
        try:
            return json.load(open(cache_file, encoding="utf-8"))
        except Exception:
            pass  # 缓存损坏则回源

    # 1) 腾讯
    try:
        raw = _fetch_tx(sym, period, days)
    except Exception:
        raw = []
    rows = _normalize(raw, "tx")

    # 2) 腾讯失败或北交所 < 20 根 -> 新浪
    is_bj = sym.startswith("bj")
    if (not rows) or (is_bj and len(rows) < 20):
        try:
            raw2 = _fetch_sina(sym, period, days)
        except Exception:
            raw2 = []
        rows2 = _normalize(raw2, "sina")
        if len(rows2) > len(rows):
            rows = rows2

    if not rows:
        return None

    # 部分网络出口下腾讯日线不含当日 bar → 用当日分时合成
    rows = _append_today_bar(rows, code, days)

    dates = [r["date"] for r in rows]
    ohlc = [[r["open"], r["close"], r["low"], r["high"]] for r in rows]
    volumes = [r["vol"] for r in rows]
    closes = [r["close"] for r in rows]

    def ma(n):
        return [None] * (n - 1) + [
            round(sum(closes[i - n + 1:i + 1]) / n, 3) for i in range(n - 1, len(closes))
        ]

    payload = {
        "code": code,
        "name": _guess_name(code),
        "period": period,
        "days": days,
        "dates": dates,
        "ohlc": ohlc,
        "volumes": volumes,
        "ma": {"ma5": ma(5), "ma10": ma(10), "ma20": ma(20), "ma30": ma(30)},
        "fetched_at": int(time.time()),
    }
    payload = _inject_snapshot(payload, get_snapshot(code))
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass
    return payload


def _append_today_bar(rows: List[dict], code: str, days: int) -> List[dict]:
    """若日线末根不是今天（部分网络出口下腾讯不返回当日 bar），
    用当日分时合成一根今日 K：开=首价、收=末价、高/低=极值、量=分钟量合计。
    """
    today = _expect_date()
    if not today or not rows:
        return rows
    if rows[-1]["date"] == today:
        return rows
    try:
        m = get_minute(code)
    except Exception:
        return rows
    if not m or m.get("date") != today or not m.get("prices"):
        return rows
    prices = m["prices"]
    vols = m.get("vols") or []
    rows = rows + [{
        "date": today,
        "open": prices[0],
        "close": prices[-1],
        "high": max(prices),
        "low": min(prices),
        "vol": float(sum(vols)) if vols else 0.0,
    }]
    if len(rows) > days:
        rows = rows[-days:]
    return rows


def _guess_name(code: str) -> str:
    """优先从本项目已有 pool 文件里捞股票名（避免额外请求）。"""
    pool_dir = os.path.join(HERE, "data")
    if not os.path.isdir(pool_dir):
        return code
    for fn in sorted(os.listdir(pool_dir), reverse=True):
        if not (fn.startswith("pool_") and fn.endswith(".json")):
            continue
        try:
            arr = json.load(open(os.path.join(pool_dir, fn), encoding="utf-8")).get("stocks") or []
        except Exception:
            continue
        for s in arr:
            if s.get("code") == code:
                return s.get("name") or code
    return code


# ---------- 实时快照（量比/换手率/市盈率/市值/流通/最高/最低/今开/昨收/成交额） ----------
def _parse_qt_line(line: str) -> Optional[Dict]:
    """解析单条 v_<sym>="...~...~..."，返回 dict 或 None。

    索引（基于腾讯 qt.gtimg.cn 实测，列以 ~ 分隔；不足则字段为 None）：
      [0]  market  1=沪 / 51=深 / 0=北 / ...
      [1]  name
      [2]  code
      [3]  now  当前价
      [4]  prev_close  昨收
      [5]  open  今开
      [6]  vol  当日累计成交量(手)
      [9]  price_again
      [30] timestamp
      [31] change  涨跌额
      [32] change_pct  涨跌幅
      [33] daily_high
      [34] daily_low
      [37] amount  当日累计成交额(元，注意是×1e4？API 直接是元；以下确认：5030056094 元 ≈ 50.3 亿元 — 是元)
      [38] volume_ratio  量比
      [39] pe_ttm  市盈率 TTM
      [43] amplitude  振幅 %
      [44] mv_1  市值(亿)  — 实测：沪/深股票该字段为流通市值
      [45] mv_2  总市值(亿)
      [46] turnover_rate  换手率 %
    """
    if not line:
        return None
    try:
        # v_sh600487="...";
        s = line.strip()
        if s.startswith("v_"):
            eq = s.find("=")
            if eq < 0: return None
            sym = s[2:eq].strip()
            s = s[eq + 1:].strip()
        else:
            return None
        if s.endswith(";"): s = s[:-1]
        if s.startswith('"') and s.endswith('"'):
            s = s[1:-1]
        parts = s.split("~")
        def at(i):
            try:
                v = parts[i].strip()
                if v == "": return None
                return float(v)
            except (IndexError, ValueError):
                return None
        def ats(i):
            try: return parts[i].strip()
            except IndexError: return ""
        return {
            "sym": sym,
            "market": ats(0),       # '1' / '51' / '0' 等
            "name": ats(1),
            "code": ats(2),
            "now": at(3),
            "prev_close": at(4),
            "open": at(5),
            "vol": at(6),           # 手
            "high": at(33),
            "low": at(34),
            "amount": (at(37) or 0) * 10000.0,  # 万元 → 元
            "volume_ratio": at(38),
            "pe_ttm": at(39),
            "amplitude": at(43),
            "mv_circ": at(44),      # 流通市值(亿)
            "mv_total": at(45),     # 总市值(亿)
            "turnover": at(46),     # %
        }
    except Exception:
        return None


def get_snapshot(code: str) -> Optional[Dict]:
    """腾讯 qt.gtimg.cn 实时快照。失败返回 None。"""
    sym = _sym_for(code)
    try:
        r = requests.get("https://qt.gtimg.cn/q=" + sym, timeout=10, headers=UA)
    except Exception:
        return None
    text = r.text or ""
    # 按行扫描（接口允许一次查多个，q=shA,szB）
    for line in text.splitlines():
        if "_" + sym in line or line.startswith("v_" + sym):
            d = _parse_qt_line(line)
            if d and d.get("code") == code:
                return d
    return None


def _inject_snapshot(payload: Dict, snap: Optional[Dict]) -> Dict:
    """把实时快照合并进 K 线/分时返回 dict，键名同花顺风格。

    新增字段：exchange / prev_close / daily_high / daily_low / daily_open /
              daily_vol / daily_amt / lb / hs / pe_ttm / mv / cmv / amp / last
    """
    if not snap:
        return payload
    # 名称兜底：_guess_name 只在本地 pool 里找，池外股票会回落成代码，
    # 而 qt 快照一定带真实名称，优先补上。
    if snap.get("name") and payload.get("name") == payload.get("code"):
        payload["name"] = snap["name"]
    # exchange 推断（个股代码前缀优先；92/4/8 = 北交所，6 = 沪，0/3 = 深）
    mkt = str(snap.get("market") or "")
    c = str(snap.get("code") or "")
    if c.startswith(("92", "4", "8")):
        exchange = "BJ"
    elif c.startswith("6"):
        exchange = "SH"
    elif c.startswith(("0", "3", "1", "2")):
        exchange = "SZ"
    elif mkt == "0":
        exchange = "BJ"
    elif mkt == "51":
        exchange = "SZ"
    else:
        exchange = "SH"
    last = {
        "close": snap.get("now"),
        "open":  snap.get("open"),
        "high":  snap.get("high"),
        "low":   snap.get("low"),
        "vol":   snap.get("vol"),
        "amount":snap.get("amount"),
    }
    payload["exchange"]   = exchange
    payload["prev_close"] = snap.get("prev_close")
    payload["daily_open"] = snap.get("open")
    payload["daily_high"] = snap.get("high")
    payload["daily_low"]  = snap.get("low")
    payload["daily_vol"]  = snap.get("vol")
    payload["daily_amt"]  = snap.get("amount")
    payload["lb"]         = snap.get("volume_ratio")
    payload["hs"]         = snap.get("turnover")
    payload["pe_ttm"]     = snap.get("pe_ttm")
    payload["mv"]         = snap.get("mv_total")
    payload["cmv"]        = snap.get("mv_circ")
    payload["amp"]        = snap.get("amplitude")
    payload["last"]       = last
    return payload


# ---------- 分时 ----------
def _fetch_tx_minute(sym: str):
    """腾讯分时：j['data'][sym]['data']['data'] = ['HHMM 价格 累计量(手) 累计额(元)', ...]。"""
    url = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
    r = requests.get(url, params={"code": sym}, timeout=20, headers=UA)
    j = r.json()
    node = (j.get("data") or {}).get(sym) or {}
    d = node.get("data") or {}
    raw = d.get("data") or []
    ymd = str(d.get("date") or "")
    # 昨收：qt 节点第 5 列（防御式解析，取不到回退首价）
    prev_close = None
    qt = node.get("qt") or {}
    arr = qt.get(sym)
    if isinstance(arr, list) and len(arr) > 4:
        try:
            prev_close = float(arr[4])
        except (TypeError, ValueError):
            prev_close = None
    return ymd, raw, prev_close


def get_minute(code: str) -> Optional[Dict]:
    """取单只股票当日分时：价格线 + 均价线 + 每分钟成交量。

    返回 {code, name, period:'minute', date, times, prices, vols(每分钟,手), avg, prev_close}
    """
    sym = _sym_for(code)
    cache_file = _cache_path(sym, "minute", 1)
    ttl = 60 if _trading_now() else 3600
    if _cache_valid(cache_file, ttl, _expect_date(), "date"):
        try:
            return json.load(open(cache_file, encoding="utf-8"))
        except Exception:
            pass

    try:
        ymd, raw, prev_close = _fetch_tx_minute(sym)
    except Exception:
        ymd, raw, prev_close = "", [], None
    if not raw:
        return None

    times, prices, cums_v, cums_a = [], [], [], []
    for row in raw:
        try:
            parts = str(row).split()
            if len(parts) < 3:
                continue
            hm = parts[0]
            times.append(hm[:2] + ":" + hm[2:4])
            prices.append(float(parts[1]))
            cums_v.append(float(parts[2]))   # 累计量（手）
            cums_a.append(float(parts[3]))   # 累计额（元）
        except (ValueError, IndexError):
            continue
    if not prices:
        return None
    if prev_close is None:
        prev_close = prices[0]

    # 每分钟量 = 累计量差分；均价优先用 累计额/(累计量*100)，
    # 但不同股票该字段口径不一（有的差 100 倍、有的缺失），
    # 算出的均价若不在当日价格区间（0.5x~2x 容差）内，回退为价格滑动均值。
    pmin, pmax = min(prices), max(prices)
    vols, avg = [], []
    run_sum = 0.0
    for i in range(len(cums_v)):
        pv = cums_v[i] - (cums_v[i - 1] if i else 0)
        vols.append(max(0.0, pv))
        run_sum += prices[i]
        cand = None
        if i < len(cums_a) and cums_a[i] > 0 and cums_v[i] > 0:
            cand = cums_a[i] / (cums_v[i] * 100.0)
        if cand is None or cand < pmin * 0.5 or cand > pmax * 2:
            cand = run_sum / (i + 1)
        avg.append(round(cand, 3))

    payload = {
        "code": code,
        "name": _guess_name(code),
        "period": "minute",
        "date": f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}" if len(ymd) == 8 else ymd,
        "times": times,
        "prices": prices,
        "vols": vols,
        "avg": avg,
        "prev_close": prev_close,
        "fetched_at": int(time.time()),
    }
    payload = _inject_snapshot(payload, get_snapshot(code))
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass
    return payload


def get_in_chart_marks(date_set=None) -> List[str]:
    """返回"上升途中入选日"序列：YYYY-MM-DD 列表。前端用作 markLine 标记。"""
    if date_set is not None:
        return sorted(date_set)
    pool_dir = os.path.join(HERE, "data")
    if not os.path.isdir(pool_dir):
        return []
    seen = set()
    for fn in sorted(os.listdir(pool_dir)):
        if not (fn.startswith("pool_") and fn.endswith(".json")):
            continue
        m = re.match(r"pool_(\d{8})\.json", fn)
        if not m:
            continue
        ymd = m.group(1)
        date_iso = f"{ymd[0:4]}-{ymd[4:6]}-{ymd[6:8]}"
        seen.add(date_iso)
    return sorted(seen)


# ---------- 大盘指数（底部 Tab 上证 · 拉一次缓存） ----------
def get_market_index(symbol: str = "sh000001") -> Optional[Dict]:
    """返回 {nm, now, prev_close, chg, pct}。symbol: sh000001 / sz399001 / sz399006。"""
    try:
        r = requests.get("https://qt.gtimg.cn/q=" + symbol, timeout=10, headers=UA)
    except Exception:
        return None
    snap = None
    for line in (r.text or "").splitlines():
        snap = _parse_qt_line(line)
        if snap:
            break
    if not snap:
        return None
    now = snap.get("now") or 0
    prev = snap.get("prev_close") or 0
    chg = (now - prev) if (now and prev) else 0
    pct = (chg / prev * 100) if prev else 0
    return {
        "sym": symbol,
        "nm": snap.get("name") or symbol,
        "now": now,
        "prev_close": prev,
        "chg": chg,
        "pct": pct,
        "fetched_at": int(time.time()),
    }


if __name__ == "__main__":
    import sys
    code = sys.argv[1] if len(sys.argv) > 1 else "688078"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 70
    d = get_kline(code, "day", days)
    if not d:
        print("FAIL: no data")
    else:
        print(f"{d['code']} {d['name']}  {d['period']} {d['days']}d  rows={len(d['dates'])}")
        print("first:", d["dates"][0], d["ohlc"][0])
        print("last :", d["dates"][-1], d["ohlc"][-1])
        print("MA30 last:", d["ma"]["ma30"][-1])
        print("cache:", _cache_path(_sym_for(code), "day", days))
