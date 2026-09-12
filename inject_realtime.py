# -*- coding: utf-8 -*-
"""给看板注入「打开页面即拉当下最新名单」的能力。

同时修复既存 bug：DATA.pool.stocks 从未被填充（analyze.py 的 pool 是汇总对象），
导致搜索框的「名称/拼音」搜索一直查不到东西。改为从 DATA.pool.stocks 动态取。

用法：
  python inject_realtime.py [worker_url]
未给 worker_url 时注入占位（不生效，页面继续用内联快照）。
"""
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = [
    os.path.join(HERE, "build_html.py"),
    os.path.join(HERE, "docs", "index.html"),
]

# 1) 搜索池：改为函数，实时刷新后能拿到新 DATA
OLD_POOL = "  var pool = (DATA.pool && DATA.pool.stocks) || [];"
NEW_POOL = "  function getPool(){ return (DATA.pool && DATA.pool.stocks) || []; }"

# 2) 引导锚点
ANCHOR = "render();\nrenderNoise();\nrenderConclusion();"

RT_JS = r"""
/* ===== 实时数据：打开页面即拉当下最新名单 ===== */
(function(){
  var API = window.UPTREND_API || '';
  if (!API) { return; }
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

  fetch(API.replace(/\/+$/, '') + '/api/board', { cache: 'no-store' })
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
"""


def patch(path, api_url):
    src = io.open(path, encoding="utf-8").read()
    orig = src
    name = os.path.basename(path)

    # 搜索池改造
    n_pool = src.count(OLD_POOL)
    if n_pool == 1:
        src = src.replace(OLD_POOL, NEW_POOL)
        # 三处 pool.find -> getPool().find
        n_find = src.count("pool.find(")
        src = src.replace("pool.find(", "getPool().find(")
        assert n_find == 3, "%s: pool.find 出现 %d 次（预期 3）" % (name, n_find)
        print("  [%s] 搜索池改为动态取值（pool.find x%d）" % (name, n_find))
    elif "function getPool()" in src:
        print("  [%s] 搜索池已改造，跳过" % name)
    else:
        print("  [%s] 警告：未找到 pool 定义，跳过" % name)

    # 注入实时引导
    if "UPTREND_API" in src:
        print("  [%s] 实时逻辑已存在，跳过" % name)
    else:
        n_anchor = src.count(ANCHOR)
        assert n_anchor == 1, "%s: 引导锚点出现 %d 次（预期 1）" % (name, n_anchor)
        block = ANCHOR + "\n"
        if api_url:
            block += "window.UPTREND_API = window.UPTREND_API || '%s';\n" % api_url
        block += RT_JS
        src = src.replace(ANCHOR, block, 1)
        print("  [%s] 已注入实时引导（API=%s）" % (name, api_url or "占位"))

    if src != orig:
        io.open(path, "w", encoding="utf-8").write(src)
        print("  [%s] 已写盘" % name)
    else:
        print("  [%s] 无改动" % name)


def main():
    api_url = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    print("注入实时数据能力（worker_url=%s）" % (api_url or "未指定"))
    for p in TARGETS:
        if not os.path.exists(p):
            print("  跳过（不存在）: %s" % p)
            continue
        patch(p, api_url)


if __name__ == "__main__":
    main()
