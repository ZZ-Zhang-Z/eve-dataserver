# create_cache.py
# 创建市场分类树的缓存，将market_groups表中的分类数据构建成树状结构并保存到market_tree_cache表
import sqlite3
import json
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from paths import DB_FILES

conn = sqlite3.connect(DB_FILES['items'])
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# 创建缓存表
cursor.execute('''
CREATE TABLE IF NOT EXISTS market_tree_cache (
    id INTEGER PRIMARY KEY,
    tree_json TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
''')

# 检查缓存是否存在
cursor.execute('SELECT COUNT(*) FROM market_tree_cache')
count = cursor.fetchone()[0]

if count == 0:
    print('Creating initial cache...')
    
    # 获取所有市场分类
    cursor.execute('SELECT market_group_id, name, parent_group_id FROM market_groups')
    groups = cursor.fetchall()
    
    # 构建分类树
    group_dict = {}
    for group in groups:
        group_id = group['market_group_id']
        group_dict[group_id] = {
            'id': group_id,
            'name': group['name'],
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
    cursor.execute('INSERT INTO market_tree_cache (tree_json) VALUES (?)', (tree_json,))
    conn.commit()
    
    print('Cache created successfully!')
else:
    print('Cache already exists')

conn.close()