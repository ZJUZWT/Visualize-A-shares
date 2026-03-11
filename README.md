# 🏔️ StockTerrain

> A股多维聚类 3D 地形可视化平台
> *Data is the terrain. Market is the landscape.*

将 A股 5000+ 支股票映射为实时动态 **3D 地形图**。相似股票在空间上自然聚合，涨跌幅化为地形的高低起伏。

## 🚀 快速开始

### 环境要求
- Python >= 3.11
- Node.js >= 20
- pnpm / npm / yarn

### 1. 启动后端引擎

```bash
cd engine

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -e ".[dev]"

# 启动服务
python main.py
# → http://localhost:8000/docs
```

### 2. 启动前端渲染引擎

```bash
cd web

# 安装依赖
npm install

# 启动开发服务器
npm run dev
# → http://localhost:3000
```

### 3. 使用

1. 打开 `http://localhost:3000`
2. 点击 **"🏔️ 生成 3D 地形"** 按钮
3. 等待数据采集 + 算法计算（首次约 10~30 秒）
4. 享受 3D 股市地形图！

## 🏗️ 架构

```
stockterrain/
├── engine/                # 🔧 Python 后端 (FastAPI)
│   ├── data/              #    数据引擎 (AKShare + BaoStock)
│   ├── algorithm/         #    算法引擎 (HDBSCAN + UMAP + RBF)
│   ├── api/               #    REST + WebSocket API
│   └── storage/           #    DuckDB + Redis
│
├── web/                   # 🎨 前端渲染引擎 (Next.js + R3F)
│   ├── components/canvas/ #    3D 场景组件
│   ├── components/ui/     #    UI 控制面板
│   ├── stores/            #    Zustand 状态管理
│   └── shaders/           #    GLSL 着色器
│
└── data/                  # 📦 本地数据 (DuckDB)
```

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| **数据源** | AKShare (主力) + BaoStock (备选) + Tushare Pro (补充) |
| **后端** | FastAPI + Uvicorn + WebSocket |
| **算法** | HDBSCAN 聚类 + UMAP 降维 + RBF 薄板样条插值 |
| **存储** | DuckDB (OLAP) + Redis (缓存) |
| **前端** | React 19 + Next.js 15 + TypeScript |
| **3D 渲染** | React Three Fiber + drei + 自定义 GLSL |
| **状态** | Zustand |
| **样式** | TailwindCSS 4 |

## 📡 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/terrain/compute` | POST | 全量计算 3D 地形 |
| `/api/v1/terrain/refresh` | GET | 快速刷新 Z 轴 |
| `/api/v1/stocks/search?q=xxx` | GET | 搜索股票 |
| `/api/v1/ws/terrain` | WS | 实时地形推送 |

## 📜 License

MIT
