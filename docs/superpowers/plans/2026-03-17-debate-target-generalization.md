# 辩论 Target 泛化 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将辩论系统的 target 从"股票代码"扩展到"板块/行业"和"宏观主题"，支持如"半导体板块值不值得配置"、"美联储降息对 A 股的影响"等辩论。

**Architecture:** 新增 TargetResolver 做三级识别（规则→行业匹配→LLM 分类），Blackboard 扩展 target_type/sector_name/display_name 字段，DataFetcher 新增 get_sector_overview/get_macro_context 两个数据源，personas.py 按 target_type 动态切换白名单和 prompt 模板，前端 InputBar 放开输入限制。

**Tech Stack:** Python 3.11, FastAPI, Pydantic, pytest, Next.js/TypeScript, Zustand

**Spec:** `docs/superpowers/specs/2026-03-17-debate-target-generalization-design.md`

---

## File Structure

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `engine/agent/target_resolver.py` | TargetResolver 类：三级识别 target 类型 |
| 新建 | `engine/tests/agent/test_target_resolver.py` | TargetResolver 单元测试 |
| 修改 | `engine/agent/schemas.py:112-145` | Blackboard 新增 target_type/sector_name/display_name |
| 修改 | `engine/agent/personas.py:107-128,287-391` | DEBATE_DATA_WHITELIST_BY_TYPE 替换静态白名单；build_debate_system_prompt 注入 target_type 前缀；build_data_request_prompt 按 target_type 调整 |
| 修改 | `engine/agent/data_fetcher.py:124-148` | 新增 get_sector_overview/get_macro_context；fetch_by_request 新增 NO_CODE_ACTIONS 守卫 |
| 修改 | `engine/agent/debate.py:30-36,165-178,609-678,684-734,670-678,1396-1470` | run_debate 调用 TargetResolver；fetch_initial_data 按类型分支；generate_industry_cognition 接收 target_override；validate_data_requests 接收 target_type；ACTION_TITLE_MAP 新增条目 |
| 修改 | `engine/api/routes/debate.py:17-47,156-188` | DebateRequest 新增 target 字段；debate_id 清洗；summarize 去掉"股票"限定词 |
| 修改 | `web/stores/useDebateStore.ts:35-54,102-115,289-304` | startDebate 参数 code→target；debate_start handler 读取 display_name/target_type |
| 修改 | `web/components/debate/InputBar.tsx:17,56-65,120` | placeholder/label 更新；移除格式校验 |

---

## Chunk 1: Schemas + TargetResolver（纯数据层，无副作用）

### Task 1: Blackboard schema 扩展

**Files:**
- Modify: `engine/agent/schemas.py:112-145`

- [x] **Step 1: Write the failing test**

```python
# engine/tests/agent/test_debate_schemas.py — 追加
def test_blackboard_target_type_defaults():
    bb = Blackboard(target="600519", debate_id="test_001")
    assert bb.target_type == "stock"
    assert bb.sector_name == ""
    assert bb.display_name == ""
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_debate_schemas.py::test_blackboard_target_type_defaults -v`
Expected: FAIL — `Blackboard` has no field `target_type`

- [x] **Step 3: Add fields to Blackboard**

In `engine/agent/schemas.py`, inside `class Blackboard`, after line 118 (`mode: Literal[...] = "standard"`), add:

```python
    target_type: Literal["stock", "sector", "macro"] = "stock"
    sector_name: str = ""           # sector 时的规范化行业名
    display_name: str = ""          # prompt 用展示名，也写入 debate_start SSE 事件
```

- [x] **Step 4: Run test to verify it passes**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_debate_schemas.py::test_blackboard_target_type_defaults -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add engine/agent/schemas.py engine/tests/agent/test_debate_schemas.py
git commit -m "feat(schemas): Blackboard 新增 target_type/sector_name/display_name 字段"
```

---

### Task 2: TargetResolver — 规则识别（无 LLM）

**Files:**
- Create: `engine/agent/target_resolver.py`
- Create: `engine/tests/agent/test_target_resolver.py`

- [x] **Step 1: Write the failing tests for rule-based resolution**

```python
# engine/tests/agent/test_target_resolver.py
"""TargetResolver 单元测试"""
import pytest
from unittest.mock import MagicMock, patch
from agent.target_resolver import TargetResolver, TargetResolution


class TestTargetResolverRules:
    """规则识别（不依赖 LLM）"""

    def test_six_digit_code_is_stock(self):
        resolver = TargetResolver()
        result = resolver._resolve_by_rules("600519")
        assert result is not None
        assert result.target_type == "stock"
        assert result.resolved_code == "600519"

    def test_six_digit_with_spaces(self):
        resolver = TargetResolver()
        result = resolver._resolve_by_rules("  000001  ")
        assert result is not None
        assert result.target_type == "stock"
        assert result.resolved_code == "000001"

    @patch("agent.target_resolver.TargetResolver._get_industry_set")
    def test_known_industry_is_sector(self, mock_ind):
        mock_ind.return_value = {"半导体", "白酒", "新能源"}
        resolver = TargetResolver()
        result = resolver._resolve_by_rules("半导体")
        assert result is not None
        assert result.target_type == "sector"
        assert result.sector_name == "半导体"

    @patch("agent.target_resolver.TargetResolver._get_industry_set")
    def test_substring_match_industry(self, mock_ind):
        mock_ind.return_value = {"半导体", "白酒", "新能源汽车"}
        resolver = TargetResolver()
        result = resolver._resolve_by_rules("新能源")
        assert result is not None
        assert result.target_type == "sector"
        assert result.sector_name == "新能源汽车"

    @patch("agent.target_resolver.TargetResolver._get_industry_set")
    def test_no_match_returns_none(self, mock_ind):
        mock_ind.return_value = {"半导体", "白酒"}
        resolver = TargetResolver()
        result = resolver._resolve_by_rules("美联储降息")
        assert result is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestTargetResolverRules -v`
Expected: FAIL — module `agent.target_resolver` does not exist

- [x] **Step 3: Implement TargetResolver with rule-based resolution**

```python
# engine/agent/target_resolver.py
"""Target 类型解析器 — 将辩论标的识别为 stock / sector / macro"""

import re
from dataclasses import dataclass

from loguru import logger


@dataclass
class TargetResolution:
    """解析结果"""
    target_type: str   # "stock" | "sector" | "macro"
    resolved_code: str = ""    # 仅 stock 时有值
    sector_name: str = ""      # 仅 sector 时有值
    display_name: str = ""     # prompt 展示名


class TargetResolver:
    """三级识别：规则 → 行业匹配 → LLM 分类"""

    def __init__(self, llm=None):
        self._llm = llm  # BaseLLMProvider | None

    def _get_industry_set(self) -> set[str]:
        """从 DataEngine profiles 获取所有行业名"""
        try:
            from data_engine import get_data_engine
            profiles = get_data_engine().get_profiles()
            return {
                info.get("industry", "")
                for info in profiles.values()
                if info.get("industry")
            }
        except Exception as e:
            logger.warning(f"获取行业列表失败: {e}")
            return set()

    def _resolve_by_rules(self, target: str) -> TargetResolution | None:
        """规则识别，返回 None 表示规则无法判断"""
        stripped = target.strip()

        # 1. 6位数字 → stock
        if re.fullmatch(r"\d{6}", stripped):
            return TargetResolution(
                target_type="stock",
                resolved_code=stripped,
                display_name=self._get_stock_name(stripped) or stripped,
            )

        # 2. 行业列表精确/子串匹配 → sector
        industries = self._get_industry_set()
        # 精确匹配优先
        if stripped in industries:
            return TargetResolution(
                target_type="sector",
                sector_name=stripped,
                display_name=stripped,
            )
        # 子串匹配：target 是某行业名的子串，或某行业名是 target 的子串
        for ind in industries:
            if stripped in ind or ind in stripped:
                return TargetResolution(
                    target_type="sector",
                    sector_name=ind,
                    display_name=ind,
                )

        return None

    def _get_stock_name(self, code: str) -> str:
        """从 profiles 获取股票名称"""
        try:
            from data_engine import get_data_engine
            profile = get_data_engine().get_profile(code)
            return profile.get("name", "") if profile else ""
        except Exception:
            return ""

    async def resolve(self, target: str) -> TargetResolution:
        """完整解析流程"""
        # 1. 规则识别
        result = self._resolve_by_rules(target)
        if result:
            logger.info(f"TargetResolver 规则识别: '{target}' → {result.target_type}")
            return result

        # 2. LLM 分类（如果可用）
        if self._llm:
            result = await self._resolve_by_llm(target)
            if result:
                return result

        # 3. fallback → macro
        logger.info(f"TargetResolver fallback: '{target}' → macro")
        return TargetResolution(
            target_type="macro",
            display_name=target,
        )

    async def _resolve_by_llm(self, target: str) -> TargetResolution | None:
        """LLM 分类 fallback（非流式，approved exception）"""
        prompt = f"判断以下辩论题目属于哪类：股票/板块/宏观主题，只输出一个词。题目：{target}"
        try:
            from llm.providers import ChatMessage
            response = await self._llm.chat(
                [ChatMessage(role="user", content=prompt)]
            )
            category = response.strip()
            logger.info(f"TargetResolver LLM 分类: '{target}' → '{category}'")

            if "股票" in category:
                # 尝试解析股票代码
                code = self._resolve_stock_code(target)
                if code:
                    return TargetResolution(
                        target_type="stock",
                        resolved_code=code,
                        display_name=self._get_stock_name(code) or target,
                    )
                # 解析失败 → macro fallback
                return None

            if "板块" in category:
                return TargetResolution(
                    target_type="sector",
                    sector_name=target,
                    display_name=target,
                )

            if "宏观" in category:
                return TargetResolution(
                    target_type="macro",
                    display_name=target,
                )

            return None  # 无法识别，交给外层 fallback

        except Exception as e:
            logger.warning(f"TargetResolver LLM 分类失败: {e}")
            return None

    def _resolve_stock_code(self, target: str) -> str:
        """复用现有 resolve_stock_code 逻辑"""
        try:
            from data_engine import get_data_engine
            profiles = get_data_engine().get_profiles()
            target_lower = target.lower()
            for code, info in profiles.items():
                name = info.get("name", "")
                if name and (name in target or target_lower in name.lower()):
                    return code
        except Exception as e:
            logger.warning(f"_resolve_stock_code 失败: {e}")
        return ""
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestTargetResolverRules -v`
Expected: PASS (5 tests)

- [x] **Step 5: Commit**

```bash
git add engine/agent/target_resolver.py engine/tests/agent/test_target_resolver.py
git commit -m "feat(target_resolver): TargetResolver 规则识别 — stock/sector 判定"
```

---

### Task 3: TargetResolver — LLM 分类 + async resolve

**Files:**
- Modify: `engine/tests/agent/test_target_resolver.py`
- (No code changes to target_resolver.py — already implemented above)

- [x] **Step 1: Write async tests for LLM classification path**

Append to `engine/tests/agent/test_target_resolver.py`:

```python
@pytest.mark.asyncio
class TestTargetResolverLLM:
    """LLM 分类路径"""

    async def test_llm_classifies_macro(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "宏观主题"
        resolver = TargetResolver(llm=mock_llm)
        with patch.object(resolver, "_get_industry_set", return_value=set()):
            result = await resolver.resolve("美联储降息对A股的影响")
        assert result.target_type == "macro"
        assert result.display_name == "美联储降息对A股的影响"

    async def test_llm_classifies_sector(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "板块"
        resolver = TargetResolver(llm=mock_llm)
        with patch.object(resolver, "_get_industry_set", return_value=set()):
            result = await resolver.resolve("AI概念股")
        assert result.target_type == "sector"
        assert result.sector_name == "AI概念股"

    async def test_llm_failure_falls_back_to_macro(self):
        mock_llm = AsyncMock()
        mock_llm.chat.side_effect = Exception("LLM down")
        resolver = TargetResolver(llm=mock_llm)
        with patch.object(resolver, "_get_industry_set", return_value=set()):
            result = await resolver.resolve("一些随机文本")
        assert result.target_type == "macro"

    async def test_no_llm_falls_back_to_macro(self):
        resolver = TargetResolver(llm=None)
        with patch.object(resolver, "_get_industry_set", return_value=set()):
            result = await resolver.resolve("一些随机文本")
        assert result.target_type == "macro"

    async def test_llm_stock_with_code_resolution(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "股票"
        resolver = TargetResolver(llm=mock_llm)
        with patch.object(resolver, "_get_industry_set", return_value=set()):
            with patch.object(resolver, "_resolve_stock_code", return_value="600519"):
                with patch.object(resolver, "_get_stock_name", return_value="贵州茅台"):
                    result = await resolver.resolve("茅台")
        assert result.target_type == "stock"
        assert result.resolved_code == "600519"

    async def test_llm_stock_no_code_falls_to_macro(self):
        mock_llm = AsyncMock()
        mock_llm.chat.return_value = "股票"
        resolver = TargetResolver(llm=mock_llm)
        with patch.object(resolver, "_get_industry_set", return_value=set()):
            with patch.object(resolver, "_resolve_stock_code", return_value=""):
                result = await resolver.resolve("不存在的股票")
        assert result.target_type == "macro"
```

Add imports at top of test file:

```python
from unittest.mock import AsyncMock, patch
import pytest
```

- [x] **Step 2: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py -v`
Expected: PASS (all 11 tests)

- [x] **Step 3: Commit**

```bash
git add engine/tests/agent/test_target_resolver.py
git commit -m "test(target_resolver): LLM 分类路径 + fallback 测试"
```

<!-- CHUNK_1_END -->

---

## Chunk 2: DataFetcher 扩展 + Personas 白名单重构

### Task 4: DataFetcher — get_sector_overview + get_macro_context

**Files:**
- Modify: `engine/agent/data_fetcher.py`
- Modify: `engine/tests/agent/test_target_resolver.py` (追加 DataFetcher 测试)

- [x] **Step 1: Write failing tests for get_sector_overview**

Append to `engine/tests/agent/test_target_resolver.py`:

```python
from agent.data_fetcher import DataFetcher


class TestDataFetcherSectorMacro:
    """get_sector_overview / get_macro_context 测试"""

    @patch("agent.data_fetcher.importlib")
    def test_get_sector_overview_returns_structure(self, mock_imp):
        """sector overview 返回正确结构"""
        # mock IndustryEngine.get_industry_stocks
        mock_ie = MagicMock()
        mock_ie.get_industry_stocks.return_value = ["600519", "000858"]
        mock_mod = MagicMock()
        mock_mod.get_industry_engine.return_value = mock_ie

        # mock DataEngine.get_snapshot + get_profiles
        import pandas as pd
        mock_de = MagicMock()
        mock_de.get_snapshot.return_value = pd.DataFrame({
            "code": ["600519", "000858"],
            "pct_chg": [2.5, -1.0],
            "pe_ttm": [30.0, 25.0],
            "total_mv": [20000.0, 5000.0],
        })
        mock_de.get_profiles.return_value = {
            "600519": {"name": "贵州茅台"},
            "000858": {"name": "五粮液"},
        }
        mock_de_mod = MagicMock()
        mock_de_mod.get_data_engine.return_value = mock_de

        def side_effect(name):
            if name == "industry_engine":
                return mock_mod
            if name == "data_engine":
                return mock_de_mod
            return MagicMock()

        mock_imp.import_module.side_effect = side_effect

        fetcher = DataFetcher()
        result = fetcher.get_sector_overview(sector="白酒")
        assert "sector" in result
        assert "top_stocks" in result
        assert "avg_pct_chg" in result

    def test_get_macro_context_returns_structure(self):
        """macro context 返回正确结构"""
        import pandas as pd
        mock_de = MagicMock()
        mock_de.get_snapshot.return_value = pd.DataFrame({
            "code": ["600519", "000001"],
            "pct_chg": [2.0, -1.0],
            "industry": ["白酒", "银行"],
        })

        fetcher = DataFetcher()
        with patch("agent.data_fetcher.importlib") as mock_imp:
            mock_mod = MagicMock()
            mock_mod.get_data_engine.return_value = mock_de
            mock_imp.import_module.return_value = mock_mod
            result = fetcher.get_macro_context(query="宏观测试")

        assert "advance_decline_ratio" in result
        assert "sector_heatmap" in result
        assert "note" in result
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestDataFetcherSectorMacro -v`
Expected: FAIL — `DataFetcher` has no method `get_sector_overview`

- [x] **Step 3: Implement get_sector_overview and get_macro_context**

Add to `engine/agent/data_fetcher.py`, after `get_restrict_stock_unlock` method (after line 395), before the end of the class:

```python
    def get_sector_overview(self, sector: str) -> dict:
        """板块概览：成分股 Top 5 + 平均涨跌幅"""
        try:
            from industry_engine import get_industry_engine
            from data_engine import get_data_engine
            ie = get_industry_engine()
            de = get_data_engine()
            codes = ie.get_industry_stocks(sector)
            if not codes:
                return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}
            snapshot = de.get_snapshot()
            if snapshot.empty or "code" not in snapshot.columns:
                return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}
            sector_df = snapshot[snapshot["code"].isin(codes)]
            if sector_df.empty:
                return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}
            avg_pct = float(sector_df["pct_chg"].mean()) if "pct_chg" in sector_df.columns else 0.0
            # Top 5 by total_mv
            sort_col = "total_mv" if "total_mv" in sector_df.columns else "pct_chg"
            top5 = sector_df.nlargest(5, sort_col)
            profiles = de.get_profiles()
            top_stocks = []
            for _, row in top5.iterrows():
                code = row["code"]
                name = profiles.get(code, {}).get("name", code)
                top_stocks.append({
                    "code": code,
                    "name": name,
                    "pct_chg": row.get("pct_chg", 0.0),
                    "pe_ttm": row.get("pe_ttm", None),
                    "total_mv": row.get("total_mv", None),
                })
            return {"sector": sector, "top_stocks": top_stocks, "avg_pct_chg": round(avg_pct, 4)}
        except Exception as e:
            logger.warning(f"get_sector_overview 失败 [{sector}]: {e}")
            return {"sector": sector, "top_stocks": [], "avg_pct_chg": 0.0}

    def get_macro_context(self, query: str) -> dict:
        """宏观上下文（best-effort）：涨跌比 + 行业热力图"""
        try:
            from data_engine import get_data_engine
            snapshot = get_data_engine().get_snapshot()
            result: dict = {"advance_decline_ratio": None, "sector_heatmap": None,
                            "note": "宏观数据为 best-effort，不含北向资金等市场级别接口"}
            if snapshot.empty or "pct_chg" not in snapshot.columns:
                return result
            # 涨跌比
            total = len(snapshot)
            up = int((snapshot["pct_chg"] > 0).sum())
            result["advance_decline_ratio"] = round(up / max(total, 1), 4)
            # 行业板块涨跌幅排行
            if "industry" in snapshot.columns:
                grouped = snapshot[snapshot["industry"].notna() & (snapshot["industry"] != "")]
                if not grouped.empty:
                    heatmap = (
                        grouped.groupby("industry")["pct_chg"]
                        .mean()
                        .sort_values(ascending=False)
                        .head(20)
                    )
                    result["sector_heatmap"] = [
                        {"industry": ind, "avg_pct_chg": round(val, 4)}
                        for ind, val in heatmap.items()
                    ]
            return result
        except Exception as e:
            logger.warning(f"get_macro_context 失败: {e}")
            return {"advance_decline_ratio": None, "sector_heatmap": None,
                    "note": "宏观数据暂不可用"}
```

- [x] **Step 4: Add to SELF_DISPATCH and NO_CODE_ACTIONS**

In `engine/agent/data_fetcher.py`, add `get_sector_overview` and `get_macro_context` to `SELF_DISPATCH` (line 15):

```python
SELF_DISPATCH: set[str] = {
    "get_financials", "get_money_flow", "get_northbound_holding",
    "get_margin_balance", "get_turnover_rate", "get_restrict_stock_unlock",
    "get_daily_history", "get_technical_indicators", "get_factor_scores",
    "get_sector_overview", "get_macro_context",
}
```

Add `NO_CODE_ACTIONS` constant after `SELF_DISPATCH`:

```python
# 不需要 code 参数的 action（跳过 code 解析守卫）
NO_CODE_ACTIONS: set[str] = {"get_sector_overview", "get_macro_context"}
```

Modify `fetch_by_request` (line 124) to skip code resolution for NO_CODE_ACTIONS:

```python
    async def fetch_by_request(self, req) -> Any:
        """按 DataRequest 路由到对应引擎方法或 DataFetcher 自身方法"""
        import re
        # NO_CODE_ACTIONS 跳过 code 解析守卫
        if req.action not in NO_CODE_ACTIONS:
            if "code" in req.params and not re.fullmatch(r"\d{6}", str(req.params["code"]).strip()):
                resolved = self._resolve_code(req.params["code"])
                if resolved:
                    req.params = {**req.params, "code": resolved}
                else:
                    return {"error": f"无法解析股票代码: {req.params['code']}"}
        if req.action in ACTION_DISPATCH:
            # ... (existing logic unchanged)
```

- [x] **Step 5: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestDataFetcherSectorMacro -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add engine/agent/data_fetcher.py engine/tests/agent/test_target_resolver.py
git commit -m "feat(data_fetcher): get_sector_overview + get_macro_context + NO_CODE_ACTIONS 守卫"
```

---

### Task 5: Personas — DEBATE_DATA_WHITELIST_BY_TYPE 替换静态白名单

**Files:**
- Modify: `engine/agent/personas.py:107-131`

- [x] **Step 1: Write failing test**

Append to `engine/tests/agent/test_target_resolver.py`:

```python
class TestWhitelistByType:
    def test_stock_whitelist_matches_original(self):
        from agent.personas import DEBATE_DATA_WHITELIST_BY_TYPE
        stock_wl = DEBATE_DATA_WHITELIST_BY_TYPE["stock"]
        assert "get_stock_info" in stock_wl["bull_expert"]
        assert "get_capital_structure" in stock_wl["bull_expert"]

    def test_sector_whitelist_has_sector_overview(self):
        from agent.personas import DEBATE_DATA_WHITELIST_BY_TYPE
        sector_wl = DEBATE_DATA_WHITELIST_BY_TYPE["sector"]
        assert "get_sector_overview" in sector_wl["bull_expert"]
        assert "get_capital_structure" not in sector_wl["bull_expert"]

    def test_macro_whitelist_has_macro_context(self):
        from agent.personas import DEBATE_DATA_WHITELIST_BY_TYPE
        macro_wl = DEBATE_DATA_WHITELIST_BY_TYPE["macro"]
        assert "get_macro_context" in macro_wl["bull_expert"]
        assert "get_stock_info" not in macro_wl["bull_expert"]
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestWhitelistByType -v`
Expected: FAIL — `DEBATE_DATA_WHITELIST_BY_TYPE` does not exist

- [x] **Step 3: Replace DEBATE_DATA_WHITELIST with DEBATE_DATA_WHITELIST_BY_TYPE**

In `engine/agent/personas.py`, replace lines 105-128 (`DEBATE_DATA_WHITELIST`) with:

```python
# ── 辩论数据请求白名单（按 target_type 动态切换）──────────────

DEBATE_DATA_WHITELIST_BY_TYPE: dict[str, dict[str, list[str]]] = {
    "stock": {
        "bull_expert": [
            "get_stock_info", "get_daily_history", "get_factor_scores",
            "get_news", "get_announcements", "get_technical_indicators",
            "get_cluster_for_stock", "get_financials", "get_turnover_rate",
            "get_industry_cognition", "get_capital_structure",
        ],
        "bear_expert": [
            "get_stock_info", "get_daily_history", "get_factor_scores",
            "get_news", "get_announcements", "get_technical_indicators",
            "get_cluster_for_stock", "get_financials", "get_restrict_stock_unlock",
            "get_margin_balance", "get_industry_cognition", "get_capital_structure",
        ],
        "retail_investor": ["get_news", "get_money_flow"],
        "smart_money": [
            "get_technical_indicators", "get_factor_scores",
            "get_money_flow", "get_northbound_holding", "get_margin_balance",
            "get_turnover_rate", "get_capital_structure",
        ],
    },
    "sector": {
        "bull_expert": ["get_sector_overview", "get_industry_cognition", "get_news"],
        "bear_expert": ["get_sector_overview", "get_industry_cognition", "get_news"],
        "retail_investor": ["get_news"],
        "smart_money": ["get_sector_overview", "get_macro_context"],
    },
    "macro": {
        "bull_expert": ["get_macro_context", "get_industry_cognition", "get_news"],
        "bear_expert": ["get_macro_context", "get_industry_cognition", "get_news"],
        "retail_investor": ["get_news"],
        "smart_money": ["get_macro_context"],
    },
}

# 向后兼容：stock 白名单作为默认
DEBATE_DATA_WHITELIST = DEBATE_DATA_WHITELIST_BY_TYPE["stock"]
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestWhitelistByType -v`
Expected: PASS

- [x] **Step 5: Run existing debate tests to verify backward compatibility**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_debate_core.py -v`
Expected: PASS (existing tests still work because `DEBATE_DATA_WHITELIST` is re-exported)

- [x] **Step 6: Commit**

```bash
git add engine/agent/personas.py engine/tests/agent/test_target_resolver.py
git commit -m "feat(personas): DEBATE_DATA_WHITELIST_BY_TYPE — 按 target_type 动态白名单"
```

---

### Task 6: Personas — build_debate_system_prompt 注入 target_type 前缀

**Files:**
- Modify: `engine/agent/personas.py:287-331`

- [x] **Step 1: Write failing test**

Append to `engine/tests/agent/test_target_resolver.py`:

```python
class TestBuildDebateSystemPromptTargetType:
    def test_stock_prompt_unchanged(self):
        from agent.personas import build_debate_system_prompt
        prompt = build_debate_system_prompt("bull_expert", "600519", False)
        assert "看多" in prompt
        # stock 不注入前缀
        assert "板块" not in prompt[:100]

    def test_sector_prompt_has_prefix(self):
        from agent.personas import build_debate_system_prompt
        prompt = build_debate_system_prompt("bull_expert", "半导体", False, target_type="sector")
        assert "板块" in prompt
        assert "景气度" in prompt

    def test_macro_prompt_has_prefix(self):
        from agent.personas import build_debate_system_prompt
        prompt = build_debate_system_prompt("bull_expert", "美联储降息", False, target_type="macro")
        assert "宏观主题" in prompt
        assert "传导链" in prompt

    def test_observer_sector_has_prefix(self):
        from agent.personas import build_debate_system_prompt
        prompt = build_debate_system_prompt("retail_investor", "白酒", False, target_type="sector")
        assert "板块" in prompt
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestBuildDebateSystemPromptTargetType -v`
Expected: FAIL — `build_debate_system_prompt` doesn't accept `target_type`

- [x] **Step 3: Modify build_debate_system_prompt**

In `engine/agent/personas.py`, change the function signature and add prefix logic:

```python
def build_debate_system_prompt(role: str, target: str, is_final_round: bool, target_type: str = "stock") -> str:
    """构建辩论角色的 system prompt"""
    final_note = _FINAL_ROUND_NOTE if is_final_round else ""

    # target_type 前缀
    prefix = ""
    if target_type == "sector":
        prefix = f"你正在辩论的是 **{target}** 板块的投资价值。请从板块整体景气度、龙头股表现、产业链位置、估值分位等角度论证，引用黑板上的板块成分股数据。\n\n"
    elif target_type == "macro":
        prefix = f"你正在辩论的是宏观主题 **{target}**。请从宏观经济指标、政策预期、市场影响传导链等角度论证，结合行业认知中的周期定位和催化剂。\n\n"

    if role == "bull_expert":
        return prefix + _DEBATER_SYSTEM_TEMPLATE.format(
            stance_desc="你是一位资深金融专业人士，在本次辩论中扮演多头（看多）角色。",
            direction="看多", target=target, bias="乐观",
            final_round_note=final_note,
        )
    elif role == "bear_expert":
        return prefix + _DEBATER_SYSTEM_TEMPLATE.format(
            stance_desc="你是一位资深金融专业人士，在本次辩论中扮演空头（看空）角色。",
            direction="看空", target=target, bias="悲观",
            final_round_note=final_note,
        )
    elif role == "retail_investor":
        return prefix + _OBSERVER_SYSTEM_TEMPLATE.format(
            observer_desc=(
                "你是市场散户的代表，代表大众投资者的情绪和行为视角。\n\n"
                "## 你的视角\n"
                "- 关注市场热度、讨论热度、追涨杀跌行为模式\n"
                "- 你的情绪往往是反向指标（极度乐观时可能是见顶信号）\n"
                "- 你不需要选边站，只提供你观察到的市场情绪信息"
            ),
            perspective="市场情绪",
            final_round_note=final_note,
        )
    elif role == "smart_money":
        return prefix + _OBSERVER_SYSTEM_TEMPLATE.format(
            observer_desc=(
                "你是市场主力资金的代表，代表机构和大资金的行为视角。\n\n"
                "## 你的视角\n"
                "- 关注量价关系、大单方向、资金流向等技术面资金信号\n"
                "- 你的判断基于可观察的资金行为数据，不基于基本面或消息面\n"
                "- 你不需要选边站，只提供你观察到的资金面信息"
            ),
            perspective="资金面",
            final_round_note=final_note,
        )
    elif role == "judge":
        return JUDGE_SYSTEM_PROMPT
    else:
        raise ValueError(f"未知辩论角色: {role}")
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestBuildDebateSystemPromptTargetType -v`
Expected: PASS

- [x] **Step 5: Run existing tests to verify backward compatibility**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/ -v`
Expected: PASS (existing callers pass no `target_type`, defaults to "stock")

- [x] **Step 6: Commit**

```bash
git add engine/agent/personas.py engine/tests/agent/test_target_resolver.py
git commit -m "feat(personas): build_debate_system_prompt 注入 target_type 前缀"
```

---

### Task 7: Personas — build_data_request_prompt 按 target_type 调整

**Files:**
- Modify: `engine/agent/personas.py:333-391`

- [x] **Step 1: Write failing test**

Append to `engine/tests/agent/test_target_resolver.py`:

```python
class TestBuildDataRequestPromptTargetType:
    def test_stock_prompt_has_code_param(self):
        from agent.personas import build_data_request_prompt
        prompt = build_data_request_prompt("bull_expert", "600519", 1, "context", target_type="stock")
        assert '"code": "600519"' in prompt

    def test_sector_prompt_has_sector_param(self):
        from agent.personas import build_data_request_prompt
        prompt = build_data_request_prompt("bull_expert", "半导体", 1, "context", target_type="sector")
        assert '"sector": "半导体"' in prompt
        assert "get_sector_overview" in prompt

    def test_macro_prompt_has_query_param(self):
        from agent.personas import build_data_request_prompt
        prompt = build_data_request_prompt("bull_expert", "美联储降息", 1, "context", target_type="macro")
        assert '"query": "美联储降息"' in prompt
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestBuildDataRequestPromptTargetType -v`
Expected: FAIL — `build_data_request_prompt` doesn't accept `target_type`

- [x] **Step 3: Modify build_data_request_prompt**

In `engine/agent/personas.py`, update `_DATA_REQUEST_TEMPLATE` params example line (line 356) and `build_data_request_prompt`:

Replace the `_DATA_REQUEST_TEMPLATE` example line:
```python
示例：
[{{"engine": "data", "action": "get_financials", "params": {{"code": "{target}"}}}}, {{"engine": "info", "action": "get_news", "params": {{"code": "{target}"}}}}]

注意：params 中 code 字段必须填写股票代码 {target}。最多请求 {max_requests} 条。"""
```

With a `{params_example}` placeholder:

```python
示例：
{params_example}

注意：{params_note}最多请求 {max_requests} 条。"""
```

Update `build_data_request_prompt`:

```python
# 数据动作价值说明 — 新增 sector/macro 条目
_ACTION_VALUE_DESC: dict[str, str] = {
    # ... existing entries unchanged ...
    "get_sector_overview": "板块概览（成分股 Top5、平均涨跌幅）— 板块整体表现",
    "get_macro_context": "宏观上下文（涨跌比、行业热力图）— 市场全局视角",
    "get_capital_structure": "资金构成（主力/北向/融资融券/换手率）— 资金面全景",
    "get_industry_cognition": "行业产业链认知（上下游/壁垒/周期）— 产业链深度分析",
}


def build_data_request_prompt(role: str, target: str, round: int, context: str, target_type: str = "stock") -> str:
    """构建数据请求专用 prompt"""
    whitelist = DEBATE_DATA_WHITELIST_BY_TYPE.get(target_type, DEBATE_DATA_WHITELIST_BY_TYPE["stock"])
    allowed = whitelist.get(role, [])
    allowed_str = "\n".join(
        f"- {a}: {_ACTION_VALUE_DESC.get(a, '数据查询')}"
        for a in allowed
    )
    persona = DEBATE_PERSONAS.get(role, {})
    role_desc = persona.get("role", role)

    # 按 target_type 调整 params 示例和注意事项
    if target_type == "sector":
        params_example = f'[{{"engine": "data", "action": "get_sector_overview", "params": {{"sector": "{target}"}}}}, {{"engine": "info", "action": "get_news", "params": {{"code": "{target}"}}}}]'
        params_note = f'params 中 sector 字段填写板块名 {target}，get_news 的 code 字段填写板块名。'
    elif target_type == "macro":
        params_example = f'[{{"engine": "data", "action": "get_macro_context", "params": {{"query": "{target}"}}}}, {{"engine": "info", "action": "get_news", "params": {{"code": "{target}"}}}}]'
        params_note = f'params 中 query 字段填写主题 {target}，get_news 的 code 字段填写主题关键词。'
    else:
        params_example = f'[{{"engine": "data", "action": "get_financials", "params": {{"code": "{target}"}}}}, {{"engine": "info", "action": "get_news", "params": {{"code": "{target}"}}}}]'
        params_note = f'params 中 code 字段必须填写股票代码 {target}。'

    return _DATA_REQUEST_TEMPLATE.format(
        role_desc=role_desc, target=target, round=round,
        context=context, allowed_actions_with_desc=allowed_str,
        params_example=params_example, params_note=params_note,
        max_requests=MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND,
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestBuildDataRequestPromptTargetType -v`
Expected: PASS

- [x] **Step 5: Run all agent tests**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/ -v`
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add engine/agent/personas.py engine/tests/agent/test_target_resolver.py
git commit -m "feat(personas): build_data_request_prompt 按 target_type 调整 params 示例"
```

<!-- CHUNK_2_END -->

---

## Chunk 3: debate.py 核心改动 + API 路由

### Task 8: debate.py — validate_data_requests 接收 target_type

**Files:**
- Modify: `engine/agent/debate.py:30-36,165-178`

- [x] **Step 1: Write failing test**

Append to `engine/tests/agent/test_target_resolver.py`:

```python
class TestValidateDataRequestsTargetType:
    def _make_req(self, role, action):
        from agent.schemas import DataRequest
        return DataRequest(requested_by=role, engine="data", action=action, round=1)

    def test_stock_allows_get_stock_info(self):
        from agent.debate import validate_data_requests
        reqs = [self._make_req("bull_expert", "get_stock_info")]
        result = validate_data_requests("bull_expert", reqs, target_type="stock")
        assert len(result) == 1

    def test_sector_blocks_get_stock_info(self):
        from agent.debate import validate_data_requests
        reqs = [self._make_req("bull_expert", "get_stock_info")]
        result = validate_data_requests("bull_expert", reqs, target_type="sector")
        assert len(result) == 0

    def test_sector_allows_get_sector_overview(self):
        from agent.debate import validate_data_requests
        reqs = [self._make_req("bull_expert", "get_sector_overview")]
        result = validate_data_requests("bull_expert", reqs, target_type="sector")
        assert len(result) == 1

    def test_macro_allows_get_macro_context(self):
        from agent.debate import validate_data_requests
        reqs = [self._make_req("bull_expert", "get_macro_context")]
        result = validate_data_requests("bull_expert", reqs, target_type="macro")
        assert len(result) == 1

    def test_default_target_type_is_stock(self):
        from agent.debate import validate_data_requests
        reqs = [self._make_req("bull_expert", "get_stock_info")]
        result = validate_data_requests("bull_expert", reqs)
        assert len(result) == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestValidateDataRequestsTargetType -v`
Expected: FAIL — `validate_data_requests` doesn't accept `target_type`

- [x] **Step 3: Update imports and validate_data_requests**

In `engine/agent/debate.py`, update the import (line 30-36):

```python
from agent.personas import (
    build_debate_system_prompt,
    JUDGE_SYSTEM_PROMPT,
    JUDGE_ROUND_EVAL_PROMPT,
    DEBATE_DATA_WHITELIST_BY_TYPE,
    MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND,
)
```

Update `validate_data_requests` (line 165):

```python
def validate_data_requests(role: str, requests: list[DataRequest], target_type: str = "stock") -> list[DataRequest]:
    """白名单过滤 + 数量截断。不抛出异常。"""
    whitelist = DEBATE_DATA_WHITELIST_BY_TYPE.get(target_type, DEBATE_DATA_WHITELIST_BY_TYPE["stock"])
    allowed = whitelist.get(role, [])
    valid = []
    for req in requests:
        if req.action not in allowed:
            logger.warning(f"辩论角色 [{role}] 请求了不在白名单的 action: {req.action}，已过滤")
            continue
        valid.append(req)
        if len(valid) >= MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND:
            if len(requests) > MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND:
                logger.warning(f"辩论角色 [{role}] 请求数超限，截断至 {MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND} 条")
            break
    return valid
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_target_resolver.py::TestValidateDataRequestsTargetType -v`
Expected: PASS

- [x] **Step 5: Run existing debate core tests**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/test_debate_core.py -v`
Expected: PASS (backward compatible — default `target_type="stock"`)

- [x] **Step 6: Commit**

```bash
git add engine/agent/debate.py engine/tests/agent/test_target_resolver.py
git commit -m "feat(debate): validate_data_requests 接收 target_type 参数"
```

---

### Task 9: debate.py — ACTION_TITLE_MAP + fetch_initial_data 按类型分支

**Files:**
- Modify: `engine/agent/debate.py:609-678`

- [x] **Step 1: Update ACTION_TITLE_MAP**

In `engine/agent/debate.py`, add two entries to `ACTION_TITLE_MAP` (line 670):

```python
ACTION_TITLE_MAP = {
    "get_stock_info": "股票基本信息", "get_daily_history": "日线行情",
    "get_news": "最新新闻", "get_announcements": "公告",
    "get_factor_scores": "因子评分", "get_technical_indicators": "技术指标",
    "get_money_flow": "资金流向", "get_northbound_holding": "北向持仓",
    "get_margin_balance": "融资融券", "get_turnover_rate": "换手率",
    "get_cluster_for_stock": "聚类分析", "get_financials": "财务数据",
    "get_restrict_stock_unlock": "限售解禁", "get_signal_history": "信号历史",
    "get_sector_overview": "板块概览", "get_macro_context": "宏观上下文",
}
```

- [x] **Step 2: Modify fetch_initial_data to branch by target_type**

Replace `fetch_initial_data` (lines 609-667) with:

```python
async def fetch_initial_data(
    blackboard: Blackboard,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """拉取公用初始数据，推送 blackboard_update 事件"""
    # 按 target_type 选择初始数据 action 列表
    if blackboard.target_type == "sector":
        INITIAL_ACTIONS = [
            ("get_sector_overview", "data", "板块概览",
             {"sector": blackboard.sector_name}),
            ("get_news", "info", "最新新闻",
             {"code": blackboard.sector_name, "limit": 10}),
        ]
    elif blackboard.target_type == "macro":
        INITIAL_ACTIONS = [
            ("get_macro_context", "data", "宏观上下文",
             {"query": blackboard.target}),
        ]
    else:
        INITIAL_ACTIONS = [
            ("get_stock_info", "data", "股票基本信息",
             {"code": blackboard.code or blackboard.target}),
            ("get_daily_history", "data", "日线行情",
             {"code": blackboard.code or blackboard.target}),
            ("get_news", "info", "最新新闻",
             {"code": blackboard.code or blackboard.target, "limit": 10}),
        ]

    success = 0
    failed = 0
    for action, engine, title, params in INITIAL_ACTIONS:
        req_id = f"public_{action}"
        yield sse("blackboard_update", {
            "request_id": req_id, "source": "public",
            "engine": engine, "action": action, "title": title,
            "status": "pending", "result_summary": "", "round": 0,
        })
        req = DataRequest(
            requested_by="public", engine=engine,
            action=action, params=params, round=0,
        )
        try:
            result = await asyncio.wait_for(
                data_fetcher.fetch_by_request(req), timeout=30.0
            )
            is_error = isinstance(result, dict) and "error" in result
            if is_error:
                summary = result["error"]
                status = "failed"
                failed += 1
            else:
                summary = str(result)[:300] if result else "（无数据）"
                status = "done"
                blackboard.facts[action] = result
                success += 1
            yield sse("blackboard_update", {
                "request_id": req_id, "source": "public",
                "engine": engine, "action": action, "title": title,
                "status": status, "result_summary": summary, "round": 0,
            })
        except Exception as e:
            logger.warning(f"公用数据拉取失败 [{action}]: {type(e).__name__}: {e}")
            failed += 1
            err_msg = str(e) or type(e).__name__
            yield sse("blackboard_update", {
                "request_id": req_id, "source": "public",
                "engine": engine, "action": action, "title": title,
                "status": "failed", "result_summary": err_msg[:200], "round": 0,
            })
    yield sse("initial_data_complete", {
        "total": len(INITIAL_ACTIONS), "success": success, "failed": failed,
    })
```

- [x] **Step 3: Run existing tests**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/ -v`
Expected: PASS

- [x] **Step 4: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat(debate): fetch_initial_data 按 target_type 分支 + ACTION_TITLE_MAP 新增条目"
```

---

### Task 10: debate.py — generate_industry_cognition 接收 target_override

**Files:**
- Modify: `engine/agent/debate.py:684-734`

- [x] **Step 1: Modify generate_industry_cognition**

Update the function signature and early-return guard:

```python
async def generate_industry_cognition(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    target_override: str = "",
) -> AsyncGenerator[dict, None]:
    """调用 IndustryEngine 获取行业产业链认知"""
    stock_info = blackboard.facts.get("get_stock_info", {})
    industry = stock_info.get("industry", "")
    stock_name = stock_info.get("name", blackboard.target)

    # target_override 用于 sector/macro 场景
    if not industry and not target_override:
        logger.info("未获取到行业信息，跳过行业认知生成")
        return
    effective_industry = target_override or industry

    yield sse("industry_cognition_start", {"industry": effective_industry, "cached": False})

    try:
        from industry_engine import get_industry_engine
        ie = get_industry_engine()
        cognition = await ie.analyze(
            target=effective_industry,
            as_of_date=blackboard.as_of_date,
        )

        if cognition:
            blackboard.industry_cognition = cognition
            yield sse("industry_cognition_done", {
                "industry": effective_industry,
                "summary": f"产业链: {' → '.join(cognition.upstream[:2])} → [{stock_name}] → {' → '.join(cognition.downstream[:2])}",
                "cycle_position": cognition.cycle_position,
                "traps_count": len(cognition.common_traps),
                "cached": False,
            })
        else:
            yield sse("industry_cognition_done", {
                "industry": effective_industry,
                "summary": "行业认知生成失败",
                "cycle_position": "",
                "traps_count": 0,
                "cached": False,
                "error": True,
            })
    except Exception as e:
        logger.warning(f"行业认知生成失败: {type(e).__name__}: {e!r}")
        yield sse("industry_cognition_done", {
            "industry": effective_industry,
            "summary": f"行业认知生成失败: {type(e).__name__}: {e}",
            "cycle_position": "",
            "traps_count": 0,
            "cached": False,
            "error": True,
        })
```

- [x] **Step 2: Run existing tests**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/ -v`
Expected: PASS (backward compatible — default `target_override=""`)

- [x] **Step 3: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat(debate): generate_industry_cognition 接收 target_override 参数"
```

---

### Task 11: debate.py — run_debate 集成 TargetResolver

**Files:**
- Modify: `engine/agent/debate.py:1396-1470`

- [x] **Step 1: Update run_debate to use TargetResolver**

Replace lines 1408-1414 (the `resolve_stock_code` block) with:

```python
    # target 类型解析（替换旧的 resolve_stock_code）
    from agent.target_resolver import TargetResolver
    resolver = TargetResolver(llm=llm)
    resolution = await resolver.resolve(blackboard.target)
    blackboard.target_type = resolution.target_type
    blackboard.code = resolution.resolved_code
    blackboard.sector_name = resolution.sector_name
    blackboard.display_name = resolution.display_name or blackboard.target
    logger.info(f"TargetResolver: '{blackboard.target}' → type={blackboard.target_type}, "
                f"code={blackboard.code}, sector={blackboard.sector_name}, display={blackboard.display_name}")
```

- [x] **Step 2: Update debate_start SSE event to include display_name and target_type**

Update the `yield sse("debate_start", ...)` block (line 1424):

```python
    yield sse("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "display_name": blackboard.display_name,
        "target_type": blackboard.target_type,
        "as_of_date": blackboard.as_of_date,
        "max_rounds": blackboard.max_rounds,
        "mode": blackboard.mode,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })
```

- [x] **Step 3: Update generate_industry_cognition call to pass target_override**

Replace line 1450:

```python
    # 行业产业链认知
    if blackboard.target_type == "stock":
        async for event in generate_industry_cognition(blackboard, llm):
            yield event
    else:
        # sector/macro: 传入 sector_name 或 target 作为 target_override
        override = blackboard.sector_name or blackboard.target
        async for event in generate_industry_cognition(blackboard, llm, target_override=override):
            yield event
```

- [x] **Step 4: Update capital_structure guard**

Replace line 1454 (`if blackboard.code:`) with:

```python
    # 资金构成分析（仅 stock 类型）
    if blackboard.code and blackboard.target_type == "stock":
```

- [x] **Step 5: Update speak_stream call to pass target_type**

In `speak_stream` (line 434), update the `build_debate_system_prompt` call:

```python
    system_prompt = build_debate_system_prompt(role, blackboard.display_name or blackboard.target, is_final_round, target_type=blackboard.target_type)
```

- [x] **Step 6: Update request_data_for_round to pass target_type**

In `request_data_for_round` (line 853), update the `build_data_request_prompt` call:

```python
    prompt = build_data_request_prompt(role, blackboard.target, blackboard.round, context, target_type=blackboard.target_type)
```

And update the `validate_data_requests` call (line 876):

```python
    requests = validate_data_requests(role, requests, target_type=blackboard.target_type)
```

- [x] **Step 7: Update speak() (non-streaming) to pass target_type**

In `speak` (line 570), update:

```python
    system_prompt = build_debate_system_prompt(role, blackboard.display_name or blackboard.target, is_final_round, target_type=blackboard.target_type)
```

- [x] **Step 8: Run all agent tests**

Run: `cd engine && .venv/bin/python -m pytest tests/agent/ -v`
Expected: PASS

- [x] **Step 9: Commit**

```bash
git add engine/agent/debate.py
git commit -m "feat(debate): run_debate 集成 TargetResolver + 全链路 target_type 传递"
```

---

### Task 12: API 路由 — DebateRequest 新增 target 字段 + debate_id 清洗

**Files:**
- Modify: `engine/api/routes/debate.py:17-47,156-188`

- [x] **Step 1: Update DebateRequest model**

Replace `DebateRequest` (line 17-22):

```python
class DebateRequest(BaseModel):
    target: str = Field(default="", description="辩论标的：股票代码/板块名/宏观主题")
    code: str = Field(default="", description="已废弃，请使用 target")
    max_rounds: int = Field(default=3, ge=1, le=5)
    mode: str = Field(default="standard", description="辩论模式: standard | fast")
    as_of_date: str = Field(default="", description="回测日期，如 '2025-06-30'，空字符串表示使用最新数据")
```

- [x] **Step 2: Update start_debate route**

Replace lines 25-47:

```python
@router.post("/debate")
async def start_debate(req: DebateRequest):
    """发起专家辩论，SSE 流式返回辩论过程"""
    import re as _re
    from llm.config import llm_settings
    if not llm_settings.api_key:
        raise HTTPException(status_code=503, detail="LLM 未配置，请先设置 API Key")

    effective_target = (req.target or req.code).strip()
    if not effective_target:
        raise HTTPException(status_code=422, detail="target 不能为空")

    now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    # debate_id 清洗：仅保留字母/数字/中文/下划线，截断 20 字符
    safe_target = _re.sub(r"[^\w\u4e00-\u9fff]", "_", effective_target)[:20]
    debate_id = f"{safe_target}_{now.strftime('%Y%m%d%H%M%S')}"

    blackboard = Blackboard(
        target=effective_target,
        debate_id=debate_id,
        max_rounds=req.max_rounds,
        mode=req.mode if req.mode in ("standard", "fast") else "standard",
        as_of_date=req.as_of_date,
    )

    async def event_stream():
        try:
            from agent import get_orchestrator
            from agent.debate import run_debate
            from expert.routes import _expert_agent
            from agent.judge import JudgeRAG

            orch = get_orchestrator()
            judge = JudgeRAG(expert=_expert_agent) if _expert_agent is not None else None
            async for event in run_debate(
                blackboard=blackboard,
                llm=orch._llm._provider,
                memory=orch._memory,
                data_fetcher=orch._data,
                judge=judge,
            ):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False, default=str)}\n\n"
        except Exception as e:
            logger.error(f"辩论流程错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [x] **Step 3: Update summarize endpoint**

In `summarize_debate` (line 180), change:

```python
        prompt = f"""以下是关于股票 {req.target} 的多空辩论记录（辩论被用户中途终止）：
```

To:

```python
        prompt = f"""以下是关于 {req.target} 的多空辩论记录（辩论被用户中途终止）：
```

- [x] **Step 4: Run existing route tests**

Run: `cd engine && .venv/bin/python -m pytest tests/test_debate_history_routes.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add engine/api/routes/debate.py
git commit -m "feat(routes): DebateRequest 新增 target 字段 + debate_id 清洗 + summarize 去掉股票限定词"
```

<!-- CHUNK_3_END -->

---

## Chunk 4: 前端改动 + DebatePage 适配

### Task 13: useDebateStore — startDebate 参数 code→target

**Files:**
- Modify: `web/stores/useDebateStore.ts:35-54,102-115,289-304`

- [x] **Step 1: Update DebateStore interface**

In `web/stores/useDebateStore.ts`, change `startDebate` signature (line ~51):

```typescript
  startDebate: (target: string, maxRounds: number, mode?: string, asOfDate?: string) => Promise<void>;
```

- [x] **Step 2: Update startDebate implementation**

In the `startDebate` method (line 102), change parameter name and request body:

```typescript
  startDebate: async (target, maxRounds, mode = "standard", asOfDate) => {
    get().reset();
    _abortController = new AbortController();
    const isBacktest = !!asOfDate;
    set({ status: "debating", currentTarget: target, isBacktestMode: isBacktest, asOfDate: asOfDate ?? null });

    try {
      const body: Record<string, unknown> = { target, max_rounds: maxRounds, mode };
      if (asOfDate) body.as_of_date = asOfDate;
```

(Rest of the method stays the same)

- [x] **Step 3: Update debate_start SSE handler to read display_name and target_type**

In `_handleSSEEvent`, case `"debate_start"` (line 289), update to store new fields:

```typescript
    case "debate_start": {
      const roleState: Record<string, RoleState> = {};
      for (const role of DEBATERS) roleState[role] = { ...INITIAL_ROLE_STATE };
      const observerState: Record<string, ObserverState> = {};
      for (const obs of OBSERVERS) observerState[obs] = { speak: false, argument: "" };
      const bbItem: TranscriptItem = {
        id: `blackboard_${data.debate_id}`,
        type: "blackboard_data",
        debateId: data.debate_id as string,
        target: (data.display_name || data.target) as string,
        participants: data.participants as string[],
      };
      const serverAsOfDate = data.as_of_date as string | undefined;
      set({
        roleState, observerState, transcript: [bbItem],
        asOfDate: serverAsOfDate ?? null,
        currentTarget: (data.display_name || data.target) as string,
      });
      break;
    }
```

- [x] **Step 4: Commit**

```bash
git add web/stores/useDebateStore.ts
git commit -m "feat(store): startDebate 参数 code→target + debate_start 读取 display_name/target_type"
```

---

### Task 14: InputBar — placeholder/label 更新

**Files:**
- Modify: `web/components/debate/InputBar.tsx:17,56-65,120`

- [x] **Step 1: Update state variable name and placeholder**

In `web/components/debate/InputBar.tsx`:

Change state variable (line 17):
```typescript
  const [target, setTarget] = useState("");
```

Update input element (line 56-64):
```typescript
            <input
              type="text"
              value={target}
              onChange={e => setTarget(e.target.value)}
              placeholder="股票代码 / 板块名 / 宏观主题"
              disabled={busy}
              className="flex-1 h-10 px-4 rounded-lg text-sm bg-[var(--bg-primary)] border border-[var(--border)]
                         text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)]
                         focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
            />
```

Note: remove `.trim()` from onChange — allow spaces in macro topics. Trim on submit instead.

Update submit button (line 120):
```typescript
                onClick={() => { const t = target.trim(); t && onStart(t, maxRounds, mode, asOfDate || undefined); }}
                disabled={!target.trim()}
```

- [x] **Step 2: Commit**

```bash
git add web/components/debate/InputBar.tsx
git commit -m "feat(InputBar): placeholder 更新为'股票代码 / 板块名 / 宏观主题' + 移除格式校验"
```

---

### Task 15: DebatePage — summarize 请求适配

**Files:**
- Modify: `web/components/debate/DebatePage.tsx:41-48`

- [x] **Step 1: Update summarize request body**

In `web/components/debate/DebatePage.tsx`, the `useEffect` for stopped status (line 41-48), change `code` to `target`:

```typescript
    fetch(`${API_BASE}/api/v1/debate/summarize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target: currentTarget, transcript }),
    })
```

Note: The backend `SummarizeRequest` model already has a `target` field (line 157 of routes/debate.py). This change aligns the frontend with the existing field name.

- [x] **Step 2: Commit**

```bash
git add web/components/debate/DebatePage.tsx
git commit -m "feat(DebatePage): summarize 请求 code→target 适配"
```

---

### Task 16: 全量回归测试 + 手动验证

- [x] **Step 1: Run all backend tests**

Run: `cd engine && .venv/bin/python -m pytest tests/ -v --ignore=tests/.venv -x`
Expected: ALL PASS

- [x] **Step 2: Run frontend type check**

Run: `cd web && npx tsc --noEmit`
Expected: No type errors

- [x] **Step 3: Manual smoke test — stock (backward compat)**

1. Start backend: `cd engine && .venv/bin/python main.py`
2. Via MCP tool `start_debate(code="600519")` — should work as before
3. Verify `debate_start` SSE event contains `display_name` and `target_type: "stock"`

- [x] **Step 4: Manual smoke test — sector**

1. Via MCP tool `start_debate(code="半导体")` — should resolve as sector
2. Verify `fetch_initial_data` calls `get_sector_overview` instead of `get_stock_info`
3. Verify industry cognition fires with `target_override="半导体"`

- [x] **Step 5: Manual smoke test — macro**

1. Via MCP tool `start_debate(code="美联储降息对A股的影响")` — should resolve as macro
2. Verify `fetch_initial_data` calls `get_macro_context`
3. Verify capital_structure phase is skipped

- [x] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: 辩论 target 泛化 — 支持板块/行业和宏观主题辩论"
```

<!-- CHUNK_4_END -->
