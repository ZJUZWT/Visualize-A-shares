"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mountain, Scale, BrainCircuit, TrendingUp, ClipboardList } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", icon: Mountain, label: "地形图" },
  { href: "/debate", icon: Scale, label: "专家辩论" },
  { href: "/expert", icon: BrainCircuit, label: "投资专家" },
  { href: "/tasks", icon: ClipboardList, label: "事务管理" },
  { href: "/sector", icon: TrendingUp, label: "板块研究" },
];

export default function NavSidebar() {
  const pathname = usePathname();

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

      {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
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
    </nav>
  );
}
