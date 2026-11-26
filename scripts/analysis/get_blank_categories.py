# get_blank_categories.py
# 获取所有名称为空或空白的分类ID，并以逗号分隔输出
import sqlite3
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from paths import DB_FILES

# 数据库文件路径
DB_FILE = DB_FILES['items']

def get_blank_categories():
    """
    获取所有仍然是空白的分类ID，并用逗号分隔输出
    """
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 查询所有名称为空或空白的分类
    cursor.execute('SELECT market_group_id FROM market_groups WHERE name IS NULL OR name = ""')
    blank_groups = cursor.fetchall()
    
    # 提取分类ID并转换为字符串列表
    blank_group_ids = [str(group[0]) for group in blank_groups]
    
    # 用逗号分隔输出
    result = ','.join(blank_group_ids)
    print(result)
    
    conn.close()

if __name__ == "__main__":
    get_blank_categories()
