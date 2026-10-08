"""Location-independent defaults for standalone T10 backend Python tools."""
from __future__ import annotations

import importlib
import os
from pathlib import Path
import sys


def configured_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def backend_root() -> Path:
    return configured_path("T10_BACKEND_ROOT", Path(__file__).resolve().parents[1])


def repo_root() -> Path:
    return configured_path("T10_REPO_ROOT", backend_root().parents[1])


def scratch_root() -> Path:
    return configured_path("T10_SCRATCH_ROOT", repo_root() / "work/t10_backend")


def load_qualification_module(name: str):
    """Load an explicitly configured evaluator; never search sibling checkouts."""
    evaluator = configured_path("T10_EVALUATOR_ROOT", repo_root() / "evaluator")
    root = configured_path("T10_QUALIFICATION_ROOT", evaluator)
    if not (root / f"{name}.py").is_file():
        raise SystemExit(
            f"Missing T10 qualification module: {root / (name + '.py')}. "
            "Set T10_QUALIFICATION_ROOT to the independent T10 evaluator directory."
        )
    sys.path.insert(0, str(root))
    return importlib.import_module(name)
