# paths.py（EVEDataserver 自包含版）
#
# 与项目根 paths.py 语义保持一致：数据、日志、config.json 仍位于**项目根**，
# 便于服务器上与其他脚本（分析、缓存管理）共享同一份数据库。
#
# 差别只有一处：本文件位于 EVEDataserver/ 内，因此 BASE_DIR 取上一级目录，
# 否则 data/ 与 logs/ 会被错误地解析到 EVEDataserver/data 下。
#
# 目录结构：
#   <项目根>/                     <- BASE_DIR
#     ├── config.json             <- esi_client / 采集器读取的运行时配置
#     ├── data/                   <- 各 SQLite 库
#     ├── logs/
#     └── EVEDataserver/
#           ├── paths.py          <- 本文件
#           ├── database_manager.py
#           ├── collectors/       <- 采集器与 esi_client
#           ├── scripts/          <- aggregate_monthly_history
#           └── runners/

import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
