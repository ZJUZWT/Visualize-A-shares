"use client";

import { useEffect, useRef } from "react";
import { useSectorStore } from "@/stores/useSectorStore";
import { createChart, CandlestickSeries, HistogramSeries, type IChartApi } from "lightweight-charts";

/** 将各种日期格式统一为 YYYY-MM-DD */
function normalizeDate(raw: string): string {
  if (!raw) return "";
  // 只取前10位（处理 "2026-03-17 00:00:00" 等带时间的格式）
  const d = raw.slice(0, 10);
  // 确保是 YYYY-MM-DD 格式
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return d;
  // 处理 YYYYMMDD 格式
  if (/^\d{8}$/.test(d)) return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  return d;
}

export function SectorTrendChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const { history, fundFlowHistory } = useSectorStore();

  useEffect(() => {
    if (!containerRef.current) return;

    // 清理旧图表
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    if (history.length === 0) return;

    try {
      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 280,
        layout: {
          background: { color: "transparent" },
          textColor: "#94a3b8",
          fontSize: 10,
        },
        grid: {
          vertLines: { color: "#1e293b" },
          horzLines: { color: "#1e293b" },
        },
        timeScale: {
          borderColor: "#334155",
          timeVisible: false,
        },
        rightPriceScale: {
          borderColor: "#334155",
        },
        crosshair: {
          horzLine: { color: "#475569" },
          vertLine: { color: "#475569" },
        },
      });
      chartRef.current = chart;

      // K 线 — 确保日期格式正确、排序、去重
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: "#ef4444",
        downColor: "#22c55e",
        borderUpColor: "#ef4444",
        borderDownColor: "#22c55e",
        wickUpColor: "#ef4444",
        wickDownColor: "#22c55e",
      });

      const seenDates = new Set<string>();
      const klineData = history
        .map((item) => {
          const time = normalizeDate(item.date);
          return { time, open: item.open, high: item.high, low: item.low, close: item.close };
        })
        .filter((d) => {
          if (!d.time || seenDates.has(d.time)) return false;
          seenDates.add(d.time);
          return true;
        })
        .sort((a, b) => a.time.localeCompare(b.time));

      if (klineData.length > 0) {
        candleSeries.setData(klineData as never);
      }

      // 资金流柱状图（如果有数据）
      if (fundFlowHistory.length > 0) {
        const volumeSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: "volume" },
          priceScaleId: "flow",
        });

        chart.priceScale("flow").applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });

        const flowSeen = new Set<string>();
        const flowData = fundFlowHistory
          .map((item) => {
            const time = normalizeDate(item.date);
            return {
              time,
              value: item.main_force_net_inflow,
              color: item.main_force_net_inflow >= 0 ? "#ef444480" : "#22c55e80",
            };
          })
          .filter((d) => {
            if (!d.time || flowSeen.has(d.time)) return false;
            flowSeen.add(d.time);
            return true;
          })
          .sort((a, b) => a.time.localeCompare(b.time));

        if (flowData.length > 0) {
          volumeSeries.setData(flowData as never);
        }
      }

      chart.timeScale().fitContent();

      // 响应式
      const resizeObserver = new ResizeObserver(() => {
        if (containerRef.current && chartRef.current) {
          chartRef.current.applyOptions({
            width: containerRef.current.clientWidth,
          });
        }
      });
      resizeObserver.observe(containerRef.current);

      return () => {
        resizeObserver.disconnect();
        chart.remove();
        chartRef.current = null;
      };
    } catch (err) {
      console.error("SectorTrendChart 渲染失败:", err);
    }
  }, [history, fundFlowHistory]);

  if (history.length === 0) {
    return (
      <div className="flex items-center justify-center h-[280px] text-xs text-[var(--text-tertiary)]">
        暂无历史数据
      </div>
    );
  }

  return <div ref={containerRef} />;
}
