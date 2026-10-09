#!/usr/bin/env python3
"""Generate the frozen, self-checking T01 PPA activity workload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from t01_check import cases_for


SEED = 20260927
SELECTION = {
    "AC-05": (0, 7, 19),
    "AC-06": (3,),
    "AC-07": (6,),
    "AC-08A": (4,),
    "AC-08B": (2,),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    vectors: list[int] = []
    selected = {}
    for group, indices in SELECTION.items():
        cases = cases_for(group, SEED)
        selected[group] = list(indices)
        for index in indices:
            vectors.extend(cases[index])
    if not vectors or len(vectors) > 4096:
        raise ValueError(f"T01 power workload has invalid cycle count: {len(vectors)}")
    payload = "".join(f"{vector:06x}\n" for vector in vectors)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(payload)
    print(json.dumps({"task_id": "T01", "seed": SEED, "cycles": len(vectors),
                      "selection": selected,
                      "sha256": hashlib.sha256(payload.encode()).hexdigest()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
