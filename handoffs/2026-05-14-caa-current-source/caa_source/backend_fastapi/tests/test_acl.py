"""Re-export of the canonical cross-user ACL matrix from `caa_backend/tests/test_acl.py`.

The Step 4 spec named `caa_backend/tests/test_acl.py` as the canonical home;
the principal-declared per-step verification command runs unittest discovery
from `backend_fastapi/tests/`. This shim makes the canonical module visible
to that discovery root without duplicating the test bodies.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the contract-analyzer-agent root so `caa_backend.tests.test_acl` is importable.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from caa_backend.tests.test_acl import TestCrossUserACL  # noqa: F401, E402
