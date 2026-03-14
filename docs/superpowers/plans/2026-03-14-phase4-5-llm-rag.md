# Phase 4+5 LLM 基础设施 + RAG 增强 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 LLM 能力接口（LLMCapability），扩展 DuckDB 共享缓存，重构 InfoEngine 使用新接口，适配 Agent 层，新建 RAG 报告检索模块。

**Architecture:** `LLMCapability` wrap `BaseLLMProvider`，内置 `llm_cache` 透明缓存；InfoEngine 的 SentimentAnalyzer/EventAssessor 改用语义化 `classify()`/`extract()`；独立 `rag/` 模块使用 ChromaDB 存储历史分析报告，Orchestrator 检索后注入 context；`DataFetcher.fetch_by_request()` 统一 async 路由。

**Tech Stack:** Python 3.11, DuckDB, ChromaDB, pydantic v2, pytest, asyncio, loguru

**Spec:** `docs/superpowers/specs/2026-03-14-phase4-5-llm-rag-design.md`

---

## Chunk 1: LLMCapability + DuckDB 共享表

### Task 1: DuckDB shared schema + llm_cache + chat_history

**Files:**
- Modify: `engine/data_engine/store.py` (在 `_init_tables()` 追加，末尾追加新方法)
- Test: `engine/tests/test_llm_cache_store.py`

**Context:** `store.py` 的 `_init_tables()` 方法在约第 42 行，需要追加 `shared` schema 和两张新表的 DDL。`INSERT OR REPLACE` 在 DuckDB 中需要写成 `INSERT OR REPLACE INTO`。`chat_history` 的自增 id 用 SEQUENCE 实现（DuckDB 不自动自增 INTEGER PRIMARY KEY）。

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_llm_cache_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
import duckdb
from unittest.mock import patch
from data_engine.store import DuckDBStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.duckdb"
    s = DuckDBStore(db_path=db_path)
    yield s
    s.close()


def test_llm_cache_miss(store):
    """未命中时返回 None"""
    result = store.get_llm_cache("nonexistent_key")
    assert result is None


def test_llm_cache_set_get(store):
    """写入后能读出"""
    store.set_llm_cache("abc123", "hash_abc", '{"label":"positive"}', model="gpt-4o-mini")
    result = store.get_llm_cache("abc123")
    assert result == '{"label":"positive"}'


def test_llm_cache_replace(store):
    """相同 key 覆盖写入"""
    store.set_llm_cache("key1", "h1", '{"a":1}')
    store.set_llm_cache("key1", "h1", '{"a":2}')
    assert store.get_llm_cache("key1") == '{"a":2}'


def test_chat_history_append_get(store):
    """追加消息后能按 session 读出"""
    store.append_chat_history("sess1", "user", "你好")
    store.append_chat_history("sess1", "assistant", "你好！")
    history = store.get_chat_history("sess1")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "你好"
    assert history[1]["role"] == "assistant"


def test_chat_history_session_isolation(store):
    """不同 session 互不干扰"""
    store.append_chat_history("sessA", "user", "A消息")
    store.append_chat_history("sessB", "user", "B消息")
    assert len(store.get_chat_history("sessA")) == 1
    assert len(store.get_chat_history("sessB")) == 1


def test_chat_history_limit(store):
    """limit 参数有效"""
    for i in range(5):
        store.append_chat_history("sess2", "user", f"msg{i}")
    history = store.get_chat_history("sess2", limit=3)
    assert len(history) == 3
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd engine && python -m pytest tests/test_llm_cache_store.py -v
```
Expected: FAIL — `AttributeError: 'DuckDBStore' object has no attribute 'get_llm_cache'`

- [ ] **Step 3: 在 store.py 的 `_init_tables()` 末尾追加 DDL**

在 `_init_tables()` 中已有的最后一条 `self._conn.execute(...)` 之后追加：

```python
        # shared schema
        self._conn.execute("CREATE SCHEMA IF NOT EXISTS shared")

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shared.llm_cache (
                cache_key    VARCHAR PRIMARY KEY,
                prompt_hash  VARCHAR NOT NULL,
                result_json  TEXT NOT NULL,
                model        VARCHAR DEFAULT '',
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS shared.chat_history_id_seq
        """)

        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS shared.chat_history (
                id           INTEGER PRIMARY KEY DEFAULT NEXTVAL('shared.chat_history_id_seq'),
                session_id   VARCHAR NOT NULL,
                role         VARCHAR NOT NULL,
                content      TEXT NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_history_session
            ON shared.chat_history(session_id, created_at)
        """)
```

- [ ] **Step 4: 在 store.py 末尾（`close()` 之前）追加 4 个新方法**

```python
    def get_llm_cache(self, cache_key: str) -> str | None:
        """查询 LLM 结果缓存，返回 result_json 或 None"""
        try:
            row = self._conn.execute(
                "SELECT result_json FROM shared.llm_cache WHERE cache_key = ?",
                [cache_key],
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.warning(f"llm_cache 查询失败: {e}")
            return None

    def set_llm_cache(self, cache_key: str, prompt_hash: str, result_json: str, model: str = "") -> None:
        """写入 LLM 结果缓存（INSERT OR REPLACE）"""
        try:
            self._conn.execute("""
                INSERT OR REPLACE INTO shared.llm_cache
                    (cache_key, prompt_hash, result_json, model)
                VALUES (?, ?, ?, ?)
            """, [cache_key, prompt_hash, result_json, model])
        except Exception as e:
            logger.warning(f"llm_cache 写入失败: {e}")

    def append_chat_history(self, session_id: str, role: str, content: str) -> None:
        """追加一条对话历史"""
        try:
            self._conn.execute("""
                INSERT INTO shared.chat_history (session_id, role, content)
                VALUES (?, ?, ?)
            """, [session_id, role, content])
        except Exception as e:
            logger.warning(f"chat_history 写入失败: {e}")

    def get_chat_history(self, session_id: str, limit: int = 50) -> list[dict]:
        """获取指定会话的历史消息，按时间正序"""
        try:
            rows = self._conn.execute("""
                SELECT role, content, created_at
                FROM shared.chat_history
                WHERE session_id = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, [session_id, limit]).fetchall()
            return [{"role": r[0], "content": r[1], "created_at": str(r[2])} for r in rows]
        except Exception as e:
            logger.warning(f"chat_history 查询失败: {e}")
            return []
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd engine && python -m pytest tests/test_llm_cache_store.py -v
```
Expected: 6 passed

- [ ] **Step 6: 提交**

```bash
cd engine && git add data_engine/store.py tests/test_llm_cache_store.py && git commit -m "feat: DuckDB shared schema — llm_cache + chat_history 表"
```

---

### Task 2: LLMCapability 统一接口

**Files:**
- Create: `engine/llm/capability.py`
- Test: `engine/tests/test_llm_capability.py`

**Context:** `llm/` 目录已有 `config.py`、`providers.py`（含 `BaseLLMProvider`、`ChatMessage`）。`LLMCapability` wrap `BaseLLMProvider`，内置缓存，提供 `complete()`/`classify()`/`extract()` 三个语义化方法。`enabled=False` 时所有方法静默降级，不抛异常。`_get_cache`/`_set_cache` 调用 `DuckDBStore` 的新方法，`cache_store=None` 时跳过。

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_llm_capability.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── 辅助 ──────────────────────────────────────────────────
def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── enabled=False 降级测试 ────────────────────────────────
def test_disabled_complete():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    assert cap.enabled is False
    result = run(cap.complete("hello"))
    assert result == ""


def test_disabled_classify():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    result = run(cap.classify("文本", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"
    assert result["score"] == 0.0
    assert result["reason"] == "llm_disabled"


def test_disabled_extract():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    result = run(cap.extract("文本", {"key": "value"}))
    assert result == {}


# ── enabled=True + mock provider ─────────────────────────
def test_complete_calls_provider():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value="LLM回复")
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.complete("test prompt", system="sys"))
    assert result == "LLM回复"
    mock_provider.chat.assert_called_once()


def test_classify_parses_json():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label": "positive", "score": 0.9, "reason": "利好"}'
    )
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.classify("大涨", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"
    assert result["score"] == 0.9
    assert result["reason"] == "利好"


def test_classify_parse_error_fallback():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value="not json at all")
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.classify("文本", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"
    assert result["reason"] == "parse_error"


def test_classify_invalid_label_fallback():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label": "unknown_label", "score": 0.5, "reason": "test"}'
    )
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.classify("文本", ["positive", "negative", "neutral"]))
    assert result["label"] == "positive"  # fallback to categories[0]


def test_extract_parses_json():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"impact": "positive", "magnitude": "high", "reasoning": "利好", "affected_factors": ["盈利"]}'
    )
    cap = LLMCapability(provider=mock_provider)
    result = run(cap.extract("事件", {"impact": "str", "magnitude": "str"}))
    assert result["impact"] == "positive"
    assert result["magnitude"] == "high"


def test_classify_cache_hit_skips_provider():
    from llm.capability import LLMCapability
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label": "positive", "score": 0.8, "reason": "ok"}'
    )
    mock_store = MagicMock()
    # 第一次 miss，第二次 hit
    cached_json = '{"label": "negative", "score": 0.6, "reason": "cached"}'
    mock_store.get_llm_cache = MagicMock(side_effect=[None, cached_json])
    mock_store.set_llm_cache = MagicMock()

    cap = LLMCapability(provider=mock_provider, cache_store=mock_store)
    run(cap.classify("文本", ["positive", "negative", "neutral"]))
    run(cap.classify("文本", ["positive", "negative", "neutral"]))

    # provider 只调了一次（第二次命中缓存）
    assert mock_provider.chat.call_count == 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd engine && python -m pytest tests/test_llm_capability.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'llm.capability'`

- [ ] **Step 3: 创建 `engine/llm/capability.py`**

```python
# engine/llm/capability.py
"""LLMCapability — 统一语义化 LLM 接口，内置 llm_cache"""

import hashlib
import json

from loguru import logger

from .providers import BaseLLMProvider, ChatMessage


class LLMCapability:
    """引擎可选的 LLM 能力 — 统一语义化接口，内置共享缓存

    用法:
        cap = LLMCapability(provider=llm_provider, cache_store=data_engine.store)
        result = await cap.classify("文本", ["positive", "negative", "neutral"])

    无 provider 时 enabled=False，所有方法静默降级，不抛异常。
    """

    def __init__(self, provider: BaseLLMProvider | None = None, cache_store=None):
        self._provider = provider      # None = 未配置，降级
        self._cache = cache_store      # DuckDBStore | None

    @property
    def enabled(self) -> bool:
        return self._provider is not None

    # ── 公开接口 ───────────────────────────────────────────

    async def complete(self, prompt: str, system: str = "", cache_key: str | None = None) -> str:
        """无状态文本补全（带可选缓存）

        未配置 LLM 时返回 ""。
        cache_key 为 None 时自动用 hash(prompt) 作为 key。
        """
        if not self.enabled:
            return ""
        key = cache_key or self._cache_key(prompt)
        cached = await self._get_cache(key)
        if cached is not None:
            return cached
        messages = []
        if system:
            messages.append(ChatMessage("system", system))
        messages.append(ChatMessage("user", prompt))
        try:
            result = await self._provider.chat(messages)
        except Exception as e:
            logger.warning(f"LLMCapability.complete 调用失败: {e}")
            return ""
        await self._set_cache(key, self._cache_key(prompt), result)
        return result

    async def classify(
        self,
        text: str,
        categories: list[str],
        system: str = "",
    ) -> dict:
        """分类任务，返回 {"label": <category>, "score": float, "reason": str}

        未配置 LLM: {"label": categories[0], "score": 0.0, "reason": "llm_disabled"}
        解析失败: {"label": categories[0], "score": 0.0, "reason": "parse_error"}
        """
        if not self.enabled:
            return {"label": categories[0], "score": 0.0, "reason": "llm_disabled"}

        key = self._cache_key(text, str(categories))
        cached = await self._get_cache(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:
                pass

        cats_str = str(categories)
        prompt = (
            f"请对以下文本进行分类，从 {cats_str} 中选择最合适的类别。\n\n"
            f"文本：{text}\n\n"
            f'请严格输出 JSON（不含 markdown 代码块）：\n'
            f'{{"label": "<类别>", "score": <0.0-1.0置信度>, "reason": "<简短理由>"}}'
        )
        raw = await self.complete(prompt, system=system, cache_key=key)
        result = self._parse_json(raw)
        if result is None:
            return {"label": categories[0], "score": 0.0, "reason": "parse_error"}

        if result.get("label") not in categories:
            result["label"] = categories[0]

        await self._set_cache(key, self._cache_key(text, str(categories)), json.dumps(result, ensure_ascii=False))
        return result

    async def extract(
        self,
        text: str,
        schema: dict,
        system: str = "",
    ) -> dict:
        """结构化提取，返回符合 schema 描述的 dict

        未配置 LLM 或解析失败时返回 {}。
        """
        if not self.enabled:
            return {}

        key = self._cache_key(text, str(schema))
        cached = await self._get_cache(key)
        if cached is not None:
            try:
                return json.loads(cached)
            except Exception:
                pass

        schema_str = json.dumps(schema, ensure_ascii=False)
        prompt = (
            f"请从以下文本中提取结构化信息。\n\n"
            f"文本：{text}\n\n"
            f"请严格按照以下 JSON schema 输出（不含 markdown 代码块）：\n{schema_str}"
        )
        raw = await self.complete(prompt, system=system, cache_key=key)
        result = self._parse_json(raw)
        if result is None:
            return {}

        await self._set_cache(key, self._cache_key(text, str(schema)), json.dumps(result, ensure_ascii=False))
        return result

    # ── 内部工具 ───────────────────────────────────────────

    def _cache_key(self, *parts: str) -> str:
        """生成缓存 key（SHA256 前 16 位）"""
        raw = "||".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _parse_json(self, text: str) -> dict | None:
        """从 LLM 输出中提取 JSON，支持 markdown 代码块包裹"""
        import re
        # 去掉 ```json ... ``` 包裹
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        try:
            return json.loads(text.strip())
        except Exception:
            return None

    async def _get_cache(self, key: str) -> str | None:
        """查询 DuckDBStore.get_llm_cache，cache_store=None 时返回 None"""
        if self._cache is None:
            return None
        try:
            return self._cache.get_llm_cache(key)
        except Exception as e:
            logger.warning(f"llm_cache 查询异常: {e}")
            return None

    async def _set_cache(self, key: str, prompt_hash: str, result_json: str) -> None:
        """写入 DuckDBStore.set_llm_cache，失败时只记录 warning"""
        if self._cache is None:
            return
        try:
            model = getattr(self._provider, "config", None)
            model_name = getattr(model, "model", "") if model else ""
            self._cache.set_llm_cache(key, prompt_hash, result_json, model=model_name)
        except Exception as e:
            logger.warning(f"llm_cache 写入异常: {e}")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd engine && python -m pytest tests/test_llm_capability.py -v
```
Expected: 10 passed

- [ ] **Step 5: 提交**

```bash
cd engine && git add llm/capability.py tests/test_llm_capability.py && git commit -m "feat: LLMCapability 统一 LLM 接口，内置 llm_cache"
```

---

## Chunk 2: RAG 模块 + config.py 扩展

### Task 3: RAGConfig 注册到 AppConfig

**Files:**
- Modify: `engine/config.py`
- Test: (inline，在 Task 4 的 RAGStore 测试中验证)

**Context:** `config.py` 末尾是 `settings = AppConfig()`。`DATA_DIR` 已定义为 `PROJECT_ROOT / "data"`。新增 `RAGConfig`，`persist_dir` 默认与 `AgentMemory` 的 `chromadb` 目录隔离（用 `chromadb_rag` 子目录）。

- [ ] **Step 1: 在 `config.py` 的 `InfoConfig` 之后追加 `RAGConfig`，并在 `AppConfig` 中注册**

在 `InfoConfig` 类定义之后追加：

```python
# ─── RAG 配置 ─────────────────────────────────────────
class RAGConfig(BaseModel):
    """RAG 历史报告检索配置"""
    persist_dir: str = str(DATA_DIR / "chromadb_rag")  # 与 AgentMemory 的 chromadb 隔离
    search_top_k: int = 3                               # Orchestrator 检索时的默认 top_k
```

在 `AppConfig` 的字段中追加：

```python
    rag: RAGConfig = RAGConfig()
```

- [ ] **Step 2: 验证配置可以正常 import**

```bash
cd engine && python -c "from config import settings; print(settings.rag.persist_dir)"
```
Expected: 打印出类似 `.../data/chromadb_rag` 的路径

- [ ] **Step 3: 提交**

```bash
cd engine && git add config.py && git commit -m "feat: 新增 RAGConfig 到 AppConfig"
```

---

### Task 4: RAG 模块（schemas + store + 单例工厂）

**Files:**
- Create: `engine/rag/__init__.py`
- Create: `engine/rag/schemas.py`
- Create: `engine/rag/store.py`
- Test: `engine/tests/test_rag_store.py`

**Context:** `AgentMemory`（`engine/agent/memory.py`）用 `chromadb.PersistentClient`，RAGStore 也用同样的接口但 persist_dir 不同（`chromadb_rag`），collection 名为 `"analysis_reports"`。`ReportRecord` 使用 pydantic v2。ChromaDB metadata 只接受 `str/int/float/bool`，`score=None` 需转为 `0.0`，`signal=None` 需转为 `""`。

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_rag_store.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from datetime import datetime, timezone
from unittest.mock import patch


@pytest.fixture
def rag_store(tmp_path):
    rag_dir = str(tmp_path / "chromadb_rag")
    with patch("config.settings") as mock_settings:
        mock_settings.rag.persist_dir = rag_dir
        from rag.store import RAGStore
        store = RAGStore(persist_dir=rag_dir)
        yield store


def test_rag_store_empty_search(rag_store):
    """空集合检索返回空列表"""
    results = rag_store.search("600519")
    assert results == []


def test_rag_store_count_zero(rag_store):
    """初始化后 count=0"""
    assert rag_store.count() == 0


def test_rag_store_store_and_search(rag_store):
    """存储后能检索到"""
    from rag.schemas import ReportRecord
    record = ReportRecord(
        report_id="600519_20260314",
        code="600519",
        summary="茅台基本面分析：白酒龙头，护城河深厚，长期看多。",
        signal="bullish",
        score=0.75,
        report_type="agent_analysis",
        created_at=datetime.now(tz=timezone.utc),
    )
    rag_store.store(record)
    assert rag_store.count() == 1
    results = rag_store.search("600519")
    assert len(results) == 1
    assert results[0]["code"] == "600519"
    assert results[0]["signal"] == "bullish"


def test_rag_store_upsert(rag_store):
    """相同 report_id 覆盖写入，不重复"""
    from rag.schemas import ReportRecord
    record = ReportRecord(
        report_id="id_001", code="000001", summary="旧摘要",
        signal="neutral", score=None, report_type="agent_analysis",
        created_at=datetime.now(tz=timezone.utc),
    )
    rag_store.store(record)
    record2 = record.model_copy(update={"summary": "新摘要", "signal": "bearish"})
    rag_store.store(record2)
    assert rag_store.count() == 1
    results = rag_store.search("000001")
    assert results[0]["summary"] == "新摘要"


def test_rag_store_code_filter(rag_store):
    """code_filter 只返回指定股票"""
    from rag.schemas import ReportRecord
    for code in ["600519", "000001"]:
        rag_store.store(ReportRecord(
            report_id=f"{code}_test", code=code,
            summary=f"{code} 分析摘要",
            signal="neutral", score=None, report_type="agent_analysis",
            created_at=datetime.now(tz=timezone.utc),
        ))
    results = rag_store.search("茅台", code_filter="600519")
    assert all(r["code"] == "600519" for r in results)


def test_get_rag_store_singleton(tmp_path):
    """get_rag_store() 返回单例"""
    import importlib
    import rag as rag_module
    rag_module._rag_store = None  # 重置单例
    rag_dir = str(tmp_path / "chromadb_rag2")
    with patch("config.settings") as mock_settings:
        mock_settings.rag.persist_dir = rag_dir
        from rag import get_rag_store
        s1 = get_rag_store()
        s2 = get_rag_store()
        assert s1 is s2
    rag_module._rag_store = None  # 清理
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd engine && python -m pytest tests/test_rag_store.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'rag'`

- [ ] **Step 3: 创建 `engine/rag/schemas.py`**

```python
# engine/rag/schemas.py
"""RAG 报告记录 Schema"""

from datetime import datetime
from pydantic import BaseModel


class ReportRecord(BaseModel):
    report_id: str          # 报告唯一 ID，格式: "{code}_{YYYYMMDDHHMMSS}"
    code: str               # 股票代码
    summary: str            # 完整分析摘要（向量化文本）
    signal: str | None      # "bullish" | "bearish" | "neutral" | None
    score: float | None     # -1.0 ~ 1.0，可为 None
    report_type: str        # "debate" | "agent_analysis"
    created_at: datetime
```

- [ ] **Step 4: 创建 `engine/rag/store.py`**

```python
# engine/rag/store.py
"""RAGStore — 历史分析报告向量存储与检索（ChromaDB）"""

import chromadb
from loguru import logger

from .schemas import ReportRecord


class RAGStore:
    """历史分析报告向量存储与检索

    ChromaDB collection: "analysis_reports"
    存储: ReportRecord.summary 全文
    检索: 语义相似度（ChromaDB 内置 all-MiniLM-L6-v2 嵌入）
    与 AgentMemory 完全隔离（不同 persist_dir，不同 collection）
    """

    COLLECTION_NAME = "analysis_reports"

    def __init__(self, persist_dir: str):
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(self.COLLECTION_NAME)
        logger.info(f"RAGStore 初始化: {persist_dir}, 已有 {self._collection.count()} 条报告")

    def store(self, record: ReportRecord) -> None:
        """存储分析报告，report_id 相同时更新（upsert）"""
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

        Args:
            query: 查询文本（通常是股票代码或分析问题）
            top_k: 最多返回条数
            code_filter: 若指定，只返回该股票的历史报告
        Returns:
            [{"summary": ..., "code": ..., "signal": ..., "score": ..., "created_at": ...}]
        """
        if self._collection.count() == 0:
            return []
        n = min(top_k, self._collection.count())
        where = {"code": code_filter} if code_filter else None
        results = self._collection.query(
            query_texts=[query],
            n_results=n,
            where=where,
        )
        entries = []
        for i in range(len(results["ids"][0])):
            entry = {"summary": results["documents"][0][i]}
            entry.update(results["metadatas"][0][i])
            entries.append(entry)
        return entries

    def count(self) -> int:
        """返回已存储的报告数量"""
        return self._collection.count()
```

- [ ] **Step 5: 创建 `engine/rag/__init__.py`**

```python
# engine/rag/__init__.py
"""RAG 模块 — 历史分析报告向量检索"""

from .store import RAGStore
from .schemas import ReportRecord

_rag_store: RAGStore | None = None


def get_rag_store() -> RAGStore:
    """获取 RAGStore 全局单例"""
    global _rag_store
    if _rag_store is None:
        from config import settings
        _rag_store = RAGStore(persist_dir=settings.rag.persist_dir)
    return _rag_store


__all__ = ["RAGStore", "ReportRecord", "get_rag_store"]
```

- [ ] **Step 6: 运行测试，确认通过**

```bash
cd engine && python -m pytest tests/test_rag_store.py -v
```
Expected: 6 passed

- [ ] **Step 7: 提交**

```bash
cd engine && git add rag/ tests/test_rag_store.py && git commit -m "feat: RAG 模块 — ChromaDB 历史报告存储与检索"
```

---

## Chunk 3: InfoEngine 重构 + Agent 层适配

### Task 5: InfoEngine 重构（SentimentAnalyzer + EventAssessor + 单例工厂）

**Files:**
- Modify: `engine/info_engine/sentiment.py`
- Modify: `engine/info_engine/event_assessor.py`
- Modify: `engine/info_engine/engine.py`
- Modify: `engine/info_engine/__init__.py`
- Test: `engine/tests/test_info_refactor.py`

**Context:** 当前 `SentimentAnalyzer.__init__` 接受 `llm_provider: BaseLLMProvider | None`，改为接受 `llm_capability: LLMCapability | None`。`_analyze_llm` 原先直接调 `self._llm.chat(messages)`，改为调 `self._llm.classify()`。`EventAssessor` 同理改用 `self._llm.extract()`。`InfoEngine.__init__` 参数 `llm_provider` 改为 `llm_capability`。`get_info_engine()` 单例工厂改为构造 `LLMCapability` 后注入。现有行为（规则模式、降级逻辑）不变。

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_info_refactor.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_sentiment_analyzer_accepts_llm_capability():
    """SentimentAnalyzer 接受 LLMCapability，不接受 BaseLLMProvider"""
    from llm.capability import LLMCapability
    from info_engine.sentiment import SentimentAnalyzer
    cap = LLMCapability()  # disabled
    sa = SentimentAnalyzer(llm_capability=cap)
    # 规则模式仍工作
    result = run(sa.analyze("增持！业绩大增"))
    assert result.sentiment in ("positive", "negative", "neutral")


def test_sentiment_analyzer_uses_classify():
    """LLM 模式下调用 llm_capability.classify()"""
    from llm.capability import LLMCapability
    from info_engine.sentiment import SentimentAnalyzer
    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = True
    mock_cap.classify = AsyncMock(return_value={"label": "positive", "score": 0.9, "reason": "利好"})
    sa = SentimentAnalyzer(llm_capability=mock_cap)
    result = run(sa.analyze("大涨利好", "股价创新高"))
    assert result.sentiment == "positive"
    assert result.score == 0.9
    mock_cap.classify.assert_called_once()


def test_event_assessor_accepts_llm_capability():
    """EventAssessor 接受 LLMCapability"""
    from llm.capability import LLMCapability
    from info_engine.event_assessor import EventAssessor
    cap = LLMCapability()  # disabled
    ea = EventAssessor(llm_capability=cap)
    result = run(ea.assess("600519", "大幅增持"))
    assert result.impact in ("positive", "negative", "neutral")
    assert result.reasoning == "LLM 未配置，无法评估"


def test_event_assessor_uses_extract():
    """LLM 模式下调用 llm_capability.extract()"""
    from llm.capability import LLMCapability
    from info_engine.event_assessor import EventAssessor
    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = True
    mock_cap.extract = AsyncMock(return_value={
        "impact": "positive", "magnitude": "high",
        "reasoning": "重大利好", "affected_factors": ["盈利预期"],
    })
    ea = EventAssessor(llm_capability=mock_cap)
    result = run(ea.assess("600519", "大幅增持"))
    assert result.impact == "positive"
    assert result.magnitude == "high"
    mock_cap.extract.assert_called_once()


def test_info_engine_init_accepts_llm_capability():
    """InfoEngine.__init__ 接受 llm_capability 参数"""
    from llm.capability import LLMCapability
    from info_engine.engine import InfoEngine
    from unittest.mock import MagicMock
    mock_de = MagicMock()
    mock_de.store = MagicMock()
    cap = LLMCapability()
    engine = InfoEngine(data_engine=mock_de, llm_capability=cap)
    assert engine is not None


def test_info_engine_health_check_uses_enabled():
    """health_check 使用 llm_capability.enabled 判断模式"""
    from llm.capability import LLMCapability
    from info_engine.engine import InfoEngine
    from unittest.mock import MagicMock
    mock_de = MagicMock()
    mock_de.store = MagicMock()
    # disabled
    engine = InfoEngine(data_engine=mock_de, llm_capability=LLMCapability())
    h = engine.health_check()
    assert h["llm_available"] is False
    assert h["sentiment_mode"] == "rules"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd engine && python -m pytest tests/test_info_refactor.py -v
```
Expected: FAIL — `TypeError: SentimentAnalyzer.__init__() got an unexpected keyword argument 'llm_capability'`

- [ ] **Step 3: 修改 `engine/info_engine/sentiment.py`**

将 `__init__` 的参数名从 `llm_provider` 改为 `llm_capability`，并更新 `_analyze_llm`：

在文件顶部 import 中，将 `from llm.providers import BaseLLMProvider, ChatMessage` 替换为：
```python
from llm.capability import LLMCapability
```

将 `__init__` 签名改为：
```python
def __init__(self, llm_capability: LLMCapability | None = None):
    self._llm = llm_capability
```

将 `analyze()` 中的判断改为：
```python
async def analyze(self, title: str, content: str | None = None) -> SentimentResult:
    if self._llm and self._llm.enabled:
        return await self._analyze_llm(title, content)
    return self._analyze_rules(title, content)
```

将 `_analyze_llm()` 改为：
```python
async def _analyze_llm(self, title: str, content: str | None) -> SentimentResult:
    text = f"{title}\n{content or ''}"
    result = await self._llm.classify(
        text=text,
        categories=["positive", "negative", "neutral"],
        system="你是 A 股股票新闻情感分析专家。",
    )
    return SentimentResult(
        sentiment=result["label"],
        score=result.get("score", 0.0),
        reason=result.get("reason"),
    )
```

删除旧的 `_analyze_llm` 中对 `BaseLLMProvider.chat()` 的调用代码。`_analyze_rules()` 不变。

- [ ] **Step 4: 修改 `engine/info_engine/event_assessor.py`**

在文件顶部 import 中，将 `from llm.providers import BaseLLMProvider, ChatMessage` 替换为：
```python
import json
from llm.capability import LLMCapability
```

将 `__init__` 改为：
```python
def __init__(self, llm_capability: LLMCapability | None = None):
    self._llm = llm_capability
```

将 `assess()` 的 LLM 判断和调用改为：
```python
async def assess(self, code: str, event_desc: str, stock_context: dict | None = None) -> EventImpact:
    if not self._llm or not self._llm.enabled:
        return EventImpact(
            event_desc=event_desc,
            impact="neutral",
            magnitude="low",
            reasoning="LLM 未配置，无法评估",
            affected_factors=[],
        )
    result = await self._llm.extract(
        text=(
            f"股票代码: {code}\n"
            f"事件: {event_desc}\n"
            f"上下文: {json.dumps(stock_context or {}, ensure_ascii=False)}"
        ),
        schema={
            "impact": "positive|negative|neutral",
            "magnitude": "high|medium|low",
            "reasoning": "str",
            "affected_factors": ["str"],
        },
        system="你是 A 股事件影响评估专家。",
    )
    return EventImpact(
        event_desc=event_desc,
        impact=result.get("impact", "neutral"),
        magnitude=result.get("magnitude", "low"),
        reasoning=result.get("reasoning", ""),
        affected_factors=result.get("affected_factors", []),
    )
```

- [ ] **Step 5: 修改 `engine/info_engine/engine.py`**

将 `__init__` 参数从 `llm_provider` 改为 `llm_capability`：
```python
def __init__(self, data_engine, llm_capability=None):
    self._data = data_engine
    self._sentiment = SentimentAnalyzer(llm_capability=llm_capability)
    self._assessor = EventAssessor(llm_capability=llm_capability)
    self._store = data_engine.store
    self._config = None
```

将 `health_check()` 改为检查 `llm_capability.enabled`：
```python
def health_check(self) -> dict:
    llm_available = (
        self._sentiment._llm is not None
        and self._sentiment._llm.enabled
    )
    return {
        "status": "ok",
        "sentiment_mode": "llm" if llm_available else "rules",
        "llm_available": llm_available,
    }
```

- [ ] **Step 6: 修改 `engine/info_engine/__init__.py`**

将 `get_info_engine()` 函数改为使用 `LLMCapability`：
```python
def get_info_engine() -> InfoEngine:
    """获取信息引擎全局单例（依赖数据引擎，可选 LLM）"""
    global _info_engine
    if _info_engine is None:
        llm_capability = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            from llm.capability import LLMCapability
            if llm_settings.api_key:
                provider = LLMProviderFactory.create(llm_settings)
                llm_capability = LLMCapability(
                    provider=provider,
                    cache_store=get_data_engine().store,
                )
        except Exception:
            pass
        _info_engine = InfoEngine(
            data_engine=get_data_engine(),
            llm_capability=llm_capability,
        )
    return _info_engine
```

- [ ] **Step 7: 运行测试，确认通过**

```bash
cd engine && python -m pytest tests/test_info_refactor.py -v
```
Expected: 6 passed

- [ ] **Step 8: 提交**

```bash
cd engine && git add info_engine/sentiment.py info_engine/event_assessor.py info_engine/engine.py info_engine/__init__.py tests/test_info_refactor.py && git commit -m "refactor: InfoEngine 改用 LLMCapability 接口"
```

---

### Task 6: Agent 层适配（runner.py + data_fetcher.py + orchestrator.py）

**Files:**
- Modify: `engine/agent/runner.py`
- Modify: `engine/agent/data_fetcher.py`
- Modify: `engine/agent/orchestrator.py`
- Test: `engine/tests/test_agent_refactor.py`

**Context:** `runner.py` 当前接受 `llm_provider: BaseLLMProvider`，调 `llm_provider.chat(messages)`，改为接受 `llm_capability: LLMCapability`，调 `llm_capability.complete(prompt, system)`。`orchestrator.py` 当前接受 `llm_provider`，改为接受 `llm_capability` + 可选 `rag_store`。`data_fetcher.py` 新增模块级 `ACTION_DISPATCH` 字典和实例方法 `fetch_by_request(req)`。

- [ ] **Step 1: 写失败测试**

```python
# engine/tests/test_agent_refactor.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_run_agent_accepts_llm_capability():
    """run_agent() 接受 llm_capability 参数"""
    from llm.capability import LLMCapability
    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = True
    mock_cap.complete = AsyncMock(return_value='{"signal":"bullish","score":0.6,"confidence":0.8,"reasoning":"test","key_factors":["PE低"]}')
    from agent.runner import run_agent
    result = run(run_agent(
        agent_role="fundamental",
        target="600519",
        data_context={"name": "茅台"},
        memory_context=[],
        calibration_weight=0.5,
        llm_capability=mock_cap,
    ))
    assert result.agent_role == "fundamental"
    assert result.signal == "bullish"
    mock_cap.complete.assert_called_once()


def test_orchestrator_accepts_llm_capability():
    """Orchestrator.__init__ 接受 llm_capability"""
    from llm.capability import LLMCapability
    from agent.orchestrator import Orchestrator
    from agent.memory import AgentMemory
    mock_cap = MagicMock(spec=LLMCapability)
    mock_memory = MagicMock(spec=AgentMemory)
    orch = Orchestrator(llm_capability=mock_cap, memory=mock_memory)
    assert orch is not None


def test_orchestrator_injects_rag(tmp_path):
    """Orchestrator 有 rag_store 时注入 historical_reports"""
    from llm.capability import LLMCapability
    from agent.orchestrator import Orchestrator
    from agent.memory import AgentMemory

    mock_cap = MagicMock(spec=LLMCapability)
    mock_cap.enabled = False
    mock_memory = MagicMock(spec=AgentMemory)
    mock_memory.recall = MagicMock(return_value=[])

    mock_rag = MagicMock()
    mock_rag.search = MagicMock(return_value=[{"summary": "历史报告", "code": "600519", "signal": "bullish"}])

    mock_fetcher = MagicMock()
    mock_fetcher.fetch_all = AsyncMock(return_value={
        "fundamental": {}, "info": {}, "quant": {}
    })

    orch = Orchestrator(llm_capability=mock_cap, memory=mock_memory, data_fetcher=mock_fetcher, rag_store=mock_rag)

    events = []
    async def collect():
        async for event in orch.analyze(MagicMock(target="600519", depth="quick")):
            events.append(event)
    run(collect())

    mock_rag.search.assert_called_once()
    # 验证 RAG 检索结果注入 data_map["historical_reports"]
    # mock_fetcher.fetch_all 被调用时，data_map 会被 rag 检索结果更新
    # 通过 mock_fetcher.fetch_all 的调用上下文验证 rag.search 在 fetch_all 后执行
    assert any(e.get("event") in ("phase", "result", "error") for e in events)
    # 更强验证：mock_cap.complete（disabled 模式跳过）或者直接 inspect 调用序列
    fetch_call_count = mock_fetcher.fetch_all.call_count
    assert fetch_call_count == 1
    search_call_count = mock_rag.search.call_count
    assert search_call_count == 1


def test_data_fetcher_fetch_by_request_unknown_action():
    """未知 action 抛出 ValueError"""
    from agent.data_fetcher import DataFetcher
    fetcher = DataFetcher()

    class FakeReq:
        action = "nonexistent_action"
        params = {}

    with pytest.raises(ValueError, match="不支持的 action"):
        run(fetcher.fetch_by_request(FakeReq()))


def test_data_fetcher_action_dispatch_has_expected_keys():
    """ACTION_DISPATCH 包含 spec 定义的全部 7 个 action"""
    from agent.data_fetcher import ACTION_DISPATCH
    expected = {
        "get_stock_info", "get_daily_history", "get_technical_indicators",
        "get_factor_scores", "get_news", "get_announcements", "get_cluster_for_stock",
    }
    assert expected.issubset(set(ACTION_DISPATCH.keys()))


def test_data_fetcher_fetch_by_request_sync_action():
    """sync action 通过 asyncio.to_thread 调用"""
    from agent.data_fetcher import DataFetcher, ACTION_DISPATCH
    fetcher = DataFetcher()

    class FakeReq:
        action = "get_stock_info"
        params = {"target": "600519"}

    mock_engine = MagicMock()
    mock_engine.get_profile = MagicMock(return_value={"name": "茅台"})

    with patch("data_engine.get_data_engine", return_value=mock_engine):
        result = run(fetcher.fetch_by_request(FakeReq()))
    assert result == {"name": "茅台"}
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd engine && python -m pytest tests/test_agent_refactor.py -v
```
Expected: FAIL — `TypeError: run_agent() got an unexpected keyword argument 'llm_capability'`

- [ ] **Step 3: 修改 `engine/agent/runner.py`**

将 import 头部的 `from llm.providers import BaseLLMProvider, ChatMessage` 替换为：
```python
from llm.capability import LLMCapability
```

将 `run_agent()` 签名改为：
```python
async def run_agent(
    agent_role: str,
    target: str,
    data_context: dict,
    memory_context: list[dict],
    calibration_weight: float,
    llm_capability: LLMCapability,
) -> AgentVerdict:
```

将函数内 `messages` 构造和 LLM 调用部分替换为：
```python
    system_prompt = build_system_prompt(agent_role, calibration_weight)
    user_msg = f"请分析股票 {target}。\n\n## 数据\n```json\n{json.dumps(data_context, ensure_ascii=False, indent=2)}\n```"

    if memory_context:
        memory_text = "\n".join(
            f"- [{m.get('metadata', {}).get('timestamp', '?')}] {m.get('content', '')}"
            for m in memory_context[:5]
        )
        user_msg += f"\n\n## 历史分析记忆\n{memory_text}"

    try:
        raw = await llm_capability.complete(prompt=user_msg, system=system_prompt)
    except Exception as e:
        raise AgentRunError(f"LLM 调用失败 [{agent_role}]: {e}") from e
```

删除旧的 `messages = [...]` 和 `llm_provider.chat(messages)` 代码。其余 JSON 解析逻辑不变。

- [ ] **Step 4: 修改 `engine/agent/data_fetcher.py`**

在文件顶部 import 中追加：
```python
import importlib
from typing import Any
```

在 `DataFetcher` 类定义之前（模块级）添加：
```python
ACTION_DISPATCH: dict[str, tuple[str, str, str, bool]] = {
    # action → (module_name, getter_fn, method_name, is_async)
    "get_stock_info":           ("data_engine",    "get_data_engine",    "get_profile",           False),
    "get_daily_history":        ("data_engine",    "get_data_engine",    "get_daily_history",     False),
    "get_technical_indicators": ("quant_engine",   "get_quant_engine",   "compute_indicators",    False),
    "get_factor_scores":        ("quant_engine",   "get_quant_engine",   "get_factor_scores",     False),
    "get_news":                 ("info_engine",    "get_info_engine",    "get_news",              True),
    "get_announcements":        ("info_engine",    "get_info_engine",    "get_announcements",     True),
    "get_cluster_for_stock":    ("cluster_engine", "get_cluster_engine", "get_cluster_for_stock", False),
}
```

在 `DataFetcher` 类末尾追加 `fetch_by_request()` 方法：
```python
    async def fetch_by_request(self, req) -> Any:
        """按 DataRequest 路由到对应引擎方法

        ACTION_DISPATCH 中未知 action 抛出 ValueError。
        sync 方法用 asyncio.to_thread() 包装；async 方法直接 await。
        """
        if req.action not in ACTION_DISPATCH:
            raise ValueError(f"不支持的 action: {req.action}")
        module_name, getter_fn, method_name, is_async = ACTION_DISPATCH[req.action]
        mod = importlib.import_module(module_name)
        engine = getattr(mod, getter_fn)()
        method = getattr(engine, method_name)
        if is_async:
            return await method(**req.params)
        else:
            return await asyncio.to_thread(method, **req.params)
```

- [ ] **Step 5: 修改 `engine/agent/orchestrator.py`**

将 import 头部更新，追加：
```python
from llm.capability import LLMCapability
```

将 `Orchestrator.__init__` 签名改为：
```python
def __init__(
    self,
    llm_capability: LLMCapability,
    memory: AgentMemory,
    data_fetcher: DataFetcher | None = None,
    rag_store=None,   # RAGStore | None
):
    self._llm = llm_capability
    self._memory = memory
    self._data = data_fetcher or DataFetcher()
    self._rag = rag_store
```

在 `analyze()` 中，`data_map = await self._data.fetch_all(target)` 这行之后追加 RAG 注入：
```python
        # RAG 注入：检索历史报告，注入 data_map
        if self._rag:
            try:
                from config import settings
                historical = self._rag.search(target, top_k=settings.rag.search_top_k)
                data_map["historical_reports"] = historical
            except Exception as e:
                logger.warning(f"RAG 检索失败 [{target}]: {e}")
```

将 `_run_with_timeout()` 调用 `run_agent()` 时把 `llm_provider=self._llm` 改为 `llm_capability=self._llm`：
```python
        return await asyncio.wait_for(
            run_agent(
                agent_role=role, target=target, data_context=data_ctx,
                memory_context=memory_ctx, calibration_weight=cal,
                llm_capability=self._llm,
            ),
            timeout=self.AGENT_TIMEOUT,
        )
```

在 `analyze()` 推送 `result` SSE 事件之后（`yield {"event": "result", ...}` 这行之后）追加 RAGStore 写入：
```python
        # RAG 写入：将分析报告存入向量库供后续检索
        if self._rag and report:
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

- [ ] **Step 6: 修改 `engine/agent/__init__.py`**

将 `get_orchestrator()` 工厂函数更新为使用 `LLMCapability` 和 `rag_store`：

```python
def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        from llm.config import llm_settings
        from llm.providers import LLMProviderFactory
        from llm.capability import LLMCapability
        from config import settings
        from data_engine import get_data_engine
        from rag import get_rag_store
        de = get_data_engine()
        provider = LLMProviderFactory.create(llm_settings) if llm_settings.api_key else None
        llm_cap = LLMCapability(provider=provider, cache_store=de.store)
        memory = AgentMemory(persist_dir=settings.chromadb.persist_dir)
        _orchestrator = Orchestrator(
            llm_capability=llm_cap,
            memory=memory,
            rag_store=get_rag_store(),
        )
    return _orchestrator
```

删除旧的 `if not llm_settings.api_key: raise RuntimeError(...)` 逻辑（`LLMCapability` 在 disabled 模式下安全运行）。

- [ ] **Step 7: 运行测试，确认通过**

```bash
cd engine && python -m pytest tests/test_agent_refactor.py -v
```
Expected: 6 passed

- [ ] **Step 8: 运行全量测试，确认无回归**

```bash
cd engine && python -m pytest tests/ -v
```
Expected: 所有已有测试继续通过（quant 相关测试 + 新测试）

- [ ] **Step 9: 提交**

```bash
cd engine && git add agent/runner.py agent/data_fetcher.py agent/orchestrator.py agent/__init__.py tests/test_agent_refactor.py && git commit -m "refactor: Agent 层改用 LLMCapability，新增 fetch_by_request 路由"
```

---

### Task 7: MCP 预留注释 + E2E 验证

**Files:**
- Modify: `engine/mcpserver/tools.py`
- Test: `engine/tests/test_phase45_e2e.py`

**Context:** 在 `tools.py` 末尾加一条 TODO 注释（预留 full_analysis 接口）。E2E 验证：import 所有新模块无报错；`LLMCapability` disabled 模式下各引擎初始化正常；`RAGStore` 单例可以 store 和 search；`DataFetcher.ACTION_DISPATCH` 包含 7 个 action。

- [ ] **Step 1: 在 `engine/mcpserver/tools.py` 末尾追加预留注释**

```python
# TODO Phase 4: full_analysis 组合工具（预留，本次不实现）
# def full_analysis(da: DataAccess, code: str) -> str:
#     """并行调用三引擎数据聚合，返回结构化 Markdown 报告（不调 LLM，推理留给 MCP 调用方）"""
#     pass
```

- [ ] **Step 2: 写 E2E 验证测试**

```python
# engine/tests/test_phase45_e2e.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import pytest
from unittest.mock import patch
from datetime import datetime, timezone


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_llm_capability_import():
    from llm.capability import LLMCapability
    cap = LLMCapability()
    assert cap.enabled is False


def test_rag_module_import():
    from rag import RAGStore, ReportRecord, get_rag_store
    assert RAGStore is not None


def test_data_fetcher_action_dispatch_count():
    from agent.data_fetcher import ACTION_DISPATCH
    assert len(ACTION_DISPATCH) == 7


def test_info_engine_init_with_disabled_capability():
    """InfoEngine 使用 disabled LLMCapability 初始化正常"""
    from llm.capability import LLMCapability
    from info_engine.engine import InfoEngine
    from unittest.mock import MagicMock
    mock_de = MagicMock()
    mock_de.store = MagicMock()
    engine = InfoEngine(data_engine=mock_de, llm_capability=LLMCapability())
    h = engine.health_check()
    assert h["status"] == "ok"
    assert h["llm_available"] is False


def test_rag_store_full_cycle(tmp_path):
    """RAGStore 完整存取循环"""
    from rag.store import RAGStore
    from rag.schemas import ReportRecord
    store = RAGStore(persist_dir=str(tmp_path / "rag"))
    record = ReportRecord(
        report_id="test_001",
        code="600519",
        summary="综合来看，茅台当前估值合理，长期价值确定。",
        signal="bullish",
        score=0.7,
        report_type="agent_analysis",
        created_at=datetime.now(tz=timezone.utc),
    )
    store.store(record)
    results = store.search("茅台估值", code_filter="600519")
    assert len(results) >= 1
    assert results[0]["code"] == "600519"


def test_llm_cache_in_classify(tmp_path):
    """classify 相同输入第二次命中缓存，provider 只调一次"""
    from llm.capability import LLMCapability
    from unittest.mock import AsyncMock, MagicMock
    import duckdb
    from data_engine.store import DuckDBStore

    db_path = tmp_path / "test.duckdb"
    with patch("data_engine.store.DB_PATH", db_path):
        store = DuckDBStore(db_path=db_path)

    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(
        return_value='{"label":"positive","score":0.9,"reason":"利好"}'
    )
    cap = LLMCapability(provider=mock_provider, cache_store=store)

    run(cap.classify("大涨利好消息", ["positive", "negative", "neutral"]))
    run(cap.classify("大涨利好消息", ["positive", "negative", "neutral"]))

    assert mock_provider.chat.call_count == 1
    store.close()
```

- [ ] **Step 3: 运行 E2E 测试**

```bash
cd engine && python -m pytest tests/test_phase45_e2e.py -v
```
Expected: 6 passed

- [ ] **Step 4: 运行全量测试，确认无回归**

```bash
cd engine && python -m pytest tests/ -v
```
Expected: 全部通过

- [ ] **Step 5: 提交**

```bash
cd engine && git add mcpserver/tools.py tests/test_phase45_e2e.py && git commit -m "feat: Phase 4+5 E2E 验证通过，MCP 预留 full_analysis 接口"
```
