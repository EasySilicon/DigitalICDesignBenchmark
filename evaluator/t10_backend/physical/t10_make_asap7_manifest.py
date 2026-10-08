#!/usr/bin/env python3
"""Create a deterministic SHA-256 manifest for the complete ORFS ASAP7 platform."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    platform = args.platform.resolve(strict=True)
    if not platform.is_dir():
        parser.error(f"platform is not a directory: {platform}")

    files = []
    for path in sorted(item for item in platform.rglob("*") if item.is_file()):
        files.append({
            "path": path.relative_to(platform).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    if not files:
        parser.error("platform tree contains no files")
    record = {
        "schema_version": 1,
        "platform": "ASAP7_7p5t_RVT_NLDM",
        "root_name": platform.name,
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(record, indent=2) + "\n")
    temporary.replace(args.output)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "file_count": len(files),
        "total_bytes": record["total_bytes"],
        "sha256": sha256(args.output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
