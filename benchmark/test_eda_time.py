from __future__ import annotations

import shutil
import subprocess
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from benchmark.eda_time import Accounting, Process, decode_cmdline, read_process, tool_name


class EdaTimeTest(unittest.TestCase):
    def test_proc_cmdline_preserves_empty_loader_option_values(self):
        loader = '/opt/oss/lib/ld-linux-x86-64.so.2'
        argv = [loader, '--inhibit-cache', '--inhibit-rpath', '',
                '--library-path', '/opt/oss/lib', '/opt/oss/libexec/yosys', '-p', 'stat']
        raw = b'\0'.join(value.encode() for value in argv) + b'\0'
        self.assertEqual(decode_cmdline(raw), argv)
        self.assertEqual(decode_cmdline(b''), [])
        self.assertEqual(decode_cmdline(b'yosys\0\0'), ['yosys', ''])
        stat = '123 (loader) ' + ' '.join(['S'] + ['0']*18 + ['1234'])
        with patch.object(Path, 'read_text', return_value=stat), \
             patch.object(Path, 'read_bytes', return_value=raw), \
             patch('benchmark.eda_time.os.readlink', return_value=loader):
            self.assertEqual(read_process(123), Process(123, 1234, 'yosys'))

    def test_oss_cad_explicit_elf_loader(self):
        loader = "/opt/oss/lib/ld-linux-x86-64.so.2"
        argv = [loader, "--inhibit-cache", "--inhibit-rpath", "",
                "--library-path", "/opt/oss/lib", "/opt/oss/libexec/yosys",
                "-p", "stat"]
        self.assertEqual(tool_name(argv, loader), "yosys")
        self.assertIsNone(tool_name([loader, "--library-path", "/opt/yosys",
                                    "/usr/bin/python3", "yosys.log"], loader))
    def test_tools_builds_and_simulators(self):
        for argv in (["yosys", "-p", "stat"], ["g++", "-c", "model.cpp"],
                     ["/workspace/obj_dir/Vtb_cpu"], ["perl", "/opt/bin/verilator"],
                     ["/usr/bin/x86_64-linux-gnu-g++-13"], ["vvp", "test.vvp"]):
            with self.subTest(argv=argv):
                self.assertIsNotNone(tool_name(argv))

    def test_reading_a_script_or_shell_text_is_not_running_eda(self):
        for argv in (["cat", "yosys.log"], ["bash", "-c", "yosys -p stat"],
                     ["python3", "verif/check_results.py"], ["node", "claude.js"]):
            with self.subTest(argv=argv):
                self.assertIsNone(tool_name(argv))

    def test_overlap_counts_wall_time_once(self):
        parent, child = Process(1, 10, "make"), Process(2, 20, "g++")
        account = Accounting(1, 0)
        account.update(1, [parent])
        account.update(2, [parent, child])
        ended = account.update(3, [])
        self.assertEqual(account.report()["eda_wall_seconds_estimate"], 2)
        self.assertEqual(account.report()["process_seconds_sum_estimate"], 3)
        self.assertEqual(len(ended), 2)
        self.assertEqual(account.report()["observed_call_count"], 2)

    def test_reused_pid_and_exec_name_are_separate(self):
        account = Accounting(1, 0)
        account.update(1, [Process(1, 10, "g++")])
        account.update(2, [Process(1, 10, "collect2")])
        account.update(3, [Process(1, 99, "g++")])
        account.update(4, [], finishing=True)
        self.assertEqual(account.report()["observed_call_count"], 3)
        self.assertTrue(account.calls[-1]["right_censored"])

    def test_first_sample_and_empty_record(self):
        account = Accounting(.1, 5)
        account.update(5, [Process(1, 10, "vvp")])
        account.update(6, [], finishing=True)
        self.assertGreaterEqual(account.calls[0]["start_offset_seconds"], 0)
        empty = Accounting(.1, 0)
        empty.update(1, [])
        self.assertEqual(empty.report()["eda_wall_seconds_estimate"], 0)

    @unittest.skipUnless(shutil.which("sleep"), "Linux sleep needed")
    def test_actual_proc_read(self):
        # Exercise Linux stat parsing and NUL-separated argv without invoking EDA.
        process = subprocess.Popen(["verilator_bin", "10"], executable=shutil.which("sleep"))
        self.addCleanup(lambda: process.poll() is None and process.kill())
        try:
            # Popen can return before the child execs sleep: don't sample the
            # transient forked Python process as if it were the final executable.
            deadline = time.monotonic() + 1
            record = None
            while record is None and time.monotonic() < deadline:
                record = read_process(process.pid)
                if record is None:
                    time.sleep(0.005)
            self.assertIsNotNone(record)
            self.assertEqual(record.tool, "verilator_bin")
            self.assertGreater(record.start_ticks, 0)
        finally:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    unittest.main()
