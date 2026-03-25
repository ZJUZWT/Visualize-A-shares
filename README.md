# 🌄 StockScape

> A股 AI 投研平台 — 3D 地形 · 多空辩论 · 专家对话
>
> *Data is the terrain. Intelligence is the landscape.*

将 A股 5000+ 支股票映射为实时 **3D 地形图**，用 Multi-Agent 辩论和多领域专家对话辅助投资决策。

---

## ✨ 三大核心功能

### 🗺️ 全市场 3D 地形

全市场股票经聚类算法（HDBSCAN + UMAP）降维到三维空间，相似股票自然聚合，涨跌幅化为地形起伏。

- 8 种 Z 轴指标一键切换：涨跌幅、换手率、成交量、PE、PB…
- 点击任意山峰定位到个股，查看关联股票
- 右下角 AI 聊天浮窗，自动注入当前地形上下文
- Multi-Agent 分析：基本面 + 消息面 + 技术面三维 Agent 并行输出买卖信号

### ⚖️ 多空辩论

多头专家 vs 空头专家对抗式辩论，散户/主力双观察员视角，AI 裁判最终裁决。

- 支持股票代码、行业板块、自由话题等多种辩论目标
- 黑板机制共享实时数据，RAG 检索增强历史知识
- 回测模式：指定历史日期作为数据基准
- 辩论报告可导出为自包含 HTML，离线可查看

### 🧠 投资专家对话

5 类可选专家（数据 / 量化 / 资讯 / 产业链 / 投资顾问），每位专家可调用后端工具获取实时数据。

- 知识图谱 + 信念系统，对话中动态更新投资观点
- 思考过程面板，透明展示 Agent 推理链和工具调用
- 多 Session 管理，随时切换对话上下文

---

## 🚀 快速开始

### 一键启动（推荐）

```bash
git clone <repo-url>
cd StockScape

scripts/setup.sh          # macOS / Linux（配置环境）
# 编辑 .env 填入 LLM API Key
scripts/start.sh           # 启动前后端
```

### Docker

```bash
cp .env.example .env && vim .env
docker compose up
```

→ 后端 http://localhost:8000 　前端 http://localhost:3000

### 生产部署骨架

```bash
cp .env.production.example .env.production
# 按实际域名、CORS、LLM Key 修改 .env.production

docker compose --env-file .env.production -f docker-compose.prod.yml up -d
```

默认拓扑：

- `frontend` 提供 Next.js 生产服务
- `backend` 提供 FastAPI
- `nginx` 统一反代 `/` 和 `/api`
- 可选 `cloudflared` profile 接入 Cloudflare Tunnel

如需启用 Tunnel：

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml --profile tunnel up -d
```

### 手动部署

<details>
<summary>展开详细步骤</summary>

#### 环境要求

| 组件 | 版本要求 |
|------|---------|
| Python | >= 3.11 |
| Node.js | >= 20 |
| Redis | 可选，不配置时退化为内存缓存 |

#### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填写 LLM 配置（辩论/分析/专家功能必填，3D 地形不需要）：

```env
LLM_ENABLED=true
LLM_PROVIDER=openai_compatible   # 或 anthropic
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

支持的 LLM 厂商：OpenAI / DeepSeek / 通义千问 / Kimi / Anthropic 等 OpenAI 兼容接口。

#### 2. 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e "." -i https://pypi.tuna.tsinghua.edu.cn/simple
python main.py
# → http://localhost:8000
```

#### 3. 前端

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

#### 4. 验证

```bash
curl http://localhost:8000/api/v1/health
```

</details>

---

## 🏗️ 架构

```
StockScape/
├── backend/               # Python 后端 (FastAPI)
│   ├── engine/
│   │   ├── data/          #   数据引擎 — 行情拉取 + DuckDB 持久化
│   │   ├── cluster/       #   聚类引擎 — HDBSCAN + UMAP + RBF 插值
│   │   ├── quant/         #   量化引擎 — 13因子 + 技术指标
│   │   ├── info/          #   信息引擎 — 新闻 + 公告 + 情感分析
│   │   ├── industry/      #   产业链引擎 — 行业认知 + 资本结构
│   │   ├── expert/        #   专家引擎 — 多专家并行 + 知识图谱
│   │   └── arena/         #   辩论引擎 — 多角色对抗 + 黑板 + 裁判
│   │       └── rag/       #     RAG 检索增强
│   ├── llm/               #   LLM 接入层 (多厂商适配)
│   ├── mcpserver/         #   MCP Server (22 tools)
│   └── main.py            #   应用入口
│
├── frontend/              # Next.js 15 前端
│   ├── app/               #   3 个路由: / (地形) /debate /expert
│   ├── components/        #   UI 组件 (Three.js 3D + 辩论 + 专家)
│   └── stores/            #   Zustand 状态管理
│
├── data/                  # DuckDB + 预计算嵌入
├── tests/                 # unit/ + integration/
├── scripts/               # 跨平台一键脚本
└── docker-compose.yml
```

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| 数据源 | AKShare + BaoStock |
| 后端 | FastAPI + Uvicorn |
| 算法 | HDBSCAN + UMAP + RBF 插值 |
| 存储 | DuckDB + Redis（可选） |
| AI | Multi-Agent 辩论 · RAG · 知识图谱 · 信念系统 |
| 前端 | React 19 + Next.js 15 + TypeScript |
| 3D | React Three Fiber + drei + GLSL |
| 状态 | Zustand |
| 样式 | Tailwind CSS v4 |
| 部署 | Docker Compose / Nginx / Cloudflare Tunnel（可选） |

## 🔌 MCP Server

内置 22 个 MCP Tool，可被 Claude Code 等外部 AI 直接调用：

```bash
cd backend && .venv/bin/python -m mcpserver
```

涵盖：全市场概览、股票搜索、个股全维度分析、条件选股、历史行情、技术指标、因子评分、新闻公告、事件评估、产业链认知、辩论触发等。

---

## License

MIT
