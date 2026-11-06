"""Candidate-independent normal-domain precision and retained range probes."""
from __future__ import annotations

import random
from runner_t10 import Case, ONE, WIDTH, pack_rows
from matmul_oracle import MODES


from t10_range_cases import numeric_group, range_stress_cases


def precision_cases(seed: int = 11) -> list[Case]:
    """256 normal-input cases, including precision-floor and scale tests."""
    rng = random.Random(seed ^ 0x4d4d41)
    cases = []
    for mode in range(2, 10):
        width, ebits, mbits, bias, mx = MODES[mode]
        sign_bit = 1 << (width - 1)
        def normal_code():
            exponent = (rng.randint(bias - 40, bias + 40) if mode == 3 else
                        rng.randint(max(1, bias - 10), min((1 << ebits) - 2, bias + 10))
                        if mode in (2, 5, 8) else rng.randint(1, (1 << ebits) - 2)
                        if mode in (4, 7) else rng.randint(1, 3))
            return (exponent << mbits) | rng.randrange(1 << mbits)
        for index in range(32):
            pattern = index % 8
            a = [[normal_code() for _ in range(64)] for _ in range(16)]
            b = [[normal_code() for _ in range(64)] for _ in range(16)]
            if pattern in (1, 2, 5, 7):
                for matrix in (a, b):
                    for vector in range(16):
                        for k in range(64):
                            if rng.getrandbits(1):
                                matrix[vector][k] |= sign_bit
            if pattern == 2:
                for vector in range(16):
                    for k in range(0, 64, 2):
                        a[vector][k + 1] = a[vector][k] ^ sign_bit
                        b[vector][k + 1] = b[vector][k]
            if pattern == 3:
                for matrix in (a, b):
                    for vector in range(16):
                        for k in range(64):
                            if k not in (0, 31, 32, 63):
                                matrix[vector][k] = 0
            if pattern == 4:
                # One plus many small normal products detects loss of
                # ordinary significant bits without requiring exact dots.
                small_exp = max(1, bias - 12)
                for vector in range(16):
                    a[vector] = [small_exp << mbits] * 64
                    b[vector] = [small_exp << mbits] * 64
                    a[vector][0] = b[vector][0] = ONE[mode]
            if pattern == 6:
                for vector in range(16):
                    a[vector] = [code | sign_bit for code in a[vector]]
            scales = []
            for _ in range(2):
                scales.append(sum((rng.randint(97, 157) if mx and pattern != 4 else 127)
                                  << (8 * i) for i in range(32)))
            cases.append(Case(numeric_group(mode), mode, pack_rows(a, mode),
                              pack_rows(b, mode), *scales, 0, 0, 0,
                              f"mma-normal-v1.m{mode}.p{pattern}.i{index}"))
    return cases
