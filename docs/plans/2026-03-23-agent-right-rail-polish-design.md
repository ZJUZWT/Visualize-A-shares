# Agent Right Rail Polish Design

> 编写日期：2026-03-23
> 范围：把 `/agent` 右栏时间线与历史回放之间的剩余交互细节一次性补齐，不再拆成多个微批次。

---

## 1. 背景

当前右栏已经完成：

- 双净值曲线展示
- 历史回放展示
- 点击曲线点同步 replay 日期

但仍有几处体验层面的缺口：

- 曲线缺少 hover 信息反馈
- 当前选中日期不够醒目
- 点选反馈较弱
- 点击命中区还不够克制

这些都属于同一块交互层，不值得继续拆成多个独立回合。

---

## 2. 目标

本批次一次性收掉以下 4 个细节：

1. hover 提示日期和资产值
2. 当前选中日期文案
3. 更明确的选中反馈
4. 更稳的点位命中区

---

## 3. 非目标

本批次不做：

- 图表库替换
- 拖拽 / 缩放
- 十字线
- 多点比较
- 复杂 tooltip 定位系统

---

## 4. 方案

采用同一套轻量 SVG 交互继续扩展：

- hover 时记录当前 point
- 在图表上方渲染一个轻量信息条，而不是复杂浮层
- 选中日期在标题区和图内同时可见
- 把透明命中圆半径控制在合理范围，减少误触

这样能把信息反馈补齐，但不会把当前实现复杂化。

---

## 5. 代码落点

- `frontend/app/agent/lib/rightRailTimelineViewModel.ts`
  - 新增 hover/selection helper
- `frontend/app/agent/lib/rightRailTimelineViewModel.test.ts`
  - 补 helper 测试
- `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
  - 增加 hover 信息条、选中日期文案、命中区和选中反馈样式

---

## 6. 测试策略

继续只做纯 helper 测试：

- hover point summary 正确
- selected date label 正确
- 空数据安全

UI 层用现有实现直接落地，不额外引入测试框架。
