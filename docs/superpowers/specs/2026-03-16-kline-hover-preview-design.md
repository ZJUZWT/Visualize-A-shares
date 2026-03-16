# K 线 Hover 浮窗预览设计

## 目标

在专家对话 ThinkingPanel 中，当 tool_result 包含 K 线数据时，显示一个 📈 图标，hover 后浮现 K 线预览小窗。

## 范围

纯前端功能。不改后端 API。

---

## 交互设计

1. ThinkingPanel 中 tool_result 条目，如果 `data.action` 为 `query_history` 或 `query_hourly`，在条目右侧显示一个小的 📈 图标（`TrendingUp` from lucide-react）
2. 鼠标 hover 图标 300ms 后，在图标附近浮现一个 K 线小窗
3. 小窗内容：蜡烛图（主图）+ 成交量柱状图（副图），标题显示股票代码+名称
4. 鼠标移走后小窗消失
5. 小窗尺寸：400x250px，`position: fixed`，定位在图标右侧或左侧（自动避免溢出屏幕）

## 数据流

```
tool_result SSE 事件
  → data.action === "query_history" | "query_hourly"
  → data.content 包含 JSON 字符串
  → 解析出 records 数组: [{ date, open, high, low, close, volume }, ...]
  → 喂给 Lightweight Charts createChart() + addCandlestickSeries() + addHistogramSeries()
```

数据解析在首次 hover 时执行，解析结果缓存在 React state 中，后续 hover 直接复用。

## 技术方案

**图表库：** `lightweight-charts` (TradingView 官方开源)

**KLinePreview 组件：**
- 接收 `records: { date, open, high, low, close, volume }[]` 和 `title: string`
- 使用 `useRef` 挂载 canvas 容器
- `useEffect` 中创建 chart 实例，设置暗色主题配色（匹配 debate-dark）
- 组件卸载时 `chart.remove()` 清理

**HoverKLineIcon 组件：**
- 渲染 `TrendingUp` 图标
- 管理 hover 状态 + 300ms 延迟定时器
- hover 激活时渲染 `KLinePreview`，通过 React Portal 挂载到 `document.body`
- 使用 `getBoundingClientRect()` 计算浮窗位置

**数据解析：**
- 从 `tool_result.data.content` 中提取 JSON
- content 格式为专家回复的 Markdown 文本，其中包含原始 JSON 数据
- 实际数据在 `tool_result.data` 的原始 SSE payload 中，需要从 store 层传递 raw records

**Store 层调整：**
- tool_result 合并到 tool_call 时，如果 action 是 `query_history`/`query_hourly`，额外保存解析后的 records 数组到 `result.chartData` 字段

## 涉及文件

| 文件 | 操作 |
|------|------|
| `web/components/expert/KLinePreview.tsx` | 新建：K 线图表组件 |
| `web/components/expert/ThinkingPanel.tsx` | 修改：tool_call 条目添加 HoverKLineIcon |
| `web/types/expert.ts` | 修改：ToolResultData 增加 chartData 可选字段 |
| `web/stores/useExpertStore.ts` | 修改：解析 OHLCV 数据存入 chartData |
| `package.json` | 修改：添加 lightweight-charts 依赖 |

## 配色

匹配 debate-dark 主题：
- 背景：`#1e293b`（--bg-secondary）
- 涨：`#ef4444`（--red-stock，A 股红涨）
- 跌：`#10b981`（--green-stock，A 股绿跌）
- 成交量涨：`rgba(239, 68, 68, 0.3)`
- 成交量跌：`rgba(16, 185, 129, 0.3)`
- 网格线：`#334155`（--border）

## 不做的事情

- 不做技术指标叠加（后续可扩展）
- 不做周期切换
- 不做图表交互（缩放、拖拽）— 纯预览
- 不改后端 API
- 不在辩论页添加（仅专家对话）
