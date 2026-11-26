# market_group_collector.py
# 异步获取EVE Online市场物品组数据并保存到数据库的脚本
import asyncio
import aiohttp
import sqlite3
import logging
import time
import random
import os
import sys

# 将项目根目录加入搜索路径，以便导入 paths
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from paths import DB_FILES

# 公共模块：统一请求头、退避、错误率、ETag 条件请求缓存
from esi_client import default_headers, HttpCache, error_rate_tracker, compute_backoff, TokenBucket

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# API配置
BASE_URL = "https://esi.evetech.net"
HEADERS = default_headers()

# ETag 条件请求缓存（在 main 中初始化）
http_cache = None

# 禁用代理（解决环境中的代理连接问题）
PROXIES = None

# 数据库配置
DB_FILE = DB_FILES['items']

# 异步配置
MAX_CONCURRENT_REQUESTS = 20  # 最大并发请求数

# 公开路由共享令牌桶（默认 12000/15m），按状态码计费
rate_limiter = TokenBucket()
BATCH_SIZE = 50  # 每批处理的物品组数量
MAX_RETRIES = 3  # API请求的最大重试次数

# 错误计数
error_count = 0

# 全局数据库连接变量
db_conn = None

async def init_database():
    """
    初始化数据库，创建表结构并建立全局连接
    """
    global db_conn
    
    # 创建数据库连接（全局复用）
    db_conn = sqlite3.connect(DB_FILE)
    cursor = db_conn.cursor()
    
    # 设置SQLite为WAL模式以提高并发性能
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=10000;")
    
    # 创建物品组表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_groups (
            market_group_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            parent_group_id INTEGER,
            FOREIGN KEY (parent_group_id) REFERENCES market_groups (market_group_id)
        )
    ''')
    
    # 创建物品组与物品类型的关联表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_group_items (
            market_group_id INTEGER NOT NULL,
            type_id INTEGER NOT NULL,
            PRIMARY KEY (market_group_id, type_id),
            FOREIGN KEY (market_group_id) REFERENCES market_groups (market_group_id)
        )
    ''')
    
    db_conn.commit()
    logger.info("数据库初始化完成")

async def get_all_market_group_ids(session):
    """
    获取所有市场物品组ID
    """
    global error_count
    
    url = f"{BASE_URL}/markets/groups"
    try:
        await rate_limiter.consume()
        async with session.get(url) as response:
            await rate_limiter.on_response(response.status, response.headers)
            if response.status == 200:
                market_group_ids = await response.json()
                logger.info(f"获取到 {len(market_group_ids)} 个市场物品组ID")
                return market_group_ids
            else:
                logger.error(f"获取市场物品组ID失败，状态码: {response.status}，响应: {await response.text()}")
                error_count += 1
                return []
    except Exception as e:
        logger.error(f"获取市场物品组ID时发生异常: {str(e)}")
        error_count += 1
        return []

async def get_market_group_info(session, market_group_id, semaphore):
    """
    获取单个市场物品组的详细信息
    参数:
        session: aiohttp会话对象
        market_group_id: 物品组ID
        semaphore: 信号量对象，用于限制并发请求
    返回:
        物品组详细信息的字典
    """
    global error_count
    url = f"{BASE_URL}/markets/groups/{market_group_id}"
    
    # 指数退避重试逻辑
    for retry in range(MAX_RETRIES + 1):
        try:
            # 使用信号量限制并发请求
            async with semaphore:
                req_headers = http_cache.conditional_headers(url) if http_cache else {}
                await rate_limiter.consume()
                async with session.get(url, headers=req_headers) as response:
                    await rate_limiter.on_response(response.status, response.headers)
                    if response.status == 200:
                        group_info = await response.json()
                        if http_cache:
                            http_cache.save(url, response.headers.get('ETag'), response.headers.get('Last-Modified'))
                        logger.debug(f"获取物品组ID {market_group_id} 的详细信息成功")
                        return group_info
                    elif response.status == 304:
                        # 命中缓存，数据未变更，跳过解析/入库
                        logger.debug(f"物品组ID {market_group_id} 数据未变更(304)")
                        return None
                    elif response.status == 404:
                        logger.warning(f"物品组ID {market_group_id} 不存在")
                        return None
                    elif response.status == 420 or response.status == 429:  # 速率限制
                        error_rate_tracker.record()
                        _, extra_delay = error_rate_tracker.get_delay()
                        if retry < MAX_RETRIES:
                            wait_time = compute_backoff(retry, status_code=response.status,
                                                        retry_after=response.headers.get('Retry-After'),
                                                        extra_delay=extra_delay)
                            logger.warning(f"获取物品组ID {market_group_id} 时遇到速率限制(状态码 {response.status})，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取物品组ID {market_group_id} 详细信息失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return None
                    else:
                        error_rate_tracker.record()
                        _, extra_delay = error_rate_tracker.get_delay()
                        if retry < MAX_RETRIES:
                            wait_time = compute_backoff(retry, status_code=response.status,
                                                        retry_after=response.headers.get('Retry-After'),
                                                        extra_delay=extra_delay)
                            logger.warning(f"获取物品组ID {market_group_id} 失败，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取物品组ID {market_group_id} 详细信息失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return None
        except aiohttp.ClientError as e:
            if retry < MAX_RETRIES:
                wait_time = 2 ** retry + random.uniform(0, 1)
                logger.warning(f"获取物品组ID {market_group_id} 时发生网络异常: {str(e)}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"获取物品组ID {market_group_id} 详细信息时发生网络异常: {str(e)}，已达到最大重试次数")
                error_count += 1
                return None
        except Exception as e:
            logger.error(f"获取物品组ID {market_group_id} 详细信息时发生意外异常: {str(e)}")
            error_count += 1
            return None

async def batch_write_market_groups_to_database(batch_groups):
    """
    批量写入物品组信息到数据库
    参数:
        batch_groups: 物品组详细信息列表
    """
    global error_count, db_conn
    
    if not batch_groups:
        return
    
    try:
        cursor = db_conn.cursor()
        
        # 批量写入物品组基本信息
        groups_sql = '''
            INSERT OR REPLACE INTO market_groups 
            (market_group_id, name, description, parent_group_id)
            VALUES (?, ?, ?, ?)
        '''
        groups_data = [(group.get('market_group_id'), group.get('name'), 
                       group.get('description'), group.get('parent_group_id')) 
                       for group in batch_groups]
        cursor.executemany(groups_sql, groups_data)
        
        # 收集并批量写入物品组与物品类型的关联
        batch_group_items = []
        for group in batch_groups:
            if 'types' in group:
                for type_id in group['types']:
                    batch_group_items.append((
                        group['market_group_id'],
                        type_id
                    ))
        
        if batch_group_items:
            group_items_sql = '''
                INSERT OR REPLACE INTO market_group_items 
                (market_group_id, type_id)
                VALUES (?, ?)
            '''
            cursor.executemany(group_items_sql, batch_group_items)
        
        db_conn.commit()
        
        logger.info(f"批量写入完成，共写入 {len(batch_groups)} 个物品组，{len(batch_group_items)} 个物品组-物品关联")
        
    except Exception as e:
        logger.error(f"批量写入数据库时发生异常: {str(e)}")
        error_count += len(batch_groups)

async def process_market_groups_batch(session, market_group_ids):
    """
    处理一批市场物品组
    参数:
        session: aiohttp会话对象
        market_group_ids: 物品组ID列表
    返回:
        成功处理的物品组数量
    """
    # 创建信号量限制并发请求
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    tasks = []
    for group_id in market_group_ids:
        task = asyncio.create_task(get_market_group_info(session, group_id, sem))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过滤掉None结果和异常
    valid_results = [result for result in results if isinstance(result, dict) and result is not None]
    
    # 批量写入数据库
    if valid_results:
        await batch_write_market_groups_to_database(valid_results)
    
    return len(valid_results)

async def process_market_groups_async(session, market_group_ids):
    """
    异步处理市场物品组列表
    参数:
        session: aiohttp会话对象
        market_group_ids: 物品组ID列表
    """
    global error_count
    total_groups = len(market_group_ids)
    processed_groups = 0
    
    logger.info(f"开始异步处理 {total_groups} 个市场物品组")
    
    # 记录开始处理的时间
    start_time = time.time()
    
    # 将物品组ID列表分割成批次
    for i in range(0, total_groups, BATCH_SIZE):
        batch_group_ids = market_group_ids[i:i+BATCH_SIZE]
        
        # 处理当前批次
        result = await process_market_groups_batch(session, batch_group_ids)
        processed_groups += result
        
        logger.info(f"已处理 {processed_groups}/{total_groups} 个物品组")
        
        # 每处理100个物品组显示预计剩余时间
        if processed_groups % 100 == 0 and processed_groups > 0:
            elapsed_time = time.time() - start_time
            groups_per_second = processed_groups / elapsed_time
            remaining_groups = total_groups - processed_groups
            estimated_remaining_time = remaining_groups / groups_per_second if groups_per_second > 0 else 0
            
            # 格式化时间为小时、分钟、秒
            hours, rem = divmod(estimated_remaining_time, 3600)
            minutes, seconds = divmod(rem, 60)
            
            logger.info(f"预计剩余时间: {int(hours)}小时 {int(minutes)}分钟 {int(seconds)}秒")
        
        # 避免请求过快
        await asyncio.sleep(0.5)
    
    logger.info(f"异步处理完成，共处理 {processed_groups} 个物品组，失败 {total_groups - processed_groups} 个")
    return processed_groups

async def main():
    """
    主函数，协调整个流程
    """
    start_time = time.time()
    
    # 初始化数据库
    await init_database()

    # 初始化 ETag 条件请求缓存
    global http_cache
    http_cache = HttpCache()
    
    # 异步获取所有市场物品组ID并处理
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        market_group_ids = await get_all_market_group_ids(session)

        if not market_group_ids:
            logger.error("没有获取到任何市场物品组ID，程序退出")
            return
        
        # 异步处理物品组数据
        processed_count = await process_market_groups_async(session, market_group_ids)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    logger.info(f"所有任务完成！")
    logger.info(f"处理物品组数量: {processed_count}")
    logger.info(f"错误数量: {error_count}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    
    # 关闭全局数据库连接
    if db_conn is not None:
        db_conn.close()
        logger.info("数据库连接已关闭")

if __name__ == "__main__":
    # 修复Windows下事件循环关闭错误
    import platform
    if platform.system() == "Windows":
        # 在Windows上使用SelectorEventLoop替代默认的ProactorEventLoop
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    # 手动管理事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    finally:
        # 确保事件循环正确关闭
        loop.close()
