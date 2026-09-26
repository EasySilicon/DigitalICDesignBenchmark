"""Compatibility import for T10's task-local public numerical oracle."""

from __future__ import annotations

import sys
from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from benchmark.tasks.T10.public.matmul_oracle import *  # noqa: F403
