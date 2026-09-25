import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sail_commit import compare_commits, parse_trace, store_port


class SailCommitTests(unittest.TestCase):
    def test_byte_lane_and_comparison(self):
        lines = [
            "[0] [M]: 0x80000000 (0x05500093) addi x1, x0, 0x55",
            "x1 <- 0x00000055",
            "[1] [M]: 0x80000004 (0x001101A3) sb x1, 0x3(x2)",
            "mem[W,0x080000103] <- 0x55",
        ]
        expected = parse_trace(lines)
        self.assertEqual(expected[1]["mem_addr"], 0x80000100)
        self.assertEqual(expected[1]["mem_wstrb"], 8)
        self.assertEqual(expected[1]["mem_wdata"], 0x55000000)
        observed = [
            {"kind": "commit", "cycle": 4, "pc": 0x80000000,
             "insn": 0x05500093, "rd": 1, "wdata": 0x55, "mem_wstrb": 0},
            {"kind": "commit", "cycle": 5, "pc": 0x80000004,
             "insn": 0x001101A3, "rd": 0, "mem_wstrb": 8,
             "mem_addr": 0x80000100, "mem_wdata": 0x55000000},
        ]
        self.assertTrue(compare_commits(expected, observed)["passed"])
        observed[1]["mem_wdata"] ^= 1
        self.assertTrue(compare_commits(expected, observed)["passed"])
        observed[1]["mem_wdata"] ^= 0x01000000
        self.assertEqual(compare_commits(expected, observed)["matched"], 1)

    def test_store_width_and_trap_rejection(self):
        self.assertEqual(store_port(0x00111023, 0x80000102, 0xABCD),
                         (0x80000100, 0xC, 0xABCD0000))
        with self.assertRaises(ValueError):
            store_port(0x00111023, 0x80000103, 0xABCD)
        self.assertFalse(compare_commits(
            [{"pc": 0, "insn": 0, "rd": 0, "mem_wstrb": 0}],
            [{"kind": "trap", "cycle": 1, "pc": 0, "cause": 2}])["passed"])


if __name__ == "__main__":
    unittest.main()
