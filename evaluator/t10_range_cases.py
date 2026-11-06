"""Shared strict T10 range and cancellation probes; no relaxed arithmetic."""
from __future__ import annotations

from runner_t10 import Case, WIDTH, pack_rows


def numeric_group(mode: int) -> str:
    return {2: "MM-F16", 3: "MM-F16", 4: "MM-F8", 5: "MM-F8",
            6: "MM-F4", 7: "MM-MX8", 8: "MM-MX8", 9: "MM-MX4"}[mode]


def range_stress_cases() -> list[Case]:
    """The 82 probes previously audited privately, with unchanged operands."""
    cases = []
    def add(mode, name, sign, terms, scale):
        width = WIDTH[mode]
        a, b = [[0] * 64 for _ in range(16)], [[0] * 64 for _ in range(16)]
        for k, ac, bc, direction in terms:
            for vector in range(16):
                a[vector][k] = ac | ((1 << (width - 1)) if direction < 0 else 0)
                b[vector][k] = bc
        bus = 0 if mode == 3 else sum(scale << (8 * i) for i in range(32))
        cases.append(Case(numeric_group(mode), mode, pack_rows(a, mode),
                          pack_rows(b, mode), bus, bus, 0, 0, 0,
                          f"opus-numeric-review-v1.m{mode}.{name}."
                          f"{'negative' if sign < 0 else 'positive'}"))
    patterns = ["within_pair_cancel_then_residual", "small_between_huge", "small_before_huge",
                "small_with_second_huge", "same_beat_mixed_cancel", "exact_zero",
                "no_cancel", "finite_residual"]
    for mode in (3, 7, 8, 9):
        lanes = 64 // WIDTH[mode]
        huge, tiny, scale = {3: (227 << 7, 192 << 7, 0), 7: (0x7e, 0x01, 201),
                             8: (0x7b, 0x01, 208), 9: (0x7, 0x1, 193)}[mode]
        for sign in (1, -1):
            for pattern in patterns:
                h, r, sc = huge, tiny, scale
                seq = [(0, h, h, 1), (lanes, r, r, sign), (2 * lanes, h, h, -1)]
                if pattern == "within_pair_cancel_then_residual":
                    seq = [(0, h, h, 1), (lanes, h, h, -1), (2 * lanes, r, r, sign)]
                elif pattern == "small_before_huge":
                    seq = [(0, r, r, sign), (lanes, h, h, 1), (2 * lanes, h, h, -1)]
                elif pattern == "small_with_second_huge":
                    seq = [(0, h, h, 1), (2 * lanes, h, h, -1), (3 * lanes, r, r, sign)]
                elif pattern == "same_beat_mixed_cancel":
                    seq = [(0, h, h, 1), (1, r, r, sign), (2, h, h, -1)]
                elif pattern == "exact_zero":
                    seq = [(0, h, h, sign), (2 * lanes, h, h, -sign)]
                elif pattern == "no_cancel":
                    seq = [(0, h, h, sign), (lanes, r, r, sign)]
                elif pattern == "finite_residual":
                    if mode == 3:
                        r = 0x3f80
                    else:
                        sc = {7: 136, 8: 143, 9: 128}[mode]
                    seq = [(0, h, h, 1), (lanes, r, r, sign), (2 * lanes, h, h, -1)]
                add(mode, pattern, sign, seq, sc)
    def power2(mode, exponent):
        if mode == 7:
            return (exponent + 7) << 3 if exponent >= -6 else 1 << (exponent + 9)
        return (exponent + 15) << 2 if exponent >= -14 else 1 << (exponent + 16)
    for mode in (3, 7, 8):
        for sign in (1, -1):
            for pattern in ("max_exact", "max_plus_tiny_same_beat", "max_plus_tiny_late"):
                if mode == 3:
                    seq = [(i, code, 0x3f80, sign) for i, code in
                           enumerate((0x7f7f, 0x7b7f, 0x777f))]
                    scale = 0
                    if pattern != "max_exact":
                        seq.append((3 if pattern.endswith("same_beat") else 63,
                                    0x3f80, 0x3f80, sign))
                else:
                    scale = 183
                    seq = [(i, power2(mode, (15 - i) // 2),
                            power2(mode, 15 - i - (15 - i) // 2), sign) for i in range(24)]
                    if pattern != "max_exact":
                        seq.append((24 if pattern.endswith("same_beat") else 63, 1, 1, sign))
                add(mode, pattern, sign, seq, scale)
    return cases
