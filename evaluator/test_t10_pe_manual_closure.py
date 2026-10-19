"""Portable controls for the v15 repair and V1.0 single-PE evidence contract."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from jsonschema import Draft202012Validator

from evaluator.t10_backend.physical.t10_manual_v15_compare_drc import check


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evaluator/fixtures/t10_v15_manual"


class ManualClosureTest(unittest.TestCase):
    def paths(self):
        return [str(FIXTURES / name) for name in (
            "historical.drc.rpt", "original_full.drc.rpt", "repaired_full.drc.rpt",
            "original_scoped.drc.rpt", "repaired_scoped.drc.rpt")]

    def test_drc_controls_and_byte_identical_native_reproduction(self):
        result = check(self.paths())
        self.assertEqual([result[k] for k in (
            "raw_before", "raw_after", "scoped_before", "scoped_after",
            "unchanged_context_only", "new_markers")], [663, 658, 5, 0, 658, 0])
        for a, b in (("original_full.drc.rpt", "original_scoped.drc.rpt.raw"),
                     ("repaired_full.drc.rpt", "repaired_scoped.drc.rpt.raw"),
                     ("historical.drc.rpt", "original_scoped.drc.rpt")):
            self.assertEqual((FIXTURES / a).read_bytes(), (FIXTURES / b).read_bytes())

    def test_blanket_filter_fails_negative_control(self):
        with tempfile.TemporaryDirectory() as directory:
            before = Path(directory) / "original.rpt"
            before.write_bytes(b"")  # Pretending the unmodified original is clean is invalid.
            before.with_suffix(".rpt.raw").write_bytes((FIXTURES / "original_full.drc.rpt").read_bytes())
            paths = self.paths()
            paths[3] = str(before)
            with self.assertRaisesRegex(ValueError, "negative control"):
                check(paths)

    def test_nonempty_repaired_report_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            after = Path(directory) / "repaired.rpt"
            after.write_bytes((FIXTURES / "historical.drc.rpt").read_bytes())
            after.with_suffix(".rpt.raw").write_bytes((FIXTURES / "repaired_full.drc.rpt").read_bytes())
            paths = self.paths()
            paths[4] = str(after)
            with self.assertRaisesRegex(ValueError, "real violation"):
                check(paths)

    def test_record_hashes_and_qualification_links(self):
        base = ROOT / "evaluator"
        record = json.loads((base / "t10_pe_manual_closure.json").read_text())
        for artifact in record["portable_artifacts"] + record["scripts"]:
            blob = (base / artifact["path"]).read_bytes()
            self.assertEqual(len(blob), artifact["bytes"], artifact["path"])
            self.assertEqual(hashlib.sha256(blob).hexdigest(), artifact["sha256"], artifact["path"])
        qualification = json.loads((base / "t10_qualification.json").read_text())
        for key in ("ppa_contract", "ppa_evidence_schema", "pe_reference_probe", "historical_pe_reference_probe"):
            blob = (base / qualification[key + "_path"]).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), qualification[key + "_sha256"])
        self.assertFalse(qualification["pe_reference_probe"]["official_ppa_baseline"])
        self.assertEqual(qualification["physical_levels"], ["pe"])
        self.assertEqual((FIXTURES / "electrical.rpt").read_text().count("(VIOLATED)"), 756)


class SinglePeSchemaTest(unittest.TestCase):
    def setUp(self):
        schema = json.loads((ROOT / "benchmark/tasks/T10/ppa-evidence.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)
        # Synthetic values only: these exercise the schema, not a real PPA baseline.
        sha = "a" * 64
        artifact = {"path": "synthetic", "bytes": 1, "sha256": sha}
        level = {"area_um2": 1, "setup_worst_slack_ps": 1, "hold_worst_slack_ps": 1,
                 "drc_violations": 0,
                 "artifacts": {name: dict(artifact) for name in schema["$defs"]["level"]["properties"]["artifacts"]["required"]}}
        power = {"workload_id": "T10-power-v1", "workload_sha256": sha, "matrix_blocks": 200,
                 "activity_annotation_fraction": 0.98, "vcd_window_seconds": 1,
                 "components_w": {"pe_shell": 1, "internal_macros": 1},
                 "instance_weights": {"pe": 1}, "total_power_w": 2, "energy_j_per_block": 0.01,
                 "artifacts": {name: dict(artifact) for name in ("workload_manifest", "activity_audit", "power_report")}}
        self.record = {
            "schema_version": 2, "task_id": "T10", "measurement_scope": "single_pe",
            "measurement_status": "three_seed_single_pe",
            "toolchain": {"yosys": "synthetic", "openroad": "synthetic", "orfs_revision": "synthetic",
                          "asap7_manifest_sha256": sha, "evaluator_sha256": sha},
            "workload": {"id": "T10-power-v1", "matrix_blocks": 200, "sha256": sha, "oracle_sha256": sha},
            "parameter_set": {"platform": "ASAP7_7p5t_RVT_NLDM", "corner": "WC", "period_ps": 1000,
                              "signal_routing_layers": "M2-M7", "clock_routing_layers": "M6-M7",
                              "utilization": 24, "density": 0.24, "seeds": [11, 29, 47]},
            "source": {"rtl_sha256": sha, "filelist_sha256": sha, "structure_report_sha256": sha,
                       "pe_rtl_sha256": sha, "pe_module": "synthetic_pe",
                       "hierarchy": {"tile_instances": 16, "pe_instances_per_tile": 16, "pe_instances_total": 256}},
            "per_seed": [{"layout_seed": seed, "levels": {"pe": copy.deepcopy(level)},
                          "area_um2": 1, "delay_ps": 999, "power": copy.deepcopy(power)} for seed in (11, 29, 47)],
            "aggregate": {"area_um2": 1, "delay_ns": 0.999, "energy_per_op_pj": 1e10, "annotation_fraction": 0.98}}

    def test_single_pe_without_tile_or_top_is_valid(self):
        self.validator.validate(self.record)

    def test_wrong_scope_incomplete_seeds_and_failed_gates_are_invalid(self):
        bad = []
        item = copy.deepcopy(self.record)
        item["measurement_scope"] = "full_dut"
        bad.append(item)
        item = copy.deepcopy(self.record)
        item["per_seed"].pop()
        bad.append(item)
        item = copy.deepcopy(self.record)
        item["per_seed"][0]["levels"]["pe"]["drc_violations"] = 1
        bad.append(item)
        item = copy.deepcopy(self.record)
        item["per_seed"][0]["levels"]["pe"]["hold_worst_slack_ps"] = -1
        bad.append(item)
        item = copy.deepcopy(self.record)
        item["per_seed"][0]["power"]["activity_annotation_fraction"] = 0.94
        bad.append(item)
        for item in bad:
            self.assertFalse(self.validator.is_valid(item))


if __name__ == "__main__":
    unittest.main()
