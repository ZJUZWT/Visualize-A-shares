"use client";

import NavSidebar from "@/components/ui/NavSidebar";
import DebatePage from "@/components/debate/DebatePage";

export default function DebatePageRoute() {
  return (
    <main
      className="relative h-screen bg-[var(--bg-primary)] flex flex-col"
      style={{marginLeft: 48, width: 'calc(100vw - 48px)', padding: '16px 20px 24px 20px'}}
    >
      <NavSidebar />
      <DebatePage />
    </main>
  );
}
