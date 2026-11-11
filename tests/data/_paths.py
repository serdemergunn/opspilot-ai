"""Make sample-data/ importable from tests (the folder name contains a hyphen)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA = REPO_ROOT / "sample-data"
if str(SAMPLE_DATA) not in sys.path:
    sys.path.insert(0, str(SAMPLE_DATA))
