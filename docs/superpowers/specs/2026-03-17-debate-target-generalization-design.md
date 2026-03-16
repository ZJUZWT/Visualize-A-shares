# 辩论 Target 泛化 设计文档（Spec B）

## 目标

将辩论系统的 target 从"股票代码/名称"扩展到"板块/行业"和"宏观主题"，让用户可以发起如"半导体板块值不值得配置"、"美联储降息对 A 股的影响"等辩论。

## 背景

当前系统中 `target` 始终被当作股票处理：`resolve_stock_code` 尝试将其解析为 6 位代码，失败则降级。数据拉取、prompt 构建、行业认知生成都假设 target 是个股。Spec A 的 JudgeRAG `analyze_topic` 已经能对任意文本做 RAG 预分析，为 target 泛化打好了基础。

## 架构

### target 类型

```
TargetType = "stock" | "sector" | "macro"
```

- **stock**：6 位代码或已知股票名，现有逻辑
- **sector**：已知行业/板块名（如"半导体"、"新能源"、"白酒"）
- **macro**：宏观主题（如"美联储降息"、"人民币汇率"、"AI 泡沫"）

### 识别流程（TargetResolver）

```
输入 target 字符串
    ↓
规则识别：
  - 6位数字 → stock（直接返回，跳过后续步骤）
  - 在 DataEngine 行业列表中精确/子串匹配 → sector（返回规范化 sector_name）
    ↓（规则无法判断）
轻量 LLM 分类（单次非流式调用，prompt 极短）
  → "股票" | "板块" | "宏观"
    ↓（LLM 失败或返回"股票"）
尝试 resolve_stock_code → stock（有 code）或 macro（fallback）
```

LLM 分类失败时 fallback → macro（最宽泛，不会崩）。

### 数据路径

| target_type | fetch_initial_data | 行业认知 | 资金构成 |
|-------------|-------------------|---------|---------|
| stock | 现有逻辑（get_stock_info / get_daily_history / get_news） | 从 facts["get_stock_info"]["industry"] 取行业名 | 按 code |
| sector | get_sector_overview + get_news（sector_name 作查询词） | 直接传 sector_name | 跳过 |
| macro | get_macro_context（best-effort 宏观指标） | 传 target 文本 | 跳过 |

### Prompt 注入

`build_debate_system_prompt` 在现有模板基础上，根据 target_type 注入一段上下文前缀：

- **sector**：「你正在辩论的是 **{sector_name}** 板块的投资价值。请从板块整体景气度、龙头股表现、产业链位置、估值分位等角度论证，引用黑板上的板块成分股数据。」
- **macro**：「你正在辩论的是宏观主题 **{target}**。请从宏观经济指标、政策预期、市场影响传导链等角度论证，结合行业认知中的周期定位和催化剂。」
- **stock**：不变

`build_data_request_prompt` 签名扩展为接收 `target_type: str = "stock"` 参数，内部白名单查询改为 `DEBATE_DATA_WHITELIST_BY_TYPE.get(target_type, ...)["role"]`，`_DATA_REQUEST_TEMPLATE` 中的 `params` 示例按 target_type 调整：
- stock：`{"code": "{code}"}` （现有）
- sector：`{"sector": "{sector_name}"}`
- macro：`{"query": "{target}"}`

裁判 `JUDGE_SYSTEM_PROMPT` 同样注入 target_type，裁决框架对应调整（板块看景气度/估值分位，宏观看传导链逻辑）。

## 组件设计

### 1. TargetResolver（新建 `engine/agent/target_resolver.py`）

```python
class TargetResolver:
    def __init__(self, llm: BaseLLMProvider | None = None):
        self._llm = llm  # 可选，用于 LLM 分类 fallback

    async def resolve(self, target: str) -> TargetResolution:
        """
        Returns:
            TargetResolution(
                target_type: "stock" | "sector" | "macro",
                resolved_code: str,   # 仅 stock 时有值
                sector_name: str,     # 仅 sector 时有值，规范化后的行业名
                display_name: str,    # 用于 prompt 的展示名
            )
        """
```

规则识别顺序：
1. `re.fullmatch(r"\d{6}", target.strip())` → stock，`resolved_code = target`
2. 在 `DataEngine.get_profiles()` 的 `industry` 字段集合中精确/子串匹配 → sector，`sector_name = 匹配到的规范行业名`
3. 以上均失败且 `self._llm` 可用 → LLM 分类（单次非流式调用）：prompt 为「判断以下辩论题目属于哪类：股票/板块/宏观主题，只输出一个词。题目：{target}」
4. LLM 返回"股票" → 再尝试 `resolve_stock_code(target)`，有结果则 stock，否则 macro
5. LLM 返回"板块" → sector，`sector_name = target`（未规范化，行业认知会处理）
6. LLM 返回"宏观"或失败 → macro

`display_name`：stock 时为股票名（从 profile 取，取失败时 fallback 为 target 原文），sector 时为 sector_name，macro 时为 target 原文。

### 2. Blackboard 扩展

```python
class Blackboard(BaseModel):
    # 新增字段
    target_type: Literal["stock", "sector", "macro"] = "stock"
    sector_name: str = ""   # sector 时的规范化行业名
    display_name: str = ""  # prompt 用展示名，也写入 debate_start SSE 事件
```

注意：`Blackboard.target_type` 与 `AnalysisRequest.target_type`（值为 "stock"/"sector"/"market"）是两个独立字段，不互通，`"macro"` vs `"market"` 的差异是有意为之。

### 3. DataFetcher 扩展

**`get_sector_overview`**（板块概览）
- 参数：`{"sector": sector_name}`（不含 `code` 字段）
- 从 `DataEngine.get_industry_mapping(sector_name)` 拿成分股列表
- 取快照中该行业 Top 5（按 `total_mv` 降序）的行情数据聚合
- `name` 字段需从 `DataEngine.get_profiles()` join 补全（快照中可能无 name 列）；单只股票 name join 失败时用 `code` 代替，不影响整体返回
- 返回：`{sector: str, top_stocks: [{code, name, pct_chg, pe_ttm, total_mv}], avg_pct_chg: float}`
- 失败时返回 `{sector: sector_name, top_stocks: [], avg_pct_chg: 0.0}`

**`get_macro_context`**（宏观上下文，best-effort）
- 参数：`{"query": target}`（不含 `code` 字段）
- 从现有 DataEngine 能拿到的数据拼装（以下均为 best-effort，单项失败不影响整体）：
  - 全市场快照的涨跌比（`snapshot` 中 `pct_chg > 0` 的比例）
  - 行业板块涨跌幅排行：按 `industry` 分组，计算 `pct_chg` 均值，降序排列，最多 20 条，忽略 `industry` 为空的行
- 返回：`{advance_decline_ratio: float | None, sector_heatmap: [{industry, avg_pct_chg}] | None, note: str}`
- 注：不依赖北向资金（无市场级别接口），`note` 字段说明数据局限性

**`fetch_by_request` 守卫调整**：
- 新增 `NO_CODE_ACTIONS = {"get_sector_overview", "get_macro_context"}` 集合（仅包含真正不使用 code 参数的 action；`get_capital_structure`、`get_industry_cognition`、`get_news` 保持原有守卫逻辑）
- `get_news` 在 sector 分支传 `{"code": sector_name, "limit": 10}`（将 sector_name 作为 code 传入，依赖 InfoEngine 的模糊匹配），不加入 `NO_CODE_ACTIONS`，不需要修改 InfoEngine 接口
- `NO_CODE_ACTIONS` 中的 action 跳过 code 解析守卫，直接按 params 调用

**辩手白名单**（`DEBATE_DATA_WHITELIST`）按 target_type 动态切换，实现方式：在 `validate_data_requests` 中，根据 `blackboard.target_type` 选取对应白名单：

```python
DEBATE_DATA_WHITELIST_BY_TYPE = {
    "stock": {
        "bull_expert": [...],  # 现有白名单
        "bear_expert": [...],
        ...
    },
    "sector": {
        "bull_expert": ["get_sector_overview", "get_industry_cognition", "get_news"],
        "bear_expert": ["get_sector_overview", "get_industry_cognition", "get_news"],
        "retail_investor": ["get_news"],
        "smart_money": ["get_sector_overview", "get_macro_context"],
        # 注：get_capital_structure 仅适用于个股，sector 类型有意不包含
    },
    "macro": {
        "bull_expert": ["get_macro_context", "get_industry_cognition", "get_news"],
        "bear_expert": ["get_macro_context", "get_industry_cognition", "get_news"],
        "retail_investor": ["get_news"],
        "smart_money": ["get_macro_context"],
    },
}
```

`validate_data_requests` 签名扩展为接收 `target_type: str` 参数。

### 4. debate.py 改动

**`run_debate` 开头**，替换现有 `resolve_stock_code` 调用：

```python
# target 类型解析（替换旧的 resolve_stock_code）
resolver = TargetResolver(llm=llm)
resolution = await resolver.resolve(blackboard.target)
blackboard.target_type = resolution.target_type
blackboard.code = resolution.resolved_code
blackboard.sector_name = resolution.sector_name
blackboard.display_name = resolution.display_name or blackboard.target
```

**`debate_start` SSE 事件**新增 `display_name` 字段：
```python
yield sse("debate_start", {
    ...,
    "display_name": blackboard.display_name,
    "target_type": blackboard.target_type,
})
```

**`fetch_initial_data`** 按 `blackboard.target_type` 分支（现有函数签名不变，内部分支）：
- stock：现有 3 个 action
- sector：`get_sector_overview`（params: `{"sector": blackboard.sector_name}`）+ `get_news`（params: `{"query": blackboard.sector_name, "limit": 10}`）
- macro：`get_macro_context`（params: `{"query": blackboard.target}`）

**`generate_industry_cognition`** 扩展：接收可选 `target_override: str` 参数，非 stock 时传入 `sector_name` 或 `target`，不再依赖 `facts["get_stock_info"]["industry"]`。早返回守卫改为：
```python
if not industry and not target_override:
    return
effective_industry = target_override or industry
```
`industry_cognition_start` SSE 事件的 `industry` 字段改用 `effective_industry`。

**`run_debate` 开头执行顺序**（明确）：
```python
# 1. target 类型解析（替换旧的 resolve_stock_code）
resolver = TargetResolver(llm=llm)
resolution = await resolver.resolve(blackboard.target)
blackboard.target_type = resolution.target_type
blackboard.code = resolution.resolved_code
blackboard.sector_name = resolution.sector_name
blackboard.display_name = resolution.display_name or blackboard.target

# 2. 确定辩论时间锚点（sector/macro 时 code 为空，直接返回 today）
if not blackboard.as_of_date:
    blackboard.as_of_date = _resolve_as_of_date(blackboard.code)
```：sector/macro 分支使用与 stock 分支完全相同的 `blackboard_update` 事件格式（不是 `data_request_start`/`data_request_done`）：
```python
# 每个 action 开始前
yield sse("blackboard_update", {"request_id": req_id, "source": "public", "engine": engine,
    "action": action, "title": title, "status": "pending", "result_summary": "", "round": 0})
# 完成后
yield sse("blackboard_update", {"request_id": req_id, ..., "status": "done", "result_summary": summary})
# 全部完成后
yield sse("initial_data_complete", {"total": N, "success": N, "failed": 0})
```

**`_resolve_as_of_date`**：sector/macro 时 `code` 为空，直接返回 today，行为不变，无需修改。

**`debate_id` 生成**：仅在路由层生成并清洗，`run_debate` 直接使用传入的 `blackboard.debate_id`，不重复生成：
```python
# 路由层（routes/debate.py）
safe_target = re.sub(r"[^\w\u4e00-\u9fff]", "_", effective_target)[:20]
debate_id = f"{safe_target}_{now.strftime('%Y%m%d%H%M%S')}"
```

**`validate_data_requests`** 签名扩展，白名单从 `personas.py` 中的 `DEBATE_DATA_WHITELIST_BY_TYPE` 取（保持在 `personas.py` 中定义，`debate.py` 更新 import）：
```python
# personas.py 中定义 DEBATE_DATA_WHITELIST_BY_TYPE
# debate.py import 改为：
from agent.personas import DEBATE_DATA_WHITELIST_BY_TYPE

def validate_data_requests(role: str, requests: list[DataRequest], target_type: str = "stock") -> list[DataRequest]:
    whitelist = DEBATE_DATA_WHITELIST_BY_TYPE.get(target_type, DEBATE_DATA_WHITELIST_BY_TYPE["stock"])
    allowed = whitelist.get(role, [])
    ...
```

**`build_debate_system_prompt` 观察员模板**：`_OBSERVER_SYSTEM_TEMPLATE` 的 `format()` 调用同样需传入 `target_type_prefix` 参数（或在 format 调用前将前缀拼接到模板头部，避免修改模板占位符）。推荐方式：在函数入口构造 `prefix` 字符串，拼接到最终 prompt 头部，不修改模板本身。

**`ACTION_TITLE_MAP`** 新增条目：
```python
"get_sector_overview": "板块概览",
"get_macro_context": "宏观上下文",
```

**`/api/v1/debate/summarize` 端点**：将 `f"以下是关于股票 {req.target} 的多空辩论记录"` 改为 `f"以下是关于 {req.target} 的多空辩论记录"`（去掉"股票"限定词）。

**LLM 分类调用说明**：`TargetResolver` 中的 LLM 分类使用非流式调用（`chat()` 而非 `chat_stream()`），这是经批准的例外——辅助性极短调用，失败有 macro fallback 兜底，符合 CLAUDE.md 的例外条款。

### 5. API 路由改动

`DebateRequest` 新增 `target` 字段，`code` 字段保留兼容：

```python
class DebateRequest(BaseModel):
    target: str = Field(default="", description="辩论标的：股票代码/板块名/宏观主题")
    code: str = Field(default="", description="已废弃，请使用 target")
    max_rounds: int = Field(default=3, ge=1, le=5)
    mode: str = Field(default="standard")
    as_of_date: str = Field(default="")
```

路由逻辑：
```python
effective_target = (req.target or req.code).strip()
if not effective_target:
    raise HTTPException(status_code=422, detail="target 不能为空")
```

`debate_id` 在路由层生成时同样做清洗（见上）。

### 6. 前端改动

**`useDebateStore.ts`**：
- `startDebate(code, ...)` → `startDebate(target, ...)`
- 请求体 `{ code }` → `{ target }`
- `debate_start` handler 新增读取 `display_name` 和 `target_type`，存入 store

**`DebatePanel.tsx`（或对应输入组件）**：
- placeholder 改为「股票代码 / 板块名 / 宏观主题」
- 输入框 label 改为「辩论标的」
- 移除任何对输入值的 6 位数字格式校验（如有），改为仅校验非空

## 错误处理

| 场景 | 处理 |
|------|------|
| TargetResolver LLM 分类失败 | fallback → macro，log warning |
| sector 但找不到成分股 | get_sector_overview 返回空列表，辩手依赖行业认知发言 |
| macro 且行业认知也失败 | 辩手纯靠 LLM 知识，JudgeRAG 预分析兜底 |
| 旧客户端传 code 字段 | 路由层兼容，`effective_target = req.target or req.code` |
| target 和 code 均为空 | 路由层 422 ValidationError |
| get_macro_context 数据源不可用 | 返回 `{note: "宏观数据暂不可用"}` 的空结构，辩手降级为纯 LLM 发言 |

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `engine/agent/target_resolver.py` | TargetResolver 类，接收可选 llm 参数；非流式 LLM 分类（approved exception） |
| 修改 | `engine/agent/schemas.py` | Blackboard 新增 target_type / sector_name / display_name |
| 修改 | `engine/agent/debate.py` | run_debate 调用 TargetResolver；fetch_initial_data 按类型分支（含完整 SSE 事件序列）；generate_industry_cognition 接收 target_override，早返回守卫更新；validate_data_requests 接收 target_type，import 改为 DEBATE_DATA_WHITELIST_BY_TYPE；debate_start 事件新增 display_name/target_type；ACTION_TITLE_MAP 新增两条目 |
| 修改 | `engine/agent/data_fetcher.py` | 新增 get_sector_overview（含 name join）、get_macro_context；fetch_by_request 新增 NO_CODE_ACTIONS 守卫跳过逻辑 |
| 修改 | `engine/agent/personas.py` | DEBATE_DATA_WHITELIST_BY_TYPE 替换静态白名单；build_debate_system_prompt 注入 target_type 前缀（拼接方式，不修改模板占位符，观察员模板同步处理）；build_data_request_prompt / _DATA_REQUEST_TEMPLATE 按 target_type 调整 params 示例；JUDGE_SYSTEM_PROMPT 扩展 |
| 修改 | `engine/api/routes/debate.py` | DebateRequest 新增 target 字段；effective_target 逻辑；空值 422 校验；debate_id 清洗（仅在路由层）；summarize 端点去掉"股票"限定词 |
| 修改 | `web/stores/useDebateStore.ts` | startDebate 参数 code→target；debate_start handler 读取 display_name/target_type |
| 修改 | `web/components/debate/DebatePanel.tsx` | 输入框 placeholder/label 更新 |

## 不在范围内

- 自由文本辩题（Spec C，需要"哲学引擎"支撑）
- 辩手 agent 的 RAG 化（保持现有 LLM agent 模式）
- 宏观数据引擎（新增宏观指标数据源，后续迭代）
- `_learn_from_conversation` 扩展支持板块/宏观节点提取
- `AnalysisRequest.target_type` 与 `Blackboard.target_type` 的统一（两者独立演化）
