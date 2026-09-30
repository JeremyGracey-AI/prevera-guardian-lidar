import sys
from pathlib import Path
REPO_ROOT = Path(__file__).resolve().parents[3]        # test -> prevera_perception -> src -> repo
HARNESS_DIR = REPO_ROOT / "tools" / "bag_analysis"
PACKAGE_DIR = REPO_ROOT / "src" / "prevera_perception"  # so bare `pytest test/` imports prevera_perception without colcon
JETSON_DIR = REPO_ROOT / "jetson"  # runners share their local transport module, as when executed on the device
for _p in (HARNESS_DIR, PACKAGE_DIR, JETSON_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
