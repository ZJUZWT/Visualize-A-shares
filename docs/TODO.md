# TODO

## 已完成

- [x] **"推荐股票"报错问题** — 修复了 `_fallback_think_parse` 中缺少"推荐/选股/买什么"等关键词，新增 `THINK_SYSTEM_PROMPT` 决策规则覆盖推荐类查询
- [x] **RAG 去重 & 垃圾数据整理** — RAGStore report_id 改为天级精度（同天同代码同类型 upsert 覆盖），AgentMemory.store() 改为天级精度 upsert，新增 `cleanup_expired()` 和 `dedup_by_code()` 方法
