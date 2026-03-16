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

## 环境安装
```bash
cd engine
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]" -i https://pypi.tuna.tsinghua.edu.cn/simple
```
> torch + sentence-transformers 较大（~2GB），仅重建嵌入时需要，日常开发可考虑移至 optional dependencies。

## 运行
- 后端: `cd engine && .venv/bin/python main.py` (端口 8000)
- 前端: `cd web && npm run dev` (端口 3000)
- MCP: `cd engine && .venv/bin/python -m mcpserver` (stdio, 配置见 `.mcp.json`)
- 重建嵌入: `cd engine && .venv/bin/python -m cluster_engine.preprocess.rebuild_bge`

## MCP 使用须知
- 使用 MCP 工具前必须先启动后端 (`cd engine && python main.py`)
- MCP Server 通过 REST API 与后端通信，后端未启动时会降级为 DuckDB 离线快照（数据非实时）
- `.mcp.json` 使用相对路径，clone 后可直接使用

## 流式优先 & 超时策略（核心架构原则）

本项目是一个**全链路流式系统**。LLM Provider 层已完整支持 `chat()` (非流式) 和 `chat_stream()` (流式) 两种接口。

### 原则
1. **所有 LLM 调用优先使用 `chat_stream()`**，即使不需要逐 token 推送到前端，也应使用流式收集模式（`async for token in llm.chat_stream(...)`），这样只要后端还在产出 token，链路就保持活跃。
2. **timeout 只用于检测"链路已死"**——即连续 N 秒没有收到任何新 token，说明上游已经卡死或断开。**绝不用 timeout 限制正常工作时间**。数据量大、prompt 长导致响应慢是正常的，不应因此被超时截断。
3. **心跳超时（token-level timeout）代替总超时（wall-clock timeout）**：
   - ✅ 正确做法：每收到一个 token 重置计时器，连续 30s 无 token → 判定死连接
   - ❌ 错误做法：`asyncio.wait_for(llm.chat(...), timeout=30)` — 这会在 30s 后无论是否还在工作都强制中断
4. **数据越大辩论越好**——不应因为数据量大就放弃请求，大数据量恰恰能让辩论质量更高。

### 标准模式
```python
# 流式收集（不推送 token 到前端，但保持链路活跃）
chunks: list[str] = []
async for token in llm.chat_stream([ChatMessage(role="user", content=prompt)]):
    chunks.append(token)
raw = "".join(chunks)

# 流式推送（逐 token 推送 SSE 事件到前端）
async for token in llm.chat_stream(messages):
    buffer += token
    yield sse("debate_token", {"role": role, "token": token})
```

### 仅在以下场景使用 `llm.chat()` + 固定超时
- 辅助性的极短 LLM 调用（如提取 JSON 字段），且失败有 fallback 兜底
- 即便如此，也应记录清晰的日志区分超时 vs 其他错误

## 自验证闭环
Claude 具备通过 MCP 工具完成开发→验证闭环的能力，修改代码后应主动验证：
1. 启动后端: `cd engine && python3 main.py` (后台运行)
2. 通过 MCP 工具调用 API 验证功能（如 `get_terrain_data`、`search_stock`）
3. 检查返回数据结构、聚类质量指标、字段完整性等
4. 不需要等用户手动测试，能自主完成端到端验证
