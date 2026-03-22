# Agent Info Review Design

> 编写日期：2026-03-22
> 范围：把 Main Agent 的 `info_digests` 接入日复盘 / 周反思，让系统不仅能“决策前消化信息”，还能“决策后审计信息是否有用、是否误导”。

---

## 1. 背景

当前 Main Agent 已经补齐了决策前的信息闭环：

- `watch_signals`
- `info_digests`
- 决策 prompt 中的 digest 上下文
- 决策质量 gate

但复盘侧仍然只看 trade 结果，不看“当时消化的信息本身是不是靠谱”。

这导致两个问题：

- 某次交易做错了，系统知道“亏了”，但不知道是不是被某条消息误导了
- 某类 digest 长期有帮助还是长期噪音，系统没有积累

所以当前系统只有“交易复盘”，没有“信息复盘”。

---

## 2. 目标

本批次只做后端闭环，不新增前端面板：

1. 日复盘时，把当日相关 `info_digests` 纳入审计
2. 生成结构化“信息复盘”结果：
   - digest 总数
   - 有帮助的 digest 数
   - 噪音 / 误导性 digest 数
   - 缺失来源最多的是哪些
3. 把信息复盘结果写入现有 `daily_reviews` / `weekly_reflections`
4. 让 `/api/v1/agent/reflections` 直接返回这部分详情

---

## 3. 非目标

本批次不做：

- 新建 `info_review_records` 表
- 新增 `/agent` 专属信息复盘面板
- LLM 参与信息复盘总结
- 回写 memory / watch signal 推荐

这些都可以在后续基于稳定语义再接。

---

## 4. 方案对比

### 方案 A：只把信息复盘拼进 summary 文本

优点：

- 改动最小

缺点：

- 难以统计
- 前端拿不到结构化字段
- 后续面板化一定返工

### 方案 B：扩现有 reflection journals，新增 `info_review_summary` + `info_review_details`

做法：

- `daily_reviews` 新增：
  - `info_review_summary TEXT`
  - `info_review_details JSON`
- `weekly_reflections` 新增同名字段
- `ReviewEngine` 负责填充
- `service.list_reflections()` 把这部分透传进 `details`

优点：

- 不新开表，增量最小
- 结构化数据可以直接复用到后续前端
- 现有 reflection feed 立刻受益

缺点：

- 日 / 周 journal 会比现在更重一点

### 方案 C：单独新建 `info_review_records`

优点：

- 语义最纯

缺点：

- 现在过早，会把 schema 和读模型都变复杂

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 日信息复盘

`daily_review()` 在处理完 trade review 后，新增一步：

- 收集当天相关 `info_digests`
  - 优先按当日 `brain_runs` 关联
  - 或者按 `created_at` / `run_id` 回收当日 digest

对每条 digest 做规则化判断：

- `impact_assessment in {"minor_adjust", "reassess"}` 且最终有对应 trade / plan -> `useful`
- `missing_sources` 非空且没有后续动作 -> `inconclusive`
- `self_critique` / 决策 gate 显示“等待确认”，但 digest 仍推动了动作 -> `misleading`
- 其他 -> `noted`

MVP 不追求绝对正确，只追求稳定、可解释。

### 5.2 周信息复盘

`weekly_review()` 聚合当周 daily info review：

- digest 总数
- useful 总数
- misleading 总数
- inconclusive 总数
- 最常见的缺失来源

并产出一段周反思摘要，例如：

`本周共消化 12 条 digest，其中 3 条对决策有帮助，2 条带来噪音，最常缺失的是 announcements。`

### 5.3 Reflection 输出

`list_reflections()` 不改路由，只增强输出：

- `details.info_review` 放结构化信息复盘对象
- `summary` 优先保留原 trade/review 摘要；若存在 `info_review_summary`，则拼接或补充

这样现有前端 `ReflectionFeedPanel` 无需修改就能看到详情 JSON。

---

## 6. 字段设计

### 6.1 `agent.daily_reviews`

- `info_review_summary TEXT`
- `info_review_details JSON`

### 6.2 `agent.weekly_reflections`

- `info_review_summary TEXT`
- `info_review_details JSON`

`info_review_details` 的最小结构：

```json
{
  "digest_count": 4,
  "useful_count": 1,
  "misleading_count": 1,
  "inconclusive_count": 2,
  "top_missing_sources": ["announcements", "technical_indicators"],
  "items": [
    {
      "digest_id": "digest-1",
      "stock_code": "600519",
      "review_label": "useful",
      "impact_assessment": "minor_adjust",
      "missing_sources": []
    }
  ]
}
```

---

## 7. 测试策略

重点做 review/memory 侧单测：

1. schema 扩展测试
2. daily review 生成 `info_review_summary` / `info_review_details`
3. weekly review 聚合 daily info review
4. reflection read model 带出 `details.info_review`

---

## 8. 后续衔接

这个批次做完后，下一步就有两个自然方向：

- `/agent` reflection 区域把 `info_review` 做成可读卡片
- 把“误导性 digest”反向喂给 decision quality / memory

如果现在直接做前端专门面板，字段语义还不够稳定，返工概率更高。
