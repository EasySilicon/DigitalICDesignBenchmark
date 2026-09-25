"""T10 gate workload must verify matrix values as well as completion markers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ppa_power_probe import check_t10_workload


class T10PowerWorkloadTest(unittest.TestCase):
    def test_complete_zero_workload_and_corrupt_lane(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            count = 10
            for name, width, lines in (("a", 256, count * 16),
                                       ("b", 256, count * 16),
                                       ("as", 64, count),
                                       ("bs", 64, count),
                                       ("reset", 1, count)):
                (root / f"{name}.mem").write_text(("0" * width + "\n") * lines)
            (root / "mode.mem").write_text("".join(f"{mode:x}\n" for mode in range(10)))
            entries = []
            for case in range(count):
                entries.extend(f"MM_ROW {case} {row} {'0' * 256}" for row in range(16))
                entries.append(f"MM_CASE {case} 1 1 1 16")
            log = "\n".join(entries) + f"\nMM_END cases={count}\n"
            check_t10_workload(log, root, count)
            corrupted = log.replace(f"MM_ROW 0 0 {'0' * 256}", "MM_ROW 0 0 1", 1)
            with self.assertRaisesRegex(RuntimeError, "numerical mismatch"):
                check_t10_workload(corrupted, root, count)
            duplicated = log.replace("MM_CASE 0 1 1 1 16\n", "MM_CASE 0 1 1 1 16\n" * 2, 1)
            with self.assertRaisesRegex(RuntimeError, "duplicated case marker"):
                check_t10_workload(duplicated, root, count)


if __name__ == "__main__":
    unittest.main()
