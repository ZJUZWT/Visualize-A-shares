"""pytest 全局 fixtures — 路径设置 + 共用 mock"""
import sys
from pathlib import Path

# 将 backend/ 目录加入 Python 路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
