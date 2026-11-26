# webapp/__init__.py
# Flask 应用工厂：创建并配置应用（CORS、secret_key、初始化钱包表、注册各 Blueprint）。

import os

from flask import Flask
from flask_cors import CORS

import paths
from database_manager import get_connection_by_table

from . import config
from .routes.pages import bp as pages_bp
from .routes.wallet import bp as wallet_bp
from .routes.analysis import bp as analysis_bp
from .routes.market import bp as market_bp
from .routes.sso import bp as sso_bp
from .routes.collectors import bp as collectors_bp


def init_wallet_db():
    """初始化钱包数据库表。"""
    conn = get_connection_by_table('wallet_transactions')
    cursor = conn.cursor()

    # 创建钱包交易表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            datetime TEXT NOT NULL,
            type TEXT NOT NULL,
            amount INTEGER NOT NULL,
            balance INTEGER NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(datetime, type, amount, balance)  -- 避免重复记录
        )
    ''')

    # 创建索引以提高查询性能
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_datetime 
        ON wallet_transactions (datetime DESC)
    ''')

    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_wallet_transactions_type 
        ON wallet_transactions (type)
    ''')

    conn.commit()
    conn.close()


def create_app():
    """创建并配置 Flask 应用。"""
    app = Flask(
        __name__,
        template_folder=os.path.join(paths.BASE_DIR, 'templates'),
    )
    CORS(app)
    app.secret_key = config.get_secret_key()

    # 应用启动时初始化数据库
    with app.app_context():
        init_wallet_db()

    # 注册各功能域 Blueprint（URL 路径与拆分前保持一致）
    app.register_blueprint(pages_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(sso_bp)
    app.register_blueprint(collectors_bp)

    return app