# 项目重构实施计划 — 目录重组 + 一键部署

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将项目从 `engine/` + `web/` 重组为 `backend/` + `frontend/`，内部按领域分组，统一路径管理，新增跨平台脚本和 Docker 支持

**Architecture:** 分 6 个 chunk 执行：(1) 顶层重命名 engine→backend, web→frontend (2) 后端内部模块重组 (3) config.py 路径统一 (4) import 路径全量更新 (5) 测试合并 (6) 脚本 + Docker + 文档更新。每个 chunk 完成后验证 import 正确性。

**Tech Stack:** Python, FastAPI, DuckDB, Next.js, Docker, Bash/Bat

---

## Chunk 1: 顶层目录重命名

### Task 1: git mv engine → backend, web → frontend

**Files:**
- Rename: `engine/` → `backend/`
- Rename: `web/` → `frontend/`

- [x] **Step 1: 重命名 engine → backend**

```bash
git mv engine backend
```

- [x] **Step 2: 重命名 web → frontend**

```bash
git mv web frontend
```

- [x] **Step 3: 更新 .mcp.json**

将 `.mcp.json` 中的路径从 `engine` 改为 `backend`：

```json
{
  "mcpServers": {
    "stockterrain": {
      "command": "./backend/.venv/bin/python",
      "args": ["-m", "mcpserver"],
      "cwd": "./backend"
    }
  }
}
```

- [x] **Step 4: 更新 .gitignore 中的路径引用**

将所有 `engine/` 引用改为 `backend/`，`web/` 改为 `frontend/`。

- [x] **Step 5: 验证目录结构**

```bash
ls -d backend/ frontend/ data/
```
Expected: 三个目录都存在

- [x] **Step 6: 验证后端可启动**

```bash
cd backend && .venv/bin/python -c "import main; print('OK')"
```
Expected: OK（此时 import 路径还没改，但 main.py 用的是相对 sys.path）

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: 顶层目录重命名 engine→backend, web→frontend"
```

---

## Chunk 2: 后端内部模块重组

### Task 2: 创建 engine/ 子目录并移动领域模块

**Files:**
- Create: `backend/engine/__init__.py`
- Rename: `backend/data_engine/` → `backend/engine/data/`
- Rename: `backend/cluster_engine/` → `backend/engine/cluster/`
- Rename: `backend/quant_engine/` → `backend/engine/quant/`
- Rename: `backend/info_engine/` → `backend/engine/info/`
- Rename: `backend/industry_engine/` → `backend/engine/industry/`
- Rename: `backend/expert/` → `backend/engine/expert/`

PLACEHOLDER_TASK2_STEPS

- [x] **Step 1: 创建 backend/engine/ 包目录**

```bash
mkdir -p backend/engine
touch backend/engine/__init__.py
```

- [x] **Step 2: 移动领域模块**

```bash
cd backend
git mv data_engine engine/data
git mv cluster_engine engine/cluster
git mv quant_engine engine/quant
git mv info_engine engine/info
git mv industry_engine engine/industry
git mv expert engine/expert
```

- [x] **Step 3: 验证目录结构**

```bash
ls backend/engine/
```
Expected: `__init__.py data cluster quant info industry expert`

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: 后端领域模块移入 backend/engine/ 子目录"
```

### Task 3: 创建 arena/ 并移动 agent + rag

**Files:**
- Rename: `backend/agent/` → `backend/engine/arena/`
- Rename: `backend/rag/` → `backend/engine/arena/rag/`

- [x] **Step 1: 移动 agent → arena**

```bash
cd backend
git mv agent engine/arena
```

- [x] **Step 2: 移动 rag 到 arena 内部**

```bash
cd backend
git mv rag engine/arena/rag
```

- [x] **Step 3: 验证目录结构**

```bash
ls backend/engine/arena/
```
Expected: `__init__.py debate.py orchestrator.py judge.py personas.py runner.py memory.py aggregator.py data_fetcher.py schemas.py rag/`

- [x] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: agent+rag 合并为 backend/engine/arena/"
```

### Task 4: 清理遗留空目录

**Files:**
- Delete: `backend/data/` (如果存在且为空的遗留目录)
- Delete: `backend/preprocess/` (如果存在且为空的遗留目录)
- Delete: `backend/storage/` (如果为空)

- [x] **Step 1: 检查并清理空目录**

```bash
# 检查是否有遗留空目录
find backend/ -maxdepth 1 -type d -empty
# 如果有，删除
# rmdir backend/data backend/preprocess backend/storage 2>/dev/null || true
```

- [x] **Step 2: Commit（如有改动）**

```bash
git add -A
git commit -m "chore: 清理遗留空目录" --allow-empty
```

---

## Chunk 3: config.py 路径统一

### Task 5: 重写 backend/config.py 为统一路径入口

**Files:**
- Modify: `backend/config.py`

- [x] **Step 1: 重写 config.py**

将 `backend/config.py` 重写为统一路径入口。保留原有的非路径配置（如 Pydantic Settings 类），只替换路径计算部分：

```python
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

注意：保留 config.py 中原有的其他配置类和变量，只替换路径相关的部分。

- [x] **Step 2: 验证 config.py 可导入**

```bash
cd backend && .venv/bin/python -c "from config import PROJECT_ROOT, DATA_DIR, DB_PATH, PRECOMPUTED_DIR, ENV_FILE; print('OK')"
```
Expected: OK

- [x] **Step 3: Commit**

```bash
git add backend/config.py
git commit -m "refactor: config.py 重写为统一路径入口"
```

### Task 6: 消除所有 Path(__file__).parent 路径计算

**Files:**
- Modify: `backend/llm/config.py`
- Modify: `backend/engine/data/precomputed.py`
- Modify: `backend/engine/cluster/algorithm/features.py`
- Modify: `backend/engine/cluster/preprocess/build_embeddings.py`
- Modify: `backend/engine/cluster/preprocess/rebuild_bge.py`
- Modify: `backend/engine/cluster/preprocess/export_snapshot.py`
- Modify: `backend/mcpserver/tools.py`
- Modify: `backend/mcpserver/server.py`
- Modify: `backend/api/routes/chat.py`
- Modify: `backend/main.py`

- [x] **Step 1: 更新 backend/main.py**

保留 `sys.path.insert(0, str(Path(__file__).resolve().parent))` — 这是启动入口，需要将 backend/ 加入 sys.path。不需要改。

- [x] **Step 2: 更新 backend/llm/config.py**

替换：
```python
_env_file = Path(__file__).resolve().parent.parent.parent / ".env"
```
改为：
```python
from config import ENV_FILE
_env_file = ENV_FILE
```

- [x] **Step 3: 更新 backend/engine/data/precomputed.py**

替换：
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
```
改为：
```python
from config import PRECOMPUTED_DIR, DATA_DIR
```
并将所有 `PROJECT_ROOT / "data" / "precomputed"` 替换为 `PRECOMPUTED_DIR`。

- [x] **Step 4: 更新 backend/engine/cluster/algorithm/features.py**

替换：
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```
改为：
```python
from config import PRECOMPUTED_DIR
```
并更新所有引用。

- [x] **Step 5: 更新 backend/engine/cluster/preprocess/build_embeddings.py**

替换：
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```
改为：
```python
from config import PROJECT_ROOT, DATA_DIR, PRECOMPUTED_DIR
```

- [x] **Step 6: 更新 backend/engine/cluster/preprocess/rebuild_bge.py**

替换：
```python
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
```
改为：
```python
from config import PROJECT_ROOT, PRECOMPUTED_DIR
```

- [x] **Step 7: 更新 backend/engine/cluster/preprocess/export_snapshot.py**

替换：
```python
ENGINE_DIR = Path(__file__).resolve().parent.parent.parent
```
改为：
```python
from config import BACKEND_DIR, DATA_DIR
```

- [x] **Step 8: 更新 backend/mcpserver/tools.py**

替换：
```python
emb_path = Path(__file__).resolve().parent.parent.parent / "data" / "precomputed" / "stock_embeddings.npz"
```
改为：
```python
from config import PRECOMPUTED_DIR
emb_path = PRECOMPUTED_DIR / "stock_embeddings.npz"
```

- [x] **Step 9: 更新 backend/mcpserver/server.py**

替换：
```python
_engine_dir = str(Path(__file__).resolve().parent.parent)
if _engine_dir not in sys.path:
    sys.path.insert(0, _engine_dir)
```
改为：
```python
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
```

- [x] **Step 10: 更新 backend/api/routes/chat.py**

替换：
```python
env_path = Path(__file__).resolve().parent.parent.parent.parent / ".env"
```
改为：
```python
from config import ENV_FILE
env_path = ENV_FILE
```

- [x] **Step 11: 验证所有修改后的文件可导入**

```bash
cd backend && .venv/bin/python -c "
from config import PROJECT_ROOT, DATA_DIR, DB_PATH
from llm.config import get_llm_config
print('config OK')
"
```
Expected: config OK

- [x] **Step 12: Commit**

```bash
git add -A
git commit -m "refactor: 消除所有 Path(__file__).parent 路径计算，统一使用 config.py"
```

---

## Chunk 4: import 路径全量更新

> 这是改动量最大的 chunk。模块重命名后所有跨模块 import 都需要更新。
> 按被依赖顺序执行：先更新底层模块（被别人 import 的），再更新上层模块（import 别人的）。

### Task 7: 更新 __init__.py 导出路径

**Files:**
- Modify: `backend/engine/data/__init__.py`
- Modify: `backend/engine/cluster/__init__.py`
- Modify: `backend/engine/quant/__init__.py`
- Modify: `backend/engine/info/__init__.py`
- Modify: `backend/engine/industry/__init__.py`
- Modify: `backend/engine/arena/__init__.py`
- Modify: `backend/engine/arena/rag/__init__.py`
- Modify: `backend/engine/expert/__init__.py`

- [x] **Step 1: 更新 engine/data/__init__.py**

将 `from data_engine import ...` 改为相对导入 `from .engine import ...`（如果原来用的是绝对导入）。确保 `get_data_engine` 可从 `engine.data` 导入。

- [x] **Step 2: 更新 engine/cluster/__init__.py**

将 `from data_engine import get_data_engine` 改为 `from engine.data import get_data_engine`。

- [x] **Step 3: 更新 engine/quant/__init__.py**

将 `from data_engine import get_data_engine` 改为 `from engine.data import get_data_engine`。

- [x] **Step 4: 更新 engine/info/__init__.py**

将 `from data_engine import get_data_engine` 改为 `from engine.data import get_data_engine`。

- [x] **Step 5: 更新 engine/industry/__init__.py**

将 `from data_engine import get_data_engine` 改为 `from engine.data import get_data_engine`。

- [x] **Step 6: 更新 engine/arena/__init__.py**

将：
```python
from data_engine import get_data_engine
from rag import get_rag_store
```
改为：
```python
from engine.data import get_data_engine
from engine.arena.rag import get_rag_store
```

- [x] **Step 7: 更新 engine/arena/rag/__init__.py**

检查是否有绝对导入需要更新。`get_rag_store` 应该用相对导入 `from .store import ...`。

- [x] **Step 8: 更新 engine/expert/__init__.py**

检查并更新任何绝对导入。

- [x] **Step 9: 验证所有 __init__.py**

```bash
cd backend && .venv/bin/python -c "
from engine.data import get_data_engine
from engine.cluster import get_cluster_engine
from engine.quant import get_quant_engine
from engine.info import get_info_engine
from engine.industry import get_industry_engine
print('All __init__.py OK')
"
```
Expected: All __init__.py OK

- [x] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: 更新所有 __init__.py 导出路径"
```

### Task 8: 更新数据层 import（data, cluster, quant）

**Files:**
- Modify: `backend/engine/cluster/routes.py`
- Modify: `backend/engine/cluster/engine.py`
- Modify: `backend/engine/cluster/algorithm/pipeline.py`
- Modify: `backend/engine/cluster/algorithm/predictor_v2.py`
- Modify: `backend/engine/cluster/algorithm/factor_backtest.py`
- Modify: `backend/engine/cluster/preprocess/export_snapshot.py`
- Modify: `backend/engine/cluster/preprocess/build_embeddings.py`
- Modify: `backend/engine/quant/routes.py`
- Modify: `backend/engine/quant/predictor.py`

- [x] **Step 1: 更新 engine/cluster/routes.py**

替换所有 import：
```
from data_engine import get_data_engine          → from engine.data import get_data_engine
from cluster_engine import get_cluster_engine    → from engine.cluster import get_cluster_engine
from cluster_engine.schemas import ...           → from engine.cluster.schemas import ...
from quant_engine.factor_backtest import ...     → from engine.quant.factor_backtest import ...
from quant_engine.predictor import FACTOR_DEFS   → from engine.quant.predictor import FACTOR_DEFS
```

- [x] **Step 2: 更新 engine/cluster/engine.py**

```
from quant_engine import get_quant_engine → from engine.quant import get_quant_engine
```

- [x] **Step 3: 更新 engine/cluster/algorithm/pipeline.py**

```
from quant_engine.predictor import StockPredictorV2 → from engine.quant.predictor import StockPredictorV2
```

- [x] **Step 4: 更新 engine/cluster/algorithm/predictor_v2.py**

```
from quant_engine.predictor import ... → from engine.quant.predictor import ...
```

- [x] **Step 5: 更新 engine/cluster/algorithm/factor_backtest.py**

```
from quant_engine.factor_backtest import ... → from engine.quant.factor_backtest import ...
```

- [x] **Step 6: 更新 engine/cluster/preprocess/export_snapshot.py**

```
from data_engine import get_data_engine                    → from engine.data import get_data_engine
from cluster_engine.algorithm.pipeline import ...          → from engine.cluster.algorithm.pipeline import ...
```

- [x] **Step 7: 更新 engine/cluster/preprocess/build_embeddings.py**

```
from cluster_engine.preprocess.rebuild_bge import ... → from engine.cluster.preprocess.rebuild_bge import ...
```

- [x] **Step 8: 更新 engine/quant/routes.py**

```
from quant_engine import get_quant_engine    → from engine.quant import get_quant_engine
from data_engine import get_data_engine      → from engine.data import get_data_engine
from cluster_engine import get_cluster_engine → from engine.cluster import get_cluster_engine
```

- [x] **Step 9: 更新 engine/quant/predictor.py**

```
from cluster_engine.algorithm.features import FeatureEngineer → from engine.cluster.algorithm.features import FeatureEngineer
```

- [x] **Step 10: 验证数据层 import**

```bash
cd backend && .venv/bin/python -c "
from engine.cluster.routes import router
from engine.quant.routes import router as qr
print('数据层 OK')
"
```
Expected: 数据层 OK

- [x] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor: 更新数据层 import 路径（data/cluster/quant）"
```

### Task 9: 更新智能层 import（info, industry, expert）

**Files:**
- Modify: `backend/engine/info/routes.py`
- Modify: `backend/engine/industry/routes.py`
- Modify: `backend/engine/industry/engine.py`
- Modify: `backend/engine/industry/agent.py`
- Modify: `backend/engine/expert/routes.py`
- Modify: `backend/engine/expert/agent.py`
- Modify: `backend/engine/expert/knowledge_graph.py`
- Modify: `backend/engine/expert/tools.py`
- Modify: `backend/engine/expert/engine_experts.py`

- [x] **Step 1: 更新 engine/info/routes.py**

```
from info_engine import get_info_engine → from engine.info import get_info_engine
```

- [x] **Step 2: 更新 engine/industry/routes.py**

```
from industry_engine import get_industry_engine → from engine.industry import get_industry_engine
```
（注意：此文件有 6 处相同 import，全部替换）

- [x] **Step 3: 更新 engine/industry/engine.py**

```
from agent.data_fetcher import DataFetcher → from engine.arena.data_fetcher import DataFetcher
```

- [x] **Step 4: 更新 engine/industry/agent.py**

```
from data_engine import get_data_engine → from engine.data import get_data_engine
```

- [x] **Step 5: 更新 engine/expert/routes.py**

```
from expert.agent import ExpertAgent                    → from engine.expert.agent import ExpertAgent
from expert.engine_experts import ...                   → from engine.expert.engine_experts import ...
from expert.schemas import ...                          → from engine.expert.schemas import ...
from expert.tools import ExpertTools                    → from engine.expert.tools import ExpertTools
from data_engine import get_data_engine                 → from engine.data import get_data_engine
from cluster_engine import get_cluster_engine           → from engine.cluster import get_cluster_engine
```

- [x] **Step 6: 更新 engine/expert/agent.py**

```
from expert.knowledge_graph import KnowledgeGraph → from engine.expert.knowledge_graph import KnowledgeGraph
from expert.personas import ...                   → from engine.expert.personas import ...
from expert.schemas import ...                    → from engine.expert.schemas import ...
from expert.tools import ExpertTools              → from engine.expert.tools import ExpertTools
from data_engine import get_data_engine           → from engine.data import get_data_engine
from agent.memory import AgentMemory              → from engine.arena.memory import AgentMemory
```

- [x] **Step 7: 更新 engine/expert/knowledge_graph.py**

```
from expert.schemas import ... → from engine.expert.schemas import ...
```

- [x] **Step 8: 更新 engine/expert/tools.py**

```
from expert.schemas import ToolCall → from engine.expert.schemas import ToolCall
```

- [x] **Step 9: 更新 engine/expert/engine_experts.py**

```
from data_engine import get_data_engine           → from engine.data import get_data_engine
from cluster_engine import get_cluster_engine     → from engine.cluster import get_cluster_engine
from quant_engine import get_quant_engine         → from engine.quant import get_quant_engine
from industry_engine import get_industry_engine   → from engine.industry import get_industry_engine
```
（注意：此文件有多处延迟 import，全部替换）

- [x] **Step 10: 验证智能层 import**

```bash
cd backend && .venv/bin/python -c "
from engine.info.routes import router
from engine.industry.routes import router as ir
from engine.expert.engine_experts import EngineExpert
print('智能层 OK')
"
```
Expected: 智能层 OK

- [x] **Step 11: Commit**

```bash
git add -A
git commit -m "refactor: 更新智能层 import 路径（info/industry/expert）"
```

### Task 10: 更新 arena 层 import（agent/debate/rag）

**Files:**
- Modify: `backend/engine/arena/debate.py`
- Modify: `backend/engine/arena/judge.py`
- Modify: `backend/engine/arena/data_fetcher.py`
- Modify: `backend/engine/arena/schemas.py`
- Modify: `backend/engine/arena/orchestrator.py`
- Modify: `backend/engine/arena/runner.py`
- Modify: `backend/engine/arena/memory.py`

- [x] **Step 1: 更新 engine/arena/debate.py**

替换所有 import（此文件 import 最多，约 15 处）：
```
from agent.memory import AgentMemory           → from engine.arena.memory import AgentMemory
from agent.data_fetcher import DataFetcher     → from engine.arena.data_fetcher import DataFetcher
from agent.schemas import ...                  → from engine.arena.schemas import ...
from agent.personas import ...                 → from engine.arena.personas import ...
from agent.debate import ...                   → from engine.arena.debate import ...（自引用，改为相对导入）
from industry_engine import ...                → from engine.industry import ...
from data_engine import get_data_engine        → from engine.data import get_data_engine
```

- [x] **Step 2: 更新 engine/arena/judge.py**

```
from agent.schemas import ...                  → from engine.arena.schemas import ...
from expert.agent import ExpertAgent           → from engine.expert.agent import ExpertAgent（TYPE_CHECKING）
from agent.personas import ...                 → from engine.arena.personas import ...
from agent.debate import ...                   → from engine.arena.debate import ...
from agent.memory import AgentMemory           → from engine.arena.memory import AgentMemory
```

- [x] **Step 3: 更新 engine/arena/data_fetcher.py**

替换所有 import（约 12 处延迟 import）：
```
from data_engine import get_data_engine        → from engine.data import get_data_engine
from quant_engine import get_quant_engine      → from engine.quant import get_quant_engine
from info_engine import get_info_engine        → from engine.info import get_info_engine
```

- [x] **Step 4: 更新 engine/arena/schemas.py**

```
from industry_engine.schemas import IndustryCognition → from engine.industry.schemas import IndustryCognition
```

- [x] **Step 5: 更新 engine/arena/orchestrator.py, runner.py, memory.py**

检查并替换所有 `from agent.` 和 `from data_engine` 等 import。

- [x] **Step 6: 验证 arena 层 import**

```bash
cd backend && .venv/bin/python -c "
from engine.arena.schemas import Blackboard
from engine.arena.data_fetcher import DataFetcher
print('Arena OK')
"
```
Expected: Arena OK

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: 更新 arena 层 import 路径（debate/judge/data_fetcher）"
```

### Task 11: 更新接口层 import（api, mcpserver, main.py）

**Files:**
- Modify: `backend/main.py`
- Modify: `backend/api/routes/debate.py`
- Modify: `backend/api/routes/analysis.py`
- Modify: `backend/api/routes/chat.py`
- Modify: `backend/mcpserver/tools.py`
- Modify: `backend/mcpserver/server.py`

- [x] **Step 1: 更新 backend/main.py**

替换所有路由 import：
```
from data_engine.routes import router as data_router       → from engine.data.routes import router as data_router
from cluster_engine.routes import router as cluster_router → from engine.cluster.routes import router as cluster_router
from quant_engine.routes import router as quant_router     → from engine.quant.routes import router as quant_router
from info_engine.routes import router as info_router       → from engine.info.routes import router as info_router
from expert.routes import router as expert_router, ...     → from engine.expert.routes import router as expert_router, ...
from industry_engine.routes import router as industry_router → from engine.industry.routes import router as industry_router
from quant_engine import get_quant_engine                  → from engine.quant import get_quant_engine
from cluster_engine import get_cluster_engine              → from engine.cluster import get_cluster_engine
from data_engine import get_data_engine                    → from engine.data import get_data_engine
```

- [x] **Step 2: 更新 backend/api/routes/debate.py**

```
from agent.schemas import Blackboard           → from engine.arena.schemas import Blackboard
from agent import get_orchestrator             → from engine.arena import get_orchestrator
from agent.debate import run_debate            → from engine.arena.debate import run_debate
from expert.routes import _expert_agent        → from engine.expert.routes import _expert_agent
from agent.judge import JudgeRAG               → from engine.arena.judge import JudgeRAG
from data_engine import get_data_engine        → from engine.data import get_data_engine
```

- [x] **Step 3: 更新 backend/api/routes/analysis.py**

```
from agent.schemas import AnalysisRequest      → from engine.arena.schemas import AnalysisRequest
from agent import get_orchestrator             → from engine.arena import get_orchestrator
```

- [x] **Step 4: 更新 backend/mcpserver/tools.py**

```
from data_engine.precomputed import load_profiles → from engine.data.precomputed import load_profiles
from quant_engine.predictor import FACTOR_DEFS    → from engine.quant.predictor import FACTOR_DEFS
from quant_engine.factor_backtest import ...      → from engine.quant.factor_backtest import ...
from quant_engine import get_quant_engine         → from engine.quant import get_quant_engine
from info_engine import get_info_engine           → from engine.info import get_info_engine
```

- [x] **Step 5: 更新 backend/mcpserver/server.py**

```
from expert.engine_experts import get_expert_profiles → from engine.expert.engine_experts import get_expert_profiles
```

- [x] **Step 6: 全量验证 — 启动后端**

```bash
cd backend && .venv/bin/python -c "
import main
print('main.py import OK')
"
```
Expected: main.py import OK

- [x] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: 更新接口层 import 路径（main/api/mcpserver）"
```

---

## Chunk 5: 测试合并

### Task 12: 合并测试目录

**Files:**
- Create: `tests/unit/`
- Create: `tests/integration/`
- Move: `backend/tests/*.py` → `tests/unit/`
- Move: `backend/tests/agent/` → `tests/unit/agent/`
- Move: `backend/tests/expert/` → `tests/unit/expert/`
- Move: `backend/tests/llm/` → `tests/unit/llm/`
- Move: `backend/tests/mcpserver/` → `tests/unit/mcpserver/`
- Move: 根目录 `tests/*.py` → `tests/integration/`
- Modify: `tests/conftest.py`

- [x] **Step 1: 创建目标目录**

```bash
mkdir -p tests/unit tests/integration
```

- [x] **Step 2: 移动根目录集成测试到 tests/integration/**

```bash
git mv tests/test_*.py tests/integration/
git mv tests/conftest.py tests/conftest.py.bak  # 暂存，后面重写
```

- [x] **Step 3: 移动 backend/tests/ 内容到 tests/unit/**

```bash
# 移动子目录
git mv backend/tests/agent tests/unit/agent
git mv backend/tests/expert tests/unit/expert
git mv backend/tests/llm tests/unit/llm
git mv backend/tests/mcpserver tests/unit/mcpserver

# 移动根级测试文件
git mv backend/tests/test_*.py tests/unit/
git mv backend/tests/conftest.py tests/unit/conftest.py.old  # 暂存
```

- [x] **Step 4: 清理 backend/tests/ 空目录**

```bash
rm -rf backend/tests/
```

- [x] **Step 5: 重写 tests/conftest.py（统一入口）**

```python
import sys
from pathlib import Path

# 将 backend/ 加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
```

- [x] **Step 6: 创建 tests/unit/conftest.py**

```python
# 单元测试的 conftest — 继承根 conftest 的 sys.path 注入
# 如果有 unit 专用的 fixture，放在这里
```

检查 `tests/unit/conftest.py.old` 中是否有需要保留的 fixture，如有则迁移到新 conftest.py 中，然后删除 `.old` 文件。

- [x] **Step 7: 创建 tests/integration/conftest.py**

```python
# 集成测试的 conftest — 继承根 conftest 的 sys.path 注入
# 如果有 integration 专用的 fixture，放在这里
```

检查 `tests/conftest.py.bak` 中是否有需要保留的 fixture，如有则迁移，然后删除 `.bak` 文件。

- [x] **Step 8: 更新所有测试文件的 import 路径**

测试文件中的 import 需要按照 Chunk 4 的映射表更新：

```
from agent.schemas import ...           → from engine.arena.schemas import ...
from agent.debate import ...            → from engine.arena.debate import ...
from agent.memory import AgentMemory    → from engine.arena.memory import AgentMemory
from agent.data_fetcher import ...      → from engine.arena.data_fetcher import ...
from agent.runner import ...            → from engine.arena.runner import ...
from agent.orchestrator import ...      → from engine.arena.orchestrator import ...
from expert.agent import ...            → from engine.expert.agent import ...
from expert.schemas import ...          → from engine.expert.schemas import ...
from expert.knowledge_graph import ...  → from engine.expert.knowledge_graph import ...
from expert.tools import ...            → from engine.expert.tools import ...
from expert.personas import ...         → from engine.expert.personas import ...
from expert.routes import ...           → from engine.expert.routes import ...
from data_engine.store import ...       → from engine.data.store import ...
from info_engine.schemas import ...     → from engine.info.schemas import ...
from info_engine.engine import ...      → from engine.info.engine import ...
from info_engine.sentiment import ...   → from engine.info.sentiment import ...
from info_engine.event_assessor import ... → from engine.info.event_assessor import ...
from quant_engine.predictor import ...  → from engine.quant.predictor import ...
from quant_engine.factor_backtest import ... → from engine.quant.factor_backtest import ...
from quant_engine.engine import ...     → from engine.quant.engine import ...
from quant_engine.indicators import ... → from engine.quant.indicators import ...
from quant_engine.routes import ...     → from engine.quant.routes import ...
from rag.store import ...               → from engine.arena.rag.store import ...
from rag.schemas import ...             → from engine.arena.rag.schemas import ...
from rag import ...                     → from engine.arena.rag import ...
from mcpserver.server import ...        → from mcpserver.server import ...（不变）
```

同时删除测试文件中所有 `sys.path.insert(0, ...)` 行 — 现在由根 conftest.py 统一处理。

- [x] **Step 9: 验证测试可运行**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
backend/.venv/bin/python -m pytest tests/ --collect-only 2>&1 | tail -5
```
Expected: 能收集到测试用例，无 import 错误

- [x] **Step 10: Commit**

```bash
git add -A
git commit -m "refactor: 合并测试目录到 tests/unit + tests/integration"
```

---

## Chunk 6: 脚本 + Docker + 文档

### Task 13: 创建 Shell 脚本

**Files:**
- Create: `scripts/setup.sh`
- Create: `scripts/setup.bat`
- Create: `scripts/start.sh`
- Create: `scripts/start.bat`

- [x] **Step 1: 创建 scripts/ 目录**

```bash
mkdir -p scripts
```

- [x] **Step 2: 创建 scripts/setup.sh**

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo "=== StockTerrain 环境配置 ==="

# 检测 Python 3.10+
if ! command -v python3 &>/dev/null; then
    echo "❌ 未找到 python3，请先安装 Python 3.10+"
    exit 1
fi
PY_VER=$(python3 -c "import sys; v=sys.version_info; print(f'{v.major}.{v.minor}')")
PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    echo "❌ Python 版本 $PY_VER 过低，需要 3.10+"
    exit 1
fi
echo "✅ Python $PY_VER"

# 检测 Node.js 18+
if ! command -v node &>/dev/null; then
    echo "❌ 未找到 node，请先安装 Node.js 18+"
    exit 1
fi
echo "✅ Node.js $(node -v)"

# 后端环境
echo ""
echo "--- 配置后端环境 ---"
cd backend
if [ ! -d .venv ]; then
    python3 -m venv .venv
    echo "  创建 .venv"
fi
.venv/bin/pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
echo "  依赖安装完成"
cd "$PROJECT_ROOT"

# 前端环境
echo ""
echo "--- 配置前端环境 ---"
cd frontend
npm install --silent
echo "  依赖安装完成"
cd "$PROJECT_ROOT"

# .env
if [ ! -f .env ]; then
    cp .env.example .env
    echo ""
    echo "📝 已创建 .env，请编辑填入 API Key"
fi

echo ""
echo "=== 配置完成 ==="
echo "运行 scripts/start.sh 启动服务"
```

- [x] **Step 3: 创建 scripts/setup.bat**

```bat
@echo off
setlocal

cd /d "%~dp0\.."

echo === StockTerrain 环境配置 ===

:: 检测 Python
where python >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 python，请先安装 Python 3.10+
    exit /b 1
)
echo ✅ Python 已安装

:: 检测 Node.js
where node >nul 2>&1
if errorlevel 1 (
    echo ❌ 未找到 node，请先安装 Node.js 18+
    exit /b 1
)
echo ✅ Node.js 已安装

:: 后端环境
echo.
echo --- 配置后端环境 ---
cd backend
if not exist .venv (
    python -m venv .venv
    echo   创建 .venv
)
.venv\Scripts\pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
echo   依赖安装完成
cd ..

:: 前端环境
echo.
echo --- 配置前端环境 ---
cd frontend
call npm install --silent
echo   依赖安装完成
cd ..

:: .env
if not exist .env (
    copy .env.example .env >nul
    echo.
    echo 📝 已创建 .env，请编辑填入 API Key
)

echo.
echo === 配置完成 ===
echo 运行 scripts\start.bat 启动服务
```

- [x] **Step 4: 创建 scripts/start.sh**

```bash
#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# 检查环境
[ -d backend/.venv ] || { echo "❌ 请先运行 scripts/setup.sh"; exit 1; }
[ -d frontend/node_modules ] || { echo "❌ 请先运行 scripts/setup.sh"; exit 1; }

echo "=== 启动 StockTerrain ==="

# 后端
cd "$PROJECT_ROOT/backend"
.venv/bin/python main.py &
BACKEND_PID=$!
cd "$PROJECT_ROOT"

# 等待后端就绪
echo "等待后端启动..."
for i in $(seq 1 30); do
    if curl -sf http://localhost:8000/api/v1/health >/dev/null 2>&1; then
        echo "✅ 后端: http://localhost:8000"
        break
    fi
    sleep 1
done

# 前端
cd "$PROJECT_ROOT/frontend"
npm run dev &
FRONTEND_PID=$!
cd "$PROJECT_ROOT"

echo "✅ 前端: http://localhost:3000"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 优雅关闭
cleanup() {
    echo ""
    echo "正在停止服务..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "已停止"
}
trap cleanup INT TERM
wait
```

- [x] **Step 5: 创建 scripts/start.bat**

```bat
@echo off
setlocal

cd /d "%~dp0\.."

if not exist backend\.venv (
    echo ❌ 请先运行 scripts\setup.bat
    exit /b 1
)
if not exist frontend\node_modules (
    echo ❌ 请先运行 scripts\setup.bat
    exit /b 1
)

echo === 启动 StockTerrain ===

:: 后端
start "StockTerrain-Backend" /D backend .venv\Scripts\python main.py

:: 等待后端
echo 等待后端启动...
:wait_backend
timeout /t 1 /nobreak >nul
curl -sf http://localhost:8000/api/v1/health >nul 2>&1
if errorlevel 1 goto wait_backend
echo ✅ 后端: http://localhost:8000

:: 前端
start "StockTerrain-Frontend" /D frontend cmd /c "npm run dev"

echo ✅ 前端: http://localhost:3000
echo.
echo 关闭此窗口或按 Ctrl+C 停止
pause
```

- [x] **Step 6: 设置执行权限**

```bash
chmod +x scripts/setup.sh scripts/start.sh
```

- [x] **Step 7: Commit**

```bash
git add scripts/
git commit -m "feat: 新增跨平台一键配置和启动脚本"
```

### Task 14: 创建 Docker 配置

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `docker-compose.yml`

- [x] **Step 1: 创建 backend/Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app/backend

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装 Python 依赖
COPY pyproject.toml .
COPY . .
RUN pip install . -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir

EXPOSE 8000
CMD ["python", "main.py"]
```

- [x] **Step 2: 创建 frontend/Dockerfile**

```dockerfile
FROM node:20-slim

WORKDIR /app/frontend

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000
CMD ["npm", "run", "dev"]
```

- [x] **Step 3: 创建 docker-compose.yml**

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

- [x] **Step 4: 更新 .gitignore 添加 Docker 相关忽略**

在 `.gitignore` 中添加：
```
# Docker
docker-compose.override.yml
```

- [x] **Step 5: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile docker-compose.yml .gitignore
git commit -m "feat: 新增 Docker Compose 配置"
```

### Task 15: 更新文档

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `DEPLOYMENT.md`
- Modify: `.github/workflows/deploy-pages.yml`

- [x] **Step 1: 更新 CLAUDE.md**

全文替换：
- `engine/` → `backend/`（目录引用）
- `web/` → `frontend/`（目录引用）
- `cd engine` → `cd backend`
- `cd web` → `cd frontend`
- `engine/data_engine/` → `backend/engine/data/`
- `engine/cluster_engine/` → `backend/engine/cluster/`
- 更新模块路径描述，反映新的 `backend/engine/` 结构
- 更新 MCP 使用须知中的路径

- [x] **Step 2: 更新 README.md**

- 更新项目结构描述
- 更新安装和运行命令（新增 `scripts/setup.sh` 和 `scripts/start.sh`）
- 新增 Docker 部署说明
- 替换所有 `cd engine` → `cd backend`，`cd web` → `cd frontend`

- [x] **Step 3: 更新 DEPLOYMENT.md**

- 更新所有路径引用
- 新增 Docker Compose 部署章节

- [x] **Step 4: 更新 .github/workflows/deploy-pages.yml**

```
working-directory: web → working-directory: frontend
cache-dependency-path: web/package-lock.json → frontend/package-lock.json
```

- [x] **Step 5: Commit**

```bash
git add CLAUDE.md README.md DEPLOYMENT.md .github/
git commit -m "docs: 更新所有文档路径引用，新增 Docker 部署说明"
```

### Task 16: 端到端验证

- [x] **Step 1: 验证后端启动**

```bash
cd backend && .venv/bin/python main.py &
sleep 3
curl -s http://localhost:8000/api/v1/health | head -20
```
Expected: `{"status":"ok",...}`

- [x] **Step 2: 验证 MCP Server**

重启 MCP（`/mcp`），然后调用一个工具验证：
```
mcp__stockterrain__query_market_overview
```
Expected: 返回市场概览数据

- [x] **Step 3: 验证前端启动**

```bash
cd frontend && npm run dev &
sleep 5
curl -s http://localhost:3000 | head -5
```
Expected: 返回 HTML

- [x] **Step 4: 运行全量测试**

```bash
cd /Users/swannzhang/Workspace/AIProjects/A_Claude
backend/.venv/bin/python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: 测试通过（允许部分需要 LLM 的测试 skip）

- [x] **Step 5: 停止服务，最终 Commit**

```bash
# 停止后台服务
kill %1 %2 2>/dev/null || true

git add -A
git commit -m "feat: 项目重构完成 — backend/frontend 结构 + 一键部署"
```