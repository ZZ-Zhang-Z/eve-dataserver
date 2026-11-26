# webapp/routes/collectors.py
# 数据采集器控制台接口：状态查询、启动、停止、增量日志、数据时效。
#
# 采集器进程与运行状态为进程内全局单例状态，集中定义在本模块，避免拆分后出现多份状态。

import json
import os
import sqlite3
import subprocess
import sys
import threading
import time

from flask import Blueprint, jsonify, request

import paths

bp = Blueprint('collectors', __name__)

PROJECT_ROOT = paths.BASE_DIR
COLLECTOR_LOG_DIR = os.path.join(paths.LOGS_DIR, 'collectors')

# 订单追踪开关存放在项目根目录 config.json，采集器运行时以文件 mtime 热读取。
CONFIG_PATH = os.path.join(paths.BASE_DIR, 'config.json')
# 默认值与采集器 load_tracker_config 保持一致
TRACKER_DEFAULTS = {'enabled': False, 'interval_minutes': 30, 'retention_hours': 72}

# 可控制的采集器（key -> 元数据）
COLLECTORS = {
    'market_orders': {
        'name': '市场订单（吉他）',
        'desc': '全量分页拉取吉他星域买卖单',
        'script': 'jita_market_orders_collector_async.py',
    },
    'market_history': {
        'name': '市场历史',
        'desc': '物品交易历史与活跃物品类型',
        'script': 'jita_market_history_collector_async.py',
    },
    'items_sde': {
        'name': '静态数据（SDE 导入）',
        'desc': '从官方静态数据导出 SDE 一次性导入物品信息、属性/效果、市场分组与星系/星域/星座',
        'script': 'item_sde_collector.py',
    },
    # 以下为一次性/手动维护脚本：原需在命令行手动运行，现纳入控制台。
    # path 为相对项目根目录的路径（缺省时 script 相对 collectors/ 解析）。
    'analysis_arbitrage': {
        'name': '交易分析',
        'desc': '基于市场订单与历史数据计算套利机会，生成分析页数据',
        'script': 'analyze_arbitrage_opportunities_optimized.py',
        'path': 'scripts/analyze_arbitrage_opportunities_optimized.py',
    },
    'history_monthly': {
        'name': '月度数据压缩',
        'desc': '将一个月前的市场历史聚合为月度数据并压缩数据库',
        'script': 'aggregate_monthly_history.py',
        'path': 'scripts/cache_management/aggregate_monthly_history.py',
    },
}


def _script_rel_path(cfg):
    """采集器脚本相对项目根目录的路径（path 优先，否则落在 collectors/ 下）。"""
    return cfg.get('path') or os.path.join('collectors', cfg['script'])


# 数据时效：(显示名, 数据库文件, 表名, 时间戳列或 None)
DATA_FRESHNESS = [
    ('市场订单', 'eve_market_orders.db', 'market_orders', 'updated_at'),
    ('市场历史', 'eve_market_history.db', 'market_history', None),
    ('物品数据与市场分组', 'eve_items.db', 'items', None),
    ('星系 / 星域 / 星座', 'eve_universe.db', 'systems', 'updated_at'),
]

_collector_procs = {}
_collector_meta = {}
_collector_lock = threading.Lock()


def _collector_log_path(key):
    return os.path.join(COLLECTOR_LOG_DIR, f'{key}.log')


def _parse_progress(text):
    """从日志文本中粗略解析进度百分比。"""
    import re
    matches = re.findall(r'(\d{1,3})%', text)
    if matches:
        try:
            return max(0, min(100, int(matches[-1])))
        except ValueError:
            pass
    return None


def _decode_log(raw):
    """解码采集器日志字节流。

    新启动的采集器通过 PYTHONIOENCODING=utf-8 强制输出 UTF-8；
    但历史日志或手动运行时在中文 Windows 上为 GBK 编码，需要兼容。
    先按 UTF-8 宽松解码，若替换符极少（仅分块边界截断多字节字符）则视为 UTF-8，
    否则回退到系统本地编码。
    """
    if not raw:
        return ''
    text = raw.decode('utf-8', errors='replace')
    if text.count('\ufffd') <= max(1, len(text) // 200):
        return text
    for enc in ('gbk', 'utf-8'):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return text


def _read_log_tail(path, max_bytes=4000):
    try:
        size = os.path.getsize(path)
        with open(path, 'rb') as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
            return _decode_log(f.read())
    except OSError:
        return ''


def _collector_snapshot(key):
    cfg = COLLECTORS[key]
    with _collector_lock:
        proc = _collector_procs.get(key)
        meta = _collector_meta.get(key, {})
    running = proc is not None and proc.poll() is None
    started_at = meta.get('started_at')
    if running and started_at:
        elapsed = int(time.time() - started_at)
    else:
        elapsed = int(meta.get('elapsed', 0))
    tail = _read_log_tail(_collector_log_path(key))
    last_line = tail.strip().splitlines()[-1] if tail.strip() else ''
    return {
        'key': key,
        'name': cfg['name'],
        'desc': cfg['desc'],
        'script': _script_rel_path(cfg),
        'running': running,
        'pid': proc.pid if running else None,
        'started_at': started_at if running else None,
        'elapsed': elapsed,
        'exit_code': None if running else (proc.poll() if proc is not None else None),
        'progress': _parse_progress(tail) if running else None,
        'last_line': last_line[:200],
    }


@bp.route('/api/collectors')
def api_collectors():
    return jsonify([_collector_snapshot(k) for k in COLLECTORS])


@bp.route('/api/collectors/<key>/start', methods=['POST'])
def api_collector_start(key):
    if key not in COLLECTORS:
        return jsonify({'success': False, 'error': '未知的采集器'}), 404
    with _collector_lock:
        proc = _collector_procs.get(key)
        if proc is not None and proc.poll() is None:
            return jsonify({'success': False, 'error': '该采集器已在运行'}), 409
        script = os.path.join(PROJECT_ROOT, _script_rel_path(COLLECTORS[key]))
        if not os.path.exists(script):
            return jsonify({'success': False, 'error': f'找不到脚本: {_script_rel_path(COLLECTORS[key])}'}), 400
        os.makedirs(COLLECTOR_LOG_DIR, exist_ok=True)
        log_file = open(_collector_log_path(key), 'w', encoding='utf-8', errors='ignore')
        # 强制子进程以 UTF-8 输出，避免中文 Windows 下按 GBK 写入导致日志乱码
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
        try:
            proc = subprocess.Popen(
                [sys.executable, '-u', script],
                cwd=PROJECT_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env,
            )
        except Exception as e:
            log_file.close()
            return jsonify({'success': False, 'error': f'启动失败: {e}'}), 500
        _collector_procs[key] = proc
        _collector_meta[key] = {'started_at': time.time(), 'log_file': log_file, 'elapsed': 0}
    return jsonify({'success': True, 'pid': proc.pid})


@bp.route('/api/collectors/<key>/stop', methods=['POST'])
def api_collector_stop(key):
    if key not in COLLECTORS:
        return jsonify({'success': False, 'error': '未知的采集器'}), 404
    with _collector_lock:
        proc = _collector_procs.get(key)
        if proc is None or proc.poll() is not None:
            return jsonify({'success': False, 'error': '该采集器未在运行'}), 409
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        meta = _collector_meta.get(key, {})
        meta['elapsed'] = int(time.time() - meta.get('started_at', time.time()))
        log_file = meta.get('log_file')
        if log_file:
            try:
                log_file.close()
            except Exception:
                pass
        meta['log_file'] = None
        _collector_meta[key] = meta
    return jsonify({'success': True})


@bp.route('/api/collectors/<key>/log')
def api_collector_log(key):
    if key not in COLLECTORS:
        return jsonify({'success': False, 'error': '未知的采集器'}), 404
    path = _collector_log_path(key)
    try:
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    try:
        size = os.path.getsize(path)
    except OSError:
        return jsonify({'success': True, 'content': '', 'offset': 0, 'size': 0})
    if offset > size:
        offset = 0
    with open(path, 'rb') as f:
        f.seek(offset)
        raw = f.read(200000)
    return jsonify({
        'success': True,
        'content': _decode_log(raw),
        'offset': offset + len(raw),
        'size': size,
    })


@bp.route('/api/data-freshness')
def api_data_freshness():
    result = []
    for label, db_name, table, ts_col in DATA_FRESHNESS:
        db_path = os.path.join(paths.DATA_DIR, db_name)
        item = {'label': label, 'table': table, 'rows': None,
                'last_update': None, 'age_seconds': None,
                'db_exists': os.path.exists(db_path)}
        if not item['db_exists']:
            result.append(item)
            continue
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(f'SELECT COUNT(*) FROM {table}')
            item['rows'] = cur.fetchone()[0]
            if ts_col and item['rows']:
                cur.execute(
                    f"SELECT MAX({ts_col}), "
                    f"strftime('%s','now') - strftime('%s', MAX({ts_col})) FROM {table}"
                )
                row = cur.fetchone()
                if row and row[0]:
                    item['last_update'] = row[0]
                    item['age_seconds'] = int(row[1]) if row[1] is not None else None
            conn.close()
        except Exception as e:
            item['error'] = str(e)
            result.append(item)
            continue
        if item['age_seconds'] is None and item['rows']:
            mtime = os.path.getmtime(db_path)
            item['age_seconds'] = int(time.time() - mtime)
            item['last_update'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
        result.append(item)
    return jsonify(result)


# ---------- 订单追踪开关 ----------
def _read_config():
    """读取项目根目录 config.json（不存在或非法时返回空 dict）。"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _tracker_config():
    """归一化后的订单追踪配置，缺失字段用默认值补齐。"""
    cfg = dict(TRACKER_DEFAULTS)
    section = _read_config().get('market_orders_tracker')
    if isinstance(section, dict):
        cfg['enabled'] = bool(section.get('enabled', False))
        for key in ('interval_minutes', 'retention_hours'):
            try:
                cfg[key] = max(1, int(section.get(key, cfg[key])))
            except (TypeError, ValueError):
                pass
    return cfg


@bp.route('/api/market-orders-tracker')
def api_tracker_get():
    return jsonify(_tracker_config())


@bp.route('/api/market-orders-tracker', methods=['POST'])
def api_tracker_set():
    """更新订单追踪开关与参数，写回 config.json（采集器运行时热读取生效）。"""
    body = request.get_json(silent=True) or {}
    data = _read_config()
    section = data.get('market_orders_tracker')
    if not isinstance(section, dict):
        section = {}
    if 'enabled' in body:
        section['enabled'] = bool(body.get('enabled'))
    for key in ('interval_minutes', 'retention_hours'):
        if key in body:
            try:
                section[key] = max(1, int(body[key]))
            except (TypeError, ValueError):
                return jsonify({'success': False, 'error': f'{key} 需为正整数'}), 400
    data['market_orders_tracker'] = section
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return jsonify({'success': False, 'error': f'写入配置失败: {e}'}), 500
    return jsonify({'success': True, 'config': _tracker_config()})