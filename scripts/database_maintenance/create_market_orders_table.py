# create_market_orders_table.py
# 创建市场订单表结构market_orders，用于存储EVE Online的市场订单数据
import sqlite3
import logging
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from paths import DB_FILES

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 数据库配置
DB_FILE = DB_FILES['items']

def create_market_orders_table():
    """创建market_orders表结构（如果不存在）"""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # 创建market_orders表（如果不存在），不会删除现有表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_orders (
            order_id INTEGER PRIMARY KEY,
            region_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            order_type TEXT NOT NULL,
            price REAL NOT NULL,
            volume_remain INTEGER NOT NULL,
            volume_total INTEGER NOT NULL,
            min_volume INTEGER NOT NULL,
            is_buy_order INTEGER NOT NULL,
            duration INTEGER NOT NULL,
            range INTEGER NOT NULL,
            issued TIMESTAMP NOT NULL,
            system_id INTEGER NOT NULL,
            location_id INTEGER NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (region_id) REFERENCES regions (region_id)
        )
        '''),
        
        # 创建索引以提高查询性能
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_orders_region_id ON market_orders (region_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_orders_type_id ON market_orders (type_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_orders_order_type ON market_orders (order_type)')
        
        conn.commit()
        logger.info("market_orders表结构创建成功")
    except Exception as e:
        logger.error(f"创建market_orders表结构时发生异常: {e}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    create_market_orders_table()
