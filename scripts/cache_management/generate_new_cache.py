# generate_new_cache.py
# 通过API请求生成新的市场分类缓存
import requests
import json

# 访问API生成新的缓存
try:
    response = requests.get('http://localhost:5000/api/market_groups')
    if response.status_code == 200:
        data = response.json()
        print(f"API请求成功，返回了{len(data)}个根分类")
        print("新的缓存已生成")
    else:
        print(f"API请求失败: {response.status_code}")
except Exception as e:
    print(f"请求过程中发生错误: {e}")
