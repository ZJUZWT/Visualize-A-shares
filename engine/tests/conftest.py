"""量化引擎测试 fixtures"""

import sys
from pathlib import Path

# 确保 engine/ 在 sys.path 中
engine_dir = Path(__file__).resolve().parent.parent
if str(engine_dir) not in sys.path:
    sys.path.insert(0, str(engine_dir))
