"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Mountain, Scale } from "lucide-react";

const NAV_ITEMS = [
  { href: "/", icon: Mountain, label: "地形图" },
  { href: "/debate", icon: Scale, label: "专家辩论" },
];

export default function NavSidebar() {
  const pathname = usePathname();

  return (
    <nav
      className="nav-sidebar fixed left-0 top-0 h-screen z-50 flex flex-col py-4 gap-1
                 bg-[var(--bg-secondary)] border-r border-[var(--border)]
                 overflow-hidden"
      style={{ width: 48 }}
    >
      <div className="flex items-center justify-center h-10 mb-2 shrink-0">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#4F8EF7] to-[#7B68EE]
                        flex items-center justify-center text-white text-xs font-bold">
          T
        </div>
        <span className="nav-label ml-2 text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap opacity-0">
          StockTerrain
        </span>
      </div>

      {NAV_ITEMS.map(({ href, icon: Icon, label }) => {
        const active = pathname === href;
        return (
          <Link
            key={href}
            href={href}
            className={`nav-item flex items-center gap-3 mx-2 px-2 py-2 rounded-lg
                        transition-colors duration-150 shrink-0
                        ${active
                          ? "bg-[var(--accent-light)] text-[var(--accent)]"
                          : "text-[var(--text-secondary)] hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]"
                        }`}
          >
            <Icon size={18} className="shrink-0" />
            <span className="nav-label text-sm font-medium whitespace-nowrap opacity-0">
              {label}
            </span>
          </Link>
        );
      })}

      <style jsx>{`
        .nav-sidebar {
          transition: width 200ms cubic-bezier(0.16, 1, 0.3, 1);
        }
        .nav-sidebar:hover {
          width: 180px !important;
        }
        .nav-sidebar:hover .nav-label {
          opacity: 1;
          transition: opacity 150ms ease 80ms;
        }
        .nav-label {
          transition: opacity 100ms ease;
        }
      `}</style>
    </nav>
  );
}
