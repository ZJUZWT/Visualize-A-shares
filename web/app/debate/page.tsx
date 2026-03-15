"use client";

import NavSidebar from "@/components/ui/NavSidebar";
import DebatePage from "@/components/debate/DebatePage";

export default function DebatePageRoute() {
  return (
    <main className="relative w-screen h-screen overflow-hidden bg-[var(--bg-primary)] ml-12 flex flex-col">
      <NavSidebar />
      <DebatePage />
    </main>
  );
}
