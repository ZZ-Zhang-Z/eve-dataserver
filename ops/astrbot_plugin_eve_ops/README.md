# astrbot_plugin_eve_ops

通过 QQ 私聊控制服务器上的 EVE 数据采集服务（`eve-controller.service`）。

## 命令

| 命令 | 说明 |
|---|---|
| `/eve status` | 服务状态 + 四个任务的退出码、耗时、下次运行 |
| `/eve start` | 启动（幂等） |
| `/eve stop` | 停止，需 60 秒内回 `/eve stop confirm` |
| `/eve restart` | 重启，同样需确认 |
| `/eve id` | 回显自己的 ID 与 UMO，用于填 `allowed_uids` |

## 限制

- 仅 AstrBot 管理员（`admins_id`）
- 仅私聊（群里 @ 不响应）
- 可选 `allowed_uids` 白名单，按平台 ID（qq_official 是 openid，不是 QQ 号）

## 依赖

宿主机上的 `eve-ops-agent`（见仓库 `ops/README.md`），提供 `http://172.18.0.1:8765/action`。
本插件只发一个动作名，真正的权限收敛在代理侧：动作白名单 + token + 3 个 systemctl 动词的 sudoers。

## 配置

`data/config/astrbot_plugin_eve_ops_config.json`

| 键 | 说明 |
|---|---|
| `agent_url` | 默认 `http://172.18.0.1:8765/action` |
| `agent_token` | 与宿主机 `/etc/eve-ops/token` 一致 |
| `allowed_uids` | 逗号分隔的平台 ID，留空表示所有管理员 |
| `confirm_ttl` | 二次确认有效期，默认 60 |
| `timeout_seconds` | 调用代理超时，默认 30 |
