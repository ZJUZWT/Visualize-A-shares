"""离线测试 _repair_truncated_json 和 _extract_json 修复逻辑"""
import sys, os
os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, ".")

from engine.industry.chain_agent import (
    _extract_json, _lenient_json_loads, _repair_truncated_json
)

# 模拟截断的 LLM 输出
truncated_output = """<think>
让我分析中泰化学...
</think>

```json
{
  "nodes": [
    {
      "name": "中泰化学",
      "node_type": "company",
      "impact": "neutral",
      "impact_score": 0.0,
      "summary": "国内氯碱化工龙头",
      "representative_stocks": ["002092"],
      "constraint": {
        "node": "中泰化学",
        "shutdown_recovery_time": "3-6个月",
        "restart_cost": "5000万",
        "capacity_ramp_curve": "6-12个月",
        "capacity_ceiling": "PVC 300万吨/年",
        "expansion_lead_time": "3-5年"
      }
    },
    {
      "name": "PVC",
      "node_type": "material",
      "impact": "neutral",
      "impact_score": 0.0,
      "summary": "中泰化学核心产品",
      "representative_stocks": [],
      "constraint": {
        "node": "PVC",
        "shutdown_recovery_time": "2-4周",
        "inventory_buffer_days": "30-45天"
      }
    },
    {
      "name": "烧碱",
      "node_type": "material",
      "impact": "neutral",
      "impact_score": 0.0,
      "summary": "氯碱化工另一主产品",
      "representative_stocks": [],
      "constraint": {
        "node": "烧碱",
        "shutdown_recovery_time": "截断测"""

# 测试 1: _extract_json
print("=== 测试 _extract_json ===")
extracted = _extract_json(truncated_output)
print(f"提取后长度: {len(extracted)}")
print(f"前 200 字符: {extracted[:200]}")
print(f"不含 ```json: {'```' not in extracted}")

# 测试 2: _repair_truncated_json
print("\n=== 测试 _repair_truncated_json ===")
repaired = _repair_truncated_json(extracted)
print(f"修复后长度: {len(repaired)}")
print(f"后 100 字符: {repaired[-100:]}")

# 测试 3: _lenient_json_loads
print("\n=== 测试 _lenient_json_loads ===")
try:
    parsed = _lenient_json_loads(truncated_output)
    nodes = parsed.get("nodes", [])
    links = parsed.get("links", [])
    print(f"✅ 解析成功! 节点: {len(nodes)}, 边: {len(links)}")
    for n in nodes:
        print(f"  节点: {n.get('name')} ({n.get('node_type')})")
except Exception as e:
    print(f"❌ 解析失败: {e}")

# 测试 4: 完全没有截断的情况
print("\n=== 测试正常 JSON ===")
normal = """<think>思考...</think>
```json
{"nodes": [{"name": "石油", "node_type": "material"}], "links": [], "expand_candidates": ["石脑油"]}
```"""
try:
    parsed = _lenient_json_loads(normal)
    print(f"✅ 正常 JSON 解析成功, 节点: {len(parsed.get('nodes', []))}")
except Exception as e:
    print(f"❌ {e}")
