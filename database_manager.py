import sqlite3
import threading

from paths import DB_FILES

# 数据库文件路径配置（集中定义于 paths.py，基于文件位置推导，不依赖 CWD）
DB_CONFIG = DB_FILES

# 表到数据库的映射
table_to_db = {
    # 物品数据库
    "items": "items",
    "item_attributes": "items",
    "item_effects": "items",
    "market_groups": "items",
    "market_group_items": "items",
    
    # 市场订单数据库
    "market_orders": "market_orders",
    
    # 市场历史数据库
    "market_history": "market_history",
    "market_history_monthly": "market_history",
    
    # 宇宙数据数据库
    "regions": "universe",
    "region_constellations": "universe",
    "constellations": "universe",
    "constellation_systems": "universe",
    "systems": "universe",
    
    # 缓存数据库
    "market_tree_cache": "cache",
    "http_cache": "cache",
    
    # 钱包数据库
    "wallet_transactions": "wallet"
}

class DatabaseManager:
    """数据库连接管理器，支持多线程安全的数据库连接"""
    
    def __init__(self):
        # 使用线程本地存储来存储每个线程的连接
        self.local = threading.local()
    
    def get_connection(self, db_type):
        """获取指定类型的数据库连接（线程安全）"""
        # 确保local对象有connections属性
        if not hasattr(self.local, 'connections'):
            self.local.connections = {}
        
        if db_type not in self.local.connections:
            if db_type not in DB_CONFIG:
                raise ValueError(f"未知的数据库类型: {db_type}")
            
            db_file = DB_CONFIG[db_type]
            
            # 创建新的数据库连接（如果文件不存在会自动创建）
            conn = sqlite3.connect(db_file)
            conn.row_factory = sqlite3.Row
            
            # 启用WAL模式以提高性能
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")  # WAL 下提交不再逐次 fsync，显著加快写库
            cursor.execute("PRAGMA cache_size=-100000;")  # 100MB缓存
            
            # 存储连接到当前线程的local对象
            self.local.connections[db_type] = conn
        
        return self.local.connections[db_type]
    
    def get_connection_by_table(self, table_name):
        """根据表名获取相应的数据库连接（线程安全）"""
        if table_name not in table_to_db:
            raise ValueError(f"未知的表名: {table_name}")
        
        db_type = table_to_db[table_name]
        return self.get_connection(db_type)
    
    def close_all(self):
        """关闭当前线程的所有数据库连接"""
        if hasattr(self.local, 'connections'):
            for conn in self.local.connections.values():
                conn.close()
            self.local.connections.clear()

# 创建全局数据库管理器实例
db_manager = DatabaseManager()

# 数据库连接工具函数
def get_db_connection(db_type):
    """获取指定类型的数据库连接"""
    return db_manager.get_connection(db_type)

def get_connection_by_table(table_name):
    """根据表名获取相应的数据库连接"""
    return db_manager.get_connection_by_table(table_name)