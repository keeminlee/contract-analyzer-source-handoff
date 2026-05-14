"""Re-export shim for the canonical no-local-fs tests.

Canonical home: `caa_backend/tests/test_no_local_fs.py` (Step 6 spec).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from caa_backend.tests.test_no_local_fs import TestNoLocalFs  # noqa: F401, E402
