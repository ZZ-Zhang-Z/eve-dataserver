#!/usr/bin/env python3
"""EVE 数据采集统一控制器（插件化）。

主循环只做四件事：算下次运行时间、查依赖、过闸门、调执行器。所有「怎么做」
都下沉到插件，因此新增能力不需要改本文件：

    执行方式   plugins.executors    subprocess / inline / 未来的 http、docker
    触发时机   plugins.schedules    interval / daily / weekly / monthly / cron
    准入检查   plugins.guards       resources / time_window / 未来的令牌余额
    生命周期   plugins.hooks        log / command / webhook / 未来的企业微信

扩展步骤固定为三步：写一个类、加 @register_xxx 装饰器、config.json 引用名字。
也可以用 config.plugin_modules 加载仓库外的自有插件模块。

其余设计取舍：
- 采集器一律跑子进程：模块级全局会互相污染，且进程退出是回收内存最彻底的方式。
- 串行执行：同一时刻只有一个任务，天然满足 ESI 令牌预算。
- SIGHUP 热重载：改 config 不必重启，运行中的任务不受影响。

用法
----
    python controller.py                    # 前台常驻
    python controller.py --status           # 任务状态表
    python controller.py --dry-run          # 未来若干次调度计划
    python controller.py --list-plugins     # 已注册的扩展点
    python controller.py --once orders      # 立即手动跑一个任务
    kill -HUP <pid>                         # 热重载 config.json
"""
import argparse
import json
import logging
import logging.handlers
import os
import signal
import sys
import threading
import time

import monitor
import plugins
from core import registry
from core.context import TaskContext, TaskResult
from core.task import load_tasks
from state import State
import paths

HERE = os.path.dirname(os.path.abspath(__file__))
# 本目录即项目根：config 里的 runner/script/log_dir/state_file 都相对它解析。
# 独立项目布局（本目录就是项目根）与早期的 EVE_helper/EVEDataserver 子目录布局
# 用的是同一套相对路径，因此两种布局都能直接运行。
ROOT = HERE

GUARD_RETRY_SECONDS = 60  # 被闸门/依赖拦下后，多久重试一次

log = logging.getLogger("controller")
CONFIG_PATH = os.path.join(HERE, "controller.json")
LEGACY_CONFIG_PATH = os.path.join(HERE, "config.json")  # 旧名，仅用于提示


# ---------------------------------------------------------------- 工具

def resolve(path):
    if not path:
        return path
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(ROOT, path))


def fmt_ts(ts):
    if not ts:
        return "-"
    return time.strftime("%m-%d %H:%M:%S", time.localtime(ts))


def fmt_duration(seconds):
    if seconds is None:
        return "-"
    seconds = float(seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, sec = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m{sec:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def _width(text):
    return sum(2 if ord(ch) > 127 else 1 for ch in str(text))


def _pad(text, width, align="left"):
    text = str(text)
    gap = max(0, width - _width(text))
    return text + " " * gap if align == "left" else " " * gap + text


def load_config(path):
    with open(path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    cfg.setdefault("tick_seconds", 10)
    cfg.setdefault("resources", {})
    cfg.setdefault("tasks", {})
    cfg["_root"] = ROOT
    return cfg


def setup_logging(log_dir, level):
    formatter = logging.Formatter("%(asctime)s %(levelname)-5s %(message)s",
                                 "%Y-%m-%d %H:%M:%S")
    log.setLevel(level)
    log.handlers.clear()
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    log.addHandler(stream)
    try:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "controller.log"),
            maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
        file_handler.setFormatter(formatter)
        log.addHandler(file_handler)
    except OSError as exc:
        log.warning("控制器日志文件不可写（%s），仅输出到 stdout", exc)


def _alive(pid):
    if os.name == "nt":
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class SingleInstance:
    """pidfile 单实例锁，防止 systemd 与手动启动叠加。"""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="ascii") as handle:
                    pid = int(handle.read().strip())
            except (OSError, ValueError):
                pid = None
            if pid and _alive(pid):
                raise SystemExit(f"已有控制器在运行（pid={pid}）：{self.path}")
        with open(self.path, "w", encoding="ascii") as handle:
            handle.write(str(os.getpid()))
        return self

    def __exit__(self, *_exc):
        try:
            os.unlink(self.path)
        except OSError:
            pass


# ---------------------------------------------------------------- 执行

def _task_succeeded(state, name):
    item = state.task(name)
    return item.get("last_exit_code") == 0 and item.get("last_end") is not None


def _safe_hook(callback, ctx, *args):
    try:
        callback(ctx, *args)
    except Exception as exc:  # 钩子失败不应改变任务结论
        log.warning("[%s] 钩子执行失败（%s）：%s",
                    ctx.task.name, type(callback).__name__, exc)


def _run_with_retry(task, ctx, stop_event):
    retry = task.retry or {}
    attempts = max(1, int(retry.get("max_attempts", 1)))
    delay = float(retry.get("delay_seconds", GUARD_RETRY_SECONDS))
    retry_codes = retry.get("on_exit_codes")  # None 表示任何非 0 都重试

    result = None
    for attempt in range(1, attempts + 1):
        if stop_event.is_set():
            return result or TaskResult(exit_code=-15, message="控制器停止")
        if attempt > 1:
            log.warning("[%s] 第 %d/%d 次重试（上次 exit=%s）",
                        task.name, attempt, attempts, result.exit_code)
            if stop_event.wait(delay):
                return result
        result = task.executor.run(ctx)
        if result.ok:
            return result
        if retry_codes is not None and result.exit_code not in retry_codes:
            return result
    return result


def run_task(task, cfg, state, stop_event):
    """执行一个任务。返回 (是否真的执行了, 跳过原因)。

    执行阶段整体兜底：executor / hook / 插件抛出的任何未捕获异常都会转成
    exit_code=1，并照常写结束状态，避免单个任务的异常把主循环带崩（那会让
    systemd 重启控制器并丢掉当前调度进度）。被闸门或依赖拦下属于「未执行」，
    不写 last_end，也不计失败次数。
    """
    ctx = TaskContext.new(task, ROOT, state, stop_event, log)
    previous = state.task(task.name)

    unmet = [dep for dep in task.depends_on if not _task_succeeded(state, dep)]
    if unmet:
        return False, "依赖未完成：" + ", ".join(unmet)

    for guard in task.guards:
        try:
            ok, reason = guard.check(ctx)
        except Exception as exc:
            ok, reason = False, f"闸门异常：{exc}"
        if not ok:
            return False, f"闸门 {getattr(guard, 'plugin_name', '?')}：{reason}"

    state.update(task.name, last_start=int(time.time()), last_skip_reason=None,
                 total_runs=previous["total_runs"] + 1)

    try:
        for hook in task.hooks:
            callback = getattr(hook, "on_before", None)
            if callable(callback):
                _safe_hook(callback, ctx)

        result = _run_with_retry(task, ctx, stop_event)

        for hook in task.hooks:
            callback = getattr(hook, "on_after", None)
            if callable(callback):
                _safe_hook(callback, ctx, result)
    except Exception as exc:
        log.exception("[%s] 任务执行出现未捕获异常，按失败处理（控制器继续运行）", task.name)
        result = TaskResult(exit_code=1, message=f"{type(exc).__name__}: {exc}")

    failures = 0 if result.ok else previous["consecutive_failures"] + 1
    state.update(
        task.name,
        last_end=int(time.time()),
        last_exit_code=result.exit_code,
        last_duration=round(result.duration, 1),
        peak_rss_mb=round(result.peak_rss_mb, 1) or None,
        consecutive_failures=failures,
        last_message=result.message or "",
    )
    return True, ""


# ---------------------------------------------------------------- 主循环

def install_signals(stop_event, reload_event):
    def on_stop(signum, _frame):
        log.info("收到信号 %s，准备退出（等待当前任务结束）", signum)
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, on_stop)
        except (ValueError, OSError):
            pass

    if hasattr(signal, "SIGHUP"):
        def on_reload(_signum, _frame):
            log.info("收到 SIGHUP，将于下一 tick 重载 config.json")
            reload_event.set()

        try:
            signal.signal(signal.SIGHUP, on_reload)
        except (ValueError, OSError):
            pass


def loop(tasks, cfg, state, stop_event, reload_event):
    tick = int(cfg.get("tick_seconds", 10))
    if not tasks:
        log.error("配置里没有定义任何任务")
        return

    snapshot = monitor.sample(ROOT)
    log.info("控制器启动：%d 个任务，tick=%ds", len(tasks), tick)
    log.info("扩展点：%s", registry.snapshot())
    log.info("资源基线：内存可用 %s MB / 磁盘可用 %s MB / load1 %s",
             snapshot.get("mem_available_mb", "?"), snapshot.get("disk_free_mb", "?"),
             snapshot.get("load1", "?"))

    now = time.time()
    for name, task in tasks.items():
        if state.task(name).get("next_run_ts") is None:
            nxt = task.schedule.next_run(now)
            state.update(name, next_run_ts=nxt)
            log.info("[%s] 首次调度：%s -> %s", name, task.schedule.describe(), fmt_ts(nxt))

    while not stop_event.is_set():
        if reload_event.is_set():
            reload_event.clear()
            try:
                new_cfg = load_config(CONFIG_PATH)
                new_tasks = load_tasks(new_cfg)
                tasks, cfg = new_tasks, new_cfg
                log.info("config.json 已热重载：%d 个任务（运行中的任务不受影响）", len(tasks))
            except Exception as exc:
                log.error("热重载失败，继续使用旧配置：%s", exc)

        now = time.time()
        for name, task in list(tasks.items()):
            if stop_event.is_set():
                break
            if not task.enabled:
                continue

            item = state.task(name)
            due = item.get("next_run_ts")
            if due is None:
                nxt = task.schedule.next_run(now)
                state.update(name, next_run_ts=nxt)
                log.info("[%s] 首次调度：%s -> %s", name, task.schedule.describe(), fmt_ts(nxt))
                continue
            if now < due:
                continue

            lag = now - due
            if lag > 3600:
                log.warning("[%s] 已落后 %s，立即补跑一次", name, fmt_duration(lag))

            executed, reason = run_task(task, cfg, state, stop_event)
            if stop_event.is_set():
                break

            if executed:
                nxt = task.schedule.next_run(now)
                state.update(name, next_run_ts=nxt)
                log.info("[%s] 下次运行：%s", name, fmt_ts(nxt))
            else:
                state.update(name, next_run_ts=now + GUARD_RETRY_SECONDS,
                             last_skip_reason=reason)
                log.info("[%s] 本轮跳过：%s（%d 秒后重试）", name, reason, GUARD_RETRY_SECONDS)

        stop_event.wait(tick)

    log.info("控制器已退出")


# ---------------------------------------------------------------- CLI

def print_plugins():
    titles = {"executor": "执行器", "schedule": "调度器", "guard": "闸门", "hook": "钩子"}
    for kind, names in registry.snapshot().items():
        print(f"{titles.get(kind, kind)}（{len(names)}）")
        for name in names:
            cls = registry.get(kind, name)
            doc = (cls.__doc__ or "").strip().splitlines()
            summary = doc[0].strip() if doc else ""
            print(f"  - {name:<12} {summary}")
        print()


def print_status(tasks, state):
    header = (_pad("任务", 14) + _pad("调度", 24) + _pad("上次运行", 16)
              + _pad("用时", 9) + _pad("退出", 6) + _pad("峰值RSS", 10)
              + _pad("连败", 6) + _pad("下次运行", 16) + "备注")
    print(header)
    print("-" * 118)
    now = time.time()
    for name, task in tasks.items():
        item = state.task(name)
        flag = "" if task.enabled else "[停用] "
        note = item.get("last_skip_reason") or ""
        due = item.get("next_run_ts")
        due_text = fmt_ts(due) if due else "~" + fmt_ts(task.schedule.next_run(now))
        print(
            _pad(flag + name, 14)
            + _pad(task.schedule.describe(), 24)
            + _pad(fmt_ts(item.get("last_start")), 16)
            + _pad(fmt_duration(item.get("last_duration")), 9)
            + _pad(item.get("last_exit_code") if item.get("last_exit_code") is not None else "-", 6)
            + _pad(f"{item['peak_rss_mb']:.0f}MB" if item.get("peak_rss_mb") else "-", 10)
            + _pad(item.get("consecutive_failures", 0), 6)
            + _pad(due_text, 16)
            + note
        )
    updated = state.data.get("updated_at")
    if updated:
        print(f"\n状态文件更新于 {fmt_ts(updated)}")


def print_plan(tasks, times):
    print(f"未来 {times} 次调度计划\n")
    for name, task in tasks.items():
        if not task.enabled:
            continue
        cursor = time.time() - 1
        slots = []
        for _ in range(times):
            cursor = task.schedule.next_run(cursor)
            slots.append(fmt_ts(cursor))
        extras = []
        if task.depends_on:
            extras.append("依赖 " + ",".join(task.depends_on))
        for guard in task.guards:
            desc = getattr(guard, "describe", None)
            if callable(desc):
                text = desc()
                if text and text != "无限制":
                    extras.append(text)
        suffix = "  " + " | ".join(extras) if extras else ""
        print(f"{_pad(name, 12)}{task.schedule.describe()}{suffix}")
        print(f"{'':12}{' | '.join(slots)}\n")


def run_once_cli(tasks, cfg, state, name):
    task = tasks.get(name)
    if task is None:
        print(f"未知任务：{name}；可选：{', '.join(tasks)}")
        return 2
    executed, reason = run_task(task, cfg, state, threading.Event())
    if not executed:
        log.warning("任务未执行：%s", reason)
        return 3
    code = state.task(name).get("last_exit_code") or 0
    # 负值按 POSIX 惯例映射，避免 sys.exit(-9) 在 shell 里显示成 127
    return 128 + abs(code) if code < 0 else code


def main(argv=None):
    global CONFIG_PATH

    parser = argparse.ArgumentParser(description="EVE 数据采集统一控制器")
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--status", action="store_true", help="打印任务状态后退出")
    parser.add_argument("--dry-run", action="store_true", help="打印调度计划后退出")
    parser.add_argument("--list-plugins", action="store_true", help="列出已注册的扩展点")
    parser.add_argument("--once", metavar="TASK", help="立即执行指定任务（调试）")
    parser.add_argument("--times", type=int, default=5)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    CONFIG_PATH = os.path.abspath(args.config)

    try:
        cfg = load_config(CONFIG_PATH)
    except (OSError, ValueError) as exc:
        print(f"读取配置失败：{exc}")
        if os.path.exists(LEGACY_CONFIG_PATH):
            print("提示：控制器的配置已改名 controller.json，检测到旧名 config.json。"
                  "\n      两者语义不同：controller.json 是调度表，"
                  "config.json 是采集器运行时配置。请把旧文件重命名为 controller.json。")
        return 2

    # 独立项目首次运行时没有 data/ 与 logs/，这里一次性补齐
    base = paths.ensure_dirs()
    log.debug("数据根目录：%s", base)

    setup_logging(resolve(cfg.get("log_dir", "logs/controller")),
                  getattr(logging, args.log_level.upper(), logging.INFO))

    plugins.load_builtin()
    try:
        extra = plugins.load_external(cfg.get("plugin_modules"))
        if extra:
            log.info("已加载外部插件模块：%s", ", ".join(extra))
    except Exception as exc:
        log.error("外部插件加载失败：%s", exc)
        return 2

    if args.list_plugins:
        print_plugins()
        return 0

    try:
        tasks = load_tasks(cfg)
    except (LookupError, ValueError) as exc:
        print(f"任务配置有误：{exc}")
        return 2

    state = State(resolve(cfg.get("state_file", "state.json")))

    if args.status:
        print_status(tasks, state)
        return 0
    if args.dry_run:
        print_plan(tasks, args.times)
        return 0
    if args.once:
        return run_once_cli(tasks, cfg, state, args.once)

    stop_event = threading.Event()
    reload_event = threading.Event()
    install_signals(stop_event, reload_event)

    lock_path = resolve(cfg.get("lock_file", ".controller.lock"))
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with SingleInstance(lock_path):
        loop(tasks, cfg, state, stop_event, reload_event)
    return 0


if __name__ == "__main__":
    sys.exit(main())
