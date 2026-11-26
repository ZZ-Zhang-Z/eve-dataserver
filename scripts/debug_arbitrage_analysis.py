import sqlite3
import os
import sys
from datetime import datetime, timedelta
import numpy as np

# 将项目根目录加入搜索路径，以便导入 paths / database_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 导入全局数据库连接管理器
from database_manager import get_db_connection
from paths import DB_FILES

# 配置参数（与主脚本相同）
ANALYSIS_DAYS = 14
MIN_VOLUME = 20
MIN_PROFIT_MARGIN = 0.05

# 交易费用参数
BROKERAGE_FEE_RATE = 0.0171  # 中介费：价格的1.71%
SALES_TAX_RATE = 0.042  # 销售税：价格的4.2%

def get_blueprint_reaction_groups():
    """获取蓝图和反应分类及其所有子分类的市场组ID"""
    try:
        conn = sqlite3.connect(DB_FILES['items'])
        cursor = conn.cursor()
        cursor.execute("SELECT market_group_id, name, parent_group_id FROM market_groups WHERE name LIKE '%蓝图和反应%'")
        top_group = cursor.fetchone()
        
        if not top_group:
            print("没有找到蓝图和反应顶级组")
            return []
        
        cursor.execute("SELECT market_group_id, name, parent_group_id FROM market_groups")
        all_groups = cursor.fetchall()
        
        group_map = {}
        for group in all_groups:
            group_id = group[0]
            parent_id = group[2]
            name = group[1]
            if parent_id not in group_map:
                group_map[parent_id] = []
            group_map[parent_id].append({'id': group_id, 'name': name})
        
        def get_all_children(parent_id):
            children = []
            if parent_id not in group_map:
                return children
            for group in group_map[parent_id]:
                children.append(group['id'])
                children.extend(get_all_children(group['id']))
            return children
        
        blueprint_reaction_group_ids = [top_group[0]] + get_all_children(top_group[0])
        conn.close()
        return blueprint_reaction_group_ids
    except Exception as e:
        print(f"获取蓝图和反应市场组失败: {e}")
        return []

def get_personalized_groups():
    """获取个性化分类及其所有子分类的市场组ID"""
    try:
        conn = sqlite3.connect(DB_FILES['items'])
        cursor = conn.cursor()
        cursor.execute("SELECT market_group_id, name, parent_group_id FROM market_groups WHERE name LIKE '%个性化%'")
        top_group = cursor.fetchone()
        
        if not top_group:
            print("没有找到个性化分类")
            return []
        
        cursor.execute("SELECT market_group_id, name, parent_group_id FROM market_groups")
        all_groups = cursor.fetchall()
        
        group_map = {}
        for group in all_groups:
            group_id = group[0]
            parent_id = group[2]
            name = group[1]
            if parent_id not in group_map:
                group_map[parent_id] = []
            group_map[parent_id].append({'id': group_id, 'name': name})
        
        def get_all_children(parent_id):
            children = []
            if parent_id not in group_map:
                return children
            for group in group_map[parent_id]:
                children.append(group['id'])
                children.extend(get_all_children(group['id']))
            return children
        
        personalized_group_ids = [top_group[0]] + get_all_children(top_group[0])
        conn.close()
        return personalized_group_ids
    except Exception as e:
        print(f"获取个性化市场组失败: {e}")
        return []

def check_database_data():
    """检查数据库中的数据情况"""
    print("=== 检查数据库数据 ===")
    
    # 检查market_orders表
    orders_conn = get_db_connection('market_orders')
    orders_cursor = orders_conn.cursor()
    
    orders_cursor.execute("SELECT COUNT(*) FROM market_orders WHERE region_id = 10000002")
    total_orders = orders_cursor.fetchone()[0]
    print(f"\n1. 市场订单表 (market_orders):")
    print(f"   - 吉他区域订单总数: {total_orders}")
    
    orders_cursor.execute("SELECT COUNT(DISTINCT type_id) FROM market_orders WHERE region_id = 10000002")
    unique_types = orders_cursor.fetchone()[0]
    print(f"   - 不同物品类型数量: {unique_types}")
    
    orders_cursor.execute("SELECT COUNT(*) FROM market_orders WHERE region_id = 10000002 AND order_type = 'sell'")
    sell_orders = orders_cursor.fetchone()[0]
    print(f"   - 卖单数量: {sell_orders}")
    
    orders_cursor.execute("SELECT COUNT(*) FROM market_orders WHERE region_id = 10000002 AND order_type = 'buy'")
    buy_orders = orders_cursor.fetchone()[0]
    print(f"   - 买单数量: {buy_orders}")
    
    # 检查market_history表
    history_conn = get_db_connection('market_history')
    history_cursor = history_conn.cursor()
    
    history_cursor.execute("SELECT COUNT(*) FROM market_history WHERE region_id = 10000002")
    total_history = history_cursor.fetchone()[0]
    print(f"\n2. 市场历史表 (market_history):")
    print(f"   - 吉他区域历史记录总数: {total_history}")
    
    history_cursor.execute("SELECT COUNT(DISTINCT type_id) FROM market_history WHERE region_id = 10000002")
    history_unique_types = history_cursor.fetchone()[0]
    print(f"   - 有历史数据的物品类型数量: {history_unique_types}")
    
    cutoff_date = (datetime.now() - timedelta(days=ANALYSIS_DAYS)).strftime("%Y-%m-%d")
    history_cursor.execute("SELECT COUNT(DISTINCT type_id) FROM market_history WHERE region_id = 10000002 AND date >= ?", (cutoff_date,))
    recent_types = history_cursor.fetchone()[0]
    print(f"   - 过去{ANALYSIS_DAYS}天有数据的物品类型数量: {recent_types}")
    
    # 检查有足够历史数据的物品
    history_cursor.execute('''
        SELECT type_id, COUNT(*) as day_count
        FROM market_history
        WHERE region_id = 10000002 AND date >= ?
        GROUP BY type_id
        HAVING COUNT(*) >= 6
    ''', (cutoff_date,))
    enough_history_types = history_cursor.fetchall()
    print(f"   - 有6天以上历史数据的物品类型数量: {len(enough_history_types)}")
    
    # 检查items表
    items_conn = get_db_connection('items')
    items_cursor = items_conn.cursor()
    
    items_cursor.execute("SELECT COUNT(*) FROM items")
    total_items = items_cursor.fetchone()[0]
    print(f"\n3. 物品信息表 (items):")
    print(f"   - 物品总数: {total_items}")
    
    # 检查过滤条件
    print(f"\n4. 过滤条件分析:")
    trade_goods_groups = (19, 20, 22, 23, 491, 492, 614, 616, 738, 739, 754, 940, 1109, 1427, 1700, 1840, 1846, 2013, 2317, 2456, 2480, 2799, 2801, 3732, 3737, 730, 731, 732, 733, 734, 735, 736, 737, 740, 741, 742, 743, 744, 745, 746, 747, 748, 749, 750, 751, 752, 2457, 2458, 2459, 2460, 2461, 2706, 2747, 2756, 2757, 3734)
    special_edition_groups = (1659, 1660, 1661, 1662, 1663, 1664, 1810, 1811, 1814, 2760)
    skill_groups = (150, 364, 365, 366, 367, 368, 369, 370, 372, 373, 374, 375, 376, 377, 378, 1110, 1323, 1745, 1746, 1747, 1748, 1823, 1824, 2152, 3656, 531, 1469, 1470, 1471, 1472, 1473, 1474, 1475, 1476, 1477, 1478, 1479, 1761, 1762, 1763, 1764, 2473, 2358)
    skin_groups = (1954, 1955, 1960, 1968, 1988, 1989, 1998, 2006, 2011, 2119, 2283, 2306, 2315, 2120)
    blueprint_reaction_groups = tuple(get_blueprint_reaction_groups())
    personalized_groups = tuple(get_personalized_groups())
    
    exclude_groups = trade_goods_groups + special_edition_groups + skill_groups + skin_groups + blueprint_reaction_groups + personalized_groups
    print(f"   - 被排除的市场组数量: {len(exclude_groups)}")
    print(f"     - 贸易货物: {len(trade_goods_groups)}")
    print(f"     - 特别版物品: {len(special_edition_groups)}")
    print(f"     - 技能: {len(skill_groups)}")
    print(f"     - 舰船涂装: {len(skin_groups)}")
    print(f"     - 蓝图和反应: {len(blueprint_reaction_groups)}")
    print(f"     - 个性化: {len(personalized_groups)}")
    
    # 检查同时有订单和历史数据的物品
    print(f"\n5. 交叉数据检查:")
    orders_cursor.execute("SELECT DISTINCT type_id FROM market_orders WHERE region_id = 10000002")
    order_type_ids = set([row[0] for row in orders_cursor.fetchall()])
    
    history_cursor.execute(f'''
        SELECT DISTINCT type_id 
        FROM market_history 
        WHERE region_id = 10000002 AND date >= ?
        GROUP BY type_id
        HAVING COUNT(*) >= 6
    ''', (cutoff_date,))
    history_type_ids = set([row[0] for row in history_cursor.fetchall()])
    
    # 获取非排除组的物品
    items_cursor.execute("SELECT type_id, market_group_id FROM items")
    items_data = items_cursor.fetchall()
    valid_type_ids = set()
    excluded_type_ids = set()
    
    for type_id, market_group_id in items_data:
        if market_group_id is None or market_group_id not in exclude_groups:
            valid_type_ids.add(type_id)
        else:
            excluded_type_ids.add(type_id)
    
    print(f"   - 有订单数据的物品: {len(order_type_ids)}")
    print(f"   - 有足够历史数据的物品: {len(history_type_ids)}")
    print(f"   - 非排除组的物品: {len(valid_type_ids)}")
    
    # 同时满足三个条件的物品
    candidate_types = order_type_ids & history_type_ids & valid_type_ids
    print(f"   - 同时满足所有条件的候选物品: {len(candidate_types)}")
    
    # 检查候选物品的订单情况
    if candidate_types:
        print(f"\n6. 候选物品订单情况抽样:")
        sample_types = list(candidate_types)[:10]
        placeholders = ','.join(['?'] * len(sample_types))
        
        orders_cursor.execute(f'''
            SELECT type_id, order_type, MIN(price) as min_price, MAX(price) as max_price, COUNT(*) as count
            FROM market_orders
            WHERE region_id = 10000002 AND type_id IN ({placeholders}) AND system_id = 30000142
            GROUP BY type_id, order_type
        ''', sample_types)
        
        order_info = {}
        for row in orders_cursor.fetchall():
            type_id = row[0]
            order_type = row[1]
            if type_id not in order_info:
                order_info[type_id] = {'sell': None, 'buy': None}
            if order_type == 'sell':
                order_info[type_id]['sell'] = {'price': row[2], 'count': row[4]}
            else:
                order_info[type_id]['buy'] = {'price': row[3], 'count': row[4]}
        
        # 计算利润率
        print(f"{'type_id':<10} {'卖单价':<12} {'买单价':<12} {'价差':<12} {'潜在利润率':<12}")
        print("-" * 60)
        
        total_count = 0
        profitable_count = 0
        
        for type_id in sample_types:
            if type_id in order_info:
                sell_info = order_info[type_id].get('sell')
                buy_info = order_info[type_id].get('buy')
                
                if sell_info and buy_info:
                    sell_price = sell_info['price']
                    buy_price = buy_info['price']
                    
                    # 计算挂单套利利润
                    user_buy_price = buy_price
                    user_sell_price = sell_price
                    
                    purchase_cost = user_buy_price * (1 + BROKERAGE_FEE_RATE)
                    sale_revenue = user_sell_price * (1 - BROKERAGE_FEE_RATE - SALES_TAX_RATE)
                    
                    profit_per_unit = sale_revenue - purchase_cost
                    if purchase_cost > 0:
                        profit_margin = profit_per_unit / purchase_cost
                    else:
                        profit_margin = 0
                    
                    spread = sell_price - buy_price
                    total_count += 1
                    if profit_margin > 0:
                        profitable_count += 1
                    
                    print(f"{type_id:<10} {sell_price:<11.2f} {buy_price:<11.2f} {spread:<11.2f} {profit_margin*100:<11.1f}%")
        
        print(f"\n   抽样统计: 共{total_count}个物品，{profitable_count}个有正利润")

if __name__ == "__main__":
    check_database_data()
