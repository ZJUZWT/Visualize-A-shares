# K 线 Hover 浮窗预览 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在专家对话 ThinkingPanel 中，hover 📈 图标时浮现 K 线预览小窗。

**Architecture:** 后端 tool_result SSE 事件增加 chartData 字段传递 OHLCV 数据；前端新建 KLinePreview 组件使用 TradingView Lightweight Charts 渲染；ThinkingPanel 中检测 chartData 显示 hover 图标。

**Tech Stack:** lightweight-charts, React, Next.js, Tailwind CSS, lucide-react

---

## File Structure

| 文件 | 职责 | 操作 |
|------|------|------|
| `web/package.json` | 依赖管理 | 修改：添加 lightweight-charts |
| `web/types/expert.ts` | 类型定义 | 修改：ToolResultData 增加 chartData |
| `engine/expert/engine_experts.py` | 引擎专家 SSE | 修改：query_history/hourly 返回 chartData |
| `engine/expert/agent.py` | RAG Agent SSE | 修改：非专家 tool_result 传递 chartData |
| `web/components/expert/KLinePreview.tsx` | K 线图表组件 | 新建 |
| `web/components/expert/ThinkingPanel.tsx` | 思考面板 | 修改：添加 HoverKLineIcon |

---

## Chunk 1: 后端 + 依赖 + 类型

### Task 1: 安装 lightweight-charts

**Files:**
- Modify: `web/package.json`

- [ ] **Step 1: 安装依赖**

```bash
cd web && npm install lightweight-charts
```

- [ ] **Step 2: Commit**

```bash
git add package.json package-lock.json
git commit -m "deps: 添加 lightweight-charts"
```

### Task 2: 后端 tool_result 增加 chartData

**Files:**
- Modify: `engine/expert/engine_experts.py:185-189`
- Modify: `engine/expert/agent.py:229-235`

- [ ] **Step 1: engine_experts.py — tool_result 增加 chartData**

找到 `yield {"event": "tool_result"` 块（line 185-189），将：

```python
yield {"event": "tool_result", "data": {
    "engine": tc.get("engine", self.expert_type),
    "action": tc.get("action", "unknown"),
    "summary": result[:200] if result else "无结果",
}}
```

替换为：

```python
tool_result_data = {
    "engine": tc.get("engine", self.expert_type),
    "action": tc.get("action", "unknown"),
    "summary": result[:200] if result else "无结果",
}
# K 线数据：query_history / query_hourly 返回 chartData
action_name = tc.get("action", "")
if action_name in ("query_history", "query_hourly") and result:
    try:
        parsed = json.loads(result)
        if "records" in parsed:
            tool_result_data["chartData"] = {
                "code": parsed.get("code", ""),
                "records": parsed["records"],
            }
    except (json.JSONDecodeError, KeyError):
        pass
yield {"event": "tool_result", "data": tool_result_data}
```

- [ ] **Step 2: agent.py — RAG agent 非专家 tool_result 传递 chartData**

找到 RAG agent 的 `yield {"event": "tool_result"` 块（line 229-235），在 `"hasError": has_error,` 之后添加 chartData 逻辑：

```python
yield {"event": "tool_result", "data": {
    "engine": r["engine"], "action": r["action"],
    "summary": result_text[:300] if not is_expert else f"{expert_label}已回复（{len(result_text)}字）",
    "label": expert_label if is_expert else r["action"],
    "content": result_text if is_expert else "",
    "hasError": has_error,
    **(_extract_chart_data(r["action"], result_text) or {}),
}}
```

在文件顶部（或 `_reply_stream` 之前）添加辅助函数：

```python
def _extract_chart_data(action: str, result_text: str) -> dict | None:
    """从 query_history/query_hourly 结果中提取 K 线数据"""
    if action not in ("query_history", "query_hourly") or not result_text:
        return None
    try:
        parsed = json.loads(result_text)
        if "records" in parsed:
            return {"chartData": {"code": parsed.get("code", ""), "records": parsed["records"]}}
    except (json.JSONDecodeError, KeyError):
        pass
    return None
```

- [ ] **Step 3: Commit**

```bash
git add engine/expert/engine_experts.py engine/expert/agent.py
git commit -m "feat: tool_result SSE 增加 chartData 字段（K线数据）"
```

### Task 3: 前端类型扩展

**Files:**
- Modify: `web/types/expert.ts:37-47`

- [ ] **Step 1: ToolResultData 增加 chartData 字段**

在 `ToolResultData` 接口中 `hasError` 之后添加：

```typescript
/** K 线图表数据（query_history/query_hourly 时有值） */
chartData?: {
  code: string;
  records: Array<{
    date?: string;
    datetime?: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    [key: string]: unknown;
  }>;
};
```

- [ ] **Step 2: Commit**

```bash
git add web/types/expert.ts
git commit -m "feat: ToolResultData 增加 chartData 类型"
```

## Chunk 2: KLinePreview 组件 + ThinkingPanel 集成

### Task 4: KLinePreview 组件

**Files:**
- Create: `web/components/expert/KLinePreview.tsx`

- [ ] **Step 1: 创建 KLinePreview 组件**

```tsx
"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, type IChartApi } from "lightweight-charts";

interface KLineRecord {
  date?: string;
  datetime?: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface KLinePreviewProps {
  code: string;
  records: KLineRecord[];
  width?: number;
  height?: number;
}

export function KLinePreview({ code, records, width = 400, height = 250 }: KLinePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || records.length === 0) return;

    const chart = createChart(containerRef.current, {
      width,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "#1e293b" },
        textColor: "#94a3b8",
        fontSize: 10,
      },
      grid: {
        vertLines: { color: "#334155" },
        horzLines: { color: "#334155" },
      },
      crosshair: {
        vertLine: { color: "#475569", width: 1, style: 2 },
        horzLine: { color: "#475569", width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: "#334155",
      },
      timeScale: {
        borderColor: "#334155",
        timeVisible: true,
      },
    });

    // 蜡烛图
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#ef4444",
      downColor: "#10b981",
      borderUpColor: "#ef4444",
      borderDownColor: "#10b981",
      wickUpColor: "#ef4444",
      wickDownColor: "#10b981",
    });

    // 成交量
    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    // 数据转换
    const candleData = records.map((r) => ({
      time: (r.date || r.datetime || "").split(" ")[0],
      open: Number(r.open),
      high: Number(r.high),
      low: Number(r.low),
      close: Number(r.close),
    }));

    const volumeData = records.map((r) => ({
      time: (r.date || r.datetime || "").split(" ")[0],
      value: Number(r.volume),
      color: Number(r.close) >= Number(r.open)
        ? "rgba(239, 68, 68, 0.3)"
        : "rgba(16, 185, 129, 0.3)",
    }));

    candleSeries.setData(candleData as any);
    volumeSeries.setData(volumeData as any);
    chart.timeScale().fitContent();

    chartRef.current = chart;

    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, [records, width, height]);

  return (
    <div className="rounded-lg overflow-hidden border border-[var(--border)] shadow-xl">
      <div className="px-3 py-1.5 bg-[#0f172a] text-[10px] text-[var(--text-secondary)] flex items-center justify-between">
        <span className="font-medium">{code}</span>
        <span className="text-[var(--text-tertiary)]">{records.length} bars</span>
      </div>
      <div ref={containerRef} />
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add web/components/expert/KLinePreview.tsx
git commit -m "feat: KLinePreview 组件（Lightweight Charts）"
```

### Task 5: ThinkingPanel 集成 HoverKLineIcon

**Files:**
- Modify: `web/components/expert/ThinkingPanel.tsx`

- [ ] **Step 1: 添加 imports**

在文件顶部添加：

```typescript
import { TrendingUp } from "lucide-react";
import { useState, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { KLinePreview } from "./KLinePreview";
```

同时将现有的 `import { useState } from "react"` 合并到上面的 import。

- [ ] **Step 2: 添加 HoverKLineIcon 组件**

在 `ThinkingPanel` 组件之前添加：

```tsx
/** Hover 触发 K 线浮窗 */
function HoverKLineIcon({ chartData }: { chartData: { code: string; records: any[] } }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const iconRef = useRef<HTMLSpanElement>(null);

  const handleEnter = useCallback(() => {
    timerRef.current = setTimeout(() => {
      if (iconRef.current) {
        const rect = iconRef.current.getBoundingClientRect();
        // 默认在图标右侧，如果右侧空间不够则放左侧
        const spaceRight = window.innerWidth - rect.right;
        const x = spaceRight > 420 ? rect.right + 8 : rect.left - 408;
        // 垂直居中对齐图标，但不超出屏幕
        const y = Math.min(Math.max(rect.top - 100, 8), window.innerHeight - 270);
        setPos({ x, y });
      }
      setShow(true);
    }, 300);
  }, []);

  const handleLeave = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
    setShow(false);
  }, []);

  return (
    <>
      <span
        ref={iconRef}
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        className="cursor-pointer text-[var(--text-tertiary)] hover:text-[var(--accent)] transition-colors"
      >
        <TrendingUp size={12} />
      </span>
      {show && typeof document !== "undefined" && createPortal(
        <div
          className="fixed z-50 pointer-events-none"
          style={{ left: pos.x, top: pos.y }}
        >
          <KLinePreview code={chartData.code} records={chartData.records} />
        </div>,
        document.body,
      )}
    </>
  );
}
```

- [ ] **Step 3: 在 tool_call 条目中添加 HoverKLineIcon**

找到 tool_call 渲染中的标题行 `<div className="flex items-center gap-1.5">`，在 `</div>` 关闭前、`{status === "error"` 之前添加：

```tsx
{status === "done" && hasResult && item.result!.chartData && (
  <HoverKLineIcon chartData={item.result!.chartData} />
)}
```

- [ ] **Step 4: 在 tool_result fallback 中也添加 HoverKLineIcon**

找到 tool_result 独立渲染分支中的标题行，在合适位置添加同样的 HoverKLineIcon：

```tsx
{item.data.chartData && (
  <HoverKLineIcon chartData={item.data.chartData} />
)}
```

- [ ] **Step 5: Commit**

```bash
git add web/components/expert/ThinkingPanel.tsx
git commit -m "feat: ThinkingPanel 集成 K 线 hover 浮窗"
```

### Task 6: 验证

- [ ] **Step 1: 重启后端**

```bash
kill $(lsof -ti :8000); cd engine && .venv/bin/python main.py &
```

- [ ] **Step 2: 验证专家对话**

打开 http://localhost:3000/expert，选择数据专家，发送 "查询贵州茅台近60天历史行情"。确认：
- ThinkingPanel 中 query_history 条目完成后显示 📈 图标
- hover 图标 300ms 后浮现 K 线小窗
- 小窗显示蜡烛图 + 成交量
- 鼠标移走后小窗消失
- A 股配色：红涨绿跌
