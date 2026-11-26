"""
蹲站交易（单站做市/价差捕获）物品推荐算法
================================================

模型目标：在单一空间站（默认 Jita 4-4, location_id=60003760）内，
通过挂买单（收购库存）+ 挂卖单（出货）捕获买卖价差，并以"改单"保持竞争力。
本脚本给出可执行的物品选择推荐：在计入经纪费/交易税后，按"可执行深度"口径
计算真实价差，并以资本效率为核心对候选物品打分排序。

关键修正（相对旧版 limit_order 脚本）：
1. 价差必须在"可执行深度 Q"上计算（VWAP），而非仅取最优一档 —— 避免薄挂单伪造价差。
2. 显式设置费用盈亏平衡门（round-trip ≈ 5.9%）与最小日成交量门（可执行性）。
3. 引入竞争强度（改单 churn）与价格波动（库存风险）作为风险调整项。
4. 以"资本周转效率"为核心评分，而非简单利润率。

依赖：numpy, sqlite3（项目 .venv 已具备）。
"""
import sqlite3
import os
import json
import math
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")
DB_ORDERS = os.path.join(DATA_DIR, "eve_market_orders.db")
DB_HISTORY = os.path.join(DATA_DIR, "eve_market_history.db")
OUT_CSV = os.path.join(DATA_DIR, "output", "station_trading_recommendations.csv")
OUT_JSON = os.path.join(DATA_DIR, "output", "station_trading_recommendations.json")

# ---------------- 参数 ----------------
JITA4_4_LOCATION = 60003760
REGION = 10000002
ANALYSIS_DAYS = 30          # 历史窗口（天）
CHURN_WINDOW_HOURS = 24     # 改单事件（竞争强度）统计窗口
MIN_DAILY_VOLUME = 50       # 最小日成交量（单位/天），低于则视为不可执行
TRADE_SHARE = 0.01          # 单次可执行批 = 日成交量的 1%（单交易者现实批大小）
DEPTH_SHARE = 0.005         # 价差测算深度 = 日成交量的 0.5%（小深度 VWAP，避免单笔陈旧挂单虚增价差）
MIN_Q = 1                   # 可执行量绝对下限（单位）
JUNK_BID_RATIO = 0.5        # 垃圾买单过滤：低于 0.5×最优卖价 的买单视为噪声，不参与定价
FEE_GATE_NET_MARGIN = 0.02  # 净收益率门槛（已扣费后仍需 >2% 才视为真实机会）
BROKER = 0.0171             # 经纪费（买/卖各收一次）
TAX = 0.042                 # 交易税（仅卖出收）
ROUND_TRIP_FEE = 2 * BROKER + TAX   # ≈ 7.6%？注意：买入仅经纪费，卖出经纪费+税
# 实际上 round-trip 成本 = 买入经纪费 + 卖出(经纪费+税) = 2*BROKER + TAX = 7.62%
# 但买入还需 (1+BROKER)，卖出 (1-BROKER-TAX)，故净门槛见 compute 内。

# 评分权重（合计 1.0）
W_PROFIT = 0.30      # 净收益率
W_CAPITAL = 0.25     # 资本效率（净收益/单价）
W_VOLUME = 0.20      # 可执行容量（日成交量，对数）
W_STABILITY = 0.15   # 价格稳定（1 - 波动率）
W_COMPETITION = 0.10 # 竞争宽松（1 - 改单拥挤度）


def load_orders(location):
    conn = sqlite3.connect(DB_ORDERS)
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT type_id, order_type, price, volume_remain FROM market_orders WHERE location_id=?",
        (location,),
    ).fetchall()
    conn.close()
    book = defaultdict(lambda: {"sell": [], "buy": []})
    for tid, ot, price, vr in rows:
        if vr <= 0:
            continue
        book[tid][ot].append((float(price), int(vr)))
    # 排序：卖单升序（最优卖价在前），买单降序（最优买价在前）
    for tid in book:
        book[tid]["sell"].sort(key=lambda x: x[0])
        book[tid]["buy"].sort(key=lambda x: x[0], reverse=True)
    return book


def depth_vwap(orders_sorted, q):
    """在 orders_sorted（已按价格方向排序）上累计到数量 q，返回成交量加权均价与能否填满。"""
    if q <= 0:
        return 0.0, False
    total = 0.0
    vol = 0
    for price, vr in orders_sorted:
        take = min(vr, q - vol)
        total += price * take
        vol += take
        if vol >= q:
            break
    if vol < q:
        # 深度不足以填满 q：用实际可得量推算均价（视为更差的执行价）
        if vol == 0:
            return (orders_sorted[-1][0] if orders_sorted else 0.0), False
        return total / vol, False
    return total / vol, True


def load_history(region, days):
    conn = sqlite3.connect(DB_HISTORY)
    cur = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = cur.execute(
        "SELECT type_id, date, average, volume FROM market_history WHERE region_id=? AND date>=? ORDER BY type_id, date",
        (region, cutoff),
    ).fetchall()
    conn.close()
    hist = defaultdict(list)
    for tid, date, avg, vol in rows:
        hist[tid].append((avg, vol))
    out = {}
    for tid, recs in hist.items():
        avgs = np.array([r[0] for r in recs], dtype=float)
        vols = np.array([r[1] for r in recs], dtype=float)
        if len(avgs) < 5 or avgs.mean() <= 0:
            continue
        daily_vol = vols.mean()
        # 价格波动率：日均价变异系数（库存风险代理）
        volat = avgs.std() / avgs.mean() if avgs.mean() > 0 else 0.0
        # 成交量稳定性
        vol_cv = vols.std() / daily_vol if daily_vol > 0 else 0.0
        out[tid] = {
            "daily_volume": float(daily_vol),
            "price_volatility": float(volat),
            "volume_cv": float(vol_cv),
            "last_avg": float(avgs[-1]),
            "n_days": len(avgs),
        }
    return out


def load_churn(location, window_hours=CHURN_WINDOW_HOURS):
    """统计窗口内该站点的改单事件，返回 (churn, meta)。

    旧实现忽略 location 与时间窗口（整表计数）：采集时长、保留期或事件陈旧
    都会直接改变竞争分。现在固定窗口 + 站点过滤，并把窗口内快照数一并返回，
    由调用方换算成"每快照事件数"，使不同采集频率下分数可比。
    """
    cutoff = int(datetime.now().timestamp()) - window_hours * 3600
    conn = sqlite3.connect(DB_ORDERS)
    cur = conn.cursor()
    snapshots = cur.execute(
        """SELECT COUNT(DISTINCT snapshot_ts) FROM market_order_events
           WHERE snapshot_ts >= ?""",
        (cutoff,),
    ).fetchone()[0]
    rows = cur.execute(
        """SELECT type_id, event_type, COUNT(*) FROM market_order_events
           WHERE location_id = ? AND snapshot_ts >= ?
           GROUP BY type_id, event_type""",
        (location, cutoff),
    ).fetchall()
    conn.close()

    churn = defaultdict(lambda: {"insert": 0, "modify": 0, "delete": 0})
    for tid, et, n in rows:
        if et in churn[tid]:
            churn[tid][et] += int(n)
    return churn, {"window_hours": window_hours, "snapshots": int(snapshots or 0)}


def main():
    print("加载 Jita 4-4 订单簿 ...")
    book = load_orders(JITA4_4_LOCATION)
    print(f"  站点内物品数: {len(book)}")

    print(f"加载近 {ANALYSIS_DAYS} 天成交历史 ...")
    hist = load_history(REGION, ANALYSIS_DAYS)
    print(f"  有历史物品数: {len(hist)}")

    print("加载改单 churn ...")
    churn, churn_meta = load_churn(JITA4_4_LOCATION)
    churn_snapshots = max(1, churn_meta["snapshots"])
    print(f"  窗口 {churn_meta['window_hours']}h / {churn_meta['snapshots']} 个快照，"
          f"有改单记录的物品种类: {len(churn)}")
    if churn_meta["snapshots"] == 0:
        print("  警告：窗口内无改单事件，竞争分将退化为中性（确认追踪模式已开启）")

    candidates = []
    skipped = defaultdict(int)
    all_nm = []  # 诊断：记录到达门槛计算的净收益率分布
    for tid, d in book.items():
        if not d["sell"] or not d["buy"]:
            skipped["单边"] += 1
            continue
        h = hist.get(tid)
        if not h:
            skipped["无历史"] += 1
            continue
        V = h["daily_volume"]
        if V < MIN_DAILY_VOLUME:
            skipped["日量不足"] += 1
            continue

        best_ask = d["sell"][0][0]
        # 垃圾买单过滤：剔除远低于卖价的噪声买单（如百万物价上的 1 ISK 买单）
        clean_bids = [(p, v) for p, v in d["buy"] if p >= JUNK_BID_RATIO * best_ask]
        if not clean_bids:
            skipped["无真实买盘"] += 1
            continue
        best_bid = clean_bids[0][0]

        # ---- 蹲站做市执行模型（正确方向）----
        # 你同时挂"买单"（成为 bid）与"卖单"（成为 ask）：
        #   · 收购成本基准 = 你挂的买单价格 ≈ 在买盘上累计 D 量的 VWAP（剔除垃圾单后）
        #   · 出货收入基准 = 你挂的卖单价格 ≈ 在卖盘上累计 D 量的 VWAP
        #   · 你捕获的价差 = 卖盘VWAP - 买盘VWAP，扣费后即为净利润
        # 用"小深度 VWAP"而非单一最优档，避免一笔陈旧挂单虚增价差（流动性高的物品尤其明显）。
        D = max(MIN_Q, DEPTH_SHARE * V)
        acq_vwap, acq_ok = depth_vwap(clean_bids, D)   # 买盘累计 D 量均价（你作为买方成本）
        dis_vwap, dis_ok = depth_vwap(d["sell"], D)    # 卖盘累计 D 量均价（你作为卖方收入）
        # 参考价（用于展示与可执行性判定）
        acquisition_price = best_bid
        disposal_price = best_ask
        top_ask_size = d["sell"][0][1]
        top_bid_size = clean_bids[0][1]

        # 可执行性：最优买卖档都需有一定挂单量，否则无法实际成交
        liquid = (top_ask_size >= MIN_Q) and (top_bid_size >= MIN_Q) and acq_ok and dis_ok

        buy_cost = acq_vwap * (1 + BROKER)        # 买单成交付经纪费
        sell_rev = dis_vwap * (1 - BROKER - TAX)   # 卖单成交付经纪费+税
        net_per_unit = sell_rev - buy_cost
        net_margin = net_per_unit / buy_cost if buy_cost > 0 else 0.0
        gross_spread_pct = (dis_vwap - acq_vwap) / acq_vwap if acq_vwap > 0 else 0.0

        if net_margin <= FEE_GATE_NET_MARGIN:
            all_nm.append(net_margin)
            skipped["未过费门槛"] += 1
            continue

        # 单次可执行批 Q（工作库存）：日成交量的 TRADE_SHARE，且不低于 MIN_Q
        Q = max(MIN_Q, TRADE_SHARE * V)

        # 日可执行利润：以规划捕获份额 BASE_SHARE 吃下日成交量；竞争在 SCORE 中另行折算
        BASE_SHARE = 0.10
        executable_daily_units = BASE_SHARE * V
        daily_profit = net_per_unit * executable_daily_units
        # 周转次数/天 = 日可吃量 / 单次批
        turns_per_day = executable_daily_units / Q if Q > 0 else 0.0
        # 资本占用：单边工作库存（买价成本 × 批大小）；双边挂单资金滚动复用，按单边计
        capital = buy_cost * Q
        capital_eff = daily_profit / capital if capital > 0 else 0.0  # 日收益率（资本维度）

        # 竞争强度：每快照改单事件数 / 日成交量（每单位成交对应的博弈强度）
        c = churn.get(tid, {"insert": 0, "modify": 0, "delete": 0})
        total_events = c["insert"] + c["modify"] + c["delete"]
        churn_per_snapshot = total_events / churn_snapshots
        churn_intensity = churn_per_snapshot / V if V > 0 else 0.0

        volat = h["price_volatility"]

        candidates.append({
            "type_id": tid,
            "name": None,  # 后续由 items 库补全
            "exec_Q": Q,
            "best_ask": best_ask,
            "best_bid": best_bid,
            "acquisition_price": acquisition_price,
            "disposal_price": disposal_price,
            "top_ask_size": top_ask_size,
            "top_bid_size": top_bid_size,
            "top_gross_spread_pct": (best_ask - best_bid) / best_bid if best_bid > 0 else 0.0,
            "gross_spread_pct": gross_spread_pct,
            "net_margin": net_margin,
            "net_per_unit": net_per_unit,
            "daily_volume": V,
            "price_volatility": volat,
            "volume_cv": h["volume_cv"],
            "executable_daily_units": executable_daily_units,
            "daily_profit": daily_profit,
            "turns_per_day": turns_per_day,
            "capital": capital,
            "capital_eff": capital_eff,
            "churn_events": total_events,
            "churn_per_snapshot": churn_per_snapshot,
            "churn_intensity": churn_intensity,
            "liquid": liquid,
            "n_days": h["n_days"],
        })

    print(f"通过门槛候选数: {len(candidates)}")
    print("  跳过分布:", dict(skipped))
    if all_nm:
        a = np.array(all_nm)
        print("  [诊断] 到达费门槛计算的净收益率: median=%.4f p5=%.4f p25=%.4f p75=%.4f max=%.4f" % (
            np.median(a), np.percentile(a, 5), np.percentile(a, 25), np.percentile(a, 75), a.max()))

    if not candidates:
        print("无候选，退出。")
        return

    # ---- 归一化（在候选集内做 min-max / log 归一）----
    def norm(arr, lo=None, hi=None):
        a = np.array(arr, dtype=float)
        if lo is None:
            lo = np.percentile(a, 5)
        if hi is None:
            hi = np.percentile(a, 95)
        if hi <= lo:
            return np.clip((a - lo) / (hi - lo + 1e-9), 0, 1)
        return np.clip((a - lo) / (hi - lo), 0, 1)

    net_margin = np.array([c["net_margin"] for c in candidates])
    cap_eff = np.array([c["capital_eff"] for c in candidates])
    dvol = np.array([c["daily_volume"] for c in candidates])
    volat = np.array([c["price_volatility"] for c in candidates])
    churn_i = np.array([c["churn_intensity"] for c in candidates])

    n_profit = norm(net_margin)
    n_capital = norm(np.log1p(cap_eff * 1e6))  # capital_eff 极小，放大
    n_volume = norm(np.log1p(dvol))
    n_stability = 1 - norm(volat)              # 波动越低越好
    n_comp = 1 - norm(np.log1p(churn_i))       # 竞争越淡越好

    for i, c in enumerate(candidates):
        score = (W_PROFIT * n_profit[i] + W_CAPITAL * n_capital[i] +
                 W_VOLUME * n_volume[i] + W_STABILITY * n_stability[i] +
                 W_COMPETITION * n_comp[i]) * 100
        c["score"] = float(score)
        c["n_profit"] = float(n_profit[i])
        c["n_capital"] = float(n_capital[i])
        c["n_volume"] = float(n_volume[i])
        c["n_stability"] = float(n_stability[i])
        c["n_competition"] = float(n_comp[i])

    candidates.sort(key=lambda x: x["score"], reverse=True)

    # 补全物品名称
    try:
        conn = sqlite3.connect(os.path.join(DATA_DIR, "eve_items.db"))
        cur = conn.cursor()
        ids = [c["type_id"] for c in candidates]
        ph = ",".join("?" * len(ids))
        names = {r[0]: r[1] for r in cur.execute(
            f"SELECT type_id, name FROM items WHERE type_id IN ({ph})", ids).fetchall()}
        conn.close()
        for c in candidates:
            c["name"] = names.get(c["type_id"], f"type_{c['type_id']}")
    except Exception as e:
        print("名称补全失败:", e)

    # 输出 CSV
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    cols = ["rank", "type_id", "name", "score", "net_margin", "gross_spread_pct",
            "best_bid", "best_ask", "acquisition_price", "disposal_price",
            "net_per_unit", "daily_volume", "price_volatility", "volume_cv",
            "exec_Q", "executable_daily_units", "daily_profit", "turns_per_day",
            "capital", "capital_eff", "churn_events", "churn_per_snapshot",
            "churn_intensity", "liquid", "n_days"]
    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write(",".join(cols) + "\n")
        for i, c in enumerate(candidates):
            row = [i + 1, c["type_id"], c["name"], f"{c['score']:.2f}",
                   f"{c['net_margin']:.4f}", f"{c['gross_spread_pct']:.4f}",
                   f"{c['best_bid']:.2f}", f"{c['best_ask']:.2f}",
                   f"{c['acquisition_price']:.2f}", f"{c['disposal_price']:.2f}",
                   f"{c['net_per_unit']:.2f}", f"{c['daily_volume']:.1f}",
                   f"{c['price_volatility']:.4f}", f"{c['volume_cv']:.4f}",
                   f"{c['exec_Q']:.1f}", f"{c['executable_daily_units']:.1f}",
                   f"{c['daily_profit']:.0f}", f"{c['turns_per_day']:.3f}",
                   f"{c['capital']:.0f}", f"{c['capital_eff']:.6f}",
                   c["churn_events"], f"{c['churn_per_snapshot']:.4f}",
                   f"{c['churn_intensity']:.4f}",
                   c["liquid"], c["n_days"]]
            f.write(",".join(str(x) for x in row) + "\n")
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n已写出: {OUT_CSV}\n{OUT_JSON}")
    print(f"\n=== TOP 30 蹲站推荐 ===")
    print(f"{'#':>3} {'物品':<34} {'评分':>6} {'净收益率':>8} {'价差%':>7} "
          f"{'日量':>10} {'波动':>6} {'竞争':>7} {'日利润(ISK)':>14}")
    for i, c in enumerate(candidates[:30]):
        print(f"{i+1:>3} {c['name'][:33]:<34} {c['score']:>6.1f} "
              f"{c['net_margin']*100:>7.1f}% {c['gross_spread_pct']*100:>6.1f}% "
              f"{c['daily_volume']:>10.0f} {c['price_volatility']:>6.2f} "
              f"{c['churn_intensity']:>7.2f} {c['daily_profit']:>14.0f}")

    # 汇总统计
    nm = np.array([c["net_margin"] for c in candidates])
    dv = np.array([c["daily_volume"] for c in candidates])
    dp = np.array([c["daily_profit"] for c in candidates])
    ce = np.array([c["capital_eff"] for c in candidates])
    print(f"\n候选汇总: n={len(candidates)}")
    print(f"  净收益率: 中位 {np.median(nm)*100:.1f}%  均值 {nm.mean()*100:.1f}%")
    print(f"  日成交量: 中位 {np.median(dv):.0f}  均值 {dv.mean():.0f}")
    print(f"  日利润ISK: 中位 {np.median(dp):.0f}  合计 {dp.sum():.0f}")
    print(f"  资本日效率: 中位 {np.median(ce)*100:.4f}%")


if __name__ == "__main__":
    main()
