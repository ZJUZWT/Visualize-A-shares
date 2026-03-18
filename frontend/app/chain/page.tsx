"use client";

import NavSidebar from "@/components/ui/NavSidebar";
import ChainToolbar from "@/components/chain/ChainToolbar";
import ChainStatusBar from "@/components/chain/ChainStatusBar";
import ChainLegend from "@/components/chain/ChainLegend";
import NodeDetail from "@/components/chain/NodeDetail";
import dynamic from "next/dynamic";

const ChainGraph = dynamic(() => import("@/components/chain/ChainGraph"), {
  ssr: false,
});

export default function ChainPageRoute() {
  return (
    <main
      className="debate-dark relative h-screen flex flex-col overflow-hidden"
      style={{
        marginLeft: 48,
        width: "calc(100vw - 48px)",
        background: "var(--bg-primary)",
      }}
    >
      <NavSidebar />

      {/* 顶部搜索栏 */}
      <ChainToolbar />

      {/* 图谱区域 + 详情面板 */}
      <div className="flex-1 relative overflow-hidden">
        <ChainLegend />
        <ChainGraph />
        <NodeDetail />
      </div>

      {/* 底部状态栏 */}
      <ChainStatusBar />
    </main>
  );
}
