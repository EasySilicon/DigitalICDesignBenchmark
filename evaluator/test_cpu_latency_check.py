#!/usr/bin/env python3
"""Synthetic trace regression for the T09 port latency oracle."""

from __future__ import annotations

import unittest

from evaluator.cpu_latency_check import (
    EDGE_DELTA, INSTRUCTION_COUNT, START_PC, check_trace,
)


def trace_for_delay(delay: int) -> list[dict]:
    rows = []
    for cycle in range(INSTRUCTION_COUNT + delay):
        fetch_index = cycle
        retire_index = cycle - delay
        rows.append({
            "cycle": cycle,
            "imem_valid_pre": fetch_index < INSTRUCTION_COUNT,
            "imem_addr_pre": START_PC + 4 * fetch_index
            if fetch_index < INSTRUCTION_COUNT else 0,
            "commit_valid_post": 0 <= retire_index < INSTRUCTION_COUNT,
            "commit_pc_post": START_PC + 4 * retire_index
            if 0 <= retire_index < INSTRUCTION_COUNT else 0,
        })
    return rows


class CpuLatencyCheckTest(unittest.TestCase):
    def test_five_stage_timing_passes(self) -> None:
        self.assertTrue(check_trace(trace_for_delay(EDGE_DELTA))["passed"])

    def test_early_commit_fails(self) -> None:
        result = check_trace(trace_for_delay(EDGE_DELTA - 1))
        self.assertFalse(result["passed"])
        self.assertIn("edge delta", result["reason"])

    def test_late_commit_fails(self) -> None:
        result = check_trace(trace_for_delay(EDGE_DELTA + 1))
        self.assertFalse(result["passed"])
        self.assertIn("edge delta", result["reason"])

    def test_missing_commit_fails(self) -> None:
        rows = trace_for_delay(EDGE_DELTA)
        rows[-1]["commit_valid_post"] = False
        self.assertFalse(check_trace(rows)["passed"])

    def test_duplicate_fetch_fails(self) -> None:
        rows = trace_for_delay(EDGE_DELTA)
        rows[1]["imem_addr_pre"] = START_PC
        self.assertIn("duplicate fetch", check_trace(rows)["reason"])

    def test_duplicate_retirement_after_window_fails(self) -> None:
        rows = trace_for_delay(EDGE_DELTA)
        rows.append({
            "cycle": rows[-1]["cycle"] + 1,
            "imem_valid_pre": False,
            "imem_addr_pre": 0,
            "commit_valid_post": True,
            "commit_pc_post": START_PC,
        })
        self.assertIn("duplicate retirement", check_trace(rows)["reason"])


if __name__ == "__main__":
    unittest.main()
