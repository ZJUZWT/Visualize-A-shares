# Agent Right Rail Point Sync Design

> 编写日期：2026-03-23
> 范围：为 `/agent` 右栏收益曲线增加“点击日期点同步历史回放日期”的最小交互闭环。

---

## 1. 背景

当前 `/agent` 右栏已经具备：

- `Equity Timeline`
- `Historical Replay`
- 日期输入框切换 replay

但两者仍是弱连接：

- 用户能看到曲线
- 也能手动改 replay 日期
- 但不能直接从曲线某个时间点跳到对应回放

这会让“看曲线 -> 回看当天发生什么”的路径多一步，验证效率不够高。

---

## 2. 目标

本批次只做一个很小的交互增强：

1. 点击曲线上的日期点
2. 自动切换下方 replay 日期
3. 当前选中日期点高亮
4. 日期输入框和曲线高亮保持同步

---

## 3. 非目标

本批次不做：

- 拖拽时间轴
- hover tooltip
- 十字线
- 缩放和平移
- 多点比较
- 曲线联动其他 tab

---

## 4. 方案对比

### 方案 A：只允许日期输入框切换

优点：

- 已经存在

缺点：

- 操作链路长
- 曲线和回放仍是割裂的

### 方案 B：为曲线点增加点击热区和选中态

做法：

- 每个日期点生成可点击命中区
- 点击后调用现有 `onReplayDateChange`
- 用 `replayDate` 驱动选中高亮

优点：

- 改动最小
- 交互最直接
- 不需要新接口

缺点：

- 需要补一层点位模型

### 方案 C：点击整段 polyline 最近点吸附

优点：

- 体验更顺滑

缺点：

- 命中逻辑更复杂
- 超出当前最小范围

本批次采用方案 B。

---

## 5. 核心设计

### 5.1 交互语义

- 默认选中日期 = 当前 `replayDate`
- 点击某个日期点：
  - 调用 `onReplayDateChange(point.date)`
  - 下方 replay 切换到该日
  - 图上该日点高亮
- 若用户手动改日期输入框：
  - 图上选中点同步变化

### 5.2 图表数据模型

在现有 `rightRailTimelineViewModel` 上增加一个纯函数，负责生成 chart point model：

- 输入：
  - timeline points
  - chart width / height
  - selected date
- 输出：
  - `date`
  - `x`
  - `y`
  - `equity`
  - `isSelected`

这样点位计算仍然可用 `node:test` 做 TDD，不依赖 UI 测试框架。

### 5.3 渲染方式

每条线仍然保持 `polyline`。

在其上额外渲染两层点：

1. 可见点
   - 普通状态：小圆点
   - 选中状态：更大圆点 + 描边
2. 透明命中点
   - 半径更大
   - 负责点击事件

这样既能保留轻量 SVG，又不需要复杂的命中算法。

### 5.4 选中态规则

- `replayDate` 等于点的 `date` 时，该点 `isSelected = true`
- 两条线共享同一选中日期
- 若该日期在两条线上都存在，两条线的点都高亮

---

## 6. 代码落点

- `frontend/app/agent/lib/rightRailTimelineViewModel.ts`
  - 新增 chart point model helper
- `frontend/app/agent/lib/rightRailTimelineViewModel.test.ts`
  - 新增点位和选中态测试
- `frontend/app/agent/components/ExecutionLedgerPanel.tsx`
  - 为两条线渲染可点击点和高亮状态

`page.tsx` 只复用已有 `replayDate` 和 `onReplayDateChange`，不需要新增状态。

---

## 7. 测试策略

本批次只做纯函数层测试：

1. chart point model 生成正确坐标
2. 选中日期会标记正确点
3. 空 timeline 不报错

UI 层只做实现，不额外引入组件测试依赖。

---

## 8. 后续扩展位

这个点选闭环做完后，后面可以自然扩展：

- hover 显示当日资产值
- 点击整条线最近点吸附
- 曲线拖动刷选日期区间

但这些都不该阻塞当前最小交互增强。
