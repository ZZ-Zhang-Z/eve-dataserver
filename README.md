# eve-dataserver

EVE Online 市场数据长期采集服务。一个常驻控制器统一调度订单快照、成交历史、
SDE 静态数据与月度聚合，做资源闸门、失败重试与状态记录；数据落在本地 SQLite，
供分析端消费。

面向小内存服务器设计（实测峰值 70–120MB，1 核 1GB 也能跑）。

## 特性

- **插件化调度**：执行方式、调度方式、准入闸门、生命周期钩子都是注册表里的扩展点，
  新增能力只写一个类，主循环不改。
- **串行执行**：同一时刻只跑一个任务，天然避免多个采集器同时抢 ESI 令牌额度。
- **时间对齐**：`interval` 按 `(now // step + 1) * step` 计算下次触发，不是相对睡眠，
  长期运行不会累积漂移。
- **逐页落盘**：订单快照边抓边写暂存表，每页校验通过即释放，不把 418 页
  全量订单聚合进内存（实测 Python 堆峰值 225MB → 1.6MB）。完整性五道闸
  与「整份丢弃重拉」的保护全部保留，只是数据落点从内存换成了磁盘。
- **快照完整性保护**：订单采集有五道闸（页级完整、数量下限、去重、规模兜底、连续失败中止），
  任何一道不过都只会「少采一轮」，不会写出残缺数据或伪造的变更事件。
- **增量写库**：暂存表与主表比对后只写有差异的行——删掉真正消失的、插入新挂的、
  更新变价或变量的。每轮约 1.6 万行，未变化的 40 万行完全不触碰，因此 15 分钟一轮
  也不会产生写放大（41.8 万单规模下实测单轮 diff 约 0.8 秒）。
- **错误限流保护**：连续 20 页失败立即中止本轮，避免把 ESI 的 `100 errors/60s` 打满。
- **热重载**：`kill -HUP` 重读配置，运行中的任务不受影响。

## 快速开始

```bash
git clone git@github.com:ZZ-Zhang-Z/eve-dataserver.git
cd eve-dataserver

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 采集器运行时配置（项目根必须有 config.json，否则走代码兜底值）
cp config.collector.example.json config.json
# 编辑：只改 user_agent（填真实邮箱）。tracker 段对控制器路径不生效，见"部署清单"第 2 步

.venv/bin/python controller.py --dry-run    # 先看调度计划，不启动
.venv/bin/python controller.py              # 前台常驻
```

首次运行会自动创建 `data/`、`logs/`、`logs/collectors/`，不需要手工建目录。

## 目录结构

```
.
├── controller.py           主循环：算时间、查依赖、过闸门、调执行器
├── controller.json         调度表与资源阈值（控制器用）
├── config.json             采集器运行时配置（由 example 生成，不入库）
├── config.collector.example.json
├── paths.py                路径常量；BASE_DIR 可用 EVE_BASE_DIR 覆盖
├── database_manager.py     SQLite 连接管理（WAL + 线程本地连接）
├── collectors/             ESI 采集器
│   ├── esi_client.py       限流/退避/ETag 缓存/分页一致性校验
│   ├── jita_market_orders_collector_async.py     订单快照与变更事件
│   ├── jita_market_history_collector_async.py    成交历史
│   └── item_sde_collector.py                     SDE 静态数据导入
├── scripts/
│   └── aggregate_monthly_history.py   历史月度聚合与压缩
├── runners/                单轮封装（子进程入口，带退出码语义）
├── core/                   注册表、任务装配、上下文
├── plugins/                内置 executor / schedule / guard / hook
├── tests/                  控制器单元与扩展性测试
├── eve-controller.service  systemd 单元
├── logrotate-eve           子进程日志轮转
├── healthcheck.sh          健康检查
└── docs/运维手册.md        面向运维交接的独立文档（启停/巡检/故障处置）
```

## 调度表（`controller.json`）

| 任务 | 触发 | 超时 | 说明 |
|---|---|---|---|
| orders | 每 15 分钟，对齐整点/一刻/半点/三刻 | 600s | 跳过 18:55–19:45（EVE 维护窗），失败重试 2 次；变更事件保留 120 小时 |
| history | 每日 19:10 起，每小时一次（19:10–23:10） | 7200s | 15216 个 type，约 40 分钟；成功后当天不再重试 |
| sde | 每周日 09:30 | 1800s | 95MB 下载，通常命中 ETag |
| monthly | 每月 1 日 04:30 | 3600s | 依赖 history 最近一次成功 |

**为什么串行**：同一时刻只跑一个任务，既避免两个采集器同时抢 ESI 的请求预算，
也让小内存机器不被两套并发连接叠加。history 排在 19:10 之后，正好落在 orders 的
维护跳过窗（18:55–19:45）内，实际不会挤掉订单轮次；即使跑满 40 分钟到 19:50，
也只推迟 19:45 那一轮。

**限流口径（2026-11 实测）**：`/markets/{region_id}/orders` 已迁到令牌桶——分组
`market-order`、12000 tokens / 15 分钟；每次 200 扣 2、304 扣 1、4xx 扣 5、5xx 扣 0。
一轮 418 页 = 836 tokens，占 7%。`/markets/{region_id}/history` 尚未迁移，仍用旧的
「100 个非 2xx/3xx 响应 / 60 秒」错误限制——这条是**全局**的，一旦打穿，
已迁移的 orders 也会一起返回 420。

### 维护日的历史采集

ESI 的历史数据每天 11:05 UTC（北京时间 19:05）生成一次，而 EVE 在 19:00 开始例行
维护，大型更新可能持续 1–2 小时。所以 history 不是「跑一次，失败就等明天」：

1. cron 在 19:10 / 20:10 / 21:10 / 22:10 / 23:10 各触发一次；
2. 每次先用一个样本 type 探 `Last-Modified`，UTC 日期不是今天就直接返回退出码 6，
   不浪费 40 分钟去拉 15216 个 type；
3. 第一次真正成功后，`daily_success` 闸门让当天剩下的触发点全部跳过。

即使当天五次全部失败（超长维护），下一次采集返回的仍是完整历史，会自然补齐，
不会留下空洞。

## 命令行

```bash
python controller.py                 # 前台常驻（systemd 用这个）
python controller.py --status        # 任务状态表
python controller.py --dry-run       # 未来若干次调度 + 实际生效的闸门
python controller.py --list-plugins  # 已注册的扩展点及说明
python controller.py --once orders   # 立即手动跑一次（调试）

# 热重载 controller.json（运行中的任务不受影响）
kill -HUP $(pgrep -f controller.py)                        # 前台运行时
sudo systemctl kill -s HUP --kill-who=main eve-controller  # systemd 运行时
```

`systemctl kill` 不加 `--kill-who=main` 会把 SIGHUP 发给 cgroup 内所有进程，正在跑的
采集子进程会被直接终止（它没有 SIGHUP 处理器）。

`--dry-run` 会顺带打印每个任务实际生效的闸门，用于确认 `skip_windows` 是否挂上：

```
orders      每 15 分钟（对齐边界）  内存≥180MB，磁盘≥2048MB，load≤2.0×核数 | 跳过 18:55-19:45
            11-26 12:00:00
monthly     每月 1 日 04:30  依赖 history | 内存≥180MB...
```

## 退出码约定

| 码 | 含义 | 控制器行为 |
|---|---|---|
| 0 | 成功 | 记录耗时与峰值 RSS |
| 2 | 快照不完整，保留旧数据 | 记失败，等下一轮 |
| 3 | 未取到订单 | 同上 |
| 4 | 写库被拒（规模骤降/重复） | 同上 |
| 5 | 历史错误超预算 | 同上 |
| 6 | 今日历史数据尚未刷新（维护延迟） | 记失败，保留后续整点重试 |
| -9 | 超时被终止 | 记失败 |
| -15 | 控制器停止时终止 | 记失败，不影响重启 |

`--once` 会把负值按 POSIX 惯例映射为 `128+n`（137/143），避免 shell 显示成 127。

## 扩展模型

主循环只依赖四个抽象接口，任何「怎么做」都是可替换的插件：

| 扩展点 | 决定什么 | 内置实现 |
|---|---|---|
| executor | 任务怎么跑 | `subprocess`、`inline` |
| schedule | 何时跑 | `interval`、`daily`、`weekly`、`monthly`、`cron` |
| guard | 能不能跑 | `resources`、`time_window`、`always` |
| hook | 跑前后做什么 | `log`、`command`、`webhook` |

**新增能力的成本是固定的**：写一个类 → 加装饰器 → config 引用名字。`controller.py` 一行不用改。

### 示例：加一个「每 15 分钟探测 ESI 可用性」的任务

```python
@register_executor("http_probe")
class HttpProbeExecutor:
    def __init__(self, spec, cfg):
        self.url = spec["url"]

    def run(self, ctx):
        import time, urllib.request
        start = time.time()
        try:
            with urllib.request.urlopen(self.url, timeout=10) as resp:
                return TaskResult(exit_code=0 if resp.status < 400 else 1,
                                  duration=time.time() - start)
        except Exception as exc:
            return TaskResult(exit_code=1, duration=time.time() - start, message=str(exc))
```

`controller.json` 的 tasks 里加：

```json
"health_probe": {
  "executor": { "type": "http_probe", "url": "https://esi.evetech.net/status" },
  "schedule": { "type": "cron", "expr": "*/15 * * * *" },
  "hooks": [ { "type": "webhook", "url": "https://your-hook", "only_on": "failure" } ]
}
```

热重载即可生效，不用重启进程。

### 不改本仓库：加载外部插件

把插件模块放到任意可导入位置，然后：

```json
"plugin_modules": ["mycompany.eve_plugins"]
```

`load_external()` 会在启动时 import 它们，注册随模块导入自动完成。

### 已支持但尚未用到的能力

- **依赖**：`"depends_on": ["history"]`，上游最近一次成功才执行（`monthly` 已启用）。
- **重试**：`"retry": {"max_attempts": 2, "delay_seconds": 120, "on_exit_codes": [2]}`。
- **收尾命令**：`{"type": "command", "command": ["/bin/bash","-c","..."], "only_on": "success"}`。
- **失败告警**：`{"type": "webhook", "url": "...", "only_on": "failure"}`。

旧格式（`"runner"`、`"script"`、`"skip_windows"`）仍然可用，会自动映射为
`subprocess` 执行器 + `resources`/`time_window` 闸门 + `log` 钩子。

## 两个配置文件不要混

| 文件 | 谁读 | 内容 |
|---|---|---|
| `controller.json` | 控制器 | 任务调度、资源阈值、日志与状态路径 |
| `config.json` | 采集器（`esi_client` 等） | ESI 版本头、`user_agent`；`market_orders_tracker` 只对单独运行采集器脚本的旧路径生效 |

采集器按 `paths.BASE_DIR/config.json` 读取，所以 `config.json` 必须放在项目根，
且**不要**把它改名或塞进子目录。

## 数据位置

默认都在项目内（`data/`、`logs/`）。如果希望把数据放到别处——例如与主项目的
分析脚本共用同一份数据库——用环境变量覆盖：

```bash
EVE_BASE_DIR=/home/admin/eve_helper python controller.py
```

`paths.BASE_DIR` 会随之改变，`data/`、`logs/`、`config.json` 都在该目录下查找。

## 部署清单（首次）

按顺序做，每一步都给了可核对的输出。**第 5 步的 `daemon-reload` 是最容易漏、
且漏了完全没有报错的一条。**

### 1. 代码与依赖

```bash
git clone git@github.com:ZZ-Zhang-Z/eve-dataserver.git ~/eve_helper
cd ~/eve_helper
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -V          # 期望 3.11.x
```

### 2. 采集器配置

```bash
cp config.collector.example.json config.json
```

必须改一处：`user_agent` 换成真实邮箱。`market_orders_tracker` 段对控制器**不生效**——
控制器走 `runners/orders_once.py` 的流式入口，变更事件总是产生，保留时长由
`controller.json` 的 `EVE_RETENTION_HOURS` 决定（该段只影响单独运行采集器脚本的旧路径）。核对：

```bash
.venv/bin/python -c "import json;c=json.load(open('config.json'));print(c['user_agent'],c['market_orders_tracker'])"
```

`user_agent` 留成 `your-email@example.com` 比留空更糟——非空值会覆盖代码内置的真实地址。

### 3. 启动前先验一遍（不装服务）

```bash
.venv/bin/python controller.py --dry-run     # 看调度计划与闸门描述
.venv/bin/python controller.py --once orders # 真跑一轮，验证 ESI 连通与建库
```

首次运行会自动创建 `data/`、`logs/`、`logs/collectors/`。

### 4. 安装单元与日志轮转

```bash
sudo cp eve-controller.service /etc/systemd/system/
sudo cp logrotate-eve /etc/logrotate.d/eve-helper
```

模板里的路径写死为 `/home/admin/eve_helper`，换路径部署时先核对这五行：

```bash
grep -E "^(User|Group|WorkingDirectory|ExecStart|Documentation)=" /etc/systemd/system/eve-controller.service
```

`logrotate-eve` 里也有 `su admin admin` 与日志路径，同样按实际用户/路径改。

### 5. 重载并启用 ← 改 unit 文件必须走这一步

```bash
sudo systemctl daemon-reload          # 少了这条，systemd 用的还是缓存的旧定义
sudo systemctl enable --now eve-controller
sudo systemctl status eve-controller --no-pager
journalctl -u eve-controller -f
```

**为什么必须 `daemon-reload`**：systemd 在内存里缓存了 unit 的解析结果，`cp` 只改了
磁盘文件。`restart` 只是用**缓存里的旧定义**重启进程，所以改了 `Environment=`、
`MemoryMax=`、`ExecStart=` 却只 `restart` 时，表现是「改了没生效」，而且日志里
一个字都不会提。首次安装时漏掉它，甚至会出现 unit 文件明明在、systemctl 却说找不到。

### 6. 校验生效值（当成交付标准）

```bash
systemctl show eve-controller -p Environment -p MemoryHigh -p MemoryMax -p Restart
systemctl show eve-controller -p MemoryMax --value | numfmt --to=iec   # 期望 300M
systemctl cat eve-controller | head -5                                  # systemd 实际加载的文件
```

期望的环境变量一行（顺序无关）：

```
Environment=PYTHONUNBUFFERED=1 PYTHONUTF8=1 TZ=Asia/Shanghai DB_CACHE_MB=32
MemoryHigh=209715200
MemoryMax=314572800
```

`DB_CACHE_MB` 不在 `Environment` 里，或 `MemoryMax` 还是默认的
`18446744073709551615`，都说明第 5 步没做成功——先 `systemctl cat` 确认文件路径再重做。

`MemoryHigh=200M / MemoryMax=300M` 是 cgroup 护栏：万一出现未预料的分配，让子进程
自己被杀并由控制器记下退出码，而不是拖死整机。

### 7. 健康检查

```bash
crontab -e
# 每 10 分钟一次
*/10 * * * * /home/admin/eve_helper/healthcheck.sh >> /home/admin/eve_helper/logs/health.log 2>&1
```

`healthcheck.sh` 用 `journalctl` 统计错误，需要用户在 `systemd-journal` 组里，否则
告警数恒为 0（有 `|| true` 兜底，不报错但会误报「无告警」）：

```bash
sudo usermod -aG systemd-journal admin    # 重新登录后生效
```

### 8. 首轮跑完后的核对（约 30 分钟后）

```bash
.venv/bin/python controller.py --status
sqlite3 data/eve_market_orders.db \
  "select count(*) from market_orders; select count(*) from market_order_events;"
```

空库建基线时，第一轮应该是「全量插入 + 零 delete 事件」。如果看到成千上万条
`delete`，说明库里残留着旧快照——先清空 `market_orders` / `market_order_events`
再重跑一轮，否则这批假事件会污染 churn 数据。

## 更新代码

改动落在哪一层，决定要不要重启、要不要重载。**先对表，再动手。**

| 改动文件 | 需要的动作 | 原因 |
|---|---|---|
| `collectors/*.py`、`runners/*.py`、`scripts/*.py`、`database_manager.py` | **什么都不用做** | 每次任务都是新起子进程，下次触发自动加载新代码 |
| `controller.json` | `sudo systemctl kill -s HUP --kill-who=main eve-controller` | SIGHUP 重读调度表，运行中的任务不受影响 |
| `controller.py`、`core/`、`plugins/`、`paths.py`、`monitor.py`、`state.py` | `sudo systemctl restart eve-controller` | 属于控制器进程内的模块，只能重启 |
| `eve-controller.service` | `cp` → `daemon-reload` → `restart` | 三步缺一不可 |
| `logrotate-eve` | `cp` 即可 | logrotate 每次运行都重读配置，与 systemd 无关 |

常规流程：

```bash
cd ~/eve_helper && git pull

# 只有改动了 unit 文件时才需要这两行：
# sudo cp eve-controller.service /etc/systemd/system/
# sudo systemctl daemon-reload

sudo systemctl restart eve-controller
journalctl -u eve-controller -n 30 --no-pager
```

**不要用 `systemctl reload` 去加载 unit 文件的改动。** 它发的是 SIGHUP，只让控制器
重读 `controller.json`，跟 systemd 的 unit 缓存没有任何关系。unit 改动只有
`daemon-reload` 一条路。

同理，只改 `controller.json` 时要用 `--kill-who=main` 限定目标。`systemctl kill`
默认发给 cgroup 内所有进程——包括正在跑的那轮采集子进程，它没有 SIGHUP 处理器，
收到就是直接终止，一轮采集白跑（订单侧会退化成「少采一轮」，history 侧则要等
下一个整点）。

回滚一次部署（`git pull` 之后发现异常）：

```bash
git log --oneline -3
git reset --hard <上一个 commit>
# 如果同时回滚了 unit：sudo cp eve-controller.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl restart eve-controller
```

## 日常运维：启停

> 完整版（含巡检清单、故障处置、应急备份）见 [`docs/运维手册.md`](docs/运维手册.md)，
> 可直接发给接手的人。本节是命令层面的摘录。

### 服务级（systemd）

```bash
sudo systemctl start   eve-controller
sudo systemctl stop    eve-controller      # 优雅停止，先让当前任务收尾
sudo systemctl restart eve-controller
systemctl status eve-controller --no-pager
sudo systemctl disable eve-controller      # 只取消开机自启，当前进程不动
sudo systemctl enable  eve-controller
```

`stop` 的耗时：控制器收到 SIGTERM 后不再派发新任务，把 SIGTERM 发给当前子进程所在的
**进程组**，10 秒仍未退出才 SIGKILL。正常 1–2 秒，最坏约 12 秒；`TimeoutStopSec=60`
只是兜底，不会真等那么久。

### 停止时正在跑的那一轮会怎样

| 数据 | 结果 |
|---|---|
| 订单主表 | **不变**。只有完整快照通过五道闸后才会更新，中途停止等于"这一轮没发生" |
| `market_orders_staging` | 留下已提交的页（每 20 页 commit），下一轮开头 `DELETE` 清空，不用手工清理 |
| `market_order_events` | **不会多出假事件**。diff 没执行过，就没有任何事件写入 |
| `state.json` | 该轮记为失败（`exit_code=-15`，连败 +1），只影响 `--status` 显示，不影响下次调度 |

一句话：停止永远是安全的，最坏结果是"少采一轮"。

### 不停服务、只暂停采集

把 `controller.json` 里对应任务的 `"enabled": false`，然后只给主进程发 HUP：

```bash
sudo systemctl kill -s HUP --kill-who=main eve-controller
```

运行中的那一轮不受影响，之后不再触发；恢复时改回 `true` 再发一次。三种"停"的区别：

| 做法 | 效果 | 适用场景 |
|---|---|---|
| `systemctl stop` | 控制器和所有采集都停，重启后按 `state.json` 恢复调度 | 换代码、改 unit、腾内存 |
| `enabled: false` + HUP | 只停这一个任务，进程还在，其他任务照常 | 临时不想要某一类数据 |
| `systemctl disable` | 只取消开机自启，当前仍在跑 | 计划内长期关停 |

### 停机久了会不会漏数据

不会漏掉"能补的"。`state.json` 里的 `next_run_ts` 会保留，重启后只要求值已过期，
下一个 tick（≤10 秒）就会立刻执行，不用等下个对齐点；过期超过 1 小时还会额外记一条
`已落后 … 立即补跑一次`。

但有两件事补不回来：订单表只保留最新快照（停机期间的历史快照 ESI 不提供），
events 是 120 小时滚动窗口（停机超过 5 天，前面的窗口已经滚掉了）。这是数据源
的上限，不是配置问题。

### 手动补跑一个任务

```bash
sudo systemctl stop eve-controller                  # 先停，避免和计划任务抢同一张暂存表
.venv/bin/python controller.py --once orders
sudo systemctl start eve-controller
```

`--once` 会照常过闸门（资源、时间窗、`daily_success` 都生效）、照常写 `state.json`，
退出码就是子进程退出码。两条注意：

- **它不拿 pidfile 锁**，所以服务在跑时也能执行。但同一个采集器绝不能和计划中的同名
  任务重叠——两边会同时写 `market_orders_staging`，结果是两份快照互相污染。
- **不要用 Ctrl-C 打断**。子进程是独立会话（`start_new_session=True`），Ctrl-C 只杀
  控制器，采集进程会变成孤儿继续跑到结束（日志还在写，`ps` 里看得到）。
  真要中断：`pgrep -af _once.py` 找到 PID 后 `kill`。

### 停完确认没留孤儿进程

```bash
pgrep -af "controller.py|_once.py" || echo "已全部退出"
```

## 与其他项目的关系

本仓库是服务器端的独立发行版。开发主项目（含 Web 前端与分析脚本）时，`collectors/`
下的采集器会同步到这里；同步时注意 `paths.py` 不随采集器一起覆盖——它的
`BASE_DIR` 语义针对本项目（自身目录）而定。

## 已知限制

- `cron` 调度只支持 5 字段的常见写法（`*/n`、`a-b`、`a-b/n`、逗号列表），
  不支持 `L`、`W`、`#`。
- `group` 字段预留但未启用：当前严格串行，若将来需要并行，按 group 做资源互斥即可。
