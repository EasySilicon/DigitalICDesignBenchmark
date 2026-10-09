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

    def test_sail_trap_event_matches_dut_trap_port(self):
        lines = [
            "[0] [M]: 0x8000000C (0xFFFFFFFF) illegal 0xffffffff",
            "trapping from M to M to handle illegal-instruction",
            "handling exc#illegal-instruction at priv M | tval=0xFFFFFFFF",
            "CSR mcause (0x342) <- 0x00000002",
            "CSR mtval (0x343) <- 0xFFFFFFFF",
        ]
        with self.assertRaises(ValueError):
            parse_trace(lines)
        expected = parse_trace(lines, include_traps=True)
        self.assertTrue(compare_commits(expected, [
            {"kind": "trap", "cycle": 10, "pc": 0x8000000C,
             "cause": 2, "tval": 0xFFFFFFFF}])["passed"])

    def test_older_commit_and_younger_trap_may_share_cycle(self):
        expected = [
            {"pc": 0x80000000, "insn": 0x00100093, "rd": 1,
             "wdata": 1, "mem_wstrb": 0},
            {"kind": "trap", "pc": 0x80000004, "cause": 2,
             "tval": 0xFFFFFFFF},
        ]
        observed = [
            {"kind": "commit", "cycle": 13, "pc": 0x80000000,
             "insn": 0x00100093, "rd": 1, "wdata": 1,
             "mem_wstrb": 0},
            {"kind": "trap", "cycle": 13, "pc": 0x80000004,
             "cause": 2, "tval": 0xFFFFFFFF},
        ]
        self.assertTrue(compare_commits(expected, observed)["passed"])

        commit = {"kind": "commit", "cycle": 13, "pc": 0x80000000,
                  "insn": 0x00100093, "rd": 1, "wdata": 1,
                  "mem_wstrb": 0}
        trap = {"kind": "trap", "cycle": 13, "pc": 0x80000004,
                "cause": 2, "tval": 0xFFFFFFFF}
        for first, second in ((commit, commit), (trap, commit), (trap, trap)):
            invalid = [first, second]
            invalid_expected = [dict(first), dict(second)]
            for item in invalid_expected:
                item.pop("cycle")
            result = compare_commits(invalid_expected, invalid)
            self.assertFalse(result["passed"])
            self.assertEqual(result["matched"], 1)


if __name__ == "__main__":
    unittest.main()
