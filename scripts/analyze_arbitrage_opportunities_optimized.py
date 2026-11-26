"""
蹲站交易（单站做市）机会分析 —— 「交易分析」页面数据产物生成脚本
====================================================================

模型来源：docs/station_trading_profit_model.md（蹲站交易利润模型与物品选择推荐算法）

相对旧版（limit_order 挂单套利）的核心修正：
1. 方向修正：蹲站是"买在买盘（bid）、卖在卖盘（ask）"，靠捕获买卖价差获利；
   旧版按"吃卖单进货、砸买单出货"的方向计算，恒定亏损。
2. 价差按"可执行深度 VWAP"测算（深度 = 日成交量 × DEPTH_SHARE），而非单一最优档，
   避免一笔陈旧/垃圾挂单虚增价差（薄挂单污染）。
   [已加固] 累计深度时加了"阶梯断裂"保护：相邻档位价格跳变 > MAX_LEVEL_GAP 即停止累计，
   否则会出现「最优卖档仅 1 个、第二档直接跳到 8 倍价」导致出货价虚高（如 紫外晶体 M 的 616% 假价差）。
3. 垃圾买单过滤：剔除价格低于 JUNK_BID_RATIO × 最优卖价 的噪声买单（如百万物价上的 1 ISK 买单）。
4. 费用盈亏平衡硬门槛：扣费后净收益率必须 > FEE_GATE_NET_MARGIN（默认 2%）。
5. 以"资本周转效率"为核心的多因子加权评分（净收益率 / 资本效率 / 成交量 / 价格稳定 / 竞争宽松）。
6. 引入改单事件（market_order_events）量化盘口竞争强度（churn）。

数据来源：Jita 4-4 空间站（location_id=60003760）订单簿 + 近 30 日成交历史 + 改单事件。

输出：data/output/arbitrage_opportunities.json（供 /api/analysis 与 analysis.html 使用）
      data/output/arbitrage_opportunities.csv（便于直接阅读/表格筛选）

字段兼容说明：为保持前端与接口不变，仍输出 profit_margin（=扣费净收益率）、
ideal_profit（=日可执行利润）、profit_per_unit、score、mvp_score（=资本效率）等既有字段。
"""

import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import numpy as np

# 将项目根目录加入搜索路径，以便导入 paths / database_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database_manager import get_db_connection
from paths import ARBITRAGE_OUTPUT, DATA_OUTPUT_DIR

# ---------------- 分析参数（可在脚本顶部调整） ----------------
REGION_ID = 10000002          # 吉他星域
JITA_LOCATION_ID = 60003760   # 吉他 4-4 空间站（事实主市场）
ANALYSIS_DAYS = 30            # 历史窗口（天）
CHURN_WINDOW_HOURS = 24       # 改单事件（竞争强度）统计窗口；按快照数归一后进入评分
MIN_DAILY_VOLUME = 50         # 最小日成交量（可执行性下限）
DEPTH_SHARE = 0.005           # 价差测算深度 = 日成交量 × 0.5%（小深度 VWAP）
TRADE_SHARE = 0.01            # 单次工作批 = 日成交量的 1%
MIN_Q = 1                     # 可执行量绝对下限（单位）
JUNK_BID_RATIO = 0.5          # 垃圾买单过滤阈值：低于 0.5 × 最优卖价 的买单不参与定价
MAX_LEVEL_GAP = 0.10          # 相邻档位跳变上限：价格跳变超过 10% 视为阶梯断裂，停止累计
MAX_PRICE_DEVIATION = 0.25    # 累计价相对本侧最优价的最大偏离（安全上限）
FEE_GATE_NET_MARGIN = 0.02    # 费用门槛：扣费后净收益率需 > 2%
BASE_SHARE = 0.10             # 规划捕获份额（日成交量的 10%）

# 交易费用参数（随技能/声望变化，改号只需调整此处）
BROKERAGE_FEE_RATE = 0.0171   # 经纪费：买/卖各收一次
SALES_TAX_RATE = 0.042        # 交易税：仅卖出收取

# 评分权重（合计 1.0）
W_PROFIT = 0.30               # 净收益率
W_CAPITAL = 0.25              # 资本效率
W_VOLUME = 0.20               # 可执行容量（日成交量）
W_STABILITY = 0.15            # 价格稳定（1 - 波动率）
W_COMPETITION = 0.10          # 竞争宽松（1 - 改单拥挤度）

# 物品过滤：以下市场分组不参与蹲站选品（不可做市或流动性极差）
TRADE_GOODS_GROUPS = (19, 20, 22, 23, 491, 492, 614, 616, 738, 739, 754, 940, 1109, 1427, 1700, 1840, 1846, 2013, 2317, 2456, 2480, 2799, 2801, 3732, 3737, 730, 731, 732, 733, 734, 735, 736, 737, 740, 741, 742, 743, 744, 745, 746, 747, 748, 749, 750, 751, 752, 2457, 2458, 2459, 2460, 2461, 2706, 2747, 2756, 2757, 3734)
SPECIAL_EDITION_GROUPS = (1659, 1660, 1661, 1662, 1663, 1664, 1810, 1811, 1814, 2760)
SKILL_GROUPS = (150, 364, 365, 366, 367, 368, 369, 370, 372, 373, 374, 375, 376, 377, 378, 1110, 1323, 1745, 1746, 1747, 1748, 1823, 1824, 2152, 3656, 531, 1469, 1470, 1471, 1472, 1473, 1474, 1475, 1476, 1477, 1478, 1479, 1761, 1762, 1763, 1764, 2473, 2358)
SKIN_GROUPS = (1954, 1955, 1960, 1968, 1988, 1989, 1998, 2006, 2011, 2119, 2283, 2306, 2315, 2120)


def get_group_ids(keyword):
    """获取名称包含 keyword 的市场组及其所有子组 ID（用于递归分类过滤）。"""
    try:
        conn = get_db_connection('items')
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT market_group_id, name, parent_group_id FROM market_groups"
        ).fetchall()

        top_id = None
        children_map = defaultdict(list)
        for r in rows:
            children_map[r['parent_group_id']].append(r['market_group_id'])
            if top_id is None and keyword in (r['name'] or ''):
                top_id = r['market_group_id']

        if top_id is None:
            print(f"没有找到包含「{keyword}」的市场组")
            return []

        result = []
        stack = [top_id]
        while stack:
            gid = stack.pop()
            result.append(gid)
            stack.extend(children_map.get(gid, []))
        return result
    except Exception as e:
        print(f"获取「{keyword}」市场组失败: {e}")
        return []


def get_exclude_groups():
    """返回需要从选品范围中排除的所有市场组 ID 集合。"""
    exclude = set(TRADE_GOODS_GROUPS) | set(SPECIAL_EDITION_GROUPS) | set(SKIN_GROUPS)
    exclude |= set(SKILL_GROUPS)
    exclude |= set(get_group_ids('蓝图和反应'))
    exclude |= set(get_group_ids('个性化'))
    return exclude


def check_and_add_indexes():
    """检查并添加必要的索引（大库查询加速，缺失时自动创建）。"""
    conn = get_db_connection('market_orders')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_orders_location_type
        ON market_orders(location_id, type_id, order_type)
    """)
    conn.commit()

    conn = get_db_connection('market_history')
    cursor = conn.cursor()
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_history_region_date
        ON market_history(region_id, date)
    """)
    conn.commit()
    print("数据库索引检查完成")


def load_order_book():
    """载入 Jita 4-4 订单簿：type_id -> {'sell': [(价, 量)...升序], 'buy': [(价, 量)...降序]}"""
    conn = get_db_connection('market_orders')
    cursor = conn.cursor()
    rows = cursor.execute(
        "SELECT type_id, order_type, price, volume_remain FROM market_orders WHERE location_id = ?",
        (JITA_LOCATION_ID,),
    ).fetchall()

    book = defaultdict(lambda: {'sell': [], 'buy': []})
    for r in rows:
        if (r['volume_remain'] or 0) <= 0:
            continue
        book[r['type_id']][r['order_type']].append((float(r['price']), int(r['volume_remain'])))

    for tid in book:
        book[tid]['sell'].sort(key=lambda x: x[0])                 # 卖单升序：最优卖价在前
        book[tid]['buy'].sort(key=lambda x: x[0], reverse=True)    # 买单降序：最优买价在前
    return book


def depth_vwap(orders_sorted, q):
    """在已按价格方向排序的订单列表上累计数量 q，返回 (均价, 实际累计量, 是否满量)。

    关键保护：一旦相邻档位价格跳变超过 MAX_LEVEL_GAP（阶梯断裂，如 6,062 → 48,000），
    或累计价相对本侧最优价偏离超过 MAX_PRICE_DEVIATION，立即停止累计。
    否则少量陈旧远挂单会把"出货价"抬到几十倍，产出假价差。
    """
    if q <= 0 or not orders_sorted:
        return 0.0, 0, False

    ref = orders_sorted[0][0]          # 本侧最优价（锚点）
    prev = ref
    total = 0.0
    vol = 0.0
    for price, vr in orders_sorted:
        if prev > 0 and abs(price - prev) / prev > MAX_LEVEL_GAP:
            break                      # 阶梯断裂
        if ref > 0 and abs(price - ref) / ref > MAX_PRICE_DEVIATION:
            break                      # 偏离锚点过远
        take = min(vr, q - vol)
        total += price * take
        vol += take
        prev = price
        if vol >= q:
            break

    if vol <= 0:
        return 0.0, 0, False
    return total / vol, vol, vol >= q


def load_history(days=ANALYSIS_DAYS):
    """载入近 N 日成交历史：type_id -> 指标字典。"""
    conn = get_db_connection('market_history')
    cursor = conn.cursor()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = cursor.execute(
        """SELECT type_id, date, average, highest, lowest, volume
           FROM market_history
           WHERE region_id = ? AND date >= ?
           ORDER BY type_id, date""",
        (REGION_ID, cutoff),
    ).fetchall()

    grouped = defaultdict(list)
    for r in rows:
        grouped[r['type_id']].append(r)

    out = {}
    for tid, recs in grouped.items():
        if len(recs) < 5:            # 历史不足 5 天，样本不可靠
            continue
        avgs = np.array([float(r['average'] or 0) for r in recs])
        vols = np.array([float(r['volume'] or 0) for r in recs])
        if avgs.mean() <= 0 or vols.mean() <= 0:
            continue

        highs = np.array([float(r['highest'] or 0) for r in recs])
        lows = np.array([float(r['lowest'] or 0) for r in recs])
        last7 = recs[-7:]
        d7_high = float(np.mean([float(r['highest'] or 0) for r in last7]))
        d7_low = float(np.mean([float(r['lowest'] or 0) for r in last7]))

        daily_vol = float(vols.mean())
        out[tid] = {
            'n_days': len(recs),
            'daily_volume': daily_vol,
            'price_volatility': float(avgs.std() / avgs.mean()),          # 库存风险代理
            'volume_cv': float(vols.std() / daily_vol),
            'first_avg': float(avgs[0]),
            'last_avg': float(avgs[-1]),
            'all_high': float(highs.max()),
            'all_low': float(lows.min()),
            'market_size': float(np.mean(vols * avgs)),
            'today_high': float(last7[-1]['highest'] or 0),
            'today_low': float(last7[-1]['lowest'] or 0),
            'avg_7d_high': d7_high,
            'avg_7d_low': d7_low,
            'avg_7d_spread': d7_high - d7_low,
        }
    return out


def load_churn(window_hours=CHURN_WINDOW_HOURS):
    """统计窗口内站点改单事件（insert/modify/delete），作为盘口竞争强度代理。

    返回 (churn, meta)。与旧实现的区别：
    - 固定时间窗（默认 24h）：旧实现是全表计数，数值随采集时长/保留期漂移；
    - 只统计 Jita 4-4 站点的订单（location_id 过滤）；
    - 附带窗口内快照数，供上层把"事件数"换算成"每快照事件数"，使不同采集
      频率下的竞争分可比。
    """
    conn = get_db_connection('market_orders')
    cursor = conn.cursor()

    now = int(time.time())
    cutoff = now - window_hours * 3600

    latest = cursor.execute(
        'SELECT MAX(snapshot_ts) FROM market_order_events'
    ).fetchone()[0]
    snapshots = cursor.execute(
        """SELECT COUNT(DISTINCT snapshot_ts) FROM market_order_events
           WHERE snapshot_ts >= ?""",
        (cutoff,),
    ).fetchone()[0]

    rows = cursor.execute(
        """SELECT type_id, event_type, COUNT(*) AS n
           FROM market_order_events
           WHERE location_id = ? AND snapshot_ts >= ?
           GROUP BY type_id, event_type""",
        (JITA_LOCATION_ID, cutoff),
    ).fetchall()

    churn = defaultdict(lambda: {'insert': 0, 'modify': 0, 'delete': 0})
    for r in rows:
        if r['event_type'] in churn[r['type_id']]:
            churn[r['type_id']][r['event_type']] = int(r['n'])

    meta = {
        'window_hours': window_hours,
        'snapshots': int(snapshots or 0),
        'latest_event_ts': latest,
        'latest_age_hours': ((now - latest) / 3600.0) if latest else None,
    }
    return churn, meta


def load_item_meta():
    """载入物品元数据：type_id -> (名称, 市场分组ID)。"""
    conn = get_db_connection('items')
    cursor = conn.cursor()
    rows = cursor.execute("SELECT type_id, name, market_group_id FROM items").fetchall()
    return {r['type_id']: (r['name'], r['market_group_id']) for r in rows}


def analyze_item(type_id, book_entry, hist, churn_entry, exclude_groups, item_meta,
                 churn_snapshots=1):
    """按蹲站做市模型计算单个物品的指标；不满足门槛返回 None。"""
    meta = item_meta.get(type_id)
    if not meta:
        return None
    name, group_id = meta
    if group_id is not None and group_id in exclude_groups:
        return None

    sell = book_entry['sell']
    buy = book_entry['buy']
    if not sell or not buy:
        return None

    V = hist['daily_volume']
    if V < MIN_DAILY_VOLUME:
        return None

    best_ask = sell[0][0]
    # 垃圾买单过滤：剔除远低于卖价的噪声买单（如 1 ISK 买单）
    clean_bids = [(p, v) for p, v in buy if p >= JUNK_BID_RATIO * best_ask]
    if not clean_bids:
        return None
    best_bid = clean_bids[0][0]

    # 可执行深度：日成交量的 DEPTH_SHARE（含阶梯断裂保护，见 depth_vwap）
    D = max(MIN_Q, DEPTH_SHARE * V)
    acq_vwap, acq_qty, acq_full = depth_vwap(clean_bids, D)   # 买盘近档均价 = 你的收购价
    dis_vwap, dis_qty, dis_full = depth_vwap(sell, D)         # 卖盘近档均价 = 你的出货价
    if acq_vwap <= 0 or dis_vwap <= 0 or acq_qty < MIN_Q or dis_qty < MIN_Q:
        return None                       # 近档无量：不具备可执行性

    # 往返净收益：买入付经纪费，卖出付经纪费 + 交易税
    buy_cost = acq_vwap * (1 + BROKERAGE_FEE_RATE)
    sell_revenue = dis_vwap * (1 - BROKERAGE_FEE_RATE - SALES_TAX_RATE)
    net_per_unit = sell_revenue - buy_cost
    net_margin = net_per_unit / buy_cost

    # 费用盈亏平衡硬门槛
    if net_margin <= FEE_GATE_NET_MARGIN:
        return None

    gross_spread_pct = (dis_vwap - acq_vwap) / acq_vwap
    top_gross_spread_pct = (best_ask - best_bid) / best_bid if best_bid > 0 else 0.0

    # 资本与周转
    Q = max(MIN_Q, TRADE_SHARE * V)                 # 单次工作批
    executable_daily_units = BASE_SHARE * V         # 规划日可吃量
    daily_profit = net_per_unit * executable_daily_units
    turns_per_day = executable_daily_units / Q
    capital = buy_cost * Q                          # 单边资金占用（双边滚动复用，按单边计）
    capital_eff = daily_profit / capital if capital > 0 else 0.0

    top_ask_size = sell[0][1]
    top_bid_size = clean_bids[0][1]
    book_depth = sum(v for _, v in sell) + sum(v for _, v in clean_bids)
    depth_volume_ratio = book_depth / V if V > 0 else 0.0

    c = churn_entry or {'insert': 0, 'modify': 0, 'delete': 0}
    churn_events = c['insert'] + c['modify'] + c['delete']
    # 按快照数归一：窗口内共 N 次快照时，churn 表示"每次快照的平均改单量"，
    # 采集频率或保留期变化不会直接抬高/压低竞争分（旧实现用全表原始计数）。
    churn_per_snapshot = (churn_events / churn_snapshots) if churn_snapshots > 0 else 0.0
    churn_intensity = churn_per_snapshot / V if V > 0 else 0.0

    price_position = 0.0
    if hist['all_high'] > hist['all_low']:
        price_position = (best_ask - hist['all_low']) / (hist['all_high'] - hist['all_low'])
    price_trend = 0.0
    if hist['first_avg'] > 0:
        price_trend = (hist['last_avg'] - hist['first_avg']) / hist['first_avg']

    return {
        'type_id': type_id,
        'name': name,
        # 兼容字段：最低卖价 / 最高买价（均为过滤垃圾单后的盘口最优档）
        'lowest_sell_price': float(best_ask),
        'highest_buy_price': float(best_bid),
        # 蹲站执行价（小深度 VWAP）
        'acquisition_price': float(acq_vwap),
        'disposal_price': float(dis_vwap),
        'top_ask_size': int(top_ask_size),
        'top_bid_size': int(top_bid_size),
        'top_gross_spread_pct': float(top_gross_spread_pct),
        'gross_spread_pct': float(gross_spread_pct),
        # 兼容字段：profit_margin = 扣费净收益率；profit_per_unit = 每单位净利；ideal_profit = 日可执行利润
        'profit_margin': float(net_margin),
        'profit_per_unit': float(net_per_unit),
        'ideal_profit': float(daily_profit),
        'daily_profit': float(daily_profit),
        'mvp_score': float(capital_eff),
        'capital_eff': float(capital_eff),
        'capital': float(capital),
        'exec_Q': float(Q),
        'executable_daily_units': float(executable_daily_units),
        'turns_per_day': float(turns_per_day),
        'unit_price': float(buy_cost),
        'avg_daily_volume': float(V),
        'market_size': float(hist['market_size']),
        'price_trend': float(price_trend),
        'price_volatility': float(hist['price_volatility']),
        'volume_cv': float(hist['volume_cv']),
        'price_position': float(price_position),
        'today_high': float(hist['today_high']),
        'today_low': float(hist['today_low']),
        'avg_7d_high': float(hist['avg_7d_high']),
        'avg_7d_low': float(hist['avg_7d_low']),
        'avg_7d_spread': float(hist['avg_7d_spread']),
        'churn_events': int(churn_events),
        'churn_per_snapshot': float(churn_per_snapshot),
        'churn_intensity': float(churn_intensity),
        'book_depth': int(book_depth),
        'depth_volume_ratio': float(depth_volume_ratio),
        'acquisition_depth_qty': int(acq_qty),
        'disposal_depth_qty': int(dis_qty),
        'liquid': bool(acq_full and dis_full),
        'sell_order_count': len(sell),
        'buy_order_count': len(clean_bids),
        'strategy': 'station_market_making',
    }


def percentile_norm(values):
    """候选集内分位归一（5%~95% 截断），避免极端值主导评分。"""
    a = np.asarray(values, dtype=float)
    lo = np.percentile(a, 5)
    hi = np.percentile(a, 95)
    if hi <= lo:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def score_candidates(candidates):
    """多因子加权评分（0~100），并把分位子分写回候选。"""
    net_margin = np.array([c['profit_margin'] for c in candidates])
    capital_eff = np.array([c['capital_eff'] for c in candidates])
    daily_vol = np.array([c['avg_daily_volume'] for c in candidates])
    volatility = np.array([c['price_volatility'] for c in candidates])
    churn_i = np.array([c['churn_intensity'] for c in candidates])

    n_profit = percentile_norm(net_margin)
    n_capital = percentile_norm(np.log1p(capital_eff * 1e6))
    n_volume = percentile_norm(np.log1p(daily_vol))
    n_stability = 1.0 - percentile_norm(volatility)       # 波动越低越好
    n_competition = 1.0 - percentile_norm(np.log1p(churn_i))  # 竞争越淡越好

    for i, c in enumerate(candidates):
        score = (W_PROFIT * n_profit[i]
                 + W_CAPITAL * n_capital[i]
                 + W_VOLUME * n_volume[i]
                 + W_STABILITY * n_stability[i]
                 + W_COMPETITION * n_competition[i]) * 100.0
        c['score'] = float(score)
        c['n_profit'] = float(n_profit[i])
        c['n_capital'] = float(n_capital[i])
        c['n_volume'] = float(n_volume[i])
        c['n_stability'] = float(n_stability[i])
        c['n_competition'] = float(n_competition[i])
    return candidates


def analyze_market():
    """执行蹲站交易机会分析，返回按评分降序的候选列表。"""
    print("=== 蹲站交易机会分析（单站做市模型）===")
    print(f"交易站点: Jita 4-4 (location_id={JITA_LOCATION_ID})")
    print(f"历史窗口: 近 {ANALYSIS_DAYS} 天    最小日成交量: {MIN_DAILY_VOLUME}")
    print(f"费用门槛: 扣费后净收益率 > {FEE_GATE_NET_MARGIN*100:.0f}%"
          f"（经纪费 {BROKERAGE_FEE_RATE*100:.2f}% / 交易税 {SALES_TAX_RATE*100:.2f}%）")
    print()

    start_all = time.time()

    check_and_add_indexes()
    print()

    print("载入订单簿 ...")
    t0 = time.time()
    book = load_order_book()
    print(f"  站点内物品种类: {len(book)}，耗时 {time.time()-t0:.2f}秒")

    print(f"载入近 {ANALYSIS_DAYS} 天成交历史 ...")
    t0 = time.time()
    hist = load_history()
    print(f"  有效历史物品数: {len(hist)}，耗时 {time.time()-t0:.2f}秒")

    print("载入改单事件（竞争强度）...")
    t0 = time.time()
    churn, churn_meta = load_churn()
    print(f"  窗口 {churn_meta['window_hours']}h、{churn_meta['snapshots']} 个快照，"
          f"有改单记录的物品种类: {len(churn)}，耗时 {time.time()-t0:.2f}秒")
    if churn_meta['snapshots'] == 0:
        print("  警告：窗口内没有任何改单事件，竞争分将退化为中性；"
              "请确认追踪模式已开启且事件数据足够新鲜")
    elif churn_meta['latest_age_hours'] is not None and churn_meta['latest_age_hours'] > churn_meta['window_hours']:
        print(f"  警告：最新改单事件距今 {churn_meta['latest_age_hours']:.1f} 小时，"
              "已超出统计窗口")
    churn_snapshots = max(1, churn_meta['snapshots'])

    print("载入物品元数据（名称 / 市场分组）...")
    t0 = time.time()
    item_meta = load_item_meta()
    print(f"  物品元数据条目: {len(item_meta)}，耗时 {time.time()-t0:.2f}秒")

    print("计算市场分组排除表 ...")
    exclude_groups = get_exclude_groups()
    print(f"  排除分组数: {len(exclude_groups)}")
    print()

    print("开始逐物品计算 ...")
    t0 = time.time()
    candidates = []
    skipped = defaultdict(int)
    type_ids = list(book.keys())
    total = len(type_ids)
    for i, tid in enumerate(type_ids):
        if (i + 1) % 1000 == 0 or (i + 1) == total:
            print(f"分析进度: {i + 1}/{total} ({(i+1)*100//max(1, total)}%)")

        if tid not in hist:
            skipped['无历史'] += 1
            continue
        result = analyze_item(tid, book[tid], hist[tid], churn.get(tid), exclude_groups,
                              item_meta, churn_snapshots)
        if result is None:
            skipped['未过门槛'] += 1
            continue
        candidates.append(result)
    print(f"物品计算完成，耗时 {time.time()-t0:.2f}秒")
    print(f"通过门槛候选数: {len(candidates)}")
    print(f"  跳过分布: {dict(skipped)}")
    print()

    if not candidates:
        print("没有发现符合条件的蹲站交易机会")
        return []

    score_candidates(candidates)
    candidates.sort(key=lambda x: x['score'], reverse=True)
    print(f"总分析时间: {time.time()-start_all:.2f}秒")
    return candidates


def write_csv(results, path):
    """输出候选清单 CSV（便于表格阅读）。"""
    cols = ['rank', 'type_id', 'name', 'score', 'profit_margin', 'gross_spread_pct',
            'acquisition_price', 'disposal_price', 'profit_per_unit', 'ideal_profit',
            'avg_daily_volume', 'capital_eff', 'capital', 'turns_per_day',
            'price_volatility', 'churn_events', 'churn_per_snapshot', 'churn_intensity',
            'liquid', 'strategy']
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        for i, c in enumerate(results):
            writer.writerow([
                i + 1, c['type_id'], c['name'], f"{c['score']:.2f}",
                f"{c['profit_margin']:.4f}", f"{c['gross_spread_pct']:.4f}",
                f"{c['acquisition_price']:.2f}", f"{c['disposal_price']:.2f}",
                f"{c['profit_per_unit']:.2f}", f"{c['ideal_profit']:.0f}",
                f"{c['avg_daily_volume']:.1f}", f"{c['capital_eff']:.4f}",
                f"{c['capital']:.0f}", f"{c['turns_per_day']:.2f}",
                f"{c['price_volatility']:.4f}", c['churn_events'],
                f"{c['churn_per_snapshot']:.4f}",
                f"{c['churn_intensity']:.4f}", c['liquid'], c['strategy'],
            ])


def generate_report(results):
    """打印结果摘要并写出 JSON / CSV 产物。"""
    print()
    print("=== 分析结果报告 ===")
    print(f"发现 {len(results)} 个潜在蹲站交易机会")
    print()

    if not results:
        return

    print("前20个最佳机会:")
    print("=" * 152)
    print(f"{'排名':<4} {'物品名称':<36} {'收购价':<11} {'出货价':<11} {'毛价差':<9} "
          f"{'净收益率':<10} {'每单位净利':<11} {'日成交量':<11} {'日利润(ISK)':<14} {'评分':<6}")
    print("=" * 152)
    for i, item in enumerate(results[:20]):
        print(f"{i + 1:<4} {item['name'][:35]:<36} {item['acquisition_price']:<11.2f} "
              f"{item['disposal_price']:<11.2f} {item['gross_spread_pct']*100:<8.1f}% "
              f"{item['profit_margin']*100:<9.1f}% {item['profit_per_unit']:<11.2f} "
              f"{item['avg_daily_volume']:<11.0f} {item['ideal_profit']:<14.0f} {item['score']:<6.1f}")
    print("=" * 152)

    os.makedirs(DATA_OUTPUT_DIR, exist_ok=True)
    with open(ARBITRAGE_OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存到 {ARBITRAGE_OUTPUT}")

    csv_path = os.path.join(DATA_OUTPUT_DIR, 'arbitrage_opportunities.csv')
    write_csv(results, csv_path)
    print(f"候选清单已保存到 {csv_path}")

    nm = np.array([i['profit_margin'] for i in results])
    dv = np.array([i['avg_daily_volume'] for i in results])
    dp = np.array([i['ideal_profit'] for i in results])
    ce = np.array([i['capital_eff'] for i in results])
    gs = np.array([i['gross_spread_pct'] for i in results])
    print("\n统计信息:")
    print(f"  净收益率: 中位 {np.median(nm)*100:.1f}%  均值 {nm.mean()*100:.1f}%")
    print(f"  毛价差:   中位 {np.median(gs)*100:.1f}%")
    print(f"  日成交量: 中位 {np.median(dv):.0f}  均值 {dv.mean():.0f}")
    print(f"  日利润ISK: 中位 {np.median(dp):.0f}  合计 {dp.sum():.0f}")
    print(f"  资本日效率: 中位 {np.median(ce):.4f}")


if __name__ == "__main__":
    try:
        start_time = time.time()
        results = analyze_market()
        generate_report(results)
        print(f"\n总耗时: {time.time()-start_time:.2f}秒")
    except Exception as e:
        print(f"分析过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
