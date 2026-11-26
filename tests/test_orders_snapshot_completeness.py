# test_orders_snapshot_completeness.py
# 订单采集器「快照完整性」保护机制的离线回归测试。
#
# 不联网、不碰 data/ 下的真实数据库：全部在 sqlite 内存库中、用桩函数替换 ESI 分页请求。
# 覆盖：
#   1. 缺页不再被静默跳过（三次重拉仍缺 -> IncompleteSnapshotError，拒绝写库）
#   2. 缺页后重拉成功 -> 返回完整快照
#   3. 首页自称多页但只返回少量数据（响应被截断）-> 判定不完整
#   4. 全量覆盖的规模下限校验（残缺快照不会清空整区）
#   5. 追踪模式的规模下限校验（不会把缺页误记成 delete 事件）
#   6. 连续 20 页失败时提前中止本轮（不把 400+ 请求全部打完）
#
# 运行：.venv\Scripts\python.exe tests\test_orders_snapshot_completeness.py
import asyncio
import logging
import os
import sqlite3
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'collectors')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import jita_market_orders_collector_async as m

# 模块导入时 logging.basicConfig 已把根日志设为 INFO，这里静音本模块的预期告警
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


def make_orders(page, count=1000):
    """构造某一页的订单（order_id 按页段生成，便于断言缺失）。"""
    return [{
        'order_id': page * 10000 + i,
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
    """桩分页：按 attempt 注入失败页 / 空页 / 首页截断。"""

    def __init__(self, total_pages=TOTAL_PAGES):
        self.total_pages = total_pages
        self.attempt = 0
        self.fail_on_attempt = {}   # {attempt_no: {pages}} -> ok=False
        self.empty_on_attempt = {}  # {attempt_no: {pages}} -> ok=True 但无数据
        self.truncate_first = False
        self.no_total_pages = False
        self.fail_all_pages = False
        self.duplicate_pages = False
        self.calls = 0

    async def page(self, session, page, order_type="all", abort_event=None):
        if abort_event is not None and abort_event.is_set():
            return [], 0, None, False
        if page == 1:
            self.attempt += 1
            count = 10 if self.truncate_first else 1000
            total = 0 if self.no_total_pages else self.total_pages
            return make_orders(1, count), total, 'LM-A', True
        self.calls += 1
        if self.fail_all_pages:
            return [], 0, None, False
        if self.duplicate_pages:
            # 每页都返回首页那批 order_id：模拟跨代混页导致的重复
            return make_orders(1), self.total_pages, 'LM-A', True
        if page in self.fail_on_attempt.get(self.attempt, set()):
            return [], 0, None, False
        if page in self.empty_on_attempt.get(self.attempt, set()):
            return [], self.total_pages, 'LM-A', True
        return make_orders(page), self.total_pages, 'LM-A', True


def new_db():
    conn = sqlite3.connect(':memory:')
    conn.execute(ORDERS_DDL)
    return conn


def count(conn, table='market_orders'):
    return conn.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]


def check(label, cond):
    print(('  PASS  ' if cond else '  FAIL  ') + label)
    return bool(cond)


async def main():
    ok = True

    print('[1] 第 3 页请求失败：三次重拉仍缺页，必须抛 IncompleteSnapshotError')
    fake = FakeMarket()
    fake.fail_on_attempt = {1: {3}, 2: {3}, 3: {3}}
    m.get_market_orders_page = fake.page
    raised = False
    try:
        await m.get_all_market_orders(None, 'all')
    except m.IncompleteSnapshotError as exc:
        raised = True
        msg = str(exc)
    ok &= check('抛出 IncompleteSnapshotError', raised)
    ok &= check('尝试次数 = 3', fake.attempt == 3)
    if raised:
        print('        原因：' + msg[:100])

    print('[2] 首次缺页、第二次完整：应重拉并返回全部 5000 单')
    fake = FakeMarket()
    fake.fail_on_attempt = {1: {2, 4}}
    m.get_market_orders_page = fake.page
    orders = await m.get_all_market_orders(None, 'all')
    ok &= check('返回 5000 单', len(orders) == 5000)
    ok &= check('确实重拉了一次（attempt=2）', fake.attempt == 2)

    print('[3] 成功但空页（ok=True, 0 条）同样视为缺页')
    fake = FakeMarket()
    fake.empty_on_attempt = {1: {5}, 2: {5}, 3: {5}}
    m.get_market_orders_page = fake.page
    raised = False
    try:
        await m.get_all_market_orders(None, 'all')
    except m.IncompleteSnapshotError:
        raised = True
    ok &= check('抛出 IncompleteSnapshotError', raised)

    print('[4] 首页自称 5 页却只返回 10 条（响应截断）视为不完整')
    fake = FakeMarket()
    fake.truncate_first = True
    m.get_market_orders_page = fake.page
    raised = False
    try:
        await m.get_all_market_orders(None, 'all')
    except m.IncompleteSnapshotError:
        raised = True
    ok &= check('抛出 IncompleteSnapshotError', raised)

    print('[5] 完整性判定函数')
    ok &= check('bad_pages 非空 -> 不可用', bool(m._snapshot_problem([], [3], 5)))
    ok &= check('数量低于分页下限 -> 不可用',
                bool(m._snapshot_problem([{'order_id': i} for i in range(3000)], [], 5)))
    ok &= check('重复 order_id -> 不可用',
                bool(m._snapshot_problem([{'order_id': 1}] * 2, [], 1)))
    ok &= check('完整 -> 可用',
                m._snapshot_problem([{'order_id': i} for i in range(4000)], [], 5) == '')

    print('[5b] 首页满页但缺少 X-Pages 头：无法判断总页数，视为不完整')
    fake = FakeMarket()
    fake.no_total_pages = True
    m.get_market_orders_page = fake.page
    raised = False
    try:
        await m.get_all_market_orders(None, 'all')
    except m.IncompleteSnapshotError:
        raised = True
    ok &= check('抛出 IncompleteSnapshotError', raised)

    print('[6] 全量覆盖：残缺快照（4000 / 库内 5000）必须被拒绝，且库内数据不变')
    conn = new_db()
    conn.executemany(INSERT_SQL, db_rows([o for p in range(1, 6) for o in make_orders(p)]))
    conn.commit()
    m.db_conn = conn
    wrote = await m.process_orders_to_database([o for p in (1, 2, 4, 5) for o in make_orders(p)])
    ok &= check('返回 False', wrote is False)
    ok &= check('库内仍为 5000 单', count(conn) == 5000)

    print('[7] 全量覆盖：规模正常（4950 / 库内 5000）应允许覆盖')
    wrote = await m.process_orders_to_database([o for p in range(1, 6) for o in make_orders(p)][:4950])
    ok &= check('返回 True', wrote is True)
    ok &= check('库内变为 4950 单', count(conn) == 4950)

    print('[8] 追踪模式：残缺快照不得伪造 delete 事件')
    conn = new_db()
    conn.executemany(INSERT_SQL, db_rows([o for p in range(1, 6) for o in make_orders(p)]))
    conn.commit()
    m.db_conn = conn
    await m.init_tracking_schema()
    wrote = await m.process_orders_tracking([o for p in (1, 2, 4, 5) for o in make_orders(p)], 1000, 72)
    ok &= check('返回 False', wrote is False)
    ok &= check('事件表为 0 条', count(conn, 'market_order_events') == 0)
    ok &= check('库内仍为 5000 单', count(conn) == 5000)

    print('[9] 追踪模式：完整快照正常写入，事件数等于真实变化')
    wrote = await m.process_orders_tracking(
        [o for p in (1, 2, 3, 4, 5) for o in make_orders(p)][:-5] + [], 2000, 72)
    ok &= check('返回 True', wrote is True)
    ok &= check('记录 5 条 delete 事件', count(conn, 'market_order_events') == 5)
    ok &= check('库内变为 4995 单', count(conn) == 4995)

    print('[10] 连续 20 页失败：立即中止本轮，不整体重拉、不打完剩余页')
    fake = FakeMarket(total_pages=30)
    fake.fail_all_pages = True
    m.get_market_orders_page = fake.page
    raised = False
    msg = ''
    try:
        await m.get_all_market_orders(None, 'all')
    except m.IncompleteSnapshotError as exc:
        raised = True
        msg = str(exc)
    ok &= check('抛出 IncompleteSnapshotError', raised)
    ok &= check('未整体重拉（attempt=1）', fake.attempt == 1)
    ok &= check(f'剩余页未发起请求（实际 {fake.calls}/29 页）', fake.calls < 29)
    ok &= check('错误信息点明限流风险', '错误限流' in msg)

    print('[11] 中止信号穿透到单页重试：不再发起请求（session 传 None 也不会被触碰）')
    ev = asyncio.Event()
    ev.set()
    res = await m.get_market_orders_page(None, 7, 'all', ev)
    ok &= check('直接返回空页失败', res == ([], 0, None, False))

    print('[12] 跨代混页导致 order_id 重复：快照作废并重拉，不写库')
    fake = FakeMarket()
    fake.duplicate_pages = True
    m.get_market_orders_page = fake.page
    raised = False
    msg = ''
    try:
        await m.get_all_market_orders(None, 'all')
    except m.IncompleteSnapshotError as exc:
        raised = True
        msg = str(exc)
    ok &= check('抛出 IncompleteSnapshotError', raised)
    ok &= check('确实重拉过（attempt=3）', fake.attempt == 3)
    ok &= check('错误信息点明重复 order_id', '重复 order_id' in msg)

    print('[13] 写库入口兜底：重复 order_id 一律拒绝写入，不产生任何事件')
    conn = new_db()
    base = [o for p in range(1, 6) for o in make_orders(p)]
    conn.executemany(INSERT_SQL, db_rows(base))
    conn.commit()
    m.db_conn = conn
    await m.init_tracking_schema()
    dirty = base + [base[0]]   # 多一条重复 order_id
    wrote_tracking = await m.process_orders_tracking(dirty, 3000, 72)
    ok &= check('追踪模式返回 False', wrote_tracking is False)
    ok &= check('事件表仍为 0 条', count(conn, 'market_order_events') == 0)
    ok &= check('库内仍为 5000 单', count(conn) == 5000)
    wrote_full = await m.process_orders_to_database(dirty)
    ok &= check('全量模式返回 False', wrote_full is False)
    ok &= check('全量库内仍为 5000 单', count(conn) == 5000)

    print()
    print('结果：' + ('全部通过' if ok else '存在失败项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
