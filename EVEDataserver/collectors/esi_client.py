# esi_client.py
# ESI 采集公共模块：统一请求头、按状态码计费的令牌桶、退避策略、
# 错误率窗口、条件请求（ETag）缓存、分页 last-modified 一致性校验。
# 依据 EVE ESI 官方文档（best-practices / rate-limiting / pagination）。
import asyncio
import json
import logging
import os
import random
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))  # 自包含副本：置顶以优先于项目根的同名模块

import paths

try:
    from database_manager import get_connection_by_table
except Exception:  # 数据库层不可用时仍允许令牌桶/退避等纯逻辑使用
    get_connection_by_table = None

logger = logging.getLogger(__name__)

ESI_BASE_URL = "https://esi.evetech.net"

# 规范 User-Agent：官方建议携带 应用名/版本 + 联系邮箱（或仓库地址）。
# 实际取值可由 config.json 的 user_agent 字段覆盖（按 mtime 热读取，见 get_user_agent）。
USER_AGENT = "EveHelperMarketCollector/1.0 (zzk.linyi@gmail.com)"

# X-Compatibility-Date：默认值（config.json 缺失/非法时回退）
COMPATIBILITY_DATE_DEFAULT = "2026-06-09"
CONFIG_PATH = os.path.join(paths.BASE_DIR, 'config.json')
_DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
# config.json 读取缓存：按 mtime 失效，读取结果同时服务于 compatibility_date 与 user_agent
_config_cache = {'mtime': None, 'data': None}


def _load_config():
    """读取项目根目录 config.json（按 mtime 缓存）；缺失或非法时返回空 dict。

    文件被修改后下一次请求即生效，无需重启进程。
    """
    try:
        mtime = os.path.getmtime(CONFIG_PATH)
    except OSError:
        _config_cache['mtime'] = None
        _config_cache['data'] = None
        return {}
    if _config_cache['mtime'] == mtime and _config_cache['data'] is not None:
        return _config_cache['data']
    data = {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data = loaded
    except Exception as exc:
        logger.warning("读取 config.json 失败: %s，回退为默认值", exc)
    _config_cache['mtime'] = mtime
    _config_cache['data'] = data
    return data


def _load_compatibility_date():
    """从 config.json 读取 compatibility_date；缺失/非法时回退到默认值并告警。"""
    raw = _load_config().get('compatibility_date')
    value = str(raw).strip() if raw is not None else ''
    if not value:
        return COMPATIBILITY_DATE_DEFAULT
    if not _DATE_RE.match(value):
        logger.warning("config.json 的 compatibility_date 格式应为 YYYY-MM-DD: %r，回退为 %s",
                       value, COMPATIBILITY_DATE_DEFAULT)
        return COMPATIBILITY_DATE_DEFAULT
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        logger.warning("config.json 的 compatibility_date 不是有效日期: %r，回退为 %s",
                       value, COMPATIBILITY_DATE_DEFAULT)
        return COMPATIBILITY_DATE_DEFAULT
    return value


def get_user_agent():
    """返回当前生效的 ESI User-Agent：优先 config.json 的 user_agent，否则用内置默认值。"""
    raw = _load_config().get('user_agent')
    value = str(raw).strip() if raw is not None else ''
    return value or USER_AGENT


def default_headers(accept_language="zh"):
    """返回统一的 ESI 请求头（含 User-Agent 与版本化头）。"""
    return {
        "User-Agent": get_user_agent(),
        "X-Compatibility-Date": _load_compatibility_date(),
        "Accept": "application/json",
        "Accept-Language": accept_language,
    }


# 默认令牌桶参数：每 15 分钟 12000 令牌（约 13.33 令牌/秒 ≈ 800 请求/分钟）
DEFAULT_BUCKET_CAPACITY = 12000
DEFAULT_BUCKET_PERIOD = 15 * 60

# 低水位：当 X-Ratelimit-Remaining 低于阈值时，对后续请求做额外延迟
LOW_WATERMARK_TOKENS = 100
LOW_WATERMARK_DELAY = 1.0

# 错误率窗口默认值（比官方 100/分钟更保守）
DEFAULT_ERROR_WINDOW_SECONDS = 60
DEFAULT_ERROR_LIMIT = 50
DEFAULT_ERROR_THRESHOLD = 30


def token_cost(status_code):
    """按官方计费规则返回一次请求的令牌消耗量。

    2xx=2、3xx=1、4xx=5（429 不计费）、5xx=0。
    """
    if 200 <= status_code < 300:
        return 2
    if 300 <= status_code < 400:
        return 1
    if status_code == 429:
        return 0
    if 400 <= status_code < 500:
        return 5
    if 500 <= status_code < 600:
        return 0
    return 1


def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def compute_backoff(retry, status_code=None, retry_after=None, extra_delay=0.0):
    """计算退避等待秒数。

    - 420：最低 60s + 抖动
    - 429：优先使用 Retry-After，回退指数退避 + 抖动
    - 其它 4xx：指数退避 * 2
    - 504：指数退避 * 3
    - 其它：指数退避 + 抖动
    最后统一叠加错误率控制给出的 extra_delay。
    """
    if status_code == 420:
        wait = 60 + random.uniform(0, 10)
    elif retry_after is not None and str(retry_after).strip() != "":
        parsed = None
        try:
            parsed = float(retry_after)
        except (TypeError, ValueError):
            parsed = None
        if parsed is not None:
            wait = max(0.0, parsed) + random.uniform(0, 1)
        else:
            wait = 2 ** retry + random.uniform(0, 1)
    elif status_code == 504:
        wait = (2 ** retry + random.uniform(0, 1)) * 3
    elif status_code is not None and 400 <= status_code < 500 and status_code != 429:
        wait = (2 ** retry + random.uniform(0, 1)) * 2
    else:
        wait = 2 ** retry + random.uniform(0, 1)
    return wait + extra_delay


class TokenBucket:
    """按官方计费的令牌桶。

    请求前 `await consume()` 预扣 1 个令牌，收到响应后 `await settle(status)`
    按状态码补扣差额（例如 2xx 需再补 1 个，5xx 退回 1 个）。
    """

    def __init__(self, capacity=DEFAULT_BUCKET_CAPACITY, period=DEFAULT_BUCKET_PERIOD, refill_rate=None):
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        if refill_rate is not None:
            self.refill_rate = float(refill_rate)
        else:
            self.refill_rate = float(capacity) / float(period) if period else float(capacity)
        self.last_refill = time.time()
        self.lock = asyncio.Lock()

    def _refill_locked(self):
        now = time.time()
        elapsed = now - self.last_refill
        if elapsed > 0:
            self.tokens = min(self.tokens + elapsed * self.refill_rate, self.capacity)
            self.last_refill = now

    async def consume(self, amount=1):
        """预扣 amount 个令牌，不足则等待补桶。"""
        async with self.lock:
            self._refill_locked()
            while self.tokens < amount:
                await asyncio.sleep(0.1)
                self._refill_locked()
            self.tokens -= amount

    async def settle(self, status_code, reserved=1):
        """按响应状态码补扣/退还令牌差额。"""
        delta = reserved - token_cost(status_code)
        async with self.lock:
            self._refill_locked()
            self.tokens = max(0.0, min(self.tokens + delta, self.capacity))

    def update_capacity_from_header(self, limit_header):
        """可选：依据 X-Ratelimit-Limit 动态校正桶容量。"""
        limit = _to_int(limit_header)
        if limit and limit > 0:
            self.capacity = float(limit)
            self.tokens = min(self.tokens, self.capacity)
            return True
        return False

    async def on_response(self, status_code, headers=None):
        """请求后统一结算：按状态码补扣令牌，并在剩余量偏低时额外降速。"""
        await self.settle(status_code)
        if headers is not None:
            self.update_capacity_from_header(headers.get('X-Ratelimit-Limit'))
            remaining = _to_int(headers.get('X-Ratelimit-Remaining'))
            if remaining is not None and remaining < LOW_WATERMARK_TOKENS:
                await asyncio.sleep(LOW_WATERMARK_DELAY)


class ErrorRateTracker:
    """错误率窗口：统计时间窗内非 2xx/3xx 数量并给出额外延迟。"""

    def __init__(self, window_seconds=DEFAULT_ERROR_WINDOW_SECONDS,
                 limit=DEFAULT_ERROR_LIMIT, threshold=DEFAULT_ERROR_THRESHOLD):
        self.window_seconds = window_seconds
        self.limit = limit
        self.threshold = threshold
        self.window = []

    def record(self):
        """登记一次错误（非 2xx/3xx）。"""
        self.window.append(time.time())

    def get_delay(self):
        """清理过期时间戳，返回 (窗口内错误数, 推荐额外延迟秒)。"""
        now = time.time()
        self.window = [t for t in self.window if now - t < self.window_seconds]
        count = len(self.window)
        if count < self.threshold:
            return count, 0.0
        if count < self.limit:
            factor = (count - self.threshold) / (self.limit - self.threshold)
            return count, 0.1 + factor * 0.5
        return count, 1.0 + random.uniform(0, 0.5)

    def trim(self, keep_ratio=0.8):
        """遇到 420 时保留部分记录以更快恢复。"""
        keep = int(self.limit * keep_ratio)
        if keep <= 0:
            self.window = []
        else:
            self.window = self.window[-keep:]


class RateLimitMonitor:
    """依据 X-Ratelimit-Remaining / X-Ratelimit-Limit 在低水位时主动降速。"""

    def __init__(self, low_watermark=0.1, medium_watermark=0.25):
        self.remaining = None
        self.limit = None
        self.low_watermark = low_watermark
        self.medium_watermark = medium_watermark

    def observe(self, headers):
        """更新剩余/上限，返回建议额外延迟秒（不阻塞）。"""
        rem = _to_int(headers.get('X-Ratelimit-Remaining'))
        lim = _to_int(headers.get('X-Ratelimit-Limit'))
        if rem is not None:
            self.remaining = rem
        if lim:
            self.limit = lim
        return self.delay()

    def delay(self):
        if self.remaining is None or not self.limit or self.limit <= 0:
            return 0.0
        ratio = self.remaining / self.limit
        if ratio < self.low_watermark:
            return 0.5
        if ratio < self.medium_watermark:
            return 0.2
        return 0.0


# 进程内共享的限流监控与错误率跟踪（各采集器脚本各自独立进程运行）
rate_limit_monitor = RateLimitMonitor()
error_rate_tracker = ErrorRateTracker()


class HttpCache:
    """基于 cache 库的 ETag / Last-Modified 条件请求缓存。"""

    def __init__(self, conn=None):
        if conn is None:
            if get_connection_by_table is None:
                raise RuntimeError("database_manager 不可用，无法初始化 HttpCache")
            conn = get_connection_by_table('http_cache')
        self.conn = conn
        self._ensure_table()

    def _ensure_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS http_cache (
                url TEXT PRIMARY KEY,
                etag TEXT,
                last_modified TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        self.conn.commit()

    def get(self, url):
        cursor = self.conn.cursor()
        cursor.execute('SELECT etag, last_modified FROM http_cache WHERE url = ?', (url,))
        row = cursor.fetchone()
        if not row:
            return None, None
        return row[0], row[1]

    def conditional_headers(self, url):
        """返回可用的条件请求头（无缓存则返回空 dict）。"""
        etag, _ = self.get(url)
        if etag:
            return {"If-None-Match": etag}
        return {}

    def save(self, url, etag, last_modified):
        if not etag and not last_modified:
            return
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO http_cache (url, etag, last_modified, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (url, etag, last_modified))
        self.conn.commit()


def check_pagination_consistency(first_last_modified, current_last_modified):
    """校验分页资源各页 last-modified 是否一致。

    返回 True 表示一致（或信息不足无法判定），False 表示不一致（可能跨代）。
    """
    if not first_last_modified or not current_last_modified:
        return True
    return first_last_modified == current_last_modified