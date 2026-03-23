# Agent Demo Structured Summary Design

> 编写日期：2026-03-23
> 范围：为 demo agent 验证链路新增一个机器友好的 MCP summary tool，供 agent 自动验收使用。

---

## 1. 背景

当前已经有两个可用入口：

- `prepare_demo_agent_portfolio`
- `verify_demo_agent_cycle`

其中 `verify_demo_agent_cycle` 的文本报告已经适合 operator 阅读，但对 agent 自动消费仍然偏重：

- 需要解析多段 markdown
- 需要从自然语言里抽取 proof
- 不适合直接作为“是否通过 demo 闭环验收”的机器判断输入

因此需要一个更薄的结构化入口。

---

## 2. 目标

本批次一次性完成：

1. 新增 `get_demo_agent_cycle_summary`
2. 返回稳定、精简、机器友好的 JSON 字符串
3. 不改变现有 `verify_demo_agent_cycle` 文本语义

---

## 3. 非目标

本批次不做：

- 替换现有文本版 tool
- 暴露完整 verification payload
- 新增前端消费界面

---

## 4. 方案选择

### A. 在 `verify_demo_agent_cycle` 上加 `json=true`

优点：

- 少一个入口

缺点：

- 文本和结构化两种职责耦合
- 长期容易变脏

### B. 新增 `get_demo_agent_cycle_summary`

优点：

- 语义清晰
- 机器消费成本最低
- 不影响现有 operator 文本版

缺点：

- MCP 多一个 tool

### C. 直接暴露完整原始 payload

优点：

- 改动最少

缺点：

- 结构太重
- 容易把内部字段永久固化

本批次采用 B。

---

## 5. 输出结构

返回 JSON 字符串，包含：

- `scenario_id`
- `portfolio_id`
- `verification_status`
- `run_id`
- `failed_stage`
- `ready`
- `proof`
  - `review_records_delta`
  - `daily_reviews_delta`
  - `weekly_reflections_delta`
  - `weekly_summaries_delta`
  - `memories_added`
  - `memories_updated`
  - `memories_retired`
- `review_effect`
  - `review_type`
  - `summary_written`
  - `reflection_written`

---

## 6. Ready 规则

`ready = true` 当且仅当：

- `verification_status == "pass"`
- `review_records_delta >= 1`
- `daily_reviews_delta >= 1`
- `weekly_reflections_delta >= 1`
- `weekly_summaries_delta >= 1`

否则 `ready = false`。

这是 demo 验收规则，不是通用交易系统规则。

---

## 7. 架构

只在 MCP 包装层新增 summary extractor：

- `backend/mcpserver/agent_verification.py`
  - `_build_demo_cycle_summary()`
  - `get_demo_agent_cycle_summary()`

然后在：

- `backend/mcpserver/server.py`

注册新 tool。

---

## 8. 测试策略

MCP wrapper 测试：

- `pass` 场景下 `ready=true`
- proof 字段完整
- review_effect 字段完整

transport 测试：

- 新 tool 已注册

---

## 9. 代码落点

- `backend/mcpserver/agent_verification.py`
- `backend/mcpserver/server.py`
- `tests/unit/mcpserver/test_agent_verification_tools.py`
- `tests/unit/mcpserver/test_http_transport.py`

