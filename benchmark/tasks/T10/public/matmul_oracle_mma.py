"""T10 MMA-inspired FP32 numerical envelope, independent of exact-dot-v1.

PTX leaves accumulation order, rounding and subnormal handling unspecified.
This is an executable benchmark policy, NOT a bit-exact NVIDIA emulator or a
vendor conformance certificate. See ../mma-profile-v1.json for its limits.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache

from .matmul_oracle import (MODES, NAN, NEG_INF, POS_INF, decode_element,
                            validate_command)

PROFILE_ID = "mma-f32-envelope-v1"
BASE_EXP = -286
MAX_UNITS = ((1 << 24) - 1) << 390
MIN_NORMAL_UNITS = 1 << 160  # 2^-126 / 2^-286
# Directed rounding can lose almost one ulp, rather than half an ulp.
GAMMA_DENOMINATOR = (1 << 23) - 128
UNDERFLOW_UNITS = 129 * MIN_NORMAL_UNITS


@dataclass(frozen=True, slots=True)
class Operand:
    coefficient: int = 0
    exponent: int = 0
    kind: str = "finite"
    flushable: bool = False
    outside_f32: bool = False


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    checked_lanes: int = 0
    diagnostic_lanes: int = 0
    subnormal_affected_lanes: int = 0
    reasons: Counter = field(default_factory=Counter)


@lru_cache(maxsize=131072)
def _operand(raw: int, mode: int, scale: int) -> Operand:
    width, ebits, mbits, _, mx = MODES[mode]
    if mx and scale == 255:
        return Operand(kind=NAN)
    value = decode_element(raw, mode)
    if isinstance(value, str):
        return Operand(kind=value)
    value = Fraction(value)
    exponent = 1 - value.denominator.bit_length()
    coefficient = value.numerator
    if mx:
        exponent += scale - 127
    # A source-format subnormal may be flushed before block scaling. A
    # binary32 subnormal decoded/scaled input may also be flushed.
    source_subnormal = mode > 1 and not ((raw >> mbits) & ((1 << ebits) - 1)) \
        and bool(raw & ((1 << mbits) - 1))
    scaled = Fraction(coefficient) * (Fraction(1 << exponent) if exponent >= 0
                                      else Fraction(1, 1 << -exponent))
    return Operand(coefficient, exponent, flushable=bool(source_subnormal or
                   0 < abs(scaled) < Fraction(1, 1 << 126)),
                   outside_f32=abs(scaled) > ((1 << 24) - 1) * (1 << 104))


def _f32(raw: int) -> tuple[str, int]:
    sign = -1 if raw >> 31 else 1
    exponent, mantissa = (raw >> 23) & 255, raw & 0x7fffff
    if exponent == 255:
        return (NAN if mantissa else NEG_INF if sign < 0 else POS_INF), 0
    if exponent == 0:
        return "finite", sign * mantissa << 137
    return "finite", sign * ((1 << 23) + mantissa) << (exponent + 136)


def _dot(left: list[Operand], right: list[Operand], raw: int) -> tuple[str, str, bool]:
    """Return pass/fail/diagnostic, explanation, subnormal involvement."""
    exact = lower = upper = absolute = positive = negative = 0
    seen_nan = seen_plus = seen_minus = False
    outside = flush_invalid = subnormal = False
    for a, b in zip(left, right):
        subnormal |= a.flushable or b.flushable
        if a.kind == NAN or b.kind == NAN:
            seen_nan = True
            continue
        outside |= a.outside_f32 or b.outside_f32
        if a.kind != "finite" or b.kind != "finite":
            if ((a.kind == "finite" and a.coefficient == 0) or
                    (b.kind == "finite" and b.coefficient == 0)):
                seen_nan = True
                continue
            flush_invalid |= a.flushable or b.flushable
            sa = -1 if a.kind == NEG_INF or a.kind == "finite" and a.coefficient < 0 else 1
            sb = -1 if b.kind == NEG_INF or b.kind == "finite" and b.coefficient < 0 else 1
            if sa * sb < 0:
                seen_minus = True
            else:
                seen_plus = True
            continue
        shift = a.exponent + b.exponent - BASE_EXP
        if shift < 0:
            raise ValueError("MMA oracle fixed-point base too small")
        term = (a.coefficient * b.coefficient) << shift
        exact += term
        absolute += abs(term)
        positive += max(term, 0)
        negative += max(-term, 0)
        if a.flushable or b.flushable:
            lower += min(term, 0)
            upper += max(term, 0)
        else:
            lower += term
            upper += term
    kind, actual = _f32(raw)
    if kind == NAN and not raw & (1 << 22):
        return "fail", "signaling NaN is not an accepted result", subnormal
    if seen_nan or seen_plus and seen_minus:
        return ("pass", "explicit_invalid", subnormal) if kind == NAN else \
            ("fail", "explicit invalid operation requires quiet NaN", subnormal)
    if outside:
        return "diagnostic", "mx_operand_outside_binary32", subnormal
    budget = 128 * absolute + UNDERFLOW_UNITS * GAMMA_DENOMINATOR
    # Opposite-sign rounding error cannot create a same-sign overflow path.
    # In particular, an enormous positive-only dot cannot produce -Inf/NaN.
    def overflow_possible(mass):
        return bool(mass and mass * (GAMMA_DENOMINATOR + 128) +
                    UNDERFLOW_UNITS * GAMMA_DENOMINATOR >= MAX_UNITS * GAMMA_DENOMINATOR)
    positive_overflow = overflow_possible(positive)
    negative_overflow = overflow_possible(negative)
    if seen_plus or seen_minus:
        expected = POS_INF if seen_plus else NEG_INF
        invalid_possible = flush_invalid or (negative_overflow if seen_plus else positive_overflow)
        if kind == expected or kind == NAN and invalid_possible:
            return "pass", "infinite_input", subnormal
        return "fail", "infinite input requires its infinity or a possible invalid operation", subnormal
    if kind == NAN:
        if positive_overflow and negative_overflow:
            return "diagnostic", "overflow_order_dependent_nan", subnormal
        return "fail", "NaN has no permitted invalid or opposing-overflow path", subnormal
    if kind in (POS_INF, NEG_INF):
        possible = positive_overflow if kind == POS_INF else negative_overflow
        if possible:
            return "diagnostic", "overflow_order_dependent_infinity", subnormal
        return "fail", "infinity has no same-sign overflow path", subnormal
    distance = max(lower - actual, actual - upper, 0)
    if distance * GAMMA_DENOMINATOR <= budget:
        return "pass", "fp32_error_envelope", subnormal
    # Directed overflow rounding can return the largest finite value.
    if abs(actual) == MAX_UNITS and (positive_overflow if actual > 0 else negative_overflow):
        return "diagnostic", "directed_overflow_saturation", subnormal
    if positive_overflow and negative or negative_overflow and positive:
        return "diagnostic", "overflow_sensitive_finite_result", subnormal
    return "fail", "finite result exceeds FP32 error envelope", subnormal


def check_output_mma(a_beats: list[int], b_beats: list[int], a_scale: int,
                     b_scale: int, mode: int, output_rows: list[int]) -> CheckResult:
    """Check every lane; explicitly count outcomes requiring diagnostic review.

    A diagnostic is not a numerical pass. Protocol and encoding checks remain
    mandatory even when the numerical behavior is implementation-dependent.
    """
    validate_command(a_beats, b_beats, a_scale, b_scale, mode)
    if len(output_rows) != 16 or any(not isinstance(x, int) or
                                    not 0 <= x < 1 << 1024 for x in output_rows):
        raise ValueError("expected sixteen 1024-bit output rows")
    width = MODES[mode][0]
    lanes = 64 // width

    def matrix(beats, scales):
        return [[_operand((beats[k // lanes] >> (width * (vector * lanes + k % lanes))) &
                          ((1 << width) - 1), mode,
                          (scales >> (8 * (2 * vector + k // 32))) & 255)
                 for k in range(64)] for vector in range(16)]

    a, b = matrix(a_beats, a_scale), matrix(b_beats, b_scale)
    def identities(vectors):
        unique = {}
        return [unique.setdefault(tuple(vector), len(unique)) for vector in vectors]
    a_ids, b_ids = identities(a), identities(b)
    dot_cache, integer_cache = {}, {}
    result = CheckResult()
    for row in range(16):
        for col in range(16):
            label = f"C[{row}][{col}]"
            lane = (output_rows[row] >> (64 * col)) & ((1 << 64) - 1)
            if mode < 2:
                key = a_ids[row], b_ids[col]
                if key not in integer_cache:
                    integer_cache[key] = sum(x.coefficient * y.coefficient for x, y in zip(a[row], b[col]))
                expected = integer_cache[key]
                actual = lane - (1 << 64) if lane >> 63 else lane
                status, reason, subnormal = ("pass", "exact_int64", False) if actual == expected else \
                    ("fail", f"got {actual}, expected exact INT64 {expected}", False)
            elif lane >> 32:
                status, reason, subnormal = "fail", "floating lane upper 32 bits must be zero", False
            else:
                key = a_ids[row], b_ids[col], lane
                if key not in dot_cache:
                    dot_cache[key] = _dot(a[row], b[col], lane)
                status, reason, subnormal = dot_cache[key]
            result.subnormal_affected_lanes += subnormal
            result.reasons[reason] += 1
            if status == "diagnostic":
                result.diagnostic_lanes += 1
                if len(result.diagnostics) < 3:
                    result.diagnostics.append(f"{label}: {reason}")
            else:
                result.checked_lanes += 1
                if status == "fail":
                    result.errors.append(f"{label}: {reason}")
    return result
