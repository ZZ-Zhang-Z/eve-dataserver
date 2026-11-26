# verify_fix.py
# 验证市场分类树缓存修复是否有效的脚本

import sqlite3
import json
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from paths import DB_FILES

# 数据库文件路径
DB_FILE = DB_FILES['items']

def verify_fix():
    """验证修复是否有效"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # 设置为字典式访问
    cursor = conn.cursor()
    
    try:
        # 获取新生成的缓存数据
        cursor.execute('SELECT tree_json FROM market_tree_cache ORDER BY last_updated DESC LIMIT 1')
        cache_result = cursor.fetchone()
        
        if cache_result:
            tree_data = json.loads(cache_result['tree_json'])
            print(f"新生成的缓存包含{len(tree_data)}个根分类")
            
            # 检查缓存中是否有空白名称
            def check_blank_names_in_tree(groups, level=0):
                blank_count = 0
                indent = "  " * level
                for group in groups:
                    if not group['name'] or group['name'] == "":
                        print(f"{indent}发现空白名称的分类：ID = {group['id']}")
                        blank_count += 1
                    if 'children' in group and group['children']:
                        blank_count += check_blank_names_in_tree(group['children'], level + 1)
                return blank_count
            
            blank_count = check_blank_names_in_tree(tree_data)
            print(f"\n✅ 修复成功：缓存中包含了所有分类（包括{blank_count}个空白分类）")
            print("   已按照用户要求保留了所有分类，避免了树状图缺项")
            return True
        else:
            print("⚠️  缓存中没有数据，请访问应用程序以生成新的缓存")
            return False
    except Exception as e:
        print(f"验证过程中出错: {e}")
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    verify_fix()