"""Host-side consistency checks; never copied into a contestant package."""
from __future__ import annotations

import hashlib
import json
import re
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK = ROOT / "benchmark/tasks/T08"
SPEC = (TASK / "task.md").read_text()


def crc_bits(body: bytes) -> int:
    state = 0xFFFFFFFF
    for octet in body:
        for bit in range(8):
            feedback = (state & 1) ^ ((octet >> bit) & 1)
            state >>= 1
            if feedback:
                state ^= 0xEDB88320
    return state ^ 0xFFFFFFFF


def number(pattern: str, text: str, base: int = 10) -> int:
    match = re.search(pattern, text)
    if not match:
        raise AssertionError(f"Missing specification field: {pattern}")
    return int(match[1], base)


class T08SpecTest(unittest.TestCase):
    def test_long_form_is_substantive_and_ids_are_unique(self):
        lines = SPEC.splitlines()
        self.assertGreaterEqual(len(lines), 3000)
        self.assertGreaterEqual(sum(bool(line.strip()) for line in lines), 3000)
        ids = re.findall(r"(?:Port|Scenario|Evidence) ID: (T08-[A-Z]+-\d+)\.", SPEC)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 39 + 81 + 22 + 32)
        self.assertIn("no token hard limit", SPEC)
        self.assertIn("3.0-frame-transactions", SPEC)
        self.assertIn("## Appendix G. Frame-transaction stress obligations", SPEC)

    def test_all_port_names_and_widths_match_frozen_top(self):
        source = (TASK / "starter/rtl/mac_1g_repair.sv").read_text()
        source = re.sub(r"//[^\n]*", "", source)
        header = source.split("module mac_1g_repair (", 1)[1].split(");", 1)[0]
        rtl_ports = {}
        direction, width = None, None
        for declaration in header.split(","):
            declaration = declaration.strip()
            explicit = re.fullmatch(r"(input|output) wire(?:\s+\[(\d+):0\])?\s+(\w+)", declaration)
            if explicit:
                direction = explicit[1]
                width = int(explicit[2]) + 1 if explicit[2] else 1
                name = explicit[3]
            else:
                self.assertRegex(declaration, r"^\w+$")
                name = declaration
            rtl_ports[name] = (direction, width)
        sections = re.findall(r"### A\.\d+\. (\w+)\n(.*?)(?=\n### A\.|\n## Appendix B)", SPEC, re.S)
        spec_ports = {}
        for name, text in sections:
            direction = re.search(r"Direction: (input|output)\.", text)[1]
            width = number(r"Width: (\d+) bits?\.", text)
            spec_ports[name] = (direction, width)
        self.assertEqual(spec_ports, rtl_ports)
        self.assertEqual(len(rtl_ports), 39)
        event = dict(sections)["rx_vlan_drop"]
        self.assertIn("Owning domain: RX.", event)
        for name in ("rx_fifo_overflow", "rx_fifo_bad_frame", "rx_fifo_good_frame"):
            self.assertIn("Owning domain: system.", dict(sections)[name])

    def test_crc_vectors_match_two_independent_oracles(self):
        vectors = re.findall(r"#### B\.7\.\d+\. (\S+)\n(.*?)(?=\n#### B\.7\.|\nA checker)", SPEC, re.S)
        self.assertEqual(len(vectors), 12)
        for name, text in vectors:
            with self.subTest(vector=name):
                length = number(r"Submitted octets: (\d+)\.", text)
                padding = number(r"Padding octets: (\d+)\.", text)
                covered = number(r"CRC-covered octets: (\d+)\.", text)
                body = b"123456789" if name.startswith("ASCII") else bytes((17*i+3) & 255 for i in range(length))
                body += bytes(padding)
                self.assertEqual(len(body), covered)
                expected = number(r"Numeric CRC/FCS: 0x([0-9A-F]+)\.", text, 16)
                self.assertEqual(expected, crc_bits(body))
                self.assertEqual(expected, zlib.crc32(body))
                fcs = bytes.fromhex(re.search(r"Serialized FCS: ([0-9A-F ]+)\.", text)[1])
                self.assertEqual(fcs, expected.to_bytes(4, "little"))

    def test_rx_scenario_decisions_metadata_and_checksums(self):
        cards = re.findall(r"### C\.R\d+\. ([^\n]+)\n(.*?)(?=\n### C\.R|\n### C\.2)", SPEC, re.S)
        self.assertEqual(len(cards), 81)
        for name, text in cards:
            with self.subTest(scenario=name):
                length = number(r"Body length: (\d+) octets\.", text)
                outer = number(r"Outer field: 0x([0-9A-F]+)", text, 16)
                tci = number(r"TCI: 0x([0-9A-F]+)", text, 16)
                inner = number(r"inner field: 0x([0-9A-F]+)", text, 16)
                enable, untagged, priority = map(int, re.search(r"Snapshot enable/untagged/priority: (\d)/(\d)/(\d)\.", text).groups())
                mask = number(r"Snapshot valid mask: 0b([01]+)", text, 2)
                slots = list(map(int, re.search(r"Snapshot slots \[0,1,2,3\]: \[([^]]+)\]", text)[1].split(",")))
                if not enable:
                    policy = "BYPASS"
                elif length < 14:
                    policy = "DENY_SHORT_HEADER"
                elif outer == 0x88A8:
                    policy = "DENY_S_TAG"
                elif outer != 0x8100:
                    policy = "ADMIT_UNTAGGED" if untagged else "DENY_UNTAGGED"
                elif length < 18:
                    policy = "DENY_SHORT_C_TAG"
                elif inner in (0x8100, 0x88A8):
                    policy = "DENY_NESTED"
                elif (tci & 4095) == 4095:
                    policy = "DENY_RESERVED"
                elif (tci & 4095) == 0:
                    policy = "ADMIT_PRIORITY" if priority else "DENY_PRIORITY"
                else:
                    matched = any(mask & (1 << i) and slot == (tci & 4095) for i, slot in enumerate(slots))
                    policy = "ADMIT_LIST" if matched else "DENY_LIST"
                self.assertIn(f"Policy result before MAC precedence: {policy}.", text)
                integrity = re.search(r"Raw integrity stimulus: (\w+)\.", text)[1]
                denied = policy.startswith("DENY")
                delivered = int(integrity == "good" and not denied)
                drops = int(integrity == "good" and denied)
                self.assertEqual(number(r"Delivered complete frames: (\d+)", text), delivered)
                self.assertEqual(number(r"delivered body bytes: (\d+)", text), delivered * length)
                self.assertEqual(number(r"VLAN-drop samples for this frame: (\d+)", text), drops)
                if delivered:
                    tagged = int(enable and outer == 0x8100)
                    self.assertIn(f"tagged={tagged}, TCI=0x{tci if tagged else 0:04X}", text)
                body = bytearray((17*i+3) & 255 for i in range(length))
                writes = [(12, outer >> 8), (13, outer & 255)]
                if outer == 0x8100:
                    writes += [(14, tci >> 8), (15, tci & 255), (16, inner >> 8), (17, inner & 255)]
                if name == "address-looks-like-tag":
                    writes += [(0, 0x81), (1, 0)]
                if name == "payload-looks-like-tag":
                    writes += [(64, 0x81), (65, 0), (66, 0x88), (67, 0xA8)]
                for index, value in writes:
                    if index < length:
                        body[index] = value
                expected_crc = number(r"Independent correct-body CRC: 0x([0-9A-F]+)", text, 16)
                self.assertEqual(expected_crc, zlib.crc32(body))
                self.assertEqual(expected_crc, crc_bits(body))
                fcs = bytes.fromhex(re.search(r"FCS octets: ([0-9A-F ]+)\.", text)[1])
                self.assertEqual(fcs, expected_crc.to_bytes(4, "little"))

    def test_starter_checksums_and_budget_metadata(self):
        for line in (TASK / "starter.sha256").read_text().splitlines():
            checksum, relative = line.split()
            self.assertEqual(hashlib.sha256((TASK / relative).read_bytes()).hexdigest(), checksum)
        metadata = (TASK / "task.yaml").read_text()
        self.assertIn("spec_revision: 3.0-frame-transactions", metadata)
        self.assertIn("starter_revision: 3.0-coalesced-commit-regression", metadata)
        self.assertIn("time_limit_minutes: 120", metadata)
        self.assertIn("same_model_token_cap: null", metadata)
        self.assertIn("ppa_policy_revision: 2.0-lambdapdk-tdp-1ghz", metadata)
        self.assertIn("ppa_timing_corners: mixed_WC_standard_cells_TT_SRAM", metadata)
        self.assertIn("ppa_memory_model: lambdapdk_fakeram7_tdp_4096x32", metadata)
        self.assertIn("ppa_clock_relationship: asynchronous", metadata)
        for clock in ("logic_clk", "tx_clk", "rx_clk"):
            self.assertIn(f"  {clock}: 1000", metadata)
        self.assertIn("PPA target: 1 GHz (1,000 ps)", SPEC)
        self.assertIn("Functional acceptance still uses 125 MHz TX/RX and 80–160 MHz logic_clk", SPEC)
        from evaluator.t08_check import JUDGE_REVISION
        self.assertIn(f"judge_revision: {JUDGE_REVISION}", metadata)

    def test_judge_case_inventory_and_unchanged_point_total(self):
        from evaluator.t08_check import GROUPS
        self.assertEqual(sum(points for _, points, _ in GROUPS), 50)
        cases = [case for _, _, group_cases in GROUPS for case in group_cases]
        self.assertEqual(sorted(cases), list(range(37)))
        self.assertEqual(len(cases), len(set(cases)))

    def test_sram_policy_is_visible_and_consistent_without_new_functional_ticket(self):
        policy = "2.0-lambdapdk-tdp-1ghz"
        for name in ("task.md", "task.yaml", "acceptance.md", "README.md"):
            text = (TASK / name).read_text()
            self.assertIn(policy, text, name)
            self.assertNotIn("1.0-uniform-1ghz", text, name)
        section = SPEC.split("### 1.5 FIFO memory implementation and physical evaluation", 1)[1].split("## 2.", 1)[0]
        for obligation in ("generic synthesizable FIFO memory arrays", "4,096-entry capacity",
                           "two independent positive-edge clocks", "read is synchronous",
                           "stall retention externally", "WC", "TT 0.7 V/25 C",
                           "not an additional feature ticket", "Historical trial inputs"):
            self.assertIn(obligation, section)
        self.assertIn("Specification revision: 3.0-frame-transactions", SPEC)
        self.assertIn("Feature ticket: implement single-C-tag RX admission", SPEC)

    def test_frame_repair_evidence_is_for_the_current_starter_and_judge(self):
        evidence = json.loads((ROOT / "evaluator/fixtures/t11_mac/repair_mutation_qualification_v31.json").read_text())
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["baseline_run_count"], 111)
        self.assertEqual(evidence["variant_count"], 5)
        self.assertEqual(evidence["detected_count"], 5)
        self.assertTrue(evidence["coalescing_positive_control"]["passed"])
        self.assertEqual(evidence["starter_fifo_sha256"],
                         hashlib.sha256((TASK / "starter/rtl/axis_async_fifo.v").read_bytes()).hexdigest())
        for relative, checksum in evidence["judge_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), checksum)

    def test_feature_evidence_is_for_current_boundary_judge(self):
        from evaluator.t08_check import JUDGE_REVISION
        evidence = json.loads((ROOT / "evaluator/fixtures/t11_mac/feature_mutation_qualification_v31.json").read_text())
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["judge_revision"], JUDGE_REVISION)
        self.assertEqual(evidence["baseline_run_count"], 111)
        self.assertEqual(evidence["variant_count"], 18)
        self.assertEqual(evidence["detected_count"], 18)
        for relative, checksum in evidence["judge_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), checksum)

    def test_boundary_evidence_catches_real_regression_without_false_positives(self):
        evidence = json.loads((ROOT / "evaluator/fixtures/t11_mac/boundary_regression_qualification_v31.json").read_text())
        self.assertTrue(evidence["passed"])
        self.assertTrue(evidence["original_trial_and_summary_unchanged"])
        replays = evidence["replays"]
        for name in ("streaming_control", "independent_kimi_replay"):
            self.assertTrue(replays[name]["full_functional_pass"])
            self.assertEqual(replays[name]["run_count"], 111)
        bad = replays["known_glm_regression"]
        self.assertFalse(bad["full_functional_pass"])
        self.assertEqual(bad["functional_total"], 44)
        self.assertEqual([case["case"] for case in bad["failed_cases"]], [28,30,31,33,35,36])
        for case in bad["failed_cases"]:
            self.assertEqual(case["failed_seeds"], [20261007,47,91])
        for relative, checksum in evidence["judge_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), checksum)


if __name__ == "__main__":
    unittest.main()
