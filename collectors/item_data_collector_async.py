# item_data_collector_async.py
# 异步获取EVE Online所有物品详细信息并保存到数据库的脚本
import asyncio
import aiohttp
import sqlite3
import logging
import time
import sys
import os
import random
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from database_manager import get_connection_by_table

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

# 异步配置
MAX_CONCURRENT_REQUESTS = 20  # 最大并发请求数

# 公开路由共享令牌桶（默认 12000/15m），按状态码计费
rate_limiter = TokenBucket()
BATCH_SIZE = 100  # 每批处理的物品数量
MAX_RETRIES = 3  # API请求的最大重试次数

# 错误计数
error_count = 0

async def init_database():
    """
    初始化数据库，创建表结构
    """
    # 获取物品数据库连接
    conn = get_connection_by_table('items')
    cursor = conn.cursor()
    
    # 设置SQLite为WAL模式以提高并发性能
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA synchronous=NORMAL;")
    cursor.execute("PRAGMA cache_size=10000;")
    
    # 创建物品表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS items (
            type_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            group_id INTEGER,
            market_group_id INTEGER,
            published BOOLEAN NOT NULL,
            mass REAL,
            volume REAL,
            capacity REAL,
            portion_size INTEGER,
            radius REAL,
            graphic_id INTEGER,
            icon_id INTEGER,
            packaged_volume REAL
        )
    ''')
    
    # 创建物品属性表（用于存储dogma_attributes）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id INTEGER NOT NULL,
            attribute_id INTEGER NOT NULL,
            value REAL NOT NULL,
            FOREIGN KEY (type_id) REFERENCES items (type_id)
        )
    ''')
    
    # 创建物品效果表（用于存储dogma_effects）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS item_effects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type_id INTEGER NOT NULL,
            effect_id INTEGER NOT NULL,
            is_default BOOLEAN NOT NULL,
            FOREIGN KEY (type_id) REFERENCES items (type_id)
        )
    ''')
    
    conn.commit()
    logger.info("数据库初始化完成")

async def get_all_item_type_ids(session):
    """
    获取所有物品类型ID
    通过分页API获取所有物品类型ID，直到返回404错误表示没有更多数据
    """
    global error_count
    all_item_ids = []
    page = 1
    
    while True:
        url = f"{BASE_URL}/universe/types?page={page}"
        try:
            await rate_limiter.consume()
            async with session.get(url) as response:
                await rate_limiter.on_response(response.status, response.headers)
                if response.status == 200:
                    item_ids = await response.json()
                    all_item_ids.extend(item_ids)
                    logger.info(f"获取第 {page} 页物品类型ID，共 {len(item_ids)} 个，累计 {len(all_item_ids)} 个")
                    page += 1
                    
                    # 避免请求过快，添加小延迟
                    await asyncio.sleep(0.1)
                elif response.status == 404:
                    logger.info(f"所有物品类型ID获取完成，共 {len(all_item_ids)} 个")
                    break
                else:
                    logger.error(f"获取物品类型ID失败，状态码: {response.status}，响应: {await response.text()}")
                    error_count += 1
                    break
        except Exception as e:
            logger.error(f"获取物品类型ID时发生异常: {str(e)}")
            error_count += 1
            # 发生异常时重试
            await asyncio.sleep(1)
    
    return all_item_ids

async def get_item_details(session, type_id, semaphore):
    """
    获取单个物品的详细信息
    参数:
        session: aiohttp会话对象
        type_id: 物品类型ID
        semaphore: 信号量对象，用于限制并发请求
    返回:
        物品详细信息的字典
    """
    global error_count
    url = f"{BASE_URL}/universe/types/{type_id}"
    
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
                        item_details = await response.json()
                        if http_cache:
                            http_cache.save(url, response.headers.get('ETag'), response.headers.get('Last-Modified'))
                        logger.debug(f"获取物品ID {type_id} 的详细信息成功")
                        return item_details
                    elif response.status == 304:
                        # 命中缓存，数据未变更，跳过解析/入库
                        logger.debug(f"物品ID {type_id} 数据未变更(304)")
                        return None
                    elif response.status == 404:
                        logger.warning(f"物品ID {type_id} 不存在")
                        return None
                    elif response.status == 420 or response.status == 429:  # 速率限制
                        error_rate_tracker.record()
                        _, extra_delay = error_rate_tracker.get_delay()
                        if retry < MAX_RETRIES:
                            wait_time = compute_backoff(retry, status_code=response.status,
                                                        retry_after=response.headers.get('Retry-After'),
                                                        extra_delay=extra_delay)
                            logger.warning(f"获取物品ID {type_id} 时遇到速率限制(状态码 {response.status})，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取物品ID {type_id} 详细信息失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return None
                    else:
                        error_rate_tracker.record()
                        _, extra_delay = error_rate_tracker.get_delay()
                        if retry < MAX_RETRIES:
                            wait_time = compute_backoff(retry, status_code=response.status,
                                                        retry_after=response.headers.get('Retry-After'),
                                                        extra_delay=extra_delay)
                            logger.warning(f"获取物品ID {type_id} 失败，状态码: {response.status}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            logger.error(f"获取物品ID {type_id} 详细信息失败，状态码: {response.status}，已达到最大重试次数")
                            error_count += 1
                            return None
        except aiohttp.ClientError as e:
            if retry < MAX_RETRIES:
                wait_time = 2 ** retry + random.uniform(0, 1)
                logger.warning(f"获取物品ID {type_id} 时发生网络异常: {str(e)}，{wait_time:.2f}秒后重试 ({retry+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
                continue
            else:
                logger.error(f"获取物品ID {type_id} 详细信息时发生网络异常: {str(e)}，已达到最大重试次数")
                error_count += 1
                return None
        except Exception as e:
            logger.error(f"获取物品ID {type_id} 详细信息时发生意外异常: {str(e)}")
            error_count += 1
            return None

async def batch_write_to_database(batch_items):
    """
    批量写入数据库函数
    参数:
        batch_items: 物品详细信息列表
    """
    global error_count
    
    if not batch_items:
        return
    
    try:
        # 获取物品数据库连接
        conn = get_connection_by_table('items')
        cursor = conn.cursor()
        
        # 批量写入物品基本信息
        items_sql = '''
            INSERT OR REPLACE INTO items 
            (type_id, name, description, group_id, market_group_id, published, 
             mass, volume, capacity, portion_size, radius, graphic_id, icon_id, packaged_volume)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        items_data = [(item.get('type_id'), item.get('name'), item.get('description'),
                      item.get('group_id'), item.get('market_group_id'), item.get('published', False),
                      item.get('mass'), item.get('volume'), item.get('capacity'),
                      item.get('portion_size'), item.get('radius'), item.get('graphic_id'),
                      item.get('icon_id'), item.get('packaged_volume')) for item in batch_items]
        cursor.executemany(items_sql, items_data)
        
        # 收集并批量写入物品属性
        batch_attributes = []
        for item in batch_items:
            if 'dogma_attributes' in item:
                for attr in item['dogma_attributes']:
                    batch_attributes.append((
                        item['type_id'],
                        attr.get('attribute_id'),
                        attr.get('value')
                    ))
        
        if batch_attributes:
            attributes_sql = '''
                INSERT OR REPLACE INTO item_attributes 
                (type_id, attribute_id, value)
                VALUES (?, ?, ?)
            '''
            cursor.executemany(attributes_sql, batch_attributes)
        
        # 收集并批量写入物品效果
        batch_effects = []
        for item in batch_items:
            if 'dogma_effects' in item:
                for effect in item['dogma_effects']:
                    batch_effects.append((
                        item['type_id'],
                        effect.get('effect_id'),
                        effect.get('is_default', False)
                    ))
        
        if batch_effects:
            effects_sql = '''
                INSERT OR REPLACE INTO item_effects 
                (type_id, effect_id, is_default)
                VALUES (?, ?, ?)
            '''
            cursor.executemany(effects_sql, batch_effects)
        
        conn.commit()
        
        logger.info(f"批量写入完成，共写入 {len(batch_items)} 个物品")
        
    except Exception as e:
        logger.error(f"批量写入数据库时发生异常: {str(e)}")
        error_count += len(batch_items)

async def process_item_batch(session, item_ids):
    """
    处理一批物品
    参数:
        session: aiohttp会话对象
        item_ids: 物品类型ID列表
    返回:
        成功处理的物品数量
    """
    # 创建信号量限制并发请求
    sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    
    tasks = []
    for type_id in item_ids:
        task = asyncio.create_task(get_item_details(session, type_id, sem))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 过滤掉None结果和异常
    valid_results = [result for result in results if isinstance(result, dict) and result is not None]
    
    # 批量写入数据库
    if valid_results:
        await batch_write_to_database(valid_results)
    
    return len(valid_results)

async def process_items_async(session, item_ids):
    """
    异步处理物品列表
    参数:
        session: aiohttp会话对象
        item_ids: 物品类型ID列表
    """
    global error_count
    total_items = len(item_ids)
    processed_items = 0
    
    logger.info(f"开始异步处理 {total_items} 个物品")
    
    # 记录开始处理的时间
    start_time = time.time()
    
    # 将物品ID列表分割成批次
    for i in range(0, total_items, BATCH_SIZE):
        batch_item_ids = item_ids[i:i+BATCH_SIZE]
        
        # 处理当前批次
        result = await process_item_batch(session, batch_item_ids)
        processed_items += result
        
        logger.info(f"已处理 {processed_items}/{total_items} 个物品")
        
        # 每处理1000个物品显示预计剩余时间
        if processed_items % 1000 == 0 and processed_items > 0:
            elapsed_time = time.time() - start_time
            items_per_second = processed_items / elapsed_time
            remaining_items = total_items - processed_items
            estimated_remaining_time = remaining_items / items_per_second if items_per_second > 0 else 0
            
            # 格式化时间为小时、分钟、秒
            hours, rem = divmod(estimated_remaining_time, 3600)
            minutes, seconds = divmod(rem, 60)
            
            logger.info(f"预计剩余时间: {int(hours)}小时 {int(minutes)}分钟 {int(seconds)}秒")
        
        # 避免请求过快
        await asyncio.sleep(0.5)
    
    logger.info(f"异步处理完成，共处理 {processed_items} 个物品，失败 {total_items - processed_items} 个")
    return processed_items

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
    
    # 异步获取所有物品类型ID并处理
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        item_ids = await get_all_item_type_ids(session)
    
        if not item_ids:
            logger.error("没有获取到任何物品类型ID，程序退出")
            return
        
        # 异步处理所有物品数据
        processed_count = await process_items_async(session, item_ids)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    logger.info(f"所有任务完成！")
    logger.info(f"处理物品数量: {processed_count}")
    logger.info(f"错误数量: {error_count}")
    logger.info(f"总耗时: {total_time:.2f} 秒")
    


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