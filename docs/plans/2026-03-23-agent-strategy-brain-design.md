# Agent Strategy Brain Design

> 编写日期：2026-03-23
> 范围：把 `/agent` 中栏从碎片化 tab 面板重构为一个完整的 `Strategy Brain` 视图，一次性补齐“当前策略状态 / 信念列表 / 决策时间线 / 反思与演化”主线。

---

## 1. 背景

当前中栏已经具备多份读模型数据：

- `/api/v1/agent/state`
- `/api/v1/agent/brain/runs`
- `/api/v1/agent/memories`
- `/api/v1/agent/reflections`
- `/api/v1/agent/strategy/history`

但前端呈现仍然是多个分散 panel + tab：

- `当前状态`
- `最近运行上下文`
- `经验规则`
- `反思记录`
- `策略演进`

这有两个问题：

1. 数据虽在，但没有形成“大脑透明化”的连续叙事
2. 用户必须自己跨 tab 拼接“现在怎么看、为什么这么看、最近怎么决策、后来怎么修正”

`TODO` 里中栏的核心诉求不是“多几个面板”，而是“让 AI 大脑透明”。

---

## 2. 目标

本批次一次性完成：

1. 用一个整合型 `Strategy Brain` 主面板替换当前中栏碎片化主视图
2. 把现有读模型重新编排成 4 个连续信息区块：
   - 当前策略状态
   - 信念列表
   - 决策日志 Timeline
   - 反思与策略演化
3. 保持后端零新增接口，全部复用现有 read models
4. 把原有 tab 切换依赖降到最低，避免中栏继续被割裂

---

## 3. 非目标

本批次不做：

- 后端新增 belief history / decision log 专门接口
- 可视化关系图、力导图、复杂图表库
- 可编辑策略脑状态
- 右栏 richer 持仓卡
- 左栏 chat 交互继续扩展

---

## 4. 方案选择

### 方案 A：做一个真正整合的 `Strategy Brain`，我推荐

把当前 `state / runs / memories / reflections / strategy history` 统一映射成一个脑图视角：

- 顶部看“当前大脑状态”
- 中部看“当前信念”
- 再往下看“最近如何决策”
- 最后看“如何复盘与演化”

优点：

- 最符合 `TODO`
- 信息阅读路径完整
- 不依赖后端新接口

缺点：

- 前端 view-model 和渲染层改动较大

### 方案 B：保留旧 tab，只在每个 tab 上做些加强

优点：

- 改动小

缺点：

- 还是碎
- 不能真正解决“Strategy Brain 不透明”

### 方案 C：先做一个壳，把旧 panel 硬塞进去

优点：

- 最快

缺点：

- 只是换皮
- 继续积累信息结构债务

结论：采用方案 A。

---

## 5. 信息架构

新的中栏 `Strategy Brain` 由一个连续面板构成，按以下顺序渲染：

### 5.1 Brain Snapshot

展示当前 agent 的高层态势：

- 大盘观点
- 仓位水平
- 行业偏好
- 风险提醒
- 最近一次 run 状态、时间、token、决策数量

用户在这里先回答“AI 现在怎么看市场”。

### 5.2 Belief Ledger

把 memory rules 映射成“信念卡”：

- 规则文本
- 分类
- 置信度进度条
- 验证次数 / 胜场
- active / retired 状态
- 来源 run

它不做复杂知识图谱，但会做成一组高可读 belief cards，满足“信念列表 + 置信度”主诉求。

### 5.3 Decision Timeline

以最近 runs 为主线，展示：

- run 时间
- run 状态
- state_before -> state_after 的关键变化
- execution_summary
- decisions 明细
- thinking_process 摘要

一条 run 就是一条简化“决策日志 Timeline”节点。

### 5.4 Reflection & Evolution

合并原来的 reflections 与 strategy history：

- 最近反思卡片
- 演化时间线节点
- 对市场观点 / 仓位 / 风险提醒的变化做轻量摘要

用户在这里回答“AI 后来如何审视自己，以及它的策略是否发生了变化”。

---

## 6. 数据映射

引入新的前端 view-model：

- `frontend/app/agent/lib/strategyBrainViewModel.ts`

它负责把现有 read models 压成统一结构：

- `buildStrategyBrainSnapshot(state, activeRun)`
- `buildStrategyBeliefs(memoryRules)`
- `buildDecisionTimeline(runs)`
- `buildStrategyEvolution(reflections, strategyHistory)`
- `buildStrategyBrainViewModel(...)`

这样组件不直接消费零散后端 shape，后续若后端演进也只改映射层。

---

## 7. UI 结构

新增：

- `frontend/app/agent/components/StrategyBrainPanel.tsx`

这个组件会成为中栏主视图，替代当前以 `activeTab` 为中心的碎片渲染。

仍可保留部分旧组件文件，但它们不再是中栏主入口。
本批次更倾向把已有渲染逻辑吸收到新面板，而不是继续维护“状态 panel / run panel / history panel”并行存在。

---

## 8. 代码落点

- `frontend/app/agent/lib/strategyBrainViewModel.ts`
  - 新增统一 brain 映射 helper
- `frontend/app/agent/lib/strategyBrainViewModel.test.ts`
  - 新增 TDD 测试
- `frontend/app/agent/components/StrategyBrainPanel.tsx`
  - 新增整合面板
- `frontend/app/agent/page.tsx`
  - 中栏从旧 tab 主视图切换到新 `StrategyBrainPanel`
  - 原 tab 状态与对应懒加载 effect 可适度简化
- `frontend/app/agent/types.ts`
  - 如有需要，补充前端 brain view-model 类型

---

## 9. 测试策略

采用前端 TDD，重点验证 view-model：

- 空数据安全
- state + activeRun 正确映射 brain snapshot
- memory rules 正确映射 beliefs
- runs 正确映射 decision timeline
- reflections + strategy history 正确映射 evolution sections

UI 层仍以组件渲染实现为主，不额外引入新测试框架。
