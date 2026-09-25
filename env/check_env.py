#!/usr/bin/env python3
"""Read-only dependency check for benchmark specification and planned runners."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROFILES = ("spec", "functional", "ppa", "cpu", "all")


def command(name: str, version_arg: str = "--version") -> dict:
    path = shutil.which(name)
    if path is None:
        return {"name": name, "ok": False, "detail": "not found on PATH"}
    try:
        result = subprocess.run([path, version_arg], capture_output=True, text=True,
                                timeout=10, check=False)
        version = (result.stdout or result.stderr).splitlines()
        detail = version[0].strip() if version else f"exit {result.returncode}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "ok": False, "detail": str(exc)}
    return {"name": name, "ok": result.returncode == 0, "detail": detail, "path": path}


def minimum_version(result: dict, pattern: str, minimum: tuple[int, ...]) -> dict:
    if result["ok"]:
        match = re.search(pattern, result["detail"])
        actual = tuple(map(int, match.groups())) if match else ()
        if actual < minimum:
            result["ok"] = False
            result["detail"] += f"; need >= {'.'.join(map(str, minimum))}"
    return result


def package(name: str) -> dict:
    try:
        version = importlib.metadata.version(name)
        return {"name": name, "ok": True, "detail": version}
    except importlib.metadata.PackageNotFoundError:
        return {"name": name, "ok": False, "detail": "not installed"}


def yosys(minimum: tuple[int, int] | None = None) -> dict:
    result = command("yosys", "-V")
    if result["ok"] and minimum is not None:
        match = re.search(r"Yosys\s+(\d+)\.(\d+)", result["detail"])
        if match is None or tuple(map(int, match.groups())) < minimum:
            result["ok"] = False
            result["detail"] += f"; need >= {minimum[0]}.{minimum[1]} for ORFS prebuilt path"
    return result


def directory(name: str, path: Path | None, required_child: str) -> dict:
    if path is None:
        return {"name": name, "ok": False, "detail": "path not supplied"}
    child = path.expanduser().resolve() / required_child
    return {"name": name, "ok": child.is_file(),
            "detail": str(child) if child.is_file() else f"missing {child}"}


def git_revision(name: str, path: Path | None, expected: str) -> dict:
    if path is None or not path.expanduser().is_dir():
        return {"name": name, "ok": False, "detail": "checkout path not supplied/found"}
    try:
        result = subprocess.run(["git", "-C", str(path.expanduser()), "rev-parse", "HEAD"],
                                capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"name": name, "ok": False, "detail": str(exc)}
    actual = result.stdout.strip()
    return {"name": name, "ok": result.returncode == 0 and actual == expected,
            "detail": f"{actual or result.stderr.strip()} (expected {expected})"}


def platform_hashes(root: Path, manifest: Path) -> dict:
    try:
        entries = [line.split("  ", 1) for line in manifest.read_text().splitlines()]
        failures = []
        for expected, relative in entries:
            target = (root / relative).resolve(strict=True)
            if not target.is_relative_to(root.resolve()) or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
                failures.append(relative)
        return {"name": "vendored ASAP7 SHA-256", "ok": bool(entries) and not failures,
                "detail": f"{len(entries)} files checked; mismatches: {failures[:5]}"}
    except (OSError, ValueError) as exc:
        return {"name": "vendored ASAP7 SHA-256", "ok": False, "detail": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="spec")
    parser.add_argument("--orfs-root", type=Path, help="OpenROAD-flow-scripts checkout")
    parser.add_argument("--act4-root", type=Path, help="riscv-arch-test ACT4 checkout")
    parser.add_argument("--json", action="store_true", help="print machine-readable result")
    parser.add_argument("--verify-platform-hashes", action="store_true",
                        help="check every vendored ASAP7 source file against SHA256SUMS")
    args = parser.parse_args()
    wanted = set(PROFILES[:-1]) if args.profile == "all" else {args.profile}
    lock_path = Path(__file__).resolve().parent.parent / "benchmark" / "sources.lock.yaml"
    try:
        import yaml
        sources = yaml.safe_load(lock_path.read_text())
    except (ImportError, OSError):
        sources = None
    checks: dict[str, list[dict]] = {}
    if "spec" in wanted:
        checks["spec"] = [
            {"name": "Python >=3.10", "ok": sys.version_info >= (3, 10),
             "detail": sys.version.split()[0]},
            package("PyYAML"), package("jsonschema"),
        ]
    if "functional" in wanted:
        checks["functional"] = [command("verilator"), yosys(),
                                command("c++"), package("cocotb")]
    if "ppa" in wanted:
        repo_root = Path(__file__).resolve().parent.parent
        platform = repo_root / "vendor" / "asap7"
        checks["ppa"] = [
            {"name": "sources.lock.yaml parse", "ok": sources is not None,
             "detail": "PyYAML + readable lock file required"},
            yosys((0, 58)), command("openroad", "-version"), command("make"),
            directory("vendored ASAP7 platform", platform, "config.mk"),
            directory("ORFS flow scripts", args.orfs_root, "flow/Makefile"),
        ]
        if args.verify_platform_hashes:
            checks["ppa"].append(platform_hashes(platform, platform / "SHA256SUMS"))
        if sources is not None:
            checks["ppa"].append(git_revision("ORFS revision", args.orfs_root,
                                              sources["ppa"]["flow_revision"]))
    if "cpu" in wanted:
        gcc = minimum_version(command("riscv32-unknown-elf-gcc"),
                              r"(\d+)\.(\d+)\.\d+\s*$", (15, 0))
        checks["cpu"] = [
                         {"name": "sources.lock.yaml parse", "ok": sources is not None,
                          "detail": "PyYAML + readable lock file required"},
                         gcc, command("riscv32-unknown-elf-objdump"),
                         minimum_version(command("sail_riscv_sim"),
                                         r"^(\d+)\.(\d+)\.(\d+)", (0, 14, 1)),
                         minimum_version(command("uv"),
                                         r"uv\s+(\d+)\.(\d+)\.(\d+)", (0, 11, 33)),
                         minimum_version(command("ruby", "--version"),
                                         r"ruby\s+(\d+)\.(\d+)\.(\d+)", (3, 4, 10)),
                         minimum_version(command("bundle", "--version"),
                                         r"(\d+)\.(\d+)\.(\d+)", (4, 0, 21)),
                         directory("ACT4 checkout", args.act4_root, "README.md")]
        if sources is not None:
            checks["cpu"].append(git_revision("ACT4 revision", args.act4_root,
                                              sources["riscv"]["arch_test_revision"]))
    result = {"profile": args.profile, "checks": checks,
              "ok": all(item["ok"] for group in checks.values() for item in group)}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for profile, group in checks.items():
            print(f"[{profile}]")
            for item in group:
                mark = "OK" if item["ok"] else "MISSING"
                print(f"  {mark:<7} {item['name']}: {item['detail']}")
        print("READY" if result["ok"] else "INCOMPLETE")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
