"use client";

import { useEffect } from "react";
import { useConnectionStore } from "@/stores/useConnectionStore";
import ConnectPage from "@/components/ConnectPage";
import { Loader2 } from "lucide-react";

/**
 * 连接守卫 — 确保前端已连接后端后才渲染主界面
 *
 * 跳过条件:
 * - NEXT_PUBLIC_API_BASE 已设置 → 开发/Docker 模式，直接放行
 *
 * 流程:
 * 1. 无 serverUrl → 显示连接页
 * 2. 有 serverUrl 但未 connected → 自动 bootstrap
 * 3. bootstrap 成功（JWT 有效或 anonymous） → 渲染 children
 * 4. bootstrap 失败（token 过期） → 清除状态，显示 ConnectPage
 */
export default function ConnectionGuard({ children }: { children: React.ReactNode }) {
  const { connected, loading, serverUrl, token, userId, bootstrap } = useConnectionStore();

  // 环境变量已配置 → 跳过连接页（开发/Docker 模式）
  const envConfigured = !!(
    process.env.NEXT_PUBLIC_API_BASE || process.env.NEXT_PUBLIC_API_URL
  );

  // 自动恢复连接：有 token 或 anonymous userId 时尝试 bootstrap
  useEffect(() => {
    if (envConfigured) return;
    if (!connected && serverUrl && (token || userId === "anonymous") && !loading) {
      bootstrap();
    }
  }, [envConfigured, connected, serverUrl, token, userId, loading, bootstrap]);

  // 环境变量已配置 → 直接放行
  if (envConfigured) return <>{children}</>;

  // 正在连接中
  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--bg-primary)",
        }}
      >
        <Loader2
          size={32}
          style={{
            color: "var(--accent)",
            animation: "spin 1s linear infinite",
          }}
        />
        <style>{`
          @keyframes spin {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    );
  }

  // 未连接 → 显示连接页
  if (!connected) return <ConnectPage />;

  // 已连接 → 正常渲染
  return <>{children}</>;
}
