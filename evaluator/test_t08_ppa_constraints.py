"""T08 physical diagnostic clock/IO assignments must not hide real IO paths."""
import re
import tempfile
import unittest
from pathlib import Path

from ppa_probe import T08_IO_DOMAINS, constraint_text, write_config


class T08ConstraintsTest(unittest.TestCase):
    def test_every_top_io_belongs_to_exactly_one_domain(self):
        # Independent frozen top-level port contract, not inferred from mapping.
        inputs = set("tx_axis_tdata tx_axis_tvalid tx_axis_tlast tx_axis_tuser "
                     "rx_axis_tready gmii_rxd gmii_rx_dv gmii_rx_er cfg_vlan_enable "
                     "cfg_accept_untagged cfg_accept_priority cfg_vlan_valid cfg_vlan_vids".split())
        outputs = set("tx_axis_tready rx_axis_tdata rx_axis_tvalid rx_axis_tlast "
                      "rx_axis_tuser rx_axis_tagged rx_axis_tci gmii_txd gmii_tx_en "
                      "gmii_tx_er rx_vlan_drop tx_error_underflow rx_error_bad_frame "
                      "rx_error_bad_fcs tx_fifo_overflow tx_fifo_bad_frame "
                      "tx_fifo_good_frame rx_fifo_overflow rx_fifo_bad_frame "
                      "rx_fifo_good_frame".split())
        for index, expected in enumerate((inputs, outputs)):
            assigned = [port for domain in T08_IO_DOMAINS.values()
                        for port in domain[index].split()]
            self.assertEqual(set(assigned), expected)
            self.assertEqual(len(assigned), len(expected))

    def test_clocks_async_but_io_is_timed_to_owning_clock(self):
        text = constraint_text("mac_1g_repair", tuple(T08_IO_DOMAINS), 1000, 0.2)
        self.assertEqual(len(re.findall(r"^create_clock", text, re.M)), 3)
        self.assertNotIn("vclk", text)
        self.assertIn("set_clock_groups -asynchronous", text)
        self.assertIn("set_output_delay 200 -clock rx_clk_clock [get_ports {rx_vlan_drop}]", text)
        for reset in ("logic_rst", "tx_rst", "rx_rst"):
            self.assertIn(f"set_false_path -from [get_ports {reset}]", text)
        self.assertNotIn("rst_n", text)

    def test_nonuniform_profile_is_rejected_instead_of_misreported(self):
        with self.assertRaises(ValueError):
            constraint_text("mac_1g_repair", tuple(T08_IO_DOMAINS), 1000, 0.2,
                            {"rx_clk": 8000})

    def test_existing_two_clock_task_is_unchanged(self):
        text = constraint_text("asynchronous_fifo", ("wr_clk", "rd_clk"),
                               1000, 0.2, {"rd_clk": 2000})
        self.assertIn("-period 2000 [get_ports rd_clk]", text)
        self.assertIn("set_input_delay 200 -clock vclk", text)
        self.assertNotIn("logic_rst", text)

    def test_full_memory_synthesis_is_t08_only_and_never_mocked(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.mk"
            for top in ("mac_1g_repair", "asynchronous_fifo"):
                write_config(config, top, [], Path("constraint.sdc"), "", 10, 0.6, "WC")
                text = config.read_text()
                if top == "mac_1g_repair":
                    self.assertIn("export SYNTH_MEMORY_MAX_BITS = 262144", text)
                    self.assertIn("export SYNTH_MOCK_LARGE_MEMORIES = 0", text)
                    self.assertNotIn("SYNTH_MOCK_LARGE_MEMORIES = 1", text)
                else:
                    self.assertNotIn("SYNTH_MEMORY_MAX_BITS", text)
                    self.assertNotIn("SYNTH_MOCK_LARGE_MEMORIES", text)


if __name__ == "__main__":
    unittest.main()
