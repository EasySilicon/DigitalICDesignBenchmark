#!/usr/bin/env python3
"""Inspect the sixteen-tile hierarchy used by the experimental reference backend.

This physical assembly helper expects sixteen identical 4x4 tiles. It is not
an extra functional requirement on benchmark candidates; the generic
256-PE mesh check lives in evaluator/t10_structure_check.py on main.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

from t10_paths import repo_root
DEFAULT_BENCHMARK_ROOT = repo_root()

import sys
sys.path.insert(0, str(DEFAULT_BENCHMARK_ROOT / "evaluator"))
from public_check import sources_from_filelist  # noqa: E402

from t10_structure_check import TOP  # noqa: E402


def _user_instances(module: dict, modules: dict) -> list[tuple[str, dict]]:
    return [(name, cell) for name, cell in module.get("cells", {}).items()
            if cell.get("type") in modules]


def _pe_candidates(modules: dict) -> list[str]:
    candidates = []
    for name, body in modules.items():
        inputs = sum(port.get("direction") == "input" and
                     len(port.get("bits", [])) == 64
                     for port in body.get("ports", {}).values())
        outputs = sum(port.get("direction") == "output" and
                      len(port.get("bits", [])) == 64
                      for port in body.get("ports", {}).values())
        if inputs >= 2 and outputs >= 3:
            candidates.append(name)
    return sorted(candidates)


def hierarchy_contract(design: dict, pe_module: str) -> dict:
    modules = design.get("modules", {})
    if TOP not in modules or pe_module not in modules:
        return {"passed": False, "reason": "top or PE module is absent"}

    top_instances = _user_instances(modules[TOP], modules)
    counts = Counter(cell["type"] for _, cell in top_instances)
    candidates = []
    for tile_module, tile_count in sorted(counts.items()):
        if tile_count != 16 or tile_module == pe_module:
            continue
        tile_instances = _user_instances(modules[tile_module], modules)
        pe_count = sum(cell["type"] == pe_module for _, cell in tile_instances)
        if pe_count == 16:
            candidates.append((tile_module, tile_instances))

    if len(candidates) != 1:
        return {
            "passed": False,
            "reason": "expected one module type instantiated 16 times at top "
                      "with 16 PE instances per tile",
            "candidate_tile_modules": [name for name, _ in candidates],
            "top_user_module_counts": dict(sorted(counts.items())),
        }

    tile_module, tile_instances = candidates[0]
    nested_non_pe = Counter(cell["type"] for _, cell in tile_instances
                            if cell["type"] != pe_module)
    return {
        "passed": True,
        "top_module": TOP,
        "tile_module": tile_module,
        "tile_instances": 16,
        "pe_module": pe_module,
        "pe_instances_per_tile": 16,
        "pe_instances_total": 256,
        "tile_non_pe_module_counts": dict(sorted(nested_non_pe.items())),
        "method": "yosys_preserved_hierarchy",
    }


def inspect(submission: Path) -> dict:
    sources = sources_from_filelist(submission.resolve())
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_t10_ppa_hier_") as temp:
        output = Path(temp) / "hierarchy.json"
        script = ("read_verilog -sv " + " ".join(map(str, sources)) +
                  f"; hierarchy -top {TOP}; proc; opt_clean; write_json {output}")
        compiled = subprocess.run(["yosys", "-Q", "-T", "-p", script],
                                  capture_output=True, text=True, timeout=300)
        if compiled.returncode:
            return {"passed": False, "status": "failed",
                    "reason": "Yosys hierarchy elaboration failed"}
        design = json.loads(output.read_text())
        candidates = _pe_candidates(design["modules"])
        if len(candidates) != 1:
            return {"passed": False, "status": "failed",
                    "reason": "expected one PE module interface",
                    "candidate_pe_modules": candidates}
        result = hierarchy_contract(design, candidates[0])
        result["status"] = "qualified" if result["passed"] else "failed"
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", type=Path)
    args = parser.parse_args()
    result = inspect(args.submission)
    print(json.dumps(result, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
