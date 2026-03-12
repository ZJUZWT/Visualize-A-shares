# 退市过滤 + 语义加权嵌入 + 相关股票面板 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 三件事：(1) 过滤退市/ST股票，(2) 重建嵌入——让营收相关语义获得更高权重以改善聚类质量，(3) 悬停/选中股票时显示同簇相关股票面板。

**Architecture:**
- 后端新增退市过滤层（在数据采集后、算法管线前），基于股票名称中"退市"关键词过滤
- 重写嵌入文本构造：将经营范围分为"核心业务"（产品/服务/收入相关）和"通用套话"两段，核心业务重复 2 次 → 模型天然给更高权重
- 前端新增 `RelatedStocksPanel` 组件：当用户悬停/选中某只股票时，从同 cluster 中按相关性排序展示关联股票列表

**Tech Stack:** Python (FastAPI, numpy, sentence-transformers), TypeScript (React, Zustand, R3F/drei)

---

## Task 1: 退市股票过滤（后端 collector 层）

**Files:**
- Modify: `engine/data/collector.py`
- Modify: `engine/data/sources/base.py`

**原理:**  
当前系统仅依赖 `price > 0` 自然过滤停牌股，但退市股可能还在交易（如退市整理期），且预计算 profiles 中也有 3 只退市股 + 155 只 ST 股（ST 保留，只过滤退市）。需要在两个层面过滤：
1. 预计算 profiles 中过滤（下一个 Task 处理）
2. 实时行情中过滤（本 Task）

### Step 1: 在 base.py 的 `_standardize_quotes()` 中添加退市过滤

在 `engine/data/sources/base.py` 的 `_standardize_quotes` 方法末尾（`price > 0` 过滤之后），追加：

```python
# 过滤退市股票（名称中包含"退市"或以"退"开头）
if "name" in df.columns:
    delist_mask = df["name"].str.contains("退市", na=False)
    n_delist = delist_mask.sum()
    if n_delist > 0:
        logger.info(f"过滤退市股票: {n_delist} 只")
        df = df[~delist_mask]
```

### Step 2: 在预计算流程中过滤退市股票

在 `engine/preprocess/build_embeddings.py` 的 `compute_embeddings` 函数中，准备文本前过滤：

```python
# 过滤退市股票
filtered_profiles = {
    code: p for code, p in profiles.items()
    if "退市" not in p.get("name", "")
}
logger.info(f"过滤退市股票: {len(profiles) - len(filtered_profiles)} 只")
```

然后用 `filtered_profiles` 代替 `profiles` 进行后续处理。

同样在 `rebuild_bge.py` 中做相同过滤。

---

## Task 2: 语义加权嵌入重建（核心改进）

**Files:**
- Modify: `engine/preprocess/build_embeddings.py` — `compute_embeddings()` 函数
- Modify: `engine/preprocess/rebuild_bge.py` — 同步修改
- 运行: `cd engine && python -m preprocess.rebuild_bge`

**问题分析:**
当前嵌入文本 = `"{行业} {经营范围全文}"`。经营范围(scope)包含大量无差别的法律套话（如"依法须经批准的项目"、"一般项目"、"货物进出口"），这些通用文本稀释了核心业务语义，导致聚类模糊。

例：
- 厦门钨业 scope 中"储能技术服务;新兴能源技术研发"被淹没在"金属矿石销售;有色金属合金制造;..."的海洋中
- 但它和宁德时代的关联（电池材料）恰恰在这些被稀释的关键词中

**解决方案: 结构化语义增强**

将经营范围智能分段，提取"核心营收关键词"并放大权重：

```python
def _build_weighted_text(industry: str, scope: str) -> str:
    """
    构建语义加权的嵌入文本
    
    策略：
    1. 从经营范围中提取"核心业务关键词"（产品名、技术名、服务名）
    2. 过滤掉通用法律套话
    3. 用"行业 + 核心关键词(重复) + 完整范围"的格式构建文本
       → 核心业务在文本中出现 2 次，BGE 自然赋予更高注意力权重
    """
    # ─── 通用套话正则（这些对区分公司毫无价值）───
    NOISE_PATTERNS = [
        r"依法须经批准的项目[^;；。]*[;；。]?",
        r"经相关部门批准后方可开展经营活动[^;；。]*[;；。]?",
        r"一般项目[:：]?",
        r"许可项目[:：]?",
        r"具体经营项目以相关部门批准文件或许可证件为准[^;；。]*[;；。]?",
        r"以上.*(?:不含|除外)[^;；。]*[;；。]?",
    ]
    
    # ─── 高价值业务关键词模式（产品、技术、服务 = 赚钱的东西）───
    REVENUE_KEYWORDS = [
        # 具体产品
        "电池", "锂", "钨", "稀土", "光伏", "芯片", "半导体",
        "新能源", "储能", "充电", "电力", "发电", "输电", "配电",
        "汽车", "整车", "发动机", "变速箱",
        "药品", "疫苗", "医疗器械", "诊断",
        "白酒", "啤酒", "乳制品", "饮料",
        "水泥", "钢铁", "煤炭", "石油", "天然气",
        "软件", "云计算", "人工智能", "大数据", "信息安全",
        "银行", "保险", "证券", "基金", "信托", "期货",
        "房地产", "物业", "商业地产",
        # 技术/服务
        "研发", "制造", "生产", "加工", "销售",
        "技术服务", "技术咨询", "工程",
    ]
    
    import re
    
    if not scope:
        return f"{industry}" if industry else "A股上市公司"
    
    # Step 1: 清洗 — 去除套话
    cleaned = scope
    for pattern in NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    
    # Step 2: 分句（按 ;；,，。 分割）
    segments = re.split(r'[;；,，。\n]+', cleaned)
    segments = [s.strip() for s in segments if len(s.strip()) >= 2]
    
    # Step 3: 识别核心营收段落（包含高价值关键词的句段）
    core_segments = []
    other_segments = []
    for seg in segments:
        is_core = any(kw in seg for kw in REVENUE_KEYWORDS)
        if is_core:
            core_segments.append(seg)
        else:
            other_segments.append(seg)
    
    # Step 4: 构建加权文本
    # 格式: "行业 | 核心业务: xxx; xxx | 经营范围: 全文"
    # 核心业务出现 2 次 → 语义权重 ×2
    parts = []
    if industry:
        parts.append(industry)
    
    if core_segments:
        core_text = ";".join(core_segments[:15])  # 最多 15 个核心段
        parts.append(f"核心业务:{core_text}")
    
    # 完整经营范围（已清洗，含核心+其他）
    full_cleaned = ";".join(segments[:30])  # 限制总段数
    parts.append(full_cleaned)
    
    return " ".join(parts)
```

### Step 1: 修改 build_embeddings.py 的文本构造

替换 `compute_embeddings` 中的文本拼接逻辑：

```python
# 替换原来的:
#   parts = []
#   if industry: parts.append(industry)
#   if scope: parts.append(scope)
#   text = " ".join(parts) if parts else "A股上市公司"

# 改为:
text = _build_weighted_text(industry, scope)
```

### Step 2: 同步修改 rebuild_bge.py

在 `rebuild_bge.py` 中做相同的修改：导入 `_build_weighted_text` 函数（或内联实现）。

### Step 3: 重建嵌入

```bash
cd engine && python -m preprocess.rebuild_bge
```

这会重新用 BGE 模型编码所有股票，生成新的 `stock_embeddings.npz`。

### Step 4: 重新生成静态快照

```bash
cd engine && python -m preprocess.export_snapshot
```

---

## Task 3: 后端返回相关股票数据

**Files:**
- Modify: `engine/api/schemas.py` — StockPoint 新增字段
- Modify: `engine/algorithm/pipeline.py` — 计算相关股票

**原理:**
在 `pipeline.compute_full()` 中，UMAP 降维后我们已经有了每只股票的 2D 坐标。同一 cluster 中的股票天然相关。我们在组装 `StockPoint` 时，为每只股票附加同簇中最近的 N 只关联股票信息。

### Step 1: 扩展 StockPoint schema

在 `engine/api/schemas.py` 的 `StockPoint` 中新增：

```python
class RelatedStock(BaseModel):
    code: str
    name: str
    industry: str = ""
    pct_chg: float = 0.0

class StockPoint(BaseModel):
    # ... 现有字段 ...
    related_stocks: list[RelatedStock] = Field(default_factory=list, description="同簇相关股票(按距离排序)")
```

### Step 2: 在 pipeline 中计算相关股票

在 `pipeline.py` 的 `compute_full` 中，UMAP 降维后、组装结果前，添加相关股票计算：

```python
from scipy.spatial import cKDTree

def _compute_related_stocks(
    codes: np.ndarray,
    names: np.ndarray,
    labels: np.ndarray,
    embedding_2d: np.ndarray,
    industries: np.ndarray,
    pct_chgs: np.ndarray,
    top_k: int = 10,
) -> dict[str, list[dict]]:
    """
    为每只股票找到同簇中最近的 top_k 只关联股票
    """
    related = {}
    
    # 按簇分组
    unique_labels = np.unique(labels)
    for label in unique_labels:
        if label == -1:  # 跳过噪声
            continue
        
        mask = labels == label
        indices = np.where(mask)[0]
        
        if len(indices) <= 1:
            continue
        
        # 在簇内构建 KDTree
        cluster_coords = embedding_2d[indices]
        tree = cKDTree(cluster_coords)
        
        for local_idx, global_idx in enumerate(indices):
            k = min(top_k + 1, len(indices))
            distances, local_neighbors = tree.query(cluster_coords[local_idx], k=k)
            
            neighbors = []
            for d, ln in zip(distances[1:], local_neighbors[1:]):  # 跳过自身
                gi = indices[ln]
                neighbors.append({
                    "code": codes[gi],
                    "name": names[gi],
                    "industry": industries[gi] if gi < len(industries) else "",
                    "pct_chg": float(pct_chgs[gi]) if gi < len(pct_chgs) else 0.0,
                })
            
            related[codes[global_idx]] = neighbors
    
    return related
```

在组装 stocks 列表时，将 `related_stocks` 附加到每个 StockPoint 中。

---

## Task 4: 前端相关股票面板

**Files:**
- Create: `web/components/ui/RelatedStocksPanel.tsx`
- Modify: `web/types/terrain.ts` — 新增 RelatedStock 类型
- Modify: `web/app/page.tsx` — 引入 RelatedStocksPanel
- Modify: `web/stores/useTerrainStore.ts` — 无需改动（已有 selectedStock/hoveredStock）

### Step 1: 扩展类型定义

在 `web/types/terrain.ts` 中新增：

```typescript
export interface RelatedStock {
  code: string;
  name: string;
  industry: string;
  pct_chg: number;
}
```

在 `StockPoint` 中新增：

```typescript
export interface StockPoint {
  // ... 现有字段 ...
  related_stocks?: RelatedStock[];
}
```

### Step 2: 创建 RelatedStocksPanel 组件

位置：右下角固定悬浮面板，使用与 Sidebar 相同的 `glass-panel` 样式。

当 `selectedStock` 或 `hoveredStock` 存在且有 `related_stocks` 时显示。

内容：
- 标题：`🔗 关联股票 · {股票名} 所在簇`
- 列表：每行显示 `代码 | 名称 | 行业 | 涨跌幅%`
- 涨跌幅红涨绿跌
- 最多显示 10 只
- 点击某行可以 `setSelectedStock()` 切换到该股票

```tsx
"use client";

import { useTerrainStore } from "@/stores/useTerrainStore";

export default function RelatedStocksPanel() {
  const { selectedStock, hoveredStock, terrainData, setSelectedStock } = useTerrainStore();
  
  // 优先显示选中股票，否则显示悬停股票
  const activeStock = selectedStock || hoveredStock;
  
  if (!activeStock || !activeStock.related_stocks || activeStock.related_stocks.length === 0) {
    return null;
  }
  
  const related = activeStock.related_stocks;
  
  return (
    <div className="overlay fixed bottom-4 right-4 w-[320px]">
      <div className="glass-panel px-4 py-3 max-h-[400px] overflow-y-auto">
        <h3 className="text-[11px] font-semibold text-[var(--text-tertiary)] mb-2 uppercase tracking-wider">
          🔗 关联股票 · {activeStock.name}
        </h3>
        
        {/* 表头 */}
        <div className="flex items-center text-[10px] text-[var(--text-tertiary)] pb-1 border-b border-[var(--border)] mb-1">
          <span className="w-[60px]">代码</span>
          <span className="flex-1">名称</span>
          <span className="w-[70px] text-right">行业</span>
          <span className="w-[55px] text-right">涨跌幅</span>
        </div>
        
        {/* 列表 */}
        {related.slice(0, 10).map((stock) => (
          <button
            key={stock.code}
            onClick={() => {
              // 在 terrainData.stocks 中找到完整的 StockPoint
              const fullStock = terrainData?.stocks.find(s => s.code === stock.code);
              if (fullStock) setSelectedStock(fullStock);
            }}
            className="flex items-center w-full text-xs py-1.5 px-1 rounded-lg hover:bg-gray-50 transition-smooth"
          >
            <span className="w-[60px] font-mono text-[var(--text-tertiary)] text-[10px]">
              {stock.code}
            </span>
            <span className="flex-1 text-[var(--text-primary)] truncate">
              {stock.name}
            </span>
            <span className="w-[70px] text-right text-[var(--text-secondary)] text-[10px] truncate">
              {stock.industry}
            </span>
            <span className={`w-[55px] text-right font-mono font-medium ${
              stock.pct_chg > 0 ? "text-rise" : stock.pct_chg < 0 ? "text-fall" : "text-[var(--text-tertiary)]"
            }`}>
              {stock.pct_chg > 0 ? "+" : ""}{stock.pct_chg.toFixed(2)}%
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
```

### Step 3: 在 page.tsx 中引入

```tsx
import RelatedStocksPanel from "@/components/ui/RelatedStocksPanel";

// 在 <main> 中添加:
<RelatedStocksPanel />
```

---

## Task 5: 重新生成快照 & 测试

### Step 1: 重建嵌入
```bash
cd engine && source .venv/bin/activate
python -m preprocess.rebuild_bge
```

### Step 2: 重启后端，测试全量计算
```bash
python main.py
# 在前端点击"生成 3D 地形"
```

### Step 3: 验证
1. 确认退市股票不在结果中
2. 确认聚类质量改善（同业公司应更紧密）
3. 确认悬停/选中股票时右下角出现关联股票面板
4. 点击关联股票可跳转选中

### Step 4: 重新生成静态快照
```bash
python -m preprocess.export_snapshot
```

---

## 执行顺序

1. **Task 1** (退市过滤) → 独立，无依赖
2. **Task 2** (语义加权嵌入) → 依赖 Task 1（过滤后的 profiles）
3. **Task 3** (后端相关股票) → 独立于 Task 2
4. **Task 4** (前端面板) → 依赖 Task 3 的 schema
5. **Task 5** (重建+测试) → 依赖全部

**可并行:** Task 1+3 可并行 | Task 2+4 可并行（在 1+3 完成后）
