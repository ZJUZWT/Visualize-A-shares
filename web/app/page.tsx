"use client";

/**
 * StockTerrain v3.0 主页面
 *
 * 支持两种模式:
 * - 动态模式: 连接后端 API 实时计算
 * - 静态模式: 加载预计算快照（GitHub Pages）
 */

import { useEffect } from "react";
import dynamic from "next/dynamic";
import Sidebar from "@/components/ui/Sidebar";
import TopBar from "@/components/ui/TopBar";
import RelatedStocksPanel from "@/components/ui/RelatedStocksPanel";
import AIChatPanel from "@/components/ui/AIChatPanel";
import { useTerrainStore } from "@/stores/useTerrainStore";

const TerrainScene = dynamic(
  () => import("@/components/canvas/TerrainScene"),
  {
    ssr: false,
    loading: () => <LoadingScreen />,
  }
);

export default function Home() {
  const { isStaticMode, terrainData, loadSnapshot } = useTerrainStore();

  // 静态模式下自动加载快照
  useEffect(() => {
    if (isStaticMode && !terrainData) {
      loadSnapshot();
    }
  }, [isStaticMode, terrainData, loadSnapshot]);
  return (
    <main className="relative w-screen h-screen overflow-hidden bg-transparent">
      {/* Layer 0: 3D 场景 */}
      <TerrainScene />

      {/* Layer 1: UI 覆盖层 */}
      <Sidebar />
      <TopBar />
      <RelatedStocksPanel />
      <AIChatPanel />

      {/* Layer 2: 底部版权 */}
      <div className="overlay fixed bottom-3 right-4">
        <span className="text-[10px] text-[var(--text-tertiary)] font-mono">
          StockTerrain v3.1 · Data is the terrain
        </span>
      </div>
    </main>
  );
}

function LoadingScreen() {
  return (
    <div className="fixed inset-0 bg-[#F8FAFE] flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE] flex items-center justify-center text-white text-xl font-bold mx-auto mb-4 shadow-lg loading-pulse">
          T
        </div>
        <div className="text-sm font-medium text-[var(--text-primary)] mb-1">
          StockTerrain
        </div>
        <div className="text-xs text-[var(--text-tertiary)]">
          渲染引擎初始化中...
        </div>
      </div>
    </div>
  );
}
