"""执行器插件：决定一个任务怎么跑。

内置两种：
- subprocess：起子进程（采集器用这个，进程退出回收内存最彻底）
- inline：在当前进程调用一个 Python 函数（适合毫秒级的轻量维护任务）

新增执行方式的模板（例如 HTTP 回调、Docker 容器）：

    @register_executor("docker")
    class DockerExecutor:
        def __init__(self, spec, cfg):
            self.image = spec["image"]
        def run(self, ctx) -> TaskResult:
            ...
"""
import asyncio
import importlib
import inspect
import os
import signal
import subprocess
import sys
import time

import monitor
from core.context import TaskResult
from core.registry import register_executor


def _resolve(root, path):
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(root, path))


@register_executor("subprocess")
class SubprocessExecutor:
    """在独立子进程中执行，附带 RSS 采样、超时与进程组清理。

    spec 支持两种写法：
        {"command": ["{python}", "-u", "runners/x.py"]}
        {"runner": "EVEDataserver/runners/orders_once.py"}  # 等价于 {python} -u <path>
    {python} 会替换为配置里的解释器（缺省用当前解释器，即 venv 里的那个）。
    """

    def __init__(self, spec, cfg):
        self.spec = spec or {}
        self.cfg = cfg or {}
        self.root = self.cfg.get("_root") or os.getcwd()

    def _command(self):
        python = str(self.cfg.get("python") or sys.executable)
        raw = self.spec.get("command")
        if raw:
            return [str(item).replace("{python}", python) for item in raw]
        path = self.spec.get("runner") or self.spec.get("script")
        if not path:
            raise ValueError("subprocess 执行器需要 command，或 runner / script")
        return [python, "-u", _resolve(self.root, path)]

    def run(self, ctx) -> TaskResult:
        command = self._command()
        timeout = int(ctx.task.timeout_seconds or 600)
        log_dir = self.cfg.get("task_log_dir") or os.path.join(self.root, "logs", "collectors")
        log_dir = _resolve(self.root, log_dir)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, f"{ctx.task.name}.log")

        env = os.environ.copy()
        env.update(ctx.task.env)
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("TZ", self.cfg.get("timezone", "Asia/Shanghai"))

        start = time.time()
        peak_rss = 0.0
        with open(log_path, "a", encoding="utf-8") as log_file:
            log_file.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 {ctx.task.name} "
                           f"| {' '.join(command)} =====\n")
            log_file.flush()
            try:
                proc = subprocess.Popen(
                    command, cwd=self.root, env=env, stdout=log_file,
                    stderr=subprocess.STDOUT, start_new_session=(os.name != "nt"))
            except OSError as exc:
                log_file.write(f"===== 启动失败：{exc} =====\n")
                return TaskResult(exit_code=-1, duration=time.time() - start,
                                  message=f"启动失败：{exc}")

            code = None
            reason = ""
            while True:
                try:
                    code = proc.wait(timeout=1)
                    break
                except subprocess.TimeoutExpired:
                    pass
                rss = monitor.read_rss_mb(proc.pid)
                if rss is not None:
                    peak_rss = max(peak_rss, rss)
                if time.time() - start > timeout:
                    reason = f"超时 {timeout}s"
                    _terminate(proc)
                    code = -9
                    break
                if ctx.stop_event.is_set():
                    reason = "控制器停止"
                    _terminate(proc)
                    code = -15
                    break

            duration = time.time() - start
            log_file.write(f"===== 结束 {ctx.task.name} exit={code} 用时 {duration:.1f}s "
                           f"峰值RSS={peak_rss:.0f}MB")
            if reason:
                log_file.write(f" | {reason}")
            log_file.write(" =====\n")

        return TaskResult(exit_code=code, duration=duration,
                          peak_rss_mb=peak_rss, message=reason)


@register_executor("inline")
class InlineExecutor:
    """在当前进程内调用函数。只建议用于极轻量的维护逻辑。

    spec:
        {"module": "plugins.tasks.cleanup", "function": "run", "kwargs": {...},
         "pass_context": true}

    pass_context=True 时函数签名为 fn(ctx=..., **kwargs)，否则 fn(**kwargs)。
    """

    def __init__(self, spec, cfg):
        self.spec = spec or {}
        self.cfg = cfg or {}
        if not self.spec.get("module") or not self.spec.get("function"):
            raise ValueError("inline 执行器需要 module 与 function")
        self.kwargs = self.spec.get("kwargs") or {}
        self.pass_context = bool(self.spec.get("pass_context"))

    def run(self, ctx) -> TaskResult:
        start = time.time()
        try:
            module = importlib.import_module(self.spec["module"])
            func = getattr(module, self.spec["function"])
            result = func(ctx=ctx, **self.kwargs) if self.pass_context else func(**self.kwargs)
            if inspect.isawaitable(result):
                result = asyncio.run(result)
            return TaskResult(exit_code=0, duration=time.time() - start,
                              message=str(result) if result is not None else "")
        except Exception as exc:  # 插件异常不应带崩控制器
            return TaskResult(exit_code=1, duration=time.time() - start,
                              message=f"{type(exc).__name__}: {exc}")


def _terminate(proc, grace=10):
    """SIGTERM 整个进程组，超时再 SIGKILL。"""
    if proc.poll() is not None:
        return
    try:
        if os.name != "nt" and hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
    except OSError:
        pass
    try:
        proc.wait(timeout=grace)
    except subprocess.TimeoutExpired:
        try:
            if os.name != "nt" and hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            else:
                proc.kill()
        except OSError:
            pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
