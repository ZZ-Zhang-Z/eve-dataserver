# paths.py
# 集中管理项目路径常量：所有路径基于本文件位置推导，不依赖当前工作目录(CWD)。
#
# 本目录即项目根（独立项目布局）。若需要把数据放到别处（例如与本地分析脚本
# 共用同一份数据库），设置环境变量 EVE_BASE_DIR 指向目标目录即可：
#   EVE_BASE_DIR=/home/admin/eve_helper python controller.py
#
# 目录布局：
#   <项目根>/                  <- BASE_DIR
#     ├── controller.json      控制器调度表
#     ├── config.json          采集器运行时配置（由 config.collector.example.json 生成）
#     ├── data/                各 SQLite 库
#     ├── logs/
#     └── collectors/ scripts/ runners/ core/ plugins/ tests/

import os

BASE_DIR = os.environ.get('EVE_BASE_DIR') or os.path.dirname(os.path.abspath(__file__))
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


def ensure_dirs():
    """创建运行时必需目录（幂等）。控制器启动与各采集器入口都可调用。"""
    for path in (DATA_DIR, DATA_OUTPUT_DIR, DATA_BACKUP_DIR,
                 LOGS_DIR, os.path.join(LOGS_DIR, 'collectors')):
        os.makedirs(path, exist_ok=True)
    return BASE_DIR
