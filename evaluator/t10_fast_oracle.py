"""Exact dyadic T10 oracle optimized for long continuous streams.

Every legal finite operand is an integer times a power of two. Products and
the gamma-bound comparison therefore use integers; no floating approximation
or early binary32 rounding enters the verdict.
"""

from __future__ import annotations

from fractions import Fraction

from t10_common import DEFAULT_BENCHMARK_ROOT

import sys
sys.path.insert(0, str(DEFAULT_BENCHMARK_ROOT / "evaluator"))
from matmul_oracle import (NAN, NEG_INF, POS_INF, element_at,
                           validate_command)  # noqa: E402

BASE_EXP = -286
MAX_F32_UNITS = ((1 << 24) - 1) << 390
GAMMA_DENOMINATOR = (1 << 24) - 128
SUBNORMAL_ALLOWANCE_UNITS = 129 << 137


def dyadic(value: int | Fraction | str) -> tuple[int, int] | str:
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return value, 0
    denominator = value.denominator
    if denominator & (denominator - 1):
        raise ValueError("non-dyadic value in T10 oracle")
    return value.numerator, 1 - denominator.bit_length()


def f32_class_and_units(bits: int) -> tuple[str, int]:
    sign = -1 if bits >> 31 else 1
    exponent = (bits >> 23) & 255
    mantissa = bits & ((1 << 23) - 1)
    if exponent == 255:
        return (NAN if mantissa else NEG_INF if sign < 0 else POS_INF), 0
    if exponent == 0:
        return "finite", sign * mantissa << 137
    return "finite", sign * ((1 << 23) + mantissa) << (exponent + 136)


def check_output_fast(a_beats: list[int], b_beats: list[int],
                      a_scale: int, b_scale: int, mode: int,
                      output_rows: list[int]) -> list[str]:
    validate_command(a_beats,b_beats,a_scale,b_scale,mode)
    if len(output_rows) != 16 or any(not isinstance(x,int) or
                                     not 0 <= x < 1 << 1024 for x in output_rows):
        raise ValueError("expected sixteen 1024-bit output rows")
    a = [[dyadic(element_at(a_beats,r,k,mode,a_scale))
          for k in range(64)] for r in range(16)]
    b = [[dyadic(element_at(b_beats,c,k,mode,b_scale))
          for k in range(64)] for c in range(16)]
    errors = []
    for row in range(16):
        for col in range(16):
            label = f"C[{row}][{col}]"
            raw = (output_rows[row] >> (64 * col)) & ((1 << 64) - 1)
            exact = 0
            absolute = 0
            seen_nan = seen_plus = seen_minus = False
            for left,right in zip(a[row],b[col]):
                if left == NAN or right == NAN:
                    seen_nan = True
                    continue
                if isinstance(left,str) or isinstance(right,str):
                    if left == (0,0) or right == (0,0):
                        seen_nan = True
                        continue
                    sign_left = -1 if left == NEG_INF or (
                        not isinstance(left,str) and left[0] < 0) else 1
                    sign_right = -1 if right == NEG_INF or (
                        not isinstance(right,str) and right[0] < 0) else 1
                    if sign_left * sign_right < 0:
                        seen_minus = True
                    else:
                        seen_plus = True
                    continue
                if mode in (0,1):
                    term = left[0] * right[0]
                else:
                    shift = left[1] + right[1] - BASE_EXP
                    if shift < 0:
                        raise ValueError("T10 exact accumulator base too small")
                    term = (left[0] * right[0]) << shift
                exact += term
                absolute += abs(term)
            if mode in (0,1):
                actual = raw-(1 << 64) if raw >> 63 else raw
                if actual != exact:
                    errors.append(f"{label}: got {actual}, expected {exact}")
                continue
            if raw >> 32:
                errors.append(f"{label}: floating lane upper 32 bits must be zero")
                continue
            value_bits = raw & ((1 << 32)-1)
            actual_kind, actual = f32_class_and_units(value_bits)
            if seen_nan or (seen_plus and seen_minus):
                if actual_kind != NAN or not (value_bits & (1 << 22)):
                    errors.append(f"{label}: expected quiet NaN")
            elif seen_plus or seen_minus or abs(exact) > MAX_F32_UNITS:
                wanted = (NEG_INF if seen_minus or not seen_plus and exact < 0
                          else POS_INF)
                if actual_kind != wanted:
                    errors.append(f"{label}: got {actual_kind}, expected {wanted}")
            elif actual_kind != "finite":
                errors.append(f"{label}: finite result expected, got {actual_kind}")
            elif abs(actual-exact) * GAMMA_DENOMINATOR > (
                    128*absolute +
                    SUBNORMAL_ALLOWANCE_UNITS*GAMMA_DENOMINATOR):
                errors.append(f"{label}: exact error exceeds allowed bound")
    return errors
