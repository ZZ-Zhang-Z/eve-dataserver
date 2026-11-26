# paths.py
# 集中管理项目路径常量：所有路径基于本文件位置推导，避免依赖当前工作目录(CWD)。

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_OUTPUT_DIR = os.path.join(DATA_DIR, 'output')
DATA_BACKUP_DIR = os.path.join(DATA_DIR, 'backup')
LOGS_DIR = os.path.join(BASE_DIR, 'logs')

# 各数据库文件路径（database_manager 与各脚本统一引用）
DB_FILES = {
    'items': os.path.join(DATA_DIR, 'eve_items.db'),
    'market_orders': os.path.join(DATA_DIR, 'eve_market_orders.db'),
    'market_history': os.path.join(DATA_DIR, 'eve_market_history.db'),
    'universe': os.path.join(DATA_DIR, 'eve_universe.db'),
    'cache': os.path.join(DATA_DIR, 'eve_cache.db'),
    'wallet': os.path.join(DATA_DIR, 'eve_wallet.db'),
}

# 分析产物输出路径
ARBITRAGE_OUTPUT = os.path.join(DATA_OUTPUT_DIR, 'arbitrage_opportunities.json')