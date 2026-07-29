from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_packaging_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, str(root / "packaging" / "validate.py")],
        cwd=root,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
