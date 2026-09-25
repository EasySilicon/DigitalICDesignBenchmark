"""Regression for the public T10 format decoder and streaming matrix packing."""

import unittest
from fractions import Fraction

from matmul_oracle import (NAN, NEG_INF, POS_INF, check_output, decode_element,
                           dot_terms, element_at, expected_dot, pow2)


class MatmulOracleTests(unittest.TestCase):
    def test_all_ten_modes_with_full_1024_bit_beats(self):
        codes = {0: 1, 1: 1, 2: 0x3C00, 3: 0x3F80,
                 4: 0x38, 5: 0x3C, 6: 0x2,
                 7: 0x38, 8: 0x3C, 9: 0x2}
        scale = sum(127 << (8 * i) for i in range(32))
        for mode, code in codes.items():
            width = 16 if mode in (1, 2, 3) else 4 if mode in (6, 9) else 8
            lanes = 64 // width
            beat = sum(code << (i * width) for i in range(16 * lanes))
            beats = [beat] * width
            lane = 64 if mode in (0, 1) else 0x42800000
            rows = [sum(lane << (64 * c) for c in range(16)) for _ in range(16)]
            with self.subTest(mode=mode):
                self.assertEqual(check_output(beats, beats, scale, scale, mode, rows), [])

    def test_format_boundaries(self):
        self.assertEqual(decode_element(0x7E, 4), Fraction(448))
        self.assertEqual(decode_element(0x7F, 4), NAN)
        self.assertEqual(decode_element(0x7C, 5), POS_INF)
        self.assertEqual(decode_element(0x01, 4), pow2(-9))
        self.assertEqual(decode_element(0x01, 6), Fraction(1, 2))
        self.assertEqual(decode_element(0x07, 6), Fraction(6))
        self.assertEqual(decode_element(0xBC00, 2), Fraction(-1))
        self.assertEqual(decode_element(0x3F80, 3), Fraction(1))
        self.assertEqual(decode_element(0xFFFF, 1), -1)

    def test_last_bit_and_mx_block_boundary(self):
        # Last nibble of A row 15 and B column 15 is the top nibble of beat 3.
        beats = [0, 0, 0, 2 << 1020]
        a_scale = 128 << (8 * 31)  # A row 15, block 1: x2
        b_scale = 126 << (8 * 31)  # B col 15, block 1: x1/2
        terms = dot_terms(beats, beats, a_scale, b_scale, 9, 15, 15)
        self.assertEqual(sum(terms), Fraction(1))
        self.assertEqual(element_at(beats, 15, 31, 9, a_scale), 0)
        self.assertEqual(element_at(beats, 15, 63, 9, a_scale), 2)
        self.assertEqual(element_at(beats, 15, 63, 9, 255 << (8 * 31)), NAN)
        rows = [0] * 16
        rows[15] = 0x3F800000 << (64 * 15)
        self.assertEqual(check_output(beats, beats, a_scale, b_scale, 9, rows), [])
        self.assertTrue(check_output(beats, beats, a_scale, b_scale, 9, [0] * 16))

    def test_integer_exact_and_nan(self):
        a = [0] * 8
        b = [0] * 8
        a[7] = 0x80 << (8 * 7)  # A row 0, k 63 = -128
        b[7] = 0x7F << (8 * 7)  # B col 0, k 63 = 127
        rows = [0] * 16
        rows[0] = (1 << 64) - 16256
        self.assertEqual(check_output(a, b, 0, 0, 0, rows), [])
        self.assertTrue(check_output(a, b, 0, 0, 0, [0] * 16))
        self.assertEqual(expected_dot([NAN])[0], NAN)
        self.assertEqual(expected_dot([POS_INF, NEG_INF])[0], NAN)


if __name__ == "__main__":
    unittest.main()
