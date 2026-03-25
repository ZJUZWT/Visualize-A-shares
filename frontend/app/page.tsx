"use client";

/**
 * StockScape v3.0 主页面
 *
 * 支持两种模式:
 * - 动态模式: 连接后端 API 实时计算
 * - 静态模式: 加载预计算快照（GitHub Pages）
 */

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Sidebar from "@/components/ui/Sidebar";
import TopBar from "@/components/ui/TopBar";
import RelatedStocksPanel from "@/components/ui/RelatedStocksPanel";
import AIChatPanel from "@/components/ui/AIChatPanel";
import AnalysisPanel from "@/components/ui/AnalysisPanel";
import { useTerrainStore } from "@/stores/useTerrainStore";
import NavSidebar from "@/components/ui/NavSidebar";
import { canUseWebGL } from "@/lib/webglSupport";

const TerrainScene = dynamic(
  () => import("@/components/canvas/TerrainScene"),
  {
    ssr: false,
    loading: () => <LoadingScreen />,
  }
);

export default function Home() {
  const { isStaticMode, terrainData, loadSnapshot } = useTerrainStore();
  const [webglStatus, setWebglStatus] = useState<"checking" | "supported" | "unsupported">("checking");

  // 静态模式下自动加载快照
  useEffect(() => {
    if (isStaticMode && !terrainData) {
      loadSnapshot();
    }
  }, [isStaticMode, terrainData, loadSnapshot]);

  useEffect(() => {
    setWebglStatus(canUseWebGL(typeof document === "undefined" ? null : document) ? "supported" : "unsupported");
  }, []);

  return (
    <main className="relative w-screen h-screen overflow-hidden bg-transparent">
      <NavSidebar />
      {/* Layer 0: 3D 场景 */}
      {webglStatus === "supported" ? (
        <TerrainScene />
      ) : (
        <TerrainFallback unsupported={webglStatus === "unsupported"} />
      )}

      {/* Layer 1: UI 覆盖层 */}
      <Sidebar />
      <TopBar />
      <RelatedStocksPanel />
      <AIChatPanel />
      <AnalysisPanel />

      {/* Layer 2: 底部版权 */}
      <div className="overlay fixed bottom-3 right-4">
        <span className="text-[10px] text-[var(--text-tertiary)] font-mono">
          StockScape v3.1 · Data is the terrain
        </span>
      </div>
    </main>
  );
}

function TerrainFallback({ unsupported }: { unsupported: boolean }) {
  return (
    <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,#eef4fb_0%,#dde8f4_45%,#cfdbe8_100%)]">
      {unsupported && (
        <div className="overlay absolute bottom-6 left-20 rounded-2xl border border-white/60 bg-white/75 px-4 py-3 text-xs text-slate-600 shadow-[0_18px_50px_rgba(15,23,42,0.08)] backdrop-blur">
          当前环境不支持 3D WebGL，已切换为简化视图。
        </div>
      )}
    </div>
  );
}

function LoadingScreen() {
  return (
    <div className="fixed inset-0 bg-[#F8FAFE] flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE] flex items-center justify-center text-white text-xl font-bold mx-auto mb-4 shadow-lg loading-pulse">
          S
        </div>
        <div className="text-sm font-medium text-[var(--text-primary)] mb-1">
          StockScape
        </div>
        <div className="text-xs text-[var(--text-tertiary)]">
          渲染引擎初始化中...
        </div>
      </div>
    </div>
  );
}
