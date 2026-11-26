# 项目根目录重构计划

> 目标：消除根目录混杂、把数据/文档/脚本各归其位、消除「当前工作目录(CWD)依赖」、补齐工程化文件；**全程保证项目仍可运行**。
> 状态：待评审 / 待实施
> 前置说明：**不执行 `git init`**（用户明确要求）。回滚安全网改用「文件备份」：实施前把将被修改的源码文件（`app.py`、`database_manager.py`、各采集器/脚本等）复制到临时目录 `_backup_pre_refactor/`，各阶段依赖它按文件回退；全部完成后由用户决定是否删除该备份。

---

## 一、目标与原则

1. **可运行优先**：每个阶段结束时，`app.py` 能启动、脚本能运行。
2. **单一数据源**：所有路径集中定义（新增 `paths.py`），不再散落 `'eve_items.db'` 这类字面量。
3. **消除 CWD 依赖**：路径一律基于 `__file__` 推导项目根，而不是 `os.path.abspath("xxx.db")`（后者随启动目录变化）。
4. **小步可回滚**：每阶段独立、可按文件回退。
5. **不动的部分**：`.venv/`、`templates/` 的内部结构、已实施的限流/缓存逻辑。

---

## 二、现状盘点

### 2.1 根目录（24 个条目：4 目录 + 20 文件）

| 类别 | 条目 | 问题 |
|---|---|---|
| 入口代码 | `app.py`、`database_manager.py` | 位置合理，保留 |
| 分析/调试脚本 | `analyze_arbitrage_opportunities_optimized.py`(26.7KB)、`debug_arbitrage_analysis.py`(11.8KB) | 应归入 `scripts/` |
| 文档 | `APIs.md`、`wall.md`、`config_description.md`、`esi_api_reference.md`、`collector_rate_limit_cache_fix_plan.md` | 5 个 md 堆在根目录 |
| 数据库 | `eve_items/market_orders/market_history/universe/wallet/cache.db`、`eve_items.db.bak`(218MB)、`items.db`/`market_orders.db`/`eve_market.db`(均为 0 字节) | 数据与代码混放，含垃圾文件 |
| 产物/配置 | `arbitrage_opportunities.json`(2.3MB)、`trade_goods_groups.json` | 生成物与配置混在根 |
| 独立页面 | `eve-station-trading-model.html`(36.5KB) | 原型页，应归档 |
| 凭证 | `esi_credentials.json` | 敏感文件，且**无 `.gitignore`** |
| 目录 | `.venv`、`__pycache__`、`logs`、`templates`、`Test` | `Test/` 命名名不副实 |

### 2.2 `Test/` 目录（20+ 文件）

```
Test/
├─ data_collectors/        ← 7 个生产采集器 + esi_client.py   ★这是生产代码，不是测试
├─ analysis/               ← 4 个查询脚本
├─ cache_management/       ← 4 个脚本
├─ database_maintenance/   ← 2 个脚本
├─ tests/                  ← 2 个真正的测试
└─ __pycache__/
```

**核心命名问题**：`Test/` 下绝大部分是**生产逻辑**（采集器），而真正的测试只有 `Test/tests/` 里 2 个文件。这会让"哪些能删、哪些不能删"变得危险。

### 2.3 缺失的工程化文件

无 `requirements.txt`、`.gitignore`、`README.md`、`.env.example`。

---

## 三、目标结构

```
EVE_helper/
├─ app.py                        # Flask 入口（P4 后为薄入口）
├─ database_manager.py           # 数据库连接
├─ webapp/                       # ★新增（P4）：Flask Blueprint 包
│   ├─ __init__.py / config.py
│   └─ routes/pages|wallet|analysis|market|sso|collectors.py
├─ paths.py                      # ★新增：集中所有路径常量
├─ requirements.txt              # ★新增
├─ README.md                     # ★新增
├─ .gitignore                    # ★新增
├─ .env.example                  # ★新增（不提交真实密钥）
├─ esi_credentials.json          # 保留在根（.gitignore 忽略）
├─ templates/                    # 不变
├─ collectors/                   # ← Test/data_collectors（生产采集器）
│   ├─ esi_client.py
│   └─ *_collector*.py / *data_collector_async.py
├─ scripts/                      # ← 脚本聚合
│   ├─ analyze_arbitrage_opportunities_optimized.py
│   ├─ debug_arbitrage_analysis.py
│   ├─ analysis/
│   ├─ cache_management/
│   └─ database_maintenance/
├─ tests/                        # ← Test/tests
├─ docs/
│   ├─ APIs.md
│   ├─ wall.md
│   ├─ config_description.md
│   ├─ esi_api_reference.md
│   ├─ plans/collector_rate_limit_cache_fix_plan.md
│   └─ prototypes/eve-station-trading-model.html
├─ data/                         # ★数据集中
│   ├─ eve_items.db / eve_market_orders.db / eve_market_history.db
│   ├─ eve_universe.db / eve_wallet.db / eve_cache.db
│   ├─ trade_goods_groups.json
│   ├─ output/arbitrage_opportunities.json
│   └─ backup/eve_items.db.bak
└─ logs/                         # 采集器日志（.gitignore）
```

---

## 四、迁移映射表

| 现路径 | 目标路径 | 需同步改动的代码 |
|---|---|---|
| `Test/data_collectors/` | `collectors/` | 8 处 `sys.path.append(...'..','..')`；`app.py` 的 `COLLECTORS_DIR` |
| `Test/analysis/` | `scripts/analysis/` | 各文件 `DB_FILE = "eve_items.db"` |
| `Test/cache_management/` | `scripts/cache_management/` | 同上 + 1 处 `sys.path.append('..','..')` |
| `Test/database_maintenance/` | `scripts/database_maintenance/` | 同上 |
| `Test/tests/` | `tests/` | `DB_FILE = "eve_items.db"` |
| `analyze_arbitrage_opportunities_optimized.py` | `scripts/` | `sqlite3.connect('eve_items.db')` ×2、`open('arbitrage_opportunities.json')` ×1 |
| `debug_arbitrage_analysis.py` | `scripts/` | `sqlite3.connect('eve_items.db')` ×2 |
| `*.md`（5 个） | `docs/`、`docs/plans/` | 无（仅引用路径变化） |
| `eve-station-trading-model.html` | `docs/prototypes/` | 无 |
| `eve_*.db`（6 个）+ `trade_goods_groups.json` | `data/` | `database_manager.py` 路径表 + 13 处字面量 + `app.py` 读 json 1 处 |
| `arbitrage_opportunities.json` | `data/output/` | `app.py:388` 读、`analyze_*.py:612` 写 |
| `eve_items.db.bak` | `data/backup/` | 无 |
| `items.db`/`market_orders.db`/`eve_market.db`(0B) | **删除** | 无 |
| `__pycache__/`（2 处） | **删除** | 无 |

---

## 五、关键风险

| 编号 | 风险 | 说明 | 缓解 |
|---|---|---|---|
| R1 | **DB 路径依赖 CWD** | `database_manager.py` 用 `os.path.abspath("eve_items.db")`（相对启动目录）；另有 13 处 `sqlite3.connect('eve_items.db')` 字面量；`market_group_collector.py:28` 也自带 `DB_FILE` 字面量 | 新增 `paths.py`，全部改为基于 `__file__` 的绝对路径；分批替换 |
| R2 | **import 深度** | 8 处 `sys.path.append('..','..')` 是为 `Test/data_collectors` 两层深度写的，移动后需改为 `'..'` | 与目录移动同批修改，改完立即 import 校验 |
| R3 | **app.py 常量** | `COLLECTORS_DIR = <root>/Test/data_collectors` | 与目录移动同批修改 |
| R4 | **外部启动方式** | 若你有快捷方式/计划任务/文档记录依赖旧路径，移动后会失效 | 重构后更新 README 并统一以 `python app.py`（在项目根）启动 |
| R5 | **误删生产代码** | `Test/` 命名让人误以为是测试 | 先重命名为 `collectors/`，再清理 |

---

## 六、分阶段计划

### P0 — 工程化基座（零风险，不移动任何代码）

- **目标**：先建立可回滚的安全网与忽略规则。
- **改动**：
  1. 创建临时备份目录 `_backup_pre_refactor/`，复制后续会被修改的源码文件（`app.py`、`database_manager.py`、`Test/data_collectors/market_group_collector.py` 及其余脚本），作为文件级回退安全网。
  2. 新增 `.gitignore`：`.venv/`、`__pycache__/`、`*.pyc`、`logs/`、`esi_credentials.json`、`data/`、`*.db`、`*.bak`、`.env`。
  3. 新增 `requirements.txt`（由现有环境导出后人工精简）。
  4. 新增 `README.md`（启动方式、目录说明、采集器控制台入口 `/collectors`）。
  5. 新增 `.env.example`（`EVE_HELPER_SECRET_KEY=` 等）。
- **涉及文件**：新增 4 个（`.gitignore`/`requirements.txt`/`README.md`/`.env.example`）+ 备份目录 `_backup_pre_refactor/`
- **验收**：`_backup_pre_refactor/` 中存在被修改文件的副本；`.gitignore` 内容覆盖 `.venv/`、`*.db`、`esi_credentials.json`（当前无 git，保留备用）。
- **回滚**：删除新增文件。

### P1 — 清理垃圾 + 文档/产物归档（低风险）

- **目标**：根目录先"减负"，不动代码逻辑。
- **改动**：
  1. 删除 0 字节库：`items.db`、`market_orders.db`、`eve_market.db`（删除前用 `Get-Item` 复核大小为 0）。
  2. 删除 `__pycache__/`（根 + `Test/data_collectors`）。
  3. `eve_items.db.bak` → `data/backup/`（保留，不删）。
  4. 5 个 md → `docs/`（`collector_rate_limit_cache_fix_plan.md` → `docs/plans/`）。
  5. `eve-station-trading-model.html` → `docs/prototypes/`。
  6. `trade_goods_groups.json` → `data/`；`arbitrage_opportunities.json` → `data/output/`。
  7. 同步改 2 处引用：`app.py:388` 读 json、`scripts/analyze_*.py:612` 写 json。
- **验收**：`py_compile app.py`；Flask test client 打 `/`、`/analysis`、`/collectors`、`/api/analysis` 均 200。
- **回滚**：文件移回原位。

### P2 — 数据库集中到 `data/`（中风险，改动面最大）

- **目标**：数据与代码彻底分离，消除 CWD 依赖。
- **改动**：
  1. 新增 `paths.py`：`BASE_DIR = os.path.dirname(os.path.abspath(__file__))`、`DATA_DIR`、`DB_FILES = {...}`、`ARBITRAGE_OUTPUT`。
  2. `database_manager.py` 路径表改用 `paths.DB_FILES`。
  3. 替换 13 处 `sqlite3.connect('eve_items.db')` 字面量（列表见第四节映射表）。
  4. `market_group_collector.py:28` 的 `DB_FILE` 改为 `paths`。
  5. 移动 6 个 db + `trade_goods_groups.json` 到 `data/`。
- **验收**：`/api/data-freshness` 行数与迁移前一致（市场订单 607,497 / 物品 52,626 / 星系 8,490 等）；`scripts/` 下任一脚本可运行。
- **回滚**：db 移回根 + 还原 `database_manager.py`。
- **注意**：迁移期间**不要**同时运行采集器写入。

### P3 — 目录重命名与脚本归类（中风险）

- **目标**：消除 `Test/` 误导性命名。
- **改动**：
  1. `Test/data_collectors/` → `collectors/`；改 8 处 `sys.path.append(...'..','..')` 为 `'..'`；改 `app.py` 的 `COLLECTORS_DIR`。
  2. `Test/analysis|cache_management|database_maintenance/` → `scripts/<同名>/`。
  3. `Test/tests/` → `tests/`；删除空壳 `Test/`。
- **验收**：`python -c "import ..."` 依次导入 7 个采集器 + `esi_client` 成功；采集控制台 `/api/collectors` 仍返回 7 项；**不启动真实采集**。
- **回滚**：目录移回，还原 import 深度。

### P4 — 拆分 `app.py`（中风险，收敛单文件体积）

- **背景**：`app.py` 约 980 行 / 35KB，路由 + SSO + 采集控制 + 市场查询全部挤在一个文件，可维护性差（用户明确要求处理）。
- **目标**：抽出 Flask Blueprint 包 `webapp/`，`app.py` 退化为薄入口，**URL 与启动方式完全不变**（`python app.py` 仍监听 5000）。
- **目标结构**：
  ```
  webapp/
  ├─ __init__.py          # create_app()：注册 CORS、secret_key、各 Blueprint、初始化钱包表
  ├─ config.py            # SSO 常量、读取 esi_credentials.json、secret_key 逻辑
  └─ routes/
      ├─ __init__.py
      ├─ pages.py         # /、/analysis、/wallet、/collectors
      ├─ wallet.py        # /api/wallet/*
      ├─ analysis.py      # /api/analysis
      ├─ market.py        # /api/market_groups、/api/market_items/<id>、/api/market_orders/<id>、/api/market_history/<id>
      ├─ sso.py           # /login、/callback
      └─ collectors.py    # /api/collectors*、/api/data-freshness
  app.py                  # from webapp import create_app; app = create_app(); if __name__=='__main__': app.run(...)
  ```
- **拆分原则**：只搬代码，**不改路由字符串与业务逻辑**；采集器管理的全局状态（进程/状态字典）保持单例语义，避免拆分后出现多份状态。
- **验收**：Flask test client 依次打全部既有路由（`/`、`/analysis`、`/wallet`、`/collectors`、`/api/analysis`、`/api/market_groups`、`/api/collectors`、`/api/data-freshness`）返回 200；`python app.py` 可启动且监听 5000。
- **回滚**：从 `_backup_pre_refactor/app.py` 恢复单文件版本，删除 `webapp/`。

---

## 七、清理清单（拟删除）

| 路径 | 大小 | 理由 |
|---|---|---|
| `items.db` | 0 B | 空文件，遗留 |
| `market_orders.db` | 0 B | 空文件，遗留 |
| `eve_market.db` | 0 B | 空文件，遗留 |
| `__pycache__/`（根） | — | 可再生成 |
| `Test/data_collectors/__pycache__/` | — | 可再生成（含 py312/py313 双版本残留） |

> `eve_items.db.bak`（218MB）**不删**，移到 `data/backup/`，确认无用后再由你决定。

---

## 八、验证策略（小范围、短超时）

- 每阶段结束：`py_compile`（秒级）。
- P1/P3：Flask test client 打本地路由，断言状态码（离线，不触发采集）。
- P2：`sqlite3` 直连新路径校验表行数，与迁移前快照比对。
- 统一：**禁止全量采集测试**；单条命令与测试均限时（≤60s）。

---

## 九、回滚方案

- 全部改动按"目录移动 + 少量常量修改"组织，**无数据结构变更**（不新增/删除表，不迁移数据）。
- 每阶段结束处标记一个可回退点；回退方式为从 `_backup_pre_refactor/` 恢复被修改的文件（不依赖 git）。
- 唯一不可逆操作是 P1 删除 3 个 0 字节文件（已确认无数据）。

---

## 十、验收清单

- [ ] 根目录只剩：入口代码、`paths.py`、工程化文件、`templates/`、`collectors/`、`scripts/`、`tests/`、`docs/`、`data/`、`logs/`
- [ ] `_backup_pre_refactor/` 备份完整保留至重构结束，再行清理
- [ ] `requirements.txt` 可复现当前依赖
- [ ] 所有 DB 访问路径不依赖 CWD（可从任意目录运行 `scripts/` 下脚本）
- [ ] `app.py` 启动正常，`/`、`/analysis`、`/wallet`、`/collectors` 正常
- [ ] `app.py` 已拆分为 `webapp/` Blueprint 包，`app.py` 仅余入口代码
- [ ] `/api/data-freshness` 各数据集行数与重构前一致
- [ ] 7 个采集器模块可正常导入
- [ ] 无 0 字节残留文件、无 `__pycache__` 残留
- [ ] README 记录了新的启动方式与目录说明

---

## 附：不建议在本轮改动

- `.venv/`（保持现状，仅忽略）
- `templates/` 内部结构与页面样式
- `esi_client.py` 的限流/缓存逻辑（已实施且验证）
- 数据库表结构（本轮只搬路径，不动表）