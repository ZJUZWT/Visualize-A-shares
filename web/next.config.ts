import type { NextConfig } from "next";

const isGHPages = process.env.GITHUB_PAGES === "true";
const repoName = "/Visualize-A-shares";

const nextConfig: NextConfig = {
  // GitHub Pages 静态导出
  ...(isGHPages && {
    output: "export",
    basePath: repoName,
    assetPrefix: repoName,
    images: { unoptimized: true },
  }),

  // 支持 GLSL shader 文件导入
  webpack: (config) => {
    config.module.rules.push({
      test: /\.(glsl|vs|fs|vert|frag)$/,
      use: ["raw-loader"],
    });
    return config;
  },

  // 后端 API 代理（仅开发/动态模式生效，静态导出时忽略）
  ...(!isGHPages && {
    async rewrites() {
      return [
        {
          source: "/api/:path*",
          destination: "http://localhost:8000/api/:path*",
        },
      ];
    },
  }),
};

export default nextConfig;
