# Multi-Agent 智能投研决策大脑 — Phase 1 MVP 实施计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现用户点击"AI 分析"按钮，3-5s 内返回三维度（基本面+消息面+技术面）聚合报告，通过 SSE 流式推送各 Agent 进度。

**Architecture:** Orchestrator 编排 PreScreen → 并行三 Agent → Aggregator 流水线。每个 Agent 通过 MCP Tool 白名单访问引擎数据，通过 ChromaDB 隔离推理记忆。LLM 无状态调用，每次重注入 persona system prompt。

**Tech Stack:** Python 3.11+ / FastAPI / DuckDB / ChromaDB / httpx (LLM) / asyncio / pytest / Next.js (前端)

**Spec:** `docs/superpowers/specs/2026-03-14-multi-agent-decision-brain-design.md`

---

## File Structure

### New files (backend)

```
engine/
├── agent/                           # Agent 编排层（新建目录）
│   ├── __init__.py                  # 导出 get_orchestrator()
│   ├── schemas.py                   # Pydantic models: AnalysisRequest, AgentVerdict, Evidence, AggregatedReport, PreScreenResult
│   ├── personas.py                  # AGENT_PERSONAS + AGENT_TOOL_ACCESS 常量
│   ├── memory.py                    # ChromaDB 封装: AgentMemory class
│   ├── runner.py                    # 单个 Agent 的 LLM 调用逻辑: run_agent()
│   ├── aggregator.py                # 聚合逻辑: aggregate_verdicts()
│   ├── data_fetcher.py              # 数据获取层: DataFetcher class
│   └── orchestrator.py              # 编排入口: Orchestrator.analyze()
├── quant_engine/                    # 量化引擎（新建目录）
│   ├── __init__.py                  # 导出 get_quant_engine()
│   ├── engine.py                    # QuantEngine class
│   ├── indicators.py                # 技术指标计算: MACD, RSI, 布林带等
│   └── routes.py                    # REST API: /api/v1/quant/*
├── api/routes/
│   └── analysis.py                  # REST API: POST /api/v1/analysis (SSE)
```

### New files (tests)

```
tests/
├── conftest.py                      # pytest fixtures: mock DuckDB, mock LLM
├── test_agent_schemas.py            # AgentVerdict, AggregatedReport 序列化
├── test_personas.py                 # persona 定义完整性
├── test_memory.py                   # ChromaDB 读写隔离
├── test_runner.py                   # Agent LLM 调用 + JSON 解析
├── test_aggregator.py               # 聚合公式 + 冲突检测
├── test_orchestrator.py             # 端到端编排流程
├── test_quant_engine.py             # 技术指标计算
└── test_analysis_api.py             # SSE API 端到端
```

### Modified files

```
engine/config.py                     # 新增 AgentConfig, ChromaDBConfig
engine/main.py                       # 注册 analysis + quant 路由
engine/mcpserver/server.py           # 新增 5 个 tools (3 quant + 2 agent)
engine/mcpserver/tools.py            # 新增 tool 实现函数
web/components/ui/Sidebar.tsx        # "AI 分析" 按钮
web/components/ui/AnalysisPanel.tsx   # 新建: 分析结果渲染面板
```

---

## Chunk 1: 基础设施 — Schemas + Config + Memory + Test fixtures

### Task 1: Agent Schemas (Pydantic models)

**Files:**
- Create: `engine/agent/__init__.py`
- Create: `engine/agent/schemas.py`
- Create: `tests/conftest.py`
- Create: `tests/test_agent_schemas.py`

- [ ] **Step 1: Write failing test for AnalysisRequest**

```python
# tests/test_agent_schemas.py
"""Agent schema 序列化和验证测试"""
import pytest
from datetime import datetime


def test_analysis_request_basic():
    from agent.schemas import AnalysisRequest
    req = AnalysisRequest(
        trigger_type="user",
        target="600519",
        target_type="stock",
        depth="standard",
    )
    assert req.trigger_type == "user"
    assert req.target == "600519"
    assert req.user_context is None
    assert req.event_payload is None


def test_analysis_request_rejects_invalid_trigger():
    from agent.schemas import AnalysisRequest
    with pytest.raises(Exception):
        AnalysisRequest(
            trigger_type="invalid",
            target="600519",
            target_type="stock",
            depth="standard",
        )


def test_evidence_model():
    from agent.schemas import Evidence
    e = Evidence(factor="PE", value="12.5", impact="positive", weight=0.3)
    assert e.impact == "positive"


def test_agent_verdict_full():
    from agent.schemas import AgentVerdict, Evidence
    v = AgentVerdict(
        agent_role="fundamental",
        signal="bullish",
        score=0.65,
        confidence=0.8,
        evidence=[
            Evidence(factor="PE", value="12.5 (行业偏低)", impact="positive", weight=0.3),
            Evidence(factor="ROE", value="8% (偏低)", impact="negative", weight=0.2),
        ],
        risk_flags=["业绩预告未出"],
        metadata={},
    )
    assert v.signal == "bullish"
    assert len(v.evidence) == 2
    assert v.evidence[1].impact == "negative"


def test_agent_verdict_rejects_invalid_signal():
    from agent.schemas import AgentVerdict
    with pytest.raises(Exception):
        AgentVerdict(
            agent_role="fundamental",
            signal="very_bullish",  # invalid
            score=0.5,
            confidence=0.8,
            evidence=[],
            risk_flags=[],
            metadata={},
        )


def test_aggregated_report():
    from agent.schemas import AggregatedReport, AgentVerdict
    report = AggregatedReport(
        target="600519",
        overall_signal="bullish",
        overall_score=0.45,
        verdicts=[],
        conflicts=[],
        summary="测试摘要",
        risk_level="low",
        timestamp=datetime.now(),
    )
    assert report.overall_signal == "bullish"
    assert report.risk_level == "low"


def test_prescreen_result():
    from agent.schemas import PreScreenResult
    r = PreScreenResult(
        should_continue=True,
        reason=None,
        critical_events=[],
        fast_verdict=None,
    )
    assert r.should_continue is True


def test_prescreen_result_short_circuit():
    from agent.schemas import PreScreenResult, AggregatedReport
    report = AggregatedReport(
        target="600519",
        overall_signal="bearish",
        overall_score=-0.8,
        verdicts=[],  # 短路时 verdicts 为空
        conflicts=[],
        summary="重大利空：公司被 ST",
        risk_level="high",
        timestamp=datetime.now(),
    )
    r = PreScreenResult(
        should_continue=False,
        reason="重大利空事件",
        critical_events=[{"type": "ST", "detail": "公司被 ST"}],
        fast_verdict=report,
    )
    assert r.should_continue is False
    assert r.fast_verdict.verdicts == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_agent_schemas.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: Create conftest.py with sys.path setup**

```python
# tests/conftest.py
"""pytest 全局 fixtures — 路径设置 + 共用 mock"""
import sys
from pathlib import Path

# 将 engine/ 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine"))
```

- [ ] **Step 4: Create agent/__init__.py**

```python
# engine/agent/__init__.py
"""Agent 编排层 — Multi-Agent 智能投研决策大脑"""
```

- [ ] **Step 5: Implement schemas.py**

```python
# engine/agent/schemas.py
"""Agent 接口契约 — 请求、响应、中间数据结构"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """分析请求"""
    trigger_type: Literal["user", "schedule", "event"]
    target: str = Field(description="股票代码如 '600519'，或板块名如 '白酒'")
    target_type: Literal["stock", "sector", "market"] = "stock"
    depth: Literal["quick", "standard", "deep"] = "standard"
    user_context: dict | None = None
    event_payload: dict | None = None


class Evidence(BaseModel):
    """单条论据"""
    factor: str
    value: str
    impact: Literal["positive", "negative", "neutral"]
    weight: float = Field(ge=0.0, le=1.0)


class AgentVerdict(BaseModel):
    """单个 Agent 的分析结论"""
    agent_role: str
    signal: Literal["bullish", "bearish", "neutral"]
    score: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]
    risk_flags: list[str]
    metadata: dict = Field(default_factory=dict)


class AggregatedReport(BaseModel):
    """聚合报告"""
    target: str
    overall_signal: Literal["bullish", "bearish", "neutral"]
    overall_score: float = Field(ge=-1.0, le=1.0)
    verdicts: list[AgentVerdict]
    conflicts: list[str]
    summary: str
    risk_level: Literal["low", "medium", "high"]
    timestamp: datetime


class PreScreenResult(BaseModel):
    """预检结果"""
    should_continue: bool
    reason: str | None = None
    critical_events: list[dict] = Field(default_factory=list)
    fast_verdict: AggregatedReport | None = None
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_agent_schemas.py -v`
Expected: 8 passed

- [ ] **Step 7: Commit**

```bash
git add engine/agent/__init__.py engine/agent/schemas.py tests/conftest.py tests/test_agent_schemas.py
git commit -m "feat(agent): Agent schemas — AnalysisRequest, AgentVerdict, AggregatedReport, PreScreenResult"
```

---

### Task 2: Personas + Tool Access

**Files:**
- Create: `engine/agent/personas.py`
- Create: `tests/test_personas.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_personas.py
"""Agent 人格定义和工具白名单测试"""
import pytest


def test_all_three_personas_defined():
    from agent.personas import AGENT_PERSONAS
    assert "fundamental" in AGENT_PERSONAS
    assert "info" in AGENT_PERSONAS
    assert "quant" in AGENT_PERSONAS


def test_persona_has_required_fields():
    from agent.personas import AGENT_PERSONAS
    required = {"role", "perspective", "bias", "risk_tolerance",
                "confidence_calibration", "forbidden_factors"}
    for name, persona in AGENT_PERSONAS.items():
        missing = required - set(persona.keys())
        assert not missing, f"Agent '{name}' 缺少字段: {missing}"


def test_tool_access_all_roles_defined():
    from agent.personas import AGENT_TOOL_ACCESS
    expected_roles = {"prescreen", "fundamental", "info", "quant",
                      "aggregator", "expert"}
    assert set(AGENT_TOOL_ACCESS.keys()) == expected_roles


def test_tool_access_no_overlap_for_analysis_agents():
    """基本面/消息面/技术面 Agent 的工具不应该交叉（除 search_stocks）"""
    from agent.personas import AGENT_TOOL_ACCESS
    fundamental = set(AGENT_TOOL_ACCESS["fundamental"])
    info = set(AGENT_TOOL_ACCESS["info"])
    quant = set(AGENT_TOOL_ACCESS["quant"])
    # fundamental 和 info 不应该有相同工具（factor_scores 只在 fundamental 和 quant 里）
    assert not (fundamental & info), f"基本面和消息面工具有交叉: {fundamental & info}"


def test_build_system_prompt_contains_persona():
    from agent.personas import build_system_prompt, AGENT_PERSONAS
    prompt = build_system_prompt("fundamental", calibration_weight=0.8)
    assert "基本面分析师" in prompt
    assert "价值投资" in prompt
    assert "0.8" in prompt  # calibration weight 注入


def test_build_system_prompt_contains_forbidden():
    from agent.personas import build_system_prompt
    prompt = build_system_prompt("info", calibration_weight=0.6)
    assert "PE" in prompt  # info 的 forbidden_factors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_personas.py -v`
Expected: FAIL

- [ ] **Step 3: Implement personas.py**

```python
# engine/agent/personas.py
"""Agent 人格定义 + 工具白名单 + System Prompt 构建"""

# ─── 人格定义 ──────────────────────────────────────
AGENT_PERSONAS: dict[str, dict] = {
    "fundamental": {
        "role": "基本面分析师",
        "perspective": "价值投资视角，关注财务健康、盈利质量、估值合理性",
        "bias": "偏保守，高 P/E 会降低信心",
        "risk_tolerance": 0.3,
        "confidence_calibration": 0.8,
        "forbidden_factors": ["舆情", "技术指标", "资金流向"],
    },
    "info": {
        "role": "消息面分析师",
        "perspective": "事件驱动视角，关注信息不对称和市场预期差",
        "bias": "对利空敏感，宁可错杀不可放过",
        "risk_tolerance": 0.5,
        "confidence_calibration": 0.6,
        "forbidden_factors": ["PE", "ROE", "MACD"],
    },
    "quant": {
        "role": "量化技术分析师",
        "perspective": "纯数据驱动，关注统计规律和动量",
        "bias": "中性，只看数字",
        "risk_tolerance": 0.7,
        "confidence_calibration": 0.7,
        "forbidden_factors": ["新闻", "公告", "行业政策"],
    },
}

# ─── 工具白名单 ──────────────────────────────────────
AGENT_TOOL_ACCESS: dict[str, list[str]] = {
    "prescreen": ["get_news", "get_announcements", "get_latest_snapshot"],
    "fundamental": ["get_stock_info", "get_daily_history", "get_factor_scores"],
    "info": ["get_news", "get_announcements", "assess_event_impact"],
    "quant": ["get_technical_indicators", "get_factor_scores",
              "get_signal_history", "get_cluster_for_stock"],
    "aggregator": ["get_analysis_history"],
    "expert": ["get_stock_info", "get_daily_history", "get_latest_snapshot",
               "get_news", "get_announcements", "assess_event_impact",
               "get_technical_indicators", "get_factor_scores",
               "get_signal_history", "get_cluster_for_stock",
               "get_cluster_members", "get_analysis_history"],
}


def build_system_prompt(agent_role: str, calibration_weight: float) -> str:
    """构建 Agent 的 system prompt（每次 LLM 调用时重新注入）"""
    persona = AGENT_PERSONAS[agent_role]
    forbidden = "、".join(persona["forbidden_factors"])

    return f"""你是 StockTerrain 的{persona['role']}。

## 分析视角
{persona['perspective']}

## 行为偏好
- 风格偏好: {persona['bias']}
- 风险容忍度: {persona['risk_tolerance']}（0=极保守, 1=极激进）
- 当前校准权重: {calibration_weight}（基于历史准确率动态调整）

## 严格禁止
你不得引用或分析以下因素: {forbidden}。
如果提供的数据中包含这些因素，忽略它们。

## 输出要求
你必须返回严格的 JSON 格式，包含以下字段:
- signal: "bullish" | "bearish" | "neutral"
- score: -1.0 到 1.0 的浮点数
- confidence: 0.0 到 1.0 的浮点数
- evidence: 论据列表，每条包含 factor, value, impact("positive"/"negative"/"neutral"), weight
- risk_flags: 风险提示列表
- metadata: 附加信息（可为空对象）

evidence 中必须同时包含看多(positive)和看空(negative)论据。

不要输出任何 JSON 以外的内容。不要包含 markdown 代码块标记。"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_personas.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add engine/agent/personas.py tests/test_personas.py
git commit -m "feat(agent): Agent personas + tool whitelist + system prompt builder"
```

---

### Task 3: ChromaDB Memory

**Files:**
- Modify: `engine/config.py`
- Create: `engine/agent/memory.py`
- Create: `tests/test_memory.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_memory.py
"""ChromaDB Agent Memory 隔离测试"""
import pytest
import tempfile
from pathlib import Path


@pytest.fixture
def temp_chromadb(tmp_path):
    """使用临时目录的 ChromaDB"""
    from agent.memory import AgentMemory
    return AgentMemory(persist_dir=str(tmp_path / "chromadb"))


def test_memory_store_and_retrieve(temp_chromadb):
    mem = temp_chromadb
    mem.store(
        agent_role="fundamental",
        target="600519",
        content="贵州茅台 PE 偏高，但 ROE 持续强劲，看多",
        metadata={"signal": "bullish", "confidence": 0.75},
    )
    results = mem.recall(agent_role="fundamental", query="茅台估值", top_k=1)
    assert len(results) == 1
    assert "600519" in results[0]["metadata"]["target"]


def test_memory_isolation_between_roles(temp_chromadb):
    """不同 agent_role 的记忆互不可见"""
    mem = temp_chromadb
    mem.store("fundamental", "600519", "基本面分析内容", {"signal": "bullish"})
    mem.store("quant", "600519", "量化分析内容", {"signal": "bearish"})

    fund_results = mem.recall("fundamental", "分析", top_k=10)
    quant_results = mem.recall("quant", "分析", top_k=10)

    # 基本面只能看到自己的记忆
    assert all(r["metadata"]["agent_role"] == "fundamental" for r in fund_results)
    # 量化只能看到自己的记忆
    assert all(r["metadata"]["agent_role"] == "quant" for r in quant_results)


def test_memory_empty_recall(temp_chromadb):
    results = temp_chromadb.recall("fundamental", "不存在的内容", top_k=5)
    assert results == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_memory.py -v`
Expected: FAIL

- [ ] **Step 3: Add ChromaDB config to engine/config.py**

在 `engine/config.py` 中，在 `class RedisConfig` 之后、`class AppConfig` 之前新增：

```python
class ChromaDBConfig(BaseModel):
    """ChromaDB 嵌入式向量数据库配置"""
    persist_dir: str = str(DATA_DIR / "chromadb")
    retention_days: int = 90
```

在 `AppConfig` 的 `redis` 字段之后新增一行：

```python
    chromadb: ChromaDBConfig = ChromaDBConfig()
```

- [ ] **Step 4: Implement memory.py**

```python
# engine/agent/memory.py
"""Agent Memory — ChromaDB 向量存储，按角色隔离 collection"""

from datetime import datetime
from typing import Any

import chromadb
from loguru import logger


class AgentMemory:
    """Agent 推理记忆管理器

    每个 agent_role 拥有独立的 ChromaDB collection，互不可见。
    """

    COLLECTION_PREFIX = "memory_"

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collections: dict[str, Any] = {}
        logger.info(f"ChromaDB 初始化: {persist_dir}")

    def _get_collection(self, agent_role: str):
        """获取或创建指定角色的 collection"""
        if agent_role not in self._collections:
            name = f"{self.COLLECTION_PREFIX}{agent_role}"
            self._collections[agent_role] = self._client.get_or_create_collection(name)
        return self._collections[agent_role]

    def store(
        self,
        agent_role: str,
        target: str,
        content: str,
        metadata: dict | None = None,
    ) -> str:
        """存储一条推理记忆，返回 ID"""
        collection = self._get_collection(agent_role)
        doc_id = f"{agent_role}_{target}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
        meta = {
            "agent_role": agent_role,
            "target": target,
            "timestamp": datetime.now().isoformat(),
            **(metadata or {}),
        }
        # ChromaDB metadata 只支持 str/int/float/bool
        meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v
                for k, v in meta.items()}
        collection.add(documents=[content], metadatas=[meta], ids=[doc_id])
        return doc_id

    def recall(
        self,
        agent_role: str,
        query: str,
        top_k: int = 5,
    ) -> list[dict]:
        """语义检索指定角色的历史记忆"""
        collection = self._get_collection(agent_role)
        if collection.count() == 0:
            return []
        n_results = min(top_k, collection.count())
        results = collection.query(query_texts=[query], n_results=n_results)
        entries = []
        for i in range(len(results["ids"][0])):
            entries.append({
                "id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else None,
            })
        return entries
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_memory.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add engine/config.py engine/agent/memory.py tests/test_memory.py
git commit -m "feat(agent): ChromaDB memory with per-role collection isolation"
```

---

### Task 4: QuantEngine — 技术指标计算

**Files:**
- Create: `engine/quant_engine/__init__.py`
- Create: `engine/quant_engine/indicators.py`
- Create: `engine/quant_engine/engine.py`
- Create: `tests/test_quant_engine.py`

- [ ] **Step 1: Write failing test for indicators**

```python
# tests/test_quant_engine.py
"""QuantEngine 技术指标计算测试"""
import pytest
import numpy as np
import pandas as pd


def _make_daily_df(n=60):
    """构造模拟日线数据"""
    np.random.seed(42)
    dates = pd.date_range("2026-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.randn(n) * 2)
    return pd.DataFrame({
        "date": dates,
        "open": close - np.random.rand(n),
        "high": close + np.abs(np.random.randn(n)),
        "low": close - np.abs(np.random.randn(n)),
        "close": close,
        "volume": np.random.randint(1000, 10000, n),
    })


def test_compute_rsi():
    from quant_engine.indicators import compute_rsi
    df = _make_daily_df()
    rsi = compute_rsi(df["close"], period=14)
    assert len(rsi) == len(df)
    # RSI 应在 0-100 之间（跳过 NaN）
    valid = rsi.dropna()
    assert (valid >= 0).all() and (valid <= 100).all()


def test_compute_macd():
    from quant_engine.indicators import compute_macd
    df = _make_daily_df()
    macd_line, signal_line, histogram = compute_macd(df["close"])
    assert len(macd_line) == len(df)
    assert len(signal_line) == len(df)
    assert len(histogram) == len(df)


def test_compute_bollinger():
    from quant_engine.indicators import compute_bollinger
    df = _make_daily_df()
    upper, middle, lower = compute_bollinger(df["close"], period=20)
    valid_idx = middle.dropna().index
    # 上轨 > 中轨 > 下轨
    assert (upper[valid_idx] >= middle[valid_idx]).all()
    assert (middle[valid_idx] >= lower[valid_idx]).all()


def test_quant_engine_get_technical_indicators():
    from quant_engine.engine import QuantEngine
    df = _make_daily_df()
    engine = QuantEngine()
    result = engine.compute_indicators(df)
    assert "rsi_14" in result
    assert "macd" in result
    assert "macd_signal" in result
    assert "macd_histogram" in result
    assert "boll_upper" in result
    assert "boll_lower" in result


def test_quant_engine_get_factor_scores():
    """因子评分应复用 predictor_v2 的 FACTOR_DEFS"""
    from quant_engine.engine import QuantEngine
    engine = QuantEngine()
    # factor_scores 需要 snapshot 行数据
    row = {
        "code": "600519", "pct_chg": 2.5, "turnover_rate": 1.2,
        "amount": 5e8, "pe_ttm": 30, "pb": 8, "total_mv": 2e12,
        "volatility_20d": 0.02, "momentum_20d": 0.05,
        "rsi_14": 55, "ma_deviation_20": 0.03, "ma_deviation_60": 0.08,
        "wb_ratio": 0.2,
    }
    scores = engine.get_factor_scores(row)
    assert isinstance(scores, dict)
    assert "reversal" in scores
    assert "momentum_20d" in scores
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_quant_engine.py -v`
Expected: FAIL

- [ ] **Step 3: Implement indicators.py**

```python
# engine/quant_engine/indicators.py
"""技术指标计算 — RSI, MACD, 布林带"""

import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """相对强弱指标 RSI"""
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def compute_macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD 指标"""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(
    close: pd.Series,
    period: int = 20,
    std_dev: float = 2.0,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """布林带"""
    middle = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = middle + std_dev * std
    lower = middle - std_dev * std
    return upper, middle, lower
```

- [ ] **Step 4: Implement quant_engine/engine.py**

```python
# engine/quant_engine/engine.py
"""QuantEngine — 量化技术分析引擎"""

import pandas as pd
from loguru import logger

from .indicators import compute_rsi, compute_macd, compute_bollinger


class QuantEngine:
    """量化引擎 — 技术指标 + 多因子评分"""

    def compute_indicators(self, daily_df: pd.DataFrame) -> dict:
        """计算常用技术指标，返回最新一行的指标值"""
        if daily_df.empty or "close" not in daily_df.columns:
            return {}

        close = daily_df["close"]
        rsi = compute_rsi(close, 14)
        macd_line, signal_line, histogram = compute_macd(close)
        boll_upper, boll_middle, boll_lower = compute_bollinger(close)

        # 取最新一行
        idx = daily_df.index[-1]
        return {
            "rsi_14": round(float(rsi.iloc[-1]), 2) if pd.notna(rsi.iloc[-1]) else None,
            "macd": round(float(macd_line.iloc[-1]), 4) if pd.notna(macd_line.iloc[-1]) else None,
            "macd_signal": round(float(signal_line.iloc[-1]), 4) if pd.notna(signal_line.iloc[-1]) else None,
            "macd_histogram": round(float(histogram.iloc[-1]), 4) if pd.notna(histogram.iloc[-1]) else None,
            "boll_upper": round(float(boll_upper.iloc[-1]), 2) if pd.notna(boll_upper.iloc[-1]) else None,
            "boll_middle": round(float(boll_middle.iloc[-1]), 2) if pd.notna(boll_middle.iloc[-1]) else None,
            "boll_lower": round(float(boll_lower.iloc[-1]), 2) if pd.notna(boll_lower.iloc[-1]) else None,
        }

    def get_factor_scores(self, stock_row: dict) -> dict:
        """获取多因子评分（复用 predictor_v2 的因子定义）"""
        from cluster_engine.algorithm.predictor_v2 import FACTOR_DEFS
        scores = {}
        for fdef in FACTOR_DEFS:
            col = fdef.source_col
            if col.startswith("_"):
                # 特殊因子（如 cluster_momentum），跳过
                continue
            val = stock_row.get(col)
            if val is not None:
                scores[fdef.name] = {
                    "value": round(float(val), 4),
                    "direction": fdef.direction,
                    "weight": fdef.default_weight,
                    "desc": fdef.desc,
                }
        return scores
```

- [ ] **Step 5: Create quant_engine/__init__.py**

```python
# engine/quant_engine/__init__.py
"""量化引擎模块 — 技术指标 + 多因子评分"""

from .engine import QuantEngine

_quant_engine: QuantEngine | None = None


def get_quant_engine() -> QuantEngine:
    global _quant_engine
    if _quant_engine is None:
        _quant_engine = QuantEngine()
    return _quant_engine


__all__ = ["QuantEngine", "get_quant_engine"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_quant_engine.py -v`
Expected: 5 passed

- [ ] **Step 7: Commit**

```bash
git add engine/quant_engine/ tests/test_quant_engine.py
git commit -m "feat(quant): QuantEngine with RSI, MACD, Bollinger indicators + factor scores"
```

---

## Chunk 2: Agent Runner + Aggregator + Orchestrator

### Task 5: Agent Runner (LLM 调用 + JSON 解析)

**Files:**
- Create: `engine/agent/runner.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_runner.py
"""Agent Runner — LLM 调用与 JSON 解析测试"""
import pytest
import json
from unittest.mock import AsyncMock, patch


MOCK_VERDICT_JSON = json.dumps({
    "signal": "bullish",
    "score": 0.65,
    "confidence": 0.8,
    "evidence": [
        {"factor": "PE", "value": "12.5", "impact": "positive", "weight": 0.3},
        {"factor": "负债率", "value": "偏高", "impact": "negative", "weight": 0.2},
    ],
    "risk_flags": ["业绩预告未出"],
    "metadata": {},
})


@pytest.mark.asyncio
async def test_run_agent_returns_verdict():
    from agent.runner import run_agent

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = MOCK_VERDICT_JSON

    verdict = await run_agent(
        agent_role="fundamental",
        target="600519",
        data_context={"pe_ttm": 30, "pb": 8},
        memory_context=[],
        calibration_weight=0.8,
        llm_provider=mock_provider,
    )
    assert verdict.signal == "bullish"
    assert verdict.agent_role == "fundamental"
    assert verdict.score == 0.65
    assert len(verdict.evidence) == 2


@pytest.mark.asyncio
async def test_run_agent_handles_malformed_json():
    from agent.runner import run_agent, AgentRunError

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = "这不是 JSON，我来分析一下..."

    with pytest.raises(AgentRunError):
        await run_agent(
            agent_role="quant",
            target="600519",
            data_context={},
            memory_context=[],
            calibration_weight=0.7,
            llm_provider=mock_provider,
        )


@pytest.mark.asyncio
async def test_run_agent_handles_json_in_markdown():
    """LLM 有时会返回 ```json ... ``` 包裹的内容"""
    from agent.runner import run_agent

    mock_provider = AsyncMock()
    mock_provider.chat.return_value = f"```json\n{MOCK_VERDICT_JSON}\n```"

    verdict = await run_agent(
        agent_role="fundamental",
        target="600519",
        data_context={},
        memory_context=[],
        calibration_weight=0.8,
        llm_provider=mock_provider,
    )
    assert verdict.signal == "bullish"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_runner.py -v`
Expected: FAIL

- [ ] **Step 3: Implement runner.py**

```python
# engine/agent/runner.py
"""Agent Runner — 单个 Agent 的 LLM 调用逻辑"""

import json
import re

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from .schemas import AgentVerdict
from .personas import build_system_prompt


class AgentRunError(Exception):
    """Agent 运行错误"""
    pass


def _extract_json(text: str) -> str:
    """从 LLM 输出中提取 JSON（处理 markdown 代码块包裹）"""
    # 尝试提取 ```json ... ``` 中的内容
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


async def run_agent(
    agent_role: str,
    target: str,
    data_context: dict,
    memory_context: list[dict],
    calibration_weight: float,
    llm_provider: BaseLLMProvider,
) -> AgentVerdict:
    """执行单个 Agent 分析

    Args:
        agent_role: fundamental / info / quant
        target: 股票代码
        data_context: 该 Agent 可见的数据（由 MCP tools 查询结果组成）
        memory_context: 该 Agent 的历史推理记忆
        calibration_weight: 当前校准权重
        llm_provider: LLM 调用实例

    Returns:
        AgentVerdict

    Raises:
        AgentRunError: LLM 返回无法解析的内容
    """
    system_prompt = build_system_prompt(agent_role, calibration_weight)

    # 构建用户消息
    user_parts = [f"请分析股票 {target}。\n\n## 数据\n```json\n{json.dumps(data_context, ensure_ascii=False, indent=2)}\n```"]

    if memory_context:
        memory_text = "\n".join(
            f"- [{m.get('metadata', {}).get('timestamp', '?')}] {m.get('content', '')}"
            for m in memory_context[:5]  # 最多注入 5 条历史记忆
        )
        user_parts.append(f"\n## 历史分析记忆\n{memory_text}")

    user_msg = "\n".join(user_parts)

    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_msg),
    ]

    try:
        raw = await llm_provider.chat(messages)
    except Exception as e:
        raise AgentRunError(f"LLM 调用失败 [{agent_role}]: {e}") from e

    # 解析 JSON
    json_str = _extract_json(raw)
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        logger.error(f"Agent [{agent_role}] 返回非 JSON: {raw[:200]}")
        raise AgentRunError(f"JSON 解析失败 [{agent_role}]: {e}") from e

    # 注入 agent_role
    data["agent_role"] = agent_role

    try:
        return AgentVerdict(**data)
    except Exception as e:
        raise AgentRunError(f"Verdict 校验失败 [{agent_role}]: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_runner.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add engine/agent/runner.py tests/test_runner.py
git commit -m "feat(agent): Agent runner with LLM call, JSON extraction, and error handling"
```

---

### Task 6: Aggregator (加权聚合 + 冲突检测)

**Files:**
- Create: `engine/agent/aggregator.py`
- Create: `tests/test_aggregator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_aggregator.py
"""聚合逻辑测试 — 加权公式 + 冲突检测 + 信号判定"""
import pytest
from datetime import datetime


def _make_verdict(role, signal, score, confidence):
    from agent.schemas import AgentVerdict
    return AgentVerdict(
        agent_role=role, signal=signal, score=score,
        confidence=confidence, evidence=[], risk_flags=[], metadata={},
    )


def test_aggregate_all_bullish():
    from agent.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.6, 0.8),
        _make_verdict("info", "bullish", 0.5, 0.7),
        _make_verdict("quant", "bullish", 0.7, 0.9),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert report.overall_signal == "bullish"
    assert report.overall_score > 0.2
    assert report.conflicts == []


def test_aggregate_mixed_signals_detects_conflict():
    from agent.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.7, 0.8),
        _make_verdict("info", "bearish", -0.6, 0.7),
        _make_verdict("quant", "neutral", 0.1, 0.5),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert len(report.conflicts) > 0  # 基本面看多 vs 消息面看空


def test_aggregate_formula_correctness():
    """验证加权公式: weighted = score * confidence * calibration"""
    from agent.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.5, 1.0),
        _make_verdict("info", "bearish", -0.5, 1.0),
        _make_verdict("quant", "neutral", 0.0, 1.0),
    ]
    calibrations = {"fundamental": 1.0, "info": 1.0, "quant": 1.0}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    # (0.5*1*1 + -0.5*1*1 + 0*1*1) / (1*1 + 1*1 + 1*1) = 0.0
    assert abs(report.overall_score) < 0.01
    assert report.overall_signal == "neutral"


def test_aggregate_risk_level():
    from agent.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bearish", -0.8, 0.9),
        _make_verdict("info", "bearish", -0.9, 0.8),
        _make_verdict("quant", "bearish", -0.7, 0.7),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert report.risk_level == "high"


def test_aggregate_partial_verdicts():
    """只有部分 Agent 成功时也能聚合"""
    from agent.aggregator import aggregate_verdicts
    verdicts = [
        _make_verdict("fundamental", "bullish", 0.6, 0.8),
    ]
    calibrations = {"fundamental": 0.8, "info": 0.6, "quant": 0.7}
    report = aggregate_verdicts("600519", verdicts, calibrations)
    assert report.overall_signal in ("bullish", "bearish", "neutral")
    assert len(report.verdicts) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_aggregator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement aggregator.py**

```python
# engine/agent/aggregator.py
"""聚合逻辑 — 加权评分 + 冲突检测 + 信号判定"""

from datetime import datetime

from .schemas import AgentVerdict, AggregatedReport


# 信号阈值
BULLISH_THRESHOLD = 0.2
BEARISH_THRESHOLD = -0.2
CONFLICT_CONFIDENCE_THRESHOLD = 0.6


def aggregate_verdicts(
    target: str,
    verdicts: list[AgentVerdict],
    calibrations: dict[str, float],
) -> AggregatedReport:
    """聚合多个 Agent 的 Verdict 为统一报告

    加权公式: weighted_score[i] = score[i] * confidence[i] * calibration[i]
    overall_score = sum(weighted) / sum(confidence[i] * calibration[i])
    """
    if not verdicts:
        return AggregatedReport(
            target=target,
            overall_signal="neutral",
            overall_score=0.0,
            verdicts=[],
            conflicts=[],
            summary="无可用分析结果",
            risk_level="medium",
            timestamp=datetime.now(),
        )

    # 加权计算
    weighted_sum = 0.0
    weight_sum = 0.0
    for v in verdicts:
        cal = calibrations.get(v.agent_role, 0.5)
        w = v.confidence * cal
        weighted_sum += v.score * w
        weight_sum += w

    overall_score = weighted_sum / weight_sum if weight_sum > 0 else 0.0
    overall_score = max(-1.0, min(1.0, overall_score))

    # 信号判定
    if overall_score > BULLISH_THRESHOLD:
        overall_signal = "bullish"
    elif overall_score < BEARISH_THRESHOLD:
        overall_signal = "bearish"
    else:
        overall_signal = "neutral"

    # 冲突检测
    conflicts = []
    for i, v1 in enumerate(verdicts):
        for v2 in verdicts[i + 1:]:
            if (v1.signal != v2.signal
                and v1.signal != "neutral" and v2.signal != "neutral"
                and v1.confidence > CONFLICT_CONFIDENCE_THRESHOLD
                and v2.confidence > CONFLICT_CONFIDENCE_THRESHOLD):
                conflicts.append(
                    f"{v1.agent_role}({v1.signal}, {v1.confidence:.0%}) "
                    f"vs {v2.agent_role}({v2.signal}, {v2.confidence:.0%})"
                )

    # 风险等级
    abs_score = abs(overall_score)
    if abs_score > 0.6 and overall_signal == "bearish":
        risk_level = "high"
    elif conflicts or overall_signal == "bearish":
        risk_level = "medium"
    else:
        risk_level = "low"

    # 摘要
    agent_summaries = []
    for v in verdicts:
        agent_summaries.append(f"{v.agent_role}: {v.signal}({v.score:+.2f})")
    summary = f"综合评分 {overall_score:+.2f} ({overall_signal})。" + " | ".join(agent_summaries)
    if conflicts:
        summary += f" 注意: 存在 {len(conflicts)} 处多空分歧。"

    return AggregatedReport(
        target=target,
        overall_signal=overall_signal,
        overall_score=round(overall_score, 4),
        verdicts=verdicts,
        conflicts=conflicts,
        summary=summary,
        risk_level=risk_level,
        timestamp=datetime.now(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_aggregator.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add engine/agent/aggregator.py tests/test_aggregator.py
git commit -m "feat(agent): Aggregator with weighted scoring, conflict detection, risk levels"
```

---

### Task 7: DataFetcher + Orchestrator (端到端编排)

**Files:**
- Create: `engine/agent/data_fetcher.py`
- Create: `engine/agent/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_orchestrator.py
"""Orchestrator 端到端编排测试"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


MOCK_VERDICT = json.dumps({
    "signal": "bullish", "score": 0.5, "confidence": 0.7,
    "evidence": [{"factor": "test", "value": "ok", "impact": "positive", "weight": 0.5}],
    "risk_flags": [], "metadata": {},
})


@pytest.fixture
def mock_deps():
    """Mock 所有外部依赖"""
    llm = AsyncMock()
    llm.chat.return_value = MOCK_VERDICT

    memory = MagicMock()
    memory.recall.return_value = []
    memory.store.return_value = "doc_id"

    data_fetcher = AsyncMock()
    data_fetcher.fetch_all.return_value = {
        "fundamental": {"pe_ttm": 30, "pb": 8, "pct_chg": 1.5},
        "info": {"news": [], "announcements": []},
        "quant": {"rsi_14": 55, "macd": 0.05},
    }

    return llm, memory, data_fetcher


@pytest.mark.asyncio
async def test_orchestrator_full_flow(mock_deps):
    from agent.orchestrator import Orchestrator
    from agent.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps
    orch = Orchestrator(llm_provider=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="standard",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "result" in event_types

    result_event = [e for e in events if e["event"] == "result"][0]
    assert "report" in result_event["data"]
    assert result_event["data"]["report"]["target"] == "600519"


@pytest.mark.asyncio
async def test_orchestrator_handles_agent_failure(mock_deps):
    """某个 Agent 失败时，用剩余结果聚合"""
    from agent.orchestrator import Orchestrator
    from agent.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps

    call_count = 0
    async def flaky_chat(messages):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise Exception("LLM timeout")
        return MOCK_VERDICT

    llm.chat.side_effect = flaky_chat
    orch = Orchestrator(llm_provider=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="standard",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    result_event = [e for e in events if e["event"] == "result"][0]
    assert len(result_event["data"]["report"]["verdicts"]) >= 1


@pytest.mark.asyncio
async def test_orchestrator_all_agents_fail(mock_deps):
    """所有 Agent 都失败时应返回 error 事件"""
    from agent.orchestrator import Orchestrator
    from agent.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps
    llm.chat.side_effect = Exception("LLM 全部超时")

    orch = Orchestrator(llm_provider=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="standard",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    event_types = [e["event"] for e in events]
    assert "error" in event_types
    assert "result" not in event_types


@pytest.mark.asyncio
async def test_orchestrator_quick_depth_skips_prescreen(mock_deps):
    """depth=quick 应跳过 PreScreen"""
    from agent.orchestrator import Orchestrator
    from agent.schemas import AnalysisRequest

    llm, memory, data_fetcher = mock_deps
    orch = Orchestrator(llm_provider=llm, memory=memory, data_fetcher=data_fetcher)

    req = AnalysisRequest(
        trigger_type="user", target="600519",
        target_type="stock", depth="quick",
    )

    events = []
    async for event in orch.analyze(req):
        events.append(event)

    phase_events = [e for e in events if e["event"] == "phase"]
    steps = [e["data"]["step"] for e in phase_events]
    assert "prescreen" not in steps
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_orchestrator.py -v`
Expected: FAIL

- [ ] **Step 3: Implement data_fetcher.py**

```python
# engine/agent/data_fetcher.py
"""数据获取层 — 从各引擎收集 Agent 所需数据

独立文件便于扩展（Phase 2 加入 InfoEngine 数据源）。
"""

import asyncio
import datetime

from loguru import logger


class DataFetcher:
    """从各引擎收集 Agent 所需数据

    Phase 1 MVP: 直接调用引擎 Python 接口。
    Phase 2+: 通过 MCP Tool 调用。
    """

    def get_stock_data(self, target: str) -> dict:
        """获取基本面数据（DataEngine + ClusterEngine）"""
        try:
            from data_engine import get_data_engine
            de = get_data_engine()

            info = de.get_profile(target) or {}
            snapshot = de.get_snapshot()
            stock_row = {}
            if not snapshot.empty and "code" in snapshot.columns:
                match = snapshot[snapshot["code"] == target]
                if not match.empty:
                    stock_row = match.iloc[0].to_dict()

            return {**info, **stock_row}
        except Exception as e:
            logger.warning(f"获取基本面数据失败 [{target}]: {e}")
            return {}

    def get_quant_data(self, target: str) -> dict:
        """获取量化数据（QuantEngine）"""
        try:
            from quant_engine import get_quant_engine
            from data_engine import get_data_engine

            de = get_data_engine()
            end = datetime.date.today().strftime("%Y-%m-%d")
            start = (datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            daily = de.get_daily_history(target, start, end)

            qe = get_quant_engine()
            indicators = qe.compute_indicators(daily) if not daily.empty else {}

            # 因子评分
            stock_data = self.get_stock_data(target)
            stock_data.update(indicators)
            factor_scores = qe.get_factor_scores(stock_data)

            return {**indicators, "factor_scores": factor_scores}
        except Exception as e:
            logger.warning(f"获取量化数据失败 [{target}]: {e}")
            return {}

    def get_info_data(self, target: str) -> dict:
        """获取消息面数据 — Phase 1 返回空（InfoEngine 在 Phase 2 实现）"""
        return {"news": [], "announcements": [], "note": "InfoEngine 尚未实现，消息面数据为空"}

    async def fetch_all(self, target: str) -> dict[str, dict]:
        """异步获取所有引擎数据（避免阻塞事件循环）"""
        loop = asyncio.get_event_loop()
        fund_data, info_data, quant_data = await asyncio.gather(
            loop.run_in_executor(None, self.get_stock_data, target),
            loop.run_in_executor(None, self.get_info_data, target),
            loop.run_in_executor(None, self.get_quant_data, target),
        )
        return {
            "fundamental": fund_data,
            "info": info_data,
            "quant": quant_data,
        }
```

- [ ] **Step 4: Implement orchestrator.py**

```python
# engine/agent/orchestrator.py
"""Orchestrator — Agent 编排入口"""

import asyncio
from typing import AsyncGenerator

from loguru import logger

from llm.providers import BaseLLMProvider
from .schemas import AnalysisRequest, AgentVerdict
from .personas import AGENT_PERSONAS
from .runner import run_agent, AgentRunError
from .aggregator import aggregate_verdicts
from .memory import AgentMemory
from .data_fetcher import DataFetcher


class Orchestrator:
    """编排器 — 驱动 PreScreen → 并行分析 → 聚合 流水线"""

    ANALYSIS_AGENTS = ["fundamental", "info", "quant"]
    AGENT_TIMEOUT = 30

    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        memory: AgentMemory,
        data_fetcher: DataFetcher | None = None,
    ):
        self._llm = llm_provider
        self._memory = memory
        self._data = data_fetcher or DataFetcher()

    async def analyze(
        self, request: AnalysisRequest
    ) -> AsyncGenerator[dict, None]:
        """执行分析流水线，通过 async generator 推送 SSE 事件"""
        target = request.target
        calibrations = self._get_calibrations()

        # PreScreen（depth=quick 跳过）
        if request.depth != "quick":
            yield {"event": "phase", "data": {"step": "prescreen", "status": "running"}}
            # Phase 1: 默认放行，Phase 2 接入 InfoEngine 后启用短路逻辑
            yield {"event": "phase", "data": {"step": "prescreen", "status": "done", "result": "continue"}}

        # 并行分析
        yield {"event": "phase", "data": {
            "step": "parallel_analysis", "status": "running",
            "agents": self.ANALYSIS_AGENTS,
        }}

        # 异步获取数据（不阻塞事件循环）
        data_map = await self._data.fetch_all(target)

        verdicts: list[AgentVerdict] = []
        tasks = []
        for role in self.ANALYSIS_AGENTS:
            memory_ctx = self._memory.recall(role, f"分析 {target}", top_k=3)
            tasks.append(self._run_with_timeout(
                role, target, data_map.get(role, {}), memory_ctx, calibrations
            ))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for role, result in zip(self.ANALYSIS_AGENTS, results):
            if isinstance(result, Exception):
                logger.warning(f"Agent [{role}] 失败: {result}")
                yield {"event": "agent_done", "data": {
                    "agent": role, "status": "failed", "error": str(result),
                }}
            else:
                verdicts.append(result)
                yield {"event": "agent_done", "data": {
                    "agent": role, "signal": result.signal,
                    "confidence": result.confidence, "score": result.score,
                }}

        # 全部失败 → 返回 error
        if not verdicts:
            yield {"event": "error", "data": {"message": "所有分析 Agent 均失败，无法生成报告"}}
            return

        # 聚合
        yield {"event": "phase", "data": {"step": "aggregation", "status": "running"}}
        report = aggregate_verdicts(target, verdicts, calibrations)

        # 持久化记忆
        for v in verdicts:
            try:
                self._memory.store(
                    agent_role=v.agent_role,
                    target=target,
                    content=f"signal={v.signal}, score={v.score:.2f}, confidence={v.confidence:.2f}",
                    metadata={"signal": v.signal, "confidence": v.confidence},
                )
            except Exception as e:
                logger.warning(f"记忆存储失败 [{v.agent_role}]: {e}")

        yield {"event": "result", "data": {"report": report.model_dump(mode="json")}}

    async def _run_with_timeout(
        self, role: str, target: str, data_ctx: dict,
        memory_ctx: list, calibrations: dict,
    ) -> AgentVerdict:
        cal = calibrations.get(role, 0.5)
        return await asyncio.wait_for(
            run_agent(
                agent_role=role, target=target, data_context=data_ctx,
                memory_context=memory_ctx, calibration_weight=cal,
                llm_provider=self._llm,
            ),
            timeout=self.AGENT_TIMEOUT,
        )

    def _get_calibrations(self) -> dict[str, float]:
        return {
            role: persona["confidence_calibration"]
            for role, persona in AGENT_PERSONAS.items()
        }
```

- [ ] **Step 5: Update engine/agent/__init__.py**

```python
# engine/agent/__init__.py
"""Agent 编排层 — Multi-Agent 智能投研决策大脑"""

from .orchestrator import Orchestrator
from .data_fetcher import DataFetcher
from .memory import AgentMemory

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    """获取 Orchestrator 全局单例"""
    global _orchestrator
    if _orchestrator is None:
        from llm.config import llm_settings
        from llm.providers import LLMProviderFactory
        from config import settings

        if not llm_settings.api_key:
            raise RuntimeError("LLM API Key 未配置。请设置环境变量 LLM_API_KEY 或在 .env 中配置。")

        provider = LLMProviderFactory.create(llm_settings)
        memory = AgentMemory(persist_dir=settings.chromadb.persist_dir)
        _orchestrator = Orchestrator(llm_provider=provider, memory=memory)
    return _orchestrator


__all__ = ["Orchestrator", "DataFetcher", "AgentMemory", "get_orchestrator"]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_orchestrator.py -v`
Expected: 4 passed

- [ ] **Step 7: Commit**

```bash
git add engine/agent/data_fetcher.py engine/agent/orchestrator.py engine/agent/__init__.py tests/test_orchestrator.py
git commit -m "feat(agent): Orchestrator + DataFetcher with async data fetch, depth handling, all-fail error"
```

---

## Chunk 3: API 路由 + MCP 扩展 + 前端

### Task 8: Analysis SSE API

**Files:**
- Create: `engine/api/routes/analysis.py`
- Modify: `engine/main.py`
- Create: `tests/test_analysis_api.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_analysis_api.py
"""分析 API SSE 端点测试"""
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def test_client():
    """FastAPI TestClient"""
    from fastapi.testclient import TestClient

    # Mock LLM 和 Memory
    mock_verdict = json.dumps({
        "signal": "bullish", "score": 0.5, "confidence": 0.7,
        "evidence": [], "risk_flags": [], "metadata": {},
    })

    with patch("agent.orchestrator.DataFetcher") as MockFetcher, \
         patch("agent.memory.chromadb") as mock_chromadb:

        mock_fetcher_inst = MagicMock()
        mock_fetcher_inst.get_stock_data.return_value = {"pe_ttm": 30}
        mock_fetcher_inst.get_quant_data.return_value = {"rsi_14": 55}
        mock_fetcher_inst.get_info_data.return_value = {"news": []}
        MockFetcher.return_value = mock_fetcher_inst

        # 需要在实际路由文件中 import app
        from main import app
        yield TestClient(app)


def test_analysis_endpoint_exists(test_client):
    """确认 /api/v1/analysis 路由已注册"""
    # POST 无 body 应该返回 422（参数验证失败），而非 404
    resp = test_client.post("/api/v1/analysis")
    assert resp.status_code != 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_analysis_api.py -v`
Expected: FAIL (路由不存在，返回 404)

- [ ] **Step 3: Implement analysis.py route**

```python
# engine/api/routes/analysis.py
"""分析 API — SSE 流式推送 Agent 分析进度和结果"""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from agent.schemas import AnalysisRequest

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.post("/analysis")
async def analyze(req: AnalysisRequest):
    """触发 Multi-Agent 分析流水线，SSE 流式返回进度和结果

    SSE 事件类型:
    - phase: {"step": "prescreen"|"parallel_analysis"|"aggregation", "status": "running"|"done"}
    - agent_done: {"agent": "fundamental"|"info"|"quant", "signal": "...", "confidence": 0.x}
    - result: {"report": {...AggregatedReport...}}
    - error: {"message": "..."}
    """
    from llm.config import llm_settings
    if not llm_settings.api_key:
        raise HTTPException(status_code=503, detail="LLM 未配置，请先设置 API Key")

    async def event_stream():
        try:
            from agent import get_orchestrator
            orch = get_orchestrator()
            async for event in orch.analyze(req):
                yield f"event: {event['event']}\ndata: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"分析流水线错误: {e}")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: Register route in main.py**

在 `engine/main.py` 中，在现有 router 导入后新增：

```python
from api.routes.analysis import router as analysis_router
```

在 `app.include_router(chat_router)` 后新增：

```python
app.include_router(analysis_router)
```

在 `root()` 的 endpoints dict 中新增：

```python
"analysis": "POST /api/v1/analysis (SSE 流式)",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/test_analysis_api.py -v`
Expected: 1 passed

- [ ] **Step 6: Commit**

```bash
git add engine/api/routes/analysis.py engine/main.py tests/test_analysis_api.py
git commit -m "feat(api): SSE analysis endpoint POST /api/v1/analysis"
```

---

### Task 9: MCP Tool 扩展

**Files:**
- Modify: `engine/mcpserver/server.py`
- Modify: `engine/mcpserver/tools.py`

- [ ] **Step 1: Add QuantEngine tools to server.py**

在 `engine/mcpserver/server.py` 中 `compute_terrain` tool 之后、`main()` 之前新增：

```python
# ─── QuantEngine Tools ──────────────────────────────

@server.tool()
def get_technical_indicators(code: str) -> str:
    """获取个股技术指标（RSI/MACD/布林带）。需要有日线历史数据。code 示例: '600519'"""
    return tools.get_technical_indicators(_da, code)


@server.tool()
def get_factor_scores(code: str) -> str:
    """获取个股多因子评分（13个因子的值、方向、权重）。code 示例: '600519'"""
    return tools.get_factor_scores(_da, code)


@server.tool()
def get_signal_history(code: str, days: int = 30) -> str:
    """查询个股历史量化信号记录。返回最近 N 天的买卖信号。Phase 1 返回空列表。"""
    return tools.get_signal_history(_da, code, days)


# ─── Agent Tools ────────────────────────────────────

@server.tool()
def submit_analysis(code: str, depth: str = "standard") -> str:
    """触发 AI Multi-Agent 分析。返回分析请求状态。depth: 'quick'|'standard'|'deep'。需要配置 LLM API Key。"""
    return tools.submit_analysis(code, depth)


@server.tool()
def get_analysis_history(code: str, limit: int = 5) -> str:
    """查询个股的历史 AI 分析报告。返回最近 N 条分析结果。"""
    return tools.get_analysis_history(code, limit)
```

- [ ] **Step 2: Implement tool functions in tools.py**

在 `engine/mcpserver/tools.py` 末尾新增：

```python
# ─── QuantEngine Tools ──────────────────────────────

def get_technical_indicators(da: "DataAccess", code: str) -> str:
    """获取技术指标"""
    import json
    import datetime

    try:
        from quant_engine import get_quant_engine
    except ImportError:
        return json.dumps({"error": "QuantEngine 未安装"}, ensure_ascii=False)

    # 获取日线数据
    daily = da.get_daily_history(code, days=90)
    if daily is None or daily.empty:
        return json.dumps({"error": f"无 {code} 日线数据"}, ensure_ascii=False)

    qe = get_quant_engine()
    indicators = qe.compute_indicators(daily)
    return json.dumps({
        "code": code,
        "indicators": indicators,
    }, ensure_ascii=False, indent=2)


def get_factor_scores(da: "DataAccess", code: str) -> str:
    """获取多因子评分"""
    import json

    try:
        from quant_engine import get_quant_engine
    except ImportError:
        return json.dumps({"error": "QuantEngine 未安装"}, ensure_ascii=False)

    stock_data = da.get_stock_detail(code)
    if not stock_data:
        return json.dumps({"error": f"无 {code} 数据"}, ensure_ascii=False)

    qe = get_quant_engine()
    scores = qe.get_factor_scores(stock_data)
    return json.dumps({
        "code": code,
        "factor_scores": scores,
    }, ensure_ascii=False, indent=2)


def submit_analysis(code: str, depth: str = "standard") -> str:
    """触发分析（同步返回状态，实际分析通过 REST API SSE 进行）"""
    import json
    return json.dumps({
        "status": "请通过 POST /api/v1/analysis 触发分析",
        "hint": f"curl -X POST http://localhost:8000/api/v1/analysis -H 'Content-Type: application/json' -d '{{\"trigger_type\":\"user\",\"target\":\"{code}\",\"target_type\":\"stock\",\"depth\":\"{depth}\"}}'",
    }, ensure_ascii=False, indent=2)


def get_analysis_history(code: str, limit: int = 5) -> str:
    """查询历史分析报告 — Phase 1: 返回空（持久化在 Phase 2 实现）"""
    import json
    return json.dumps({
        "code": code,
        "history": [],
        "note": "历史分析报告持久化将在 Phase 2 实现",
    }, ensure_ascii=False, indent=2)


def get_signal_history(da: "DataAccess", code: str, days: int = 30) -> str:
    """查询历史量化信号 — Phase 1: 返回空（信号持久化在 Phase 2 实现）"""
    import json
    return json.dumps({
        "code": code,
        "signals": [],
        "note": "历史信号记录将在 Phase 2 QuantEngine DuckDB 持久化后实现",
    }, ensure_ascii=False, indent=2)
```

- [ ] **Step 3: Verify MCP server starts**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from mcpserver.server import server; print(f'MCP tools: {len(server._tool_manager._tools)} registered')"`
Expected: 输出 `MCP tools: 15 registered`（10 原有 + 5 新增）

- [ ] **Step 4: Commit**

```bash
git add engine/mcpserver/server.py engine/mcpserver/tools.py
git commit -m "feat(mcp): add 4 new tools — get_technical_indicators, get_factor_scores, submit_analysis, get_analysis_history"
```

---

### Task 10: 前端 — AI 分析按钮 + 结果面板

**Files:**
- Create: `web/components/ui/AnalysisPanel.tsx`
- Modify: `web/components/ui/Sidebar.tsx`

- [ ] **Step 1: Create AnalysisPanel.tsx**

```tsx
// web/components/ui/AnalysisPanel.tsx
"use client";

/**
 * AI 分析结果面板 — SSE 流式展示 Multi-Agent 分析进度和结果
 */

import { useState, useCallback } from "react";
import { Brain, TrendingUp, TrendingDown, Minus, AlertTriangle, Loader2, CheckCircle2, XCircle } from "lucide-react";

interface AgentStatus {
  agent: string;
  status: "pending" | "running" | "done" | "failed";
  signal?: string;
  confidence?: number;
  score?: number;
  error?: string;
}

interface AnalysisReport {
  target: string;
  overall_signal: string;
  overall_score: number;
  verdicts: Array<{
    agent_role: string;
    signal: string;
    score: number;
    confidence: number;
    evidence: Array<{ factor: string; value: string; impact: string; weight: number }>;
    risk_flags: string[];
  }>;
  conflicts: string[];
  summary: string;
  risk_level: string;
}

interface Props {
  stockCode: string;
  stockName?: string;
  onClose: () => void;
}

const AGENT_LABELS: Record<string, string> = {
  fundamental: "基本面",
  info: "消息面",
  quant: "技术面",
};

const SIGNAL_CONFIG: Record<string, { icon: typeof TrendingUp; color: string; label: string }> = {
  bullish: { icon: TrendingUp, color: "text-red-500", label: "看多" },
  bearish: { icon: TrendingDown, color: "text-green-500", label: "看空" },
  neutral: { icon: Minus, color: "text-gray-500", label: "中性" },
};

export default function AnalysisPanel({ stockCode, stockName, onClose }: Props) {
  const [phase, setPhase] = useState<string>("");
  const [agents, setAgents] = useState<Record<string, AgentStatus>>({
    fundamental: { agent: "fundamental", status: "pending" },
    info: { agent: "info", status: "pending" },
    quant: { agent: "quant", status: "pending" },
  });
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isRunning, setIsRunning] = useState(false);

  const runAnalysis = useCallback(async () => {
    setIsRunning(true);
    setReport(null);
    setError(null);
    setAgents({
      fundamental: { agent: "fundamental", status: "pending" },
      info: { agent: "info", status: "pending" },
      quant: { agent: "quant", status: "pending" },
    });

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const resp = await fetch(`${apiBase}/api/v1/analysis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          trigger_type: "user",
          target: stockCode,
          target_type: "stock",
          depth: "standard",
        }),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        setError(err.detail || "请求失败");
        setIsRunning(false);
        return;
      }

      const reader = resp.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ") && eventType) {
            try {
              const data = JSON.parse(line.slice(6));
              handleSSEEvent(eventType, data);
            } catch (e) {
              console.warn("SSE 事件解析失败:", line);
            }
            eventType = "";
          }
        }
      }
    } catch (e: any) {
      setError(e.message || "网络错误");
    } finally {
      setIsRunning(false);
    }
  }, [stockCode]);

  const handleSSEEvent = (event: string, data: any) => {
    if (event === "phase") {
      setPhase(data.step);
      if (data.step === "parallel_analysis" && data.status === "running") {
        setAgents((prev) => {
          const next = { ...prev };
          for (const a of data.agents || []) {
            next[a] = { ...next[a], status: "running" };
          }
          return next;
        });
      }
    } else if (event === "agent_done") {
      setAgents((prev) => ({
        ...prev,
        [data.agent]: {
          agent: data.agent,
          status: data.status === "failed" ? "failed" : "done",
          signal: data.signal,
          confidence: data.confidence,
          score: data.score,
          error: data.error,
        },
      }));
    } else if (event === "result") {
      setReport(data.report);
    } else if (event === "error") {
      setError(data.message);
    }
  };

  const SignalBadge = ({ signal }: { signal: string }) => {
    const cfg = SIGNAL_CONFIG[signal] || SIGNAL_CONFIG.neutral;
    const Icon = cfg.icon;
    return (
      <span className={`inline-flex items-center gap-1 text-xs font-medium ${cfg.color}`}>
        <Icon className="w-3 h-3" /> {cfg.label}
      </span>
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div className="flex items-center gap-2">
          <Brain className="w-4 h-4 text-[var(--accent)]" />
          <span className="text-sm font-medium">AI 分析</span>
          <span className="text-xs text-[var(--text-secondary)]">{stockName || stockCode}</span>
        </div>
        <button onClick={onClose} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] text-lg">&times;</button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin">
        {!isRunning && !report && !error && (
          <div className="text-center py-8">
            <Brain className="w-10 h-10 mx-auto text-[var(--accent)] opacity-50 mb-3" />
            <p className="text-sm text-[var(--text-secondary)] mb-4">三维度 AI 分析: 基本面 + 消息面 + 技术面</p>
            <button onClick={runAnalysis} className="btn-primary">开始分析</button>
          </div>
        )}

        {/* Agent 进度 */}
        {isRunning && (
          <div className="space-y-2">
            {Object.values(agents).map((a) => (
              <div key={a.agent} className="flex items-center justify-between p-2 rounded-lg bg-[var(--bg-primary)]">
                <span className="text-xs font-medium">{AGENT_LABELS[a.agent] || a.agent}</span>
                <div className="flex items-center gap-2">
                  {a.status === "pending" && <span className="text-xs text-[var(--text-tertiary)]">等待中</span>}
                  {a.status === "running" && <Loader2 className="w-3 h-3 animate-spin text-[var(--accent)]" />}
                  {a.status === "done" && (
                    <>
                      <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                      {a.signal && <SignalBadge signal={a.signal} />}
                    </>
                  )}
                  {a.status === "failed" && <XCircle className="w-3 h-3 text-red-400" />}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 结果 */}
        {report && (
          <div className="space-y-3">
            {/* 总评 */}
            <div className="p-3 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs font-medium">综合评分</span>
                <SignalBadge signal={report.overall_signal} />
              </div>
              <div className="text-2xl font-bold font-mono">{report.overall_score > 0 ? "+" : ""}{report.overall_score.toFixed(2)}</div>
              <p className="text-xs text-[var(--text-secondary)] mt-1">{report.summary}</p>
            </div>

            {/* 冲突提示 */}
            {report.conflicts.length > 0 && (
              <div className="p-2 rounded-lg bg-amber-50 border border-amber-200">
                <div className="flex items-center gap-1 text-xs text-amber-700 font-medium mb-1">
                  <AlertTriangle className="w-3 h-3" /> 多空分歧
                </div>
                {report.conflicts.map((c, i) => (
                  <p key={i} className="text-xs text-amber-600">{c}</p>
                ))}
              </div>
            )}

            {/* 各 Agent 详情 */}
            {report.verdicts.map((v) => (
              <div key={v.agent_role} className="p-3 rounded-lg bg-[var(--bg-primary)] border border-[var(--border)]">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-medium">{AGENT_LABELS[v.agent_role]}</span>
                  <div className="flex items-center gap-2">
                    <SignalBadge signal={v.signal} />
                    <span className="text-xs text-[var(--text-tertiary)]">{(v.confidence * 100).toFixed(0)}%</span>
                  </div>
                </div>
                {v.evidence.length > 0 && (
                  <div className="space-y-1 mt-2">
                    {v.evidence.slice(0, 4).map((e, i) => (
                      <div key={i} className="flex items-center justify-between text-xs">
                        <span className="text-[var(--text-secondary)]">{e.factor}</span>
                        <span className={e.impact === "positive" ? "text-red-500" : e.impact === "negative" ? "text-green-500" : "text-gray-400"}>
                          {e.value}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {v.risk_flags.length > 0 && (
                  <div className="mt-2 text-xs text-amber-600">
                    {v.risk_flags.map((f, i) => <span key={i} className="mr-2">⚠ {f}</span>)}
                  </div>
                )}
              </div>
            ))}

            {/* 重新分析 */}
            <button onClick={runAnalysis} className="btn-secondary w-full text-xs">重新分析</button>
          </div>
        )}

        {/* 错误 */}
        {error && (
          <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-center">
            <p className="text-sm text-red-600 mb-2">{error}</p>
            <button onClick={runAnalysis} className="btn-secondary text-xs">重试</button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add "AI 分析" trigger to Sidebar.tsx**

在 `web/components/ui/Sidebar.tsx` 中集成 AI 分析按钮。查找方式：`grep -n "selectedStock" Sidebar.tsx` 定位选中股票展示区域。

1. 在文件顶部 import 区新增（在现有 lucide import 行追加 `Brain`）:
```tsx
import AnalysisPanel from "./AnalysisPanel";
```
并确保 lucide import 中包含 `Brain`。

2. 在组件函数体内（`function LeftPanel` 或包含选中股票逻辑的组件），添加 state:
```tsx
const [showAnalysis, setShowAnalysis] = useState(false);
```

3. 在选中股票详情区域（包含 `selectedStock.name` 的 JSX 附近），添加"AI 分析"按钮:
```tsx
<button
  onClick={() => setShowAnalysis(true)}
  className="btn-primary flex items-center gap-1.5 text-xs w-full justify-center mt-2"
>
  <Brain className="w-3.5 h-3.5" /> AI 分析
</button>
```

4. 在面板主内容区（LeftPanel return 的 JSX 中），条件渲染 AnalysisPanel:
```tsx
{showAnalysis && selectedStock && (
  <AnalysisPanel
    stockCode={selectedStock.code}
    stockName={selectedStock.name}
    onClose={() => setShowAnalysis(false)}
  />
)}
```

（注: Sidebar.tsx 约 1091 行，具体 JSX 位置需读取最新代码。关键锚点: 搜索 `selectedStock` 和 `RelatedStocksPanel` 附近。）

- [ ] **Step 3: Verify frontend compiles**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/web && npx next build 2>&1 | tail -5`
Expected: Build 成功

- [ ] **Step 4: Commit**

```bash
git add web/components/ui/AnalysisPanel.tsx web/components/ui/Sidebar.tsx
git commit -m "feat(web): AI analysis panel with SSE progress + result rendering"
```

---

### Task 11: 端到端集成验证

**Files:** 无新增

- [ ] **Step 1: 运行全量测试**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude && python -m pytest tests/ -v --tb=short`
Expected: 全部 PASS（约 25+ tests）

- [ ] **Step 2: 启动后端验证路由**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from main import app; from fastapi.testclient import TestClient; c = TestClient(app); r = c.get('/'); print([k for k in r.json()['endpoints']])"`
Expected: 输出包含 `'analysis'`

- [ ] **Step 3: 验证前端编译**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/web && npx next build 2>&1 | tail -3`
Expected: Build 成功

- [ ] **Step 4: 验证 MCP 工具数量**

Run: `cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine && python -c "from mcpserver.server import server; print(f'Tools: {len(server._tool_manager._tools)}')" 2>/dev/null`
Expected: `Tools: 15`

- [ ] **Step 5: Commit final**

如果有任何修复，先 `git status` 确认变更文件，再针对性提交:
```bash
git status
git add <具体修改的文件>
git commit -m "fix: integration fixes for Multi-Agent Phase 1 MVP"
```
