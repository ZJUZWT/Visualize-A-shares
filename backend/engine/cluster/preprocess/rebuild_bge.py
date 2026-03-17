"""
BGE 嵌入快速重建脚本 v4.0

v4.0 核心改进 — 产业链拓扑嵌入:
- 通过产业链标签系统让跨行业但有供应链关系的公司在语义空间中形成蜘蛛网连接
- 去除行业名称作为文本前缀（避免行业硬分类主导嵌入）
- 更激进的 scope 清洗（去除所有法律/行政套话）
- 退市股票过滤

用法：cd engine && python -m cluster_engine.preprocess.rebuild_bge
"""

import sys
import os
import re
import time
import json
from pathlib import Path

import numpy as np
from loguru import logger

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "data" / "precomputed"

sys.path.insert(0, str(BACKEND_DIR))


# ─── 通用套话正则（对区分公司毫无价值，激进清洗）───────────
NOISE_PATTERNS = [
    r"依法须经批准的项目[^;；。]*[;；。]?",
    r"经相关部门批准后方可开展经营活动[^;；。]*[;；。]?",
    r"一般项目[:：]?\s*",
    r"许可项目[:：]?\s*",
    r"具体经营项目以相关部门批准文件或许可证件为准[^;；。]*[;；。]?",
    r"以上.*?(?:不含|除外)[^;；。]*[;；。]?",
    r"\(.*?经相关部门批准.*?\)",
    r"（.*?经相关部门批准.*?）",
    r"除依法须经批准的项目外.*?(?:[;；。]|$)",
    r"自主开展经营活动[^;；。]*[;；。]?",
    r"技术咨询[;；,，]?技术服务[;；,，]?技术开发[;；,，]?技术转让[;；,，]?",
    r"技术进出口[;；,，]?货物进出口[;；,，]?",
    r"进出口业务[^;；。]*[;；。]?",
    r"企业管理咨询[;；,，]?",
    r"自有[房屋|场地].*?租赁[;；,，。]?",
    r"经济信息咨询[;；,，]?",
]

# ─── 产业链图谱 ──────────────────────────────────────────
# 每条 chain: (触发关键词列表, 产业链标签)
# 当 scope 命中触发词时，自动注入产业链标签到嵌入文本
# 这让跨行业但有供应链关系的公司共享语义信号
SUPPLY_CHAIN_GRAPH = [
    # === 电力能源大链（拆分火电/水电/核电为独立条目）===
    (["火电", "火力发电", "燃煤发电", "热电"],
     "火力发电 燃煤电厂 热电联产 火电运营"),
    (["水电", "水力发电", "水电站", "梯级电站"],
     "水力发电 水电站运营 梯级开发 水利发电"),
    (["核电", "核能", "核电站", "核燃料"],
     "核能发电 核电站运营 核燃料加工 核工业"),
    (["风电", "风力发电", "风机", "风电场"],
     "风力发电 风机叶片 海上风电 风电运维"),
    (["光伏", "太阳能", "光伏发电", "光伏组件", "硅片", "硅料"],
     "光伏组件 硅片电池 太阳能电站 分布式光伏"),
    (["电网", "输电", "配电", "变压器", "开关柜", "电力设备"],
     "电网设备 电力传输 电力系统 输配电"),
    (["储能", "蓄电", "电化学储能"],
     "储能系统 电力调峰 新能源配套 电池储能"),
    (["燃气轮机", "天然气发电", "燃气发电"],
     "燃气发电 天然气轮机 热电联产 燃气电厂"),
    (["电力销售", "售电", "电力经营", "电力开发"],
     "电力销售 售电服务 电力运营"),
    (["煤炭", "煤矿", "采煤"],
     "煤炭开采 煤矿生产 动力煤 焦煤焦炭"),
    (["石油", "原油", "炼油", "成品油"],
     "石油开采 原油炼化 成品油销售 石化能源"),
    (["氢能", "氢燃料", "制氢"],
     "氢能源 制氢技术 氢燃料电池 绿氢"),
    (["充电", "充电桩", "充电站", "换电"],
     "充电设施 充电桩运营 换电站 新能源汽车补能"),

    # === 电池 & 材料链 ===
    (["锂电池", "动力电池", "电芯"],
     "锂电池制造 动力电池组装 电芯生产"),
    (["正极材料", "负极材料", "电解液", "隔膜"],
     "电池材料 正极负极 电解液隔膜 锂电上游"),
    (["锂", "碳酸锂", "氢氧化锂", "锂矿"],
     "锂矿资源 碳酸锂提取 锂盐加工"),
    (["钴", "镍", "锰", "三元材料"],
     "钴镍锰资源 三元正极材料 电池金属"),
    (["钨", "钨矿", "钨制品", "硬质合金"],
     "钨矿开采 钨制品加工 硬质合金刀具 稀有金属钨"),
    (["稀土", "永磁", "磁性材料", "钕铁硼"],
     "稀土矿开采 钕铁硼永磁 稀土分离冶炼 磁性材料"),

    # === 贵金属 & 有色独立链 ===
    (["黄金", "金矿", "金条", "贵金属"],
     "黄金开采 金矿生产 贵金属冶炼 黄金珠宝"),
    (["铜", "铜矿", "铜冶炼", "铜加工", "铜箔"],
     "铜矿开采 铜冶炼加工 铜箔制造 有色铜"),
    (["铝", "铝矿", "电解铝", "铝加工", "铝型材"],
     "电解铝生产 铝加工型材 氧化铝 有色铝"),

    # === 半导体链 ===
    (["芯片", "集成电路", "IC设计"],
     "芯片设计 半导体 集成电路 电子信息"),
    (["晶圆", "晶圆代工", "半导体制造"],
     "晶圆制造 半导体制造 芯片生产"),
    (["封装测试", "封测", "芯片封装"],
     "封装测试 半导体后道 芯片封装"),
    (["半导体设备", "光刻", "刻蚀"],
     "半导体设备 芯片制造设备 精密制造"),
    (["显示面板", "OLED面板", "LCD面板", "Mini LED"],
     "显示面板 平板显示 消费电子屏幕"),
    (["PCB", "印制电路板", "线路板"],
     "PCB制造 电子元器件 电路板"),

    # === 汽车链 ===
    (["整车", "乘用车", "商用车", "新能源汽车", "电动汽车"],
     "整车制造 汽车工业 新能源汽车"),
    (["汽车零部件", "底盘", "转向", "制动"],
     "汽车零部件 整车配套 汽车供应链"),
    (["自动驾驶", "智能驾驶", "车联网"],
     "智能驾驶 汽车电子 车联网"),

    # === 医药链 ===
    (["原料药", "化学药", "制剂"],
     "化学制药 原料药 药品制造"),
    (["中药", "中成药", "中药饮片"],
     "中医药 中药制造 传统医学"),
    (["生物制品", "疫苗", "抗体", "基因"],
     "生物医药 生物技术 基因工程"),
    (["医疗器械", "诊断", "影像", "体外诊断"],
     "医疗器械 诊断设备 医疗设备"),
    (["CRO", "CMO", "CDMO", "临床试验"],
     "医药外包 药物研发 临床试验"),

    # === 消费链 ===
    (["白酒", "酿酒", "酱香", "浓香"],
     "白酒酿造 食品饮料 消费品"),
    (["啤酒", "饮料", "乳制品", "牛奶"],
     "饮料食品 快消品 消费品"),
    (["调味品", "酱油", "醋", "味精"],
     "调味品 食品加工 消费品"),
    (["家电", "空调", "冰箱", "洗衣机", "电视"],
     "家用电器 消费电子 家电制造"),

    # === 金融链（去掉共享"金融"前缀，各用独特标签）===
    (["商业银行", "存款", "贷款业务", "信贷业务", "银行业务"],
     "商业银行 存贷款业务 信贷风控 银行网点"),
    (["证券经纪", "证券承销", "证券自营", "投资银行业务"],
     "证券经纪 股票承销 投行业务 资本中介"),
    (["保险", "寿险", "财险", "再保险", "保险理赔"],
     "保险承保 寿险财险 保费理赔 精算定价"),
    (["基金管理", "公募基金", "私募基金"],
     "公募私募 基金管理 资产配置 投资组合"),

    # === 地产基建链 ===
    (["房地产", "住宅", "商业地产", "物业"],
     "房地产开发 物业管理 城市建设"),
    (["建筑", "施工", "工程总承包", "基建"],
     "建筑施工 基础建设 工程建设"),
    (["水泥", "混凝土", "砂石"],
     "水泥建材 建筑材料 基建材料"),
    (["钢铁", "钢材", "钢管", "型钢"],
     "钢铁冶炼 金属材料 工业基础材料"),

    # === 通信 & 科技链 ===
    (["5G", "基站", "通信设备", "通信网络"],
     "5G通信 通信设备 网络基建"),
    (["光纤", "光缆", "光通信", "光模块"],
     "光通信 光纤网络 通信传输"),
    (["云计算", "数据中心", "服务器", "算力"],
     "云计算 数据中心 IT基础设施"),
    (["人工智能", "机器学习", "深度学习", "大模型"],
     "人工智能 AI技术 智能计算"),
    (["软件", "操作系统", "数据库", "中间件"],
     "基础软件 信息技术 软件开发"),
    (["信息安全", "网络安全", "密码"],
     "网络安全 信息安全 安全防护"),

    # === 军工链 ===
    (["航空发动机", "飞机", "航空"],
     "航空工业 军工航空 国防装备"),
    (["航天", "火箭", "卫星", "导弹"],
     "航天工业 军工航天 国防装备"),
    (["舰船", "船舶", "海军装备"],
     "船舶制造 军工船舶 海洋装备"),
    (["雷达", "电子战", "军用电子"],
     "军用电子 雷达系统 国防电子"),

    # === 农业链 ===
    (["种子", "育种", "种业"],
     "种业 农业育种 农业上游"),
    (["化肥", "氮肥", "磷肥", "钾肥", "复合肥"],
     "化肥 农资 农业投入品"),
    (["农药", "除草剂", "杀虫剂"],
     "农药 植保 农业投入品"),
    (["饲料", "养殖", "畜牧", "猪", "鸡", "牛"],
     "畜牧养殖 饲料加工 农业养殖"),
]


def _clean_scope(scope: str) -> str:
    """激进清洗 scope 文本"""
    cleaned = scope
    for pattern in NOISE_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned)
    # 去除多余空白
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _match_supply_chains(scope: str) -> list[str]:
    """
    匹配产业链标签

    遍历产业链图谱，返回该公司命中的所有产业链标签
    一家公司可能同时命中多条产业链（如厦门钨业：钨矿 + 电池材料）
    """
    matched_labels = []
    text = scope.lower() if scope else ""

    for trigger_keywords, chain_label in SUPPLY_CHAIN_GRAPH:
        for kw in trigger_keywords:
            if kw.lower() in text:
                matched_labels.append(chain_label)
                break  # 每条链只需命中一次

    return matched_labels


def _build_weighted_text(industry: str, scope: str) -> str:
    """
    构建产业链拓扑嵌入文本 v4.0

    设计原理：
    - 不使用行业名称作为前缀（避免行业硬分类主导嵌入距离）
    - 通过产业链标签注入，让跨行业但有供应链关系的公司共享语义信号
      例如：厦门钨业 → "钨矿资源 硬质合金" + "电池材料 锂电池上游"
            宁德时代 → "锂电池制造" + "储能电池"
      两者共享 "电池" 相关语义 → 在嵌入空间中产生连接
    - 核心业务段落重复 → BGE 自然提高这些 token 的权重

    文本结构：
    [产业链标签(×2)] [核心业务段落] [清洗后经营范围]
    """
    if not scope:
        # 无 scope 时，退化为行业标签
        return f"{industry}" if industry else "A股上市公司"

    # Step 1: 激进清洗 scope
    cleaned = _clean_scope(scope)

    # Step 2: 分句
    segments = re.split(r'[;；。\n]+', cleaned)
    segments = [s.strip() for s in segments if len(s.strip()) >= 2]

    # Step 3: 匹配产业链标签
    chain_labels = _match_supply_chains(scope)

    # Step 4: 构建嵌入文本
    parts = []

    # 产业链标签在最前面 + 重复一次（×2 权重）
    if chain_labels:
        chain_text = " ".join(chain_labels)
        parts.append(chain_text)

    # 核心业务段落（包含产品/技术/材料名词的句子）
    # 使用更精准的判断：句子中包含具体的产品/技术名词
    core_segments = []
    for seg in segments:
        # 检查是否包含实质性业务内容（而非通用服务描述）
        has_product = any(kw in seg for kw in _PRODUCT_KEYWORDS)
        if has_product and len(seg) >= 4:
            core_segments.append(seg)

    if core_segments:
        core_text = ";".join(core_segments[:12])
        parts.append(core_text)

    # 产业链标签再次出现（强化关联信号）
    if chain_labels:
        parts.append(" ".join(chain_labels))

    # 清洗后的完整经营范围（截断防止太长稀释信号）
    full_text = ";".join(segments[:20])
    if full_text:
        parts.append(full_text)

    return " ".join(parts) if parts else "A股上市公司"


# ─── 产品/技术关键词（判断句子是否包含实质性业务内容）────────
_PRODUCT_KEYWORDS = [
    # 能源
    "电力", "发电", "电站", "电厂", "风电", "光伏", "核电", "水电", "火电",
    "电网", "输电", "配电", "变压器", "储能", "充电", "燃气", "热力", "热电",
    "煤炭", "石油", "天然气", "氢能",
    # 电池 & 材料
    "电池", "锂", "钴", "镍", "钨", "稀土", "磁性材料", "永磁",
    "正极", "负极", "电解液", "隔膜", "硬质合金",
    # 半导体
    "芯片", "半导体", "晶圆", "封装", "集成电路", "传感器",
    "显示", "面板", "OLED", "LED", "PCB",
    # 汽车
    "汽车", "整车", "发动机", "变速箱", "底盘", "自动驾驶",
    # 医药
    "药品", "疫苗", "医疗器械", "诊断", "生物制品", "中药",
    "原料药", "制剂", "抗体", "基因",
    # 消费
    "白酒", "啤酒", "乳制品", "饮料", "食品", "调味品",
    "家电", "空调", "冰箱",
    # 材料
    "水泥", "钢铁", "钢材", "铝", "铜", "塑料", "橡胶", "碳纤维",
    # 科技
    "软件", "云计算", "人工智能", "大数据", "信息安全",
    "服务器", "数据库", "操作系统",
    # 通信
    "5G", "基站", "光纤", "光缆", "通信",
    # 金融
    "银行", "保险", "证券", "基金", "信托", "贷款",
    # 地产基建
    "房地产", "建筑", "施工", "水泥", "钢结构",
    # 军工
    "航空", "航天", "卫星", "雷达", "导弹", "舰船",
    # 农业
    "种子", "化肥", "农药", "饲料", "养殖",
]


def main():
    logger.info("=" * 60)
    logger.info("🧠 BGE 嵌入快速重建 v4.0 — 产业链拓扑嵌入")
    logger.info("=" * 60)

    # 加载已缓存的公司概况
    profiles_path = PRECOMPUTED_DIR / "company_profiles.json"
    if not profiles_path.exists():
        logger.error("❌ company_profiles.json 不存在，请先运行 build_embeddings")
        return

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    logger.info(f"📋 加载 {len(profiles)} 只股票的公司概况")

    # ─── 过滤退市股票 ──────────────────────────────
    original_count = len(profiles)
    profiles = {
        code: p for code, p in profiles.items()
        if "退市" not in p.get("name", "")
    }
    delist_count = original_count - len(profiles)
    if delist_count > 0:
        logger.info(f"🚫 过滤退市股票: {delist_count} 只")
    logger.info(f"📋 有效股票: {len(profiles)} 只")

    # 加载 BGE 模型
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    logger.info("📦 加载 BGE 模型: BAAI/bge-base-zh-v1.5 ...")
    model = SentenceTransformer("BAAI/bge-base-zh-v1.5")
    dim = model.get_sentence_embedding_dimension()
    logger.info(f"✅ BGE 加载完成: {dim} 维, 耗时 {time.time()-t0:.1f}s")

    # ─── 准备产业链拓扑嵌入文本 ──────────────────────
    texts = []
    valid_codes = []
    chain_count = 0
    chain_distribution: dict[str, int] = {}

    for code, profile in sorted(profiles.items()):
        scope = profile.get("scope", "")
        industry = profile.get("industry", "")
        text = _build_weighted_text(industry, scope)

        # 统计产业链命中
        chains = _match_supply_chains(scope)
        if chains:
            chain_count += 1
            for chain in chains:
                first_word = chain.split()[0]
                chain_distribution[first_word] = chain_distribution.get(first_word, 0) + 1

        # BGE 检索前缀
        texts.append(f"为这个句子生成表示以用于检索中文金融文档: {text}")
        valid_codes.append(code)

    logger.info(f"📝 文本准备完成:")
    logger.info(f"  总计: {len(texts)} 条")
    logger.info(f"  含产业链标签: {chain_count} 条 ({100*chain_count/max(len(texts),1):.1f}%)")

    # 输出前15大产业链
    top_chains = sorted(chain_distribution.items(), key=lambda x: -x[1])[:15]
    for name, cnt in top_chains:
        logger.info(f"    {name}: {cnt} 只")

    # 编码
    logger.info(f"🔄 编码 {len(texts)} 条文本 (batch_size=64) ...")
    t1 = time.time()
    embeddings = model.encode(
        texts,
        batch_size=64,
        show_progress_bar=True,
        normalize_embeddings=True,
    )
    embeddings = np.array(embeddings, dtype=np.float32)
    encode_time = time.time() - t1
    logger.info(f"✅ 编码完成: {embeddings.shape}, 耗时 {encode_time:.1f}s")

    # 保存嵌入
    output_path = PRECOMPUTED_DIR / "stock_embeddings.npz"
    np.savez_compressed(
        output_path,
        codes=np.array(valid_codes),
        embeddings=embeddings,
        model_name="BAAI/bge-base-zh-v1.5",
        dim=embeddings.shape[1],
    )
    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info(f"💾 已保存: {output_path} ({size_mb:.1f} MB)")

    # 更新元信息
    total_time = time.time() - t0
    meta = {
        "version": "4.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_stocks": len(valid_codes),
        "n_with_scope": sum(1 for p in profiles.values() if p.get("scope")),
        "n_with_industry": sum(1 for p in profiles.values() if p.get("industry")),
        "n_with_chain_labels": chain_count,
        "n_delist_filtered": delist_count,
        "embedding_dim": embeddings.shape[1],
        "embedding_model": "BAAI/bge-base-zh-v1.5",
        "text_strategy": "v4.0: supply_chain_labels(×2) + core_products + cleaned_scope",
        "total_time_seconds": round(total_time, 1),
    }
    meta_path = PRECOMPUTED_DIR / "precompute_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    logger.info(f"💾 元信息已更新: {meta_path}")

    logger.info("=" * 60)
    logger.info(f"🎉 BGE 嵌入重建完成！总耗时 {total_time:.0f}s")
    logger.info(f"  {len(valid_codes)} 只股票 × {embeddings.shape[1]} 维")
    logger.info(f"  退市过滤: {delist_count} 只")
    logger.info(f"  产业链标签命中: {chain_count} 只")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
