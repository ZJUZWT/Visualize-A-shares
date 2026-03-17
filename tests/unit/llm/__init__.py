import sys
from pathlib import Path
_backend = str(Path(__file__).resolve().parent.parent.parent.parent / "backend")
if _backend not in sys.path:
    sys.path.insert(0, _backend)
