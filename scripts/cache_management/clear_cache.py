# clear_cache.py
# 清理市场分类树缓存数据的脚本
import sqlite3
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from paths import DB_FILES

# 数据库文件路径
DB_FILE = DB_FILES['items']

def clear_market_tree_cache():
    """清理市场分类树缓存"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # 删除所有缓存数据
        cursor.execute('DELETE FROM market_tree_cache')
        conn.commit()
        print("缓存已成功清理")
    except Exception as e:
        print(f"清理缓存时出错: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    clear_market_tree_cache()
