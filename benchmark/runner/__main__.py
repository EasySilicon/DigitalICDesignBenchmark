"""Run a complete benchmark suite from a strict local configuration."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .orchestrator import SuiteRunner


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    SuiteRunner(load_config(args.config)).main(preflight_only=args.preflight_only)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
