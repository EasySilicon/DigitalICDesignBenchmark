"""SRAM policy, physical accounting, and provenance regression tests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ppa_probe import write_config, report_fields
from t11_sram import contract, validated_mapping, CELL, MACRO_SIM, sha256


class SramPolicyTest(unittest.TestCase):
    def test_pinned_views_have_independent_clocks_and_explicit_scope(self):
        policy = contract()
        self.assertEqual(policy["cell"], CELL)
        self.assertEqual(policy["capacity_bits_per_macro"], 131072)
        self.assertFalse(policy["corner_policy"]["full_chip_worst_corner_signoff"])
        model = MACRO_SIM.read_text()
        self.assertIn("always @(posedge clk_A)", model)
        self.assertIn("always @(posedge clk_B)", model)
        self.assertEqual(model.count("integer j;"), 1)
        self.assertEqual(model.count("integer k;"), 1)
        self.assertNotIn("ce_in_B,\n);", model)

    def test_macro_config_is_opt_in_and_does_not_modify_other_tasks(self):
        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "config.mk"
            write_config(path, "mac_1g_repair", [], Path("clock.sdc"), "", 10, .6, "WC", t11_sram=True)
            text = path.read_text()
            self.assertIn("ADDITIONAL_LEFS", text)
            self.assertIn("ADDITIONAL_LIBS", text)
            self.assertIn("SYNTH_MOCK_LARGE_MEMORIES = 0", text)
            write_config(path, "asynchronous_fifo", [], Path("clock.sdc"), "", 10, .6, "WC")
            self.assertNotIn("ADDITIONAL_LIBS", path.read_text())

    def test_missing_or_changed_mapping_qualification_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            submitted, mapped = root / "source", root / "mapped"
            for directory in (submitted, mapped):
                (directory / "rtl").mkdir(parents=True)
            source = submitted / "rtl/top.v"
            source.write_text("module mac_1g_repair; endmodule\n")
            (submitted / "rtl/files.f").write_text("top.v\n")
            (mapped / "rtl/mapped.v").write_bytes(source.read_bytes())
            (mapped / "rtl/macro.v").write_bytes(MACRO_SIM.read_bytes())
            (mapped / "rtl/files.f").write_text("mapped.v\nmacro.v\n")
            receipt = {"policy": contract(), "source_sha256": {"rtl/top.v": sha256(source)},
                       "mapped_netlist_sha256": sha256(mapped / "rtl/mapped.v")}
            (mapped / "mapping.json").write_text(json.dumps(receipt))
            with self.assertRaises(FileNotFoundError):
                validated_mapping(submitted, mapped)
            qualified = {"mapped_netlist_sha256": receipt["mapped_netlist_sha256"],
                         "contract_sha256": contract()["contract_sha256"],
                         "functional_passes": 111, "stress_passes": 270}
            (mapped / "evidence").mkdir()
            functional = {"full_functional_pass": True,
                          "cases": {str(n): {"runs": [{"passed": True}] * 3} for n in range(37)}}
            stress = {"full_pass": True, "run_count": 270, "passed_count": 270}
            for key, report in (("mapped_functional.json", functional), ("mapped_stress.json", stress)):
                (mapped / "evidence" / key).write_text(json.dumps(report))
            qualified["evidence_sha256"] = {"evidence/" + key: sha256(mapped / "evidence" / key)
                                            for key in ("mapped_functional.json", "mapped_stress.json")}
            (mapped / "qualification.json").write_text(json.dumps(qualified))
            self.assertEqual(validated_mapping(submitted, mapped), receipt)
            (mapped / "evidence/mapped_stress.json").write_text('{}')
            with self.assertRaises(ValueError):
                validated_mapping(submitted, mapped)
            (mapped / "evidence/mapped_stress.json").write_text(json.dumps(stress))
            source.write_text("module mac_1g_repair; wire changed; endmodule\n")
            with self.assertRaises(ValueError):
                validated_mapping(submitted, mapped)


if __name__ == "__main__":
    unittest.main()
