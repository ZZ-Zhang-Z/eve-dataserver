# jita_market_history_collector_async.py
# 异步获取吉他市场历史订单数据并保存到数据库的脚本，支持并发控制、批量处理和错误重试
import asyncio
import aiohttp
import sqlite3
import logging
import time
import random
import sys
import os
import math
from datetime import datetime, timedelta

# 尝试导入tqdm，如果失败则使用简单的进度显示
from tqdm import tqdm

# 添加项目根目录到Python路径以导入database_manager
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database_manager import get_connection_by_table

# 公共模块：统一请求头、按状态码计费的令牌桶、退避、错误率
from esi_client import (
    default_headers,
    TokenBucket,
    ErrorRateTracker,
    rate_limit_monitor,
    compute_backoff,
    check_pagination_consistency,
)

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API配置
BASE_URL = "https://esi.evetech.net"
HEADERS = default_headers()

# 禁用代理（解决环境中的代理连接问题）
PROXIES = None

# 异步配置
MAX_CONCURRENT_REQUESTS = 20  # 进一步降低并发请求数，避免短时间内发送过多请求
MAX_RETRIES = 3  # API请求的最大重试次数

# 吉他市场配置
JITA_REGION_ID = 10000002  # 吉他市场区域ID

# 错误计数
error_count = 0

# 错误速率控制 - 防止每分钟超过100个非2xx/3xx状态码（公共实现）
ERROR_RATE_LIMIT = 50  # 每分钟允许的最大非2xx/3xx状态码数量
ERROR_TIME_WINDOW_SECONDS = 60  # 时间窗口（秒）
ERROR_RATE_THRESHOLD = 30  # 触发延迟的阈值（接近限制前开始减慢）
error_rate_tracker = ErrorRateTracker(ERROR_TIME_WINDOW_SECONDS, ERROR_RATE_LIMIT, ERROR_RATE_THRESHOLD)

# 速率限制配置 - 基于实际API行为调整
REQUESTS_PER_MINUTE = 5000  # 每分钟最大请求数
batch_size = 500  # 每批请求保存一次数据

# 令牌桶：每15分钟12000个令牌（约800请求/分钟），按状态码计费
RATE_LIMIT_TOKENS = 12000
RATE_LIMIT_PERIOD = 15 * 60
rate_limiter = TokenBucket(RATE_LIMIT_TOKENS, RATE_LIMIT_PERIOD)

async def init_database():
    """
    初始化数据库，确保表结构存在
    """
    # 获取市场历史数据库连接
    conn = get_connection_by_table('market_history')
    cursor = conn.cursor()
    
    # 创建market_history表（如果不存在）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_history (
            region_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            average REAL NOT NULL,
            highest REAL NOT NULL,
            lowest REAL NOT NULL,
            order_count INTEGER NOT NULL,
            volume INTEGER NOT NULL,
            PRIMARY KEY (region_id, type_id, date)
        )
    ''')
    
    # 创建索引以提高查询性能
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_history_type_id ON market_history (type_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_market_history_date ON market_history (date)')
    
    conn.commit()
    logger.info("market_history表结构初始化成功")

def manage_error_rate():
    """
    管理错误速率控制（委托给公共 ErrorRateTracker）
    返回:
        当前时间窗口内的错误数量
        推荐的额外延迟时间（秒）
    """
    return error_rate_tracker.get_delay()

async def get_latest_history_date():
    """
    获取数据库中最新的历史订单日期
    返回:
        最新日期字符串或None
    """
    conn = get_connection_by_table('market_history')
    cursor = conn.cursor()
    cursor.execute("SELECT MAX(date) FROM market_history WHERE region_id = ?", (JITA_REGION_ID,))
    result = cursor.fetchone()
    return result[0] if result[0] else None

async def get_market_history(session, type_id):
    """
    获取指定物品类型的吉他市场历史订单数据
    参数:
        session: aiohttp会话对象
        type_id: 物品类型ID
    返回:
        历史订单数据列表
    """
    global error_count
    url = f"{BASE_URL}/markets/{JITA_REGION_ID}/history?type_id={type_id}"
    
    # 指数退避重试逻辑
    for retry in range(MAX_RETRIES + 1):
        try:
            # 使用速率限制器（先预扣1个令牌）
            await rate_limiter.consume()
            
            async with session.get(url) as response:
                # 按状态码补扣/退还令牌
                await rate_limiter.settle(response.status)

                if response.status == 200:
                    # 依据 X-Ratelimit-* 主动降速
                    rate_limiter.update_capacity_from_header(response.headers.get('X-Ratelimit-Limit'))
                    extra_delay = rate_limit_monitor.observe(response.headers)
                    if extra_delay:
                        await asyncio.sleep(extra_delay)

                    history = await response.json()
                    return history
                elif response.status == 404:
                    logger.info(f"物品类型 {type_id} 无历史订单数据")
                    return []
                else:
                    # 记录非2xx/3xx状态码到错误时间窗口
                    error_rate_tracker.record()
                    
                    # 检查错误速率
                    current_error_count, extra_delay = manage_error_rate()
                    
                    if current_error_count >= ERROR_RATE_LIMIT:
                        logger.warning(f"当前时间窗口内已发生 {current_error_count} 个错误，接近限制 ({ERROR_RATE_LIMIT})，将添加额外延迟")
                    
                    if response.status == 420:  # Enhance Your Calm (旧版错误速率限制)
                        if retry < MAX_RETRIES:
                            # 420错误需要更长的延迟，并且应该清理部分错误记录以更快恢复
                            error_rate_tracker.trim(0.8)  # 保留80%的错误记录
                            
                            # 420错误需要更长的延迟
                            wait_time = 60 + random.uniform(0, 10) + extra_delay  # 至少等待60秒 + 错误速率控制延迟
                            logger.warning(f"物品类型 {type_id} 获取历史订单时遇到420错误(旧版错误速率限制)，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"物品类型 {type_id} 获取历史订单失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return []
                    elif response.status == 429:  # Too Many Requests
                        if retry < MAX_RETRIES:
                            # 优先使用API返回的Retry-After时间
                            retry_after = response.headers.get('Retry-After')
                            if retry_after:
                                try:
                                    wait_time = int(retry_after) + random.uniform(0, 1) + extra_delay
                                except ValueError:
                                    wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                            else:
                                # 计算指数退避时间并添加随机抖动
                                wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                        
                            logger.warning(f"物品类型 {type_id} 获取历史订单时遇到429错误，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"物品类型 {type_id} 获取历史订单失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return []
                    else:
                        if retry < MAX_RETRIES:
                            # 根据状态码调整重试策略
                            if 400 <= response.status < 500 and response.status != 429:  # 4XX错误，消耗5个令牌
                                wait_time = (2 ** retry + random.uniform(0, 1)) * 2 + extra_delay  # 增加延迟时间 + 错误速率控制延迟
                                logger.warning(f"物品类型 {type_id} 获取历史订单失败(4XX错误)，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            elif 500 <= response.status < 600:  # 5XX错误，消耗0个令牌
                                # 对于504等服务器错误，增加更长的延迟
                                if response.status == 504:
                                    wait_time = (2 ** retry + random.uniform(0, 1)) * 3 + extra_delay  # 增加延迟时间
                                    logger.warning(f"物品类型 {type_id} 获取历史订单失败(网关超时)，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                                else:
                                    wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                                    logger.warning(f"物品类型 {type_id} 获取历史订单失败(服务器错误)，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            else:
                                wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                                logger.warning(f"物品类型 {type_id} 获取历史订单失败，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                        
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"物品类型 {type_id} 获取历史订单失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return []
        except aiohttp.ClientError as e:
            # 记录异常到错误时间窗口
            error_rate_tracker.record()
            
            if retry < MAX_RETRIES:
                # 获取错误速率控制延迟
                current_error_count, extra_delay = manage_error_rate()
                wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                logger.warning(f"物品类型 {type_id} 获取历史订单时发生网络异常: {str(e)}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"物品类型 {type_id} 获取历史订单时发生网络异常: {str(e)}，已达到最大重试次数")
                error_count += 1
                return []
        except Exception as e:
            # 记录异常到错误时间窗口
            error_rate_tracker.record()
            
            logger.error(f"物品类型 {type_id} 获取历史订单时发生意外异常: {str(e)}")
            error_count += 1
            return []

def _clean_type_ids(ids):
    """去重 + 类型校验：分页期间列表可能变化，可能带来重复或非整数项。"""
    clean = []
    seen = set()
    for tid in ids:
        if isinstance(tid, int) and tid not in seen:
            seen.add(tid)
            clean.append(tid)
    if len(clean) != len(ids):
        logger.info("活跃物品类型清洗：%d -> %d 条（去重 / 剔除非法项）", len(ids), len(clean))
    return clean


async def get_active_type_ids(session):
    """
    获取吉他市场具有活跃订单的物品类型ID列表
    参数:
        session: aiohttp会话对象
    返回:
        活跃物品类型ID列表
    """
    active_type_ids = []
    page = 1
    max_page_size = 1000  # ESI API每页最大返回1000个结果
    first_last_modified = None
    
    while True:
        url = f"{BASE_URL}/markets/{JITA_REGION_ID}/types?page={page}"
        
        # 指数退避重试逻辑
        for retry in range(MAX_RETRIES + 1):
            try:
                # 使用速率限制器（先预扣1个令牌）
                await rate_limiter.consume()
                async with session.get(url) as response:
                    # 按状态码补扣/退还令牌
                    await rate_limiter.settle(response.status)
                    if response.status == 200:
                        # 依据 X-Ratelimit-* 主动降速
                        rate_limiter.update_capacity_from_header(response.headers.get('X-Ratelimit-Limit'))
                        extra_delay = rate_limit_monitor.observe(response.headers)
                        if extra_delay:
                            await asyncio.sleep(extra_delay)
                        # 获取速率限制相关头部信息
                        rate_limit_group = response.headers.get('X-Ratelimit-Group', 'unknown')
                        rate_limit_limit = response.headers.get('X-Ratelimit-Limit', 'unknown')
                        rate_limit_remaining = response.headers.get('X-Ratelimit-Remaining', 'unknown')
                        rate_limit_used = response.headers.get('X-Ratelimit-Used', 'unknown')
                        
                        # 不再记录速率限制信息
                        
                        type_ids = await response.json()
                        logger.info(f"获取吉他市场活跃物品类型第 {page} 页，共 {len(type_ids)} 个")

                        # 分页一致性：各页 last-modified 应一致，否则列表在采集期间变化过
                        last_modified = response.headers.get('Last-Modified')
                        if first_last_modified is None:
                            first_last_modified = last_modified
                        elif not check_pagination_consistency(first_last_modified, last_modified):
                            logger.warning(
                                "活跃物品类型分页 last-modified 不一致（第 %d 页），"
                                "列表可能在采集期间变化，按去重结果继续", page)

                        active_type_ids.extend(type_ids)
                        
                        # 如果当前页数据量小于最大页大小，则是最后一页
                        if len(type_ids) < max_page_size:
                            logger.info(f"获取到 {len(type_ids)} 个活跃物品类型ID，小于每页最大数量 {max_page_size}，停止分页")
                            logger.info(f"吉他市场活跃物品类型所有页面已获取完成")
                            return _clean_type_ids(active_type_ids)
                        
                        break
                    elif response.status == 404:
                        logger.warning(
                            "活跃物品类型第 %d 页返回 404（分页收缩），"
                            "按已取到的 %d 个类型继续", page, len(active_type_ids))
                        return _clean_type_ids(active_type_ids)
                    elif response.status == 420:  # Enhance Your Calm (旧版错误速率限制)
                        if retry < MAX_RETRIES:
                            # 记录错误到错误时间窗口
                            error_rate_tracker.record()
                            
                            # 获取错误速率控制延迟
                            current_error_count, extra_delay = manage_error_rate()
                            
                            # 420错误需要更长的延迟，并且应该清理部分错误记录以更快恢复
                            error_rate_tracker.trim(0.8)  # 保留80%的错误记录
                            
                            # 420错误需要更长的延迟
                            wait_time = 60 + random.uniform(0, 10) + extra_delay  # 至少等待60秒 + 错误速率控制延迟
                            logger.warning(f"获取活跃物品类型时遇到420错误(旧版错误速率限制)，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取活跃物品类型失败，状态码: {response.status}，已达到最大重试次数")
                            return []
                    elif response.status == 429:  # Too Many Requests
                        if retry < MAX_RETRIES:
                            # 记录错误到错误时间窗口
                            error_rate_tracker.record()
                            
                            # 获取错误速率控制延迟
                            current_error_count, extra_delay = manage_error_rate()
                            
                            # 优先使用API返回的Retry-After时间
                            retry_after = response.headers.get('Retry-After')
                            if retry_after:
                                try:
                                    wait_time = int(retry_after) + random.uniform(0, 1) + extra_delay
                                except ValueError:
                                    wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                            else:
                                # 计算指数退避时间并添加随机抖动
                                wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                            
                            logger.warning(f"获取活跃物品类型时遇到429错误，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取活跃物品类型失败，状态码: {response.status}，已达到最大重试次数")
                            return []
                    else:
                        # 记录错误到错误时间窗口
                        error_rate_tracker.record()
                        
                        # 获取错误速率控制延迟
                        current_error_count, extra_delay = manage_error_rate()
                        
                        if retry < MAX_RETRIES:
                            # 根据状态码调整重试策略
                            if 400 <= response.status < 500 and response.status != 429:  # 4XX错误，消耗5个令牌
                                wait_time = (2 ** retry + random.uniform(0, 1)) * 2 + extra_delay  # 增加延迟时间 + 错误速率控制延迟
                                logger.warning(f"获取活跃物品类型失败(4XX错误)，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            elif 500 <= response.status < 600:  # 5XX错误，消耗0个令牌
                                wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                                logger.warning(f"获取活跃物品类型失败(服务器错误)，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            else:
                                wait_time = 2 ** retry + random.uniform(0, 1) + extra_delay
                                logger.warning(f"获取活跃物品类型失败，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取活跃物品类型失败，状态码: {response.status}，已达到最大重试次数")
                            return []
            except aiohttp.ClientError as e:
                if retry < MAX_RETRIES:
                    wait_time = 2 ** retry + random.uniform(0, 1)
                    logger.warning(f"获取活跃物品类型时发生网络异常: {str(e)}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(f"获取活跃物品类型时发生网络异常: {str(e)}，已达到最大重试次数")
                    return []
            except Exception as e:
                logger.error(f"获取活跃物品类型时发生意外异常: {str(e)}")
                return []
        
        page += 1
        
        # 固定延迟时间，不再基于令牌数动态调整
        delay = 0.1 + random.uniform(0, 0.05)
        
        await asyncio.sleep(delay)
    
    logger.info(f"吉他市场活跃物品类型获取完成，共 {len(active_type_ids)} 个类型")
    return _clean_type_ids(active_type_ids)

# 历史保留窗口（天）。必须覆盖分析脚本的 30 天窗口（ANALYSIS_DAYS=30），
# 否则新装环境永远凑不够 30 天；同时避免"只写最近 7 天"导致采集间隔一旦
# 超过 7 天就永久缺数据。ESI /history 一次返回全量历史，窗口只影响入库量。
HISTORY_KEEP_DAYS = 35


def _normalize_history_record(type_id, record):
    """校验并规范化一条历史记录；非法返回 None。

    ESI 偶发返回缺字段或异常值（最高价低于最低价、均价越界、未来日期等），
    直接入库会污染均价、波动率与成交量门槛，因此逐条校验后再写。
    """
    if not isinstance(type_id, int):
        return None
    try:
        date_str = str(record['date'])
        record_date = datetime.strptime(date_str, '%Y-%m-%d')
        average = float(record['average'])
        highest = float(record['highest'])
        lowest = float(record['lowest'])
        order_count = int(record['order_count'])
        volume = int(record['volume'])
    except (KeyError, TypeError, ValueError):
        return None
    if lowest <= 0 or highest < lowest or average <= 0:
        return None
    if not (lowest - 1e-9 <= average <= highest + 1e-9):
        return None
    if order_count < 0 or volume < 0:
        return None
    if record_date.date() > datetime.now().date():
        return None
    return (JITA_REGION_ID, type_id, date_str, average, highest, lowest, order_count, volume)


async def batch_save_history_to_db(batch_data, keep_days=HISTORY_KEEP_DAYS):
    """批量保存历史订单数据（逐条校验 + 窗口过滤 + 批内去重）。

    返回 (写入条数, 跳过条数)；跳过包含字段非法、超出窗口、未来日期与重复。
    """
    if not batch_data:
        return 0, 0

    conn = get_connection_by_table('market_history')
    cursor = conn.cursor()

    cutoff = datetime.now() - timedelta(days=keep_days)
    insert_data = []
    seen = set()
    skipped = 0

    for type_id, history_data in batch_data:
        for record in history_data or []:
            row = _normalize_history_record(type_id, record)
            if row is None:
                skipped += 1
                continue
            if datetime.strptime(row[2], '%Y-%m-%d') < cutoff:
                skipped += 1
                continue
            key = (row[1], row[2])
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            insert_data.append(row)

    try:
        if insert_data:
            cursor.executemany('''
                INSERT OR REPLACE INTO market_history
                (region_id, type_id, date, average, highest, lowest, order_count, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', insert_data)
            conn.commit()
        logger.info("历史数据写入 %d 条（窗口 %d 天），跳过 %d 条非法/超期/重复",
                    len(insert_data), keep_days, skipped)
    except sqlite3.Error as e:
        logger.error("批量保存历史订单数据到数据库时发生错误: %s", str(e))
        conn.rollback()
        return 0, skipped
    return len(insert_data), skipped


async def get_all_market_history():
    """
    获取吉他市场所有活跃物品的历史订单数据
    """
    # 创建aiohttp会话，优化连接池配置
    timeout = aiohttp.ClientTimeout(total=180, sock_connect=30, sock_read=60)  # 优化超时设置
    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT_REQUESTS,
        limit_per_host=MAX_CONCURRENT_REQUESTS,  # 每个主机的最大连接数
        keepalive_timeout=60,  # 保持连接活跃时间
        force_close=False  # 不强制关闭连接
    )
    async with aiohttp.ClientSession(timeout=timeout, headers=HEADERS, connector=connector) as session:
        # 获取活跃物品类型ID列表
        active_type_ids = await get_active_type_ids(session)
        
        if not active_type_ids:
            logger.warning("未获取到任何活跃物品类型，跳过历史订单获取")
            return
        
        total_types = len(active_type_ids)
        logger.info(f"开始获取 {total_types} 个物品类型的历史订单")
        
        # 优化1: 使用任务队列和动态并发控制
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)  # 初始并发数
        tasks = []
        history_data_batches = []  # 用于批量保存的历史数据
        
        async def fetch_history_worker(type_id):
            async with semaphore:
                return type_id, await get_market_history(session, type_id)
        
        # 创建所有任务
        for type_id in active_type_ids:
            task = asyncio.create_task(fetch_history_worker(type_id))
            tasks.append(task)
        
        # 收集结果，每收集一批就保存到数据库
        collected_count = 0
        success_count = 0
        start_time = time.time()
        last_save_time = start_time
        
        # 使用tqdm显示进度
        with tqdm(total=total_types, desc="获取历史订单", unit="个") as pbar:
            for task in asyncio.as_completed(tasks):
                try:
                    type_id, history_data = await task
                    collected_count += 1
                    pbar.update(1)
                    
                    if history_data:
                        # 将数据添加到批量保存列表
                        history_data_batches.append((type_id, history_data))
                        success_count += 1
                    
                    # 每收集一定数量的数据就保存到数据库
                    if len(history_data_batches) >= batch_size:
                        if history_data_batches:  # 确保有数据要保存
                            current_time = time.time()
                            time_elapsed = current_time - start_time
                            time_per_batch = (current_time - last_save_time) if collected_count > batch_size else time_elapsed
                            batches_remaining = math.ceil((total_types - collected_count) / batch_size)
                            
                            # 基于历史处理速度的预估时间
                            estimated_time_based_on_history = time_per_batch * batches_remaining
                            
                            # 考虑速率限制的最小预估时间
                            remaining_requests = total_types - collected_count
                            min_time_based_on_rate_limit = remaining_requests / (REQUESTS_PER_MINUTE / 60)  # 转换为秒
                            
                            # 取较大的预估时间（考虑速率限制）
                            estimated_time_remaining = max(estimated_time_based_on_history, min_time_based_on_rate_limit)
                            
                            # 记录保存前的统计信息
                            logger.info(f"已处理 {collected_count}/{total_types} 个类型 ({collected_count/total_types*100:.1f}%)，开始保存第 {collected_count // batch_size} 批数据")
                            logger.info(f"预估剩余时间: {estimated_time_remaining:.2f} 秒")
                            
                            await batch_save_history_to_db(history_data_batches)
                            history_data_batches = []  # 清空批量列表
                            last_save_time = current_time
                except Exception as e:
                    logger.error(f"处理物品类型时发生异常: {str(e)}")
        
        # 保存剩余的数据
        if history_data_batches:
            logger.info(f"保存最后一批数据（剩余 {len(history_data_batches)} 个类型）")
            await batch_save_history_to_db(history_data_batches)
        
        logger.info(f"最后一批处理完成，共处理 {collected_count} 个物品类型")
    
    logger.info(f"吉他市场历史订单获取完成，共处理 {collected_count} 个物品类型，成功保存 {success_count} 个物品类型的历史订单")
    logger.info(f"获取过程中发生 {error_count} 个错误")

async def main():
    """
    主函数，协调整个历史订单获取流程
    """
    try:
        start_time = time.time()
        logger.info("开始获取吉他市场活跃物品的历史订单数据")
        
        # 初始化数据库
        await init_database()
        
        # 获取并保存所有活跃物品的历史订单数据
        await get_all_market_history()
        
        end_time = time.time()
        logger.info(f"吉他市场历史订单数据获取完成，总耗时: {end_time - start_time:.2f}秒")
    except KeyboardInterrupt:
        logger.info("用户中断了历史订单获取过程")
    except Exception as e:
        logger.error(f"获取历史订单数据时发生意外异常: {str(e)}")

if __name__ == "__main__":
    # 在Windows系统上使用正确的事件循环策略
    import platform
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 运行主函数
    asyncio.run(main())