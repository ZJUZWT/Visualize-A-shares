"""
BGE 嵌入快速重建脚本

仅执行 Step 3（语义编码），跳过 Step 1/2（代码获取+概况爬取）
前提：company_profiles.json 已存在 + BGE 模型已下载

用法：cd engine && python -m preprocess.rebuild_bge
"""

import sys
import os
import time
import json
from pathlib import Path

import numpy as np
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
PRECOMPUTED_DIR = PROJECT_ROOT / "data" / "precomputed"

sys.path.insert(0, str(PROJECT_ROOT / "engine"))


def main():
    logger.info("=" * 60)
    logger.info("🧠 BGE 嵌入快速重建 — 仅 Step 3")
    logger.info("=" * 60)

    # 加载已缓存的公司概况
    profiles_path = PRECOMPUTED_DIR / "company_profiles.json"
    if not profiles_path.exists():
        logger.error("❌ company_profiles.json 不存在，请先运行 build_embeddings")
        return

    with open(profiles_path, "r", encoding="utf-8") as f:
        profiles = json.load(f)
    logger.info(f"📋 加载 {len(profiles)} 只股票的公司概况")

    # 加载 BGE 模型
    from sentence_transformers import SentenceTransformer

    t0 = time.time()
    logger.info("📦 加载 BGE 模型: BAAI/bge-base-zh-v1.5 ...")
    model = SentenceTransformer("BAAI/bge-base-zh-v1.5")
    dim = model.get_sentence_embedding_dimension()
    logger.info(f"✅ BGE 加载完成: {dim} 维, 耗时 {time.time()-t0:.1f}s")

    # 准备文本（行业 + 经营范围 + BGE 检索前缀）
    texts = []
    valid_codes = []
    for code, profile in sorted(profiles.items()):
        scope = profile.get("scope", "")
        industry = profile.get("industry", "")
        parts = []
        if industry:
            parts.append(industry)
        if scope:
            parts.append(scope)
        text = " ".join(parts) if parts else "A股上市公司"
        texts.append(f"为这个句子生成表示以用于检索中文金融文档: {text}")
        valid_codes.append(code)

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
        "version": "3.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_stocks": len(valid_codes),
        "n_with_scope": sum(1 for p in profiles.values() if p.get("scope")),
        "n_with_industry": sum(1 for p in profiles.values() if p.get("industry")),
        "embedding_dim": embeddings.shape[1],
        "embedding_model": "BAAI/bge-base-zh-v1.5",
        "total_time_seconds": round(total_time, 1),
    }
    meta_path = PRECOMPUTED_DIR / "precompute_meta.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    logger.info(f"💾 元信息已更新: {meta_path}")

    logger.info("=" * 60)
    logger.info(f"🎉 BGE 嵌入重建完成！总耗时 {total_time:.0f}s")
    logger.info(f"  {len(valid_codes)} 只股票 × {embeddings.shape[1]} 维")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
