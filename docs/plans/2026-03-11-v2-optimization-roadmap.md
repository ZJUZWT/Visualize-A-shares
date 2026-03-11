# 🏔️ StockTerrain v2.0 — 优化路线图

## 核心优化方案 (4 大方向)

> **编写日期**：2026-03-11
> **前置条件**：v1.0 MVP 已完成基础功能（聚类 + 降维 + RBF 插值 + R3F 渲染）
> **优化目标**：更好的行业识别、更真实的地形渲染、更美观的 UI、更流畅的交互体验

---

## 一、混合聚类预处理 — 申万行业 + text2vec 语义嵌入

### 1.1 核心需求

**用户痛点**：当前仅用 6 维数值特征（pe_ttm, pb, total_mv 等）做 HDBSCAN 聚类，无法区分行业。关键需求是发现**跨行业关联企业**（如比亚迪：汽车+电池+半导体；宁德时代：电池+矿+新能源），这类企业恰恰是投资重点关注对象。

**核心洞察**：单一申万行业分类无法捕捉跨界关联性，而文本嵌入能把"电池+矿+电"等多维语义关系编码到向量空间中。

### 1.2 方案：三层特征融合 + 预处理硬编码

```
final_vector = concat(
    industry_onehot × 3.0,     # 31维 × 3 = 93维（申万行业分类）
    text_embedding × 2.0,       # 384维 × 2 = 768维（text2vec 语义嵌入）
    numeric_features × 1.0      # 6维 × 1 = 6维（财务数值特征）
)
# 总维度: 93 + 768 + 6 = 867维
# → PCA 降到 50 维 → UMAP 降到 2D
```

#### 第 1 层 — 申万行业 one-hot（权重 ×3）
- 数据来源：AKShare `stock_board_industry_name_em()` + `stock_board_industry_cons_em()`
- 31 维 one-hot 向量，确保同行业基础聚拢
- 作为"锚点"：银行就是银行，不会乱跑

#### 第 2 层 — text2vec 语义嵌入（权重 ×2）
- 模型：`shibing624/text2vec-base-chinese`（384 维，~400MB）
- 编码内容：公司经营范围 + 主营业务描述
- 数据来源：AKShare `stock_individual_info_em()` 获取公司简介
- **关键效果**：宁德时代（电池+矿+新能源）和比亚迪（汽车+电池）会在向量空间中靠近，即使申万分类不同
- **全部预处理**：离线跑一次，输出 `data/stock_embeddings.npz`（~50MB），运行时直接加载

#### 第 3 层 — 数值特征（权重 ×1）
- pe_ttm, pb, total_mv, circ_mv, turnover_rate, pct_chg
- 区分同行业内的大盘 vs 小盘

### 1.3 预处理流程

```
预处理脚本 (run once):
  1. AKShare 拉取全市场股票列表 + 申万行业分类 → industry_mapping.json
  2. AKShare 拉取每只股票的公司简介/经营范围
  3. text2vec-base-chinese 编码 → 384维向量
  4. 合并三层特征 → PCA 降到 50 维
  5. UMAP 降到 2D → stock_layout.json
  6. HDBSCAN 聚类 → cluster_labels.json
  
输出文件:
  data/precomputed/industry_mapping.json     # {股票代码 → 行业ID}
  data/precomputed/stock_embeddings.npz      # text2vec 嵌入向量
  data/precomputed/stock_layout.json         # UMAP 2D 坐标
  data/precomputed/cluster_labels.json       # 聚类标签
```

### 1.4 实现清单

- [ ] 编写预处理脚本 `engine/preprocess/build_embeddings.py`
- [ ] 申万行业分类拉取 + one-hot 编码
- [ ] text2vec-base-chinese 模型加载 + 批量编码
- [ ] 三层特征融合 + PCA + UMAP + HDBSCAN 流水线
- [ ] 输出预计算文件到 `data/precomputed/`
- [ ] 修改 `algorithm/pipeline.py` 加载预计算结果

---

## 二、数据驱动的热力地形 — Wendland 紧支撑核 + 自适应影响半径

### 2.1 核心需求

**用户痛点**：
1. 高斯卷积会让没有数据的空白区域"凭空冒出地形"
2. 高斯卷积会磨平板块内部的剧变信号（涨停/跌停并存的情况）
3. 跨行业企业不应该被硬塞进某个板块的"岛屿"

**核心洞察**：不需要板块概念，每只股票就是一个独立的"地形贡献源"，跨界企业在两个密集区之间自然形成"桥梁/山脊"。

### 2.2 方案：数据驱动的核密度地形

```
terrain[x][y] = Σ stock_i.z_value × W(distance(x,y, stock_i), r_i)
```

#### 核函数：Wendland C2 紧支撑核

```python
def wendland_c2(d, r):
    """
    Wendland C2 紧支撑核函数
    - d: 距离
    - r: 影响半径
    - 超出半径贡献为 0（不会无限扩散，比高斯核好）
    """
    if d >= r:
        return 0.0
    q = d / r
    return ((1 - q) ** 4) * (4 * q + 1)
```

**优势**：
- ✅ 紧支撑：超出影响半径就是 0，空白区域自然为海面
- ✅ C2 连续：地形曲面平滑，无突变
- ✅ 计算高效：只需计算影响半径内的点

#### 自适应影响半径

```python
r_i = k × dist_to_5th_neighbor(stock_i)
```

- **密集区域**（如银行板块）：5th 近邻很近 → r_i 小 → 地形细节丰富，涨停跌停都能看到
- **稀疏区域**（如跨界企业周围）：5th 近邻较远 → r_i 大 → 单只股票也能撑起一小块地形
- **跨界企业**：在两个密集区之间，自然形成"桥"或"山脊"连接两个板块

#### 前端滑块

- 提供全局缩放因子 `k`（影响半径倍率）滑块
  - k 小 → 每只股票是独立山峰（火山群）
  - k 大 → 相近的股票连成连绵山脉

### 2.3 视觉效果

```
     银行板块         跨界企业          新能源板块
    ┌────────┐                      ┌────────┐
    │ /\/\/\ │      /\              │ /\  /\ │
    │/ 密集  \│    /  \  ← 比亚迪    │/  \/  \│
    │ 小山群  │___/    \____________│ 山脉   │
    │        │   桥梁/山脊连接       │        │
    └────────┘                      └────────┘
              ↑ 海面（无数据区域自然为0）
```

### 2.4 实现清单

- [ ] 编写 Wendland C2 核函数
- [ ] 实现自适应影响半径计算（KNN 第 5 近邻距离）
- [ ] 替换 `interpolation.py` 中的 RBF 插值为 Wendland 核密度场
- [ ] 后端 API 支持 `radius_scale` 参数（影响半径倍率）
- [ ] 前端添加"地形连续度"滑块
- [ ] 海面检测：地形值低于阈值的区域标记为海面

---

## 三、清爽简约渲染风格 — MiroFish 风格升级

### 3.1 核心需求

**用户痛点**：黑色背景 + 真实感光照难看，UI 不够精致。
**目标风格**：清爽、简约、现代化，参考 MiroFish 数据仪表盘风格。

### 3.2 配色方案

| 元素 | 当前（v1.0） | 优化后（v2.0） |
|------|------------|--------------|
| 背景 | 纯黑 #000 | 浅灰白渐变 #F8FAFE → #EEF2F7 |
| 地形色带 | 绿→黄→红（真实感） | 柔和渐变：薄荷绿 → 天蓝 → 薰衣草紫 |
| 光照 | 真实感 PBR（MeshStandardMaterial） | 扁平化 Toon Shading（MeshToonMaterial） |
| 网格线 | 无 | 轻微的白色半透明网格线（Low-poly 感） |
| 标签 | 白色文字 | 深灰文字 + 圆角白底卡片 |
| UI 面板 | 半透明黑底 | 白色毛玻璃面板 + 柔和阴影 |
| 强调色 | #00BCD4（科技青） | #4F8EF7（清爽蓝）|
| 涨 | 红色 #E53935 | 珊瑚红 #FF6B6B |
| 跌 | 绿色 #00C853 | 薄荷绿 #51CF66 |
| 海面 | 无 | 浅蓝色半透明平面 + 微波纹动画 |

### 3.3 Three.js 渲染调整

- `MeshStandardMaterial` → `MeshToonMaterial`（卡通着色）
- `scene.background` → 柔和渐变色纹理
- 光照：柔和环境光 + 单方向光（无硬阴影）
- 地形颜色：自定义 `gradientMap` 实现柔和色带
- 添加海面平面（z=0，半透明蓝色 + 微波纹 shader）
- 标签改用 HTML overlay（更清晰、更美观）

### 3.4 UI 组件升级

- 整体主题从 Dark Mode 切换为 Light Mode
- 控制面板：白色底 + 毛玻璃效果（`backdrop-filter: blur(12px)`）
- 圆角统一 12px
- 阴影统一 `0 2px 8px rgba(0,0,0,0.08)`
- 字体：Inter（UI）+ 等宽字体（数据）
- 动画：添加柔和过渡动画（Framer Motion）

### 3.5 实现清单

- [ ] Three.js 材质从 StandardMaterial → ToonMaterial
- [ ] 场景背景改为浅色渐变
- [ ] 添加海面平面组件（z=0 半透明蓝色 + 波纹动画）
- [ ] 重写 GLSL 着色器适配浅色主题
- [ ] UI 主题从 Dark → Light（globals.css 重写）
- [ ] 控制面板毛玻璃效果
- [ ] 股票节点和标签样式更新
- [ ] 光照体系调整（柔和环境光）

---

## 四、Z 轴指标一次性预计算 — 零延迟切换

### 4.1 核心需求

**用户痛点**：每次切换 Z 轴指标要重新请求后端 + 重新计算，体验卡顿。

### 4.2 方案：一次性返回所有指标网格

```
当前：前端选择指标 → 请求后端 → 后端计算 → 返回单个网格（慢）
优化：前端启动 → 一次请求 → 后端计算所有指标 → 返回全部网格
      切换指标 → 纯前端切换，零延迟
```

#### 后端改动

`/api/terrain` 接口一次性返回所有指标的网格数据：

```json
{
  "grid_x": [...],
  "grid_y": [...],
  "grids": {
    "pct_chg": [[...], ...],
    "turnover_rate": [[...], ...],
    "volume": [[...], ...],
    "amount": [[...], ...],
    "pe_ttm": [[...], ...],
    "pb": [[...], ...]
  },
  "stocks": [...]
}
```

#### 数据量评估

- 100×100 网格 × 6 指标 = 60,000 个浮点数
- 原始 ≈ 480KB → gzip 后 ≈ 100KB
- **完全可接受**

#### 前端改动

- `useTerrainStore` 存储所有指标的网格 map
- 切换 Z 轴指标时，直接从 store 取对应网格数据更新 mesh geometry
- 地形渲染也在前端做，切换指标时重新应用当前影响半径参数
- **零延迟切换体验**

### 4.3 实现清单

- [ ] 后端 `interpolation.py` 支持批量生成多指标网格
- [ ] 后端 API 响应格式改为 `grids: { metric_name: grid_data }`
- [ ] 前端 `useTerrainStore` 存储 `Map<string, number[][]>`
- [ ] 前端切换指标时直接 swap 网格数据
- [ ] 添加指标切换动画（地形高度平滑过渡）

---

## 五、实施优先级与时间线

```
Phase 2.1 — 聚类预处理 [优先级最高] [~1周]
  └→ 预处理脚本 + 三层特征融合 + 预计算文件输出
  └→ 修改 pipeline 加载预计算结果

Phase 2.2 — 地形渲染算法 [优先级高] [~1周]
  └→ Wendland C2 核函数 + 自适应影响半径
  └→ 替换 RBF 插值

Phase 2.3 — Z 轴预计算 [优先级中] [~3天]
  └→ 后端批量返回 + 前端 store 改造

Phase 2.4 — 渲染风格升级 [优先级中] [~1周]
  └→ 浅色主题 + ToonMaterial + 海面 + UI 美化
```

---

*"不是分板块看市场，而是看市场中各个板块之间的连接与桥梁。"*
