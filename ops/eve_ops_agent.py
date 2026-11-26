#!/usr/bin/env python3
"""EVE 采集服务 · 宿主机受限执行代理。

只做四件事：start / stop / restart eve-controller.service，以及 status（只读）。
供 AstrBot 容器里的 astrbot_plugin_eve_ops 调用，不暴露到公网。

设计约束（改代码前先读）：
- 动作是白名单枚举，请求体里只有 action 名，不参与任何命令拼接；全程无 shell=True。
- token 从 /etc/eve-ops/token 读取，常数时间比较；缺失则拒绝启动。
- 只监听 127.0.0.1 与 docker 网桥地址（默认 172.18.0.1），不做 0.0.0.0 监听。
- 变更动作有 2 秒节流，避免机器人重试把 systemctl 打成连击。
"""
import hmac
import json
import logging
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_DIR = os.environ.get("EVE_OPS_APP_DIR", "/home/admin/eve_helper")
TOKEN_FILE = os.environ.get("EVE_OPS_TOKEN_FILE", "/etc/eve-ops/token")
BINDS = os.environ.get("EVE_OPS_BIND", "127.0.0.1 172.18.0.1").split()
SYSTEMCTL = "/usr/bin/systemctl"
UNIT = "eve-controller"
MUTATION_INTERVAL = 2.0
MAX_OUTPUT = 1800

log = logging.getLogger("eve-ops-agent")

with open(TOKEN_FILE, encoding="utf-8") as fh:
    TOKEN = fh.read().strip()
if not TOKEN:
    print("token 文件为空，拒绝启动", file=sys.stderr)
    sys.exit(1)

_lock = threading.Lock()
_last_mutation = 0.0


def _run(argv, timeout):
    """执行固定命令，返回 (ok, 输出)。

    不设 cwd：/home/admin 是 0700，eveops 连 chdir 都进不去（Errno 13）。
    所有路径都用绝对路径，systemctl 也不依赖工作目录。
    """
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"超时 {timeout}s"
    except OSError as exc:
        return False, f"执行失败：{exc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, (err or out or f"退出码 {proc.returncode}")
    return True, out


def _fmt_ts(ts):
    if not ts:
        return "-"
    try:
        return time.strftime("%m-%d %H:%M", time.localtime(float(ts)))
    except (TypeError, ValueError, OSError):
        return "-"


def _read_state():
    """state.json 是 admin:admin 0600，eveops 读不到；用一条受限的 sudo cat 兜底。

    注意 state.py 用 mkstemp + os.replace 落盘，权限每次都会回到 0600，
    所以不要指望用 chmod/chgrp 长期放开。
    """
    path = os.path.join(APP_DIR, "state.json")
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        pass

    ok, out = _run(["sudo", "-n", "-u", "admin", "/bin/cat", path], 10)
    if not ok:
        log.warning("读取 state.json 失败：%s", out[:200])
        return {}
    try:
        return json.loads(out)
    except ValueError:
        return {}


def _status_text():
    _, active = _run([SYSTEMCTL, "is-active", UNIT], 10)
    active = active or "unknown"
    tasks = _read_state().get("tasks") or {}
    lines = [f"服务 {active}"]

    order = ("orders", "history", "sde", "monthly")
    for name in order:
        item = tasks.get(name) or {}
        if item.get("last_end") is None:
            lines.append(f"{name:<8} 未运行  下次 {_fmt_ts(item.get('next_run_ts'))}")
            continue
        code = item.get("last_exit_code")
        dur = item.get("last_duration") or 0
        fails = item.get("consecutive_failures") or 0
        line = (f"{name:<8} exit={code} {dur:.0f}s "
                f"下次 {_fmt_ts(item.get('next_run_ts'))}")
        if fails:
            line += f" 连败{fails}"
        lines.append(line)
    return "\n".join(lines)


def _do_action(action):
    """返回 (ok, detail)。"""
    global _last_mutation

    if action == "status":
        return True, _status_text()

    if action not in ("start", "stop", "restart"):
        return False, f"不支持的动作：{action}"

    with _lock:
        wait = MUTATION_INTERVAL - (time.time() - _last_mutation)
        if wait > 0:
            time.sleep(wait)
        _last_mutation = time.time()

        ok, out = _run(["sudo", "-n", SYSTEMCTL, action, UNIT], 45)
        time.sleep(1.0)
        _, active = _run([SYSTEMCTL, "is-active", UNIT], 10)
        detail = f"{action} -> {active or 'unknown'}"
        if not ok:
            detail += f"\n{out[:400]}"
        return ok, detail


class Handler(BaseHTTPRequestHandler):
    server_version = "eve-ops-agent/1.0"

    def _send(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self):
        raw = self.headers.get("Authorization", "")
        token = raw[7:].strip() if raw.lower().startswith("bearer ") else ""
        if not token:
            token = self.headers.get("X-Token", "").strip()
        return bool(token) and hmac.compare_digest(token, TOKEN)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "service": "eve-ops-agent"})
        else:
            self._send(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/action":
            self._send(404, {"ok": False, "error": "not found"})
            return
        if not self._authorized():
            log.warning("拒绝未授权请求 from %s", self.client_address[0])
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 4096:
                raise ValueError("bad length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            action = str(payload.get("action") or "").strip().lower()
        except (ValueError, UnicodeDecodeError) as exc:
            self._send(400, {"ok": False, "error": f"bad request: {exc}"})
            return

        started = time.time()
        ok, detail = _do_action(action)
        took = time.time() - started
        log.info("action=%s ok=%s %.2fs from %s", action, ok, took, self.client_address[0])
        self._send(200 if ok else 500, {
            "ok": ok,
            "action": action,
            "detail": detail[:MAX_OUTPUT],
            "elapsed": round(took, 2),
        })

    def log_message(self, fmt, *args):  # 交给 logging，保持 journal 干净
        log.debug("%s - %s", self.address_string(), fmt % args)


def _serve(host):
    server = ThreadingHTTPServer((host, 8765), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, name=f"http-{host}", daemon=True).start()
    log.info("监听 %s:8765", host)
    return server


def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")
    servers = []
    for host in BINDS:
        try:
            servers.append(_serve(host))
        except OSError as exc:
            log.error("绑定 %s:8765 失败：%s", host, exc)
    if not servers:
        log.error("没有任何地址绑定成功，退出")
        return 1
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        for server in servers:
            server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
