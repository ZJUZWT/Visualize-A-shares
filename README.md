# 🏔️ StockTerrain

> A股多维聚类 3D 地形可视化平台
> *Data is the terrain. Market is the landscape.*

将 A股 5000+ 支股票映射为实时动态 **3D 地形图**。相似股票在空间上自然聚合，涨跌幅化为地形的高低起伏。

---

## 部署教程

### 场景一：仅查看导出的辩论报告（纯前端）

如果你收到了一份 `debate-*.html` 导出文件，**不需要部署任何服务**，直接双击用浏览器打开即可。文件完全自包含，离线可用。

---

### 场景二：完整部署（前端 + 后端）

#### 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | >= 3.11 |
| Node.js | >= 20 |
| npm / pnpm / yarn | 任意 |
| Redis | 可选，不配置时退化为内存缓存 |

#### 1. 克隆仓库

```bash
git clone <repo-url>
cd stockterrain
```

#### 2. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填写 LLM 配置（辩论/分析功能必填，3D 地形功能不需要）：

```env
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible   # 或 anthropic
LLM_API_KEY=sk-...               # 你的 API Key

# 按实际厂商填写 Base URL：
# OpenAI:   https://api.openai.com/v1
# DeepSeek: https://api.deepseek.com/v1
# 通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1
# Kimi:     https://api.moonshot.cn/v1
# Anthropic: https://api.anthropic.com
LLM_BASE_URL=https://api.openai.com/v1

LLM_MODEL=gpt-4o-mini
```

#### 3. 启动后端

```bash
cd engine

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows

# 安装依赖（首次约 2~5 分钟，含 torch/sentence-transformers）
pip install -e "." -i https://pypi.tuna.tsinghua.edu.cn/simple

# 启动
python main.py
# → http://localhost:8000
# → API 文档: http://localhost:8000/docs
```

> **注意：** `torch` + `sentence-transformers` 约 2GB，仅重建 BGE 嵌入时需要。
> 如果只用辩论/分析功能，可以先跳过，等报错再装。

#### 4. 启动前端

```bash
cd web

npm install

# 开发模式
npm run dev
# → http://localhost:3000

# 或生产构建
npm run build
npm start
```

前端默认通过 Next.js rewrites 将 `/api/*` 代理到 `http://localhost:8000`，无需额外配置。

#### 5. 验证

打开 `http://localhost:3000`，后端健康检查：

```bash
curl http://localhost:8000/api/v1/health
```

---

### 场景三：仅部署前端（只看 3D 地形，不用 AI 功能）

前端可以独立运行，但 3D 地形数据、辩论等功能需要后端。如果只想静态部署前端页面：

```bash
cd web
GITHUB_PAGES=true npm run build   # 生成静态文件到 out/
```

将 `out/` 目录部署到任意静态托管（Vercel、Nginx、GitHub Pages 等）。

> 静态模式下 API 调用不可用，辩论/分析/地形计算均无法使用。

---

### 生产部署建议

**后端（Linux 服务器）：**

```bash
# 关闭 reload，绑定公网地址
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2

# 或用 systemd / supervisor 管理进程
```

修改 `engine/config.py` 中的 CORS 配置，将前端域名加入白名单：

```python
cors_origins: list[str] = ["https://your-frontend-domain.com"]
```

**前端（Vercel / 自托管）：**

```bash
npm run build && npm start
```

设置环境变量 `NEXT_PUBLIC_API_BASE=https://your-backend-domain.com`，前端会用它替代默认的 `http://localhost:8000`。

---

## 架构

```
stockterrain/
├── engine/                # Python 后端 (FastAPI + Uvicorn)
│   ├── data_engine/       #   行情数据 (AKShare + BaoStock)
│   ├── cluster_engine/    #   聚类算法 (HDBSCAN + UMAP + RBF)
│   ├── quant_engine/      #   量化因子 (13因子 + 技术指标)
│   ├── info_engine/       #   信息引擎 (新闻 + 公告 + 情感)
│   ├── agent/             #   辩论 Agent (多角色 + 黑板)
│   ├── llm/               #   LLM 接入层
│   ├── mcpserver/         #   MCP Server (stdio)
│   └── main.py            #   应用入口
│
├── web/                   # Next.js 15 前端
│   ├── components/        #   UI 组件 (3D 地形 + 辩论页)
│   ├── stores/            #   Zustand 状态管理
│   └── lib/               #   工具函数 (含导出 HTML)
│
├── data/                  # 本地数据
│   └── stockterrain.duckdb  # DuckDB 单文件数据库
│
└── .env                   # LLM 配置（从 .env.example 复制）
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 数据源 | AKShare + BaoStock |
| 后端 | FastAPI + Uvicorn |
| 算法 | HDBSCAN + UMAP + RBF 插值 |
| 存储 | DuckDB + Redis（可选） |
| 前端 | React 19 + Next.js 15 + TypeScript |
| 3D 渲染 | React Three Fiber + drei + GLSL |
| 状态 | Zustand |
| 样式 | Tailwind CSS v4 |

## License

MIT
