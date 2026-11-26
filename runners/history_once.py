"""历史采集单轮。

不直接调用采集器的 main()：它的外层 try/except 会吞掉异常并返回 0，
控制器无法区分「跑完了」和「全军覆没」。这里组合两个内部函数，并读取模块级
error_count 做一次粗略的成功判断。

依赖全部来自 EVEDataserver 内部（collectors/、paths.py、database_manager.py），
不再引用项目根目录的代码；但数据与 config.json 仍在项目根，位置不变。

退出码：
  0  正常
  5  错误计数过高（超过 20% 的 type 失败，通常是网络或限流问题）
  1  未预期异常
"""
import asyncio
import os
import platform
import sys

# EVEDataserver 根目录（本文件的上一级）
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "collectors"))
sys.path.insert(0, HERE)

import jita_market_history_collector_async as collector  # noqa: E402

# 15216 个 type，允许个别物品下架导致的失败，但 20% 以上视为异常
ERROR_BUDGET = int(os.environ.get("EVE_HISTORY_ERROR_BUDGET", "3000"))


async def run_once():
    await collector.init_database()
    await collector.get_all_market_history()

    errors = getattr(collector, "error_count", 0)
    collector.logger.info("历史采集结束，累计错误计数 %s（预算 %s）", errors, ERROR_BUDGET)
    if errors > ERROR_BUDGET:
        collector.logger.error("错误计数超出预算，判定本轮失败")
        return 5
    return 0


if __name__ == "__main__":
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.exit(asyncio.run(run_once()))
