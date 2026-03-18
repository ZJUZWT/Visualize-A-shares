"""测试流式 JSON 提取器和名称归一化"""
import sys
sys.path.insert(0, "backend")

from engine.industry.chain_agent import _StreamingJsonExtractor, _normalize_name


def test_streaming_extractor():
    """验证逐字符喂入时能正确提取 node 和 link 对象"""
    mock_stream = '''{
  "nodes": [
    {
      "name": "PVC",
      "node_type": "material",
      "impact": "neutral",
      "impact_score": 0.0,
      "summary": "核心化工产品"
    },
    {
      "name": "电石",
      "node_type": "material",
      "impact": "neutral",
      "impact_score": 0.0,
      "summary": "PVC上游"
    }
  ],
  "links": [
    {
      "source": "电石",
      "target": "PVC",
      "relation": "upstream"
    }
  ],
  "expand_candidates": ["煤炭"]
}'''

    extractor = _StreamingJsonExtractor()
    all_items = []

    # 模拟逐字符喂入
    for char in mock_stream:
        items = extractor.feed(char)
        all_items.extend(items)

    print(f"提取到 {len(all_items)} 个对象:")
    for item_type, obj in all_items:
        name = obj.get("name", f"{obj.get('source', '?')}->{obj.get('target', '?')}")
        print(f"  → {item_type}: {name}")

    assert len(all_items) == 3, f"期望 3 个对象（2 nodes + 1 link），得到 {len(all_items)}"
    assert all_items[0][0] == "node"
    assert all_items[1][0] == "node"
    assert all_items[2][0] == "link"
    print("✅ 流式 JSON 提取器测试通过")


def test_streaming_with_think_tags():
    """验证能正确跳过 <think> 标签"""
    mock = '<think>我来分析一下...</think>{"nodes": [{"name": "石油", "node_type": "material"}], "links": []}'

    extractor = _StreamingJsonExtractor()
    all_items = []
    for char in mock:
        items = extractor.feed(char)
        all_items.extend(items)

    assert len(all_items) == 1, f"期望 1 个对象，得到 {len(all_items)}"
    assert all_items[0][1]["name"] == "石油"
    print("✅ think tag 跳过测试通过")


def test_streaming_chunk_mode():
    """验证按 chunk（多字符）喂入也能正确工作"""
    chunks = [
        '{"nodes": [{"name": "黄',
        '金", "node_type": "com',
        'modity", "summary": "贵金属"}',
        ', {"name": "白银", "node_type": "commodity"}',
        '], "links": [{"source": "黄金',
        '", "target": "白银", "relation": "substitute"}]}',
    ]

    extractor = _StreamingJsonExtractor()
    all_items = []
    for chunk in chunks:
        items = extractor.feed(chunk)
        all_items.extend(items)
        if items:
            for t, o in items:
                print(f"  chunk → {t}: {o.get('name', o.get('source', '?'))}")

    assert len(all_items) == 3, f"期望 3 个对象，得到 {len(all_items)}"
    print("✅ chunk 模式测试通过")


def test_normalize_name():
    """验证名称归一化"""
    cases = [
        ("PVC（聚氯乙烯）", "PVC"),
        ("聚氯乙烯", "PVC"),
        ("烧碱（氢氧化钠）", "烧碱"),
        ("电石（碳化钙）", "电石"),
        ("碳化钙", "电石"),
        ("多晶硅（硅料）", "多晶硅"),
        ("石油", "原油"),
        ("中泰化学", "中泰化学"),
    ]
    all_pass = True
    for raw, expected in cases:
        result = _normalize_name(raw)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  {'✅' if ok else '❌'} \"{raw}\" → \"{result}\" (期望 \"{expected}\")")

    assert all_pass
    print("✅ 名称归一化测试通过")


if __name__ == "__main__":
    test_streaming_extractor()
    print()
    test_streaming_with_think_tags()
    print()
    test_streaming_chunk_mode()
    print()
    test_normalize_name()
    print("\n🎉 全部测试通过!")
