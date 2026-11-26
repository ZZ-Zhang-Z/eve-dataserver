# EVE ESI 常用接口速查

> 自动提取自官方 OpenAPI: https://esi.evetech.net/meta/openapi.json
> 仅收录与市场套利/钱包/资产/工业/合同/结构/技能相关的接口；
> 所有请求需带 `X-Compatibility-Date`（当前 2026-06-09）与 `User-Agent`。

### `GET /characters/{character_id}/assets`
- 说明: Get character assets
- 所需权限: esi-assets.read_assets.v1
- 路径参数: character_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'char-asset', 'max-tokens': 1800, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `POST /characters/{character_id}/assets/locations`
- 说明: Get character asset locations
- 所需权限: esi-assets.read_assets.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-asset', 'max-tokens': 1800, 'window-size': '15m'}, x-compatibility-date=2020-01-01

### `POST /characters/{character_id}/assets/names`
- 说明: Get character asset names
- 所需权限: esi-assets.read_assets.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-asset', 'max-tokens': 1800, 'window-size': '15m'}, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/blueprints`
- 说明: Get blueprints
- 所需权限: esi-characters.read_blueprints.v1
- 路径参数: character_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'char-industry', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/contracts`
- 说明: Get contracts
- 所需权限: esi-contracts.read_character_contracts.v1
- 路径参数: character_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'char-contract', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/contracts/{contract_id}/bids`
- 说明: Get contract bids
- 所需权限: esi-contracts.read_character_contracts.v1
- 路径参数: character_id, contract_id
- 扩展: x-rate-limit={'group': 'char-contract', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/contracts/{contract_id}/items`
- 说明: Get contract items
- 所需权限: esi-contracts.read_character_contracts.v1
- 路径参数: character_id, contract_id
- 扩展: x-rate-limit={'group': 'char-contract', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/industry/jobs`
- 说明: List character industry jobs
- 所需权限: esi-industry.read_character_jobs.v1
- 路径参数: character_id
- 查询参数: include_completed
- 扩展: x-rate-limit={'group': 'char-industry', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/location`
- 说明: Get character location
- 所需权限: esi-location.read_location.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-location', 'max-tokens': 1200, 'window-size': '15m'}, x-cache-age=5, x-server-cache-mode=event-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/loyalty/points`
- 说明: Get loyalty points
- 所需权限: esi-characters.read_loyalty.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-wallet', 'max-tokens': 150, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/mining`
- 说明: Character mining ledger
- 所需权限: esi-industry.read_character_mining.v1
- 路径参数: character_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'char-industry', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=600, x-server-cache-ttl=600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/online`
- 说明: Get character online
- 所需权限: esi-location.read_online.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-location', 'max-tokens': 1200, 'window-size': '15m'}, x-cache-age=60, x-server-cache-mode=event-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/orders`
- 说明: List open orders from a character
- 所需权限: esi-markets.read_character_orders.v1
- 路径参数: character_id
- 扩展: x-cache-age=1200, x-server-cache-ttl=1200, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/orders/history`
- 说明: List historical orders by a character
- 所需权限: esi-markets.read_character_orders.v1
- 路径参数: character_id
- 查询参数: page
- 扩展: x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/ship`
- 说明: Get current ship
- 所需权限: esi-location.read_ship_type.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-location', 'max-tokens': 1200, 'window-size': '15m'}, x-cache-age=5, x-server-cache-ttl=5, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/skills`
- 说明: Get character skills
- 所需权限: esi-skills.read_skills.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-detail', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=60, x-server-cache-mode=event-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/wallet`
- 说明: Get a character's wallet balance
- 所需权限: esi-wallet.read_character_wallet.v1
- 路径参数: character_id
- 扩展: x-rate-limit={'group': 'char-wallet', 'max-tokens': 150, 'window-size': '15m'}, x-cache-age=120, x-server-cache-ttl=120, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/wallet/journal`
- 说明: Get character wallet journal
- 所需权限: esi-wallet.read_character_wallet.v1
- 路径参数: character_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'char-wallet', 'max-tokens': 150, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /characters/{character_id}/wallet/transactions`
- 说明: Get wallet transactions
- 所需权限: esi-wallet.read_character_wallet.v1
- 路径参数: character_id
- 查询参数: from_id
- 扩展: x-rate-limit={'group': 'char-wallet', 'max-tokens': 150, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/assets`
- 说明: Get corporation assets
- 所需权限: esi-assets.read_corporation_assets.v1
- 路径参数: corporation_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'corp-asset', 'max-tokens': 1800, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `POST /corporations/{corporation_id}/assets/locations`
- 说明: Get corporation asset locations
- 所需权限: esi-assets.read_corporation_assets.v1
- 路径参数: corporation_id
- 扩展: x-rate-limit={'group': 'corp-asset', 'max-tokens': 1800, 'window-size': '15m'}, x-compatibility-date=2020-01-01

### `POST /corporations/{corporation_id}/assets/names`
- 说明: Get corporation asset names
- 所需权限: esi-assets.read_corporation_assets.v1
- 路径参数: corporation_id
- 扩展: x-rate-limit={'group': 'corp-asset', 'max-tokens': 1800, 'window-size': '15m'}, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/blueprints`
- 说明: Get corporation blueprints
- 所需权限: esi-corporations.read_blueprints.v1
- 路径参数: corporation_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'corp-industry', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/contracts`
- 说明: Get corporation contracts
- 所需权限: esi-contracts.read_corporation_contracts.v1
- 路径参数: corporation_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'corp-contract', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/contracts/{contract_id}/bids`
- 说明: Get corporation contract bids
- 所需权限: esi-contracts.read_corporation_contracts.v1
- 路径参数: contract_id, corporation_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'corp-contract', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/contracts/{contract_id}/items`
- 说明: Get corporation contract items
- 所需权限: esi-contracts.read_corporation_contracts.v1
- 路径参数: contract_id, corporation_id
- 扩展: x-rate-limit={'group': 'corp-contract', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/divisions`
- 说明: Get corporation divisions
- 所需权限: esi-corporations.read_divisions.v1
- 路径参数: corporation_id
- 扩展: x-rate-limit={'group': 'corp-wallet', 'max-tokens': 300, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/facilities`
- 说明: Get corporation facilities
- 所需权限: esi-corporations.read_facilities.v1
- 路径参数: corporation_id
- 扩展: x-rate-limit={'group': 'corp-structure', 'max-tokens': 300, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/industry/jobs`
- 说明: List corporation industry jobs
- 所需权限: esi-industry.read_corporation_jobs.v1
- 路径参数: corporation_id
- 查询参数: include_completed, page
- 扩展: x-rate-limit={'group': 'corp-industry', 'max-tokens': 600, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/orders`
- 说明: List open orders from a corporation
- 所需权限: esi-markets.read_corporation_orders.v1
- 路径参数: corporation_id
- 查询参数: page
- 扩展: x-cache-age=1200, x-server-cache-ttl=1200, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/orders/history`
- 说明: List historical orders from a corporation
- 所需权限: esi-markets.read_corporation_orders.v1
- 路径参数: corporation_id
- 查询参数: page
- 扩展: x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/structures`
- 说明: Get corporation structures
- 所需权限: esi-corporations.read_structures.v1
- 路径参数: corporation_id
- 查询参数: page
- 扩展: x-rate-limit={'group': 'corp-structure', 'max-tokens': 300, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/wallets`
- 说明: Returns a corporation's wallet balance
- 所需权限: esi-wallet.read_corporation_wallets.v1
- 路径参数: corporation_id
- 扩展: x-rate-limit={'group': 'corp-wallet', 'max-tokens': 300, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/wallets/{division}/journal`
- 说明: Get corporation wallet journal
- 所需权限: esi-wallet.read_corporation_wallets.v1
- 路径参数: corporation_id, division
- 查询参数: page
- 扩展: x-rate-limit={'group': 'corp-wallet', 'max-tokens': 300, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /corporations/{corporation_id}/wallets/{division}/transactions`
- 说明: Get corporation wallet transactions
- 所需权限: esi-wallet.read_corporation_wallets.v1
- 路径参数: corporation_id, division
- 查询参数: from_id
- 扩展: x-rate-limit={'group': 'corp-wallet', 'max-tokens': 300, 'window-size': '15m'}, x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /markets/groups`
- 说明: Get item groups
- 所需权限: 无需认证(公开)
- 扩展: x-compatibility-date=2020-01-01

### `GET /markets/groups/{market_group_id}`
- 说明: Get item group information
- 所需权限: 无需认证(公开)
- 路径参数: market_group_id
- 扩展: x-compatibility-date=2020-01-01

### `GET /markets/structures/{structure_id}`
- 说明: List orders in a structure
- 所需权限: esi-markets.structure_markets.v1
- 路径参数: structure_id
- 查询参数: page
- 扩展: x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /markets/{region_id}/history`
- 说明: List historical market statistics in a region
- 所需权限: 无需认证(公开)
- 路径参数: region_id
- 查询参数: type_id
- 扩展: x-compatibility-date=2020-01-01

### `GET /markets/{region_id}/orders`
- 说明: List orders in a region
- 所需权限: 无需认证(公开)
- 路径参数: region_id
- 查询参数: order_type, page, type_id
- 扩展: x-rate-limit={'group': 'market-order', 'max-tokens': 12000, 'window-size': '15m'}, x-cache-age=300, x-server-cache-ttl=300, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /markets/{region_id}/types`
- 说明: List type IDs relevant to a market
- 所需权限: 无需认证(公开)
- 路径参数: region_id
- 查询参数: page
- 扩展: x-cache-age=600, x-server-cache-ttl=600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /universe/constellations`
- 说明: Get constellations
- 所需权限: 无需认证(公开)
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/constellations/{constellation_id}`
- 说明: Get constellation information
- 所需权限: 无需认证(公开)
- 路径参数: constellation_id
- 扩展: x-compatibility-date=2020-01-01

### `POST /universe/names`
- 说明: Get names and categories for a set of IDs
- 所需权限: 无需认证(公开)
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/regions`
- 说明: Get regions
- 所需权限: 无需认证(公开)
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/regions/{region_id}`
- 说明: Get region information
- 所需权限: 无需认证(公开)
- 路径参数: region_id
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/structures`
- 说明: List all public structures
- 所需权限: 无需认证(公开)
- 查询参数: filter
- 扩展: x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /universe/structures/{structure_id}`
- 说明: Get structure information
- 所需权限: esi-universe.read_structures.v1
- 路径参数: structure_id
- 扩展: x-cache-age=3600, x-server-cache-ttl=3600, x-server-cache-mode=ttl-based, x-compatibility-date=2020-01-01

### `GET /universe/systems`
- 说明: Get solar systems
- 所需权限: 无需认证(公开)
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/systems/{system_id}`
- 说明: Get solar system information
- 所需权限: 无需认证(公开)
- 路径参数: system_id
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/types`
- 说明: Get types
- 所需权限: 无需认证(公开)
- 查询参数: page
- 扩展: x-compatibility-date=2020-01-01

### `GET /universe/types/{type_id}`
- 说明: Get type information
- 所需权限: 无需认证(公开)
- 路径参数: type_id
- 扩展: x-compatibility-date=2020-01-01

<!-- total endpoints: 52 -->