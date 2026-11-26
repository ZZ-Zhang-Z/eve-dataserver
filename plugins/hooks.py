"""钩子插件：任务生命周期回调。

阶段只有两个：on_before（执行前）、on_after（执行后，带结果）。
插件按需实现，未实现的方法会被控制器跳过。

新增钩子的模板：

    @register_hook("notify_wecom")
    class WecomHook:
        def on_after(self, ctx, result):
            ...
"""
import json
import logging
import subprocess
import time
import urllib.request

from core.registry import register_hook


@register_hook("log")
class LogHook:
    """默认钩子：把开始与结束写进控制器日志。"""

    def __init__(self, spec, cfg):
        self.spec = spec or {}

    def on_before(self, ctx):
        ctx.log("开始（executor=%s）", getattr(ctx.task.executor, "plugin_name", "?"))

    def on_after(self, ctx, result):
        if result.ok:
            ctx.log("完成：用时 %.1fs，峰值 RSS %.0fMB", result.duration, result.peak_rss_mb)
        else:
            ctx.log("失败：exit=%s %s", result.exit_code, result.message or "",
                    level=logging.WARNING)


@register_hook("command")
class CommandHook:
    """执行一条外部命令，用于备份、清理、归档等收尾动作。

    spec:
        {"command": ["/bin/bash", "-c", "..."],
         "phases": ["after"],              # before / after
         "only_on": "any|success|failure",
         "timeout_seconds": 120}
    """

    def __init__(self, spec, cfg):
        self.spec = spec or {}
        self.command = self.spec.get("command")
        if not self.command:
            raise ValueError("command 钩子需要 command 字段")
        self.phases = set(self.spec.get("phases") or ["after"])
        self.only_on = self.spec.get("only_on", "any")
        self.timeout = int(self.spec.get("timeout_seconds", 120))
        self.root = (cfg or {}).get("_root")

    def _should_run(self, result):
        if self.only_on == "success":
            return result.ok
        if self.only_on == "failure":
            return not result.ok
        return True

    def _exec(self, ctx):
        try:
            subprocess.run(self.command, cwd=self.root or ctx.root, timeout=self.timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception as exc:  # 钩子失败不应影响任务结论
            ctx.log("钩子命令失败：%s", exc, level=logging.WARNING)

    def on_before(self, ctx):
        if "before" in self.phases:
            self._exec(ctx)

    def on_after(self, ctx, result):
        if "after" in self.phases and self._should_run(result):
            self._exec(ctx)


@register_hook("webhook")
class WebhookHook:
    """POST 一段 JSON 到指定 URL，用于告警或通知。

    spec:
        {"url": "https://...", "only_on": "failure|success|any", "timeout_seconds": 10}
    """

    def __init__(self, spec, cfg):
        self.spec = spec or {}
        self.url = self.spec.get("url")
        if not self.url:
            raise ValueError("webhook 钩子需要 url 字段")
        self.only_on = self.spec.get("only_on", "failure")
        self.timeout = int(self.spec.get("timeout_seconds", 10))

    def _match(self, result):
        if self.only_on == "success":
            return result.ok
        if self.only_on == "failure":
            return not result.ok
        return True

    def on_after(self, ctx, result):
        if not self._match(result):
            return
        payload = {
            "task": ctx.task.name,
            "run_id": ctx.run_id,
            "exit_code": result.exit_code,
            "ok": result.ok,
            "duration": round(result.duration, 1),
            "peak_rss_mb": round(result.peak_rss_mb, 1),
            "message": result.message,
            "ts": int(time.time()),
        }
        try:
            request = urllib.request.Request(
                self.url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except Exception as exc:
            ctx.log("webhook 发送失败：%s", exc, level=logging.WARNING)
