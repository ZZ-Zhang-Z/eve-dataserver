# test_market_orders.py
# 测试market_orders表中数据是否正确保存的脚本
import sqlite3
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from paths import DB_FILES

# 数据库配置
DB_FILE = DB_FILES['items']

def test_market_orders():
    """测试market_orders表中的数据是否正确保存"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 1. 检查总订单数
        cursor.execute('SELECT COUNT(*) FROM market_orders')
        total_orders = cursor.fetchone()[0]
        print(f"数据库中的总订单数: {total_orders}")
        
        # 2. 检查每个区域的订单数
        cursor.execute('SELECT region_id, COUNT(*) FROM market_orders GROUP BY region_id')
        region_orders = cursor.fetchall()
        print("\n每个区域的订单数:")
        for region_id, count in region_orders:
            region_name = "吉他市场" if region_id == 10000002 else "艾玛市场" if region_id == 10000043 else "未知市场"
            print(f"{region_name} ({region_id}): {count}个订单")
        
        # 3. 检查买单和卖单的数量
        cursor.execute('SELECT order_type, COUNT(*) FROM market_orders GROUP BY order_type')
        order_type_counts = cursor.fetchall()
        print("\n买单和卖单的数量:")
        for order_type, count in order_type_counts:
            print(f"{order_type}单: {count}个订单")
        
        # 4. 查看前5个订单的详细信息
        cursor.execute('SELECT * FROM market_orders LIMIT 5')
        sample_orders = cursor.fetchall()
        print("\n前5个订单的详细信息:")
        print("order_id | region_id | type_id | order_type | price | volume_remain | volume_total | min_volume | is_buy_order | duration | range | issued | system_id | location_id")
        print("-" * 150)
        for order in sample_orders:
            print(f"{order[0]} | {order[1]} | {order[2]} | {order[3]} | {order[4]} | {order[5]} | {order[6]} | {order[7]} | {order[8]} | {order[9]} | {order[10]} | {order[11]} | {order[12]} | {order[13]}")
        
    except Exception as e:
        print(f"测试数据库时发生异常: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    test_market_orders()