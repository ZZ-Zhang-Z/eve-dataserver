# test_esi_behavior.py
# ESI 交互细节的离线回归测试（不联网）。
#
# 覆盖：
#   1. 历史采集遇到 404（该物品无历史）时仍记入本地错误窗口
#      —— 404 在 ESI 侧计入全局「100 个非 2xx/3xx / 60 秒」限制，
#         不记录的话本地限流器完全感知不到，可能打穿后连带订单采集 420
#   2. 200 正常响应不污染错误窗口
#   3. SDE 下载中断不留下 .part 半成品（最大约 100MB）
#
# 运行：.venv\Scripts\python.exe tests\test_esi_behavior.py
import asyncio
import logging
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'collectors'))
sys.path.insert(0, os.path.dirname(HERE))

import jita_market_history_collector_async as m  # noqa: E402

logging.getLogger('jita_market_history_collector_async').setLevel(logging.CRITICAL)


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status = status
        self._payload = payload if payload is not None else []
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self._payload


class FakeSession:
    def __init__(self, *responses):
        self._responses = list(responses)

    def get(self, url):
        return self._responses.pop(0)


def check(label, cond):
    print(('  PASS  ' if cond else '  FAIL  ') + label)
    return bool(cond)


def test_sde_part_cleanup():
    """SDE 下载失败（无论是启动时有残留还是中途断开）都不留 .part。"""
    import item_sde_collector as sde

    tmpdir = tempfile.mkdtemp(prefix='sde_part_test_')
    sde.SDE_CACHE_DIR = tmpdir
    sde.SDE_ZIP_PATH = os.path.join(tmpdir, 'sde_latest.zip')
    sde.SDE_META_PATH = os.path.join(tmpdir, 'meta.json')
    part = sde.SDE_ZIP_PATH + '.part'
    original = sde.urllib.request.urlopen

    # 场景 1：上次崩溃留下的残留，应在开始下载前被清掉
    with open(part, 'wb') as handle:
        handle.write(b'x' * 4096)
    sde.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError('offline'))
    try:
        sde._download_sde()
    except OSError:
        pass
    finally:
        sde.urllib.request.urlopen = original
    ok = check('启动时清理了残留 .part', not os.path.exists(part))

    # 场景 2：下载中途断开，半成品必须删除而不是留 100MB 在盘上
    class BrokenResponse:
        headers = {'Content-Length': '1024', 'ETag': '"x"'}

        def __init__(self):
            self.calls = 0

        def read(self, _size):
            self.calls += 1
            if self.calls == 1:
                return b'y' * 512
            raise OSError('connection reset')

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    sde.urllib.request.urlopen = lambda *a, **k: BrokenResponse()
    try:
        sde._download_sde()
    except OSError:
        pass
    finally:
        sde.urllib.request.urlopen = original
    ok &= check('下载中断后删除了 .part', not os.path.exists(part))
    ok &= check('未生成半成品 zip', not os.path.exists(sde.SDE_ZIP_PATH))

    return ok


async def main():
    ok = True

    # ---------------------------------------------------------------- 1
    print('[1] 历史 404：返回空列表，但计入错误窗口')
    before = len(m.error_rate_tracker.window)
    result = await m.get_market_history(FakeSession(FakeResponse(404)), 34)
    after = len(m.error_rate_tracker.window)
    ok &= check('404 返回空列表（不抛异常）', result == [])
    ok &= check(f'错误窗口 +1（{before} -> {after}）', after == before + 1)

    # ---------------------------------------------------------------- 2
    print('[2] 历史 200：正常入账，不污染错误窗口')
    before = len(m.error_rate_tracker.window)
    payload = [{'date': '2026-11-25', 'average': 5.0, 'highest': 5.0,
                'lowest': 5.0, 'order_count': 10, 'volume': 100}]
    result = await m.get_market_history(
        FakeSession(FakeResponse(200, payload, {'Last-Modified': 'Wed, 25 Nov 2026 11:05:58 GMT'})), 34)
    after = len(m.error_rate_tracker.window)
    ok &= check('返回原始历史记录', result == payload)
    ok &= check('错误窗口不变', after == before)

    # ---------------------------------------------------------------- 3
    print('[3] SDE 下载中断：不留下 .part 半成品')
    ok &= test_sde_part_cleanup()

    print()
    print('结果：' + ('全部通过' if ok else '存在失败项'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
