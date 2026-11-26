# test_streaming_snapshot.py
# 订单采集「逐页落盘」路径的离线回归测试。
#
# 不联网、不碰 data/ 下的真实数据库：全部在 sqlite 内存库中、用桩函数替换 ESI 分页。
# 覆盖：
#   1. 逐页落盘把每页写入暂存表，不再聚合成内存 list
#   2. 缺页导致快照作废时，暂存表被清空（不会残留半成品）
#   3. 跨代混页产生重复 order_id -> 由 staging 主键冲突检出并作废
#   4. run_tracking_once 完整快照 -> 返回 0，事件数等于真实变化
#   5. run_tracking_once 规模骤降 -> 返回 4，主表与暂存表都不被污染
#   6. main() 全量覆盖同样走暂存表，内存不再持有全量订单
#   7. 增量同步只写差异行：删消失 / 插新增 / 改变更，未变化行不重写
#   8. 跨代混页：某页 last-modified 与首页不一致 -> 整体作废并重拉
#
# 运行：.venv\Scripts\python.exe tests\test_streaming_snapshot.py
import asyncio
import logging
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'collectors')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import jita_market_orders_collector_async as m

logging.getLogger('jita_market_orders_collector_async').setLevel(logging.CRITICAL)

m.tqdm = None
m.MAX_CONCURRENT_REQUESTS = 10

REGION = m.JITA_REGION_ID
TOTAL_PAGES = 5

ORDERS_DDL = '''
    CREATE TABLE market_orders (
        order_id INTEGER PRIMARY KEY,
        region_id INTEGER NOT NULL,
        type_id INTEGER NOT NULL,
        order_type TEXT NOT NULL,
        price REAL NOT NULL,
        volume_remain INTEGER NOT NULL,
        volume_total INTEGER NOT NULL,
        min_volume INTEGER NOT NULL,
        is_buy_order INTEGER NOT NULL,
        duration INTEGER NOT NULL,
        range INTEGER NOT NULL,
        issued TIMESTAMP NOT NULL,
        system_id INTEGER NOT NULL,
        location_id INTEGER NOT NULL,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
'''

INSERT_SQL = '''
    INSERT INTO market_orders
    (order_id, region_id, type_id, order_type, price, volume_remain, volume_total,
     min_volume, is_buy_order, duration, range, issued, system_id, location_id)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
'''


def make_orders(page, count=1000, start=0):
    """构造某一页的订单（order_id 按页段生成，便于断言缺失）。"""
    return [{
        'order_id': page * 10000 + start + i,
        'type_id': 34,
        'price': 5.0,
        'volume_remain': 10,
        'volume_total': 10,
        'min_volume': 1,
        'is_buy_order': False,
        'duration': 90,
        'range': 'station',
        'issued': '2026-11-26T00:00:00Z',
        'system_id': 30000142,
        'location_id': 60003760,
    } for i in range(count)]


def db_rows(orders):
    return [(o['order_id'], REGION, o['type_id'], 'sell', o['price'], o['volume_remain'],
             o['volume_total'], o['min_volume'], 0, o['duration'], o['issued'],
             o['system_id'], o['location_id']) for o in orders]


class FakeMarket:
    """桩分页：按 attempt 注入失败页 / 重复页 / 跨代页。"""

    def __init__(self, total_pages=TOTAL_PAGES):
        self.total_pages = total_pages
        self.attempt = 0
        self.fail_on_attempt = {}
        self.duplicate_pages = False
        self.trim_last_page = 0  # 最后一页少返回 N 条
        self.stale_from_page = None  # 从该页起返回不同的 last-modified（模拟跨代刷新）

    def lm(self, page):
        if self.stale_from_page and page >= self.stale_from_page:
            return 'LM-B'
        return 'LM-A'

    async def page(self, session, page, order_type="all", abort_event=None):
        if abort_event is not None and abort_event.is_set():
            return [], 0, None, False
        if page == 1:
            self.attempt += 1
            return make_orders(1), self.total_pages, self.lm(page), True
        if self.duplicate_pages:
            return make_orders(1), self.total_pages, self.lm(page), True
        if page in self.fail_on_attempt.get(self.attempt, set()):
            return [], 0, None, False
        if page == self.total_pages and self.trim_last_page:
            return (make_orders(page, 1000 - self.trim_last_page),
                    self.total_pages, self.lm(page), True)
        return make_orders(page), self.total_pages, self.lm(page), True


class FakeSession:
    """记录构造参数，用于断言会话确实带上了超时设置。"""

    last_kwargs = {}

    def __init__(self, **kwargs):
        FakeSession.last_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class FakeAiohttp:
    ClientSession = FakeSession


async def _noop_init():
    pass


def new_db(preload_pages=0):
    conn = sqlite3.connect(':memory:')
    conn.execute(ORDERS_DDL)
    if preload_pages:
        rows = []
        for p in range(1, preload_pages + 1):
            rows.extend(db_rows(make_orders(p)))
        conn.executemany(INSERT_SQL, rows)
    conn.commit()
    return conn


def count(conn, table='market_orders'):
    return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


def check(label, cond):
    print(('  PASS  ' if cond else '  FAIL  ') + label)
    return bool(cond)


async def main():
    ok = True

    m.aiohttp = FakeAiohttp
    m.init_database = _noop_init

    # ---------------------------------------------------------------- 1
    print('[1] 逐页落盘：5 页全部写入暂存表，内存里不保留订单')
    fake = FakeMarket()
    m.get_market_orders_page = fake.page
    conn = new_db()
    m.db_conn = conn
    await m.init_tracking_schema()

    buffer = m.StagingBuffer(conn)
    got = await m.get_all_market_orders_streaming(None, buffer, 'all')
    ok &= check('返回实际写入行数 5000', got == 5000)
    ok &= check('暂存表 5000 行', count(conn, 'market_orders_staging') == 5000)
    ok &= check('主表仍为空（尚未 diff）', count(conn) == 0)
    ok &= check('buffer.received == 5000', buffer.received == 5000)

    # ---------------------------------------------------------------- 2
    print('[2] 缺页：三次重拉仍缺 -> 抛异常且暂存表被清空')
    fake = FakeMarket()
    fake.fail_on_attempt = {1: {3}, 2: {3}, 3: {3}}
    m.get_market_orders_page = fake.page
    conn = new_db()
    m.db_conn = conn
    await m.init_tracking_schema()

    buffer = m.StagingBuffer(conn)
    raised = False
    try:
        await m.get_all_market_orders_streaming(None, buffer, 'all')
    except m.IncompleteSnapshotError:
        raised = True
    ok &= check('抛出 IncompleteSnapshotError', raised)
    ok &= check('暂存表已清空', count(conn, 'market_orders_staging') == 0)
    ok &= check('主表未受影响', count(conn) == 0)

    # ---------------------------------------------------------------- 3
    print('[3] 跨代混页：重复 order_id 由暂存表主键检出并作废')
    fake = FakeMarket()
    fake.duplicate_pages = True
    m.get_market_orders_page = fake.page
    conn = new_db()
    m.db_conn = conn
    await m.init_tracking_schema()

    buffer = m.StagingBuffer(conn)
    raised = False
    msg = ''
    try:
        await m.get_all_market_orders_streaming(None, buffer, 'all')
    except m.IncompleteSnapshotError as exc:
        raised = True
        msg = str(exc)
    ok &= check('抛出 IncompleteSnapshotError', raised)
    ok &= check('错误信息点明重复 order_id', '重复 order_id' in msg)
    ok &= check('暂存表已清空', count(conn, 'market_orders_staging') == 0)

    # ---------------------------------------------------------------- 4
    print('[4] run_tracking_once：完整快照写入，事件数等于真实变化')
    fake = FakeMarket()
    m.get_market_orders_page = fake.page
    conn = new_db(preload_pages=5)
    # 库内删掉 5 单，快照里仍存在 -> 应记 5 条 insert
    conn.execute('DELETE FROM market_orders WHERE order_id BETWEEN 10000 AND 10004')
    conn.commit()
    m.db_conn = conn

    code = await m.run_tracking_once(retention_hours=24)
    ok &= check('返回 0', code == 0)
    ok &= check('主表恢复为 5000 单', count(conn) == 5000)
    ok &= check('记录 5 条 insert 事件',
                conn.execute("SELECT COUNT(*) FROM market_order_events "
                             "WHERE event_type='insert'").fetchone()[0] == 5)
    ok &= check('快照元数据已写入',
                count(conn, 'market_order_snapshots') == 1)
    ok &= check('订单会话带上了 60s 总超时',
                FakeSession.last_kwargs.get('timeout') is m.CLIENT_TIMEOUT)
    ok &= check('超时预算为 60s / 连接 10s / 读 30s',
                (m.CLIENT_TIMEOUT.total, m.CLIENT_TIMEOUT.sock_connect,
                 m.CLIENT_TIMEOUT.sock_read) == (60, 10, 30))

    # ---------------------------------------------------------------- 5
    print('[5] run_tracking_once：快照规模骤降 -> 拒绝写入，主表保持')
    fake = FakeMarket()
    m.get_market_orders_page = fake.page
    conn = new_db(preload_pages=5)
    # 额外塞 2000 单，使基线 7000，而快照只有 5000（< 7000×0.9=6300）
    extra = [dict(o, order_id=o['order_id'] + 500000) for p in (1, 2) for o in make_orders(p)]
    conn.executemany(INSERT_SQL, db_rows(extra))
    conn.commit()
    before = count(conn)
    m.db_conn = conn

    code = await m.run_tracking_once(retention_hours=24)
    ok &= check('返回 4（被规模校验拒绝）', code == 4)
    ok &= check('主表行数不变', count(conn) == before)
    ok &= check('未产生任何事件', count(conn, 'market_order_events') == 0)
    ok &= check('暂存表已清空', count(conn, 'market_orders_staging') == 0)

    # ---------------------------------------------------------------- 6
    print('[6] main()：全量覆盖走暂存表，主表被整体替换')
    # main() 结束时会把连接关掉，内存库随之消失，所以这里用临时文件库
    import tempfile
    db_path = os.path.join(tempfile.gettempdir(), 'eve_stream_main_test.db')
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass

    fake = FakeMarket()
    m.get_market_orders_page = fake.page
    conn = sqlite3.connect(db_path)
    conn.execute(ORDERS_DDL)
    preload = [o for p in range(1, 4) for o in make_orders(p)]   # 库内 3000
    conn.executemany(INSERT_SQL, db_rows(preload))
    conn.commit()
    m.db_conn = conn
    m.error_count = 0

    await m.main()

    check_conn = sqlite3.connect(db_path)
    ok &= check('主表变为 5000 单', count(check_conn) == 5000)
    ok &= check('旧的第 3 页数据被新快照覆盖',
                check_conn.execute('SELECT COUNT(*) FROM market_orders '
                                   'WHERE order_id BETWEEN 30000 AND 39999').fetchone()[0] == 1000)
    check_conn.close()
    for suffix in ('', '-wal', '-shm'):
        try:
            os.remove(db_path + suffix)
        except OSError:
            pass

    # ---------------------------------------------------------------- 7
    print('[7] 增量同步：只写差异行，未变化的订单保留原 updated_at')
    conn = new_db(preload_pages=5)
    m.db_conn = conn
    conn.execute("UPDATE market_orders SET updated_at = '2020-01-01 00:00:00'")
    conn.commit()
    await m.init_tracking_schema()

    staged = [o for p in range(1, 6) for o in make_orders(p)]
    dropped = staged[-5:]          # 从快照里消失的 5 单
    staged = staged[:-5]
    for o in staged[:10]:          # 10 单改价
        o['price'] = 9.5
    conn.executemany(
        'INSERT INTO market_orders_staging (order_id, type_id, order_type, price, '
        'volume_remain, volume_total, min_volume, is_buy_order, duration, range, '
        'issued, system_id, location_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
        [(o['order_id'], o['type_id'], 'sell', o['price'], o['volume_remain'],
          o['volume_total'], o['min_volume'], 0, o['duration'], 0, o['issued'],
          o['system_id'], o['location_id']) for o in staged])
    conn.commit()

    deleted, inserted, updated = m._sync_orders_from_staging()
    conn.commit()
    ok &= check(f'删除 5 单、新增 0、更新 10 单（实际 {deleted}/{inserted}/{updated}）',
                (deleted, inserted, updated) == (5, 0, 10))
    ok &= check('主表 5000 - 5 = 4995 单', count(conn) == 4995)
    untouched = conn.execute(
        "SELECT COUNT(*) FROM market_orders WHERE updated_at = '2020-01-01 00:00:00'"
    ).fetchone()[0]
    ok &= check(f'未变化的 4985 行 updated_at 未被重写（实际 {untouched}）', untouched == 4985)
    ok &= check('消失的 5 单确实不在主表',
                all(conn.execute('SELECT COUNT(*) FROM market_orders WHERE order_id = ?',
                                 (o['order_id'],)).fetchone()[0] == 0 for o in dropped))
    ok &= check('改价已生效',
                conn.execute('SELECT COUNT(*) FROM market_orders WHERE price = 9.5'
                             ).fetchone()[0] == 10)

    # ---------------------------------------------------------------- 8
    print('[8] 跨代混页：部分页 last-modified 与首页不一致 -> 快照作废')
    fake = FakeMarket()
    fake.stale_from_page = 4        # 第 4 页起属于新的一代
    m.get_market_orders_page = fake.page
    conn = new_db()
    m.db_conn = conn
    await m.init_tracking_schema()

    buffer = m.StagingBuffer(conn)
    raised = False
    try:
        await m.get_all_market_orders_streaming(None, buffer, 'all')
    except m.IncompleteSnapshotError:
        raised = True
    ok &= check('抛出 IncompleteSnapshotError', raised)
    ok &= check('跨代快照的暂存行已被清空', count(conn, 'market_orders_staging') == 0)
    ok &= check('主表未受影响', count(conn) == 0)
    ok &= check(f'触发了 {fake.attempt} 次整体重拉（应为 3）', fake.attempt == 3)

    print()
    print('结果：' + ('全部通过' if ok else '存在失败项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
