# 🗺️ StockScape Roadmap

> A股多维聚类 3D 地形可视化平台 — 版本路线图
>
> 最后更新: 2026-03-15

---

## ✅ 已完成 (Released)

### v1.0 — 基础框架 `2026-03 初`
- [x] FastAPI 后端 + Next.js 前端基础架构
- [x] AKShare / BaoStock / Tushare Pro 三级数据源
- [x] HDBSCAN 聚类 + UMAP 2D 降维
- [x] RBF 薄板样条插值生成地形网格
- [x] React Three Fiber 3D 地形渲染
- [x] DuckDB 本地存储 + Redis 可选缓存
- [x] WebSocket 实时推送
- [x] Z 轴指标切换（涨跌幅/换手率/成交量/成交额/PE/PB）

### v2.0 — 多指标预计算 + Wendland 核密度场
- [x] 多指标一次性预计算（Z 轴切换零延迟）
- [x] Wendland C2 紧支撑核密度地形（替代 RBF 全局插值）
- [x] 自适应影响半径（密集区细腻/稀疏区扩展）
- [x] `radius_scale` 后端参数支持
- [x] XY 缩放因子 (`xyScale`) 解决 UMAP 空间拥挤

### v3.0 — 产业链拓扑聚类 + UI 重构
- [x] BGE 语义嵌入 (`bge-base-zh-v1.5`, 768 维)
- [x] 产业链图谱嵌入（40+ 条供应链规则，自动标注产业链标签）
- [x] 语义加权文本构建（核心业务 × 2 提高注意力权重）
- [x] 退市股票自动过滤
- [x] 三层特征融合（嵌入 + 行业 one-hot + 数值特征）+ 运行时权重调节
- [x] HDBSCAN `leaf` 模式细粒度聚类
- [x] 同簇关联股票面板（簇内 KDTree 近邻查询）
- [x] Sidebar 双面板布局（左核心操作 + 右辅助设置）
- [x] 所有面板可折叠/展开，带动画过渡

### v3.1 — 地形稳定性 + 性能优化
- [x] UMAP 布局缓存复用（参数不变 + 股票集重叠 > 95% 时跳过重计算）
- [x] Numba 并发锁保护（防止多 UMAP 同时运行崩溃）
- [x] TerrainMesh v3.0: 自建 BufferGeometry 替代 planeGeometry + rotation
- [x] 三角形 CCW 缠绕顺序修复
- [x] 着色器 `dFdx/dFdy` 法线计算 + 双面渲染

### v4.0 — 颜色系统 + 静态部署
- [x] 红涨绿跌连续渐变着色器 + 零位透明过渡
- [x] GitHub Pages 静态部署支持（快照导出 + 静态加载模式）
- [x] 球体着色始终使用涨跌幅（不受 Z 轴指标影响）

### v5.0 — 球体拍平 + 历史回放
- [x] 球体拍平动画（lerp 逐帧插值过渡到 Y=0 平面）
- [x] 7 天历史回放（逐日 Wendland 插值生成地形帧）
- [x] DuckDB 每日快照自动积累
- [x] 回放控件：播放/暂停/步进/速度/时间轴滑块
- [x] History API 降低并发 + 超时保护

### v6.0 — 地形精细调控 `2026-03-12`
- [x] **核平滑半径滑块** (`radius_scale`: 0.1 ~ 6.0)
  - 控制 Wendland C2 核函数的影响半径缩放因子
  - 极小值 → 几乎无平滑，可观察单个股票点的影响
  - 极大值 → 高度平滑，地形连续圆润
  - 调节后点击"应用核半径"按钮触发重算
- [x] **XY 整体缩放滑块** (`xyScale`: 0.5 ~ 5.0)
  - 实时放大/缩小地形在 XZ 平面的展布范围
  - 不需要重新计算后端，前端即时生效
- [x] **X / Y 轴独立比例因子** (`xScaleRatio` / `yScaleRatio`: 0.3 ~ 3.0)
  - 可以拉伸/压缩某一个轴方向
  - 实时生效，方便观察特定方向的聚类分布
  - 地形网格 + 股票球体 + Hover/选中标签全部同步

---

## 🔜 计划中 (Planned)

### v7.0 — 多引擎架构 + LLM 基础设施 `2026-03-14`
- [x] DataEngine / ClusterEngine / QuantEngine / InfoEngine 模块化分离
- [x] `LLMCapability` 统一 LLM 接口（complete / classify / extract + 透明缓存）
- [x] DuckDB 新增 `shared.llm_cache` + `shared.chat_history` 表
- [x] InfoEngine：新闻/公告抓取 + 情感分析（LLM 或规则降级）
- [x] QuantEngine：RSI / MACD / 布林带 / 13 因子 IC 回测
- [x] Agent 层：Orchestrator + run_agent 多角色并行推理
- [x] RAG 增强：ChromaDB 历史分析报告存储与检索，自动注入分析上下文
- [x] `DataFetcher.fetch_by_request()` + `ACTION_DISPATCH` 统一路由
- [x] 专家辩论系统：5 角色辩论 + Blackboard 黑板协作 + JudgeVerdict 裁决
- [x] MCP Server 扩展：debate 工具集

### v8.0 — 交互增强
- [ ] 股票搜索框（模糊匹配代码/名称，定位到 3D 位置并高亮）
- [ ] 聚类区域悬浮标签（显示簇内主要行业/概念）
- [ ] 点击聚类区域展示所有成员股票列表
- [ ] 键盘快捷键（空格暂停回放 / ESC 取消选中 / WASD 移动相机）

### v8.0 — 数据增强
- [ ] 实时行情自动刷新（WebSocket 推送 / 定时轮询）
- [ ] 北向资金净流入/出覆盖层
- [ ] 龙虎榜数据层
- [ ] 行业热力图 overlay（半透明行业边界区域）
- [ ] 自定义自选股高亮组

### v9.0 — 算法迭代
- [ ] 多粒度聚类探索（支持在 HDBSCAN 聚类树上交互选择粒度）
- [ ] 时序嵌入（引入 T 天收益率序列做时序相似性降维）
- [ ] 供应链传导可视化（产业链上下游关系的有向边）
- [ ] LLM 辅助分析（接入大模型解读聚类含义和市场趋势）✅ 已在 v7.0 完成

### v10.0 — 性能 & 部署
- [ ] WebGPU 加速渲染（替代 WebGL）
- [ ] 地形 LOD（远处低分辨率，近处高分辨率）
- [ ] 增量式 UMAP（新股票插入无需全量重算）
- [ ] Docker 一键部署镜像
- [ ] 移动端适配（触摸手势 + 响应式 UI）

---

## 💡 远期探索 (Exploration)

- 多市场对比（沪深/港股/美股三维地形并排）
- VR/AR 沉浸式浏览（WebXR 支持）
- 自定义特征拼装器（用户上传自定义因子参与聚类）
- 社区协作标注（用户标注有趣的聚类区域）

---

## 📊 版本时间线

```
v1.0  ████████  基础框架
v2.0  ████████  Wendland 核密度
v3.0  ████████  产业链拓扑
v3.1  ████████  地形稳定性
v4.0  ████████  颜色系统 + 部署
v5.0  ████████  历史回放
v6.0  ████████  精细调控
v7.0  ████████  多引擎 + LLM + RAG + 辩论系统  ← 当前版本
v8.0  ░░░░░░░░  交互增强
v9.0  ░░░░░░░░  数据增强
v10.0 ░░░░░░░░  算法迭代
v11.0 ░░░░░░░░  性能 & 部署
```

---

*This roadmap is a living document and may be updated as priorities evolve.*
