# Multi-Market Data Expansion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为系统补齐统一的多市场数据适配与跨市场桥接能力，覆盖 A 股、港股、美股、场外基金、期货，并让 `data`、`industry`、`expert` 三层都能复用。

**Architecture:** 在 `engine/data` 下新增统一资产身份模型、解析器、市场适配器和注册中心；`DataEngine` 新增多市场统一入口，`IndustryEngine` 新增跨市场桥接规则层，`ExpertTools` 复用新的统一查询接口。现有 A 股接口保持兼容，不改原有快照和聚类主链路。

**Tech Stack:** Python, FastAPI, pandas, AKShare, yfinance, pytest

---

### Task 1: Add asset identity and resolver

**Files:**
- Create: `backend/engine/data/market_types.py`
- Create: `backend/engine/data/asset_resolver.py`
- Create: `tests/unit/data/test_asset_resolver.py`

**Step 1: Write the failing test**

Add tests that prove:

- `600519` resolves to `cn/stock`
- `00700` resolves to `hk/stock`
- `AAPL` resolves to `us/stock`
- `161725` resolves to `fund/fund`
- `CL` or `SC` resolves to `futures/future`

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/test_asset_resolver.py -v`

Expected: FAIL because the resolver and shared asset model do not exist.

**Step 3: Write minimal implementation**

- add `AssetIdentity`
- add market and asset type enums/constants
- add `AssetResolver.resolve()` heuristics

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/test_asset_resolver.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/data/market_types.py backend/engine/data/asset_resolver.py tests/unit/data/test_asset_resolver.py
git commit -m "feat(data): add unified asset identity and resolver"
```

### Task 2: Add market adapter abstraction and registry

**Files:**
- Create: `backend/engine/data/market_adapters/base.py`
- Create: `backend/engine/data/market_adapters/cn_adapter.py`
- Create: `backend/engine/data/market_adapters/hk_adapter.py`
- Create: `backend/engine/data/market_adapters/us_adapter.py`
- Create: `backend/engine/data/market_adapters/fund_adapter.py`
- Create: `backend/engine/data/market_adapters/futures_adapter.py`
- Create: `backend/engine/data/market_adapters/registry.py`
- Modify: `backend/pyproject.toml`
- Create: `tests/unit/data/test_market_adapters.py`

**Step 1: Write the failing test**

Add tests that prove:

- registry returns the correct adapter for each market
- adapters expose a unified response contract
- US adapter degrades gracefully when `yfinance` is unavailable

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/test_market_adapters.py -v`

Expected: FAIL because no market adapter layer exists.

**Step 3: Write minimal implementation**

- define adapter base interface
- implement A 股 adapter over current `DataEngine`
- implement港股/基金/期货 adapters over AKShare
- implement美股 adapter over optional `yfinance`
- add `yfinance` dependency

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/test_market_adapters.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/data/market_adapters backend/pyproject.toml tests/unit/data/test_market_adapters.py
git commit -m "feat(data): add market adapter abstraction and registry"
```

### Task 3: Extend DataEngine and data routes with multi-market endpoints

**Files:**
- Modify: `backend/engine/data/engine.py`
- Modify: `backend/engine/data/routes.py`
- Modify: `backend/engine/data/schemas.py`
- Create: `tests/unit/data/test_multi_market_engine.py`
- Create: `tests/unit/data/test_multi_market_routes.py`

**Step 1: Write the failing test**

Add tests that prove:

- `DataEngine.search_assets()` works for `all` and specific markets
- `DataEngine.get_asset_profile/get_asset_quote/get_asset_daily_history()` dispatch correctly
- new `/api/v1/data/assets/*` routes return the unified contract

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/data/test_multi_market_engine.py tests/unit/data/test_multi_market_routes.py -v`

Expected: FAIL because unified multi-market engine and routes do not exist.

**Step 3: Write minimal implementation**

- wire resolver + registry into `DataEngine`
- add multi-market response schemas
- add search/profile/quote/daily routes
- preserve existing A 股 routes unchanged

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/data/test_multi_market_engine.py tests/unit/data/test_multi_market_routes.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/data/engine.py backend/engine/data/routes.py backend/engine/data/schemas.py tests/unit/data/test_multi_market_engine.py tests/unit/data/test_multi_market_routes.py
git commit -m "feat(data): add unified multi-market engine and routes"
```

### Task 4: Add cross-market bridge for industry analysis

**Files:**
- Create: `backend/engine/industry/market_bridge.py`
- Modify: `backend/engine/industry/engine.py`
- Modify: `backend/engine/industry/routes.py`
- Create: `tests/unit/industry/test_market_bridge.py`

**Step 1: Write the failing test**

Add tests that prove:

- bridge returns related assets for industry themes
- bridge can connect commodity futures to A 股 and美股/ETF proxies
- new industry bridge route returns structured results

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/industry/test_market_bridge.py -v`

Expected: FAIL because no bridge layer exists.

**Step 3: Write minimal implementation**

- add rule-based `CrossMarketBridge`
- integrate bridge into `IndustryEngine`
- expose bridge route in `industry/routes.py`

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/industry/test_market_bridge.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/industry/market_bridge.py backend/engine/industry/engine.py backend/engine/industry/routes.py tests/unit/industry/test_market_bridge.py
git commit -m "feat(industry): add cross-market bridge analysis"
```

### Task 5: Reuse unified multi-market queries in ExpertTools

**Files:**
- Modify: `backend/engine/expert/tools.py`
- Create: `tests/unit/expert/test_multi_market_tools.py`

**Step 1: Write the failing test**

Add tests that prove:

- `ExpertTools` can search and query non-A-share assets via unified data methods
- old A 股 actions still work
- bridge action can be surfaced through expert tools

**Step 2: Run test to verify it fails**

Run: `pytest tests/unit/expert/test_multi_market_tools.py -v`

Expected: FAIL because ExpertTools only exposes A 股 data actions.

**Step 3: Write minimal implementation**

- add `search_asset`
- add `get_asset_profile`
- add `get_asset_quote`
- add `get_asset_daily_history`
- add `bridge_market_assets`

**Step 4: Run test to verify it passes**

Run: `pytest tests/unit/expert/test_multi_market_tools.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/engine/expert/tools.py tests/unit/expert/test_multi_market_tools.py
git commit -m "feat(expert): add unified multi-market data tools"
```

### Task 6: Final verification and TODO alignment

**Files:**
- Modify: `TODO.md`

**Step 1: Run multi-market unit tests**

Run: `pytest tests/unit/data/test_asset_resolver.py tests/unit/data/test_market_adapters.py tests/unit/data/test_multi_market_engine.py tests/unit/data/test_multi_market_routes.py tests/unit/industry/test_market_bridge.py tests/unit/expert/test_multi_market_tools.py -v`

Expected: PASS

**Step 2: Run regression verification**

Run: `pytest tests/unit/expert/test_agent.py tests/unit/expert/test_tools.py tests/unit/test_info_refactor.py -v`

Expected: PASS

**Step 3: Run syntax verification**

Run: `python3 -m py_compile backend/engine/data/asset_resolver.py backend/engine/data/market_types.py backend/engine/data/engine.py backend/engine/data/routes.py backend/engine/industry/market_bridge.py backend/engine/industry/engine.py backend/engine/industry/routes.py backend/engine/expert/tools.py`

Expected: PASS

**Step 4: Update TODO**

Mark complete only if these are true:

- `MarketAdapter` 抽象层已存在且覆盖五类市场
- 跨市场联动分析可通过产业链桥接得到结构化结果

**Step 5: Commit**

```bash
git add TODO.md backend/pyproject.toml backend/engine/data backend/engine/industry backend/engine/expert/tools.py tests/unit/data tests/unit/industry tests/unit/expert/test_multi_market_tools.py docs/plans/2026-03-24-multi-market-data-expansion-design.md docs/plans/2026-03-24-multi-market-data-expansion.md
git commit -m "feat(data): complete multi-market data expansion module"
```
