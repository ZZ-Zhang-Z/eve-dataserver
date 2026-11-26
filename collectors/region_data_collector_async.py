# region_data_collector_async.py
# 异步获取EVE Online区域数据并保存到数据库的脚本
import asyncio
import aiohttp
import sqlite3
import logging
import time
import sys
import os
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
MAX_RETRIES = 3  # API请求的最大重试次数

async def get_region_ids(session):
    """获取所有星域ID列表"""
    url = f"{BASE_URL}/universe/regions"
    try:
        await rate_limiter.consume()
        async with session.get(url) as response:
            await rate_limiter.on_response(response.status, response.headers)
            if response.status == 200:
                region_ids = await response.json()
                logger.info(f"成功获取星域ID列表，共{len(region_ids)}个星域")
                return region_ids
            else:
                logger.error(f"获取星域ID列表失败，状态码: {response.status}")
                return []
    except Exception as e:
        logger.error(f"获取星域ID列表时发生异常: {e}")
        return []

async def get_region_info(session, region_id):
    """获取单个星域的详细信息（支持 ETag 条件请求）"""
    url = f"{BASE_URL}/universe/regions/{region_id}"
    for retry in range(MAX_RETRIES):
        try:
            req_headers = http_cache.conditional_headers(url) if http_cache else {}
            await rate_limiter.consume()
            async with session.get(url, headers=req_headers) as response:
                await rate_limiter.on_response(response.status, response.headers)
                if response.status == 200:
                    region_info = await response.json()
                    if http_cache:
                        http_cache.save(url, response.headers.get('ETag'), response.headers.get('Last-Modified'))
                    logger.info(f"成功获取星域ID={region_id}的信息: {region_info.get('name')}")
                    return region_info
                elif response.status == 304:
                    # 命中缓存，数据未变更，跳过解析/入库
                    logger.debug(f"星域ID={region_id} 数据未变更(304)")
                    return None
                elif response.status == 420 or response.status == 429:
                    error_rate_tracker.record()
                    _, extra_delay = error_rate_tracker.get_delay()
                    if retry < MAX_RETRIES - 1:
                        wait_time = compute_backoff(retry, status_code=response.status,
                                                    retry_after=response.headers.get('Retry-After'),
                                                    extra_delay=extra_delay)
                        logger.warning(f"获取星域ID={region_id}时遇到速率限制(状态码 {response.status})，{wait_time:.2f}秒后重试 (重试 {retry+1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"获取星域ID={region_id}的信息失败，状态码: {response.status}")
                        return None
                elif response.status in (504, 503, 502, 500) and retry < MAX_RETRIES - 1:
                    error_rate_tracker.record()
                    _, extra_delay = error_rate_tracker.get_delay()
                    wait_time = compute_backoff(retry, status_code=response.status, extra_delay=extra_delay)
                    logger.warning(f"获取星域ID={region_id}失败，状态码: {response.status}, 将在{wait_time:.2f}秒后重试 (重试 {retry+1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"获取星域ID={region_id}的信息失败，状态码: {response.status}")
                    return None
        except Exception as e:
            error_rate_tracker.record()
            _, extra_delay = error_rate_tracker.get_delay()
            if retry < MAX_RETRIES - 1:
                wait_time = compute_backoff(retry, extra_delay=extra_delay)
                logger.warning(f"获取星域ID={region_id}时发生异常: {e}, 将在{wait_time:.2f}秒后重试 (重试 {retry+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"获取星域ID={region_id}的信息时发生异常: {e}")
                return None
    return None

async def fetch_all_region_data():
    """获取所有星域的ID和详细信息"""
    async with aiohttp.ClientSession(headers=HEADERS, trust_env=False) as session:
        # 获取所有星域ID
        region_ids = await get_region_ids(session)
        if not region_ids:
            logger.error("没有获取到任何星域ID，程序终止")
            return []
        
        # 创建信号量限制并发请求数
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        async def fetch_with_semaphore(region_id):
            async with semaphore:
                return await get_region_info(session, region_id)
        
        # 并发获取所有星域的详细信息
        tasks = [fetch_with_semaphore(region_id) for region_id in region_ids]
        region_infos = await asyncio.gather(*tasks)
        
        # 过滤掉获取失败的星域信息
        valid_region_infos = [info for info in region_infos if info is not None]
        logger.info(f"成功获取{len(valid_region_infos)}个星域的详细信息")
        
        return valid_region_infos

def init_database():
    """初始化数据库表结构"""
    try:
        conn = get_connection_by_table('regions')
        cursor = conn.cursor()
        
        # 创建regions表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS regions (
            region_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # 创建region_constellations表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS region_constellations (
            region_id INTEGER,
            constellation_id INTEGER,
            PRIMARY KEY (region_id, constellation_id),
            FOREIGN KEY (region_id) REFERENCES regions (region_id)
        )
        ''')
        
        conn.commit()
        logger.info("数据库表结构初始化成功")
    except Exception as e:
        logger.error(f"初始化数据库表结构时发生异常: {e}")
        if conn:
            conn.rollback()

def save_region_data(region_infos):
    """将星域数据保存到数据库"""
    try:
        conn = get_connection_by_table('regions')
        cursor = conn.cursor()
        
        for region_info in region_infos:
            # 更新或插入regions表
            cursor.execute('''
            INSERT OR REPLACE INTO regions (region_id, name, description, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (region_info['region_id'], region_info['name'], region_info.get('description', '')))
            
            # 删除旧的星座关联
            cursor.execute('DELETE FROM region_constellations WHERE region_id = ?', (region_info['region_id'],))
            
            # 插入新的星座关联
            for constellation_id in region_info.get('constellations', []):
                cursor.execute('''
                INSERT INTO region_constellations (region_id, constellation_id)
                VALUES (?, ?)
                ''', (region_info['region_id'], constellation_id))
        
        conn.commit()
        logger.info(f"成功将{len(region_infos)}个星域数据保存到数据库")
    except Exception as e:
        logger.error(f"保存星域数据到数据库时发生异常: {e}")
        if conn:
            conn.rollback()

def verify_data():
    """验证数据库中的星域数据"""
    try:
        conn = get_connection_by_table('regions')
        cursor = conn.cursor()
        
        # 统计星域数量
        cursor.execute('SELECT COUNT(*) FROM regions')
        region_count = cursor.fetchone()[0]
        logger.info(f"数据库中共有{region_count}个星域记录")
        
        # 统计星座关联数量
        cursor.execute('SELECT COUNT(*) FROM region_constellations')
        constellation_count = cursor.fetchone()[0]
        logger.info(f"数据库中共有{constellation_count}个星座关联记录")
        
        # 查询前5个星域的信息
        cursor.execute('SELECT region_id, name, description FROM regions ORDER BY region_id LIMIT 5')
        sample_regions = cursor.fetchall()
        logger.info("前5个星域的示例数据:")
        for region in sample_regions:
            logger.info(f"region_id: {region[0]}, name: {region[1]}, description: {region[2][:100]}...")
        
    except Exception as e:
        logger.error(f"验证数据库数据时发生异常: {e}")

async def main():
    """主函数"""
    start_time = time.time()
    
    logger.info("开始获取星域数据...")
    
    # 初始化数据库
    init_database()

    # 初始化 ETag 条件请求缓存
    global http_cache
    http_cache = HttpCache()

    # 获取所有星域数据
    region_infos = await fetch_all_region_data()
    
    if region_infos:
        # 保存数据到数据库
        save_region_data(region_infos)
        
        # 验证数据
        verify_data()
    
    end_time = time.time()
    logger.info(f"星域数据获取和保存完成，总耗时: {end_time - start_time:.2f}秒")

if __name__ == "__main__":
    asyncio.run(main())