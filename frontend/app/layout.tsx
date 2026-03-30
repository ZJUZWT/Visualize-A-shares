import type { Metadata } from "next";
import { Toaster } from "sonner";
import ConnectionGuard from "@/components/ConnectionGuard";
import "./globals.css";

export const metadata: Metadata = {
  title: "StockScape — A股 AI 投研平台",
  description: "A股多维聚类3D地形可视化平台",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="antialiased">
        <ConnectionGuard>
          {children}
        </ConnectionGuard>
        <Toaster richColors position="top-right" />
      </body>
    </html>
  );
}
