# query_jita_tritanium.py
# 查询吉他市场三钛合金的市场订单数据，用于分析价格趋势和交易量
import sqlite3
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from paths import DB_FILES

# 数据库文件路径
DB_FILE = DB_FILES['items']

def query_tritanium_market():
    """
    查询吉他市场三钛合金的卖单数据
    """
    try:
        # 连接数据库
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 步骤1: 查询三钛合金的type_id
        cursor.execute("SELECT type_id, name FROM items WHERE name LIKE '%三钛合金%' LIMIT 10;")
        tritanium_items = cursor.fetchall()
        
        if not tritanium_items:
            print("未找到三钛合金相关物品")
            return
        
        print("找到的三钛合金相关物品:")
        for item in tritanium_items:
            print(f"type_id: {item[0]}, 名称: {item[1]}")
        
        # 假设第一个结果是我们需要的三钛合金
        tritanium_type_id = tritanium_items[0][0]
        print(f"\n使用的三钛合金type_id: {tritanium_type_id}")
        
        # 步骤2: 查询吉他市场三钛合金的卖单数据
        cursor.execute('''
            SELECT order_id, price, volume_remain, volume_total, duration, issued, system_id, location_id
            FROM market_orders 
            WHERE region_id = 10000002 
              AND type_id = ? 
              AND order_type = 'sell'
            ORDER BY price ASC
            LIMIT 20;
        ''', (tritanium_type_id,))
        
        sell_orders = cursor.fetchall()
        
        if not sell_orders:
            print("未找到吉他市场三钛合金的卖单数据")
            return
        
        print(f"\n吉他市场三钛合金的卖单数据 (共 {len(sell_orders)} 条，按价格升序排列):")
        print("order_id | price | volume_remain | volume_total | duration | issued | system_id | location_id")
        print("-" * 130)
        
        for order in sell_orders:
            print(f"{order[0]} | {order[1]} | {order[2]} | {order[3]} | {order[4]} | {order[5]} | {order[6]} | {order[7]}")
        
        # 步骤3: 查询市场统计信息
        cursor.execute('''
            SELECT MIN(price), AVG(price), MAX(price), SUM(volume_remain)
            FROM market_orders 
            WHERE region_id = 10000002 
              AND type_id = ? 
              AND order_type = 'sell';
        ''', (tritanium_type_id,))
        
        stats = cursor.fetchone()
        if stats:
            print(f"\n吉他市场三钛合金卖单统计:")
            print(f"最低价格: {stats[0]:.2f}")
            print(f"平均价格: {stats[1]:.2f}")
            print(f"最高价格: {stats[2]:.2f}")
            print(f"总可售数量: {stats[3]:,}")
            
    except Exception as e:
        print(f"查询过程中发生错误: {str(e)}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    query_tritanium_market()