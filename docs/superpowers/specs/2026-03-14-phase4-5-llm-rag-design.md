# Phase 4+5 LLM 基础设施 + RAG 增强 — 架构设计 Spec

> **定位：** StockTerrain 多引擎架构 Phase 4（后端部分）+ Phase 5，统一 LLM 能力接口、共享缓存基础设施、DataFetcher async 路由规范、RAG 历史报告检索。
> **前置依赖：** `2026-03-14-multi-engine-roadmap.md`（四引擎路线图）、`2026-03-14-info-engine-design.md`（InfoEngine 已完成）
> **与辩论系统的关系：** 本 spec 的 `LLMCapability` 和 `DataFetcher.fetch_by_request()` 为 `2026-03-14-expert-debate-system-design.md` 提供基础设施；建议辩论系统实现时用 `LLMCapability` 替换直接持有 `BaseLLMProvider`。
> **不在本次范围：** 前端对话面板改造、MCP 跨引擎组合工具（预留接口）

---

## 1. 目标

1. **`LLMCapability` 统一接口**：各引擎通过语义化方法（`complete`/`classify`/`extract`）调 LLM，不直接操作 `BaseLLMProvider`，内置共享 `llm_cache` 避免重复调用
2. **DataEngine 扩展**：新增 `llm_cache`（KV 缓存）+ `chat_history`（对话历史）两张 DuckDB 表
3. **InfoEngine 重构**：`SentimentAnalyzer` 和 `EventAssessor` 改用 `LLMCapability.classify()` / `LLMCapability.extract()`
4. **Agent 层适配**：`Orchestrator` 改用 `LLMCapability`，统一 `DataFetcher.fetch_by_request()` async 路由
5. **RAG 模块**：独立 `engine/rag/` 模块，ChromaDB 存储完整分析报告，检索后注入 Orchestrator context

**交付标准：** 调用 `LLMCapability.classify()` 分析情感时，相同输入第二次直接命中 `llm_cache`，不再发起 LLM 请求；`Orchestrator` 分析时能检索历史报告并注入 context；所有现有测试继续通过。

---

## 2. 分层架构

```
engine/llm/
├── config.py          ← 不变
├── providers.py       ← 不变
└── capability.py      ← 新增：LLMCapability 统一接口

engine/data_engine/
└── store.py           ← 扩展：新增 llm_cache + chat_history 表

engine/info_engine/
├── sentiment.py       ← 重构：改用 LLMCapability.classify()
└── event_assessor.py  ← 重构：改用 LLMCapability.extract()

engine/agent/
├── data_fetcher.py    ← 扩展：新增 fetch_by_request()
└── orchestrator.py    ← 重构：改用 LLMCapability，接入 RAG

engine/rag/
├── __init__.py        ← get_rag_store() 单例
├── store.py           ← RAGStore：ChromaDB 存储 + 检索
└── schemas.py         ← ReportRecord

engine/config.py       ← 扩展：新增 RAGConfig
```

### 设计原则

- **LLMCapability 是可选的**：无 API Key 时 `enabled=False`，所有调用静默降级（规则/空结果），不抛异常
- **缓存透明**：调用方不感知缓存，`LLMCapability` 内部自动 hash → 查 `llm_cache` → miss 才调 LLM
- **RAG 独立**：`AgentMemory`（短期推理记忆，ChromaDB）与 `RAGStore`（长期报告知识库，ChromaDB）完全隔离，不共享 client
- **DataFetcher 统一桥接**：async 方法直接 await，sync 方法用 `asyncio.to_thread()` 包装，路由表集中管理

---

## 3. LLMCapability 统一接口

### 3.1 接口定义

```python
# engine/llm/capability.py

import hashlib
import json
from typing import Any

from loguru import logger
from .providers import BaseLLMProvider, ChatMessage


class LLMCapability:
    """引擎可选的 LLM 能力 — 统一语义化接口，内置 llm_cache

    用法：
        cap = LLMCapability(provider=llm_provider, cache_store=data_engine.store)
        result = await cap.classify("这只股票大涨", ["positive", "negative", "neutral"])
    """

    def __init__(self, provider: BaseLLMProvider | None = None, cache_store=None):
        self._provider = provider        # None = 未配置，功能降级
        self._cache = cache_store        # DuckDBStore | None

    @property
    def enabled(self) -> bool:
        return self._provider is not None

    async def complete(self, prompt: str, system: str = "", cache_key: str | None = None) -> str:
        """无状态文本补全（带可选缓存）
        - cache_key 为 None 时自动用 prompt 内容的 hash 作为 key
        - 未配置 LLM 时返回空字符串
        """

    async def classify(
        self,
        text: str,
        categories: list[str],
        system: str = "",
        extra_schema: dict | None = None,
    ) -> dict:
        """分类任务，返回 {"label": <category>, "score": float, "reason": str}
        - 要求 LLM 输出 JSON，解析失败时返回 {"label": categories[0], "score": 0.0, "reason": "parse_error"}
        - 未配置 LLM 时返回 {"label": categories[0], "score": 0.0, "reason": "llm_disabled"}
        - 自动缓存（key = hash(text + str(categories))）
        """

    async def extract(
        self,
        text: str,
        schema: dict,
        system: str = "",
    ) -> dict:
        """结构化提取，schema 描述期望的 JSON 结构
        - 返回符合 schema 的 dict，解析失败时返回 {}
        - 未配置 LLM 时返回 {}
        - 自动缓存（key = hash(text + str(schema))）
        """

    def _cache_key(self, *parts: str) -> str:
        """生成缓存 key（SHA256 前 16 位）"""
        raw = "||".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def _get_cache(self, key: str) -> str | None:
        """从 llm_cache 查找缓存，返回 result_json 或 None"""

    async def _set_cache(self, key: str, prompt_hash: str, result_json: str) -> None:
        """写入 llm_cache，失败时只记录 warning 不抛出"""
```

### 3.2 缓存策略

- `complete()`：`cache_key` 显式传入时用传入值；否则用 `hash(prompt)`
- `classify()`：`hash(text + str(categories))` 永久缓存（相同文本+类别必然相同结果）
- `extract()`：`hash(text + str(schema))` 永久缓存
- 缓存写入失败（DuckDB 不可用）：只打 warning，不影响正常流程

### 3.3 与现有 LLM 模块的关系

```
LLMConfig (config.py)          ← 不变，全局配置单例
BaseLLMProvider (providers.py) ← 不变，底层 HTTP 调用
LLMCapability (capability.py)  ← 新增，wrap BaseLLMProvider
                                  各引擎持有 LLMCapability 而不是 BaseLLMProvider
```

`LLMProviderFactory` 不变，`get_info_engine()` / `Orchestrator` 的工厂函数在创建时：
```python
provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None
capability = LLMCapability(provider=provider, cache_store=data_engine.store)
```

---

## 4. DataEngine DuckDB 扩展

### 4.1 新增两张表

```sql
-- 各引擎共享的 LLM 调用结果缓存
CREATE TABLE IF NOT EXISTS shared.llm_cache (
    cache_key    VARCHAR PRIMARY KEY,   -- hash(prompt)，16 字符
    prompt_hash  VARCHAR NOT NULL,      -- hash(完整 prompt)，用于 debug
    result_json  TEXT NOT NULL,         -- LLM 返回的 JSON 字符串
    model        VARCHAR,               -- 调用时使用的模型名
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 对话历史（供后续前端对话面板使用）
CREATE TABLE IF NOT EXISTS shared.chat_history (
    id           INTEGER PRIMARY KEY,
    session_id   VARCHAR NOT NULL,      -- 会话 ID（前端生成 UUID）
    role         VARCHAR NOT NULL,      -- "user" | "assistant" | "system"
    content      TEXT NOT NULL,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_chat_history_session ON shared.chat_history(session_id, created_at);
```

### 4.2 shared schema 初始化

`shared` schema 在 `store._init_tables()` 中随其他表一起创建：
```sql
CREATE SCHEMA IF NOT EXISTS shared;
```

（`info` schema 已在 Phase 3 创建，`shared` 是新增 schema）

### 4.3 DuckDBStore 新增方法

```python
# engine/data_engine/store.py 新增

def get_llm_cache(self, cache_key: str) -> str | None:
    """查询 llm_cache，返回 result_json 或 None"""

def set_llm_cache(self, cache_key: str, prompt_hash: str, result_json: str, model: str = "") -> None:
    """写入 llm_cache，INSERT OR REPLACE"""

def append_chat_history(self, session_id: str, role: str, content: str) -> None:
    """追加一条对话历史"""

def get_chat_history(self, session_id: str, limit: int = 50) -> list[dict]:
    """获取指定会话的历史消息，按时间正序"""
```

---

## 5. InfoEngine 重构

### 5.1 SentimentAnalyzer

`SentimentAnalyzer.__init__` 从接受 `llm_provider: BaseLLMProvider | None` 改为接受 `llm_capability: LLMCapability | None`：

```python
class SentimentAnalyzer:
    def __init__(self, llm_capability: LLMCapability | None = None):
        self._llm = llm_capability

    async def analyze(self, title: str, content: str | None = None) -> SentimentResult:
        if self._llm and self._llm.enabled:
            return await self._analyze_llm(title, content)
        return self._analyze_rules(title, content)

    async def _analyze_llm(self, title, content) -> SentimentResult:
        text = f"{title}\n{content or ''}"
        result = await self._llm.classify(
            text=text,
            categories=["positive", "negative", "neutral"],
            system="你是 A 股股票新闻情感分析专家。",
        )
        return SentimentResult(
            sentiment=result["label"],
            score=result["score"],
            reason=result.get("reason"),
        )
```

规则分析 `_analyze_rules` 不变。

### 5.2 EventAssessor

类似重构，改用 `LLMCapability.extract()`：

```python
class EventAssessor:
    def __init__(self, llm_capability: LLMCapability | None = None):
        self._llm = llm_capability

    async def assess(self, code: str, event_desc: str, stock_context: dict | None = None) -> EventImpact:
        if not self._llm or not self._llm.enabled:
            return EventImpact(
                event_desc=event_desc,
                impact="neutral", magnitude="low",
                reasoning="LLM 未配置，无法评估",
                affected_factors=[],
            )
        result = await self._llm.extract(
            text=f"股票代码: {code}\n事件: {event_desc}\n上下文: {json.dumps(stock_context or {}, ensure_ascii=False)}",
            schema={"impact": "positive|negative|neutral", "magnitude": "high|medium|low",
                    "reasoning": "str", "affected_factors": ["str"]},
            system="你是 A 股事件影响评估专家。",
        )
        # 解析 result，构造 EventImpact
```

### 5.3 InfoEngine 单例工厂

`get_info_engine()` 改为注入 `LLMCapability` 而非 `BaseLLMProvider`：

```python
# engine/info_engine/__init__.py
def get_info_engine() -> InfoEngine:
    global _info_engine
    if _info_engine is None:
        from llm.capability import LLMCapability
        from data_engine import get_data_engine
        de = get_data_engine()
        llm_capability = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            if llm_settings.api_key:
                provider = LLMProviderFactory.create(llm_settings)
                llm_capability = LLMCapability(provider=provider, cache_store=de.store)
        except Exception:
            pass
        _info_engine = InfoEngine(data_engine=de, llm_capability=llm_capability)
    return _info_engine
```

`InfoEngine.__init__` 签名从 `llm_provider` 改为 `llm_capability`，对应传给 `SentimentAnalyzer` 和 `EventAssessor`。

---

## 6. Agent 层适配

### 6.1 DataFetcher.fetch_by_request()

辩论系统（`expert-debate-system-design.md`）需要 `DataFetcher.fetch_by_request(DataRequest)`，统一在此定义路由规范：

```python
# engine/agent/data_fetcher.py 新增

ACTION_DISPATCH: dict[str, tuple[str, str, bool]] = {
    # action_name → (engine_getter, method_name, is_async)
    "get_stock_info":           ("data_engine.get_data_engine",   "get_profile",           False),
    "get_daily_history":        ("data_engine.get_data_engine",   "get_daily_history",     False),
    "get_technical_indicators": ("quant_engine.get_quant_engine", "compute_indicators",    False),
    "get_factor_scores":        ("quant_engine.get_quant_engine", "get_factor_scores",     False),
    "get_news":                 ("info_engine.get_info_engine",   "get_news",              True),   # async
    "get_announcements":        ("info_engine.get_info_engine",   "get_announcements",     True),   # async
    "get_cluster_for_stock":    ("cluster_engine.get_cluster_engine", "get_cluster_for_stock", False),
}

async def fetch_by_request(self, req) -> Any:
    """按 DataRequest 路由到对应引擎方法
    - sync 方法用 asyncio.to_thread() 包装
    - async 方法直接 await
    - 失败时抛出异常，由调用方（fulfill_data_requests）处理
    """
    if req.action not in ACTION_DISPATCH:
        raise ValueError(f"不支持的 action: {req.action}")
    module_path, method_name, is_async = ACTION_DISPATCH[req.action]
    # 动态 import 引擎单例，调用对应方法
    engine_getter_module, engine_getter_fn = module_path.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(engine_getter_module)
    engine = getattr(mod, engine_getter_fn)()
    method = getattr(engine, method_name)
    if is_async:
        return await method(**req.params)
    else:
        return await asyncio.to_thread(method, **req.params)
```

### 6.2 Orchestrator 改用 LLMCapability

`Orchestrator.__init__` 从接受 `BaseLLMProvider` 改为接受 `LLMCapability`：

```python
class Orchestrator:
    def __init__(
        self,
        llm_capability: LLMCapability,
        memory: AgentMemory,
        data_fetcher: DataFetcher | None = None,
        rag_store=None,   # RAGStore | None，可选
    ):
        self._llm = llm_capability
        self._memory = memory
        self._data = data_fetcher or DataFetcher()
        self._rag = rag_store
```

`run_agent()` 内部调 `LLMCapability.complete()` 替换直接调 `BaseLLMProvider.chat()`。

RAG 注入点：在 `analyze()` 的并行分析阶段前，检索历史报告注入 `data_map`：

```python
# analyze() 中，data_map 获取后
if self._rag:
    historical = self._rag.search(target, top_k=3)
    data_map["historical_reports"] = historical   # 各 agent persona 的 prompt 模板需引用此字段
```

### 6.3 agent 单例工厂更新

```python
# engine/agent/__init__.py 或 main.py 中的 Orchestrator 初始化

from llm.capability import LLMCapability
from llm.config import llm_settings
from llm.providers import LLMProviderFactory
from data_engine import get_data_engine
from rag import get_rag_store

de = get_data_engine()
provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None
llm_cap = LLMCapability(provider=provider, cache_store=de.store)
orchestrator = Orchestrator(llm_capability=llm_cap, memory=..., rag_store=get_rag_store())
```

---

## 7. RAG 模块

### 7.1 文件结构

```
engine/rag/
├── __init__.py     ← get_rag_store() 单例工厂
├── store.py        ← RAGStore：ChromaDB 存储 + 检索
└── schemas.py      ← ReportRecord
```

与 `engine/agent/memory.py`（AgentMemory）完全独立：
- `AgentMemory`：短期推理记忆，存 verdict 片段（signal/score），按 agent_role 隔离
- `RAGStore`：长期报告知识库，存完整 `JudgeVerdict.summary`，按 stock code 检索

### 7.2 Schemas

```python
# engine/rag/schemas.py

from pydantic import BaseModel
from datetime import datetime

class ReportRecord(BaseModel):
    report_id: str          # debate_id 或普通分析的 "{code}_{timestamp}"
    code: str               # 股票代码
    summary: str            # 完整分析摘要（向量化文本）
    signal: str | None      # "bullish" | "bearish" | "neutral" | None
    score: float | None     # -1.0 ~ 1.0
    report_type: str        # "debate" | "agent_analysis"
    created_at: datetime
```

### 7.3 RAGStore

```python
# engine/rag/store.py

import chromadb
from loguru import logger
from .schemas import ReportRecord


class RAGStore:
    """历史分析报告向量存储与检索

    ChromaDB collection: "analysis_reports"
    存储内容: ReportRecord.summary（全文）
    检索方式: 语义相似度（ChromaDB 内置嵌入）
    """

    COLLECTION_NAME = "analysis_reports"

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(self.COLLECTION_NAME)
        logger.info(f"RAGStore 初始化: {persist_dir}, 已有 {self._collection.count()} 条报告")

    def store(self, record: ReportRecord) -> None:
        """存储分析报告，report_id 相同时更新"""
        metadata = {
            "code": record.code,
            "signal": record.signal or "",
            "score": record.score if record.score is not None else 0.0,
            "report_type": record.report_type,
            "created_at": record.created_at.isoformat(),
        }
        self._collection.upsert(
            documents=[record.summary],
            metadatas=[metadata],
            ids=[record.report_id],
        )

    def search(self, query: str, top_k: int = 3, code_filter: str | None = None) -> list[dict]:
        """语义检索，返回最相关的历史报告
        - query: 通常是股票代码或分析问题
        - code_filter: 可选，只返回特定股票的历史报告
        - 返回 [{"summary": ..., "code": ..., "signal": ..., "created_at": ...}]
        """
        if self._collection.count() == 0:
            return []
        where = {"code": code_filter} if code_filter else None
        results = self._collection.query(
            query_texts=[query],
            n_results=min(top_k, self._collection.count()),
            where=where,
        )
        entries = []
        for i in range(len(results["ids"][0])):
            entries.append({
                "summary": results["documents"][0][i],
                **results["metadatas"][0][i],
            })
        return entries

    def count(self) -> int:
        return self._collection.count()
```

### 7.4 RAGStore 单例工厂

```python
# engine/rag/__init__.py

from .store import RAGStore

_rag_store: RAGStore | None = None

def get_rag_store() -> RAGStore:
    global _rag_store
    if _rag_store is None:
        from config import settings
        _rag_store = RAGStore(persist_dir=settings.rag.persist_dir)
    return _rag_store

__all__ = ["RAGStore", "get_rag_store"]
```

### 7.5 报告写入点

`Orchestrator.analyze()` 在推送 `result` SSE 事件后写入 RAGStore：

```python
# orchestrator.py analyze() 末尾
if self._rag:
    try:
        from rag.schemas import ReportRecord
        from datetime import datetime, timezone
        self._rag.store(ReportRecord(
            report_id=f"{target}_{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}",
            code=target,
            summary=report.summary,
            signal=report.overall_signal,
            score=report.score,
            report_type="agent_analysis",
            created_at=datetime.now(tz=timezone.utc),
        ))
    except Exception as e:
        logger.warning(f"RAG 报告存储失败 [{target}]: {e}")
```

辩论系统的 `persist_debate()` 中同样调用 `get_rag_store().store()`，存储 `JudgeVerdict`（`report_type="debate"`）。

---

## 8. config.py 扩展

```python
# engine/config.py 新增

class RAGConfig(BaseModel):
    """RAG 模块配置"""
    persist_dir: str = str(DATA_DIR / "chromadb_rag")   # 与 AgentMemory 的 chromadb 目录隔离
    max_reports: int = 10000                              # 超出时不再写入（防止无限增长，Phase 5 优化）
    search_top_k: int = 3                                 # Orchestrator 检索时的默认 top_k

class AppConfig(BaseModel):
    # ... 现有字段 ...
    rag: RAGConfig = RAGConfig()
```

---

## 9. MCP 预留接口

本次不实现跨引擎组合工具，但在 `engine/mcpserver/tools.py` 预留：

```python
# engine/mcpserver/tools.py
# TODO Phase 4: full_analysis 组合工具
# def full_analysis(da: DataAccess, code: str) -> str:
#     """并行调用三引擎，返回结构化 Markdown 报告（不调 LLM，推理留给 MCP 调用方）"""
#     pass
```

---

## 10. 与辩论系统的接口契约

辩论系统实现时，以下接口由本 spec 提供：

| 本 spec 提供 | 辩论系统使用方式 |
|-------------|----------------|
| `LLMCapability.complete(prompt, system)` | `speak()` 中调用（替换 `llm.chat(messages)`）|
| `DataFetcher.fetch_by_request(DataRequest)` | `fulfill_data_requests()` 内部调用 |
| `ACTION_DISPATCH` 路由表 | 辩论 spec 中的 `DEBATE_DATA_WHITELIST` 直接复用 |
| `get_rag_store().store(record)` | `persist_debate()` 中写入 `JudgeVerdict` |

**注意：** 辩论 spec 的 `speak()` 目前用 `llm.chat(messages)` 直接调用，建议改为：
```python
raw = await capability.complete(
    prompt=build_user_prompt(role, blackboard, memory_ctx, is_final_round),
    system=AGENT_PERSONAS[role]["system_prompt"],
)
```
这样可复用 `llm_cache`——相同辩论局面不会重复调 LLM。

---

## 11. 不在本次范围

- 前端对话面板接入 `chat_history`（Phase 4 前端部分，后续单独 spec）
- MCP 跨引擎组合工具（预留注释，Phase 4 后续实现）
- RAGStore 容量管理（`max_reports` 超出时的淘汰策略，Phase 5 优化）
- `chat_history` REST API（供前端读取对话历史，随前端 spec 一起实现）

---

## 12. 测试策略

- **LLMCapability**：`enabled=False` 时所有方法返回降级值（不报错）；`enabled=True` 时 mock provider 验证 prompt 构造；缓存命中测试（相同 key 第二次不调 provider）
- **DuckDB 新表**：`llm_cache` SET/GET；`chat_history` APPEND/GET 分页
- **InfoEngine 重构**：现有 `test_sentiment.py` / `test_event_assessor.py` 只需更新 mock 对象（`LLMCapability` 替换 `BaseLLMProvider`），行为不变
- **DataFetcher.fetch_by_request()**：mock 各引擎单例，验证 sync 用 `to_thread`、async 直接 await
- **RAGStore**：存储后能检索到；相同 `report_id` upsert 不报错；空 collection 检索返回 `[]`
- **Orchestrator 集成**：mock `LLMCapability` + mock `RAGStore`，验证 RAG 检索结果注入 `data_map["historical_reports"]`
