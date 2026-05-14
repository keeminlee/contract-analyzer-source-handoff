"""Re-export shim for the canonical soft-delete tests.

Canonical home: `caa_backend/tests/test_soft_delete.py` (Step 5 spec).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from caa_backend.tests.test_soft_delete import TestSoftDeleteEndpoint  # noqa: F401, E402
