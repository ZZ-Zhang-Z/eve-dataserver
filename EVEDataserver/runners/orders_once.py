"""订单采集单轮：抓一份完整快照、写库、退出。

作为独立子进程运行，让控制器能在每轮结束后彻底回收内存 —— 418 页聚合时
峰值可达 284MB，进程退出是最彻底的回收方式。

退出码：
  0  成功写入
  2  快照不完整（已保留上一份数据，属预期内的保护性跳过）
  3  未取到任何订单
  4  写库被拒（规模骤降或重复 order_id）
  1  未预期异常
"""
import asyncio
import os
import platform
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "collectors"))
sys.path.insert(0, ROOT)

import aiohttp  # noqa: E402
import jita_market_orders_collector_async as collector  # noqa: E402


async def run_once():
    retention = int(os.environ.get("EVE_RETENTION_HOURS", "24"))

    # 采集器若已提供流式单轮入口，优先使用：内存峰值只与并发数相关
    streaming = getattr(collector, "run_tracking_once", None)
    if callable(streaming):
        return await streaming(retention_hours=retention)

    await collector.init_database()
    await collector.init_tracking_schema()

    async with aiohttp.ClientSession(headers=collector.HEADERS) as session:
        try:
            orders = await collector.get_all_market_orders(session, "all")
        except collector.IncompleteSnapshotError as exc:
            collector.logger.error("本轮快照不完整，保留上一份数据：%s", exc)
            return 2

        if not orders:
            collector.logger.warning("未获取到任何订单，跳过写库")
            return 3

        written = await collector.process_orders_tracking(
            orders, int(time.time()), retention)
        return 0 if written else 4


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(run_once()))
