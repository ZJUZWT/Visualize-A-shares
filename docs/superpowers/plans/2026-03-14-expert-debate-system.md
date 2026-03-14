# Expert Debate System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 Orchestrator 流水线末尾新增 Phase 4 专家辩论系统，5 个 LLM 角色（多头/空头/散户/主力/裁判）围绕 Blackboard 共享状态进行结构化辩论，最终由裁判输出 JudgeVerdict。

**Architecture:** Blackboard 模式 — Orchestrator 初始化 Blackboard（含 Worker verdicts 和 facts），`run_debate()` async generator 驱动辩论循环，每轮多头必发→空头必发→观察员可选发，认输或达到 max_rounds 后裁判总结。辩论全程通过 SSE 事件实时推送。

**Tech Stack:** Python 3.11+, Pydantic v2, asyncio, loguru, ChromaDB (已有), DuckDB (已有), FastMCP (已有), ZoneInfo

---

## File Map

| 文件 | 变动 | 职责 |
|------|------|------|
| `engine/agent/schemas.py` | 修改 | 新增 `Blackboard`、`DebateEntry`、`DataRequest`、`JudgeVerdict` 4 个模型 |
| `engine/agent/personas.py` | 修改 | 新增 5 个辩论角色人格定义和完整 prompt 模板 |
| `engine/agent/data_fetcher.py` | 修改 | 新增 `fetch_by_request()` 方法和 `ACTION_DISPATCH` 路由表 |
| `engine/agent/debate.py` | 新增 | 辩论主逻辑：`run_debate`, `speak`, `judge_summarize`, `fulfill_data_requests`, `_fallback_entry`, `validate_data_requests`, `persist_debate` |
| `engine/agent/orchestrator.py` | 修改 | `analyze()` 末尾接入 Phase 4 辩论 |
| `engine/mcpserver/tools.py` | 修改 | 新增 4 个 debate tools 函数 |
| `engine/mcpserver/server.py` | 修改 | 注册 4 个新 MCP tool |
| `tests/agent/test_debate_schemas.py` | 新增 | schemas 单元测试 |
| `tests/agent/test_debate_core.py` | 新增 | debate 核心逻辑测试 |
| `tests/agent/test_data_fetcher_dispatch.py` | 新增 | fetch_by_request 路由测试 |

---

## Chunk 1: 数据结构（schemas + personas）

### Task 1: 新增辩论数据模型到 schemas.py

**Files:**
- Modify: `engine/agent/schemas.py`
- Test: `tests/agent/test_debate_schemas.py`

- [ ] **Step 1: 新建测试文件，写 schemas 测试**

```python
# tests/agent/test_debate_schemas.py
import pytest
from datetime import datetime
from engine.agent.schemas import (
    Blackboard, DebateEntry, DataRequest, JudgeVerdict, AgentVerdict
)


def make_verdict(role="fundamental"):
    return AgentVerdict(
        agent_role=role, signal="bullish", score=0.5,
        confidence=0.7, evidence=[], risk_flags=[]
    )


class TestBlackboard:
    def test_default_values(self):
        bb = Blackboard(target="600519", debate_id="600519_20260314100000")
        assert bb.round == 0
        assert bb.max_rounds == 3
        assert bb.status == "debating"
        assert bb.bull_conceded is False
        assert bb.bear_conceded is False
        assert bb.termination_reason is None
        assert bb.transcript == []
        assert bb.data_requests == []

    def test_accepts_worker_verdicts(self):
        bb = Blackboard(
            target="600519", debate_id="600519_20260314100000",
            worker_verdicts=[make_verdict(), make_verdict("quant")],
            conflicts=["基本面 vs 量化分歧"],
        )
        assert len(bb.worker_verdicts) == 2
        assert len(bb.conflicts) == 1


class TestDebateEntry:
    def test_debater_entry(self):
        entry = DebateEntry(
            role="bull_expert", round=1,
            stance="insist", speak=True,
            argument="估值合理，上涨可期",
            challenges=["空头的PE论据有误"],
            confidence=0.8,
        )
        assert entry.stance == "insist"
        assert entry.retail_sentiment_score is None

    def test_observer_silent_entry(self):
        entry = DebateEntry(role="retail_investor", round=1, speak=False)
        assert entry.speak is False
        assert entry.argument == ""
        assert entry.stance is None

    def test_retail_sentiment_score(self):
        entry = DebateEntry(
            role="retail_investor", round=1, speak=True,
            argument="论坛上都在喊冲", retail_sentiment_score=0.9
        )
        assert entry.retail_sentiment_score == 0.9


class TestDataRequest:
    def test_default_pending(self):
        req = DataRequest(
            requested_by="bull_expert", engine="quant",
            action="get_factor_scores", params={"code": "600519"}, round=1
        )
        assert req.status == "pending"
        assert req.result is None


class TestJudgeVerdict:
    def test_optional_signal(self):
        v = JudgeVerdict(
            target="600519", debate_id="600519_20260314100000",
            summary="综合来看...", signal=None, score=None,
            key_arguments=["多头：估值合理", "空头：增长放缓"],
            bull_core_thesis="估值合理，成长确定",
            bear_core_thesis="宏观压力，增速下行",
            retail_sentiment_note="散户偏乐观，需警惕反转",
            smart_money_note="资金流向中性",
            risk_warnings=["行业政策风险", "汇率波动"],
            debate_quality="strong_disagreement",
            termination_reason="max_rounds",
            timestamp=datetime.now(),
        )
        assert v.signal is None
        assert v.score is None
        assert len(v.risk_warnings) == 2
```

- [ ] **Step 2: 运行测试确认全部失败**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_debate_schemas.py -v 2>&1 | head -30
```

Expected: `ImportError` 或 `ModuleNotFoundError`（模型尚未定义）

- [ ] **Step 3: 在 schemas.py 末尾追加 4 个新模型**

在 `engine/agent/schemas.py` 文件末尾追加（在现有 `PreScreenResult` 类之后）：

```python
# ── 专家辩论系统数据结构 ─────────────────────────────────────


class DataRequest(BaseModel):
    """专家向引擎下发的数据补充请求"""
    requested_by: str                    # 提出请求的角色 ID
    engine: str                          # "data" | "quant" | "info"
    action: str                          # 具体操作名
    params: dict = Field(default_factory=dict)
    result: Any = None                   # 执行结果，初始 None
    status: Literal["pending", "done", "failed"] = "pending"
    round: int = 0                       # 提出请求时的轮次


class DebateEntry(BaseModel):
    """单条辩论发言"""
    role: str                            # bull_expert / bear_expert / retail_investor / smart_money
    round: int

    # 辩论者专属（观察员为 None）
    stance: Literal["insist", "partial_concede", "concede"] | None = None

    # 观察员专属
    speak: bool = True                   # False = 本轮选择沉默

    # 发言内容
    argument: str = ""
    challenges: list[str] = Field(default_factory=list)
    data_requests: list[DataRequest] = Field(default_factory=list)
    confidence: float = 0.5
    retail_sentiment_score: float | None = None  # 仅 retail_investor：+1极度乐观，-1极度悲观


class Blackboard(BaseModel):
    """辩论共享状态 — 所有参与者读写的中心桌面"""
    target: str
    debate_id: str                       # "{target}_{YYYYMMDDHHMMSS}"

    # 事实层（Phase 2/3 产出，只读）
    facts: dict[str, Any] = Field(default_factory=dict)
    worker_verdicts: list[AgentVerdict] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)

    # 辩论层
    transcript: list[DebateEntry] = Field(default_factory=list)

    # 数据请求层
    data_requests: list[DataRequest] = Field(default_factory=list)

    # 控制层
    round: int = 0
    max_rounds: int = 3
    bull_conceded: bool = False
    bear_conceded: bool = False
    status: Literal["debating", "final_round", "judging", "completed"] = "debating"
    termination_reason: Literal[
        "bull_conceded", "bear_conceded", "both_conceded", "max_rounds"
    ] | None = None


class JudgeVerdict(BaseModel):
    """裁判最终总结"""
    target: str
    debate_id: str
    summary: str
    signal: Literal["bullish", "bearish", "neutral"] | None = None
    score: float | None = None

    key_arguments: list[str]
    bull_core_thesis: str
    bear_core_thesis: str
    retail_sentiment_note: str
    smart_money_note: str
    risk_warnings: list[str]
    debate_quality: Literal["consensus", "strong_disagreement", "one_sided"]
    termination_reason: str
    timestamp: datetime
```

注意：在文件顶部的 import 区域补充 `from typing import Any`（如果还没有）。

- [ ] **Step 4: 运行测试确认全部通过**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_debate_schemas.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add engine/agent/schemas.py tests/agent/test_debate_schemas.py
git commit -m "feat: 新增专家辩论数据模型 Blackboard/DebateEntry/DataRequest/JudgeVerdict"
```

---

### Task 2: 新增辩论角色人格到 personas.py

**Files:**
- Modify: `engine/agent/personas.py`

- [ ] **Step 1: 在 personas.py 末尾追加辩论角色定义**

在 `engine/agent/personas.py` 文件末尾追加：

```python
# ── 专家辩论角色人格 ──────────────────────────────────────────

DEBATE_PERSONAS: dict[str, dict] = {
    "bull_expert": {
        "role": "多头专家",
        "description": "金融专业者，价值发现视角，坚定看多",
    },
    "bear_expert": {
        "role": "空头专家",
        "description": "金融专业者，风险识别视角，坚定看空",
    },
    "retail_investor": {
        "role": "散户代表",
        "description": "大众投资者情绪与行为视角，反向参考指标",
    },
    "smart_money": {
        "role": "主力代表",
        "description": "机构和大资金行为视角，量价关系与资金信号",
    },
    "judge": {
        "role": "裁判",
        "description": "资深金融专业人士，综合各方观点做最终汇总",
    },
}

_DEBATER_SYSTEM_TEMPLATE = """{stance_desc}

## 你的使命
你必须为{direction} {target} 寻找并捍卫一切有据可查的理由。你的立场是坚定的，
不轻易被说服。只有当对方的论据真正压倒性、你找不到任何有效反驳时，
才可以选择认输（concede）。轻易认输是不诚实的表现。

## 行为规范
- 论据必须基于数据和金融逻辑，不允许无根据的{bias}
- 每轮必须针对对方上一轮的核心论点提出具体反驳
- 如果需要更多数据支撑论点，可通过 data_requests 请求（最后一轮除外）
- partial_concede 表示承认对方某个具体论点，但整体立场不变

## 输出格式（严格 JSON，不含 markdown 代码块）
{{
  "stance": "insist" | "partial_concede" | "concede",
  "argument": "你的核心发言内容",
  "challenges": ["你质疑对方的具体论据1", "..."],
  "confidence": 0.0到1.0的浮点数,
  "data_requests": [
    {{"engine": "quant", "action": "get_factor_scores", "params": {{"code": "xxx"}}}}
  ]
}}
{final_round_note}"""

_OBSERVER_SYSTEM_TEMPLATE = """{observer_desc}

## 发言决策
如果当前辩论中缺乏{perspective}视角的信息，或你有重要信息要补充，
选择发言（speak: true）。否则选择沉默（speak: false）。

## 输出格式（严格 JSON，不含 markdown 代码块）
{output_schema}
{final_round_note}"""

_FINAL_ROUND_NOTE = "\n## 重要\n这是最后一轮辩论。请发表你的最终观点，总结你认为最核心的论据。本轮结束后裁判将做出最终裁决。"

JUDGE_SYSTEM_PROMPT = """你是一位资深金融专业人士，担任本次辩论的裁判。

## 你的职责
综合以下所有信息，为用户提供一份客观、专业的投资参考报告：
- 三位 Worker 分析师的初步判断（基本面/消息面/技术面）
- 多头专家和空头专家的完整辩论记录（含各轮 stance 变化）
- 散户代表的情绪面观察（注意：散户情绪具有反向参考价值）
- 主力代表的资金面观察

## debate_quality 判定规则
- "consensus": 有一方认输
- "strong_disagreement": max_rounds 到达且双方最后一轮 confidence 差值 < 0.3
- "one_sided": max_rounds 到达且一方最后一轮 confidence < 0.35、另一方 > 0.65

## 输出要求
- summary: 面向普通用户，语言清晰易懂，客观呈现多空双方的核心观点
- signal/score 不强制填写，信息不充分时可为 null
- retail_sentiment_note 必须说明散户情绪的反向参考含义
- risk_warnings 必须具体，至少包含一条，不允许"市场有不确定性"此类泛泛表述

## 输出格式（严格 JSON，不含 markdown 代码块）
注意：target、debate_id、termination_reason、timestamp 由调用代码注入，无需输出
{
  "summary": "...",
  "signal": "bullish" | "bearish" | "neutral" | null,
  "score": 浮点数或null,
  "key_arguments": ["..."],
  "bull_core_thesis": "...",
  "bear_core_thesis": "...",
  "retail_sentiment_note": "...",
  "smart_money_note": "...",
  "risk_warnings": ["具体风险1", "..."],
  "debate_quality": "consensus" | "strong_disagreement" | "one_sided"
}"""


def build_debate_system_prompt(role: str, target: str, is_final_round: bool) -> str:
    """构建辩论角色的 system prompt"""
    final_note = _FINAL_ROUND_NOTE if is_final_round else ""

    if role == "bull_expert":
        return _DEBATER_SYSTEM_TEMPLATE.format(
            stance_desc="你是一位资深金融专业人士，在本次辩论中扮演多头（看多）角色。",
            direction="看多",
            target=target,
            bias="乐观",
            final_round_note=final_note,
        )
    elif role == "bear_expert":
        return _DEBATER_SYSTEM_TEMPLATE.format(
            stance_desc="你是一位资深金融专业人士，在本次辩论中扮演空头（看空）角色。",
            direction="看空",
            target=target,
            bias="悲观",
            final_round_note=final_note,
        )
    elif role == "retail_investor":
        return _OBSERVER_SYSTEM_TEMPLATE.format(
            observer_desc="你是市场散户的代表，代表大众投资者的情绪和行为视角。\n\n## 你的视角\n- 关注市场热度、讨论热度、追涨杀跌行为模式\n- 你的情绪往往是反向指标（极度乐观时可能是见顶信号）\n- 你不需要选边站，只提供你观察到的市场情绪信息",
            perspective="市场情绪",
            output_schema='{\n  "speak": true 或 false,\n  "argument": "你的观察内容（speak=false 时为空字符串）",\n  "retail_sentiment_score": -1.0到1.0的浮点数,\n  "data_requests": []\n}',
            final_round_note=final_note,
        )
    elif role == "smart_money":
        return _OBSERVER_SYSTEM_TEMPLATE.format(
            observer_desc="你是市场主力资金的代表，代表机构和大资金的行为视角。\n\n## 你的视角\n- 关注量价关系、大单方向、资金流向等技术面资金信号\n- 你的判断基于可观察的资金行为数据，不基于基本面或消息面\n- 你不需要选边站，只提供你观察到的资金面信息",
            perspective="资金面",
            output_schema='{\n  "speak": true 或 false,\n  "argument": "你的观察内容（speak=false 时为空字符串）",\n  "data_requests": [\n    {"engine": "quant", "action": "get_technical_indicators", "params": {"code": "xxx"}}\n  ]\n}',
            final_round_note=final_note,
        )
    elif role == "judge":
        return JUDGE_SYSTEM_PROMPT
    else:
        raise ValueError(f"未知辩论角色: {role}")
```

- [ ] **Step 2: 快速验证函数可调用**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine
python -c "
from agent.personas import build_debate_system_prompt, JUDGE_SYSTEM_PROMPT
p = build_debate_system_prompt('bull_expert', '600519', False)
assert '看多' in p and '600519' in p
p2 = build_debate_system_prompt('bull_expert', '600519', True)
assert '最后一轮' in p2
p3 = build_debate_system_prompt('retail_investor', '600519', False)
assert '散户' in p3
print('personas OK')
"
```

Expected: `personas OK`

- [ ] **Step 3: 提交**

```bash
git add engine/agent/personas.py
git commit -m "feat: 新增辩论角色人格定义和 prompt 模板 (5 个角色)"
```

---

## Chunk 2: DataFetcher 路由扩展

### Task 3: 新增 fetch_by_request 到 data_fetcher.py

**Files:**
- Modify: `engine/agent/data_fetcher.py`
- Test: `tests/agent/test_data_fetcher_dispatch.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/test_data_fetcher_dispatch.py
import asyncio
import pytest
from unittest.mock import MagicMock, patch
from engine.agent.schemas import DataRequest
from engine.agent.data_fetcher import DataFetcher


class TestFetchByRequest:
    def setup_method(self):
        self.fetcher = DataFetcher()

    def test_raises_on_unknown_action(self):
        req = DataRequest(
            requested_by="bull_expert", engine="quant",
            action="hack_the_system", params={}, round=1
        )
        with pytest.raises(ValueError, match="不支持的 action"):
            asyncio.run(self.fetcher.fetch_by_request(req))

    def test_routes_get_stock_info(self):
        req = DataRequest(
            requested_by="bull_expert", engine="data",
            action="get_stock_info", params={"code": "600519"}, round=1
        )
        with patch.object(self.fetcher, 'get_stock_data', return_value={"name": "贵州茅台"}):
            result = asyncio.run(self.fetcher.fetch_by_request(req))
            assert result == {"name": "贵州茅台"}

    def test_routes_get_technical_indicators(self):
        req = DataRequest(
            requested_by="smart_money", engine="quant",
            action="get_technical_indicators", params={"code": "600519"}, round=1
        )
        with patch.object(self.fetcher, 'get_quant_data', return_value={"macd": 0.5}):
            result = asyncio.run(self.fetcher.fetch_by_request(req))
            assert result == {"macd": 0.5}
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_data_fetcher_dispatch.py -v 2>&1 | head -20
```

Expected: `AttributeError` 或 `ImportError`

- [ ] **Step 3: 在 data_fetcher.py 末尾追加路由表和方法**

在 `engine/agent/data_fetcher.py` 的 `DataFetcher` 类中追加：

```python
    # ── 动态路由（辩论系统专用）────────────────────────────

    # action → (method_name, is_async) 的映射（白名单以外的 action 一律拒绝）
    _ACTION_DISPATCH: dict[str, tuple[str, bool]] = {
        "get_stock_info":           ("get_stock_data", False),
        "get_daily_history":        ("get_stock_data", False),
        "get_technical_indicators": ("get_quant_data", False),
        "get_factor_scores":        ("get_quant_data", False),
        "get_news":                 ("get_info_data", True),   # async
        "get_announcements":        ("get_info_data", True),   # async
        "get_cluster_for_stock":    ("_get_cluster_data", False),
    }

    async def fetch_by_request(self, request) -> dict:
        """按 DataRequest 动态路由到对应引擎方法（async）

        白名单之外的 action 抛出 ValueError。
        get_info_data 是 async coroutine，其余 sync 方法通过 asyncio.to_thread 包装。
        """
        action = request.action
        dispatch = self._ACTION_DISPATCH.get(action)
        if not dispatch:
            raise ValueError(f"不支持的 action: {action}，仅允许 {list(self._ACTION_DISPATCH.keys())}")

        method_name, is_async = dispatch
        code = request.params.get("code", "")
        method = getattr(self, method_name)

        if is_async:
            return await method(code)
        else:
            return await asyncio.to_thread(method, code)

    def _get_cluster_data(self, target: str) -> dict:
        """获取聚类归属信息"""
        try:
            from cluster_engine import get_cluster_engine
            ce = get_cluster_engine()
            result = ce.get_cluster_for_stock(target)
            return result if result else {}
        except Exception as e:
            logger.warning(f"获取聚类数据失败 [{target}]: {e}")
            return {}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_data_fetcher_dispatch.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add engine/agent/data_fetcher.py tests/agent/test_data_fetcher_dispatch.py
git commit -m "feat: DataFetcher 新增 fetch_by_request 动态路由"
```

---

## Chunk 3: 辩论核心逻辑

### Task 4: 新建 debate.py — 核心辩论逻辑

**Files:**
- Create: `engine/agent/debate.py`
- Test: `tests/agent/test_debate_core.py`

- [ ] **Step 1: 写核心逻辑的失败测试**

```python
# tests/agent/test_debate_core.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from engine.agent.schemas import (
    Blackboard, DebateEntry, DataRequest, JudgeVerdict, AgentVerdict
)
from engine.agent.debate import (
    validate_data_requests,
    _fallback_entry,
    _parse_debate_entry,
    _parse_judge_output,
)


# ── validate_data_requests ────────────────────────────

class TestValidateDataRequests:
    def _make_req(self, role, action):
        return DataRequest(requested_by=role, engine="quant", action=action, round=1)

    def test_filters_out_of_whitelist(self):
        reqs = [self._make_req("bull_expert", "hack_system")]
        result = validate_data_requests("bull_expert", reqs)
        assert result == []

    def test_allows_whitelisted_action(self):
        reqs = [self._make_req("bull_expert", "get_factor_scores")]
        result = validate_data_requests("bull_expert", reqs)
        assert len(result) == 1

    def test_truncates_beyond_max(self):
        reqs = [self._make_req("bull_expert", "get_factor_scores")] * 5
        result = validate_data_requests("bull_expert", reqs)
        assert len(result) == 2  # MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND = 2

    def test_retail_investor_only_gets_news(self):
        reqs = [
            self._make_req("retail_investor", "get_news"),
            self._make_req("retail_investor", "get_factor_scores"),  # 不允许
        ]
        result = validate_data_requests("retail_investor", reqs)
        assert len(result) == 1
        assert result[0].action == "get_news"


# ── _fallback_entry ──────────────────────────────────

class TestFallbackEntry:
    def test_debater_fallback(self):
        entry = _fallback_entry("bull_expert", round=2, reason="timeout")
        assert entry.stance == "insist"
        assert entry.speak is True
        assert entry.round == 2

    def test_observer_fallback(self):
        entry = _fallback_entry("retail_investor", round=1, reason="error")
        assert entry.speak is False
        assert entry.stance is None


# ── _parse_debate_entry ──────────────────────────────

class TestParseDebateEntry:
    def test_parses_valid_debater_json(self):
        raw = '{"stance": "insist", "argument": "PE合理", "challenges": ["空头误判"], "confidence": 0.8, "data_requests": []}'
        entry = _parse_debate_entry("bull_expert", round=1, raw=raw)
        assert entry.stance == "insist"
        assert entry.confidence == 0.8

    def test_parses_observer_with_speak_false(self):
        raw = '{"speak": false, "argument": "", "retail_sentiment_score": null, "data_requests": []}'
        entry = _parse_debate_entry("retail_investor", round=1, raw=raw)
        assert entry.speak is False

    def test_falls_back_on_invalid_json(self):
        entry = _parse_debate_entry("bull_expert", round=1, raw="not json at all")
        assert entry.stance == "insist"  # fallback


# ── _parse_judge_output ──────────────────────────────

class TestParseJudgeOutput:
    def test_injects_metadata(self):
        raw = '''{
            "summary": "综合来看...",
            "signal": "neutral",
            "score": 0.1,
            "key_arguments": ["多头论据"],
            "bull_core_thesis": "估值合理",
            "bear_core_thesis": "增速下行",
            "retail_sentiment_note": "散户偏乐观，反向信号",
            "smart_money_note": "资金流向中性",
            "risk_warnings": ["行业政策风险"],
            "debate_quality": "strong_disagreement"
        }'''
        bb = Blackboard(
            target="600519", debate_id="600519_20260314100000",
            termination_reason="max_rounds",
        )
        verdict = _parse_judge_output(raw=raw, blackboard=bb)
        assert verdict.target == "600519"
        assert verdict.debate_id == "600519_20260314100000"
        assert verdict.termination_reason == "max_rounds"
        assert isinstance(verdict.timestamp, datetime)
```

- [ ] **Step 2: 运行确认失败**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_debate_core.py -v 2>&1 | head -20
```

Expected: `ImportError`（debate.py 不存在）

- [ ] **Step 3: 新建 engine/agent/debate.py**

```python
"""
debate.py — 专家辩论系统核心逻辑

Blackboard 模式：
- run_debate(): async generator，驱动辩论主循环，推送 SSE 事件
- speak(): 单个角色发言（含超时/异常 fallback）
- judge_summarize(): 裁判总结
- fulfill_data_requests(): 执行专家的数据补充请求
- validate_data_requests(): 白名单过滤
- _fallback_entry(): LLM 失败时的默认发言
- _parse_debate_entry(): 解析 LLM JSON 输出为 DebateEntry
- _parse_judge_output(): 解析裁判 LLM 输出并注入元数据
- persist_debate(): 持久化到 DuckDB
"""

import asyncio
import json
import re
from datetime import datetime
from typing import AsyncGenerator
from zoneinfo import ZoneInfo

from loguru import logger

from llm.providers import BaseLLMProvider, ChatMessage
from agent.memory import AgentMemory
from agent.data_fetcher import DataFetcher
from agent.schemas import Blackboard, DebateEntry, DataRequest, JudgeVerdict
from agent.personas import build_debate_system_prompt, JUDGE_SYSTEM_PROMPT

# ── 常量 ──────────────────────────────────────────────

DEBATE_DATA_WHITELIST: dict[str, list[str]] = {
    "bull_expert": [
        "get_stock_info", "get_daily_history", "get_factor_scores",
        "get_news", "get_announcements", "get_technical_indicators",
        "get_cluster_for_stock",
    ],
    "bear_expert": [
        "get_stock_info", "get_daily_history", "get_factor_scores",
        "get_news", "get_announcements", "get_technical_indicators",
        "get_cluster_for_stock",
    ],
    "retail_investor": ["get_news"],
    "smart_money": ["get_technical_indicators", "get_factor_scores"],
}
MAX_DATA_REQUESTS_PER_ROLE_PER_ROUND = 2
OBSERVERS = ["retail_investor", "smart_money"]


# ── 辅助函数 ──────────────────────────────────────────

def _extract_json(text: str) -> str:
    """从 LLM 输出提取 JSON（处理 markdown 代码块）"""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()


def validate_data_requests(role: str, requests: list[DataRequest]) -> list[DataRequest]:
    """白名单过滤 + 数量截断。不抛出异常。"""
    allowed = DEBATE_DATA_WHITELIST.get(role, [])
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


def _fallback_entry(role: str, round: int, reason: str) -> DebateEntry:
    """LLM 失败时的默认发言"""
    if role in OBSERVERS:
        return DebateEntry(role=role, round=round, speak=False, argument="")
    # 辩论者默认 insist
    return DebateEntry(
        role=role, round=round,
        stance="insist",
        speak=True,
        argument=f"（本轮发言暂时不可用：{reason}）",
        confidence=0.5,
    )


def _parse_debate_entry(role: str, round: int, raw: str) -> DebateEntry:
    """解析 LLM 输出为 DebateEntry，解析失败时返回 fallback"""
    try:
        json_str = _extract_json(raw)
        data = json.loads(json_str)
        data["role"] = role
        data["round"] = round
        # 将嵌套的 data_requests 列表转为 DataRequest 对象
        raw_reqs = data.pop("data_requests", [])
        data_requests = []
        for r in raw_reqs:
            if isinstance(r, dict):
                data_requests.append(DataRequest(
                    requested_by=role,
                    engine=r.get("engine", "quant"),
                    action=r.get("action", ""),
                    params=r.get("params", {}),
                    round=round,
                ))
        data["data_requests"] = data_requests
        return DebateEntry(**data)
    except Exception as e:
        logger.warning(f"解析辩论发言失败 [{role}]: {e}，使用 fallback")
        return _fallback_entry(role, round, reason=f"parse_error: {e}")


def _parse_judge_output(raw: str, blackboard: Blackboard) -> JudgeVerdict:
    """解析裁判 LLM 输出，注入 target/debate_id/termination_reason/timestamp"""
    json_str = _extract_json(raw)
    data = json.loads(json_str)
    # 注入元数据（LLM 不生成这 4 个字段）
    data["target"] = blackboard.target
    data["debate_id"] = blackboard.debate_id
    data["termination_reason"] = blackboard.termination_reason or "max_rounds"
    data["timestamp"] = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    return JudgeVerdict(**data)


def _build_context_for_role(blackboard: Blackboard) -> str:
    """将 Blackboard 核心内容序列化为 LLM 可读的上下文"""
    parts = []

    # Worker 初步判断
    if blackboard.worker_verdicts:
        parts.append("## Worker 分析师初步判断")
        for v in blackboard.worker_verdicts:
            parts.append(f"- {v.agent_role}: {v.signal} (score={v.score:.2f}, confidence={v.confidence:.2f})")

    # 分歧
    if blackboard.conflicts:
        parts.append("\n## 已检测到的分歧")
        for c in blackboard.conflicts:
            parts.append(f"- {c}")

    # 辩论记录
    if blackboard.transcript:
        parts.append("\n## 辩论记录")
        for entry in blackboard.transcript:
            if not entry.speak and entry.role in OBSERVERS:
                continue  # 沉默的观察员不出现在上下文
            stance_str = f" [{entry.stance}]" if entry.stance else ""
            parts.append(f"\n**Round {entry.round} - {entry.role}{stance_str}** (confidence={entry.confidence:.2f})")
            if entry.argument:
                parts.append(entry.argument)
            if entry.challenges:
                parts.append("质疑: " + "；".join(entry.challenges))

    # 已到位的补充数据
    done_reqs = [r for r in blackboard.data_requests if r.status == "done"]
    if done_reqs:
        parts.append("\n## 补充数据")
        for r in done_reqs:
            parts.append(f"- {r.action} ({r.requested_by} 请求): {str(r.result)[:200]}")

    return "\n".join(parts)


# ── 核心函数 ──────────────────────────────────────────

async def speak(
    role: str,
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    is_final_round: bool,
) -> DebateEntry:
    """单个角色发言，含超时和异常 fallback"""
    memory_ctx = memory.recall(role, f"辩论 {blackboard.target}", top_k=3)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 你的历史辩论记忆\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )

    system_prompt = build_debate_system_prompt(role, blackboard.target, is_final_round)
    context = _build_context_for_role(blackboard)
    user_content = f"## 当前辩论状态（Round {blackboard.round}）\n\n{context}{memory_text}\n\n请发表你的观点。"

    messages = [
        ChatMessage("system", system_prompt),
        ChatMessage("user", user_content),
    ]

    try:
        raw = await asyncio.wait_for(llm.chat(messages), timeout=45.0)
        entry = _parse_debate_entry(role, blackboard.round, raw)
    except asyncio.TimeoutError:
        logger.warning(f"辩论角色 [{role}] LLM 超时，使用 fallback")
        entry = _fallback_entry(role, blackboard.round, reason="timeout")
    except Exception as e:
        logger.warning(f"辩论角色 [{role}] LLM 失败: {e}，使用 fallback")
        entry = _fallback_entry(role, blackboard.round, reason=str(e))

    if not is_final_round:
        validated = validate_data_requests(role, entry.data_requests)
        blackboard.data_requests.extend(validated)

    return entry


async def fulfill_data_requests(
    pending: list[DataRequest],
    data_fetcher: DataFetcher,
) -> None:
    """执行数据请求，结果就地写入 req.result/status。不抛出异常。

    fetch_by_request 已是 async（内部按需 to_thread），直接 await 即可。
    """
    for req in pending:
        try:
            result = await data_fetcher.fetch_by_request(req)
            req.result = result
            req.status = "done"
        except Exception as e:
            logger.warning(f"数据请求失败 [{req.action}]: {e}")
            req.result = f"获取失败: {e}"
            req.status = "failed"


async def judge_summarize(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
) -> JudgeVerdict:
    """裁判总结——读完整 Blackboard，输出 JudgeVerdict"""
    memory_ctx = memory.recall("judge", f"辩论 {blackboard.target}", top_k=3)
    memory_text = ""
    if memory_ctx:
        memory_text = "\n## 你过去类似辩论的裁决记录\n" + "\n".join(
            f"- {m.get('content', '')}" for m in memory_ctx[:3]
        )

    context = _build_context_for_role(blackboard)
    user_content = (
        f"## 完整辩论记录（标的：{blackboard.target}）\n\n{context}{memory_text}\n\n"
        f"辩论终止原因：{blackboard.termination_reason}，共进行 {blackboard.round} 轮。\n\n"
        "请做出你的最终裁决。"
    )

    messages = [
        ChatMessage("system", JUDGE_SYSTEM_PROMPT),
        ChatMessage("user", user_content),
    ]

    try:
        raw = await asyncio.wait_for(llm.chat(messages), timeout=60.0)
        verdict = _parse_judge_output(raw, blackboard)
    except Exception as e:
        logger.error(f"裁判总结失败: {e}，生成降级 verdict")
        verdict = JudgeVerdict(
            target=blackboard.target,
            debate_id=blackboard.debate_id,
            summary=f"裁判总结暂时不可用（{e}），请参考各方辩论记录自行判断。",
            signal=None, score=None,
            key_arguments=[],
            bull_core_thesis="（不可用）",
            bear_core_thesis="（不可用）",
            retail_sentiment_note="（不可用）",
            smart_money_note="（不可用）",
            risk_warnings=["裁判服务异常，请谨慎参考"],
            debate_quality="strong_disagreement",
            termination_reason=blackboard.termination_reason or "max_rounds",
            timestamp=datetime.now(tz=ZoneInfo("Asia/Shanghai")),
        )

    # 存储裁判记忆
    try:
        memory.store(
            agent_role="judge",
            target=blackboard.target,
            content=f"裁决: {verdict.debate_quality}, signal={verdict.signal}",
            metadata={"debate_id": blackboard.debate_id, "signal": str(verdict.signal)},
        )
    except Exception as e:
        logger.warning(f"裁判记忆存储失败: {e}")

    return verdict


async def persist_debate(
    blackboard: Blackboard,
    judge_verdict: JudgeVerdict,
) -> None:
    """持久化到 DuckDB shared.debate_records。失败只记录 warning，不抛出。

    使用 DataEngine 单例的已有连接，避免多进程锁冲突。
    """
    try:
        from data_engine import get_data_engine
        con = get_data_engine().store._conn

        con.execute("CREATE SCHEMA IF NOT EXISTS shared")
        con.execute("""
            CREATE TABLE IF NOT EXISTS shared.debate_records (
                id                  VARCHAR PRIMARY KEY,
                target              VARCHAR,
                max_rounds          INTEGER,
                rounds_completed    INTEGER,
                termination_reason  VARCHAR,
                blackboard_json     TEXT,
                judge_verdict_json  TEXT,
                created_at          TIMESTAMP,
                completed_at        TIMESTAMP
            )
        """)

        now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
        con.execute("""
            INSERT INTO shared.debate_records
                (id, target, max_rounds, rounds_completed, termination_reason,
                 blackboard_json, judge_verdict_json, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                rounds_completed   = excluded.rounds_completed,
                termination_reason = excluded.termination_reason,
                blackboard_json    = excluded.blackboard_json,
                judge_verdict_json = excluded.judge_verdict_json,
                completed_at       = excluded.completed_at
        """, [
            blackboard.debate_id,
            blackboard.target,
            blackboard.max_rounds,
            blackboard.round,
            blackboard.termination_reason,
            blackboard.model_dump_json(),
            judge_verdict.model_dump_json(),
            now,
            now,
        ])
        logger.info(f"辩论记录已持久化: {blackboard.debate_id}")
    except Exception as e:
        logger.warning(f"辩论记录持久化失败: {e}")


# ── 主循环 ────────────────────────────────────────────

async def run_debate(
    blackboard: Blackboard,
    llm: BaseLLMProvider,
    memory: AgentMemory,
    data_fetcher: DataFetcher,
) -> AsyncGenerator[dict, None]:
    """专家辩论主循环 — async generator，推送 SSE 事件"""

    def sse(event: str, data: dict) -> dict:
        return {"event": event, "data": data}

    yield sse("debate_start", {
        "debate_id": blackboard.debate_id,
        "target": blackboard.target,
        "max_rounds": blackboard.max_rounds,
        "participants": ["bull_expert", "bear_expert", "retail_investor", "smart_money", "judge"],
    })

    while blackboard.round < blackboard.max_rounds:
        blackboard.round += 1
        is_final = (blackboard.round == blackboard.max_rounds)

        if is_final:
            blackboard.status = "final_round"

        yield sse("debate_round_start", {
            "round": blackboard.round,
            "is_final": is_final,
        })

        # 1. 多头发言
        bull_entry = await speak("bull_expert", blackboard, llm, memory, is_final)
        blackboard.transcript.append(bull_entry)
        if bull_entry.stance == "concede":
            blackboard.bull_conceded = True
        yield sse("debate_entry", bull_entry.model_dump(mode="json"))

        # 2. 空头发言
        bear_entry = await speak("bear_expert", blackboard, llm, memory, is_final)
        blackboard.transcript.append(bear_entry)
        if bear_entry.stance == "concede":
            blackboard.bear_conceded = True
        yield sse("debate_entry", bear_entry.model_dump(mode="json"))

        # 3. 观察员
        for observer in OBSERVERS:
            entry = await speak(observer, blackboard, llm, memory, is_final)
            blackboard.transcript.append(entry)
            if entry.speak:
                yield sse("debate_entry", entry.model_dump(mode="json"))

        # 4. 执行数据请求
        pending = [r for r in blackboard.data_requests if r.status == "pending"]
        if pending and not is_final:
            for req in pending:
                yield sse("data_fetching", {
                    "requested_by": req.requested_by,
                    "engine": req.engine,
                    "action": req.action,
                })
            await fulfill_data_requests(pending, data_fetcher)
            yield sse("data_ready", {
                "count": len(pending),
                "result_summary": f"已获取 {len(pending)} 条补充数据",
            })

        # 5. 轮次控制
        if blackboard.bull_conceded and blackboard.bear_conceded:
            blackboard.termination_reason = "both_conceded"
            break
        elif blackboard.bull_conceded:
            blackboard.termination_reason = "bull_conceded"
            break
        elif blackboard.bear_conceded:
            blackboard.termination_reason = "bear_conceded"
            break
        elif is_final:
            blackboard.termination_reason = "max_rounds"
            break

    # 6. 裁判总结
    blackboard.status = "judging"
    yield sse("debate_end", {
        "reason": blackboard.termination_reason,
        "rounds_completed": blackboard.round,
    })

    judge_verdict = await judge_summarize(blackboard, llm, memory)
    blackboard.status = "completed"
    yield sse("judge_verdict", judge_verdict.model_dump(mode="json"))

    # 7. 持久化
    await persist_debate(blackboard, judge_verdict)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_debate_core.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add engine/agent/debate.py tests/agent/test_debate_core.py
git commit -m "feat: 新增 debate.py — 辩论核心逻辑（speak/judge_summarize/run_debate）"
```

---

## Chunk 4: Orchestrator 接入 + MCP Tools

### Task 5: Orchestrator 接入 Phase 4

**Files:**
- Modify: `engine/agent/orchestrator.py`

- [ ] **Step 1: 在 orchestrator.py 顶部导入区追加 debate 相关导入**

在 `engine/agent/orchestrator.py` 的 import 区追加：

```python
from datetime import datetime
from zoneinfo import ZoneInfo
from .debate import run_debate
from .schemas import Blackboard
```

- [ ] **Step 2: 在 analyze() 末尾 yield result 事件之后接入 Phase 4**

找到 `orchestrator.py` 中 `yield {"event": "result", "data": {"report": report.model_dump(mode="json")}}` 这一行，在其之后追加：

```python
        # Phase 4: 专家辩论
        debate_id = f"{target}_{datetime.now(tz=ZoneInfo('Asia/Shanghai')).strftime('%Y%m%d%H%M%S')}"
        blackboard = Blackboard(
            target=target,
            debate_id=debate_id,
            facts=data_map,
            worker_verdicts=verdicts,
            conflicts=report.conflicts,
            max_rounds=request.user_context.get("max_rounds", 3) if request.user_context else 3,
        )
        async for debate_event in run_debate(blackboard, self._llm, self._memory, self._data):
            yield debate_event
```

- [ ] **Step 3: 快速导入验证**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine
python -c "from agent.orchestrator import Orchestrator; print('orchestrator OK')"
```

Expected: `orchestrator OK`

- [ ] **Step 4: 提交**

```bash
git add engine/agent/orchestrator.py
git commit -m "feat: Orchestrator 接入 Phase 4 专家辩论"
```

---

### Task 6: 新增 4 个 MCP Debate Tools

**Files:**
- Modify: `engine/mcpserver/tools.py`
- Modify: `engine/mcpserver/server.py`

- [ ] **Step 1: 在 tools.py 末尾追加 4 个辩论工具函数**

在 `engine/mcpserver/tools.py` 末尾追加：

```python
# ═══════════════════════════════════════════════════════
# Debate Tools — 专家辩论系统
# ═══════════════════════════════════════════════════════

def start_debate(da: DataAccess, code: str, max_rounds: int = 3) -> str:
    """发起专家辩论（通过现有 /api/v1/analysis SSE 端点触发 Orchestrator）

    debate_id 由后端 Orchestrator 在 Phase 4 生成，格式为 "{code}_{YYYYMMDDHHMMSS}"。
    辩论为异步执行，使用 get_debate_status / get_debate_transcript / get_judge_verdict 查询进度。
    """
    if da.is_online():
        result = da.api_post(
            "/api/v1/analysis",
            params={
                "target": code,
                "trigger_type": "user",
                "depth": "deep",
                "max_rounds": max_rounds,
            },
        )
        if result and "_error" not in result:
            return (
                f"辩论已排队启动\n"
                f"- 标的: {code}\n"
                f"- 最大轮数: {max_rounds}\n\n"
                f"辩论在 Orchestrator 完成 Phase 1-3 后自动进入 Phase 4。\n"
                f"debate_id 将出现在分析流的 `debate_start` SSE 事件中，格式为 \"{code}_YYYYMMDDHHMMSS\"。\n"
                f"获得 debate_id 后，使用 get_debate_transcript / get_judge_verdict 查询结果。"
            )
        if result and result.get("_error") == "BUSY":
            return f"计算正在进行中，请稍后重试。"
    return f"后端未连接，无法启动辩论。请先启动后端: `cd engine && python main.py`"


def get_debate_status(da: DataAccess, debate_id: str) -> str:
    """查询辩论进度（从 DuckDB shared.debate_records 读取）"""
    try:
        df = da.db_query(
            "SELECT * FROM shared.debate_records WHERE id = ?",
            [debate_id],
        )
        if df.empty:
            return f"未找到辩论记录: {debate_id}（辩论可能尚未完成或不存在）"
        row = df.iloc[0]
        import json
        bb = json.loads(row["blackboard_json"])
        status = bb.get("status", "unknown")
        round_cur = bb.get("round", 0)
        max_rounds = bb.get("max_rounds", 3)
        bull_c = "已认输" if bb.get("bull_conceded") else "坚持中"
        bear_c = "已认输" if bb.get("bear_conceded") else "坚持中"
        return (
            f"## 辩论状态: {debate_id}\n\n"
            f"- 状态: **{status}**\n"
            f"- 当前轮次: {round_cur}/{max_rounds}\n"
            f"- 终止原因: {row.get('termination_reason', '进行中')}\n"
            f"- 多头专家: {bull_c}\n"
            f"- 空头专家: {bear_c}\n"
        )
    except Exception as e:
        return f"查询辩论状态失败: {e}"


def get_debate_transcript(
    da: DataAccess,
    debate_id: str,
    round: int | None = None,
    role: str | None = None,
) -> str:
    """获取辩论记录（从 DuckDB shared.debate_records 读取，可按轮次和角色过滤）"""
    try:
        df = da.db_query(
            "SELECT blackboard_json FROM shared.debate_records WHERE id = ?",
            [debate_id],
        )
        if df.empty:
            return f"未找到辩论记录: {debate_id}"
        import json
        bb = json.loads(df.iloc[0]["blackboard_json"])
        entries = bb.get("transcript", [])
        if round is not None:
            entries = [e for e in entries if e.get("round") == round]
        if role is not None:
            entries = [e for e in entries if e.get("role") == role]
        if not entries:
            return f"暂无辩论记录（debate_id={debate_id}，round={round}，role={role}）"
        lines = [f"## 辩论记录: {debate_id}\n"]
        for e in entries:
            if not e.get("speak", True) and e.get("role") in ("retail_investor", "smart_money"):
                continue  # 沉默的观察员跳过
            stance_str = f" [{e.get('stance', '')}]" if e.get("stance") else ""
            lines.append(f"\n**Round {e.get('round')} - {e.get('role')}{stance_str}**")
            lines.append(e.get("argument", "（沉默）"))
            if e.get("challenges"):
                lines.append("质疑: " + "；".join(e["challenges"]))
        return "\n".join(lines)
    except Exception as e:
        return f"获取辩论记录失败: {e}"


def get_judge_verdict(da: DataAccess, debate_id: str) -> str:
    """获取裁判最终总结（从 DuckDB shared.debate_records 读取，辩论 completed 后可用）"""
    try:
        df = da.db_query(
            "SELECT judge_verdict_json FROM shared.debate_records WHERE id = ?",
            [debate_id],
        )
        if df.empty:
            return f"未找到辩论记录: {debate_id}（辩论可能尚未完成）"
        import json
        result = json.loads(df.iloc[0]["judge_verdict_json"])
        signal = result.get("signal") or "（待定）"
        score = result.get("score")
        score_str = f"{score:+.2f}" if score is not None else "（待定）"
        quality_map = {
            "consensus": "达成共识",
            "strong_disagreement": "强烈分歧",
            "one_sided": "一边倒",
        }
        quality = quality_map.get(result.get("debate_quality", ""), result.get("debate_quality", ""))
        lines = [
            f"## 裁判总结: {debate_id}\n",
            f"**最终信号**: {signal} | **评分**: {score_str} | **辩论质量**: {quality}",
            f"\n### 核心观点",
            f"- 多头: {result.get('bull_core_thesis', '')}",
            f"- 空头: {result.get('bear_core_thesis', '')}",
            f"\n### 完整总结",
            result.get("summary", ""),
            f"\n### 散户情绪",
            result.get("retail_sentiment_note", ""),
            f"\n### 主力动向",
            result.get("smart_money_note", ""),
            f"\n### 风险提示",
        ]
        for w in result.get("risk_warnings", []):
            lines.append(f"- {w}")
        return "\n".join(lines)
    except Exception as e:
        return f"获取裁判总结失败: {e}"
```

- [ ] **Step 2: 在 server.py 注册 4 个新工具**

在 `engine/mcpserver/server.py` 中找到现有 tool 注册区，追加以下注册代码（参考现有工具的注册模式）：

```python
@server.tool()
def start_debate_tool(code: str, max_rounds: int = 3) -> str:
    """发起专家辩论。多头专家、空头专家、散户代表、主力代表围绕 Blackboard 辩论，最终由裁判汇总。"""
    da = DataAccess()
    return tools.start_debate(da, code=code, max_rounds=max_rounds)


@server.tool()
def get_debate_status_tool(debate_id: str) -> str:
    """查询辩论进度（当前轮次、各方是否认输、辩论状态）。"""
    da = DataAccess()
    return tools.get_debate_status(da, debate_id=debate_id)


@server.tool()
def get_debate_transcript_tool(
    debate_id: str,
    round: int | None = None,
    role: str | None = None,
) -> str:
    """获取辩论完整记录。可按轮次（round）和角色（role）过滤。"""
    da = DataAccess()
    return tools.get_debate_transcript(da, debate_id=debate_id, round=round, role=role)


@server.tool()
def get_judge_verdict_tool(debate_id: str) -> str:
    """获取裁判最终总结（辩论完成后可用）。包含综合分析、信号判断、风险提示。"""
    da = DataAccess()
    return tools.get_judge_verdict(da, debate_id=debate_id)
```

- [ ] **Step 3: 验证 MCP server 可导入**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine
python -c "from mcpserver.server import server; print(f'MCP server OK, tools registered')"
```

Expected: `MCP server OK, tools registered`

- [ ] **Step 4: 提交**

```bash
git add engine/mcpserver/tools.py engine/mcpserver/server.py
git commit -m "feat: MCP 新增 4 个 debate tools (start/status/transcript/verdict)"
```

---

## Chunk 5: 集成验证

### Task 7: 端到端冒烟测试

**Files:**
- Test: `tests/agent/test_debate_smoke.py`

- [ ] **Step 1: 写集成冒烟测试**

```python
# tests/agent/test_debate_smoke.py
"""
辩论系统集成冒烟测试
使用 mock LLM 验证完整辩论流程不崩溃，事件流正确。
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

from engine.agent.schemas import Blackboard, AgentVerdict, Evidence
from engine.agent.debate import run_debate
from engine.agent.memory import AgentMemory
from engine.agent.data_fetcher import DataFetcher


def make_verdict(role, signal="bullish", score=0.5):
    return AgentVerdict(
        agent_role=role, signal=signal, score=score,
        confidence=0.7, evidence=[], risk_flags=[]
    )


BULL_RESPONSE = '''{
  "stance": "insist",
  "argument": "估值合理，基本面稳健，看多理由充分",
  "challenges": ["空头的利率论据被历史数据否定"],
  "confidence": 0.8,
  "data_requests": []
}'''

BEAR_RESPONSE = '''{
  "stance": "insist",
  "argument": "宏观压力明显，下行风险被低估",
  "challenges": ["多头忽略了流动性风险"],
  "confidence": 0.75,
  "data_requests": []
}'''

OBSERVER_SILENT = '{"speak": false, "argument": "", "retail_sentiment_score": 0.0, "data_requests": []}'

JUDGE_RESPONSE = '''{
  "summary": "多空双方均有合理论据，综合来看偏中性。",
  "signal": "neutral",
  "score": 0.05,
  "key_arguments": ["多头：估值合理", "空头：宏观压力"],
  "bull_core_thesis": "估值合理，成长可期",
  "bear_core_thesis": "宏观压力，下行风险",
  "retail_sentiment_note": "散户情绪中性，无明显反向信号",
  "smart_money_note": "资金面数据获取失败，参考价值有限",
  "risk_warnings": ["宏观政策收紧风险", "行业竞争加剧"],
  "debate_quality": "strong_disagreement"
}'''


def make_mock_llm():
    """根据发言顺序循环返回不同响应"""
    responses = [
        BULL_RESPONSE, BEAR_RESPONSE, OBSERVER_SILENT, OBSERVER_SILENT,  # round 1
        BULL_RESPONSE, BEAR_RESPONSE, OBSERVER_SILENT, OBSERVER_SILENT,  # round 2
        BULL_RESPONSE, BEAR_RESPONSE, OBSERVER_SILENT, OBSERVER_SILENT,  # round 3
        JUDGE_RESPONSE,
    ]
    idx = {"i": 0}

    async def mock_chat(messages):
        r = responses[idx["i"] % len(responses)]
        idx["i"] += 1
        return r

    llm = MagicMock()
    llm.chat = mock_chat
    return llm


class TestDebateSmoke:
    def setup_method(self):
        self.blackboard = Blackboard(
            target="600519",
            debate_id="600519_20260314100000",
            worker_verdicts=[
                make_verdict("fundamental", "bullish", 0.4),
                make_verdict("quant", "bearish", -0.3),
            ],
            conflicts=["fundamental vs quant 分歧"],
            max_rounds=3,
        )
        self.llm = make_mock_llm()
        self.memory = MagicMock()
        self.memory.recall = MagicMock(return_value=[])
        self.memory.store = MagicMock()
        self.data_fetcher = MagicMock(spec=DataFetcher)

    def test_run_debate_yields_expected_events(self):
        """验证辩论流程产生正确的事件序列"""
        events = []

        async def collect():
            async for event in run_debate(
                self.blackboard, self.llm, self.memory, self.data_fetcher
            ):
                events.append(event)

        asyncio.run(collect())

        event_types = [e["event"] for e in events]
        assert "debate_start" in event_types
        assert "debate_round_start" in event_types
        assert "debate_entry" in event_types
        assert "debate_end" in event_types
        assert "judge_verdict" in event_types

    def test_debate_start_contains_debate_id(self):
        events = []

        async def collect():
            async for event in run_debate(
                self.blackboard, self.llm, self.memory, self.data_fetcher
            ):
                events.append(event)

        asyncio.run(collect())
        start_event = next(e for e in events if e["event"] == "debate_start")
        assert start_event["data"]["debate_id"] == "600519_20260314100000"

    def test_debate_completes_with_judge_verdict(self):
        events = []

        async def collect():
            async for event in run_debate(
                self.blackboard, self.llm, self.memory, self.data_fetcher
            ):
                events.append(event)

        asyncio.run(collect())
        verdict_event = next(e for e in events if e["event"] == "judge_verdict")
        assert verdict_event["data"]["target"] == "600519"
        assert "summary" in verdict_event["data"]

    def test_concede_terminates_early(self):
        """空头认输时辩论在 round 1 结束"""
        bear_concede = '''{
          "stance": "concede",
          "argument": "多头论据确实压倒性，我认输",
          "challenges": [],
          "confidence": 0.1,
          "data_requests": []
        }'''
        responses = [BULL_RESPONSE, bear_concede, OBSERVER_SILENT, OBSERVER_SILENT, JUDGE_RESPONSE]
        idx = {"i": 0}

        async def mock_chat(messages):
            r = responses[idx["i"] % len(responses)]
            idx["i"] += 1
            return r

        self.llm.chat = mock_chat
        events = []

        async def collect():
            async for event in run_debate(
                self.blackboard, self.llm, self.memory, self.data_fetcher
            ):
                events.append(event)

        asyncio.run(collect())
        end_event = next(e for e in events if e["event"] == "debate_end")
        assert end_event["data"]["reason"] == "bear_conceded"
        assert end_event["data"]["rounds_completed"] == 1
```

- [ ] **Step 2: 运行冒烟测试**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/test_debate_smoke.py -v
```

Expected: 全部 `PASSED`

- [ ] **Step 3: 运行全部 debate 相关测试**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/agent/ -v -k "debate"
```

Expected: 全部通过，无 FAILED

- [ ] **Step 4: 提交**

```bash
git add tests/agent/test_debate_smoke.py
git commit -m "test: 辩论系统集成冒烟测试"
```

---

### Task 8: 最终验证和清理

- [ ] **Step 1: 运行全量测试，确认没有回归**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
python -m pytest tests/ -v 2>&1 | tail -20
```

Expected: 所有既有测试仍然通过，新增测试通过

- [ ] **Step 2: 验证完整 import 链路**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude/engine
python -c "
from agent.schemas import Blackboard, DebateEntry, DataRequest, JudgeVerdict
from agent.personas import build_debate_system_prompt, JUDGE_SYSTEM_PROMPT
from agent.debate import run_debate, speak, validate_data_requests
from agent.data_fetcher import DataFetcher
from agent.orchestrator import Orchestrator
from mcpserver.server import server
print('全部 import 通过')
"
```

Expected: `全部 import 通过`

- [ ] **Step 3: 最终提交**

```bash
git add -A
git commit -m "feat: 专家辩论系统 Phase 1 完成

- Blackboard 模式多角色辩论（多头/空头/散户/主力/裁判）
- 结构化认输机制，可配置最大轮数（默认 3）
- 辩论途中允许专家下发数据补充请求
- SSE 实时推送辩论进度和裁判总结
- MCP 4 个 debate tools
- ChromaDB 5 个辩论角色记忆 collection
- DuckDB shared.debate_records 持久化"
```
