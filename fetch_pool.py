# -*- coding: utf-8 -*-
"""抓取「上升途中」股票池（同花顺问财口径），含三级行业与概念归属。

分段策略：问财 v2 单次最多返回 100 条且 page 分页无效，
因此按交易所分段；若某段仍满 100 条（被截断），再按一级行业细分。
"""
import datetime as dt
import json
import os
import sys
import time

import ths

BASE_COND = "上升途中"
EXTRA_FIELDS = "所属同花顺行业 所属概念"
SEGMENTS = ["沪市A股", "深市A股", "北交所"]

INDUSTRY_L1 = [
    "农林牧渔", "基础化工", "钢铁", "有色金属", "电子", "汽车", "家用电器",
    "食品饮料", "纺织服饰", "轻工制造", "医药生物", "公用事业", "交通运输",
    "房地产", "商贸零售", "社会服务", "银行", "非银金融", "综合",
    "建筑材料", "建筑装饰", "电力设备", "机械设备", "国防军工",
    "计算机", "传媒", "通信", "煤炭", "石油石化", "环保", "美容护理",
]

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PERPAGE = 100


def _dyn(r, prefix):
    for k, v in r.items():
        if k.startswith(prefix):
            return v
    return None


def norm_row(r):
    def pick(*keys):
        for k in keys:
            if k in r and r[k] not in (None, "", "--"):
                return r[k]
        return None

    def fnum(v):
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return None

    industry_full = str(pick("所属同花顺行业") or "")
    parts = [p.strip() for p in industry_full.split("-") if p.strip()]
    concepts_raw = str(pick("所属概念") or "")
    concepts = [c.strip() for c in concepts_raw.replace(";", "|").split("|") if c.strip()]

    code6 = str(pick("code") or "")
    full_code = str(pick("股票代码") or code6)
    name = str(pick("股票简称") or "")
    market_code = str(pick("market_code") or "")
    exchange = ths.MARKET_MAP.get(
        market_code, full_code.split(".")[-1] if "." in full_code else ""
    )

    return {
        "code": code6,
        "full_code": full_code,
        "name": name,
        "exchange": exchange,
        "price": fnum(pick("最新价")),
        "chg_pct": fnum(pick("最新涨跌幅")),
        "ind_l1": parts[0] if len(parts) > 0 else "",
        "ind_l2": parts[1] if len(parts) > 1 else "",
        "ind_l3": parts[2] if len(parts) > 2 else "",
        "industry": "-".join(parts),
        "concepts": concepts,
        "concept_count": len(concepts),
        "buy_signal": pick("买入信号inter") or _dyn(r, "买入信号inter"),
        "tech_pattern": pick("技术形态") or _dyn(r, "技术形态"),
        "is_st": ("ST" in name.upper()) or name.startswith("*"),
    }


def fetch_segment(cond, extra=EXTRA_FIELDS):
    """抓取一个分段，若被 100 条截断则按一级行业细分。返回 (rows, trade_date)。"""
    q = f"{cond} {extra}".strip()
    rows, meta = ths.query(q, perpage=PERPAGE)
    total = (meta or {}).get("row_count", 0)
    trade_date = (meta or {}).get("trade_date", "")
    print(f"  [段] {cond:<12} 返回 {len(rows):>3} 条 / 问财总数 {total} / 交易日 {trade_date}")
    if len(rows) < PERPAGE:
        return rows, trade_date
    # 被截断 -> 按一级行业细分
    print(f"  [段] {cond} 达上限，按一级行业细分...")
    out = []
    collected = set()
    for ind in INDUSTRY_L1:
        sub, m2 = ths.query(f"{cond} {ind} {extra}".strip(), perpage=PERPAGE)
        if not sub:
            continue
        if not trade_date:
            trade_date = (m2 or {}).get("trade_date", "")
        for r in sub:
            c = r.get("code")
            if c and c not in collected:
                collected.add(c)
                out.append(r)
        time.sleep(0.2)
    print(f"  [段] {cond} 细分后累计 {len(out)} 条")
    return out, trade_date


def main():
    today = dt.date.today().strftime("%Y%m%d")
    print(f"开始抓取：{BASE_COND}（同花顺问财口径）  系统日期 {today}")
    raw = []
    trade_date = ""
    for seg in SEGMENTS:
        rows, td = fetch_segment(f"{BASE_COND} {seg}")
        raw += rows
        trade_date = trade_date or td
        time.sleep(0.3)

    stocks, seen = [], set()
    for r in raw:
        s = norm_row(r)
        if s["code"] and s["code"] not in seen:
            seen.add(s["code"])
            stocks.append(s)

    if not stocks:
        print("抓取失败：无数据")
        sys.exit(1)

    # 以问财返回的交易日期为准，避免节假日运行时把上一交易日数据标成当天
    date_str = trade_date or today
    if date_str != today:
        print(f"  注意：问财交易日 {date_str} ≠ 系统日期 {today}，以交易日为准")
    payload = {
        "date": date_str,
        "trade_date": date_str,
        "query": f"{BASE_COND} {EXTRA_FIELDS}",
        "source": "同花顺问财 iwencai",
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(stocks),
        "stocks": stocks,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"pool_{date_str}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT_DIR, "latest_date.txt"), "w", encoding="utf-8") as f:
        f.write(date_str)

    st_cnt = sum(1 for s in stocks if s["is_st"])
    print(f"\n抓取完成 -> {path}")
    print(f"  股票数: {len(stocks)}（其中 ST {st_cnt} 只）")
    ex = {}
    for s in stocks:
        ex[s["exchange"]] = ex.get(s["exchange"], 0) + 1
    print(f"  交易所分布: {ex}")
    print(f"  行业覆盖: {len({s['industry'] for s in stocks})} 个三级行业 / "
          f"{len({s['ind_l1'] for s in stocks})} 个一级行业")
    print(f"  概念覆盖: {len({c for s in stocks for c in s['concepts']})} 个独立概念")


if __name__ == "__main__":
    main()
