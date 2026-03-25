# StockScape 部署清单

> A股 AI 投研平台 — 部署与依赖文档  
> 最后更新：2026-03-17

---

## 一、环境要求

| 项目 | 最低版本 | 推荐版本 | 说明 |
|------|---------|---------|------|
| **操作系统** | Linux / macOS | Ubuntu 22.04+ / macOS 14+ | Windows 未测试 |
| **Node.js** | 20.x | 22.x LTS | 前端构建运行 |
| **npm** | 10.x | 随 Node.js | 包管理 |
| **Python** | 3.11 | 3.12 | 后端引擎 |
| **pip** | 23.0+ | 最新 | Python 包管理 |
| **Git** | 2.30+ | 最新 | 版本控制 |
| **Git LFS** | 3.0+ | 最新 | 大文件存储（嵌入向量等） |
| **Docker** | 24.0+ | 最新 | 可选，容器化部署 |

### 可选组件

| 组件 | 版本 | 说明 |
|------|------|------|
| Redis | >= 5.0 | 数据缓存（不启用则退化为内存缓存） |
| CUDA | >= 11.8 | GPU 加速嵌入编码（无 GPU 时 CPU 回退） |

---

## 二、项目结构

```
Visualize-A-shares/
├── backend/                    # Python 后端（FastAPI）
│   ├── main.py                 # 入口 — uvicorn 启动
│   ├── config.py               # 全局配置（统一路径入口）
│   ├── pyproject.toml          # Python 依赖声明
│   ├── engine/                 # 领域引擎
│   │   ├── data/               # 数据引擎（行情、持久化）
│   │   ├── cluster/            # 聚类引擎（UMAP / HDBSCAN / RBF）
│   │   │   ├── algorithm/      # 算法核心
│   │   │   └── preprocess/     # 预处理脚本
│   │   ├── quant/              # 量化引擎（因子、技术指标）
│   │   ├── info/               # 信息引擎（新闻、公告、情感）
│   │   ├── industry/           # 行业引擎（认知、资本结构）
│   │   ├── expert/             # 专家引擎（多专家并行）
│   │   └── arena/              # 辩论引擎（多角色 + 黑板）
│   │       └── rag/            # RAG 检索增强
│   ├── api/                    # REST API 路由
│   ├── llm/                    # LLM 接入层
│   └── mcpserver/              # MCP Server
├── frontend/                   # Next.js 前端
│   ├── package.json            # 前端依赖声明
│   ├── next.config.ts          # Next.js 配置 + API 代理
│   ├── app/                    # 页面路由
│   ├── components/             # React / Three.js 组件
│   ├── stores/                 # Zustand 状态管理
│   └── types/                  # TypeScript 类型定义
├── data/
│   └── precomputed/            # ★ 预计算数据（需提交到仓库）
│       ├── company_profiles.json   # 公司概况（~5 MB）
│       ├── stock_embeddings.npz    # 语义嵌入（~15 MB）
│       └── precompute_meta.json    # 元信息
├── tests/
│   ├── unit/                   # 单元测试
│   └── integration/            # 集成测试
├── scripts/
│   ├── setup.sh / setup.bat    # 一键配置环境
│   └── start.sh / start.bat    # 一键启动服务
├── docker-compose.yml          # Docker 编排
└── DEPLOYMENT.md               # 本文件
```

---

## 三、后端 Python 依赖

> 声明文件：`backend/pyproject.toml`  
> 安装方式：`cd backend && pip install -e .`（或 `pip install -e ".[dev]"` 含开发依赖）

### 3.1 运行时依赖

| 分类 | 包名 | 版本要求 | 用途 |
|------|------|---------|------|
| **Web 框架** | fastapi | >= 0.115.0 | REST API 服务 |
| | uvicorn[standard] | >= 0.32.0 | ASGI 服务器 |
| | websockets | >= 13.0 | WebSocket 支持 |
| **数据采集** | akshare | >= 1.14.0 | A股行情/财务数据 |
| | baostock | >= 0.8.8 | 证券数据接口（备用源） |
| **数据处理** | pandas | >= 2.2.0 | 数据表操作 |
| | numpy | >= 1.26.0 | 数值计算 |
| | duckdb | >= 1.1.0 | 嵌入式 OLAP 数据库 |
| **机器学习** | scikit-learn | >= 1.5.0 | 特征处理 / PCA |
| | hdbscan | >= 0.8.38 | 密度聚类 |
| | umap-learn | >= 0.5.6 | 高维降维 (UMAP) |
| | scipy | >= 1.14.0 | RBF 插值 / 科学计算 |
| **缓存 & 调度** | redis | >= 5.0.0 | 缓存层（可选） |
| | apscheduler | >= 3.10.0 | 定时任务调度 |
| **NLP / 嵌入** | sentence-transformers | >= 3.0.0 | 文本向量化框架 |
| | torch | >= 2.0.0 | PyTorch 深度学习 |
| **工具** | pydantic | >= 2.9.0 | 数据校验 / Schema |
| | loguru | >= 0.7.0 | 日志框架 |
| | httpx | >= 0.27.0 | 异步 HTTP 客户端 |

### 3.2 开发依赖（可选）

| 包名 | 版本要求 | 用途 |
|------|---------|------|
| pytest | >= 8.0.0 | 单元测试 |
| pytest-asyncio | >= 0.24.0 | 异步测试支持 |
| ruff | >= 0.8.0 | 代码格式化 / Lint |

### 3.3 构建系统

| 项 | 值 |
|----|---|
| 构建后端 | hatchling |
| Python 版本 | >= 3.11 |
| Ruff line-length | 100 |
| Ruff target-version | py311 |

---

## 四、前端 Node.js 依赖

> 声明文件：`frontend/package.json`  
> 安装方式：`cd frontend && npm install`

### 4.1 运行时依赖

| 分类 | 包名 | 版本要求 | 用途 |
|------|------|---------|------|
| **框架** | next | ^15.1.0 | React 全栈框架 |
| | react | ^19.0.0 | UI 库 |
| | react-dom | ^19.0.0 | DOM 渲染 |
| **3D 渲染** | three | ^0.170.0 | WebGL 3D 引擎 |
| | @react-three/fiber | ^9.0.0 | React ↔ Three.js 桥接 |
| | @react-three/drei | ^10.0.0 | Three.js 常用工具集 |
| | @react-three/postprocessing | ^3.0.0 | 后处理效果（Bloom 等） |
| **状态管理** | zustand | ^5.0.0 | 轻量状态管理 |
| **动画** | framer-motion | ^11.0.0 | UI 动画 |
| **工具** | lucide-react | latest | 图标库 |
| | clsx | ^2.1.0 | className 合并 |
| **类型** | @types/three | ^0.170.0 | Three.js 类型定义 |

### 4.2 开发依赖

| 包名 | 版本要求 | 用途 |
|------|---------|------|
| typescript | ^5.7.0 | 类型系统 |
| @types/react | ^19.0.0 | React 类型 |
| @types/react-dom | ^19.0.0 | ReactDOM 类型 |
| @types/node | ^22.0.0 | Node.js 类型 |
| tailwindcss | ^4.0.0 | CSS 框架 |
| @tailwindcss/postcss | ^4.0.0 | TailwindCSS PostCSS 插件 |
| postcss | ^8.4.0 | CSS 处理工具链 |
| eslint | ^9.0.0 | 代码检查 |
| eslint-config-next | ^15.1.0 | Next.js ESLint 规则 |

### 4.3 前端配置要点

- **API 代理**：`next.config.ts` 中 `/api/*` 请求代理到 `http://localhost:8000/api/*`
- **Shader 支持**：GLSL 文件通过 raw-loader 导入
- **PostCSS**：TailwindCSS v4 通过 `@tailwindcss/postcss` 插件集成

---

## 五、预计算数据

> 目录：`data/precomputed/`  
> **这些文件已纳入版本控制，部署时无需重新生成。**

| 文件 | 大小 | 说明 |
|------|------|------|
| `company_profiles.json` | ~5 MB | 全市场 5516 只股票的公司概况（代码、名称、行业、经营范围） |
| `stock_embeddings.npz` | ~15 MB | BGE 语义嵌入矩阵（5516 × 768 维） |
| `precompute_meta.json` | <1 KB | 元信息（版本、股票数、嵌入维度、模型名等） |

### 5.1 嵌入模型信息

| 项 | 值 |
|----|---|
| 模型 | `BAAI/bge-base-zh-v1.5` |
| 维度 | 768 |
| 模型大小 | ~390 MB（首次运行自动从 HuggingFace 下载） |

### 5.2 重新生成预计算数据（仅开发时需要）

如需更新股票数据或重新编码嵌入：

```bash
# 完整流程：获取全市场股票 → 爬取公司概况 → 生成嵌入
cd backend
python -m engine.cluster.preprocess.build_embeddings

# 快速重建：仅用已有概况重新编码嵌入（跳过爬取）
cd backend
python -m engine.cluster.preprocess.rebuild_bge
```

**降级策略**（无 GPU / 无法下载模型时）：
1. 首选：`BAAI/bge-base-zh-v1.5`（768 维，需 PyTorch）
2. 备选：`shibing624/text2vec-base-chinese`（384 维）
3. 保底：TF-IDF + SVD（256 维，纯 CPU，无需额外模型）

---

## 六、服务端口与启动

### 6.1 一键启动（推荐）

```bash
# macOS / Linux
scripts/setup.sh     # 首次：配置环境
scripts/start.sh     # 启动所有服务

# Windows
scripts\setup.bat
scripts\start.bat
```

### 6.2 Docker Compose（本地）

```bash
cp .env.example .env
# 编辑 .env 填入 API Key
docker compose up
```

| 服务 | 端口 | 说明 |
|------|------|------|
| backend | 8000 | FastAPI + Uvicorn |
| frontend | 3000 | Next.js Production Server |

### 6.3 生产部署（推荐）

```bash
cp .env.production.example .env.production
# 修改域名、CORS、LLM API Key、Tunnel Token（如使用）

docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

生产拓扑：

- `backend`：FastAPI + Uvicorn
- `frontend`：Next.js 生产构建
- `nginx`：统一反向代理 `/` 与 `/api`
- `cloudflared`：可选 profile，用于免公网 IP 暴露服务

#### 可选：Cloudflare Tunnel

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml --profile tunnel up -d
```

Tunnel 配置示例文件：

- `deploy/cloudflared/config.yml.example`

#### Nginx 与 SSL

- 主配置：`deploy/nginx/nginx.conf`
- 证书目录：`deploy/ssl/`
- 若已有证书，可按文件内注释启用 `443 ssl` server block

#### 持久化目录

- `./data` → DuckDB / ChromaDB / expert_kg.json
- `./logs` → 后端日志
- `./deploy/ssl` → Nginx SSL 证书挂载

### 6.4 手动启动 — 后端（FastAPI）

```bash
cd backend

# 安装依赖
pip install -e .

# 启动（开发模式）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或直接运行
python main.py
```

| 项 | 值 |
|----|---|
| 监听地址 | `0.0.0.0:8000` |
| CORS 允许 | `localhost:3000`, `localhost:5173` |
| 日志目录 | `logs/engine_{date}.log`（保留 30 天） |

### 6.5 手动启动 — 前端（Next.js）

```bash
cd frontend

# 安装依赖
npm install

# 开发模式
npm run dev        # → http://localhost:3000

# 生产构建 & 启动
npm run build
npm run start      # → http://localhost:3000
```

| 项 | 值 |
|----|---|
| 开发端口 | 3000 |
| API 代理 | `/api/*` → `http://localhost:8000/api/*` |

---

## 七、关键配置项

> 文件：`backend/config.py` — 统一路径入口 + 全局配置

| 配置项 | 默认值 | 说明 |
|--------|-------|------|
| 数据库路径 | `data/stockterrain.duckdb` | DuckDB 嵌入式数据库 |
| AKShare 启用 | `True` | A股行情数据源 |
| BaoStock 启用 | `True` | 证券数据源（备用） |
| Tushare 启用 | `False` | 需配置 Token |
| Redis 启用 | `False` | 不启用时退化为内存缓存 |
| UMAP n_neighbors | 30 | 降维邻域 |
| UMAP min_dist | 0.3 | 降维最小距离 |
| HDBSCAN min_cluster_size | 20 | 最小聚类规模 |
| 插值方法 | `wendland_c2` | RBF 径向基函数 |
| 地形分辨率 | 128 × 128 | 插值网格分辨率 |
| 特征融合 PCA 维度 | 50 | 降维目标维度 |

---

## 八、部署步骤汇总

### 方式一：一键脚本

```bash
# 1. 克隆项目
git clone <repo-url>
cd Visualize-A-shares

# 2. 一键配置
scripts/setup.sh

# 3. 编辑 .env 填入 API Key

# 4. 一键启动
scripts/start.sh
```

### 方式二：Docker Compose

```bash
# 1. 克隆项目
git clone <repo-url>
cd Visualize-A-shares

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 3. 启动
docker compose up -d
```

### 方式三：手动部署

```bash
# 1. 克隆项目
git clone <repo-url>
cd Visualize-A-shares

# 2. 后端环境
cd backend
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e .

# 3. 前端环境
cd ../frontend
npm install

# 4. 预计算数据已随仓库提供，无需额外操作
# （如需更新：cd backend && python -m engine.cluster.preprocess.build_embeddings）

# 5. 启动后端（终端 1）
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000

# 6. 启动前端（终端 2）
cd frontend
npm run build && npm run start
# 或开发模式：npm run dev
```

---

## 九、注意事项

1. **启动顺序**：先启动后端（8000），再启动前端（3000），前端依赖后端 API 代理
2. **首次运行需联网**：后端会访问 AKShare / BaoStock 获取实时行情
3. **磁盘空间**：后端依赖（含 PyTorch）约需 2-4 GB，前端 node_modules 约 500 MB
4. **内存要求**：建议至少 4 GB RAM（UMAP + HDBSCAN 运算时峰值较高）
5. **DuckDB 数据库**：运行时自动创建，不纳入版本控制
6. **日志**：自动输出到 `logs/` 目录，保留 30 天
