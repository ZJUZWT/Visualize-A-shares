# StockTerrain — A股多维聚类3D地形可视化平台

## 项目结构
- `engine/` — Python 后端 (FastAPI + DuckDB + HDBSCAN/UMAP 算法流水线)
- `web/` — Next.js 前端 (Three.js 3D 地形渲染)
- `data/precomputed/` — BGE 嵌入向量、公司概况 JSON

## 后端核心模块
- `engine/data_engine/` — 数据引擎 (行情拉取、DuckDB 持久化、公司概况)
  - `engine.py` DataEngine 门面类
  - `collector.py` 数据采集器 (Tencent/AKShare/BaoStock 三级降级)
  - `store.py` DuckDB 持久化
  - `routes.py` REST API `/api/v1/data/*`
- `engine/cluster_engine/` — 聚类引擎 (特征提取、聚类、降维、插值、预测)
  - `engine.py` ClusterEngine 门面类
  - `algorithm/pipeline.py` 算法流水线 (特征→聚类→降维→插值)
  - `algorithm/predictor_v2.py` 13因子预测器
  - `algorithm/factor_backtest.py` 因子 IC 回测
  - `routes.py` REST API `/api/v1/terrain/*`
- `engine/mcpserver/` — MCP Server (10 tools, stdio transport)
- `engine/llm/` — LLM 模块 (AI 聊天)

## 开发约定
- 中文注释和日志
- Loguru 日志框架
- DuckDB 单文件数据库，路径: `data/stockterrain.duckdb`
- `engine/main.py` 会将 engine/ 加入 sys.path
- MCP 包命名 `mcpserver` 而非 `mcp`，避免与 mcp SDK 冲突

## 运行
- 后端: `cd engine && python main.py` (端口 8000)
- 前端: `cd web && npm run dev` (端口 3000)
- MCP: `cd engine && python -m mcpserver` (stdio, 配置见 `.mcp.json`)
- 重建嵌入: `cd engine && python -m cluster_engine.preprocess.rebuild_bge`

## MCP 使用须知
- 使用 MCP 工具前必须先启动后端 (`cd engine && python main.py`)
- MCP Server 通过 REST API 与后端通信，后端未启动时会降级为 DuckDB 离线快照（数据非实时）
- `.mcp.json` 使用相对路径，clone 后可直接使用

## 自验证闭环
Claude 具备通过 MCP 工具完成开发→验证闭环的能力，修改代码后应主动验证：
1. 启动后端: `cd engine && python3 main.py` (后台运行)
2. 通过 MCP 工具调用 API 验证功能（如 `get_terrain_data`、`search_stock`）
3. 检查返回数据结构、聚类质量指标、字段完整性等
4. 不需要等用户手动测试，能自主完成端到端验证
