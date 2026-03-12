"""
预处理脚本 v3.0 — 纯语义嵌入聚类

核心理念：
  不做行业硬分类 one-hot，而是用公司经营范围描述通过 BGE 模型
  生成语义嵌入，让模型自动发现语义相近的公司（跨行业关联）。

数据源：
  东方财富 F10 公司概况 API（全市场覆盖、字段丰富）

输出文件 → data/precomputed/
  - company_profiles.json  : {code → {name, industry, scope, ...}}
  - stock_embeddings.npz   : {codes, embeddings, model_name, dim}
  - precompute_meta.json   : 元信息

使用方式:
  cd engine && python -m preprocess.build_embeddings
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from loguru import logger

# ─── 路径 ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ENGINE_ROOT = PROJECT_ROOT / "engine"
DATA_DIR = PROJECT_ROOT / "data"
PRECOMPUTED_DIR = DATA_DIR / "precomputed"
PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)

# 将 engine 加入 path
sys.path.insert(0, str(ENGINE_ROOT))

# ─── 配置 ─────────────────────────────────────────────
HF_MIRROR = "https://hf-mirror.com"
BGE_MODEL_NAME = "BAAI/bge-base-zh-v1.5"  # 768 维, ~400MB
BGE_EMBEDDING_DIM = 768
BATCH_SIZE = 64
MAX_WORKERS = 8  # 并发线程数

FALLBACK_MODEL = "shibing624/text2vec-base-chinese"
FALLBACK_DIM = 384

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://emweb.securities.eastmoney.com/",
}


# ═══════════════════════════════════════════════════════
# Step 1: 获取全市场股票代码
# ═══════════════════════════════════════════════════════

def get_all_stock_codes() -> list[str]:
    """
    获取全市场 A 股代码列表

    使用腾讯行情接口批量验证候选代码的有效性。
    与 tencent_source.py 的逻辑一致。

    Returns:
        ["600519", "000858", ...]  纯6位数字代码
    """
    import requests
    from concurrent.futures import ThreadPoolExecutor, as_completed

    logger.info("=" * 60)
    logger.info("📋 Step 1: 获取全市场股票代码...")
    logger.info("=" * 60)

    # 生成候选代码（与 tencent_source._get_all_stock_codes 一致）
    candidates = []
    # 沪市主板: 600000-605999
    for i in range(600000, 606000):
        candidates.append(f"sh{i}")
    # 沪市科创板: 688000-689999
    for i in range(688000, 690000):
        candidates.append(f"sh{i}")
    # 深市主板: 000001-003999
    for i in range(1, 4000):
        candidates.append(f"sz{i:06d}")
    # 创业板: 300000-301999
    for i in range(300000, 302000):
        candidates.append(f"sz{i}")

    logger.info(f"候选代码: {len(candidates)} 个")

    # 分批查询腾讯行情，过滤有效代码
    valid_codes = set()
    batch_size = 50

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Referer": "https://finance.qq.com/",
    })

    def _check_batch(batch: list[str]) -> list[str]:
        query = ",".join(batch)
        try:
            r = session.get(
                f"https://qt.gtimg.cn/q={query}", timeout=10
            )
            results = []
            for line in r.text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # 格式: v_sh600519="1~贵州茅台~600519~..."
                #   或: v_sz000001="51~平安银行~000001~..."
                m = re.search(r'v_\w+="\d+~([^~]+)~(\d{6})~', line)
                if m and m.group(1):
                    results.append(m.group(2))
            return results
        except Exception:
            return []

    batches = [
        candidates[i: i + batch_size]
        for i in range(0, len(candidates), batch_size)
    ]

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(_check_batch, batch): idx
            for idx, batch in enumerate(batches)
        }
        done = 0
        for future in as_completed(futures):
            codes = future.result()
            valid_codes.update(codes)
            done += 1
            if done % 50 == 0:
                logger.info(
                    f"  进度: {done}/{len(batches)} 批次, "
                    f"已发现 {len(valid_codes)} 只有效股票"
                )

    logger.info(f"✅ 获取到 {len(valid_codes)} 只有效股票代码")
    return sorted(valid_codes)


# ═══════════════════════════════════════════════════════
# Step 2: 爬取公司概况（东方财富 F10）
# ═══════════════════════════════════════════════════════

def _fetch_em_f10(code: str) -> dict:
    """
    从东方财富 F10 获取单只股票的公司概况

    Returns:
        {code, name, industry, zjh_industry, scope} 或空 dict
    """
    import requests

    if code.startswith("6"):
        em_code = f"SH{code}"
    elif code.startswith(("0", "3")):
        em_code = f"SZ{code}"
    elif code.startswith(("4", "8", "9")):
        em_code = f"BJ{code}"
    else:
        em_code = f"SZ{code}"

    try:
        url = (
            f"https://emweb.securities.eastmoney.com/"
            f"PC_HSF10/CompanySurvey/CompanySurveyAjax?"
            f"code={em_code}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()

        jbzl = data.get("jbzl", {})
        if not jbzl:
            return {}

        scope = jbzl.get("jyfw", "") or ""
        name = jbzl.get("agjc", "") or jbzl.get("gsmc", "")
        industry = jbzl.get("sshy", "") or ""
        zjh_industry = jbzl.get("sszjhhy", "") or ""

        if not scope and not industry:
            return {}

        return {
            "code": code,
            "name": name,
            "industry": industry,
            "zjh_industry": zjh_industry,
            "scope": scope[:800],  # 截断过长的
        }
    except Exception:
        return {}


def fetch_company_profiles(codes: list[str]) -> dict[str, dict]:
    """
    批量爬取公司概况

    Returns:
        {code: {name, industry, zjh_industry, scope}, ...}
    """
    logger.info("=" * 60)
    logger.info("🏢 Step 2: 爬取公司概况（东方财富 F10）...")
    logger.info("=" * 60)

    profiles = {}

    # 检查缓存
    cache_path = PRECOMPUTED_DIR / "company_profiles.json"
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
            # 已缓存的不再拉取
            codes_to_fetch = [c for c in codes if c not in cached]
            profiles.update(cached)
            logger.info(
                f"缓存命中 {len(cached)} 只, 还需拉取 {len(codes_to_fetch)} 只"
            )
        except Exception:
            codes_to_fetch = list(codes)
    else:
        codes_to_fetch = list(codes)
        logger.info(f"需要拉取 {len(codes_to_fetch)} 只股票的公司概况")

    if not codes_to_fetch:
        return profiles

    # 先测试接口可用性
    test_result = _fetch_em_f10(codes_to_fetch[0])
    if not test_result:
        logger.warning("⚠️ 东方财富 F10 接口不可用，跳过爬取")
        return profiles

    logger.info(
        f"✅ 接口可用 (测试: {test_result.get('name', '?')} "
        f"行业={test_result.get('industry', '?')})"
    )

    # 分批并行拉取
    batch_size = 100
    total_batches = (len(codes_to_fetch) + batch_size - 1) // batch_size
    failed_count = 0
    t0 = time.time()

    for batch_idx in range(total_batches):
        batch_start = batch_idx * batch_size
        batch_codes = codes_to_fetch[batch_start: batch_start + batch_size]

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_em_f10, code): code
                for code in batch_codes
            }
            for future in as_completed(futures):
                result = future.result()
                if result:
                    profiles[result["code"]] = result
                else:
                    failed_count += 1

        elapsed = time.time() - t0
        speed = len(profiles) / max(elapsed, 0.1)
        logger.info(
            f"  批次 [{batch_idx + 1}/{total_batches}] "
            f"已获取 {len(profiles)} 只 "
            f"({speed:.1f} 只/秒)"
        )

        # 每 5 批保存一次缓存
        if (batch_idx + 1) % 5 == 0 or batch_idx == total_batches - 1:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(profiles, f, ensure_ascii=False)

        time.sleep(0.3)  # 限速

    total_elapsed = time.time() - t0

    # 统计
    has_scope = sum(1 for p in profiles.values() if p.get("scope"))
    has_industry = sum(1 for p in profiles.values() if p.get("industry"))
    avg_scope_len = (
        sum(len(p.get("scope", "")) for p in profiles.values()) / max(len(profiles), 1)
    )

    logger.info(
        f"✅ 公司概况爬取完成: {len(profiles)} 成功, {failed_count} 失败 "
        f"({total_elapsed:.0f}s)"
    )
    logger.info(f"  有经营范围: {has_scope} 只 ({100*has_scope/max(len(profiles),1):.1f}%)")
    logger.info(f"  有行业信息: {has_industry} 只")
    logger.info(f"  平均描述长度: {avg_scope_len:.0f} 字")

    # 最终保存
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(profiles, f, ensure_ascii=False)
    logger.info(f"💾 已保存: {cache_path}")

    return profiles


# ═══════════════════════════════════════════════════════
# Step 3: 语义嵌入
# ═══════════════════════════════════════════════════════

def _check_model_cached(model_name: str) -> bool:
    """检查 HuggingFace 模型是否已完整下载到本地"""
    cache_dir = os.path.expanduser("~/.cache/huggingface/hub")
    model_dir_name = f"models--{model_name.replace('/', '--')}"
    model_path = os.path.join(cache_dir, model_dir_name, "snapshots")
    if os.path.exists(model_path):
        for snapshot in os.listdir(model_path):
            snapshot_dir = os.path.join(model_path, snapshot)
            if os.path.isdir(snapshot_dir):
                total_size = sum(
                    os.path.getsize(os.path.join(dp, f))
                    for dp, _, fn in os.walk(snapshot_dir)
                    for f in fn
                )
                if total_size > 200 * 1024 * 1024:
                    return True
    return False


def _try_load_sentence_model():
    """
    尝试加载句子嵌入模型

    Returns:
        (model, dim, model_name) 或 None
    """
    try:
        from sentence_transformers import SentenceTransformer

        # BGE
        if _check_model_cached(BGE_MODEL_NAME):
            logger.info(f"发现本地缓存: {BGE_MODEL_NAME}，加载中...")
            try:
                model = SentenceTransformer(BGE_MODEL_NAME)
                logger.info(f"✅ BGE 模型加载成功 ({BGE_EMBEDDING_DIM} 维)")
                return model, BGE_EMBEDDING_DIM, BGE_MODEL_NAME
            except Exception as e:
                logger.warning(f"BGE 加载失败: {e}")

        # text2vec
        if _check_model_cached(FALLBACK_MODEL):
            logger.info(f"发现本地缓存: {FALLBACK_MODEL}，加载中...")
            try:
                model = SentenceTransformer(FALLBACK_MODEL)
                logger.info(f"✅ text2vec 模型加载成功 ({FALLBACK_DIM} 维)")
                return model, FALLBACK_DIM, FALLBACK_MODEL
            except Exception as e:
                logger.warning(f"text2vec 加载失败: {e}")

        logger.info(
            "📦 本地无嵌入模型，使用 TF-IDF + SVD 保底方案"
        )
    except ImportError:
        logger.warning("sentence-transformers 未安装")

    return None


def _compute_tfidf_embeddings(
    texts: list[str], target_dim: int = 256
) -> np.ndarray:
    """TF-IDF + SVD 保底方案"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD

    logger.info("🔄 使用 TF-IDF + SVD 保底方案...")

    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(1, 3),
        max_features=10000,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(texts)
    logger.info(f"  TF-IDF 矩阵: {tfidf_matrix.shape}")

    actual_dim = min(target_dim, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1)
    svd = TruncatedSVD(n_components=actual_dim, random_state=42)
    embeddings = svd.fit_transform(tfidf_matrix)

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    logger.info(
        f"  SVD 降维后: {embeddings.shape}, "
        f"解释方差: {svd.explained_variance_ratio_.sum() * 100:.1f}%"
    )
    return embeddings.astype(np.float32)


def compute_embeddings(
    profiles: dict[str, dict],
) -> tuple[list[str], np.ndarray, str]:
    """
    Step 3: 用公司经营范围计算语义嵌入

    文本构成：[行业] + 经营范围描述
    行业作为语义上下文前缀（非 one-hot 硬分类）
    """
    logger.info("=" * 60)
    logger.info("🧠 Step 3: 语义嵌入计算...")
    logger.info("=" * 60)

    # 准备文本
    texts = []
    valid_codes = []

    for code, profile in sorted(profiles.items()):
        scope = profile.get("scope", "")
        industry = profile.get("industry", "")

        # 组合文本：行业 + 经营范围
        parts = []
        if industry:
            parts.append(industry)
        if scope:
            parts.append(scope)

        text = " ".join(parts) if parts else "A股上市公司"
        texts.append(text)
        valid_codes.append(code)

    has_scope = sum(
        1 for c in valid_codes if profiles[c].get("scope")
    )
    has_industry_only = sum(
        1 for c in valid_codes
        if not profiles[c].get("scope") and profiles[c].get("industry")
    )

    logger.info(f"准备编码 {len(texts)} 条文本...")
    logger.info(f"  有经营范围: {has_scope} 只")
    logger.info(f"  仅有行业名: {has_industry_only} 只")

    # 加载模型
    model_result = _try_load_sentence_model()

    t0 = time.time()

    if model_result is not None:
        model, dim, model_name_used = model_result

        # BGE 模型的检索前缀
        if "bge" in model_name_used.lower():
            encode_texts = [
                f"为这个句子生成表示以用于检索中文金融文档: {t}"
                for t in texts
            ]
        else:
            encode_texts = texts

        embeddings = model.encode(
            encode_texts,
            batch_size=BATCH_SIZE,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        embeddings = np.array(embeddings, dtype=np.float32)
    else:
        model_name_used = "tfidf-svd-256d"
        dim = 256
        embeddings = _compute_tfidf_embeddings(texts, target_dim=dim)

    elapsed = time.time() - t0

    logger.info(
        f"✅ 嵌入计算完成: {embeddings.shape} | "
        f"模型: {model_name_used} | 耗时 {elapsed:.1f}s"
    )

    # 保存
    output_path = PRECOMPUTED_DIR / "stock_embeddings.npz"
    np.savez_compressed(
        output_path,
        codes=np.array(valid_codes),
        embeddings=embeddings,
        model_name=model_name_used,
        dim=embeddings.shape[1],
    )
    file_size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info(f"💾 已保存: {output_path} ({file_size_mb:.1f} MB)")

    return valid_codes, embeddings, model_name_used


# ═══════════════════════════════════════════════════════
# 元信息
# ═══════════════════════════════════════════════════════

def save_metadata(
    n_stocks: int,
    embedding_dim: int,
    model_name: str,
    elapsed_seconds: float,
    profiles: dict[str, dict],
):
    """保存预计算元信息"""
    has_scope = sum(1 for p in profiles.values() if p.get("scope"))
    has_industry = sum(1 for p in profiles.values() if p.get("industry"))

    meta = {
        "version": "3.0",
        "created_at": datetime.now().isoformat(),
        "n_stocks": n_stocks,
        "n_with_scope": has_scope,
        "n_with_industry": has_industry,
        "embedding_dim": embedding_dim,
        "embedding_model": model_name,
        "total_time_seconds": round(elapsed_seconds, 1),
        "files": [
            "company_profiles.json",
            "stock_embeddings.npz",
        ],
        "feature_fusion": {
            "layer_1": f"BGE 语义嵌入 ({embedding_dim} dim) × weight 2.0",
            "layer_2": "numeric_features (6 dim) × weight 1.0",
            "total_raw_dim": embedding_dim + 6,
            "pca_target_dim": 50,
            "note": "v3.0: 去掉行业 one-hot，纯语义嵌入 + 数值特征",
        },
    }

    output_path = PRECOMPUTED_DIR / "precompute_meta.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    logger.info(f"💾 元信息已保存: {output_path}")


# ═══════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════

def main():
    """执行完整预处理流程"""
    logger.info("🚀" * 30)
    logger.info("StockTerrain 预处理 v3.0 — 纯语义嵌入聚类")
    logger.info("🚀" * 30)

    t_total = time.time()

    # Step 1: 获取全市场股票代码
    all_codes = get_all_stock_codes()

    if not all_codes:
        logger.error("❌ 无法获取股票代码列表！")
        return

    # Step 2: 爬取公司概况
    profiles = fetch_company_profiles(all_codes)

    if not profiles:
        logger.error("❌ 公司概况为空，无法继续！")
        return

    # Step 3: 语义嵌入
    valid_codes, embeddings, actual_model_name = compute_embeddings(profiles)

    # 保存元信息
    total_elapsed = time.time() - t_total
    save_metadata(
        n_stocks=len(valid_codes),
        embedding_dim=embeddings.shape[1],
        model_name=actual_model_name,
        elapsed_seconds=total_elapsed,
        profiles=profiles,
    )

    logger.info("=" * 60)
    logger.info(f"🎉 预处理全部完成！总耗时 {total_elapsed:.0f}s")
    logger.info(f"📁 输出目录: {PRECOMPUTED_DIR}")
    logger.info(f"  - company_profiles.json ({len(profiles)} 只股票)")
    logger.info(
        f"  - stock_embeddings.npz "
        f"({embeddings.shape[0]} × {embeddings.shape[1]})"
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
