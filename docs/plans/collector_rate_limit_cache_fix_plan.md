# 采集器限流与缓存修复计划

> 依据：EVE 官方第三方开发者文档 [developers.eveonline.com/docs](https://developers.eveonline.com/docs/)
> 主要参考：ESI [Overview](https://developers.eveonline.com/docs/services/esi/overview/)、[Best Practices](https://developers.eveonline.com/docs/services/esi/best-practices/)、[Rate Limiting](https://developers.eveonline.com/docs/services/esi/rate-limiting/)
> 核查对象：`collectors/` 下的全部采集器
> 状态：已实施（P0/P1/P2 全部完成，验收见第六节）

---

## 一、目标与范围

让 ESI 采集器符合官方限流与缓存规范，降低被封禁风险、减少无效流量、保证入库数据一致性。

范围：`collectors/` 下的采集器

- `jita_market_orders_collector_async.py`（订单，分页）
- `jita_market_history_collector_async.py`（历史，含活跃物品类型）
- `item_data_collector_async.py` / `market_group_collector.py`
- `system_data_collector_async.py` / `region_data_collector_async.py` / `constellation_data_collector_async.py`
- `test_jita_active_types.py`（测试脚本，需清理）

不作为本次范围：业务侧分析脚本（`analyze_arbitrage_opportunities_optimized.py`）与 Flask 服务。

---

## 二、核查结论摘要

| 维度 | 结论 |
|---|---|
| 限流 | 部分实现，且参数/计费有错（详见 2.1） |
| 缓存 | 基本未实现，无任何条件请求（详见 2.2） |
| 合规 | 全部采集器缺失 `User-Agent`（详见 2.3） |

### 2.1 限流问题明细

| 严重度 | 问题 | 位置 |
|---|---|---|
| 高 | 令牌桶按「1 请求 = 1 令牌」计费，但文档规定 **2xx 消耗 2 令牌**，允许速率被高估约 2 倍 | 各采集器的 `TokenBucket` |
| 高 | 历史采集器令牌桶形同虚设：`RATE_LIMIT_TOKENS=500000`、周期 60s → 补桶 ~8333/秒 | `jita_market_history_collector_async.py` 配置区（`RATE_LIMIT_TOKENS/PERIOD`） |
| 高 | 订单采集器桶容量前后矛盾：一处封顶 `RATE_LIMIT_TOKENS`(12000)，另一处封顶 `REQUESTS_PER_MINUTE`(800) | `jita_market_orders_collector_async.py` `TokenBucket.consume()` |
| 中 | 桶为全局单一配额，而限流按 `(rate limit group, userID)` 分桶、各组上限不同；未认证按 `sourceIP` 计 | 各采集器 |
| 中 | 订单采集器不使用 `Retry-After`，仅指数退避；`420` 固定 +60s | `jita_market_orders_collector_async.py` 重试分支 |
| 中 | `X-Ratelimit-Remaining` 读取后未据此降速 | 订单采集器、历史采集器 |
| 中 | 仅历史采集器跟踪错误率；其余采集器不记录非 2xx/3xx，触发全局 100/分钟错误限流会导致**所有路由返回 420** | 除 history 外的采集器 |
| 低 | `X-ESI-Error-Limit-Remain/Reset` 响应头未使用 | 全局 |

**已经正确的部分（实施时保留）**
- 所有采集器携带 `X-Compatibility-Date: 2026-06-09`
- 请求前本地令牌桶 + `asyncio.Semaphore` 限并发
- 订单采集器读取 `X-Pages` 分页
- 历史采集器优先用 `Retry-After`、单独处理 `420`
- 历史采集器自建错误时间窗（阈值 50/分钟，比官方 100/分钟更保守）

### 2.2 缓存问题明细

| 严重度 | 问题 | 位置 |
|---|---|---|
| 高 | 生产采集器**无任何** `ETag` / `If-None-Match` / `expires` / `last-modified` 处理，每次全量重下 | 全部采集器 |
| 中 | 测试脚本传空 `If-None-Match: ""`（无效条件头），说明曾尝试未落地 | `test_jita_active_types.py` |
| 中 | 分页一致性未校验：同一分页资源各页 `last-modified` 应一致，订单采集器未检查，翻页期间可能混入两代数据 | `jita_market_orders_collector_async.py` |
| 中 | 静态类采集器（items/systems/regions/constellations/market_groups）全量重拉，未用条件请求 | 对应采集器 |

> 文档要点：`expires` 到期前不应刷新；`ETag` + `If-None-Match` 命中返回 304；**绕过 ESI 缓存可能导致封禁**。

### 2.3 合规问题明细

| 严重度 | 问题 | 位置 |
|---|---|---|
| 中 | 所有采集器 `HEADERS` 未设置 `User-Agent`，文档强烈建议带邮箱 + `AppName/版本` | 各采集器 `HEADERS` 常量 |

---

## 三、修复计划

### P0 — 低风险、直接收益

#### P0-1 统一补 `User-Agent`
- **目标**：所有采集器请求携带规范 UA。
- **实现要点**：
  - 抽取公共常量：`User-Agent: EveHelperMarketCollector/1.0 (<email>; +<repo-url>)`
  - 同步保留 `X-Compatibility-Date`、`Accept`、`Accept-Language`
  - 浏览器类请求不涉及（本项目为服务端脚本），直接用 `User-Agent`
- **涉及文件**：全部采集器的 `HEADERS`
- **验收**：抓包/日志可见 UA 头；`HEADERS` 中不再只有三项。
- **依赖**：无

#### P0-2 修正令牌桶计费与参数
- **目标**：令牌消耗符合官方计费，参数不再自相矛盾。
- **实现要点**：
  - 计费按响应状态码：`2xx=2`、`3xx=1`、`4xx=5`（429 不计）、`5xx=0`；**先请求、后按结果补扣差额**
  - 统一桶容量与上限来源，消除订单采集器「12000 vs 800」矛盾
  - 修正历史采集器 `RATE_LIMIT_TOKENS=500000`（改为与订单一致的合理量级）
  - 可用 `X-Ratelimit-Limit` 动态校正桶上限（可选）
- **涉及文件**：各采集器的 `TokenBucket` 与配置常量
- **验收**：单元自测——模拟 2xx/4xx 序列，扣费数量与文档一致；长时间空转后桶容量不超过设定上限。
- **依赖**：无

### P1 — 稳定性与公共化

#### P1-1 统一退避：优先 `Retry-After`
- **目标**：所有采集器对 429/420 行为一致。
- **实现要点**：
  - 429：优先读 `Retry-After`（秒），回退指数退避 + 抖动
  - 420：最低 60s + 抖动
  - 订单采集器补齐当前缺失的 `Retry-After` 分支
- **涉及文件**：订单采集器、物品/市场组/星系/区域/星座采集器（对齐历史采集器实现）
- **验收**：模拟 429 且带 `Retry-After: 30`，实际等待 ≥30s。

#### P1-2 依据 `X-Ratelimit-Remaining` 主动降速
- **目标**：剩余令牌接近 0 时降低请求速率/并发。
- **实现要点**：
  - 每次响应后更新全局剩余值；低于阈值（如 10%）时对令牌桶加额外延迟或临时降低并发
- **涉及文件**：订单采集器、历史采集器（已读取，补齐动作）
- **验收**：注入人为低 `X-Ratelimit-Remaining`，观测请求间隔被拉长。

#### P1-3 错误率控制公共化
- **目标**：所有采集器共享错误率窗口，避免触发全局 100/分钟错误限流。
- **实现要点**：
  - 抽取公共模块（见第四节 `esi_client.py`），迁移历史采集器的 `manage_error_rate()` 逻辑
  - 所有采集器在非 2xx/3xx 时登记时间戳并计算额外延迟
  - 可选：读取 `X-ESI-Error-Limit-Remain` 做二次校正
- **涉及文件**：新增公共模块 + 全部采集器
- **验收**：并发注入大量 4xx，错误率逼近阈值时日志出现延迟提示且不再出现 420。

### P2 — 收益最大、改动较大

#### P2-1 ETag 条件请求缓存
- **目标**：命中 304 时跳过解析/入库，减少流量与配额消耗。
- **实现要点**：
  - 持久化每路由（key 可为 `url` 或 `url+type_id`）的 `ETag` 与 `last-modified`
  - 存储位置：复用现有 `eve_cache` 库或新建 `http_cache` 表
  - 请求带 `If-None-Match`；响应 304 时跳过入库
  - 遵守 `expires`：到期前不发请求（可选，取决于时效要求）
  - 静态数据（items/systems/regions/constellations/market_groups）优先，收益最高
- **涉及文件**：公共模块 + 全部采集器 + 数据库层（`database_manager.py` 新增表/接口）
- **验收**：连续两次运行，第二次出现 304 且入库行数为 0/仅增量。
- **依赖**：P0-2（令牌桶计费），便于评估节省效果

#### P2-2 分页一致性校验
- **目标**：翻页期间数据不跨代混合。
- **实现要点**：
  - 订单采集：记录首页 `last-modified`，后续页比对，不一致则整轮重取或标记告警
- **涉及文件**：`jita_market_orders_collector_async.py`
- **验收**：构造 `last-modified` 变化的模拟响应，触发重取/告警。
- **依赖**：无

### P2-3 清理测试脚本无效条件头
- **目标**：移除 `test_jita_active_types.py` 的空 `If-None-Match`，避免误导。
- **验收**：文件不再包含空条件头。

---

## 四、建议的公共模块

新增 `collectors/esi_client.py`（或 `common/`），集中：

1. 统一 `HEADERS`（含 `User-Agent`、`X-Compatibility-Date`）
2. `TokenBucket`（按状态码计费，参数可配）
3. 退避策略（`Retry-After` / 420 / 指数退避 + 抖动）
4. 错误率窗口（迁移 `manage_error_rate`）
5. 条件请求封装（ETag 读写）
6. `X-Pages` 分页 + `last-modified` 一致性校验

各采集器改为调用公共模块，消除重复实现与参数漂移。

---

## 五、风险与回滚

| 风险 | 影响 | 缓解 |
|---|---|---|
| 令牌桶计费改严后采集变慢 | 全量采集耗时上升 | 先小流量试跑；必要时按路由组分别设桶 |
| ETag 缓存引入旧数据 | 分析结果滞后 | 对市场订单/历史设置合理 `expires` 上限；提供 `--no-cache` 开关 |
| 公共模块改动面广 | 回归风险 | 分批替换（先订单+历史，再静态类）；保留原函数名兼容 |

回滚：全部改动集中在采集器与新增公共模块，未触及数据库结构（除 P2-1 新增缓存表），可按文件回退。

---

## 六、验收清单

- [x] 所有采集器请求头含规范 `User-Agent`
- [x] 令牌桶按 `2xx=2 / 3xx=1 / 4xx=5 / 5xx=0` 计费，参数无矛盾
- [x] 所有采集器 429 优先使用 `Retry-After`；420 最低 60s
- [x] `X-Ratelimit-Remaining` 低水位触发降速
- [x] 错误率控制为公共实现，所有采集器共享
- [x] 静态类采集器支持 ETag 条件请求，命中 304 跳过入库
- [x] 订单采集校验分页 `last-modified` 一致性
- [x] 测试脚本清理无效条件头
- [ ] 连续两次全量采集：第二次流量/耗时显著下降（需全量采集，未在本次验证中执行）

> 已通过小范围验证：`esi_client.py` 单元逻辑自测（令牌计费/退避/错误率/降速/分页/缓存）与
> 全部采集器模块导入检查（`HEADERS` 含规范 `User-Agent`）均通过，未做全量采集以免拖慢开发。

---

## 附：官方依据

- ESI Overview（版本化 `X-Compatibility-Date`，UTC 11:00 切换）：https://developers.eveonline.com/docs/services/esi/overview/
- Best Practices（User-Agent、错误限流头、缓存 `expires`/`ETag`/`last-modified`）：https://developers.eveonline.com/docs/services/esi/best-practices/
- Rate Limiting（滑动窗口、令牌成本、`X-Ratelimit-*`、`Retry-After`）：https://developers.eveonline.com/docs/services/esi/rate-limiting/
- 分页（x-pages / from-id / cursor-based）：https://developers.eveonline.com/docs/services/esi/pagination/x-pages/
- 静态数据 SDE：https://developers.eveonline.com/docs/services/static-data/