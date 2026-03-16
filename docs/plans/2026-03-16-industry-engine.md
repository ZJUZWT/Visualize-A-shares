# IndustryEngine 产业链引擎实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将产业链认知从辩论系统的内嵌函数升级为独立引擎，与 DataEngine/InfoEngine/QuantEngine/ClusterEngine 平级，上面放一个 LLM Agent，支持独立调用和辩论前主动访问。同时新增资金构成分析作为黑板公共知识。

**Architecture:** IndustryEngine 遵循项目已有的门面+单例模式（参考 `InfoEngine`）。内部组合：`IndustryAgent`（LLM 推理）+ `DuckDBStore`（缓存）+ `DataEngine`（基础数据）。Agent 负责：产业链结构推理、行业→股票映射、周期定位、认知陷阱生成。辩论系统通过调用 `get_industry_engine().analyze()` 替代原来的 `generate_industry_cognition()`。

**Tech Stack:** Python 3.11+, Pydantic v2, FastAPI, DuckDB, LLM (ChatMessage/BaseLLMProvider), AKShare, loguru

---

## Task 1: IndustryEngine 核心模块

**Files:**
- Create: `engine/industry_engine/__init__.py`
- Create: `engine/industry_engine/schemas.py`
- Create: `engine/industry_engine/engine.py`

### Step 1: 创建 schemas.py — 数据模型

```python
# engine/industry_engine/schemas.py
"""产业链引擎数据结构"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class IndustryCognition(BaseModel):
    """行业产业链认知 — LLM 生成，缓存复用
    
    NOTE: 从 agent/schemas.py 迁移过来，成为 IndustryEngine 的核心输出。
    agent/schemas.py 中的 IndustryCognition 将改为 re-export。
    """
    industry: str                    # 行业名称（如"小金属"、"半导体"）
    target: str                      # 触发股票代码

    # 产业链结构
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    core_drivers: list[str] = Field(default_factory=list)
    cost_structure: str = ""
    barriers: str = ""

    # 供需格局
    supply_demand: str = ""

    # 认知陷阱
    common_traps: list[str] = Field(default_factory=list)

    # 周期定位
    cycle_position: str = ""         # 景气上行|下行|拐点向上|拐点向下|高位震荡|底部盘整
    cycle_reasoning: str = ""

    # 催化剂/风险
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    # 元数据
    generated_at: str = ""
    as_of_date: str = ""


class IndustryMapping(BaseModel):
    """行业→股票映射"""
    industry: str
    stocks: list[str]               # 股票代码列表
    stock_count: int = 0


class IndustryAnalysisRequest(BaseModel):
    """产业链分析请求"""
    target: str = Field(description="股票代码如 '600519'，或行业名如 '半导体'")
    target_type: Literal["stock", "industry"] = "stock"
    as_of_date: str = ""            # 空字符串时 fallback 到 today


class CapitalStructure(BaseModel):
    """资金构成分析 — 黑板公共知识"""
    code: str
    as_of_date: str = ""

    # 主力资金
    main_force_net_inflow: str = ""       # 主力净流入
    main_force_ratio: str = ""            # 主力净流入占比
    super_large_net_inflow: str = ""      # 超大单净流入
    large_net_inflow: str = ""            # 大单净流入
    small_net_inflow: str = ""            # 小单净流入

    # 北向持股
    northbound_shares: str = ""           # 持股数量
    northbound_market_value: str = ""     # 持股市值
    northbound_ratio: str = ""            # 持股占比
    northbound_change: str = ""           # 持股变化

    # 融资融券
    margin_balance: str = ""              # 融资余额
    margin_buy: str = ""                  # 融资买入额
    short_selling_volume: str = ""        # 融券余量

    # 换手率
    turnover_rate: float = 0.0

    # 综合判断（后续由 Agent 或规则填充）
    structure_summary: str = ""           # 资金构成摘要
```

### Step 2: 创建 engine.py — 门面类

```python
# engine/industry_engine/engine.py
"""IndustryEngine — 产业链引擎门面类

统一管理行业认知生成、行业→股票映射、资金构成分析。
数据源通过 DataEngine，LLM 推理通过 IndustryAgent，缓存在 DuckDB shared.* schema。
"""

import json
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from .schemas import IndustryCognition, IndustryMapping, CapitalStructure


class IndustryEngine:
    """产业链引擎 — 行业认知/映射/资金构成的门面"""

    def __init__(self, data_engine, llm_provider=None):
        self._data = data_engine
        self._store = data_engine.store
        self._llm = llm_provider
        self._agent = None  # 延迟初始化

    @property
    def agent(self):
        """延迟初始化 IndustryAgent（避免循环依赖）"""
        if self._agent is None:
            from .agent import IndustryAgent
            self._agent = IndustryAgent(self._llm, self._store)
        return self._agent

    # ── 行业认知 ──

    async def analyze(
        self,
        target: str,
        as_of_date: str = "",
        force_refresh: bool = False,
    ) -> IndustryCognition | None:
        """获取目标的行业产业链认知（缓存优先，未命中则 Agent 生成）

        Args:
            target: 股票代码或行业名
            as_of_date: 时间锚点
            force_refresh: 强制刷新缓存

        Returns:
            IndustryCognition 或 None（无行业信息时）
        """
        industry, code = self._resolve_industry(target)
        if not industry:
            logger.info(f"无法识别行业: {target}")
            return None

        if not as_of_date:
            as_of_date = datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

        # 缓存检查
        if not force_refresh:
            cached = self._load_cached(industry, as_of_date)
            if cached:
                logger.info(f"行业认知缓存命中: {industry} @ {as_of_date}")
                return cached

        # Agent 生成
        if not self._llm:
            logger.warning("LLM 未配置，无法生成行业认知")
            return None

        cognition = await self.agent.generate_cognition(
            industry=industry,
            target=code or target,
            as_of_date=as_of_date,
        )
        if cognition:
            self._save_cache(cognition)
        return cognition

    # ── 行业映射 ──

    def get_industry_mapping(self) -> dict[str, list[str]]:
        """获取行业→股票代码映射（从 company_profiles 构建）"""
        profiles = self._data.get_profiles()
        mapping: dict[str, list[str]] = {}
        for code, info in profiles.items():
            industry = info.get("industry", "")
            if industry:
                mapping.setdefault(industry, []).append(code)
        return mapping

    def get_industry_stocks(self, industry: str) -> list[str]:
        """获取指定行业的全部股票代码"""
        mapping = self.get_industry_mapping()
        return mapping.get(industry, [])

    def get_stock_industry(self, code: str) -> str:
        """获取股票所属行业"""
        profile = self._data.get_profile(code)
        return profile.get("industry", "") if profile else ""

    def list_industries(self) -> list[IndustryMapping]:
        """列出所有行业及其股票数量"""
        mapping = self.get_industry_mapping()
        return [
            IndustryMapping(industry=ind, stocks=codes, stock_count=len(codes))
            for ind, codes in sorted(mapping.items(), key=lambda x: -len(x[1]))
        ]

    # ── 资金构成分析 ──

    async def get_capital_structure(self, code: str, as_of_date: str = "") -> CapitalStructure:
        """汇聚资金流向 + 北向持股 + 融资融券 + 换手率，构建结构化资金构成"""
        from agent.data_fetcher import DataFetcher
        fetcher = DataFetcher(as_of_date=as_of_date)

        import asyncio
        money_flow, northbound, margin, turnover = await asyncio.gather(
            asyncio.to_thread(fetcher.get_money_flow, code),
            asyncio.to_thread(fetcher.get_northbound_holding, code),
            asyncio.to_thread(fetcher.get_margin_balance, code),
            asyncio.to_thread(fetcher.get_turnover_rate, code),
        )

        cs = CapitalStructure(code=code, as_of_date=as_of_date or fetcher.end_date)

        # 资金流向
        if "error" not in money_flow:
            cs.main_force_net_inflow = money_flow.get("主力净流入", "")
            cs.main_force_ratio = money_flow.get("主力净流入占比", "")
            cs.super_large_net_inflow = money_flow.get("超大单净流入", "")
            cs.large_net_inflow = money_flow.get("大单净流入", "")
            cs.small_net_inflow = money_flow.get("小单净流入", "")

        # 北向持股
        if "error" not in northbound:
            cs.northbound_shares = northbound.get("持股数量", "")
            cs.northbound_market_value = northbound.get("持股市值", "")
            cs.northbound_ratio = northbound.get("持股占比", "")
            cs.northbound_change = northbound.get("持股变化", "")

        # 融资融券
        if "error" not in margin:
            cs.margin_balance = margin.get("融资余额", "")
            cs.margin_buy = margin.get("融资买入额", "")
            cs.short_selling_volume = margin.get("融券余量", "")

        # 换手率
        if "error" not in turnover:
            cs.turnover_rate = turnover.get("turnover_rate", 0.0)

        # 构建摘要
        cs.structure_summary = self._build_capital_summary(cs)

        return cs

    def _build_capital_summary(self, cs: CapitalStructure) -> str:
        """基于规则生成资金构成的文字摘要"""
        parts = []
        if cs.main_force_net_inflow:
            parts.append(f"主力净流入{cs.main_force_net_inflow}（占比{cs.main_force_ratio}）")
        if cs.northbound_ratio:
            parts.append(f"北向持股占比{cs.northbound_ratio}，变化{cs.northbound_change}")
        if cs.margin_balance:
            parts.append(f"融资余额{cs.margin_balance}")
        if cs.turnover_rate:
            parts.append(f"换手率{cs.turnover_rate:.2f}%")
        return "；".join(parts) if parts else "资金数据暂缺"

    # ── 健康检查 ──

    def health_check(self) -> dict:
        return {
            "status": "ok",
            "llm_available": self._llm is not None,
            "industry_count": len(self.get_industry_mapping()),
        }

    # ── 私有方法 ──

    def _resolve_industry(self, target: str) -> tuple[str, str]:
        """解析目标为 (行业名, 股票代码)"""
        import re
        # 如果是 6 位数字，当作股票代码
        if re.fullmatch(r"\d{6}", target.strip()):
            profile = self._data.get_profile(target.strip())
            if profile:
                return profile.get("industry", ""), target.strip()
            return "", target.strip()

        # 否则当作行业名，检查是否存在
        mapping = self.get_industry_mapping()
        if target in mapping:
            return target, ""

        # 模糊匹配
        for ind in mapping:
            if target in ind or ind in target:
                return ind, ""

        return "", ""

    def _load_cached(self, industry: str, as_of_date: str) -> IndustryCognition | None:
        """从 DuckDB 读取缓存"""
        try:
            row = self._store._conn.execute(
                "SELECT cognition_json FROM shared.industry_cognition "
                "WHERE industry = ? AND as_of_date = ?",
                [industry, as_of_date],
            ).fetchone()
            if row:
                data = json.loads(row[0])
                return IndustryCognition(**data)
        except Exception as e:
            logger.debug(f"行业认知缓存读取失败: {e}")
        return None

    def _save_cache(self, cognition: IndustryCognition):
        """写入 DuckDB 缓存"""
        try:
            self._store._conn.execute(
                "INSERT OR REPLACE INTO shared.industry_cognition "
                "(industry, as_of_date, target, cognition_json) VALUES (?, ?, ?, ?)",
                [cognition.industry, cognition.as_of_date, cognition.target,
                 cognition.model_dump_json()],
            )
        except Exception as e:
            logger.warning(f"行业认知缓存写入失败: {e}")
```

### Step 3: 创建 __init__.py — 单例模式

```python
# engine/industry_engine/__init__.py
"""产业链引擎模块 — 行业认知/映射/资金构成"""

from .engine import IndustryEngine

_industry_engine: IndustryEngine | None = None


def get_industry_engine() -> IndustryEngine:
    """获取产业链引擎全局单例（依赖数据引擎，可选 LLM）"""
    global _industry_engine
    if _industry_engine is None:
        llm_provider = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            if llm_settings.api_key:
                llm_provider = LLMProviderFactory.create(llm_settings)
        except Exception:
            pass
        from data_engine import get_data_engine
        _industry_engine = IndustryEngine(
            data_engine=get_data_engine(),
            llm_provider=llm_provider,
        )
    return _industry_engine


__all__ = ["IndustryEngine", "get_industry_engine"]
```

### Step 4: 迁移 IndustryCognition — 修改 agent/schemas.py

将 `agent/schemas.py` 中的 `IndustryCognition` 改为从 `industry_engine.schemas` re-export，保持后向兼容。

**Modify:** `engine/agent/schemas.py`
- 删除 `IndustryCognition` 类定义（约第 108-136 行）
- 添加：`from industry_engine.schemas import IndustryCognition`

---

## Task 2: IndustryAgent — LLM 驱动的产业链推理

**Files:**
- Create: `engine/industry_engine/agent.py`

### Step 1: 创建 IndustryAgent

```python
# engine/industry_engine/agent.py
"""产业链 Agent — LLM 驱动的行业认知推理

职责：
1. 产业链结构推理（上下游、核心驱动、壁垒）
2. 供需格局分析
3. 周期定位
4. 认知陷阱生成
"""

import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from .schemas import IndustryCognition

# ── Prompt 模板 ──

INDUSTRY_COGNITION_PROMPT = """你是产业链分析专家。请基于你对 {industry} 行业的深度理解，生成以下结构化分析。
当前讨论标的：{target}（{stock_name}），时间基准：{as_of_date}。

请以 JSON 格式返回：
{{
  "upstream": ["上游环节1", "上游环节2"],
  "downstream": ["下游应用1", "下游应用2"],
  "core_drivers": ["核心驱动变量1 — 简要说明", "..."],
  "cost_structure": "成本结构描述（原材料占比、人工、能源等）",
  "barriers": "行业壁垒（资源、技术、资质、规模等）",
  "supply_demand": "当前供需格局分析（供给端变化、需求端趋势、库存状态）",
  "common_traps": [
    "认知陷阱1 — 表面逻辑 vs 实际逻辑",
    "认知陷阱2 — ..."
  ],
  "cycle_position": "景气上行 | 景气下行 | 拐点向上 | 拐点向下 | 高位震荡 | 底部盘整",
  "cycle_reasoning": "周期判断的具体依据",
  "catalysts": ["潜在催化剂1", "..."],
  "risks": ["关键风险1", "..."]
}}

要求：
- common_traps 是最关键的部分，必须列出该行业中投资者最容易犯的认知错误
- 每个陷阱要说明「表面逻辑」和「实际逻辑」的差异
- cycle_position 必须给出明确判断，不能模棱两可
- 所有分析基于 {as_of_date} 时点的行业状态"""


# 独立可调用的行业分析 prompt（不依赖特定股票）
INDUSTRY_STANDALONE_PROMPT = """你是产业链分析专家。请基于你对 {industry} 行业的深度理解，生成以下结构化分析。
时间基准：{as_of_date}。

请以 JSON 格式返回：
{{
  "upstream": ["上游环节1", "上游环节2"],
  "downstream": ["下游应用1", "下游应用2"],
  "core_drivers": ["核心驱动变量1 — 简要说明", "..."],
  "cost_structure": "成本结构描述",
  "barriers": "行业壁垒",
  "supply_demand": "当前供需格局分析",
  "common_traps": ["认知陷阱1 — 表面逻辑 vs 实际逻辑", "..."],
  "cycle_position": "景气上行 | 景气下行 | 拐点向上 | 拐点向下 | 高位震荡 | 底部盘整",
  "cycle_reasoning": "周期判断的具体依据",
  "catalysts": ["潜在催化剂1", "..."],
  "risks": ["关键风险1", "..."]
}}

要求：
- common_traps 必须列出投资者最容易犯的认知错误，说明「表面逻辑」和「实际逻辑」
- cycle_position 必须给出明确判断
- 所有分析基于 {as_of_date} 时点"""


class IndustryAgent:
    """产业链推理 Agent"""

    def __init__(self, llm: BaseLLMProvider, store=None):
        self._llm = llm
        self._store = store

    async def generate_cognition(
        self,
        industry: str,
        target: str = "",
        as_of_date: str = "",
    ) -> IndustryCognition | None:
        """LLM 生成行业认知

        Args:
            industry: 行业名称
            target: 触发股票代码（可选，独立调用时为空）
            as_of_date: 时间锚点
        """
        if not as_of_date:
            as_of_date = datetime.now(tz=ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

        # 获取股票名称（如果有 target）
        stock_name = ""
        if target:
            try:
                from data_engine import get_data_engine
                profile = get_data_engine().get_profile(target)
                stock_name = profile.get("name", target) if profile else target
            except Exception:
                stock_name = target

        # 选择 prompt
        if target and stock_name:
            prompt = INDUSTRY_COGNITION_PROMPT.format(
                industry=industry,
                target=target,
                stock_name=stock_name,
                as_of_date=as_of_date,
            )
        else:
            prompt = INDUSTRY_STANDALONE_PROMPT.format(
                industry=industry,
                as_of_date=as_of_date,
            )

        try:
            # 流式收集完整响应
            chunks: list[str] = []
            async for token in self._llm.chat_stream(
                [ChatMessage(role="user", content=prompt)]
            ):
                chunks.append(token)
            raw = "".join(chunks)
            logger.debug(f"行业认知 LLM 原始返回 (前200字): {raw[:200] if raw else '(空)'}")

            parsed = _lenient_json_loads(raw)
            if not isinstance(parsed, dict):
                logger.warning(f"行业认知 LLM 返回非 dict: {type(parsed)}")
                return None

            cognition = IndustryCognition(
                industry=industry,
                target=target,
                generated_at=datetime.now(tz=ZoneInfo("Asia/Shanghai")).isoformat(),
                as_of_date=as_of_date,
                **{k: v for k, v in parsed.items() if k in IndustryCognition.model_fields},
            )
            logger.info(
                f"行业认知生成完成: {industry}, "
                f"周期={cognition.cycle_position}, "
                f"陷阱={len(cognition.common_traps)}条"
            )
            return cognition

        except Exception as e:
            logger.warning(f"行业认知生成失败: {type(e).__name__}: {e!r}")
            return None


# ── JSON 解析工具（从 debate.py 复用） ──

def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON"""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    result = match.group(1).strip() if match else text.strip()
    result = result.replace("\u201c", '"').replace("\u201d", '"')
    result = result.replace("\u2018", "'").replace("\u2019", "'")
    result = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', result)
    return result


def _lenient_json_loads(text: str) -> dict | list:
    """宽松 JSON 解析"""
    raw = _extract_json(text)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    fixed = re.sub(r',\s*([}\]])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass
    fixed2 = fixed.replace("'", '"')
    try:
        return json.loads(fixed2)
    except json.JSONDecodeError:
        pass
    m = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}|\[.*\])', fixed, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    raise json.JSONDecodeError("宽松解析也失败", raw, 0)
```

---

## Task 3: API 路由 + DataFetcher 集成

**Files:**
- Create: `engine/industry_engine/routes.py`
- Modify: `engine/agent/data_fetcher.py` — 新增 ACTION_DISPATCH 条目
- Modify: `engine/main.py` — 注册路由 + startup 初始化

### Step 1: 创建 routes.py

```python
# engine/industry_engine/routes.py
"""产业链引擎 API 路由"""

import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger

from .schemas import IndustryAnalysisRequest

router = APIRouter(prefix="/api/v1/industry", tags=["industry"])


@router.post("/analyze")
async def analyze_industry(req: IndustryAnalysisRequest):
    """分析产业链认知（SSE 流式推送进度）"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()

    async def event_stream():
        yield f"event: industry_cognition_start\ndata: {json.dumps({'target': req.target}, ensure_ascii=False)}\n\n"
        try:
            cognition = await ie.analyze(
                target=req.target,
                as_of_date=req.as_of_date,
            )
            if cognition:
                yield f"event: industry_cognition_done\ndata: {json.dumps(cognition.model_dump(), ensure_ascii=False)}\n\n"
            else:
                yield f"event: industry_cognition_done\ndata: {json.dumps({'error': '无法生成行业认知'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"产业链分析失败: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/cognition/{target}")
async def get_cognition(target: str, as_of_date: str = ""):
    """获取产业链认知（JSON，缓存优先）"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    cognition = await ie.analyze(target=target, as_of_date=as_of_date)
    if cognition:
        return cognition.model_dump()
    return {"error": f"无法获取 {target} 的行业认知"}


@router.get("/mapping")
async def get_mapping():
    """获取行业→股票映射"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    industries = ie.list_industries()
    return {
        "total_industries": len(industries),
        "industries": [m.model_dump() for m in industries[:50]],  # 返回前 50 个
    }


@router.get("/mapping/{industry}")
async def get_industry_stocks(industry: str):
    """获取指定行业的全部股票"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    stocks = ie.get_industry_stocks(industry)
    return {"industry": industry, "stock_count": len(stocks), "stocks": stocks}


@router.get("/capital/{code}")
async def get_capital_structure(code: str, as_of_date: str = ""):
    """获取资金构成分析"""
    from industry_engine import get_industry_engine
    ie = get_industry_engine()
    cs = await ie.get_capital_structure(code, as_of_date)
    return cs.model_dump()


@router.get("/health")
async def health():
    """健康检查"""
    from industry_engine import get_industry_engine
    return get_industry_engine().health_check()
```

### Step 2: 修改 data_fetcher.py — 新增 industry_engine 路由

**Modify:** `engine/agent/data_fetcher.py`

在 `ACTION_DISPATCH` 字典中添加：
```python
"get_industry_cognition": ("industry_engine", "get_industry_engine", "analyze", True),
"get_capital_structure":  ("industry_engine", "get_industry_engine", "get_capital_structure", True),
```

### Step 3: 修改 main.py — 注册路由

**Modify:** `engine/main.py`

添加 import：
```python
from industry_engine.routes import router as industry_router
```

在路由注册块添加：
```python
app.include_router(industry_router)
```

在 startup 日志中添加产业链引擎状态：
```python
logger.info(f"   产业链引擎: 已加载")
```

---

## Task 4: MCP Tool 注册

**Files:**
- Modify: `engine/mcpserver/server.py` — 注册新 Tool
- Modify: `engine/mcpserver/tools.py` — 添加实现函数

### Step 1: 添加 MCP Tool 实现

**Modify:** `engine/mcpserver/tools.py`

在文件末尾添加 3 个工具函数：

```python
# ── IndustryEngine Tools ──────────────────────────────

def get_industry_cognition(da: DataAccess, target: str) -> str:
    """获取产业链认知"""
    if da.is_online():
        result = da.api_get(f"/api/v1/industry/cognition/{target}")
        if result:
            return _format_industry_cognition(result)
    return "⚠️ 需要后端在线且配置 LLM 才能获取产业链认知"


def get_industry_mapping_tool(da: DataAccess, industry: str = "") -> str:
    """获取行业映射"""
    if industry:
        if da.is_online():
            result = da.api_get(f"/api/v1/industry/mapping/{industry}")
            if result:
                stocks = result.get("stocks", [])
                return f"## {industry}（{len(stocks)} 只）\n\n" + ", ".join(stocks[:50])
        return f"⚠️ 无法获取 {industry} 的股票列表"
    else:
        if da.is_online():
            result = da.api_get("/api/v1/industry/mapping")
            if result:
                lines = [f"## 行业板块列表（共 {result.get('total_industries', 0)} 个）\n"]
                for ind in result.get("industries", [])[:30]:
                    lines.append(f"- **{ind['industry']}**: {ind['stock_count']} 只")
                return "\n".join(lines)
        return "⚠️ 需要后端在线"


def get_capital_structure_tool(da: DataAccess, code: str) -> str:
    """获取资金构成分析"""
    if da.is_online():
        result = da.api_get(f"/api/v1/industry/capital/{code}")
        if result:
            return _format_capital_structure(result)
    return f"⚠️ 无法获取 {code} 的资金构成"


def _format_industry_cognition(data: dict) -> str:
    """格式化产业链认知为 Markdown"""
    if "error" in data:
        return f"⚠️ {data['error']}"
    lines = [f"# {data.get('industry', '?')} 产业链认知\n"]
    if data.get("upstream"):
        lines.append(f"**上游**: {', '.join(data['upstream'])}")
    if data.get("downstream"):
        lines.append(f"**下游**: {', '.join(data['downstream'])}")
    if data.get("core_drivers"):
        lines.append(f"\n**核心驱动**: {'; '.join(data['core_drivers'])}")
    if data.get("supply_demand"):
        lines.append(f"\n**供需格局**: {data['supply_demand']}")
    if data.get("cycle_position"):
        lines.append(f"\n**周期定位**: {data['cycle_position']}")
        lines.append(f"**判断依据**: {data.get('cycle_reasoning', '')}")
    if data.get("common_traps"):
        lines.append("\n**认知陷阱**:")
        for trap in data["common_traps"]:
            lines.append(f"- {trap}")
    if data.get("catalysts"):
        lines.append(f"\n**催化剂**: {'; '.join(data['catalysts'])}")
    if data.get("risks"):
        lines.append(f"\n**风险**: {'; '.join(data['risks'])}")
    return "\n".join(lines)


def _format_capital_structure(data: dict) -> str:
    """格式化资金构成为 Markdown"""
    lines = [f"# {data.get('code', '?')} 资金构成分析\n"]
    if data.get("main_force_net_inflow"):
        lines.append(f"**主力净流入**: {data['main_force_net_inflow']}（占比{data.get('main_force_ratio', '')}）")
    if data.get("northbound_ratio"):
        lines.append(f"**北向持股**: 占比{data['northbound_ratio']}，变化{data.get('northbound_change', '')}")
    if data.get("margin_balance"):
        lines.append(f"**融资余额**: {data['margin_balance']}")
    if data.get("turnover_rate"):
        lines.append(f"**换手率**: {data['turnover_rate']:.2f}%")
    if data.get("structure_summary"):
        lines.append(f"\n**综合**: {data['structure_summary']}")
    return "\n".join(lines)
```

### Step 2: 注册到 MCP Server

**Modify:** `engine/mcpserver/server.py`

在 Debate Tools 区块之前添加：

```python
# ─── IndustryEngine Tools ──────────────────────────────

@server.tool()
def query_industry_cognition(target: str) -> str:
    """获取产业链认知。输入股票代码（如 '600519'）或行业名（如 '半导体'），返回产业链结构、供需格局、周期定位、认知陷阱等。"""
    return tools.get_industry_cognition(_da, target)


@server.tool()
def query_industry_mapping(industry: str = "") -> str:
    """查询行业板块列表及成分股。不传 industry 返回所有行业概览；传入行业名返回该行业全部成分股。"""
    return tools.get_industry_mapping_tool(_da, industry)


@server.tool()
def query_capital_structure(code: str) -> str:
    """获取个股资金构成分析。汇聚主力资金流向、北向持股、融资融券、换手率数据。code 示例: '600519'"""
    return tools.get_capital_structure_tool(_da, code)
```

---

## Task 5: 辩论系统对接

**Files:**
- Modify: `engine/agent/debate.py` — 改造 `generate_industry_cognition` 和 `fetch_initial_data`
- Modify: `engine/agent/schemas.py` — IndustryCognition re-export

### Step 1: 修改 agent/schemas.py

删除 `IndustryCognition` 类定义，改为从 `industry_engine.schemas` 导入：

**Modify:** `engine/agent/schemas.py:108-136`

替换 `IndustryCognition` 类定义为：
```python
# IndustryCognition 已迁移至 industry_engine.schemas，此处 re-export 保持兼容
from industry_engine.schemas import IndustryCognition
```

### Step 2: 重写 generate_industry_cognition — 调用 IndustryEngine

**Modify:** `engine/agent/debate.py`

将 `generate_industry_cognition()` 函数重写为调用 `IndustryEngine.analyze()`：

```python
async def generate_industry_cognition(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
) -> AsyncGenerator[dict, None]:
    """调用 IndustryEngine 获取行业产业链认知"""
    stock_info = blackboard.facts.get("get_stock_info", {})
    industry = stock_info.get("industry", "")
    stock_name = stock_info.get("name", blackboard.target)

    if not industry:
        logger.info("未获取到行业信息，跳过行业认知生成")
        return

    yield sse("industry_cognition_start", {"industry": industry, "cached": False})

    try:
        from industry_engine import get_industry_engine
        ie = get_industry_engine()
        cognition = await ie.analyze(
            target=blackboard.code or blackboard.target,
            as_of_date=blackboard.as_of_date,
        )

        if cognition:
            blackboard.industry_cognition = cognition
            yield sse("industry_cognition_done", {
                "industry": industry,
                "summary": f"产业链: {' → '.join(cognition.upstream[:2])} → [{stock_name}] → {' → '.join(cognition.downstream[:2])}",
                "cycle_position": cognition.cycle_position,
                "traps_count": len(cognition.common_traps),
                "cached": False,  # IndustryEngine 内部处理缓存
            })
        else:
            yield sse("industry_cognition_done", {
                "industry": industry,
                "summary": "行业认知生成失败",
                "cycle_position": "",
                "traps_count": 0,
                "cached": False,
                "error": True,
            })
    except Exception as e:
        logger.warning(f"行业认知生成失败: {type(e).__name__}: {e!r}")
        yield sse("industry_cognition_done", {
            "industry": industry,
            "summary": f"行业认知生成失败: {type(e).__name__}: {e}",
            "cycle_position": "",
            "traps_count": 0,
            "cached": False,
            "error": True,
        })
```

### Step 3: 在 fetch_initial_data 后新增资金构成分析

**Modify:** `engine/agent/debate.py` — 在 `run_debate()` 函数中，`generate_industry_cognition()` 之后添加：

```python
    # ── 资金构成分析（写入黑板 facts） ──
    if blackboard.code:
        yield sse("phase", {"name": "capital_structure", "status": "start"})
        try:
            from industry_engine import get_industry_engine
            ie = get_industry_engine()
            capital = await ie.get_capital_structure(
                blackboard.code, blackboard.as_of_date
            )
            blackboard.facts["capital_structure"] = capital.model_dump()
            yield sse("phase", {"name": "capital_structure", "status": "done",
                                "summary": capital.structure_summary})
        except Exception as e:
            logger.warning(f"资金构成分析失败: {e}")
            yield sse("phase", {"name": "capital_structure", "status": "error",
                                "error": str(e)})
```

同时需要确保在 `_build_context_for_role()` 中将资金构成注入上下文文本。

### Step 4: 清理 debate.py 中的旧代码

删除 debate.py 中以下已迁移到 IndustryEngine 的代码：
- `INDUSTRY_COGNITION_PROMPT` 常量（约第 661-686 行）
- `_load_cached_cognition()` 函数（约第 689-704 行）
- `_save_cognition_cache()` 函数（约第 707-738 行）

这些逻辑已被 `IndustryEngine.analyze()` 和 `IndustryAgent.generate_cognition()` 接管。

---

## Task 6: _build_context_for_role 增强 — 注入资金构成

**Files:**
- Modify: `engine/agent/debate.py` — `_build_context_for_role()` 函数

### Step 1: 在上下文构建中加入资金构成

在 `_build_context_for_role()` 函数中，在行业认知部分之后，添加资金构成的文本序列化：

```python
    # 资金构成（公共知识）
    capital = blackboard.facts.get("capital_structure")
    if capital and isinstance(capital, dict):
        parts.append("## 资金构成")
        if capital.get("main_force_net_inflow"):
            parts.append(f"- 主力净流入: {capital['main_force_net_inflow']}（占比{capital.get('main_force_ratio', '')}）")
        if capital.get("super_large_net_inflow"):
            parts.append(f"- 超大单净流入: {capital['super_large_net_inflow']}")
        if capital.get("large_net_inflow"):
            parts.append(f"- 大单净流入: {capital['large_net_inflow']}")
        if capital.get("small_net_inflow"):
            parts.append(f"- 小单净流入: {capital['small_net_inflow']}")
        if capital.get("northbound_ratio"):
            parts.append(f"- 北向持股占比: {capital['northbound_ratio']}，变化: {capital.get('northbound_change', '')}")
        if capital.get("margin_balance"):
            parts.append(f"- 融资余额: {capital['margin_balance']}，融资买入额: {capital.get('margin_buy', '')}")
        if capital.get("turnover_rate"):
            parts.append(f"- 换手率: {capital['turnover_rate']:.2f}%")
        if capital.get("structure_summary"):
            parts.append(f"\n综合判断: {capital['structure_summary']}")
```

---

## 依赖关系

```
Task 1 (核心模块) ← 无依赖，最先做
Task 2 (Agent) ← 依赖 Task 1
Task 3 (API 路由) ← 依赖 Task 1 + 2
Task 4 (MCP Tools) ← 依赖 Task 3
Task 5 (辩论对接) ← 依赖 Task 1 + 2
Task 6 (上下文增强) ← 依赖 Task 5
```

建议执行顺序：Task 1 → Task 2 → Task 5 → Task 3 → Task 6 → Task 4

---

## 测试验证

完成后可通过以下方式验证：

1. **单元测试**: `python -c "from industry_engine import get_industry_engine; ie = get_industry_engine(); print(ie.health_check())"`
2. **API 测试**: 启动 engine 后访问 `GET /api/v1/industry/health`
3. **行业映射**: `GET /api/v1/industry/mapping` 检查行业列表
4. **辩论集成**: 发起辩论，检查是否走 IndustryEngine 路径
5. **资金构成**: `GET /api/v1/industry/capital/600519` 检查资金数据
