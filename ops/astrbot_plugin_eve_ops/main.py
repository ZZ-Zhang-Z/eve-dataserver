"""私聊控制 EVE 采集服务。

命令（仅 AstrBot 管理员 + 仅私聊 + 可再限定 QQ 号）：
    /eve status           只读，看服务与四个任务
    /eve start            启动 eve-controller
    /eve stop             停止（需二次确认）
    /eve restart          重启（需二次确认）
    /eve id               回显自己的 QQ 号，便于填 allowed_uids

设计说明：
- 插件本身不碰 systemctl，只向宿主机上的受限代理发一个 action 名；
  代理侧有白名单、token 与节流，两处独立校验。
- stop / restart 必须先确认，避免误触把正在跑的 40 分钟历史采集打断。
"""
import time

import aiohttp

from astrbot.api import logger
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star


class EveOpsPlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.config = config or {}
        self._pending = {}      # qq号 -> (action, 时间戳)
        self._last_call = 0.0   # 简易节流
        logger.info("[eve_ops] 插件已初始化，agent_url=%s",
                    self._cfg("agent_url", "未配置"))

    # ------------------------------------------------------------ 基础设施

    def _cfg(self, key, default=None):
        try:
            value = self.config.get(key, default)
        except AttributeError:
            return default
        return default if value is None else value

    def _denied(self, event: AstrMessageEvent):
        """额外一层 QQ 号白名单；返回拒绝原因，None 表示放行。"""
        raw = str(self._cfg("allowed_uids", "") or "")
        allowed = {x.strip() for x in raw.replace("，", ",").split(",") if x.strip()}
        if not allowed:
            return None
        uid = str(event.get_sender_id())
        return None if uid in allowed else "此 QQ 号不在 allowed_uids 白名单内"

    async def _call(self, action):
        logger.info("[eve_ops] 执行 %s", action)
        url = str(self._cfg("agent_url", "http://172.18.0.1:8765/action"))
        token = str(self._cfg("agent_token", "") or "")
        if not token:
            raise RuntimeError("插件未配置 agent_token")
        timeout = float(self._cfg("timeout_seconds", 30))

        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"action": action},
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    data = {}
                if resp.status != 200 or not data.get("ok"):
                    detail = (data.get("detail") or data.get("error")
                              or f"HTTP {resp.status}")
                    raise RuntimeError(detail)
                return str(data.get("detail") or "")

    def _throttled(self):
        now = time.time()
        if now - self._last_call < 3:
            return True
        self._last_call = now
        return False

    # ------------------------------------------------------------ 命令

    @filter.command_group("eve")
    def eve(self):
        """EVE 采集服务控制"""
        pass

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @eve.command("status")
    async def eve_status(self, event: AstrMessageEvent):
        """查看服务状态与四个任务"""
        denied = self._denied(event)
        if denied:
            yield event.plain_result(denied)
            return
        try:
            detail = await self._call("status")
        except Exception as exc:
            logger.warning("eve status 失败：%s", exc)
            yield event.plain_result(f"查询失败：{exc}")
            return
        yield event.plain_result(detail)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @eve.command("start")
    async def eve_start(self, event: AstrMessageEvent):
        """启动采集服务"""
        denied = self._denied(event)
        if denied:
            yield event.plain_result(denied)
            return
        if self._throttled():
            yield event.plain_result("操作太频繁，等几秒再试")
            return
        try:
            detail = await self._call("start")
        except Exception as exc:
            logger.warning("eve start 失败：%s", exc)
            yield event.plain_result(f"启动失败：{exc}")
            return
        yield event.plain_result(detail)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @eve.command("stop")
    async def eve_stop(self, event: AstrMessageEvent, arg: str = ""):
        """停止采集服务（需二次确认）"""
        yield await self._guarded_action(event, "stop", arg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @eve.command("restart")
    async def eve_restart(self, event: AstrMessageEvent, arg: str = ""):
        """重启采集服务（需二次确认）"""
        yield await self._guarded_action(event, "restart", arg)

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    @eve.command("id")
    async def eve_id(self, event: AstrMessageEvent):
        """回显自己的 QQ 号，便于填写 allowed_uids"""
        yield event.plain_result(
            f"你的 QQ 号：{event.get_sender_id()}\n"
            f"会话 UMO：{event.unified_msg_origin}")

    # ------------------------------------------------------------ 内部

    async def _guarded_action(self, event: AstrMessageEvent, action: str, arg: str):
        """stop / restart 的确认流程。"""
        denied = self._denied(event)
        if denied:
            return event.plain_result(denied)

        uid = str(event.get_sender_id())
        ttl = int(self._cfg("confirm_ttl", 60))

        if arg.strip().lower() != "confirm":
            self._pending[uid] = (action, time.time())
            return event.plain_result(
                f"即将执行 {action}（会打断正在跑的那一轮采集）。\n"
                f"{ttl} 秒内回复 /eve {action} confirm 确认。")

        pending = self._pending.pop(uid, None)
        if not pending or pending[0] != action or time.time() - pending[1] > ttl:
            return event.plain_result(f"确认已过期，请重新发送 /eve {action}")

        if self._throttled():
            return event.plain_result("操作太频繁，等几秒再试")

        try:
            detail = await self._call(action)
        except Exception as exc:
            logger.warning("eve %s 失败：%s", action, exc)
            return event.plain_result(f"{action} 失败：{exc}")
        return event.plain_result(detail)
