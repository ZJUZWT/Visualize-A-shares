# Agent Wake UI Visibility Design

> 编写日期：2026-03-22
> 范围：把已落地的 `watch_signals` 与 `info_digests` 接入 `/agent` 页面，让 wake/data-hunger 闭环从“后端存在”变成“前端可见、可操作、可追溯”。

---

## 1. 背景

当前主干已经具备 wake/data-hunger 的最小后端闭环：

- `GET/POST/PATCH /api/v1/agent/watch-signals`
- `GET /api/v1/agent/info-digests`
- `brain_runs` 已可记录 `info_digest_ids` 与 `triggered_signal_ids`

但 `/agent` 仍只展示 run、review、memory、reflection。结果是：

- Agent 在“等什么信号”不可见
- 某次 run “消化了什么信息”不可见
- 用户无法从前端直接补充或维护 watch signal

这让 wake/data-hunger 成了隐藏能力，无法支撑下一步的信息免疫、信息复盘和策略审计。

---

## 2. 目标

本批次只做前端可视化与最小交互，不改后端行为：

1. `/agent` 新增 `wake` tab
2. 展示当前组合的 watch signals
3. 展示 info digests，并默认优先关联当前选中的 run
4. 支持从 `/agent` 创建新的 watch signal
5. 支持最小状态维护：把 signal 标记为 `triggered` 或 `cancelled`

---

## 3. 非目标

本批次不做：

- 新的后端 schema 或新的 agent prompt
- 自动创建 watch signal 的推荐器
- digest 的全文事件溯源展开页
- 盘中调度、定时轮询或 websocket
- `/agent` 整体布局重写

---

## 4. 设计选择

### 4.1 新增独立 `wake` tab，而不是塞进 `runs`

候选方案有三种：

- 直接塞进 `runs` tab：实现快，但会继续膨胀已有页面逻辑
- 做成 run 详情的附属卡片：run 相关性强，但 watch signal 是跨 run 的，不适合被 run 详情吞掉
- 新增 `wake` tab：把“观察条件”和“信息消化结果”收敛到单独语义面

本批次采用第三种。

理由：

- `watch_signals` 是组合级对象，不是单次 run 对象
- `info_digests` 与 run 强相关，但也需要看最近全量
- 新 tab 能避免 `runs` 页进一步失控

### 4.2 抽出 wake view-model，而不是继续把归一化逻辑堆进 `page.tsx`

当前 `frontend/app/agent/page.tsx` 已经承载大量 normalize/fetch/filter 逻辑。继续往里塞 wake 逻辑，只会让后续维护更差。

因此本批次新增独立的 wake view-model 模块，负责：

- `WatchSignal` / `InfoDigest` 的归一化
- wake 摘要统计
- digest 过滤规则
- create form 的 payload 组装

这样可以用纯 `node:test` 对前端数据层做 TDD，而不必先引入新的 UI 测试框架。

---

## 5. 交互设计

### 5.1 左栏：Watch Signals Panel

左栏展示三层内容：

1. wake summary
   - watching 数
   - triggered 数
   - failed / cancelled 数
2. create form
   - `stock_code`
   - `sector`
   - `signal_description`
   - `keywords`（逗号分隔）
   - `if_triggered`
   - `cycle_context`
   - `check_engine` 先固定 `info`
3. signal list
   - 标的、行业、描述、关键词、状态
   - `if_triggered`
   - `trigger_evidence`
   - 最小状态按钮：`triggered` / `cancelled`

### 5.2 右栏：Info Digests Panel

右栏展示 digest timeline：

- 默认优先展示当前选中 run 的 digests
- 如果当前 run 没有关联 digest，则回退到最近 digests
- 提供一个简单切换：
  - `selected run`
  - `recent`
- 每条 digest 展示：
  - `stock_code`
  - `digest_type`
  - `impact_assessment`
  - `strategy_relevance`
  - `structured_summary.summary`
  - `key_evidence`
  - `risk_flags`
  - `missing_sources`
  - `created_at`

---

## 6. 数据流

### 6.1 读取

当 `activeTab === "wake"` 且存在 `portfolioId` 时：

- 请求 `GET /api/v1/agent/watch-signals?portfolio_id=...`
- 请求 `GET /api/v1/agent/info-digests?portfolio_id=...&limit=30`

digest 不在 fetch 阶段强绑 `run_id`，而是在前端根据 `selectedRun.id` 做过滤，这样切换 run 不需要重复请求。

### 6.2 写入

create form 提交到：

- `POST /api/v1/agent/watch-signals`

状态按钮提交到：

- `PATCH /api/v1/agent/watch-signals/{signal_id}`

成功后直接刷新 wake 数据；不做 optimistic update，先保持逻辑简单和可审计。

---

## 7. 错误处理

- watch signal 读取失败：左栏保留错误卡片
- digest 读取失败：右栏保留错误卡片
- create / patch 失败：表单或列表顶部给出具体错误信息
- 某类字段缺失：按只读容错处理，不阻断整个 tab

---

## 8. 测试策略

本批次不新增 UI E2E。

测试收敛为两层：

1. `node:test` 覆盖 wake view-model
   - watch signal 归一化
   - info digest 归一化
   - selected run / recent digest 过滤
   - create payload 组装
2. 前端编译验证
   - `tsc --noEmit`
   - `next build`

---

## 9. 风险与后续

当前页面仍然偏胖，wake 只是进一步提醒：`page.tsx` 需要继续把各 tab 的数据层拆出去。

但本批次先做到两点即可：

- 不把 wake 逻辑继续内联成不可维护的大文件
- 不把前端变成只能展示、不能维护的只读壳

完成后，后续就能继续推进：

- 信息复盘面板
- run 与 digest 的更细粒度联动
- 自动生成 watch signal 的建议流
