"""Independent witnesses and negative controls for the separate MMA profile."""
import math
import random
import struct
import unittest
from fractions import Fraction

from matmul_oracle import MAX_F32, check_output, decode_f32, dot_terms, pow2
from runner_t10 import Case, ONE, WIDTH, pack_rows
from runner_t10_mma import evaluate, mma_cases
from t10_mma_cases import precision_cases, range_stress_cases
from t10_mma_oracle import check_output_mma


def scalar_case(mode, terms, scale=127):
    a, b = [[0] * 64 for _ in range(16)], [[0] * 64 for _ in range(16)]
    for k, ac, bc in terms:
        for vector in range(16):
            a[vector][k], b[vector][k] = ac, bc
    bus = sum(scale << (8 * i) for i in range(32))
    return Case("MM-F16", mode, pack_rows(a, mode), pack_rows(b, mode), bus, bus, 0, 0, 0)


def check(case, raw):
    rows = [sum(raw << (64 * c) for c in range(16))] * 16
    return check_output_mma(list(case.a), list(case.b), case.a_scale,
                            case.b_scale, case.mode, rows)


class MmaOracleTests(unittest.TestCase):
    def test_all_modes_and_integer_exactness(self):
        for mode in range(10):
            case = scalar_case(mode, [(k, ONE[mode], ONE[mode]) for k in range(64)])
            result = check(case, 64 if mode < 2 else 0x42800000)
            self.assertEqual(result.errors, [], mode)
            self.assertEqual(result.checked_lanes, 256, mode)
            self.assertEqual(result.diagnostic_lanes, 0, mode)
            self.assertTrue(check(case, 0).errors, mode)

    def test_max_plus_one_is_finite_in_new_profile_only(self):
        case = scalar_case(3, [(i, x, 0x3f80) for i, x in
                              enumerate((0x7f7f, 0x7b7f, 0x777f, 0x3f80))])
        self.assertEqual(sum(dot_terms(list(case.a), list(case.b), 0, 0, 3, 0, 0)), MAX_F32 + 1)
        self.assertEqual(check(case, 0x7f7fffff).errors, [])
        self.assertEqual(check(case, 0x7f7fffff).diagnostic_lanes, 0)
        rows = [sum(0x7f7fffff << (64 * c) for c in range(16))] * 16
        self.assertTrue(check_output(list(case.a), list(case.b), 0, 0, 3, rows))

    def test_large_cancellation_does_not_require_exact_range_class(self):
        case = scalar_case(3, [(0, 0x7180, 0x7180), (4, 0x6000, 0x6000),
                              (8, 0xf180, 0x7180)])
        self.assertEqual(sum(dot_terms(list(case.a), list(case.b), 0, 0, 3, 0, 0)), pow2(130))
        self.assertEqual(check(case, 0).errors, [])
        self.assertEqual(check(case, 0).checked_lanes, 256)

    def test_nan_cannot_hide_an_ordinary_arithmetic_bug(self):
        case = scalar_case(3, [(0, 0x3f80, 0x3f80)])
        for raw in (0x7fc00000, 0x7f800000, 0xff800000, 0x7f800001):
            self.assertTrue(check(case, raw).errors)

    def test_explicit_nan_and_invalid_still_require_quiet_nan(self):
        for terms in [[(0, 0x7fc0, 0x3f80)], [(0, 0x7f80, 0)],
                      [(0, 0x7f80, 0x3f80), (1, 0xff80, 0x3f80)]]:
            case = scalar_case(3, terms)
            self.assertFalse(check(case, 0x7fc00000).errors)
            self.assertTrue(check(case, 0).errors)
            self.assertTrue(check(case, 0x7f800001).errors)

    def test_infinite_input_cannot_become_finite_or_opposite_infinity(self):
        case = scalar_case(3, [(0, 0x7f80, 0x3f80)])
        self.assertFalse(check(case, 0x7f800000).errors)
        for raw in (0, 0xff800000, 0x7fc00000):
            self.assertTrue(check(case, raw).errors)

    def test_overflow_diagnostics_are_not_numerical_passes(self):
        case = scalar_case(3, [(0, 0x7180, 0x7180)])
        result = check(case, 0x7f800000)
        self.assertFalse(result.errors)
        self.assertEqual(result.checked_lanes, 0)
        self.assertEqual(result.diagnostic_lanes, 256)
        self.assertTrue(check(case, 0xff800000).errors)
        self.assertTrue(check(case, 0x7fc00000).errors)
        self.assertTrue(check(case, 0).errors)

    def test_nonportable_mx_inputs_do_not_count_as_passes(self):
        case = scalar_case(7, [(0, 0x7e, 0x38)], scale=254)
        result = check(case, 0)
        self.assertEqual(result.checked_lanes, 0)
        self.assertEqual(result.diagnostic_lanes, 256)
        self.assertTrue(check(case, 1 << 32).errors)

    def test_subnormal_flushing_before_mx_scaling(self):
        case = scalar_case(9, [(0, 1, 2)], scale=128)
        self.assertFalse(check(case, 0).errors)
        self.assertFalse(check(case, 0x40000000).errors)  # 0.5*1*2*2
        self.assertTrue(check(case, 0x42c80000).errors)  # 100 is not a flush result

    def test_normal_precision_mutation_is_detected(self):
        # FP16 unit products added to one; rounding at FP16 precision loses
        # small increments by far more than the FP32 envelope permits.
        case = scalar_case(2, [(0, 0x3c00, 0x3c00)] + [(k, 0x2000, 0x2000) for k in range(1, 64)])
        self.assertTrue(check(case, 0x3f800000).errors)

    def test_fraction_reference_agrees_on_safe_random_dots(self):
        rng = random.Random(11)
        for _ in range(16):
            case = scalar_case(3, [(k, rng.randrange(0x3e00, 0x4100),
                                   rng.randrange(0x3e00, 0x4100)) for k in range(64)])
            exact = sum(dot_terms(list(case.a), list(case.b), 0, 0, 3, 0, 0))
            raw = struct.unpack("<I", struct.pack("<f", float(exact)))[0]
            self.assertFalse(check(case, raw).errors)
            actual = decode_f32(raw)
            self.assertLess(abs(actual - exact), abs(exact) * Fraction(1, 1 << 23))

    def test_normal_cases_cover_all_formats_without_subnormals_or_overflow(self):
        cases = precision_cases(11)
        self.assertEqual(len(cases), 256)
        self.assertEqual({x.mode for x in cases}, set(range(2, 10)))
        # Independently inspect source-format fields and exact products.
        for case in cases:
            terms = dot_terms(list(case.a), list(case.b), case.a_scale, case.b_scale, case.mode, 0, 0)
            self.assertTrue(all(isinstance(x, (int, Fraction)) for x in terms))
            self.assertLess(sum(map(abs, terms)), MAX_F32 / 4)

    def test_retained_range_probes_and_duplicate_rows(self):
        self.assertEqual(len(range_stress_cases()), 82)
        case = scalar_case(3, [(0, 0x3f80, 0x3f80)])
        row = sum(0x3f800000 << (64 * c) for c in range(16))
        log = "\n".join(f"MM_ROW 0 {r} {row:x}" for r in range(16))
        log += f"\nMM_ROW 0 0 {row:x}\nMM_CASE 0 1 1 1 16\n"
        log += "MM_STREAM input_bubble_phases=00000000000000 finished=1\n"
        result = evaluate(log, [case])
        self.assertEqual(result["cases_failed"], 1)
        self.assertFalse(result["numerical_and_interface_passed"])

    def test_arithmetic_probes_precede_backpressure_without_reentering_phase_zero(self):
        cases, phases = mma_cases(11)
        first_train = next(i for i, phase in enumerate(phases) if phase != 0)
        self.assertTrue(all(phase != 0 for phase in phases[first_train:]))
        self.assertEqual(phases[-1], 13)
        probes = [(case, phase) for case, phase in zip(cases, phases) if case.case_id and
                  (case.case_id.startswith("mma-normal") or case.case_id.startswith("opus-numeric-review"))]
        self.assertEqual(len(probes), 338)
        self.assertTrue(all(phase == 0 for case, phase in probes))


if __name__ == "__main__":
    unittest.main()
