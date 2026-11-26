# system_data_collector_async.py
# 异步获取EVE Online系统数据并保存到数据库的脚本
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

async def get_system_ids(session):
    """获取所有恒星系ID列表"""
    url = f"{BASE_URL}/universe/systems"
    try:
        await rate_limiter.consume()
        async with session.get(url) as response:
            await rate_limiter.on_response(response.status, response.headers)
            if response.status == 200:
                system_ids = await response.json()
                logger.info(f"成功获取恒星系ID列表，共{len(system_ids)}个恒星系")
                return system_ids
            else:
                logger.error(f"获取恒星系ID列表失败，状态码: {response.status}")
                return []
    except Exception as e:
        logger.error(f"获取恒星系ID列表时发生异常: {e}")
        return []

async def get_system_info(session, system_id):
    """获取单个恒星系的详细信息（支持 ETag 条件请求）"""
    url = f"{BASE_URL}/universe/systems/{system_id}"
    for retry in range(MAX_RETRIES):
        try:
            req_headers = http_cache.conditional_headers(url) if http_cache else {}
            await rate_limiter.consume()
            async with session.get(url, headers=req_headers) as response:
                await rate_limiter.on_response(response.status, response.headers)
                if response.status == 200:
                    system_info = await response.json()
                    if http_cache:
                        http_cache.save(url, response.headers.get('ETag'), response.headers.get('Last-Modified'))
                    logger.info(f"成功获取恒星系ID={system_id}的信息: {system_info.get('name')}")
                    return system_info
                elif response.status == 304:
                    # 命中缓存，数据未变更，跳过解析/入库
                    logger.debug(f"恒星系ID={system_id} 数据未变更(304)")
                    return None
                elif response.status == 420 or response.status == 429:
                    error_rate_tracker.record()
                    _, extra_delay = error_rate_tracker.get_delay()
                    if retry < MAX_RETRIES - 1:
                        wait_time = compute_backoff(retry, status_code=response.status,
                                                    retry_after=response.headers.get('Retry-After'),
                                                    extra_delay=extra_delay)
                        logger.warning(f"获取恒星系ID={system_id}时遇到速率限制(状态码 {response.status})，{wait_time:.2f}秒后重试 (重试 {retry+1}/{MAX_RETRIES})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"获取恒星系ID={system_id}的信息失败，状态码: {response.status}")
                        return None
                elif response.status in (504, 503, 502, 500) and retry < MAX_RETRIES - 1:
                    error_rate_tracker.record()
                    _, extra_delay = error_rate_tracker.get_delay()
                    wait_time = compute_backoff(retry, status_code=response.status, extra_delay=extra_delay)
                    logger.warning(f"获取恒星系ID={system_id}失败，状态码: {response.status}, 将在{wait_time:.2f}秒后重试 (重试 {retry+1}/{MAX_RETRIES})")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"获取恒星系ID={system_id}的信息失败，状态码: {response.status}")
                    return None
        except Exception as e:
            error_rate_tracker.record()
            _, extra_delay = error_rate_tracker.get_delay()
            if retry < MAX_RETRIES - 1:
                wait_time = compute_backoff(retry, extra_delay=extra_delay)
                logger.warning(f"获取恒星系ID={system_id}时发生异常: {e}, 将在{wait_time:.2f}秒后重试 (重试 {retry+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"获取恒星系ID={system_id}的信息时发生异常: {e}")
                return None
    return None

async def fetch_all_system_data():
    """获取所有恒星系的ID和详细信息"""
    async with aiohttp.ClientSession(headers=HEADERS, trust_env=False) as session:
        # 获取所有恒星系ID
        system_ids = await get_system_ids(session)
        if not system_ids:
            logger.error("没有获取到任何恒星系ID，程序终止")
            return []
        
        # 创建信号量限制并发请求数
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
        
        async def fetch_with_semaphore(system_id):
            async with semaphore:
                return await get_system_info(session, system_id)
        
        # 并发获取所有恒星系的详细信息
        tasks = [fetch_with_semaphore(system_id) for system_id in system_ids]
        system_infos = await asyncio.gather(*tasks)
        
        # 过滤掉获取失败的恒星系信息
        valid_system_infos = [info for info in system_infos if info is not None]
        logger.info(f"成功获取{len(valid_system_infos)}个恒星系的详细信息")
        
        return valid_system_infos

def init_database():
    """初始化数据库表结构"""
    try:
        conn = get_connection_by_table('systems')
        cursor = conn.cursor()
        
        # 删除旧的systems表（如果存在），因为我们需要修改表结构
        cursor.execute('DROP TABLE IF EXISTS systems')
        
        # 创建新的systems表
        cursor.execute('''
        CREATE TABLE systems (
            system_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            constellation_id INTEGER,
            position_x REAL,
            position_y REAL,
            position_z REAL,
            security_status REAL,
            security_class TEXT,
            star_id INTEGER,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (constellation_id) REFERENCES constellations (constellation_id)
        )
        ''')
        
        conn.commit()
        logger.info("数据库表结构初始化成功")
    except Exception as e:
        logger.error(f"初始化数据库表结构时发生异常: {e}")
        if conn:
            conn.rollback()

def save_system_data(system_infos):
    """将恒星系数据保存到数据库"""
    try:
        conn = get_connection_by_table('systems')
        cursor = conn.cursor()
        
        for system_info in system_infos:
            # 获取位置信息
            position = system_info.get('position', {})
            position_x = position.get('x', 0.0)
            position_y = position.get('y', 0.0)
            position_z = position.get('z', 0.0)
            
            # 更新或插入systems表
            cursor.execute('''
            INSERT OR REPLACE INTO systems (system_id, name, constellation_id, position_x, position_y, position_z, 
                                           security_status, security_class, star_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (system_info['system_id'], system_info['name'], 
                  system_info['constellation_id'],
                  position_x, position_y, position_z,
                  system_info.get('security_status', 0.0),
                  system_info.get('security_class', None),
                  system_info.get('star_id', None)))
        
        conn.commit()
        logger.info(f"成功将{len(system_infos)}个恒星系数据保存到数据库")
    except Exception as e:
        logger.error(f"保存恒星系数据到数据库时发生异常: {e}")
        if conn:
            conn.rollback()

def verify_data():
    """验证数据库中的恒星系数据"""
    try:
        conn = get_connection_by_table('systems')
        cursor = conn.cursor()
        
        # 统计恒星系数量
        cursor.execute('SELECT COUNT(*) FROM systems')
        system_count = cursor.fetchone()[0]
        logger.info(f"数据库中共有{system_count}个恒星系记录")
        
        # 查询前5个恒星系的信息
        cursor.execute('SELECT system_id, name, constellation_id, security_status FROM systems ORDER BY system_id LIMIT 5')
        sample_systems = cursor.fetchall()
        logger.info("前5个恒星系的示例数据:")
        for system in sample_systems:
            logger.info(f"system_id: {system[0]}, name: {system[1]}, constellation_id: {system[2]}, security_status: {system[3]}")
        
    except Exception as e:
        logger.error(f"验证数据库数据时发生异常: {e}")

async def main():
    """主函数"""
    start_time = time.time()
    
    logger.info("开始获取恒星系数据...")
    
    # 初始化数据库
    init_database()

    # 初始化 ETag 条件请求缓存
    global http_cache
    http_cache = HttpCache()

    # 获取所有恒星系数据
    system_infos = await fetch_all_system_data()
    
    if system_infos:
        # 保存数据到数据库
        save_system_data(system_infos)
        
        # 验证数据
        verify_data()
    
    end_time = time.time()
    logger.info(f"恒星系数据获取和保存完成，总耗时: {end_time - start_time:.2f}秒")

if __name__ == "__main__":
    # 在Windows环境下解决事件循环关闭的警告
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    asyncio.run(main())