#!/usr/bin/env python3
"""Public, exact-arithmetic numerical contract for T10 (not the hidden tests)."""

from __future__ import annotations

from fractions import Fraction


# Mode: element bits, exponent bits, mantissa bits, exponent bias, MX scaling.
MODES = {
    0: (8, 0, 0, 0, False),
    1: (16, 0, 0, 0, False),
    2: (16, 5, 10, 15, False),
    3: (16, 8, 7, 127, False),
    4: (8, 4, 3, 7, False),
    5: (8, 5, 2, 15, False),
    6: (4, 2, 1, 1, False),
    7: (8, 4, 3, 7, True),
    8: (8, 5, 2, 15, True),
    9: (4, 2, 1, 1, True),
}
NAN = "nan"
POS_INF = "+inf"
NEG_INF = "-inf"
MAX_F32 = Fraction((2**24 - 1) * 2**104)


def pow2(exponent: int) -> Fraction:
    return Fraction(1 << exponent) if exponent >= 0 else Fraction(1, 1 << -exponent)


def decode_element(raw: int, mode: int) -> int | Fraction | str:
    width, exponent_bits, mantissa_bits, bias, _ = MODES[mode]
    if not 0 <= raw < (1 << width):
        raise ValueError("element encoding out of range")
    if mode in (0, 1):
        return raw - (1 << width) if raw & (1 << (width - 1)) else raw
    sign = -1 if raw & (1 << (width - 1)) else 1
    mantissa = raw & ((1 << mantissa_bits) - 1)
    exponent = (raw >> mantissa_bits) & ((1 << exponent_bits) - 1)
    top = (1 << exponent_bits) - 1
    if mode in (4, 7) and exponent == top and mantissa == (1 << mantissa_bits) - 1:
        return NAN  # OFP8 E4M3 has no infinity.
    if mode in (2, 3, 5, 8) and exponent == top:
        return NAN if mantissa else (NEG_INF if sign < 0 else POS_INF)
    if exponent == 0:
        return sign * mantissa * pow2(1 - bias - mantissa_bits)
    return sign * ((1 << mantissa_bits) + mantissa) * pow2(exponent - bias - mantissa_bits)


def decode_f32(bits: int) -> Fraction | str:
    if not 0 <= bits < (1 << 32):
        raise ValueError("binary32 encoding out of range")
    sign = -1 if bits >> 31 else 1
    exp = (bits >> 23) & 0xFF
    mant = bits & 0x7FFFFF
    if exp == 255:
        return NAN if mant else (NEG_INF if sign < 0 else POS_INF)
    if exp == 0:
        return sign * mant * pow2(-149)
    return sign * ((1 << 23) + mant) * pow2(exp - 150)


def scale_value(scale_bus: int, vector: int, k: int) -> Fraction | str:
    code = (scale_bus >> (8 * (2 * vector + k // 32))) & 0xFF
    return NAN if code == 255 else pow2(code - 127)


def element_at(bus: int, vector: int, k: int, mode: int, scale_bus: int) -> Fraction | str:
    width, _, _, _, mx = MODES[mode]
    count = 1024 // (4 * width)
    raw = (bus >> (width * (vector * count + k))) & ((1 << width) - 1)
    value = decode_element(raw, mode)
    if mx:
        scale = scale_value(scale_bus, vector, k)
        if scale == NAN:
            return NAN
        if isinstance(value, Fraction) or isinstance(value, int):
            return value * scale
    return value


def multiply(a: Fraction | str, b: Fraction | str) -> Fraction | str:
    if a == NAN or b == NAN:
        return NAN
    if isinstance(a, str) or isinstance(b, str):
        if a == 0 or b == 0:
            return NAN
        sign_a = -1 if a == NEG_INF or not isinstance(a, str) and a < 0 else 1
        sign_b = -1 if b == NEG_INF or not isinstance(b, str) and b < 0 else 1
        return NEG_INF if sign_a * sign_b < 0 else POS_INF
    return a * b


def dot_terms(a_data: int, b_data: int, a_scale: int, b_scale: int,
              mode: int, row: int, col: int) -> list[Fraction | str]:
    if mode not in MODES or min(a_data, b_data, a_scale, b_scale) < 0 or \
            a_data >= 1 << 1024 or b_data >= 1 << 1024 or \
            a_scale >= 1 << 64 or b_scale >= 1 << 64:
        raise ValueError("invalid command encoding")
    if not 0 <= row < 4 or not 0 <= col < 4:
        raise ValueError("matrix index out of range")
    count = 1024 // (4 * MODES[mode][0])
    return [multiply(element_at(a_data, row, k, mode, a_scale),
                     element_at(b_data, col, k, mode, b_scale))
            for k in range(count)]


def expected_dot(terms: list[Fraction | str]) -> tuple[str, Fraction, Fraction]:
    """Return class, exact sum, absolute sum. Classes: finite/nan/+inf/-inf."""
    if NAN in terms or POS_INF in terms and NEG_INF in terms:
        return NAN, Fraction(0), Fraction(0)
    if POS_INF in terms:
        return POS_INF, Fraction(0), Fraction(0)
    if NEG_INF in terms:
        return NEG_INF, Fraction(0), Fraction(0)
    numeric = [Fraction(t) for t in terms]
    total = sum(numeric, Fraction(0))
    if total > MAX_F32:
        return POS_INF, total, sum(map(abs, numeric), Fraction(0))
    if total < -MAX_F32:
        return NEG_INF, total, sum(map(abs, numeric), Fraction(0))
    return "finite", total, sum(map(abs, numeric), Fraction(0))


def check_output(a_data: int, b_data: int, a_scale: int, b_scale: int,
                 mode: int, c_data: int) -> list[str]:
    """Return one error per mismatching C element, empty on pass."""
    if not 0 <= c_data < 1 << 1024:
        raise ValueError("output width out of range")
    width = MODES[mode][0]
    count = 1024 // (4 * width)
    gamma = Fraction(2 * count, (1 << 24) - 2 * count)
    errors = []
    for row in range(4):
        for col in range(4):
            lane = (c_data >> (64 * (4 * row + col))) & ((1 << 64) - 1)
            label = f"C[{row}][{col}]"
            if mode in (0, 1):
                expected = sum(dot_terms(a_data, b_data, a_scale, b_scale, mode, row, col))
                actual = lane - (1 << 64) if lane >> 63 else lane
                if actual != expected:
                    errors.append(f"{label}: got {actual}, expected {expected}")
                continue
            if lane >> 32:
                errors.append(f"{label}: floating lane upper 32 bits must be zero")
                continue
            raw = lane & 0xFFFFFFFF
            actual = decode_f32(raw)
            kind, exact, sumabs = expected_dot(
                dot_terms(a_data, b_data, a_scale, b_scale, mode, row, col))
            if kind == NAN:
                if actual != NAN or not (raw & (1 << 22)):
                    errors.append(f"{label}: expected quiet NaN")
            elif kind in (POS_INF, NEG_INF):
                if actual != kind:
                    errors.append(f"{label}: got {actual}, expected {kind}")
            elif not isinstance(actual, Fraction):
                errors.append(f"{label}: finite result expected, got {actual}")
            else:
                allowance = gamma * sumabs + (2 * count + 1) * pow2(-149)
                if abs(actual - exact) > allowance:
                    errors.append(f"{label}: error {abs(actual-exact)} exceeds {allowance}")
    return errors
