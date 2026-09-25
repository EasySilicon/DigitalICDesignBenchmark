#!/usr/bin/env python3
"""Generate three public RV32I ELF smoke programs without a compiler dependency."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

RESET_PC = 0x8000_0000


def addi(rd: int, rs1: int, imm: int) -> int:
    if not -2048 <= imm <= 2047:
        raise ValueError("ADDI immediate out of range")
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (rd << 7) | 0x13


def lui(rd: int, imm20: int) -> int:
    return (imm20 << 12) | (rd << 7) | 0x37


def add(rd: int, rs1: int, rs2: int) -> int:
    return (rs2 << 20) | (rs1 << 15) | (rd << 7) | 0x33


def load_word(rd: int, rs1: int, imm: int = 0) -> int:
    return ((imm & 0xFFF) << 20) | (rs1 << 15) | (2 << 12) | (rd << 7) | 0x03


def store_word(rs2: int, rs1: int, imm: int = 0) -> int:
    bits = imm & 0xFFF
    return ((bits >> 5) << 25) | (rs2 << 20) | (rs1 << 15) | \
        (2 << 12) | ((bits & 0x1F) << 7) | 0x23


def bne(rs1: int, rs2: int, offset: int) -> int:
    if offset % 2 or not -4096 <= offset <= 4094:
        raise ValueError("BNE offset out of range")
    bits = offset & 0x1FFF
    return (((bits >> 12) & 1) << 31) | (((bits >> 5) & 0x3F) << 25) | \
        (rs2 << 20) | (rs1 << 15) | (1 << 12) | \
        (((bits >> 1) & 0xF) << 8) | (((bits >> 11) & 1) << 7) | 0x63


def finish(value: int) -> list[int]:
    return [lui(31, 0x8003F), addi(30, 0, value), store_word(30, 31),
            0x0000_006F]


def program(name: str) -> list[int]:
    if name == "basic":
        return [addi(1, 0, 1), lui(2, 0x8003F), store_word(1, 2),
                0x0000_006F]
    if name == "arithmetic":
        words = [addi(3, 0, 5), addi(4, 0, 7), add(5, 3, 4),
                 addi(6, 0, 12), 0]
    elif name == "memory":
        words = [lui(10, 0x80000), addi(10, 10, 0x100),
                 addi(1, 0, 0x55), store_word(1, 10),
                 load_word(2, 10), 0]
    else:
        raise ValueError(f"unknown program: {name}")
    branch_index = len(words) - 1
    words += finish(1)
    fail_index = len(words)
    words += finish(2)
    rs1, rs2 = (5, 6) if name == "arithmetic" else (1, 2)
    words[branch_index] = bne(rs1, rs2, (fail_index - branch_index) * 4)
    return words


def write_elf(words: list[int], path: Path) -> None:
    code = b"".join(struct.pack("<I", word) for word in words)
    ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", ident, 2, 243, 1,
                         RESET_PC, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    ph = struct.pack("<IIIIIIII", 1, 84, RESET_PC, RESET_PC,
                     len(code), len(code), 5, 4)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + ph + code)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    for name in ("basic", "arithmetic", "memory"):
        path = args.output_dir / f"{name}.elf"
        write_elf(program(name), path)
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
