# 通过 QQ 私聊控制采集服务

```
QQ 私聊 ──WS──> AstrBot 容器（qq_official）
                   └─ 插件 astrbot_plugin_eve_ops
                        └─ HTTP POST + token ──> 172.18.0.1:8765
                                                  宿主机 eve-ops-agent
                                                    └─ sudo systemctl start|stop|restart eve-controller
```

容器里没有 ssh，也不该把宿主机入口交给一个跑第三方插件的进程，所以控制走宿主机上的
一个小代理：只认 4 个动作、只监听环回与 docker 网桥、token 鉴权、无 shell。

## 一、宿主机侧（一次性）

```bash
# 1) 专用用户（无登录 shell）
sudo useradd --system --no-create-home --shell /usr/sbin/nologin eveops

# 2) 目录与令牌
sudo install -d -m 0755 /opt/eve-ops
sudo install -d -m 0750 -o root -g eveops /etc/eve-ops
openssl rand -hex 24 | sudo tee /etc/eve-ops/token >/dev/null
sudo chgrp eveops /etc/eve-ops/token && sudo chmod 0640 /etc/eve-ops/token

# 3) 代理与单元
sudo install -m 0755 eve_ops_agent.py /opt/eve-ops/eve_ops_agent.py
sudo install -m 0644 eve-ops-agent.service /etc/systemd/system/

# 4) 精确 sudoers（3 个 systemctl 动词 + 一条只读 cat）
sudo install -m 0440 -o root -g root sudoers-eve-ops /etc/sudoers.d/eve-ops
sudo visudo -cf /etc/sudoers.d/eve-ops

# 5) 启动
sudo systemctl daemon-reload
sudo systemctl enable --now eve-ops-agent
```

验证（令牌在 `/etc/eve-ops/token`）：

```bash
TOKEN=$(sudo cat /etc/eve-ops/token)
curl -s http://127.0.0.1:8765/health
curl -s -H "Authorization: Bearer $TOKEN" \
     -d '{"action":"status"}' http://127.0.0.1:8765/action
curl -s -o /dev/null -w '%{http_code}\n' -d '{"action":"status"}' \
     http://127.0.0.1:8765/action          # 期望 401
```

`EVE_OPS_BIND` 默认 `127.0.0.1 172.18.0.1`。**docker 网络重建后网关可能变化**，
用 `ip -4 addr | grep 172.` 确认后改 unit 里的环境变量。

## 二、AstrBot 侧

```bash
PLUGINS=/opt/1panel/apps/astrbot/astrbot/data/plugins
sudo cp -r astrbot_plugin_eve_ops "$PLUGINS"/
sudo chown -R root:root "$PLUGINS/astrbot_plugin_eve_ops"

# 插件配置（与 /etc/eve-ops/token 一致）
sudo tee /opt/1panel/apps/astrbot/astrbot/data/config/astrbot_plugin_eve_ops_config.json >/dev/null <<EOF
{
  "agent_url": "http://172.18.0.1:8765/action",
  "agent_token": "$(sudo cat /etc/eve-ops/token)",
  "allowed_uids": "",
  "confirm_ttl": 60,
  "timeout_seconds": 30
}
EOF

sudo docker restart astrbot
sudo docker logs --tail 80 astrbot 2>&1 | grep -i eve
```

## 三、使用

| 命令 | 说明 |
|---|---|
| `/eve status` | 服务状态 + 四个任务的退出码、耗时、下次运行 |
| `/eve start` | 启动（已启动时是幂等的） |
| `/eve stop` | 停止，需在 60 秒内回 `/eve stop confirm` |
| `/eve restart` | 重启，同样需确认 |
| `/eve id` | 回显自己的 QQ 号与 UMO，用来填 `allowed_uids` |

三道限制同时生效：AstrBot 管理员、仅私聊、`allowed_uids`（留空则不限）。

## 四、排障

| 现象 | 检查 |
|---|---|
| 机器人没反应 | `docker logs --tail 100 astrbot \| grep -i eve`；确认是私聊且在管理员列表 |
| 回复「查询失败：403」 | 插件 `agent_token` 与 `/etc/eve-ops/token` 不一致 |
| 回复「查询失败：Connection refused」 | `systemctl status eve-ops-agent`；容器到 `172.18.0.1` 是否通 |
| 回复「start 失败」 | `journalctl -u eve-ops-agent -n 20`，看 sudoers 是否放行 |
| 群聊里@机器人无反应 | 设计如此：只处理私聊 |

## 五、安全边界

- 代理只做 `start/stop/restart`，不接受命令参数，不写任何配置文件。
- sudoers 只放这 3 个 systemctl 动词 + 一条 `/bin/cat state.json`；即使代理进程被拿下，
  能做的也只有启停和读一个状态文件。
- 令牌同时存在于宿主机 `/etc/eve-ops/token`（0640 root:eveops）与 AstrBot 配置里，
  轮换时两处一起改并 `systemctl restart eve-ops-agent` + `docker restart astrbot`。
- 不要把这套东西扩展到 `pause orders`（要改 `controller.json` 并发 HUP），
  那会把「只读执行」变成「可写配置」，权限面完全不同。
