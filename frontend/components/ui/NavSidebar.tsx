"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mountain, Scale, BrainCircuit, TrendingUp, ClipboardList, GitBranch, FileText, Bot, LogOut, User, AlertTriangle } from "lucide-react";
import { useConnectionStore } from "@/stores/useConnectionStore";

const NAV_ITEMS = [
  { href: "/", icon: Mountain, label: "地形图", feature: "terrain" },
  { href: "/debate", icon: Scale, label: "专家辩论", feature: "debate" },
  { href: "/expert", icon: BrainCircuit, label: "投资专家", feature: "expert" },
  { href: "/admin/feedback", icon: AlertTriangle, label: "反馈后台", feature: "expert", adminOnly: true },
  { href: "/plans", icon: FileText, label: "交易计划", feature: "plans" },
  { href: "/agent", icon: Bot, label: "Agent", feature: "agent" },
  { href: "/tasks", icon: ClipboardList, label: "事务管理", feature: "tasks" },
  { href: "/sector", icon: TrendingUp, label: "板块研究", feature: "sector" },
  { href: "/chain", icon: GitBranch, label: "产业链图谱", feature: "chain" },
];

export default function NavSidebar() {
  const pathname = usePathname();
  const features = useConnectionStore((s) => s.features);
  const userId = useConnectionStore((s) => s.userId);
  const username = useConnectionStore((s) => s.username);
  const logout = useConnectionStore((s) => s.logout);

  // features 为 null（未加载）→ 全部显示；后端明确返回 false → 隐藏
  const visibleItems = NAV_ITEMS.filter(
    (item) => {
      if (item.adminOnly && userId !== "Admin") {
        return false;
      }
      return !features || features[item.feature] !== false;
    }
  );

  return (
    <nav
      className="group fixed left-0 top-0 h-screen z-50 flex flex-col py-4 gap-2
                 bg-[var(--bg-secondary)] border-r border-[var(--border)]
                 overflow-hidden transition-[width] duration-200 ease-out"
      style={{ width: 48 }}
      onMouseEnter={e => (e.currentTarget.style.width = "180px")}
      onMouseLeave={e => (e.currentTarget.style.width = "48px")}
    >
      <div className="flex items-center h-10 mb-1 shrink-0 px-0">
        <span className="flex items-center justify-center shrink-0" style={{width: 48, height: 48}}>
          <Mountain size={20} className="text-[#4F8EF7]" />
        </span>
        <span className="ml-1 text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap
                         opacity-0 group-hover:opacity-100 transition-opacity duration-150 delay-75">
          StockScape
        </span>
      </div>

      {visibleItems.map(({ href, icon: Icon, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`flex items-center shrink-0
                        transition-colors duration-150
                        ${active
                          ? "bg-[var(--accent-light)] text-[var(--accent)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]"
                        }`}
          >
            <span className="flex items-center justify-center shrink-0" style={{width: 48, height: 48}}>
              <Icon size={22} />
            </span>
            <span className="text-sm font-medium whitespace-nowrap pr-4
                             opacity-0 group-hover:opacity-100 transition-opacity duration-150 delay-75">
              {label}
            </span>
          </Link>
        );
      })}

      {/* 底部用户信息 */}
      <div className="mt-auto">
        <div className="border-t border-[var(--border)] mx-2 mb-2" />
        {username ? (
          <div className="flex items-center shrink-0 text-[var(--text-secondary)]">
            <span className="flex items-center justify-center shrink-0" style={{width: 48, height: 48}}>
              <User size={18} />
            </span>
            <span className="text-xs font-medium whitespace-nowrap
                             opacity-0 group-hover:opacity-100 transition-opacity duration-150 delay-75"
                  style={{ maxWidth: 80, overflow: "hidden", textOverflow: "ellipsis" }}>
              {username}
            </span>
            <button
              onClick={logout}
              className="ml-auto mr-2 p-1 rounded hover:bg-[var(--bg-primary)]
                         opacity-0 group-hover:opacity-100 transition-opacity duration-150 delay-75"
              title="退出登录"
            >
              <LogOut size={14} />
            </button>
          </div>
        ) : (
          <div className="flex items-center shrink-0 text-[var(--text-tertiary)]">
            <span className="flex items-center justify-center shrink-0" style={{width: 48, height: 48}}>
              <User size={18} />
            </span>
            <span className="text-xs whitespace-nowrap
                             opacity-0 group-hover:opacity-100 transition-opacity duration-150 delay-75">
              匿名
            </span>
          </div>
        )}
      </div>
    </nav>
  );
}
