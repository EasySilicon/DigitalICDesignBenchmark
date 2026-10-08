#!/usr/bin/env python3
"""Make an isolated, hash-guarded diagnostic executable with 60-pitch GCells.

This is NOT the installed OpenROAD and is NOT release baseline evidence.
The source equivalent is changing pitches_in_tile from 15 to 60 in the
upstream dbBlock::getGCellTileSize(), commit 08f67ee5ec. Physical track grids,
layer limits, obstruction handling, capacity calculation and STA stay intact.
A source-built tool and a frozen evaluation policy are required for release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import struct
import urllib.request

ORIGINAL_SHA = "fcd7dcfc37d329bd43a7ede75805319a2e70e6879da11d42b4fd1c2e50e645c3"
PREFIX = Path("/home/reefshark/.local/share/openroad-26Q2-1164-g08f67ee5ec")
SOURCE_URL = "https://raw.githubusercontent.com/The-OpenROAD-Project/OpenROAD/08f67ee5ec/src/odb/src/db/dbBlock.cpp"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    original = PREFIX / "usr/bin/openroad"
    data = original.read_bytes()
    if hashlib.sha256(data).hexdigest() != ORIGINAL_SHA:
        raise SystemExit("unrecognized original executable; refusing to patch")
    if data[:6] != b"\x7fELF\x02\x01":
        raise SystemExit("expected little-endian ELF64")
    phoff = struct.unpack_from("<Q", data, 32)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 54)

    def file_offset(va):
        for i in range(phnum):
            kind, flags, offset, vaddr, _, filesz, _, _ = struct.unpack_from(
                "<IIQQQQQQ", data, phoff + i * phentsize
            )
            if kind == 1 and flags & 1 and vaddr <= va < vaddr + filesz:
                return offset + va - vaddr
        raise ValueError(f"no executable segment for {va:#x}")

    # Both return branches of the known getter, checked against disassembly.
    # First: imul ebx,ebx,15 -> imul ebx,ebx,60.
    # Second: (eax << 4) - eax -> imul ebx,eax,60 plus two NOPs.
    patches = [
        (0x30298D5, bytes.fromhex("6b db 0f"), bytes.fromhex("6b db 3c")),
        (0x3029ACF, bytes.fromhex("c1 e3 04 29 c3"), bytes.fromhex("6b d8 3c 90 90")),
    ]
    patched = bytearray(data)
    records = []
    for va, expected, replacement in patches:
        pos = file_offset(va)
        if data[pos:pos + len(expected)] != expected:
            raise SystemExit(f"instruction mismatch at {va:#x}")
        patched[pos:pos + len(expected)] = replacement
        records.append({"va": hex(va), "offset": pos,
                        "before": expected.hex(), "after": replacement.hex()})
    source = urllib.request.urlopen(SOURCE_URL, timeout=30).read().decode()
    old = "const int pitches_in_tile = 15;"
    if source.count(old) != 1:
        raise SystemExit("upstream source no longer matches")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "dbBlock.cpp.original").write_text(source)
    (args.output / "dbBlock.cpp.gcell60").write_text(source.replace(old, "const int pitches_in_tile = 60;"))
    executable = args.output / "openroad-gcell60"
    executable.write_bytes(patched)
    executable.chmod(0o755)
    wrapper = args.output / "openroad"
    dependency_paths = f"{PREFIX}/opt/or-tools/lib:{PREFIX}/usr/lib/x86_64-linux-gnu"
    wrapper.write_text("#!/usr/bin/env bash\nset -euo pipefail\n"
                       f"export LD_LIBRARY_PATH={shlex.quote(dependency_paths)}"
                       '${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}\n'
                       f"exec {shlex.quote(str(executable))} \"$@\"\n")
    wrapper.chmod(0o755)
    metadata = {"diagnostic_only": True, "original": str(original),
                "original_sha256": ORIGINAL_SHA,
                "executable_sha256": hashlib.sha256(patched).hexdigest(),
                "source_url": SOURCE_URL,
                "source_sha256": hashlib.sha256(source.encode()).hexdigest(),
                "source_change": "pitches_in_tile: 15 -> 60",
                "patches": records,
                "changed_byte_count": sum(a != b for a, b in zip(data, patched)),
                "track_grids_modified": False, "capacities_infinite": False}
    (args.output / "manifest.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
