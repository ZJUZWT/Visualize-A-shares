"use client";

import { useEffect } from "react";
import NavSidebar from "@/components/ui/NavSidebar";
import { SectorDashboard } from "@/components/sector/SectorDashboard";
import { useSectorStore } from "@/stores/useSectorStore";

export default function SectorPageRoute() {
  const { loadBoards, loadHeatmap, loadRotation } = useSectorStore();

  useEffect(() => {
    loadBoards();
    loadHeatmap();
    loadRotation();
  }, [loadBoards, loadHeatmap, loadRotation]);

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
      <SectorDashboard />
    </main>
  );
}
