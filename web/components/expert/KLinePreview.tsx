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
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155" },
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

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    candleSeries.setData(candleData as any);
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
