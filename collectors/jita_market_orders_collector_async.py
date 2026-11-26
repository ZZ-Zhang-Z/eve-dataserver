# jita_market_orders_collector_async.py
# 异步获取吉他市场订单数据并保存到数据库的脚本
import asyncio
import aiohttp
import json
import logging
import time
import sys
import os

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))  # 自包含副本：置顶以优先于项目根的同名模块

import paths
from database_manager import get_connection_by_table

# 公共模块：统一请求头、按状态码计费的令牌桶、退避、错误率、分页一致性校验
from esi_client import (
    default_headers,
    TokenBucket,
    error_rate_tracker,
    rate_limit_monitor,
    compute_backoff,
    check_pagination_consistency,
)

# 尝试导入tqdm库，用于显示进度条
try:
    from tqdm import tqdm
except ImportError:
    logger.warning("tqdm库未安装，将不显示进度条")
    tqdm = None

# API配置
BASE_URL = "https://esi.evetech.net"
HEADERS = default_headers()

# 配置参数
MAX_RETRIES = 3  # API请求的最大重试次数
REQUESTS_PER_MINUTE = 800  # 每分钟最大请求数（基于每15分钟12000个令牌）
JITA_REGION_ID = 10000002  # 吉他市场区域ID
MAX_CONCURRENT_REQUESTS = 20  # 最大并发请求数
MAX_SNAPSHOT_ATTEMPTS = 3  # 检测到跨代/缺页时整体重拉的最大尝试次数
MAX_PAGE_SIZE = 1000  # ESI 分页上限（每页最多 1000 条），用于快照完整性下限校验
MIN_SNAPSHOT_RATIO = 0.9  # 新快照订单数不得低于库内现有行数的该比例，否则拒绝覆盖
MAX_CONSECUTIVE_FAILURES = 20  # 连续失败页达到该值即中止本轮，避免触发 ESI 错误限流（100 errors/60s）
MAX_CYCLE_ERRORS = 5  # 追踪模式连续多少轮异常后停止循环（单轮异常只跳过该轮）

# 错误计数
error_count = 0


class IncompleteSnapshotError(RuntimeError):
    """连续多次拉取仍无法得到完整快照。

    调用方必须放弃本轮写库（保留上一份完整数据），不得把残缺快照写入数据库。
    """

# 令牌桶实例：每15分钟12000个令牌（约800请求/分钟），按状态码计费
RATE_LIMIT_TOKENS = 12000  # 桶容量（每15分钟令牌数）
RATE_LIMIT_PERIOD = 15 * 60  # 15分钟（秒）
rate_limiter = TokenBucket(RATE_LIMIT_TOKENS, RATE_LIMIT_PERIOD)

# 全局数据库连接
db_conn = None

# 追踪模式开关（读取项目根目录 config.json 的 market_orders_tracker 段）
#   关闭：启动采集器只做一次全量快照，行为与改动前完全一致（走原有 main()）
#   开启：采集器每 interval_minutes 分钟重复采集一次，并记录订单变更事件
TRACKER_CONFIG_PATH = os.path.join(paths.BASE_DIR, 'config.json')
TRACKER_DEFAULTS = {'enabled': False, 'interval_minutes': 30, 'retention_hours': 72}

async def init_database():
    """
    初始化数据库，确保表结构存在
    """
    global db_conn
    db_conn = get_connection_by_table('market_orders')
    cursor = db_conn.cursor()
    
    # 创建market_orders表（如果不存在）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_orders (
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
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_orders_region_id ON market_orders (region_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_orders_type_id ON market_orders (type_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_orders_order_type ON market_orders (order_type)')
    
    db_conn.commit()
    logger.info("market_orders表结构初始化成功")

async def get_market_orders_page(session, page, order_type="all", abort_event=None):
    """
    获取吉他市场某一页的订单数据
    返回: (订单数据列表, 总页数, last-modified, ok)

    ok 用于区分"请求成功但该页无数据"与"请求失败"：
    - ok=True  请求成功（200）；orders 可能为空
    - ok=False 该页失败（404 / 4xx / 5xx / 网络异常重试耗尽），
      调用方必须把它当作缺页处理，绝不能静默跳过，否则会得到一份
      "少了一页却看似完整"的快照。

    abort_event：本轮已判定中止时置位；此后不再发起任何请求（含重试），
    避免系统性故障时把剩余重试也打出去、加剧 ESI 错误限流。
    """
    global error_count
    url = f"{BASE_URL}/markets/{JITA_REGION_ID}/orders?page={page}&order_type={order_type}"
    total_pages = 0
    last_modified = None

    # 指数退避重试逻辑
    for retry in range(MAX_RETRIES + 1):
        if abort_event is not None and abort_event.is_set():
            return [], 0, None, False
        try:
            # 使用令牌桶进行速率限制（先预扣1个令牌）
            await rate_limiter.consume()
            async with session.get(url) as response:
                # 按响应状态码补扣/退还令牌（2xx=2/3xx=1/4xx=5/5xx=0）
                await rate_limiter.settle(response.status)

                if response.status == 200:
                    # 依据 X-Ratelimit-* 动态校正桶容量并主动降速
                    rate_limiter.update_capacity_from_header(response.headers.get('X-Ratelimit-Limit'))
                    extra_delay = rate_limit_monitor.observe(response.headers)
                    if extra_delay:
                        await asyncio.sleep(extra_delay)

                    # 获取总页数
                    try:
                        total_pages = int(response.headers.get('X-Pages', '0'))
                    except (ValueError, TypeError):
                        total_pages = 0

                    # 记录 last-modified 用于分页一致性校验
                    last_modified = response.headers.get('Last-Modified')

                    orders = await response.json()
                    return orders, total_pages, last_modified, True
                elif response.status == 404:
                    # 分页区间内出现 404（通常是采集期间市场收缩）不能当作"已取完"，
                    # 否则整份快照会缺页且无人察觉；标记失败，交由上层整体重拉。
                    logger.warning(f"吉他市场订单第 {page} 页返回 404，本轮快照作废（将整体重拉）")
                    return [], 0, None, False
                elif response.status == 420 or response.status == 429:  # 速率限制错误
                    # 登记错误并获取错误率控制延迟
                    error_rate_tracker.record()
                    _, extra_delay = error_rate_tracker.get_delay()
                    if retry < MAX_RETRIES:
                        if response.status == 420:
                            error_rate_tracker.trim(0.8)
                        wait_time = compute_backoff(
                            retry,
                            status_code=response.status,
                            retry_after=response.headers.get('Retry-After'),
                            extra_delay=extra_delay,
                        )
                        logger.warning(f"获取吉他市场订单时遇到速率限制，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"获取吉他市场订单失败，已达到最大重试次数")
                        error_count += 1
                        return [], 0, None, False
                else:
                    error_rate_tracker.record()
                    _, extra_delay = error_rate_tracker.get_delay()
                    if retry < MAX_RETRIES:
                        wait_time = compute_backoff(
                            retry,
                            status_code=response.status,
                            retry_after=response.headers.get('Retry-After'),
                            extra_delay=extra_delay,
                        )
                        logger.warning(f"获取吉他市场订单失败，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"获取吉他市场订单失败，状态码: {response.status}，已达到最大重试次数")
                        error_count += 1
                        return [], 0, None, False
        except aiohttp.ClientError as e:
            error_rate_tracker.record()
            _, extra_delay = error_rate_tracker.get_delay()
            if retry < MAX_RETRIES:
                wait_time = compute_backoff(retry, extra_delay=extra_delay)
                logger.warning(f"获取吉他市场订单时发生网络异常: {str(e)}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"获取吉他市场订单时发生网络异常: {str(e)}，已达到最大重试次数")
                error_count += 1
                return [], 0, None, False
        except Exception as e:
            logger.error(f"获取吉他市场订单时发生意外异常: {str(e)}")
            error_count += 1
            return [], 0, None, False
    return [], 0, None, False

async def _fetch_full_snapshot(session, order_type="all"):
    """
    执行一次完整的全量分页拉取（只拉取到内存，不写数据库）。

    返回 (orders, bad_pages, total_pages, aborted)：
    - bad_pages 为「请求失败 / 成功但空页 / last-modified 与首页不一致」的页码；
      非空表示该快照不可用，调用方须整体丢弃后重拉。
    - total_pages 为首页 X-Pages 报告的总页数，供订单总数下限校验使用。
    - aborted 为 True 表示因连续失败达到 MAX_CONSECUTIVE_FAILURES 而提前中止；
      此时剩余页根本没有发起请求，调用方不应立即整体重拉（会放大错误风暴）。

    拆分为独立函数是为了在检测到跨代或缺页时能整体丢弃并重拉，且不会污染数据库。
    """
    global error_count

    all_orders = []
    page = 1
    total_pages = 0
    bad_pages = []
    pages = []
    fetched = {}
    state = {'consecutive_failures': 0, 'aborted': False, 'skipped': 0}
    abort_event = asyncio.Event()

    # 使用tqdm显示进度条
    pbar = None
    if tqdm:
        pbar = tqdm(desc=f"获取{order_type}订单")

    try:
        # 先获取第一页以确定总页数
        first_page_orders, page_total, first_last_modified, first_ok = await get_market_orders_page(
            session, page, order_type)
        if not first_ok:
            logger.error("首页（第 1 页）请求失败，本轮快照作废")
            return all_orders, [1], 0, False

        # 首页满页却拿不到 X-Pages：无法判断是否还有后续页，按不完整处理
        if page_total <= 0 and len(first_page_orders) >= MAX_PAGE_SIZE:
            logger.warning(
                "首页返回满页 %d 条但缺少 X-Pages 头，无法判断总页数，本轮快照作废",
                len(first_page_orders))
            return all_orders, [1], 0, False

        # 设置总页数
        total_pages = page_total if page_total > 0 else 1
        if pbar is not None:
            pbar.total = total_pages

        # 添加第一页数据
        all_orders.extend(first_page_orders)
        if pbar is not None:
            pbar.update(1)

        # 单页市场：首页即全部
        if total_pages <= 1:
            return all_orders, bad_pages, total_pages, False

        # 首页自称多页却不足一页，说明响应被截断；若照旧返回，会得到一份
        # "只有一页的完整快照"，随后全量覆盖会把整区订单删掉
        if len(first_page_orders) < MAX_PAGE_SIZE:
            logger.warning(
                "首页自称共 %d 页，但只返回 %d 条（< %d），判定响应被截断，本轮快照作废",
                total_pages, len(first_page_orders), MAX_PAGE_SIZE)
            bad_pages.append(1)
            return all_orders, bad_pages, total_pages, False

        # 并发获取剩余页面。
        # 用「有界工作池 + 中止标志」而不是一次 gather 全部任务：
        # 连续多页失败时剩余页不再派发，避免在系统性故障（4xx/5xx 风暴）下
        # 把 400+ 个请求全部打完，直接冲向 ESI 的错误限流（100 errors / 60s）。
        pages = list(range(2, total_pages + 1))

        async def worker():
            while pages:
                page_num = pages.pop(0)
                if state['aborted']:
                    state['skipped'] += 1
                    continue
                try:
                    result_orders, _, result_last_modified, ok = await get_market_orders_page(
                        session, page_num, order_type, abort_event)
                except Exception as exc:
                    logger.error(f"获取第{page_num}页数据时发生异常: {str(exc)}")
                    error_count += 1
                    result_orders, result_last_modified, ok = None, None, False
                fetched[page_num] = (result_orders, result_last_modified, ok)
                if abort_event.is_set():
                    # 已被其他 worker 判定中止，不再累计/记录（该页数据也不可用）
                    continue
                # 空页同样算失败：分页区间内不该出现空页
                if ok and result_orders:
                    state['consecutive_failures'] = 0
                    if pbar is not None:
                        pbar.update(1)
                else:
                    state['consecutive_failures'] += 1
                    if state['consecutive_failures'] >= MAX_CONSECUTIVE_FAILURES:
                        state['aborted'] = True
                        abort_event.set()
                        logger.error(
                            "连续 %d 页请求失败，立即中止本轮抓取："
                            "继续请求有触发 ESI 错误限流（100 errors/60s）的风险",
                            MAX_CONSECUTIVE_FAILURES)

        await asyncio.gather(*[worker() for _ in range(MAX_CONCURRENT_REQUESTS)])

        # 处理结果（按页号排序，便于日志与缺失页统计）
        for page_num in sorted(fetched):
            result_orders, result_last_modified, ok = fetched[page_num]
            if not ok:
                # 失败页必须计入 bad_pages：静默跳过会得到缺页却看似完整的快照
                logger.warning(f"第 {page_num} 页请求失败，本轮快照作废")
                bad_pages.append(page_num)
                continue
            if not result_orders:
                # 分页区间内不该出现空页，按异常页处理，避免静默漏数据
                logger.warning(f"第 {page_num} 页返回空数据，本轮快照作废")
                bad_pages.append(page_num)
                continue
            # 分页一致性校验：各页 last-modified 应与首页一致，否则可能跨代
            if not check_pagination_consistency(first_last_modified, result_last_modified):
                # 记录不一致页，交由上层整体丢弃本快照并重拉，避免混代
                bad_pages.append(page_num)
                continue
            all_orders.extend(result_orders)

        if state['aborted']:
            logger.error(
                "本轮抓取已中止：已发起 %d 页请求，%d 页未发起（分页共 %d 页）",
                len(fetched), state['skipped'], total_pages)
    finally:
        # 关闭进度条
        if pbar is not None:
            pbar.close()

    return all_orders, bad_pages, total_pages, state['aborted']


def _duplicate_order_ids(orders):
    """统计快照内重复的 order_id 个数（0 表示无重复）。

    正常快照里 order_id 全局唯一；出现重复基本只可能是分页跨代混页
    （同一订单同时出现在两代的两页里）。重复行会让 market_orders_staging
    的主键冲突（IntegrityError），也会让"缺失页"统计失真，因此统一在
    写库前拦掉。
    """
    seen = set()
    dup = 0
    for order in orders:
        oid = order.get('order_id')
        if oid in seen:
            dup += 1
        else:
            seen.add(oid)
    return dup


def _snapshot_problem(orders, bad_pages, total_pages):
    """判断快照是否可用；可用返回空字符串，否则返回具体原因。"""
    if bad_pages:
        shown = bad_pages[:10]
        suffix = ' ...' if len(bad_pages) > 10 else ''
        return f"缺失/失败页 {len(bad_pages)} 个：{shown}{suffix}"
    dup = _duplicate_order_ids(orders)
    if dup:
        return f"快照内出现 {dup} 个重复 order_id（疑似跨代混页）"
    if total_pages > 1:
        expected_min = (total_pages - 1) * MAX_PAGE_SIZE
        if len(orders) < expected_min:
            return (f"订单数 {len(orders)} 低于分页下限 {expected_min}"
                    f"（首页报告 {total_pages} 页）")
    return ""


async def get_all_market_orders(session, order_type="all"):
    """获取吉他市场全量订单（跨代 + 缺页 + 数量校验：任何一项不满足都整体重拉）。

    一份"可用快照"须同时满足：
    1. 没有失败页 / 空页 / 跨代页（bad_pages 为空）；
    2. 订单总数不低于 (总页数-1) × 1000，防止分页被静默截断。

    最多重试 MAX_SNAPSHOT_ATTEMPTS 次；仍不满足则抛 IncompleteSnapshotError，
    由调用方放弃本轮写库（保留上一份完整数据），而不是把残缺快照写进数据库。
    例外：若本次是「连续失败达到阈值而中止」，说明故障是系统性的，立即报错退出、
    不再整体重拉——此时重复拉取只会把错误风暴放大成 ESI 错误限流。
    本函数只返回内存中的订单，写库由调用方在确认快照可用后统一执行。
    """
    best_count = 0
    best_problem = ''
    for attempt in range(1, MAX_SNAPSHOT_ATTEMPTS + 1):
        if attempt > 1:
            logger.warning(
                "上一轮快照不可用（%s），已丢弃并整体重拉（第 %d/%d 次尝试）",
                best_problem, attempt, MAX_SNAPSHOT_ATTEMPTS)
        orders, bad_pages, total_pages, aborted = await _fetch_full_snapshot(session, order_type)
        problem = _snapshot_problem(orders, bad_pages, total_pages)
        if not problem:
            if attempt > 1:
                logger.info(f"第 {attempt} 次整体拉取已获得完整快照")
            logger.info(f"吉他市场{order_type}订单获取完成，共 {len(orders)} 个订单")
            return orders
        best_count = max(best_count, len(orders))
        best_problem = problem
        if aborted:
            raise IncompleteSnapshotError(
                f"连续 {MAX_CONSECUTIVE_FAILURES} 页请求失败，已提前中止本轮抓取以避免触发 "
                f"ESI 错误限流（100 errors/60s）；问题：{best_problem}")

    raise IncompleteSnapshotError(
        f"连续 {MAX_SNAPSHOT_ATTEMPTS} 次拉取均未得到完整快照，最后一次问题：{best_problem}；"
        f"最多只拿到 {best_count} 个订单，已放弃写库以保留上一份完整数据")


async def process_orders_to_database(orders, incremental=False):
    """
    处理订单数据并写入数据库。

    全量覆盖（incremental=False）前会先比对规模：新快照订单数低于库内现有
    行数的 MIN_SNAPSHOT_RATIO 时拒绝写入，避免用残缺快照清空整个区域。
    返回 True 表示已成功写入，False 表示被拒或写入失败（库内数据保持不变）。
    """
    global error_count, db_conn

    if not orders:
        return False

    dup = _duplicate_order_ids(orders)
    if dup:
        logger.error(
            "快照含 %d 个重复 order_id（疑似跨代混页），已中止写库以保留旧数据", dup)
        return False

    try:
        cursor = db_conn.cursor()

        # 只有在非增量保存时才清理旧数据
        if not incremental:
            existing = cursor.execute(
                'SELECT COUNT(*) FROM market_orders WHERE region_id = ?', (JITA_REGION_ID,)
            ).fetchone()[0]
            if existing and len(orders) < existing * MIN_SNAPSHOT_RATIO:
                logger.error(
                    "快照规模异常：本次 %d 个订单，库内现有 %d，低于 %.0f%% 阈值；"
                    "已中止覆盖以保留旧数据（若确认市场确实大幅收缩，"
                    "请先清空该区旧数据或调整 MIN_SNAPSHOT_RATIO）",
                    len(orders), existing, MIN_SNAPSHOT_RATIO * 100)
                return False
            logger.info(f"清理吉他市场(区域ID: {JITA_REGION_ID})的旧订单数据...")
            cursor.execute('DELETE FROM market_orders WHERE region_id = ?', (JITA_REGION_ID,))
            logger.info(f"成功清理吉他市场的旧订单数据")
        
        # 批量写入订单数据
        orders_sql = '''
            INSERT OR REPLACE INTO market_orders 
            (order_id, region_id, type_id, order_type, price, volume_remain, volume_total, 
             min_volume, is_buy_order, duration, range, issued, system_id, location_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        
        orders_data = []
        for order in orders:
            # 确定订单类型
            order_type = "buy" if order.get('is_buy_order') else "sell"
            
            # 处理range字段
            range_value = order.get('range')
            if isinstance(range_value, str):
                if range_value == "station":
                    range_value = 0
                elif range_value == "region":
                    range_value = -1
                elif range_value == "solarsystem":
                    range_value = -2
                else:
                    try:
                        range_value = int(range_value)
                    except ValueError:
                        range_value = -99
            
            order_data = (
                order.get('order_id'),
                JITA_REGION_ID,
                order.get('type_id'),
                order_type,
                order.get('price'),
                order.get('volume_remain'),
                order.get('volume_total'),
                order.get('min_volume'),
                1 if order.get('is_buy_order') else 0,
                order.get('duration'),
                range_value,
                order.get('issued'),
                order.get('system_id'),
                order.get('location_id')
            )
            orders_data.append(order_data)
        
        cursor.executemany(orders_sql, orders_data)
        db_conn.commit()

        logger.info(f"成功写入 {len(orders_data)} 个订单到数据库")
        return True

    except Exception as e:
        logger.error(f"写入数据库时发生异常: {str(e)}")
        # 回滚未提交的 DELETE/INSERT，避免留下半份快照
        try:
            db_conn.rollback()
        except Exception:
            pass
        error_count += len(orders)
        return False

def load_tracker_config():
    """读取项目根目录 config.json 的 market_orders_tracker 开关。

    关闭：启动采集器只做一次全量快照（走原有 main()，行为与改动前一致）。
    开启：采集器每 interval_minutes 分钟采集一次，并以磁盘暂存表做 diff、记录变更事件。
    每次循环重新读取，修改 config.json 后可即时生效。
    """
    cfg = dict(TRACKER_DEFAULTS)
    try:
        with open(TRACKER_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("读取 config.json 失败: %s，按关闭处理", exc)
        return cfg
    section = data.get('market_orders_tracker') if isinstance(data, dict) else None
    if isinstance(section, dict):
        cfg['enabled'] = bool(section.get('enabled', False))
        for key in ('interval_minutes', 'retention_hours'):
            try:
                cfg[key] = max(1, int(section.get(key, cfg[key])))
            except (TypeError, ValueError):
                pass
    return cfg


async def init_tracking_schema():
    """创建追踪所需的表：变更事件 / 采集元数据 / 磁盘暂存表。

    仅在追踪模式启用时调用；不改动原有 market_orders 表结构。
    """
    cursor = db_conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_ts INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            location_id INTEGER,
            is_buy_order INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            old_price REAL,
            new_price REAL,
            old_volume_remain INTEGER,
            new_volume_remain INTEGER,
            delta_pct REAL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_moe_type_ts ON market_order_events (type_id, snapshot_ts)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_moe_order_ts ON market_order_events (order_id, snapshot_ts)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_moe_ts ON market_order_events (snapshot_ts)')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_order_snapshots (
            snapshot_ts INTEGER PRIMARY KEY,
            region_id INTEGER,
            order_count INTEGER,
            event_count INTEGER,
            last_modified TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_orders_staging (
            order_id INTEGER PRIMARY KEY,
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
            location_id INTEGER NOT NULL
        )
    ''')
    db_conn.commit()
    logger.info("追踪表结构初始化成功（events / snapshots / staging）")


def _build_staging_rows(orders):
    """把 ESI 订单 dict 转成暂存表的行（与原有写库口径一致）。"""
    rows = []
    for order in orders:
        order_type = "buy" if order.get('is_buy_order') else "sell"
        range_value = order.get('range')
        if isinstance(range_value, str):
            if range_value == "station":
                range_value = 0
            elif range_value == "region":
                range_value = -1
            elif range_value == "solarsystem":
                range_value = -2
            else:
                try:
                    range_value = int(range_value)
                except ValueError:
                    range_value = -99
        rows.append((
            order.get('order_id'),
            order.get('type_id'),
            order_type,
            order.get('price'),
            order.get('volume_remain'),
            order.get('volume_total'),
            order.get('min_volume'),
            1 if order.get('is_buy_order') else 0,
            order.get('duration'),
            range_value,
            order.get('issued'),
            order.get('system_id'),
            order.get('location_id'),
        ))
    return rows


async def process_orders_tracking(orders, snapshot_ts, retention_hours):
    """追踪写库：用磁盘暂存表在 SQLite 内完成快照 diff，不做内存对比，断电可恢复。

    整个流程在一个事务内完成：若中途断电回滚，market_orders 仍停留在上一份
    已确认快照，下次采集重新拉取并重新 diff 即可，不会写错或丢状态。
    原有 process_orders_to_database 保持不变，仅在开关关闭时使用。

    写库前做规模比对：快照订单数低于库内基线 × MIN_SNAPSHOT_RATIO 时直接放弃
    本轮 diff —— 否则缺页会被误判成"订单消失"，伪造大量 delete 事件并污染
    churn 统计。返回 True 表示已写入，False 表示被拒。
    """
    global db_conn
    cursor = db_conn.cursor()

    baseline = cursor.execute(
        'SELECT COUNT(*) FROM market_orders WHERE region_id = ?', (JITA_REGION_ID,)
    ).fetchone()[0]

    if baseline and len(orders) < baseline * MIN_SNAPSHOT_RATIO:
        logger.error(
            "快照规模异常：本次 %d 个订单，库内基线 %d，低于 %.0f%% 阈值；"
            "跳过本轮 diff（不写订单、不记事件，库内数据保持上一份）",
            len(orders), baseline, MIN_SNAPSHOT_RATIO * 100)
        return False

    dup = _duplicate_order_ids(orders)
    if dup:
        logger.error(
            "快照含 %d 个重复 order_id（疑似跨代混页），跳过本轮 diff："
            "重复行会触发 staging 主键冲突并让缺失页统计失真", dup)
        return False

    # 1) 新快照写入暂存表（覆盖上一次暂存内容）
    cursor.execute('DELETE FROM market_orders_staging')
    cursor.executemany(
        'INSERT INTO market_orders_staging (order_id, type_id, order_type, price, '
        'volume_remain, volume_total, min_volume, is_buy_order, duration, range, issued, '
        'system_id, location_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        _build_staging_rows(orders))

    # 2) 记录并删除已消失的订单（delete）
    cursor.execute('''
        INSERT INTO market_order_events
            (snapshot_ts, order_id, type_id, location_id, is_buy_order, event_type,
             old_price, old_volume_remain)
        SELECT ?, m.order_id, m.type_id, m.location_id, m.is_buy_order, 'delete',
               m.price, m.volume_remain
        FROM market_orders m
        WHERE m.region_id = ?
          AND NOT EXISTS (SELECT 1 FROM market_orders_staging s WHERE s.order_id = m.order_id)
    ''', (snapshot_ts, JITA_REGION_ID))
    cursor.execute('''
        DELETE FROM market_orders
        WHERE region_id = ?
          AND NOT EXISTS (SELECT 1 FROM market_orders_staging s WHERE s.order_id = market_orders.order_id)
    ''', (JITA_REGION_ID,))

    if baseline > 0:
        # 3) 新增订单（insert）——首次建立基线时不记，避免把存量订单误记为新增
        cursor.execute('''
            INSERT INTO market_order_events
                (snapshot_ts, order_id, type_id, location_id, is_buy_order, event_type,
                 new_price, new_volume_remain)
            SELECT ?, s.order_id, s.type_id, s.location_id, s.is_buy_order, 'insert',
                   s.price, s.volume_remain
            FROM market_orders_staging s
            WHERE NOT EXISTS (SELECT 1 FROM market_orders m WHERE m.order_id = s.order_id)
        ''', (snapshot_ts,))

    # 4) 记录改单（modify）：同 order_id 且价格/数量发生变化
    cursor.execute('''
        INSERT INTO market_order_events
            (snapshot_ts, order_id, type_id, location_id, is_buy_order, event_type,
             old_price, new_price, old_volume_remain, new_volume_remain, delta_pct)
        SELECT ?, m.order_id, m.type_id, m.location_id, m.is_buy_order, 'modify',
               m.price, s.price, m.volume_remain, s.volume_remain,
               CASE WHEN m.price > 0 THEN (s.price - m.price) / m.price ELSE NULL END
        FROM market_orders m
        JOIN market_orders_staging s ON s.order_id = m.order_id
        WHERE m.region_id = ?
          AND (m.price <> s.price OR m.volume_remain <> s.volume_remain
               OR m.volume_total <> s.volume_total)
    ''', (snapshot_ts, JITA_REGION_ID))

    # 5) 暂存合并进 market_orders：新增插入，变化行更新，未变化行保持不动
    cursor.execute('''
        INSERT OR IGNORE INTO market_orders
            (order_id, region_id, type_id, order_type, price, volume_remain, volume_total,
             min_volume, is_buy_order, duration, range, issued, system_id, location_id)
        SELECT s.order_id, ?, s.type_id, s.order_type, s.price, s.volume_remain, s.volume_total,
               s.min_volume, s.is_buy_order, s.duration, s.range, s.issued, s.system_id, s.location_id
        FROM market_orders_staging s
    ''', (JITA_REGION_ID,))
    cursor.execute('''
        UPDATE market_orders AS m SET
            price = s.price,
            volume_remain = s.volume_remain,
            volume_total = s.volume_total,
            min_volume = s.min_volume,
            duration = s.duration,
            range = s.range,
            system_id = s.system_id,
            location_id = s.location_id,
            updated_at = CURRENT_TIMESTAMP
        FROM market_orders_staging AS s
        WHERE m.order_id = s.order_id
          AND (m.price <> s.price OR m.volume_remain <> s.volume_remain
               OR m.volume_total <> s.volume_total
               OR m.location_id <> s.location_id OR m.system_id <> s.system_id)
    ''')

    # 6) 本次采集元数据
    event_count = cursor.execute(
        'SELECT COUNT(*) FROM market_order_events WHERE snapshot_ts = ?', (snapshot_ts,)
    ).fetchone()[0]
    cursor.execute('''
        INSERT OR REPLACE INTO market_order_snapshots
            (snapshot_ts, region_id, order_count, event_count, last_modified)
        VALUES (?, ?, ?, ?, ?)
    ''', (snapshot_ts, JITA_REGION_ID, len(orders), event_count, None))

    # 7) 清理超期事件与元数据（保留窗口 = retention_hours）
    cutoff = snapshot_ts - retention_hours * 3600
    cursor.execute('DELETE FROM market_order_events WHERE snapshot_ts < ?', (cutoff,))
    cursor.execute('DELETE FROM market_order_snapshots WHERE snapshot_ts < ?', (cutoff,))

    db_conn.commit()
    logger.info(
        "追踪写入完成：快照时间 %s，订单数 %d，本次变更事件 %d",
        snapshot_ts, len(orders), event_count)
    return True


async def main_tracking():
    """追踪模式主循环：每 interval_minutes 分钟采集一次并记录变更事件。

    开关关闭时不会被调用（见文件末尾分派），关闭状态仍走原有 main()。
    """
    start_time = time.time()
    all_orders = []
    last_incomplete = False
    last_failed = False
    try:
        await init_database()
        await init_tracking_schema()

        async with aiohttp.ClientSession(headers=HEADERS) as session:
            cycle_errors = 0
            while True:
                tracker = load_tracker_config()
                if not tracker['enabled']:
                    logger.info("追踪开关已关闭，停止追踪循环")
                    break

                # 单轮异常不允许终止整个追踪循环：记录后等下一轮重试，
                # 连续多轮仍失败才停止（避免一个坏快照/一次主键冲突就让采集器静默退出）
                try:
                    logger.info("开始获取吉他市场订单数据（追踪模式）...")
                    snapshot_incomplete = False
                    try:
                        all_orders = await get_all_market_orders(session, "all")
                    except IncompleteSnapshotError as exc:
                        snapshot_incomplete = True
                        all_orders = []
                        logger.error("本轮快照不完整，跳过本次 diff（保留上一份快照与事件）：%s", exc)

                    last_incomplete = snapshot_incomplete
                    if snapshot_incomplete:
                        logger.warning("本轮未采集到可用快照，数据库与事件表保持不变")
                    elif not all_orders:
                        logger.warning("没有获取到任何吉他市场订单数据")
                    else:
                        logger.info(f"获取到 {len(all_orders)} 个吉他市场订单数据")
                        await process_orders_tracking(
                            all_orders, int(time.time()), tracker['retention_hours'])
                    cycle_errors = 0
                    last_failed = False
                except Exception as exc:
                    last_failed = True
                    cycle_errors += 1
                    logger.error(
                        "本轮采集/写库异常（连续第 %d 次），已跳过本轮并等待下一次采集：%s",
                        cycle_errors, exc, exc_info=True)
                    if cycle_errors >= MAX_CYCLE_ERRORS:
                        logger.error(
                            "连续 %d 轮异常，停止追踪循环；请检查数据库可用性与磁盘空间",
                            cycle_errors)
                        break

                interval = tracker['interval_minutes']
                logger.info(f"追踪模式已启用，{interval} 分钟后进行下一次采集（关闭 config.json 开关可停止）")
                await asyncio.sleep(interval * 60)
    except Exception as e:
        logger.error(f"发生未预期的错误: {str(e)}", exc_info=True)
    finally:
        if db_conn is not None:
            try:
                db_conn.close()
                logger.info("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接时出错: {str(e)}")
        end_time = time.time()
        logger.info(f"吉他市场订单追踪结束！")
        if last_incomplete:
            logger.warning("最后一次采集快照不完整，未写库；数据库保持上一份完整快照")
        elif last_failed:
            logger.warning("最后一次采集异常，未写库；数据库保持上一份快照")
        else:
            logger.info(f"最后一次获取订单数: {len(all_orders)}")
        logger.info(f"错误数量: {error_count}")
        logger.info(f"总运行时长: {end_time - start_time:.2f} 秒")


async def main():
    """
    主函数，协调整个流程
    """
    start_time = time.time()
    all_orders = []
    snapshot_incomplete = False

    try:
        # 初始化数据库
        await init_database()
        
        # 异步获取吉他市场订单数据
        async with aiohttp.ClientSession(headers=HEADERS) as session:
            logger.info("开始获取吉他市场订单数据...")
            
            # 一次性获取所有订单（买单和卖单）
            try:
                all_orders = await get_all_market_orders(session, "all")
            except IncompleteSnapshotError as exc:
                snapshot_incomplete = True
                logger.error("本轮快照不完整，已跳过写库以保留上一份完整数据：%s", exc)

            if snapshot_incomplete:
                logger.warning("写库已跳过，数据库保持上一份完整快照")
            elif not all_orders:
                logger.warning("没有获取到任何吉他市场订单数据")
            else:
                logger.info(f"获取到 {len(all_orders)} 个吉他市场订单数据")

                # 将订单数据写入数据库
                await process_orders_to_database(all_orders)
    
    except Exception as e:
        logger.error(f"发生未预期的错误: {str(e)}", exc_info=True)
    finally:
        # 确保关闭数据库连接
        if db_conn is not None:
            try:
                db_conn.close()
                logger.info("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接时出错: {str(e)}")
        
        # 计算并记录执行时间
        end_time = time.time()
        total_time = end_time - start_time
        
        logger.info(f"吉他市场订单数据收集完成！")
        if snapshot_incomplete:
            logger.warning("本轮快照不完整，未写库；数据库保持上一份完整快照")
        else:
            logger.info(f"获取订单总数: {len(all_orders)}")
        logger.info(f"错误数量: {error_count}")
        logger.info(f"总耗时: {total_time:.2f} 秒")

if __name__ == "__main__":
    # 修复Windows下事件循环关闭错误
    import platform
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 按 config.json 的 market_orders_tracker 开关选择运行模式：
    #   关闭 -> 只采集一次全量快照（原有行为，走 main()）
    #   开启 -> 每 interval_minutes 分钟循环采集并记录变更事件（走 main_tracking()）
    if load_tracker_config()['enabled']:
        asyncio.run(main_tracking())
    else:
        asyncio.run(main())