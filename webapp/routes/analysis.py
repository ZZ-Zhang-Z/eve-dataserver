# webapp/routes/analysis.py
# 交易分析接口：读取套利分析结果 JSON 并按条件筛选排序。

import json

from flask import Blueprint, jsonify, request

from database_manager import get_connection_by_table
import paths

bp = Blueprint('analysis', __name__)


@bp.route('/api/analysis')
def get_analysis_results():
    """获取交易分析结果"""
    # 从JSON文件中读取分析结果
    try:
        arbitrage_file = paths.ARBITRAGE_OUTPUT
        with open(arbitrage_file, 'r', encoding='utf-8') as f:
            results = json.load(f)

        # 获取筛选参数
        min_profit = float(request.args.get('min_profit', 0))
        min_ideal_profit_param = request.args.get('min_ideal_profit', '0')
        item_group = request.args.get('item_group', '')
        sort_by = request.args.get('sort_by', 'score')
        sort_order = request.args.get('sort_order', 'desc')

        # 如果有物品组筛选，需要获取物品的market_group_id映射和所有子分组ID
        item_market_groups = {}
        selected_group_ids = []
        if item_group:
            try:
                # 获取所有子分组ID
                conn = get_connection_by_table('market_groups')
                cursor = conn.cursor()

                # 递归获取所有子分组ID
                def get_all_child_group_ids(parent_id):
                    group_ids = [parent_id]
                    # 获取直接子分组
                    cursor.execute("SELECT market_group_id FROM market_groups WHERE parent_group_id = ?", (parent_id,))
                    child_groups = cursor.fetchall()
                    # 递归获取所有子分组的子分组
                    for child in child_groups:
                        group_ids.extend(get_all_child_group_ids(child['market_group_id']))
                    return group_ids

                # 获取选中分组及其所有子分组ID
                selected_group_id = int(item_group)
                selected_group_ids = get_all_child_group_ids(selected_group_id)

                # 获取物品的market_group_id
                type_ids = [item['type_id'] for item in results]
                if type_ids:
                    # 使用参数化查询，注意SQLite的参数占位符是?
                    placeholders = ','.join(['?'] * len(type_ids))
                    cursor.execute(f"SELECT type_id, market_group_id FROM items WHERE type_id IN ({placeholders})", type_ids)

                    for row in cursor.fetchall():
                        item_market_groups[row['type_id']] = row['market_group_id']

                conn.close()
            except Exception as e:
                print(f"获取物品市场组信息失败: {e}")
                # 即使获取失败，也继续执行，不影响其他筛选

        # 应用筛选条件
        filtered_results = []
        for item in results:
            # 检查利润率筛选
            profit_condition = item['profit_margin'] >= min_profit

            # 检查理想利润筛选
            ideal_profit_condition = True
            if min_ideal_profit_param == '':
                # 不筛选理想利润
                ideal_profit_condition = True
            elif min_ideal_profit_param == '5000000_less':
                # 筛选理想利润≤5,000,000 ISK的项
                ideal_profit_condition = item['ideal_profit'] <= 5000000
            else:
                # 筛选理想利润≥指定值的项
                min_ideal_profit = float(min_ideal_profit_param)
                ideal_profit_condition = item['ideal_profit'] >= min_ideal_profit

            # 检查物品组筛选
            item_group_condition = True
            if item_group and selected_group_ids:
                try:
                    # 检查物品的market_group_id是否在选中的分组ID列表中
                    item_type_id = item['type_id']
                    if item_type_id in item_market_groups:
                        item_group_condition = (item_market_groups[item_type_id] in selected_group_ids)
                    else:
                        # 如果没有找到物品的market_group_id，默认不匹配
                        item_group_condition = False
                except ValueError:
                    # 如果item_group不是有效的整数，默认不匹配
                    item_group_condition = False

            if profit_condition and ideal_profit_condition and item_group_condition:
                filtered_results.append(item)

        # 应用排序
        filtered_results.sort(key=lambda x: x.get(sort_by, 0), reverse=(sort_order == 'desc'))

        # 计算所有已分析物品的期望利润总和
        total_ideal_profit_all = sum(item['ideal_profit'] for item in results)

        # 返回结果
        return jsonify({
            'total_items': len(results),
            'total_ideal_profit_all': total_ideal_profit_all,
            'results': filtered_results
        })

    except FileNotFoundError:
        return jsonify({
            'total_items': 0,
            'results': []
        }), 404
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500