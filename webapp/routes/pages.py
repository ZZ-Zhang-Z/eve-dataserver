# webapp/routes/pages.py
# 页面路由：首页、分析页、钱包页、采集器控制台页。

from flask import Blueprint, render_template

bp = Blueprint('pages', __name__)


@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/analysis')
def trading_analysis():
    return render_template('analysis.html')


@bp.route('/wallet')
def wallet():
    return render_template('wallet.html')


@bp.route('/collectors')
def collectors_page():
    return render_template('collectors.html')