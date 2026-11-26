"""
根据 station_trading_recommendations.json 生成可交互可视化的分析报告（离线内联 SVG，无外部依赖）。
输出：docs/station_trading_report.html
"""
import json
import os
import sqlite3
import numpy as np
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data")
JSON_IN = os.path.join(DATA, "output", "station_trading_recommendations.json")
ITEMS_DB = os.path.join(DATA, "eve_items.db")
OUT = os.path.join(BASE, "..", "docs", "station_trading_report.html")

BROKER = 0.0171
TAX = 0.042
FEE_BREAKEVEN = (1 + BROKER) / (1 - BROKER - TAX) - 1  # 净收益>0 所需的毛价差下限

with open(JSON_IN, encoding="utf-8") as f:
    recs = json.load(f)

# 补全 market_group 名称
conn = sqlite3.connect(ITEMS_DB)
cur = conn.cursor()
ids = [r["type_id"] for r in recs]
ph = ",".join("?" * len(ids))
names = {r[0]: r[1] for r in cur.execute(
    f"SELECT type_id, name FROM items WHERE type_id IN ({ph})", ids).fetchall()}
grp = {r[0]: r[1] for r in cur.execute(
    f"SELECT type_id, market_group_id FROM items WHERE type_id IN ({ph})", ids).fetchall()}
gname = {r[0]: r[1] for r in cur.execute(
    "SELECT market_group_id, name FROM market_groups").fetchall()}
conn.close()
for r in recs:
    r["name"] = names.get(r["type_id"], r["name"])
    r["group"] = gname.get(grp.get(r["type_id"]), "?")

# 关键统计
nm = np.array([r["net_margin"] for r in recs])
dv = np.array([r["daily_volume"] for r in recs])
dp = np.array([r["daily_profit"] for r in recs])
gs = np.array([r["gross_spread_pct"] for r in recs])
n = len(recs)
stat = {
    "n": n,
    "net_median": float(np.median(nm)),
    "net_mean": float(nm.mean()),
    "gross_median": float(np.median(gs)),
    "vol_median": float(np.median(dv)),
    "vol_mean": float(dv.mean()),
    "profit_sum": float(dp.sum()),
    "profit_median": float(np.median(dp)),
    "fee_be": FEE_BREAKEVEN,
    "n_gt_8pct": int((gs > FEE_BREAKEVEN).sum()),
}

# 分组集中度（按 market_group 聚合候选数）
from collections import Counter
gc = Counter(r["group"] for r in recs)
top_groups = gc.most_common(12)

# ---------- 内联 SVG 图表 ----------
def svg_hist(data, bins=24, w=520, h=180, title="", color="#3b82f6"):
    a = np.array(data, dtype=float)
    lo, hi = np.percentile(a, 1), np.percentile(a, 99)
    if hi <= lo:
        hi = lo + 1e-9
    edges = np.linspace(lo, hi, bins + 1)
    counts, _ = np.histogram(a, edges)
    mx = max(counts.max(), 1)
    bw = w / bins
    parts = []
    for i, c in enumerate(counts):
        x = i * bw
        bh = (c / mx) * (h - 30)
        y = h - 20 - bh
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw-1:.1f}" height="{bh:.1f}" fill="{color}" opacity="0.85"/>')
    # 费平衡线
    xb = (FEE_BREAKEVEN - lo) / (hi - lo) * w
    if 0 <= xb <= w:
        parts.append(f'<line x1="{xb:.1f}" y1="10" x2="{xb:.1f}" y2="{h-20}" stroke="#ef4444" stroke-dasharray="4 3"/>')
        parts.append(f'<text x="{xb+3:.1f}" y="14" font-size="10" fill="#ef4444">费平衡 {FEE_BREAKEVEN*100:.1f}%</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">'
            f'<text x="4" y="10" font-size="11" fill="#94a3b8">{title}</text>' + "".join(parts) +
            f'<text x="4" y="{h-6}" font-size="9" fill="#64748b">{lo*100:.0f}%</text>'
            f'<text x="{w-30}" y="{h-6}" font-size="9" fill="#64748b">{hi*100:.0f}%</text></svg>')

def svg_bar(labels, vals, w=560, h=300, color="#10b981", unit=""):
    mx = max(max(vals), 1e-9)
    n = len(vals)
    bw = w / max(n, 1)
    parts = []
    for i, (lb, v) in enumerate(zip(labels, vals)):
        bh = (v / mx) * (h - 50)
        x = i * bw
        y = h - 30 - bh
        parts.append(f'<rect x="{x+bw*0.15:.1f}" y="{y:.1f}" width="{bw*0.7:.1f}" height="{bh:.1f}" fill="{color}" opacity="0.9"/>')
        if i % 2 == 0:
            parts.append(f'<text x="{x+bw/2:.1f}" y="{h-18}" font-size="7.5" fill="#64748b" transform="rotate(45 {x+bw/2:.1f} {h-18:.1f})" text-anchor="start">{lb[:10]}</text>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">'
            + "".join(parts) +
            f'<text x="4" y="12" font-size="11" fill="#94a3b8">评分 Top {n}{unit}</text></svg>')

def svg_scatter(xs, ys, w=560, h=240, color="#f59e0b"):
    xs = np.array(xs, dtype=float); ys = np.array(ys, dtype=float)
    lx = np.log10(np.clip(xs, 1, None))
    lo_x, hi_x = lx.min(), lx.max()
    lo_y, hi_y = np.percentile(ys, 1), np.percentile(ys, 99)
    if hi_y <= lo_y:
        hi_y = lo_y + 1e-9
    def px(x):
        return 40 + (np.log10(max(x,1)) - lo_x) / (hi_x - lo_x + 1e-9) * (w - 60)
    def py(y):
        return 20 + (hi_y - y) / (hi_y - lo_y + 1e-9) * (h - 50)
    pts = []
    for x, y in zip(xs, ys):
        pts.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="2.4" fill="{color}" opacity="0.55"/>')
    # 费平衡水平线
    yb = py(FEE_BREAKEVEN)
    if 0 <= yb <= h:
        pts.append(f'<line x1="40" y1="{yb:.1f}" x2="{w-20}" y2="{yb:.1f}" stroke="#ef4444" stroke-dasharray="4 3"/>')
    grid = "".join(
        f'<text x="{px(10**vx):.1f}" y="{h-12}" font-size="8" fill="#64748b" text-anchor="middle">{10**vx:.0e}</text>'
        for vx in [lo_x, (lo_x+hi_x)/2, hi_x])
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:{w}px">'
            f'<text x="4" y="12" font-size="11" fill="#94a3b8">日成交量(对数x) vs 净收益率(绿线=费平衡)</text>'
            + "".join(pts) + grid +
            f'<text x="4" y="{h-2}" font-size="9" fill="#64748b">x: 日成交量(单位/天, log)</text></svg>')

hist_svg = svg_hist(gs * 100, title="候选物品毛价差分布 (%)")
bar_svg = svg_bar([r["name"][:12] for r in recs[:20]], [r["score"] for r in recs[:20]], unit="")
scatter_svg = svg_scatter([r["daily_volume"] for r in recs[:400]], [r["net_margin"] for r in recs[:400]])

# 分组表
group_rows = "".join(
    f"<tr><td>{g}</td><td>{c}</td><td>{c/n*100:.1f}%</td></tr>" for g, c in top_groups)

# Top30 表
rows = ""
for i, r in enumerate(recs[:30]):
    rows += (f"<tr><td>{i+1}</td><td>{r['name']}</td><td>{r['group']}</td>"
             f"<td>{r['score']:.1f}</td>"
             f"<td style='color:#10b981'>{r['net_margin']*100:.1f}%</td>"
             f"<td>{r['gross_spread_pct']*100:.1f}%</td>"
             f"<td>{r['daily_volume']:,.0f}</td>"
             f"<td>{r['price_volatility']:.2f}</td>"
             f"<td>{r['churn_intensity']:.2f}</td>"
             f"<td>{r['daily_profit']:,.0f}</td></tr>")

html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EVE 蹲站交易推荐报告</title>
<style>
body{{font-family:-apple-system,'Segoe UI',Roboto,'Microsoft YaHei',sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:24px;}}
h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:16px;color:#93c5fd;margin:24px 0 8px;border-left:3px solid #3b82f6;padding-left:8px}}
.sub{{color:#94a3b8;font-size:13px;margin-bottom:16px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}}
.card{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px 16px;min-width:150px}}
.card .k{{font-size:12px;color:#94a3b8}} .card .v{{font-size:20px;font-weight:700;color:#f8fafc;margin-top:4px}}
.card .v.g{{color:#10b981}} .card .v.r{{color:#ef4444}}
table{{border-collapse:collapse;width:100%;font-size:12.5px;margin-top:8px}}
th,td{{border-bottom:1px solid #334155;padding:6px 8px;text-align:right}}
th{{color:#93c5fd;background:#1e293b;position:sticky;top:0}}
td:nth-child(2),td:nth-child(3),th:nth-child(2),th:nth-child(3){{text-align:left}}
.chartbox{{background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px;margin:10px 0}}
.note{{font-size:12px;color:#94a3b8;line-height:1.7;background:#1e293b;border:1px solid #334155;border-radius:10px;padding:12px 16px}}
code{{background:#0b1220;padding:1px 5px;border-radius:4px;color:#fbbf24}}
</style></head><body>
<h1>EVE Online 蹲站交易 · 物品选择推荐报告</h1>
<div class="sub">站点：Jita IV - Moon 4 (location 60003760) · 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 数据源：本地订单簿快照 + 近30日成交历史</div>

<div class="cards">
  <div class="card"><div class="k">通过门槛候选</div><div class="v">{stat['n']:,}</div></div>
  <div class="card"><div class="k">中位净收益率</div><div class="v g">{stat['net_median']*100:.1f}%</div></div>
  <div class="card"><div class="k">中位毛价差</div><div class="v">{stat['gross_median']*100:.1f}%</div></div>
  <div class="card"><div class="k">中位日成交量</div><div class="v">{stat['vol_median']:,.0f}</div></div>
  <div class="card"><div class="k">候选合计日利润</div><div class="v">{stat['profit_sum']/1e9:.1f}B ISK</div></div>
  <div class="card"><div class="k">费平衡阈值</div><div class="v r">{stat['fee_be']*100:.1f}%</div></div>
</div>

<div class="note">
<b>模型要点：</b>蹲站 = 在单一站点<b>同时挂买单与卖单</b>做市，捕获 <code>卖价−买价</code> 价差。净利润 =
<code>卖价×(1−经纪费−交易税) − 买价×(1+经纪费)</code>。任一档价差必须高于 <b>{stat['fee_be']*100:.1f}%</b> 的往返费用才不亏。
价差按日成交量 0.5% 的小深度 VWAP 测算（避免单笔陈旧挂单虚增），并剔除低于卖价 50% 的垃圾买单。
推荐评分 = 0.30·净收益率 + 0.25·资本效率 + 0.20·日成交量(对数) + 0.15·价格稳定 + 0.10·竞争宽松。
</div>

<h2>候选物品毛价差分布</h2>
<div class="chartbox">{hist_svg}</div>

<h2>评分 Top 20</h2>
<div class="chartbox">{bar_svg}</div>

<h2>日成交量 × 净收益率（散点，前400候选）</h2>
<div class="chartbox">{scatter_svg}</div>

<h2>候选集中度（按市场分组 Top 12）</h2>
<table><thead><tr><th>市场分组</th><th>候选数</th><th>占比</th></tr></thead><tbody>{group_rows}</tbody></table>

<h2>Top 30 推荐物品</h2>
<table><thead><tr><th>#</th><th>物品</th><th>分组</th><th>评分</th><th>净收益率</th><th>毛价差</th><th>日成交量</th><th>价格波动</th><th>竞争</th><th>日利润(ISK)</th></tr></thead><tbody>{rows}</tbody></table>

<div class="note" style="margin-top:20px">
<b>风险提示：</b>① 本表基于<b>单一时点订单簿快照</b>，宽价差可能被后续挂单迅速抹平，需高频刷新复核；
② 高净收益率 + 低日成交量的物品多为<b>薄流动性陷阱</b>（价差真实但难以放量执行），应小仓位试单；
③ 版本更新 / 战争 / 资源改版会剧烈改变供需，历史参数需滚动窗口；
④ 评分仅做<b>初筛</b>，实盘须结合自身资金、技能（降费）与挂单改单节奏。
完整算法见 <code>docs/station_trading_profit_model.md</code>，明细见 <code>data/output/station_trading_recommendations.json</code>。
</div>
</body></html>"""

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write(html)
print("报告已生成:", OUT)
print("统计:", json.dumps({k: (round(v,4) if isinstance(v,float) else v) for k,v in stat.items()}, ensure_ascii=False))
