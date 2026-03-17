"""集成测试 fixtures — 继承根 conftest 的 sys.path 注入"""

import sys
from pathlib import Path

# 确保 backend/ 在 sys.path 中
backend_dir = str(Path(__file__).resolve().parent.parent.parent / "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
