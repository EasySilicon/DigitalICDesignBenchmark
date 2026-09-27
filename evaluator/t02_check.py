#!/usr/bin/env python3
"""Independent T02 hidden acceptance runner and bit-stream oracle."""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from public_check import ROOT, sources_from_filelist


COMMA_P = 0b0011111010
COMMA_N = 0b1100000101
COMMAs = {COMMA_P, COMMA_N}


def symbol_bits(symbol: int) -> list[int]:
    return [(symbol >> bit) & 1 for bit in range(10)]


def bits_to_symbol(bits: list[int]) -> int:
    return sum(bit << index for index, bit in enumerate(bits))


def append_symbol(stream: list[int], symbol: int) -> None:
    stream.extend(symbol_bits(symbol))


def payload_symbol(rng: random.Random) -> int:
    while True:
        value = rng.randrange(1 << 10)
        if value not in COMMAs:
            return value


def append_training(stream: list[int], polarities: tuple[int, int, int]) -> None:
    for polarity in polarities:
        append_symbol(stream, COMMA_N if polarity else COMMA_P)


def append_frame(stream: list[int], rng: random.Random, marker: int | None = None) -> None:
    for _ in range(15):
        append_symbol(stream, payload_symbol(rng))
    append_symbol(stream, payload_symbol(rng) if marker is None else marker)


def chunks(stream: list[int]) -> list[int]:
    stream = list(stream)
    stream.extend([0] * ((-len(stream)) % 10))
    return [bits_to_symbol(stream[start:start + 10])
            for start in range(0, len(stream), 10)]


@dataclass
class Oracle:
    previous: int | None = None
    train: list[int] = field(default_factory=lambda: [0] * 10)
    locked: bool = False
    phase: int = 0
    frame_position: int = 0
    marker_missed_once: bool = False
    symbol_out: int = 0

    def reset(self) -> tuple[int, int, int]:
        self.previous = None
        self.train = [0] * 10
        self.locked = False
        self.phase = 0
        self.frame_position = 0
        self.marker_missed_once = False
        self.symbol_out = 0
        return 0, 0, 0

    def step(self, rst_n: int, valid: int, value: int) -> tuple[int, int, int]:
        if not rst_n:
            return self.reset()
        symbol_valid = False
        if not valid:
            return int(self.locked), 0, self.symbol_out
        old_previous = self.previous
        self.previous = value
        pair_bits = ([] if old_previous is None else symbol_bits(old_previous)) + symbol_bits(value)
        windows = [value] + [
            bits_to_symbol(pair_bits[phase:phase + 10]) if old_previous is not None else 0
            for phase in range(1, 10)
        ]
        if not self.locked:
            found = None
            next_train = list(self.train)
            for phase, window in enumerate(windows):
                if phase != 0 and old_previous is None:
                    continue
                if window in COMMAs:
                    if self.train[phase] == 2 and found is None:
                        found = phase
                    next_train[phase] = min(2, self.train[phase] + 1)
                else:
                    next_train[phase] = 0
            self.train = next_train
            if found is not None:
                self.locked = True
                self.phase = found
                self.frame_position = 0
                self.marker_missed_once = False
                self.train = [0] * 10
            return int(self.locked), 0, self.symbol_out
        self.symbol_out = windows[self.phase]
        symbol_valid = True
        if self.frame_position == 15:
            self.frame_position = 0
            if self.symbol_out in COMMAs:
                self.marker_missed_once = False
            elif self.marker_missed_once:
                self.locked = False
                symbol_valid = False
                self.marker_missed_once = False
                self.train = [0] * 10
            else:
                self.marker_missed_once = True
        else:
            self.frame_position += 1
        return int(self.locked), int(symbol_valid), self.symbol_out


def make_vectors(cycles: list[tuple[int, int, int]]) -> list[int]:
    oracle = Oracle()
    vectors = []
    for rst_n, valid, value in cycles:
        expected_locked, expected_valid, expected_symbol = oracle.step(rst_n, valid, value)
        vectors.append((rst_n << 23) | (valid << 22) | ((value & 0x3ff) << 12) |
                       (expected_locked << 11) | (expected_valid << 10) |
                       (expected_symbol & 0x3ff))
    return vectors


def stream_case(stream: list[int], gap_rng: random.Random | None = None) -> list[tuple[int, int, int]]:
    cycles = [(0, 0, 0), (0, 0, 0), (1, 0, 0)]
    for value in chunks(stream):
        if gap_rng is not None:
            for _ in range(gap_rng.randrange(3)):
                cycles.append((1, 0, gap_rng.randrange(1 << 10)))
        cycles.append((1, 1, value))
    cycles.extend([(1, 0, 0)] * 3)
    return cycles


def cases_for(group: str, seed: int) -> list[list[int]]:
    cases = []
    if group == "AC-05":
        for phase in range(10):
            for polarity in (0, 1):
                rng = random.Random(seed ^ phase ^ (polarity << 8))
                stream = [rng.randrange(2) for _ in range(phase)]
                append_training(stream, (polarity, polarity, polarity))
                append_frame(stream, rng, COMMA_P)
                cases.append(make_vectors(stream_case(stream)))
    elif group == "AC-06":
        for case in range(8):
            rng = random.Random(seed + case)
            stream = [rng.randrange(2) for _ in range((case * 3) % 10)]
            append_training(stream, (0, 1, 0))
            for frame in range(12):
                append_frame(stream, rng, COMMA_N if frame & 1 else COMMA_P)
            cases.append(make_vectors(stream_case(stream)))
    elif group == "AC-07":
        for phase in range(10):
            rng = random.Random(seed ^ (phase << 12))
            stream = [rng.randrange(2) for _ in range(phase)]
            append_training(stream, (phase & 1, 1, 0))
            for frame in range(5):
                append_frame(stream, rng, COMMA_N if (phase + frame) & 1 else COMMA_P)
            cases.append(make_vectors(stream_case(stream, random.Random(seed + phase + 1000))))
    elif group == "AC-08A":
        for case in range(8):
            rng = random.Random(seed + case * 101)
            stream = [rng.randrange(2) for _ in range(case % 10)]
            append_training(stream, (0, 1, 1))
            append_frame(stream, rng, COMMA_P)
            append_frame(stream, rng, None)
            append_frame(stream, rng, None)
            stream.extend(rng.randrange(2) for _ in range((case % 9) + 1))
            append_training(stream, (1, 0, 1))
            for frame in range(3):
                append_frame(stream, rng, COMMA_N if frame & 1 else COMMA_P)
            cases.append(make_vectors(stream_case(stream, random.Random(seed ^ case))))
    elif group == "AC-08B":
        for case in range(6):
            rng = random.Random(seed + case * 211)
            first = [rng.randrange(2) for _ in range(case % 10)]
            append_training(first, (0, 1, 0))
            append_frame(first, rng, COMMA_P)
            first_chunks = chunks(first)
            cycles = [(0, 0, 0), (1, 0, 0)] + [(1, 1, value) for value in first_chunks]
            cycles += [(0, 0, rng.randrange(1 << 10)), (0, 1, rng.randrange(1 << 10)),
                       (1, 0, 0)]
            second = [rng.randrange(2) for _ in range((case * 3 + 1) % 10)]
            append_training(second, (1, 1, 0))
            append_frame(second, rng, COMMA_N)
            cycles += [(1, 1, value) for value in chunks(second)]
            cycles += [(1, 0, 0)] * 3
            cases.append(make_vectors(cycles))
    else:
        raise ValueError(f"unknown group: {group}")
    return cases


def compile_sources(sources: list[Path], build: Path) -> Path:
    command = ["verilator", "--binary", "--timing", "--assert", "-Wno-fatal",
               "-j", "4", "--top-module", "t02_hidden_tb", "--Mdir", str(build),
               *map(str, sources), str(ROOT / "t02_hidden_tb.sv")]
    outcome = subprocess.run(command, text=True, capture_output=True, timeout=180)
    if outcome.returncode:
        raise RuntimeError("compile failed:\n" + (outcome.stdout + outcome.stderr)[-8000:])
    return build / "Vt02_hidden_tb"


def run(submission: Path | None, seed: int) -> dict:
    results = {}
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_T02_hidden_") as temporary:
        temporary_path = Path(temporary)
        sources = (sources_from_filelist(submission) if submission is not None else
                   [ROOT / "reference/T02/serdes_rx_comma_aligner.sv"])
        binary = compile_sources(sources, temporary_path / "build")
        for group in ("AC-05", "AC-06", "AC-07", "AC-08A", "AC-08B"):
            passed = 0
            cases = cases_for(group, seed)
            for index, vectors in enumerate(cases):
                vector_file = temporary_path / f"{group}_{index}.mem"
                vector_file.write_text("".join(f"{vector:06x}\n" for vector in vectors))
                outcome = subprocess.run(
                    [str(binary), f"+VECTORS={vector_file}", f"+COUNT={len(vectors)}"],
                    text=True, capture_output=True, timeout=20,
                )
                passed += outcome.returncode == 0 and "HIDDEN_PASS T02" in outcome.stdout
            results[group] = {"cases_passed": int(passed), "cases_total": len(cases),
                              "safety_violation": False}
    return {"task_id": "T02", "seed": seed, "groups": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("submission", nargs="?", type=Path)
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--seed", type=int, default=20260927)
    args = parser.parse_args()
    try:
        if args.reference == (args.submission is not None):
            parser.error("provide exactly one submission path or --reference")
        result = run(None if args.reference else args.submission.resolve(), args.seed)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result = {"task_id": "T02", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if "error" not in result and all(
        row["cases_passed"] == row["cases_total"] for row in result["groups"].values()
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
