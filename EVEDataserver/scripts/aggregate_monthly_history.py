import sqlite3
import datetime
import logging
import sys
import os

# 将 EVEDataserver 根目录添加到 Python 搜索路径（本文件位于 EVEDataserver/scripts/）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))  # 自包含副本：置顶以优先于项目根的同名模块

from database_manager import get_connection_by_table

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 吉他市场配置
JITA_REGION_ID = 10000002


def init_aggregation_table():
    """
    初始化月度聚合表结构
    """
    conn = get_connection_by_table('market_history')
    cursor = conn.cursor()
    
    try:
        # 创建月度聚合表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS market_history_monthly (
                region_id INTEGER NOT NULL,
                type_id INTEGER NOT NULL,
                month TEXT NOT NULL,  -- YYYY-MM 格式
                avg_price REAL NOT NULL,
                max_price REAL NOT NULL,
                min_price REAL NOT NULL,
                total_orders INTEGER NOT NULL,
                total_volume INTEGER NOT NULL,
                PRIMARY KEY (region_id, type_id, month)
            )
        ''')
        
        # 创建索引以提高查询性能
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_market_history_monthly_type_month 
            ON market_history_monthly (type_id, month DESC)
        ''')
        
        conn.commit()
        logger.info("月度聚合表初始化成功")
    except sqlite3.Error as e:
        logger.error(f"初始化聚合表时出错: {str(e)}")
        conn.rollback()
        raise


def aggregate_old_data(months=1):
    """
    将指定月数之前的历史数据聚合为月度数据
    
    参数:
        months: 聚合月数阈值，默认1个月
    """
    conn = get_connection_by_table('market_history')
    conn.execute("PRAGMA journal_mode=WAL;")
    cursor = conn.cursor()
    
    try:
        # 计算聚合日期（1个月前的今天）
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=months*30)).strftime('%Y-%m-%d')
        logger.info(f"开始聚合{cutoff_date}之前的历史数据")
        
        # 聚合数据并插入到月度聚合表
        # 使用INSERT OR REPLACE处理可能的重复数据
        cursor.execute('''
            INSERT OR REPLACE INTO market_history_monthly (
                region_id, type_id, month, avg_price, max_price, min_price, total_orders, total_volume
            )
            SELECT 
                region_id,
                type_id,
                SUBSTR(date, 1, 7) AS month,  -- 提取YYYY-MM格式
                AVG(average) AS avg_price,
                MAX(highest) AS max_price,
                MIN(lowest) AS min_price,
                SUM(order_count) AS total_orders,
                SUM(volume) AS total_volume
            FROM market_history
            WHERE date < ? AND region_id = ?
            GROUP BY region_id, type_id, SUBSTR(date, 1, 7)
        ''', (cutoff_date, JITA_REGION_ID))
        
        aggregated_count = cursor.rowcount
        logger.info(f"成功聚合{aggregated_count}条月度数据")
        
        # 删除原表中已聚合的旧数据
        cursor.execute('''
            DELETE FROM market_history 
            WHERE date < ? AND region_id = ?
        ''', (cutoff_date, JITA_REGION_ID))
        
        deleted_count = cursor.rowcount
        logger.info(f"成功删除原表中{deleted_count}条已聚合的旧数据")
        
        conn.commit()
        
        # 压缩数据库以释放空间（需在事务外执行）
        conn.execute("VACUUM;")
        logger.info("数据库压缩完成")
        
        conn.commit()
        
        return {
            'aggregated_count': aggregated_count,
            'deleted_count': deleted_count,
            'cutoff_date': cutoff_date
        }
        
    except sqlite3.Error as e:
        logger.error(f"聚合数据时出错: {str(e)}")
        conn.rollback()
        raise


def verify_aggregation():
    """
    验证聚合结果
    """
    conn = get_connection_by_table('market_history')
    cursor = conn.cursor()
    
    try:
        # 查询聚合表中的记录数
        cursor.execute('SELECT COUNT(*) FROM market_history_monthly WHERE region_id = ?', (JITA_REGION_ID,))
        monthly_count = cursor.fetchone()[0]
        
        # 查询原表中剩余的记录数
        cursor.execute('SELECT COUNT(*) FROM market_history WHERE region_id = ?', (JITA_REGION_ID,))
        daily_count = cursor.fetchone()[0]
        
        # 查询原表中最新的日期
        cursor.execute('SELECT MAX(date) FROM market_history WHERE region_id = ?', (JITA_REGION_ID,))
        latest_date = cursor.fetchone()[0]
        
        logger.info(f"聚合表记录数: {monthly_count}")
        logger.info(f"原表剩余记录数: {daily_count}")
        logger.info(f"原表最新日期: {latest_date}")
        
        return {
            'monthly_count': monthly_count,
            'daily_count': daily_count,
            'latest_date': latest_date
        }
        
    except sqlite3.Error as e:
        logger.error(f"验证聚合结果时出错: {str(e)}")
        raise


if __name__ == "__main__":
    logger.info("开始执行月度数据聚合任务")
    
    # 初始化聚合表
    init_aggregation_table()
    
    # 聚合1个月以上的数据
    result = aggregate_old_data(months=1)
    
    # 验证聚合结果
    verify_result = verify_aggregation()
    
    logger.info("月度数据聚合任务完成")
    logger.info(f"聚合统计: 聚合{result['aggregated_count']}条月度数据, 删除原表{result['deleted_count']}条旧数据")
    logger.info(f"数据分布: 聚合表{verify_result['monthly_count']}条记录, 原表{verify_result['daily_count']}条记录")
