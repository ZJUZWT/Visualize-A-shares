"use client";

import NavSidebar from "@/components/ui/NavSidebar";
import { TaskManager } from "@/components/tasks/TaskManager";

export default function TasksPageRoute() {
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
      <TaskManager />
    </main>
  );
}
