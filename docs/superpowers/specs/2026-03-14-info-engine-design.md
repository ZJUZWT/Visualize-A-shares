# InfoEngine 消息面引擎 — 架构设计 Spec

> **定位：** StockTerrain 多引擎架构 Phase 3，消息面数据采集 + 情感分析 + 事件影响评估
> **前置依赖：** `2026-03-14-multi-engine-roadmap.md`（四引擎路线图）、`2026-03-14-multi-agent-decision-brain-design.md`（Multi-Agent spec）
> **架构模式：** DataEngine 采集原始数据 → InfoEngine 分析推理 → Agent 层消费

---

## 1. 目标

让 Multi-Agent 的消息面 Agent（Info Agent）从 stub 变为真实可用：
- 个股新闻获取 + 情感分析
- 公司公告获取 + 情感分析
- 事件影响评估（LLM 驱动）

**交付标准：** 调用 `DataFetcher.get_info_data("600519")` 返回带情感标注的新闻和公告数据，而非空列表。

## 2. 分层架构

```
DataEngine (数据采集层 — 已有，扩展)
├── sources/akshare_source.py  ← 扩展: 新增 get_stock_news() + get_announcements()
├── collector.py               ← 扩展: 新增 news/announcement 采集方法
└── engine.py                  ← 扩展: 对外暴露 get_news() + get_announcements()

InfoEngine (消息面分析层 — 新建 engine/info_engine/)
├── __init__.py        ← get_info_engine() 单例
├── engine.py          ← 门面类，编排情感分析 + 事件评估
├── sentiment.py       ← 情感分析（LLM 优先，规则退化）
├── event_assessor.py  ← 事件影响评估（LLM 驱动）
├── schemas.py         ← NewsArticle, Announcement, EventImpact
└── routes.py          ← REST API /api/v1/info/*
```

### 设计原则

- **数据源走 DataEngine：** InfoEngine 不直接调 AKShare，通过 DataEngine 获取原始数据
- **存储走 DataEngine：** InfoEngine 分析结果缓存在 DataEngine 的 DuckDB `info.*` schema，InfoEngine 不拥有数据库
- **LLM 可选：** 无 LLM API Key 时退化为规则匹配，功能不中断
- **与 QuantEngine 同构：** 模块结构、单例模式、路由注册方式保持一致

## 3. DataEngine 扩展

### 3.1 AKShareSource 新增方法

```python
# engine/data_engine/sources/akshare_source.py

def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
    """获取个股新闻（东方财富）
    底层接口: ak.stock_news_em(symbol=code)
    返回: title, content, source, publish_time, url
    注意: AKShare API 名称可能随版本变动，实现时需验证当前版本的实际接口名。
    """

def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
    """获取公司公告（东方财富）
    底层接口: ak.stock_notice_report_em(symbol=code)
    返回: title, type, date, url
    注意: 同上，需验证 AKShare 当前版本的实际接口名，失败时返回空 DataFrame。
    """
```

### 3.2 BaseDataSource 新增抽象方法

```python
# 非 @abstractmethod — 可选实现，默认 raise NotImplementedError
def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
    raise NotImplementedError

def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
    raise NotImplementedError
```

### 3.3 DataCollector 新增方法

```python
def get_stock_news(self, code: str, limit: int = 50) -> pd.DataFrame:
    """获取个股新闻 — 逐级降级"""
    # 与 get_daily_history 同模式

def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
    """获取公司公告 — 逐级降级"""
```

### 3.4 DataEngine 对外接口

```python
# engine/data_engine/engine.py 新增
def get_news(self, code: str, limit: int = 50) -> pd.DataFrame:
    return self._collector.get_stock_news(code, limit)

def get_announcements(self, code: str, limit: int = 20) -> pd.DataFrame:
    return self._collector.get_announcements(code, limit)
```

**原始数据不持久化：** 新闻是实时性数据，每次从源拉取。InfoEngine 分析后的结果才写入 DuckDB 缓存。

## 4. InfoEngine 核心

### 4.1 Schemas

```python
class NewsArticle(BaseModel):
    title: str
    content: str | None = None
    source: str                  # "东方财富" 等
    publish_time: str
    url: str | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None
    sentiment_score: float | None = None  # -1.0 ~ 1.0

class Announcement(BaseModel):
    title: str
    type: str                    # "业绩预告", "股份变动" 等
    date: str
    url: str | None = None
    sentiment: Literal["positive", "negative", "neutral"] | None = None

class SentimentResult(BaseModel):
    sentiment: Literal["positive", "negative", "neutral"]
    score: float                 # -1.0 ~ 1.0
    reason: str | None = None   # LLM 模式下有值

class EventImpact(BaseModel):
    event_desc: str
    impact: Literal["positive", "negative", "neutral"]
    magnitude: Literal["high", "medium", "low"]
    reasoning: str               # LLM 推理过程
    affected_factors: list[str]  # 影响的因素
```

### 4.2 情感分析 (sentiment.py)

**Async/Sync 桥接：** `BaseLLMProvider.chat()` 是 async 方法。SentimentAnalyzer 和 EventAssessor 的 LLM 调用方法设计为 async，InfoEngine 门面的 `get_news()` / `get_announcements()` / `assess_event_impact()` 也是 async。REST API 路由层天然 async，DataFetcher 通过 `asyncio.to_thread()` 包装同步采集 + `await` 异步分析。

```python
class SentimentAnalyzer:
    def __init__(self, llm_provider=None):
        self._llm = llm_provider  # BaseLLMProvider | None

    async def analyze(self, title: str, content: str | None = None) -> SentimentResult:
        if self._llm:
            return await self._analyze_llm(title, content)
        return self._analyze_rules(title, content)

    def _analyze_rules(self, title, content) -> SentimentResult:
        """关键词词典：利好词/利空词各 ~50 个，统计正负词频打分
        词典作为 POSITIVE_KEYWORDS / NEGATIVE_KEYWORDS 常量定义在模块顶层。
        """

    async def _analyze_llm(self, title, content) -> SentimentResult:
        """单次无状态 LLM 调用
        Prompt 要求返回 JSON: {"sentiment": "positive|negative|neutral", "score": -1.0~1.0, "reason": "..."}
        解析失败时退化为规则模式。
        """
```

**规则模式词典示例：**
- 利好词：增持、业绩大增、超预期、中标、回购、突破、创新高...
- 利空词：减持、亏损、处罚、退市、暴雷、违规、下修、破位...

### 4.3 事件影响评估 (event_assessor.py)

```python
class EventAssessor:
    def __init__(self, llm_provider=None):
        self._llm = llm_provider

    async def assess(self, code: str, event_desc: str, stock_context: dict | None = None) -> EventImpact:
        """评估事件对个股的影响
        注入个股基本面上下文（行业、市值等）让 LLM 做更精准判断。
        无 LLM 时返回 neutral + magnitude=low + "LLM 未配置，无法评估"

        LLM Prompt 期望返回 JSON:
        {"impact": "positive|negative|neutral", "magnitude": "high|medium|low",
         "reasoning": "...", "affected_factors": ["盈利预期", "市场情绪"]}
        """
```

### 4.4 InfoEngine 门面 (engine.py)

```python
class InfoEngine:
    def __init__(self, data_engine, llm_provider=None):
        self._data = data_engine
        self._sentiment = SentimentAnalyzer(llm_provider)
        self._assessor = EventAssessor(llm_provider)
        self._store = data_engine.store  # DuckDB
        self._config = None  # 延迟加载 InfoConfig

    async def get_news(self, code: str, limit: int = 50) -> list[NewsArticle]:
        """拉取新闻 + 情感分析
        1. 检查 DuckDB info.news_articles 缓存（config.news_cache_hours 内）
        2. 缓存未命中 → DataEngine.get_news() 拉取原始数据（同步，通过 to_thread）
        3. 逐条情感分析（async LLM 调用）
        4. 写入缓存
        """

    async def get_announcements(self, code: str, limit: int = 20) -> list[Announcement]:
        """拉取公告 + 情感分析
        同上，缓存 config.announcement_cache_hours
        """

    async def assess_event_impact(self, code: str, event_desc: str) -> EventImpact:
        """事件影响评估
        1. 检查 info.event_impacts 缓存
        2. 未命中 → LLM 评估（async）
        3. 写入缓存
        """
```

### 4.5 单例工厂

```python
# engine/info_engine/__init__.py
_info_engine: InfoEngine | None = None

def get_info_engine() -> InfoEngine:
    global _info_engine
    if _info_engine is None:
        from data_engine import get_data_engine
        from config import settings
        llm_provider = None
        try:
            from llm.config import llm_settings
            from llm.providers import LLMProviderFactory
            if llm_settings.api_key:
                llm_provider = LLMProviderFactory.create(llm_settings)
        except Exception:
            pass  # LLM 不可用，退化为规则模式
        _info_engine = InfoEngine(
            data_engine=get_data_engine(),
            llm_provider=llm_provider,
        )
    return _info_engine
```

## 5. DuckDB Schema

表在 DataEngine 的 `stockterrain.duckdb` 中，`info` schema：

```sql
CREATE SCHEMA IF NOT EXISTS info;

CREATE TABLE IF NOT EXISTS info.news_articles (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR NOT NULL,
    title       VARCHAR NOT NULL,
    content     VARCHAR,
    source      VARCHAR,
    publish_time VARCHAR,
    url         VARCHAR,
    sentiment   VARCHAR,          -- positive/negative/neutral
    sentiment_score DOUBLE,       -- -1.0 ~ 1.0
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, title)           -- 相同股票+标题不重复存储
);

CREATE TABLE IF NOT EXISTS info.announcements (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR NOT NULL,
    title       VARCHAR NOT NULL,
    type        VARCHAR,
    date        VARCHAR,
    url         VARCHAR,
    sentiment   VARCHAR,
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, title)
);

CREATE TABLE IF NOT EXISTS info.event_impacts (
    id          INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        VARCHAR NOT NULL,
    event_desc  VARCHAR NOT NULL,
    impact      VARCHAR,          -- positive/negative/neutral
    magnitude   VARCHAR,          -- high/medium/low
    reasoning   VARCHAR,
    affected_factors VARCHAR,     -- JSON array
    assessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(code, event_desc)
);
```

**缓存策略：**
- news_articles: 24h 内同 code+title 命中缓存
- announcements: 48h 内同 code+title 命中缓存
- event_impacts: 相同 code+event_desc 永久缓存（事件评估是确定性的）

## 6. REST API

```
GET  /api/v1/info/news/{code}
    ?limit=50
    → { code, news: [NewsArticle], sentiment_summary: {positive: N, negative: N, neutral: N} }

GET  /api/v1/info/announcements/{code}
    ?limit=20
    → { code, announcements: [Announcement] }

POST /api/v1/info/assess
    body: { code, event_desc }
    → EventImpact

GET  /api/v1/info/health
    → { status, sentiment_mode, llm_available }
```

## 7. 集成点

### 7.1 Agent DataFetcher

替换 `engine/agent/data_fetcher.py` 中的 stub：

```python
def get_info_data(self, target: str) -> dict:
    from info_engine import get_info_engine
    ie = get_info_engine()
    news = ie.get_news(target, limit=20)
    announcements = ie.get_announcements(target, limit=10)
    return {
        "news": [n.model_dump() for n in news],
        "announcements": [a.model_dump() for a in announcements],
    }
```

### 7.2 MCP Tools

新增 3 个 tool 到 `mcpserver/tools.py` 和 `mcpserver/server.py`（15 → 18 tools）：
- `get_news` → 调 InfoEngine.get_news()
- `get_announcements` → 调 InfoEngine.get_announcements()
- `assess_event_impact` → 调 InfoEngine.assess_event_impact()

> 注：路线图 `/api/v1/news/*` 改为 `/api/v1/info/*`，因为 InfoEngine 不仅覆盖新闻，还包括公告和事件评估。

### 7.3 main.py

注册 `info_router`，与 quant_router 同模式。

### 7.4 config.py

新增 `InfoConfig` 并注册到 `AppConfig`：

```python
class InfoConfig(BaseModel):
    news_cache_hours: int = 24
    announcement_cache_hours: int = 48
    default_news_limit: int = 50
    default_announcement_limit: int = 20
    sentiment_mode: str = "auto"  # "auto" | "llm" | "rules"

class AppConfig(BaseModel):
    # ... 现有字段 ...
    info: InfoConfig = InfoConfig()
```

## 8. 不在本次范围内

- **PreScreen 短路逻辑** — InfoEngine 数据跑通后下一轮再做
- **事件驱动触发** — Orchestrator 自动检测重大事件并触发分析
- **行业/板块级舆情聚合** — 个股级别先跑通
- **新闻去重/聚合** — 多源新闻的去重和合并
- **定时采集任务** — 当前按需拉取，不做定时爬取

## 9. 测试策略

- **单元测试：** schemas 验证、规则情感分析（关键词匹配）、缓存命中/未命中
- **集成测试：** DataEngine → InfoEngine 全链路（mock AKShare 返回）
- **LLM 测试：** mock LLM provider，验证 prompt 构造和 JSON 解析，LLM 返回格式异常时退化为规则
- **降级测试：** AKShare 新闻接口不可用时返回空列表（不抛异常），LLM 不可用时退化为规则
- **MCP/API 测试：** 路由注册、参数校验、tool count 验证（18 tools）
