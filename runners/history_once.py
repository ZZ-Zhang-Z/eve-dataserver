"""历史采集单轮。

不直接调用采集器的 main()：它的外层 try/except 会吞掉异常并返回 0，
控制器无法区分「跑完了」和「全军覆没」。这里组合两个内部函数，并读取模块级
error_count 做一次粗略的成功判断。

采集中途还会先做一次「数据是否已刷新」的预检：ESI 的历史数据每天 11:05 UTC
生成一次，维护日可能推迟数小时。若当天还没刷新，返回 6 让控制器保留这个触发点，
由后续的整点保底重试接手——避免把「成功但拿到昨天的数据」当成完成。

依赖全部来自 EVEDataserver 内部（collectors/、paths.py、database_manager.py），
不再引用项目根目录的代码；但数据与 config.json 仍在项目根，位置不变。

退出码：
  0  正常
  6  今日数据尚未刷新（维护延迟），保留给后续触发点重试
  5  错误计数过高（超过 20% 的 type 失败，通常是网络或限流问题）
  1  未预期异常
"""
import asyncio
import os
import platform
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# EVEDataserver 根目录（本文件的上一级）
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "collectors"))
sys.path.insert(0, HERE)

import aiohttp  # noqa: E402
import jita_market_history_collector_async as collector  # noqa: E402

# 15216 个 type，允许个别物品下架导致的失败，但 20% 以上视为异常
ERROR_BUDGET = int(os.environ.get("EVE_HISTORY_ERROR_BUDGET", "3000"))

# 用一个长期存在的 type（Tritanium）探数据新鲜度，成本一次请求
PROBE_URL = "https://esi.evetech.net/markets/10000002/history?type_id=34"
EXIT_NOT_REFRESHED = 6


def freshness_from_header(raw, now=None):
    """纯函数：根据 Last-Modified 判断「今天」的历史数据是否已生成。

    时间统一换算到 UTC 比较；Last-Modified 的 UTC 日期 >= 今天即视为已刷新。
    与网络无关，便于单测。
    """
    if not raw:
        return False, "缺少 Last-Modified"
    try:
        stamp = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return False, f"无法解析 Last-Modified: {raw!r}"
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    stamp = stamp.astimezone(timezone.utc)

    now = now or datetime.now(timezone.utc)
    if stamp.date() >= now.date():
        return True, f"Last-Modified {stamp:%Y-%m-%d %H:%M} UTC（今日已刷新）"
    return False, f"Last-Modified {stamp:%Y-%m-%d %H:%M} UTC，今日尚未刷新"


async def check_freshness():
    """判断今天的历史数据是否已生成，返回 (fresh, detail)。

    依据响应的 Last-Modified：ESI 每天 11:05 UTC 刷新一次，正常情况下
    该时间戳的 UTC 日期就是当天。维护推迟时会停留在前一天。
    网络异常一律视为「不新鲜」，交给下一次触发重试。
    """
    try:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(headers=collector.HEADERS) as session:
            async with session.get(PROBE_URL, timeout=timeout) as resp:
                if resp.status != 200:
                    await resp.read()
                    return False, f"预检返回 HTTP {resp.status}"
                raw = resp.headers.get("Last-Modified")
                await resp.read()
    except Exception as exc:
        return False, f"预检请求失败：{exc}"

    return freshness_from_header(raw)


async def run_once():
    fresh, detail = await check_freshness()
    if not fresh:
        collector.logger.warning("历史数据尚未刷新，跳过本轮：%s", detail)
        return EXIT_NOT_REFRESHED
    collector.logger.info("数据新鲜度预检通过：%s", detail)

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
