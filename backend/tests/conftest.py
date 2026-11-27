import sys
from pathlib import Path

# Allows tests to run even before an editable installation.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
