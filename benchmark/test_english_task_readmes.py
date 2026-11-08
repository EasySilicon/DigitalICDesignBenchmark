"""Keep consolidated English task descriptions aligned with acceptance IDs."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "tasks"


class EnglishTaskReadmesTest(unittest.TestCase):
    def test_acceptance_groups_and_common_delivery_are_present(self):
        pattern = re.compile(r"AC-\d+[AB]?|CPU-[A-Z]+(?:-[A-Z]+)?|MM-[A-Z0-9]+")
        for number in range(1, 11):
            task = f"T{number:02d}"
            with self.subTest(task=task):
                directory = ROOT / task
                readme = (directory / "README.en.md").read_text()
                acceptance = (directory / "acceptance.md").read_text()
                self.assertFalse(re.search(r"[\u4e00-\u9fff]", readme))
                self.assertEqual(set(pattern.findall(acceptance)) - set(pattern.findall(readme)), set())
                self.assertIn("## Delivery and evaluation", readme)
                self.assertIn("without a token budget", readme)
                self.assertIn("120 minutes for T10", readme)
                self.assertIn("20 minutes for T01–T09 and 40 minutes for T10", readme)

    def test_task_index_combines_english_then_chinese(self):
        index = (ROOT / "README.md").read_text()
        self.assertLess(index.index("## English"), index.index("## 中文"))
        self.assertFalse((ROOT / "README.en.md").exists())

    def test_t08_retains_complete_english_specification_and_acceptance(self):
        directory = ROOT / "T08"
        readme = (directory / "README.en.md").read_text()
        readme = readme.replace("See the acceptance plan below for the functional-group point allocation.",
                                "See acceptance.md for the functional-group point allocation.")
        readme = readme.replace("dual-clock model specified in section 1.5 above.",
                                "dual-clock model specified in task.md section 1.5.")
        for filename in ("task.md", "acceptance.md"):
            self.assertIn((directory / filename).read_text().strip(), readme)

    def test_cpu_and_systolic_timing_and_scoring_contracts_are_explicit(self):
        cpu = (ROOT / "T09/README.en.md").read_text()
        for term in ("n+4", "22/22", "11–21", "0–10", "response_cycles+ready_delay"):
            self.assertIn(term, cpu)
        systolic = (ROOT / "T10/README.en.md").read_text()
        for term in ("7,200-second", "2,400-second", "306,304", "MM-SYSTOLIC", "γ(128)",
                     "public/matmul_oracle.py", "ST-MIX", "512", "ST-BP/RST", "128-block",
                     "32-cycle", "0,126,127,128,254,255", "exponent − bias − mantissa_bits",
                     "compilation timeout for **any** seed", "D_eff", "D_setup", "t/14400"):
            self.assertIn(term, systolic)


if __name__ == "__main__":
    unittest.main()
