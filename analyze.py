# -*- coding: utf-8 -*-
"""板块统计：分层统计行业与概念的命中数与渗透率，并剔除无区分度的属性标签。

分母（板块全市场股票数）获取策略：
  - 默认本地 SKIP_TOTAL=0：实时查问财（带限速+多轮补抓）。
  - 云端 SKIP_TOTAL=1：优先复用 data/totals_cache.json，避免云 IP 风控导致分母查询极慢/限流。
  - 两种模式下都会把查到的分母写回 totals_cache.json，供下次复用。
  - SKIP 模式下若某板块缓存缺失，会自动补查一次（兜底，保证不空）。
"""
import datetime as dt
import json
import os
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import ths

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")

# ---- 无区分度标签黑名单（交易通道 / 指数成分 / 风格估值 / 持仓属性） ----
NOISE_KEYWORDS = [
    "融资融券", "沪股通", "深股通", "港股通", "转融券", "两融",
    "融资标的", "融券标的", "债券标的",
    "ST板块", "ST股", "退市", "风险警示", "面值退市",
    "沪深300", "中证", "上证50", "上证180", "上证380", "MSCI",
    "富时罗素", "标普", "成分股", "深证100", "创业板综", "科创50", "北证50",
    "高股息", "破净", "绩优", "百元股", "低价股", "高价股",
    "大盘股", "中盘股", "小盘股", "微盘股", "超跌", "滞涨", "活跃股", "强势股",
    "重仓", "QFII", "北向", "陆股通", "社保基金", "养老金", "信托", "公募",
    "专精特新", "次新股", "送转",
]

# 分母查询下限：命中数低于该值的板块渗透率无统计意义，不查分母
MIN_HIT_FOR_TOTAL = 2

# 本地默认实时查；云端默认走缓存（环境变量覆盖）
SKIP_DEFAULT = os.environ.get("SKIP_TOTAL", "0") == "1"


def is_noise(name):
    return any(k in name for k in NOISE_KEYWORDS)


def _ck(level, name):
    return f"{level}||{name}"


def _load_cache():
    p = os.path.join(DATA_DIR, "totals_cache.json")
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_cache(cache):
    p = os.path.join(DATA_DIR, "totals_cache.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def latest_date():
    p = os.path.join(DATA_DIR, "latest_date.txt")
    if os.path.exists(p):
        s = open(p, encoding="utf-8").read().strip()
        if s:
            return s
    return dt.date.today().strftime("%Y%m%d")


def _clean_name(n):
    """问财对带罗马数字的细分行业名可能无数据，去掉后重试。"""
    return re.sub(r"[ⅢⅡⅠ]", "", str(n)).strip()


def _run_pool(names, workers, label, total_n):
    out = {}
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(ths.query_count, n): n for n in names}
        for f in as_completed(futs):
            n = futs[f]
            try:
                out[n] = f.result() or 0
            except Exception:  # noqa: BLE001
                out[n] = 0
            done += 1
            if done % 30 == 0:
                print(f"    {label} 分母进度 {done}/{total_n}")
    return out


def fetch_totals(names, workers=2, label="", rounds=3):
    """并发查询各板块全市场股票数（实时查问财）。"""
    names = [n for n in names if n]
    out = {n: 0 for n in names}
    if not names:
        return out
    for rd in range(rounds):
        todo = [n for n in names if not out[n]]
        if not todo:
            break
        if rd:
            wait = 5 * rd
            print(f"    {label} 第 {rd + 1} 轮补抓 {len(todo)} 个（等待 {wait}s 避开限流）")
            time.sleep(wait)
        alias, qset = {}, []
        for n in todo:
            qset.append(n)
            c = _clean_name(n)
            if c and c != n:
                alias[c] = n
                qset.append(c)
        qset = list(dict.fromkeys(qset))
        res = _run_pool(qset, workers, label, len(qset))
        for n in todo:
            out[n] = res.get(n, 0)
        for c, n in alias.items():
            if not out[n]:
                out[n] = res.get(c, 0)
        ok = sum(1 for n in names if out[n])
        print(f"    {label} 分母覆盖 {ok}/{len(names)}")
    return out


def resolve_totals(names, cache, level, label, skip):
    """先查缓存（skip 模式为主），缓存缺失再实时补查并写回缓存。

    云端 skip 模式下，缺失项只做「单轮高并发」实时补查（不再多轮等待），
    把分析耗时从数分钟压到几十秒；个别仍缺失的板块渗透率记为 0（仅展示命中数）。
    写回的缓存会在后续每日运行中逐步预热，渗透率覆盖越来越全。
    """
    out = {}
    todo = []
    for n in names:
        if skip:
            c = cache.get(_ck(level, n))
            if c:
                out[n] = c
                continue
            todo.append(n)   # 云端 skip：缺失项入补查队列，但只补查一次
            continue
        c = cache.get(_ck(level, n))
        if c:
            out[n] = c
            continue
        todo.append(n)
    if todo:
        if skip:
            # 单轮、高并发、不等待：workers=6 / rounds=1，把耗时压到秒级
            print(f"    {label} 缓存缺失 {len(todo)} 个，单轮高并发补查（不空等）")
            res = fetch_totals(todo, workers=10, label=label, rounds=1)
        else:
            res = fetch_totals(todo, label=label)
        for n in todo:
            out[n] = res.get(n, 0)
            if out[n]:
                cache[_ck(level, n)] = out[n]
    return out


def _stock_brief(s):
    return {
        "code": s["code"],
        "name": s["name"],
        "price": s["price"],
        "chg": s["chg_pct"],
        "industry": s["industry"],
        "concepts": s.get("concepts") or [],
        "is_st": s["is_st"],
        "amount": None,  # 由 build_html.enrich_amounts 补全
    }


def build_board(counter, stock_map, totals):
    board = []
    for name, hit in counter.items():
        if not name:
            continue
        stocks = stock_map.get(name, [])
        st_hit = sum(1 for x in stocks if x["is_st"])
        total = totals.get(name, 0)
        board.append({
            "name": name,
            "hit": hit,
            "st_hit": st_hit,
            "total": total,
            "ratio": round(min(1.0, hit / total), 4) if total else None,
            "stocks": [_stock_brief(x) for x in stocks],
        })
    board.sort(key=lambda x: (-x["hit"], x["name"]))
    return board


def compute_diff(date_str):
    """对比上一交易日股票池，返回当日新进入 / 退出的个股。

    依赖 data/pool_<date>.json 的历史快照（由 fetch_pool 每日生成）。
    若无更早的快照，返回 has_baseline=False（首次统计，无对比基准）。
    """
    pool_path = os.path.join(DATA_DIR, f"pool_{date_str}.json")
    if not os.path.exists(pool_path):
        return None
    cur = json.load(open(pool_path, encoding="utf-8"))
    cur_map = {s["code"]: s for s in cur["stocks"]}
    cur_codes = set(cur_map)

    # 找上一交易日的池子（严格小于当日的最大日期）
    prev_date = ""
    try:
        for fn in os.listdir(DATA_DIR):
            if fn.startswith("pool_") and fn.endswith(".json"):
                d = fn[len("pool_"):-len(".json")]
                if len(d) == 8 and d < date_str and d > prev_date:
                    prev_date = d
    except Exception:  # noqa: BLE001
        pass

    if not prev_date:
        return {"prev_date": "", "new": [], "exited": [],
                "new_count": 0, "exited_count": 0, "has_baseline": False}

    prev = json.load(open(os.path.join(DATA_DIR, f"pool_{prev_date}.json"), encoding="utf-8"))
    prev_map = {s["code"]: s for s in prev["stocks"]}
    prev_codes = set(prev_map)

    def brief(s):
        return {
            "code": s.get("code"), "name": s.get("name"),
            "price": s.get("price"), "chg": s.get("chg_pct"),
            "ind_l1": s.get("ind_l1"), "ind_l2": s.get("ind_l2"), "ind_l3": s.get("ind_l3"),
            "concepts": s.get("concepts", []), "is_st": s.get("is_st", False),
        }

    new_codes = cur_codes - prev_codes
    exited_codes = prev_codes - cur_codes
    new = [brief(cur_map[c]) for c in new_codes]
    exited = [brief(prev_map[c]) for c in exited_codes]
    new.sort(key=lambda x: (x["ind_l1"] or "", x["name"] or ""))
    exited.sort(key=lambda x: (x["ind_l1"] or "", x["name"] or ""))
    return {"prev_date": prev_date, "new": new, "exited": exited,
            "new_count": len(new), "exited_count": len(exited), "has_baseline": True}


def main(date_str=None):
    date_str = date_str or latest_date()
    pool_path = os.path.join(DATA_DIR, f"pool_{date_str}.json")
    if not os.path.exists(pool_path):
        print(f"找不到股票池文件：{pool_path}")
        raise SystemExit(1)
    with open(pool_path, encoding="utf-8") as f:
        pool = json.load(f)
    stocks = pool["stocks"]

    # ---------- 计数 ----------
    c_l1, c_l2, c_l3, c_concept = Counter(), Counter(), Counter(), Counter()
    m_l1, m_l2, m_l3, m_concept = {}, {}, {}, {}
    for s in stocks:
        for lvl, counter, mp in (
            (s["ind_l1"], c_l1, m_l1),
            (s["ind_l2"], c_l2, m_l2),
            (s["ind_l3"], c_l3, m_l3),
        ):
            if lvl:
                counter[lvl] += 1
                mp.setdefault(lvl, []).append(s)
        for c in s["concepts"]:
            c_concept[c] += 1
            m_concept.setdefault(c, []).append(s)

    # ---------- 概念清洗 ----------
    keep_concept = Counter({k: v for k, v in c_concept.items() if not is_noise(k)})
    noise = [(k, v) for k, v in c_concept.items() if is_noise(k)]
    noise.sort(key=lambda x: -x[1])

    # ---------- 分母 ----------
    skip = SKIP_DEFAULT
    cache = _load_cache()
    print(f"  分母策略：{'缓存复用(SKIP_TOTAL=1)' if skip else '实时查问财'}（缓存命中 {sum(1 for k in cache)} 项）")
    t_l1 = resolve_totals(list(c_l1.keys()), cache, "industry_l1", "一级行业", skip)
    t_l2 = resolve_totals(list(c_l2.keys()), cache, "industry_l2", "二级行业", skip)
    t_l3 = resolve_totals([k for k, v in c_l3.items() if v >= MIN_HIT_FOR_TOTAL],
                          cache, "industry_l3", "三级行业", skip)
    t_con = resolve_totals([k for k, v in keep_concept.items() if v >= MIN_HIT_FOR_TOTAL],
                           cache, "concept", "概念", skip)
    _save_cache(cache)

    result = {
        "date": date_str,
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "同花顺问财 iwencai（口径：上升途中 → 上升通道）",
        "query": pool.get("query", ""),
        "pool": {
            "total": len(stocks),
            "st": sum(1 for s in stocks if s["is_st"]),
            "sh": sum(1 for s in stocks if s["exchange"] == "SH"),
            "sz": sum(1 for s in stocks if s["exchange"] == "SZ"),
            "bj": sum(1 for s in stocks if s["exchange"] == "BJ"),
        },
        "boards": {
            "industry_l1": build_board(c_l1, m_l1, t_l1),
            "industry_l2": build_board(c_l2, m_l2, t_l2),
            "industry_l3": build_board(c_l3, m_l3, t_l3),
            "concept": build_board(keep_concept, m_concept, t_con),
        },
        "noise": [{"name": k, "hit": v} for k, v in noise],
        "coverage": {
            "ind_l1": len(c_l1), "ind_l2": len(c_l2),
            "ind_l3": len(c_l3), "concept": len(c_concept),
            "concept_kept": len(keep_concept), "concept_noise": len(noise),
        },
    }

    # 日环比：与上一交易日对比，拆出新进入 / 退出的个股
    try:
        diff = compute_diff(date_str)
        if diff is not None:
            result["diff"] = diff
            print(f"  日环比：对比 {diff.get('prev_date') or '无'} → "
                  f"新进入 {diff['new_count']} 只，退出 {diff['exited_count']} 只")
    except Exception as e:  # noqa: BLE001
        print(f"  [warn] 差集计算跳过：{e}")

    out_path = os.path.join(DATA_DIR, f"stats_{date_str}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n统计完成 -> {out_path}")
    for key, title in (("industry_l1", "一级行业"), ("industry_l2", "二级行业"),
                       ("industry_l3", "三级行业"), ("concept", "概念题材")):
        b = result["boards"][key]
        print(f"  {title}: {len(b)} 个板块，含分母 {sum(1 for x in b if x['total'])} 个")
    print(f"  已过滤属性标签 {len(noise)} 个（如 "
          f"{', '.join(n[0] for n in noise[:5])}）")
    return result


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
