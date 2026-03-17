"use client";

import { useEffect, useRef } from "react";
import { useSectorStore } from "@/stores/useSectorStore";
import { createChart, type IChartApi } from "lightweight-charts";

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

    // K 线
    const candleSeries = chart.addCandlestickSeries({
      upColor: "#ef4444",
      downColor: "#22c55e",
      borderUpColor: "#ef4444",
      borderDownColor: "#22c55e",
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
    });

    const klineData = history.map((item) => ({
      time: item.date.replace(/-/g, "-"),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
    candleSeries.setData(klineData as never);

    // 资金流柱状图（如果有数据）
    if (fundFlowHistory.length > 0) {
      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "flow",
      });

      chart.priceScale("flow").applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });

      const flowData = fundFlowHistory.map((item) => ({
        time: item.date.replace(/-/g, "-"),
        value: item.main_force_net_inflow,
        color: item.main_force_net_inflow >= 0 ? "#ef444480" : "#22c55e80",
      }));
      volumeSeries.setData(flowData as never);
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
