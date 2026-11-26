# analyze_blank_categories.py
# 用于分析EVE Online市场数据中的空白分类信息，包括空白分类的数量、父分类、包含的物品以及子分类情况
import sqlite3
import json
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from paths import DB_FILES

# 数据库文件路径
DB_FILE = DB_FILES['items']

def analyze_blank_categories():
    """分析空白分类的详细信息"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # 获取所有空白名称的分类
        cursor.execute('SELECT market_group_id, name, parent_group_id FROM market_groups WHERE name IS NULL OR name = ""')
        blank_groups = cursor.fetchall()
        
        print(f"发现{len(blank_groups)}个空白名称的分类")
        print("\n详细信息：")
        
        # 分析每个空白分类
        for group in blank_groups:
            group_id = group['market_group_id']
            parent_id = group['parent_group_id']
            
            print(f"分类ID: {group_id}, 父分类ID: {parent_id}")
            
            # 检查父分类信息
            if parent_id:
                cursor.execute('SELECT name FROM market_groups WHERE market_group_id = ?', (parent_id,))
                parent = cursor.fetchone()
                if parent:
                    print(f"  父分类名称: {parent['name']}")
                else:
                    print(f"  父分类不存在")
            else:
                print("  这是一个根分类")
            
            # 检查该分类下的物品
            cursor.execute('SELECT COUNT(*) as item_count FROM items WHERE market_group_id = ?', (group_id,))
            item_count = cursor.fetchone()['item_count']
            print(f"  分类下物品数量: {item_count}")
            
            # 如果有物品，显示一些示例
            if item_count > 0:
                cursor.execute('SELECT type_id, name FROM items WHERE market_group_id = ? LIMIT 3', (group_id,))
                items = cursor.fetchall()
                print("  部分物品示例:")
                for item in items:
                    print(f"    - {item['name']} (ID: {item['type_id']})")
            
            print()
            
        # 检查这些空白分类是否有子分类
        print("\n检查空白分类是否有子分类：")
        for group in blank_groups:
            group_id = group['market_group_id']
            cursor.execute('SELECT COUNT(*) as child_count FROM market_groups WHERE parent_group_id = ?', (group_id,))
            child_count = cursor.fetchone()['child_count']
            if child_count > 0:
                print(f"分类ID {group_id} 有 {child_count} 个子分类")
                cursor.execute('SELECT market_group_id, name FROM market_groups WHERE parent_group_id = ?', (group_id,))
                children = cursor.fetchall()
                for child in children:
                    print(f"  - 子分类: {child['name']} (ID: {child['market_group_id']})")
                print()
                
    except Exception as e:
        print(f"分析过程中出错: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    analyze_blank_categories()