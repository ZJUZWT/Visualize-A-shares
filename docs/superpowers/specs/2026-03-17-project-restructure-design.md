# 项目重构 — 目录重组 + 一键部署设计文档

## 目标

将项目从当前的 `engine/` + `web/` 结构重组为 `backend/` + `frontend/`，内部按领域分组，统一路径管理，新增跨平台一键配置/启动脚本和 Docker Compose 支持。

## 动机

- 目录命名不直观（`engine` 不如 `backend` 通用）
- 后端内部模块扁平堆放，缺乏逻辑分层
- 没有一键配置/启动方式，新用户上手成本高
- 19 个文件各自用 `Path(__file__).parent.parent...` 定位路径，脆弱且不一致
- 不支持 Docker 部署

## 设计决策

### 已确认的决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 顶层目录命名 | `backend/` + `frontend/` | 通用、直观 |
| data/ 目录 | 保留根目录 | 只有后端使用，通过相对路径访问，未来 Docker 挂载即可 |
| 测试目录 | 合并到根目录 `tests/unit/` + `tests/integration/` | 开发环境统一管理，生产不需要 |
| .env 文件 | 保留根目录单个 `.env` | 前端几乎无配置，不需要拆分 |
| 启动方式 | Shell 脚本 + Docker Compose | 本地开发用脚本，容器化部署用 Docker |
| 后端内部分组 | 按领域分组，放在 `engine/` 子目录下 | 未来每个领域可内置专属 Agent |
| 路由归属 | 跟着领域走 | 领域内聚合度高，加新接口只改一个文件夹 |
| 路径管理 | 收敛到 `config.py` 统一入口 | 19 个文件的 `.parent.parent` 全部消除 |
| 环境隔离 | 全本地（`.venv` + `node_modules`） | 不污染用户全局环境 |
| 实施策略 | 一步到位（重命名 + 内部重组 + 脚本 + Docker） | 长期主义，一次搞定 |

### 未来规划（不在本次实施）

- expert 模块从无状态 LLM 包装升级为有记忆、能学习的专属 Agent
- 每个领域引擎内置专属 Agent，能不断学习和精炼

## 目标目录结构

```
A_Claude/
├── backend/
│   ├── engine/                    ← 领域模块
│   │   ├── data/                  ← 原 data_engine/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py          ← DataEngine 门面
│   │   │   ├── collector.py       ← 数据采集器
│   │   │   ├── store.py           ← DuckDB 持久化
│   │   │   ├── routes.py          ← REST API /api/v1/data/*
│   │   │   ├── schemas.py
│   │   │   ├── precomputed.py
│   │   │   └── sources/           ← 数据源（Tencent/AKShare/BaoStock）
│   │   ├── cluster/               ← 原 cluster_engine/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py          ← ClusterEngine 门面
│   │   │   ├── routes.py          ← REST API /api/v1/terrain/*
│   │   │   ├── schemas.py
│   │   │   ├── algorithm/         ← 算法流水线
│   │   │   │   ├── __init__.py
│   │   │   │   ├── pipeline.py
│   │   │   │   ├── clustering.py
│   │   │   │   ├── interpolation.py
│   │   │   │   ├── projection.py
│   │   │   │   ├── predictor.py
│   │   │   │   ├── predictor_v2.py
│   │   │   │   ├── factor_backtest.py
│   │   │   │   └── features.py
│   │   │   └── preprocess/        ← 预处理脚本
│   │   │       ├── __init__.py
│   │   │       ├── build_embeddings.py
│   │   │       ├── rebuild_bge.py
│   │   │       └── export_snapshot.py
│   │   ├── quant/                 ← 原 quant_engine/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── predictor.py
│   │   │   ├── indicators.py
│   │   │   ├── factor_backtest.py
│   │   │   └── routes.py
│   │   ├── info/                  ← 原 info_engine/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── sentiment.py
│   │   │   ├── event_assessor.py
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   ├── industry/              ← 原 industry_engine/
│   │   │   ├── __init__.py
│   │   │   ├── engine.py
│   │   │   ├── agent.py
│   │   │   ├── routes.py
│   │   │   └── schemas.py
│   │   ├── arena/                 ← 原 agent/ + rag/
│   │   │   ├── __init__.py
│   │   │   ├── debate.py
│   │   │   ├── orchestrator.py
│   │   │   ├── judge.py
│   │   │   ├── personas.py
│   │   │   ├── runner.py
│   │   │   ├── memory.py
│   │   │   ├── aggregator.py
│   │   │   ├── data_fetcher.py
│   │   │   ├── schemas.py
│   │   │   └── rag/               ← 原 rag/
│   │   │       ├── __init__.py
│   │   │       ├── store.py
│   │   │       └── schemas.py
│   │   └── expert/                ← 原 expert/（专家调度器）
│   │       ├── __init__.py
│   │       ├── agent.py
│   │       ├── engine_experts.py
│   │       ├── knowledge_graph.py
│   │       ├── personas.py
│   │       ├── tools.py
│   │       ├── routes.py
│   │       └── schemas.py
│   ├── llm/                       ← LLM 基础设施（不变）
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── providers.py
│   │   ├── capability.py
│   │   └── context.py
│   ├── api/                       ← 跨领域路由（chat/analysis/debate）
│   │   ├── __init__.py
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── chat.py
│   │       ├── analysis.py
│   │       └── debate.py
│   ├── mcpserver/                 ← MCP Server（不变）
│   │   ├── __init__.py
│   │   ├── __main__.py
│   │   ├── server.py
│   │   ├── tools.py
│   │   ├── data_access.py
│   │   └── formatters.py
│   ├── storage/                   ← 存储抽象
│   ├── config.py                  ← 统一路径入口
│   ├── main.py                    ← FastAPI 启动
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                      ← 原 web/
│   ├── app/
│   ├── components/
│   ├── stores/
│   ├── lib/
│   ├── types/
│   ├── public/
│   ├── package.json
│   ├── next.config.ts
│   └── Dockerfile
├── tests/                         ← 合并两套测试
│   ├── conftest.py                ← 统一 sys.path 注入
│   ├── unit/                      ← 原 engine/tests/
│   │   ├── agent/
│   │   ├── expert/
│   │   ├── llm/
│   │   └── mcpserver/
│   └── integration/               ← 原根目录 tests/
├── scripts/
│   ├── setup.sh                   ← macOS/Linux 一键配置
│   ├── setup.bat                  ← Windows 一键配置
│   ├── start.sh                   ← macOS/Linux 一键启动
│   └── start.bat                  ← Windows 一键启动
├── data/                          ← 不动
│   ├── precomputed/
│   ├── stockterrain.duckdb
│   ├── chromadb/
│   └── chromadb_rag/
├── docs/
├── docker-compose.yml
├── .env
├── .env.example
├── .mcp.json
├── .gitignore
├── CLAUDE.md
└── README.md
```

## config.py — 统一路径入口

当前 19 个文件各自用 `Path(__file__).resolve().parent.parent...` 定位项目根目录，层级不一致。重构后收敛到 `backend/config.py` 一个入口。

```python
# backend/config.py
import os
from pathlib import Path

# 项目根目录 — 支持环境变量覆盖（Docker 场景）
PROJECT_ROOT = Path(os.environ.get(
    "PROJECT_ROOT",
    str(Path(__file__).resolve().parent.parent)
))

# 核心路径
BACKEND_DIR = PROJECT_ROOT / "backend"
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "stockterrain.duckdb"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"
LOGS_DIR = PROJECT_ROOT / "logs"
ENV_FILE = PROJECT_ROOT / ".env"

# ChromaDB
CHROMADB_DIR = DATA_DIR / "chromadb"
CHROMADB_RAG_DIR = DATA_DIR / "chromadb_rag"
```

所有其他文件不再自己算路径：

```python
# 之前（散落在 19 个文件中）：
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 之后（统一）：
from config import DATA_DIR, PRECOMPUTED_DIR, DB_PATH
```

## import 路径映射

内部模块重组后，所有 import 路径需要更新。`main.py` 启动时将 `backend/` 加入 `sys.path`，因此 import 起点是 `backend/` 目录。

| 旧 import | 新 import |
|-----------|-----------|
| `from data_engine import ...` | `from engine.data import ...` |
| `from data_engine.engine import DataEngine` | `from engine.data.engine import DataEngine` |
| `from data_engine.sources.base import ...` | `from engine.data.sources.base import ...` |
| `from cluster_engine import ...` | `from engine.cluster import ...` |
| `from cluster_engine.algorithm.pipeline import ...` | `from engine.cluster.algorithm.pipeline import ...` |
| `from quant_engine import ...` | `from engine.quant import ...` |
| `from info_engine import ...` | `from engine.info import ...` |
| `from industry_engine import ...` | `from engine.industry import ...` |
| `from agent.debate import ...` | `from engine.arena.debate import ...` |
| `from agent.orchestrator import ...` | `from engine.arena.orchestrator import ...` |
| `from rag.store import ...` | `from engine.arena.rag.store import ...` |
| `from expert.engine_experts import ...` | `from engine.expert.engine_experts import ...` |
| `from llm.providers import ...` | `from llm.providers import ...`（不变） |
| `from api.routes import ...` | `from api.routes import ...`（不变） |
| `from mcpserver import ...` | `from mcpserver import ...`（不变） |
| `from config import ...` | `from config import ...`（不变） |

### 单例获取函数

各引擎的 `get_*_engine()` 单例函数需要同步更新 `__init__.py` 中的导出路径。例如：

```python
# engine/data/__init__.py
from .engine import DataEngine, get_data_engine
```

## Shell 脚本设计

### scripts/setup.sh（macOS/Linux）

```bash
#!/usr/bin/env bash
set -e

echo "=== StockTerrain 环境配置 ==="

# 1. 检测 Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PY_VER"

# 2. 检测 Node.js 18+
if ! command -v node &>/dev/null; then
    echo "❌ 未找到 node，请先安装 Node.js 18+"
    exit 1
fi
echo "✅ Node.js $(node -v)"

# 3. 后端环境
echo "--- 配置后端环境 ---"
cd backend
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
cd ..

# 4. 前端环境
echo "--- 配置前端环境 ---"
cd frontend
npm install
cd ..

# 5. .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo "📝 已创建 .env，请编辑填入 API Key"
fi

echo "=== 配置完成 ==="
```

### scripts/setup.bat（Windows）

同等逻辑，使用 `where python`、`python -m venv .venv`、`.venv\Scripts\pip install` 等 Windows 命令。

### scripts/start.sh（macOS/Linux）

```bash
#!/usr/bin/env bash
set -e

# 检查环境
[ -d backend/.venv ] || { echo "❌ 请先运行 scripts/setup.sh"; exit 1; }
[ -d frontend/node_modules ] || { echo "❌ 请先运行 scripts/setup.sh"; exit 1; }

echo "=== 启动 StockTerrain ==="

# 后端
cd backend && .venv/bin/python main.py &
BACKEND_PID=$!
cd ..

# 前端
cd frontend && npm run dev &
FRONTEND_PID=$!
cd ..

echo "✅ 后端: http://localhost:8000"
echo "✅ 前端: http://localhost:3000"
echo "按 Ctrl+C 停止"

# 优雅关闭
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
```

### scripts/start.bat（Windows）

同等逻辑，使用 `start /B` 启动后台进程。

## Docker Compose 设计

### docker-compose.yml

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env:ro
    environment:
      - PROJECT_ROOT=/app
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 10s
      timeout: 3s
      retries: 3

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    depends_on:
      backend:
        condition: service_healthy
    environment:
      - NEXT_PUBLIC_API_BASE=http://localhost:8000
```

> 注意：`NEXT_PUBLIC_API_BASE` 是浏览器端使用的地址，必须用 `localhost` 而非 Docker 内部域名 `backend`。浏览器无法解析容器间的 DNS。

### backend/Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app/backend

# 先复制依赖声明，利用 Docker 层缓存
COPY pyproject.toml .
COPY . .

RUN pip install . -i https://pypi.tuna.tsinghua.edu.cn/simple

EXPOSE 8000
CMD ["python", "main.py"]
```

### frontend/Dockerfile

```dockerfile
FROM node:20-slim

WORKDIR /app/frontend

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
```

Docker 环境下 `config.py` 通过 `PROJECT_ROOT=/app` 环境变量定位数据目录为 `/app/data`，与宿主机 `./data` 挂载对应。

## 测试目录合并

### 合并策略

| 来源 | 目标 | 说明 |
|------|------|------|
| `engine/tests/*.py` | `tests/unit/` | 后端单元测试 |
| `engine/tests/agent/` | `tests/unit/agent/` | agent 子目录测试 |
| `engine/tests/expert/` | `tests/unit/expert/` | expert 子目录测试 |
| `engine/tests/llm/` | `tests/unit/llm/` | llm 子目录测试 |
| `engine/tests/mcpserver/` | `tests/unit/mcpserver/` | mcpserver 子目录测试 |
| 根目录 `tests/*.py` | `tests/integration/` | 集成测试 |

### tests/conftest.py

```python
import sys
from pathlib import Path

# 将 backend/ 加入 sys.path，使 import engine.data / llm / config 等生效
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
```

单元测试和集成测试共用这一个 conftest.py，不再需要两套。

运行方式：
```bash
# 全部测试
pytest tests/

# 只跑单元测试
pytest tests/unit/

# 只跑集成测试
pytest tests/integration/
```

## 配置文件更新清单

| 文件 | 改动 |
|------|------|
| `.mcp.json` | `cwd: "./engine"` → `"./backend"`, `command: "./engine/.venv/bin/python"` → `"./backend/.venv/bin/python"` |
| `.github/workflows/deploy-pages.yml` | `working-directory: web` → `frontend`, `cache-dependency-path: web/...` → `frontend/...` |
| `.gitignore` | `engine/.venv` → `backend/.venv` 等路径更新 |
| `CLAUDE.md` | 所有 `engine/` → `backend/`，`web/` → `frontend/`，模块路径更新 |
| `README.md` | 所有命令和路径更新 |
| `DEPLOYMENT.md` | 所有命令和路径更新，新增 Docker 部署说明 |
| `ROADMAP.md` | 路径引用更新（如有） |

## 需要更新 import 的文件（完整清单）

### 路径收敛（19 个文件，消除 .parent.parent）

1. `backend/config.py` — 重写为统一路径入口
2. `backend/llm/config.py` — `_env_file` 改用 `from config import ENV_FILE`
3. `backend/engine/data/precomputed.py` — `PROJECT_ROOT` 改用 `from config import PRECOMPUTED_DIR`
4. `backend/engine/cluster/algorithm/features.py` — 改用 `from config import PRECOMPUTED_DIR`
5. `backend/engine/cluster/preprocess/build_embeddings.py` — 改用 `from config import ...`
6. `backend/engine/cluster/preprocess/rebuild_bge.py` — 改用 `from config import ...`
7. `backend/engine/cluster/preprocess/export_snapshot.py` — 改用 `from config import ...`
8. `backend/mcpserver/tools.py` — `emb_path` 改用 `from config import PRECOMPUTED_DIR`
9. `backend/mcpserver/server.py` — sys.path 注入更新
10. `backend/api/routes/chat.py` — `env_path` 改用 `from config import ENV_FILE`
11-19. 其余散落的 `Path(__file__).parent.parent` 引用

### import 路径更新（模块重命名）

所有 `from data_engine`、`from cluster_engine`、`from quant_engine`、`from info_engine`、`from industry_engine`、`from agent`、`from rag`、`from expert` 的 import 语句需要按映射表更新。涉及文件包括但不限于：

- `backend/main.py` — 路由注册
- `backend/api/routes/*.py` — 引擎调用
- `backend/mcpserver/tools.py` — 引擎调用
- `backend/engine/expert/engine_experts.py` — 调用各引擎
- `backend/engine/arena/data_fetcher.py` — 调用各引擎
- `backend/engine/arena/orchestrator.py` — 调用辩论模块
- `backend/engine/cluster/algorithm/*.py` — 内部引用
- 各引擎的 `__init__.py` — 导出路径

## 不做的事情

- 不改 REST API 的 URL 路径（`/api/v1/data/*` 等保持不变）
- 不改前端代码逻辑（只改目录名 `web/` → `frontend/`）
- 不改 DuckDB 表结构
- 不改 LLM 调用逻辑
- 不实现 expert 升级为有记忆的 Agent（记录为未来规划）
- 不做前端 SSR/Docker 生产构建优化（frontend Dockerfile 用 dev 模式即可）

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| import 路径遗漏导致运行时报错 | 每个 chunk 完成后运行 `python -c "import ..."` 验证 |
| git mv 后 git history 丢失 | `git mv` 保留文件历史，不用 delete + create |
| MCP Server 连接断开 | 更新 `.mcp.json` 后重启 MCP |
| Docker 构建失败 | 本地先验证 Shell 脚本方式，Docker 作为最后一步 |
| 测试合并后路径错误 | conftest.py 统一注入，合并后立即跑全量测试 |
