# webapp/routes/market.py
# 市场数据接口：市场分类树、分类物品、物品订单、物品历史。

import json

from flask import Blueprint, jsonify

from database_manager import get_connection_by_table

bp = Blueprint('market', __name__)


@bp.route('/api/market_groups')
def get_market_groups():
    """获取市场分类树（使用缓存）"""
    try:
        # 尝试从缓存获取
        cache_conn = get_connection_by_table('market_tree_cache')
        cache_cursor = cache_conn.cursor()
        cache_cursor.execute('SELECT tree_json FROM market_tree_cache ORDER BY last_updated DESC LIMIT 1')
        result = cache_cursor.fetchone()

        if result:
            tree_json = result['tree_json']
            root_groups = json.loads(tree_json)
            return jsonify(root_groups)
        else:
            # 缓存不存在，构建树结构
            items_conn = get_connection_by_table('market_groups')
            items_cursor = items_conn.cursor()
            items_cursor.execute('SELECT market_group_id, name, parent_group_id FROM market_groups')
            groups = items_cursor.fetchall()

            # 构建分类树，包含所有分类（包括空白名称的分类）
            group_dict = {}
            for group in groups:
                group_id = group['market_group_id']
                group_name = group['name']

                # 使用原始名称（包括空白），不进行过滤
                group_dict[group_id] = {
                    'id': group_id,
                    'name': group_name,
                    'parent_id': group['parent_group_id'],
                    'children': []
                }

            # 构建树结构
            root_groups = []
            for group in group_dict.values():
                parent_id = group['parent_id']
                if parent_id is None:
                    root_groups.append(group)
                elif parent_id in group_dict:
                    group_dict[parent_id]['children'].append(group)

            # 保存到缓存
            tree_json = json.dumps(root_groups)
            cache_cursor.execute('INSERT INTO market_tree_cache (tree_json) VALUES (?)', (tree_json,))
            cache_conn.commit()

            return jsonify(root_groups)
    finally:
        pass


@bp.route('/api/market_items/<int:group_id>')
def get_market_items(group_id):
    """获取分类下的物品列表"""
    conn = get_connection_by_table('items')
    cursor = conn.cursor()

    # 获取分类下的所有物品
    cursor.execute('''
        SELECT i.type_id, i.name 
        FROM items i 
        WHERE i.market_group_id = ? AND i.published = 1
        ORDER BY i.name
    ''', (group_id,))
    items = cursor.fetchall()

    return jsonify([{'id': item['type_id'], 'name': item['name']} for item in items])


@bp.route('/api/market_orders/<int:type_id>')
def get_market_orders(type_id):
    """获取物品的订单数据"""
    conn = get_connection_by_table('market_orders')
    cursor = conn.cursor()

    # 获取卖单数据（按价格升序）
    cursor.execute('''
        SELECT order_id, price, volume_remain, volume_total, duration, issued, system_id, location_id
        FROM market_orders 
        WHERE region_id = 10000002 AND type_id = ? AND order_type = 'sell' AND system_id = 30000142
        ORDER BY price ASC
        LIMIT 50;
    ''', (type_id,))
    sell_orders = cursor.fetchall()

    # 获取买单数据（按价格降序）
    cursor.execute('''
        SELECT order_id, price, volume_remain, volume_total, duration, issued, system_id, location_id
        FROM market_orders 
        WHERE region_id = 10000002 AND type_id = ? AND order_type = 'buy' AND system_id = 30000142
        ORDER BY price DESC
        LIMIT 50;
    ''', (type_id,))
    buy_orders = cursor.fetchall()

    return jsonify({
        'sell_orders': [dict(order) for order in sell_orders],
        'buy_orders': [dict(order) for order in buy_orders]
    })


@bp.route('/api/market_history/<int:type_id>')
def get_market_history(type_id):
    """获取物品的历史订单数据（近一个月）"""
    conn = get_connection_by_table('market_history')
    cursor = conn.cursor()

    # 获取近一个月的历史订单数据
    cursor.execute('''
        SELECT date AS period, average AS avg_price, highest AS max_price, lowest AS min_price, order_count AS total_orders, volume AS total_volume
        FROM market_history
        WHERE region_id = 10000002 AND type_id = ?
        ORDER BY date DESC
        LIMIT 30;
    ''', (type_id,))
    history_data = cursor.fetchall()

    # 转换为数组格式，便于前端处理
    return jsonify([dict(row) for row in history_data])