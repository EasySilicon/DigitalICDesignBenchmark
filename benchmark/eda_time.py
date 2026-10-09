#!/usr/bin/env python3
"""Host-side, sampled EDA wall-time accounting for isolated Docker trials.

No files or tools are injected into contestants. Durations are estimates from
Linux /proc sampling, NOT exact exec/exit tracing. Short-lived processes between
samples can be missed; reports explicitly retain the method and sample interval.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


EDA = {
    "yosys", "yosys-abc", "abc", "openroad", "opensta", "sta", "verilator",
    "verilator_bin", "verilator_bin_dbg", "iverilog", "ivl", "vvp", "vsim",
    "vlog", "vcom", "vcs", "simv", "xrun", "xmelab", "xmsim", "nvc",
    "ghdl", "sby", "boolector", "z3", "nextpnr", "nextpnr-ice40",
    "nextpnr-ecp5", "surelog", "slang", "sv2v", "gtkwave",
}
BUILD = {"make", "gmake", "cmake", "ninja", "gcc", "g++", "cc", "c++",
         "clang", "clang++", "cc1", "cc1plus", "collect2", "ld", "ld.lld", "as", "ar"}
SIM = re.compile(r"^(?:V[A-Za-z_][\w.-]*|simv|simulator|simulation|sim|tb(?:[_-].*)?)$")
COMPILER = re.compile(r"^(?:[\w.-]+-)?(?:gcc|g\+\+|clang(?:\+\+)?)(?:-\d+(?:\.\d+)*)?$")


def tool_name(argv: list[str], executable: str = "") -> str | None:
    """Match actual executable/interpreter script, never shell argument substrings."""
    if not argv:
        return None
    names = [Path(argv[0]).name, Path(executable).name]
    if names[0].startswith("ld-linux"):
        # OSS CAD executes its ELF loader explicitly. Parse loader options to
        # identify the real executable, not a random tool name in its arguments.
        position = 1
        takes_value = {"--library-path", "--inhibit-rpath", "--argv0",
                       "--glibc-hwcaps-prepend", "--glibc-hwcaps-mask"}
        no_value = {"--inhibit-cache", "--list", "--verify"}
        while position < len(argv):
            option = argv[position]
            if option in takes_value:
                position += 2
            elif option in no_value:
                position += 1
            elif option.startswith("--") and "=" in option:
                position += 1
            else:
                break
        if position < len(argv) and not argv[position].startswith("-"):
            names.append(Path(argv[position]).name)
    if re.fullmatch(r"(?:python\d*(?:\.\d+)*|perl|tclsh\d*|bash|sh)", names[0]):
        # Covers e.g. Perl's verilator wrapper, but not `bash -c 'yosys ...'`.
        if len(argv) > 1 and not argv[1].startswith("-"):
            names.append(Path(argv[1]).name)
    for name in names:
        if name in EDA or name in BUILD or COMPILER.fullmatch(name) or SIM.fullmatch(name):
            return name
    return None


@dataclass(frozen=True)
class Process:
    pid: int
    start_ticks: int
    tool: str


def decode_cmdline(raw: bytes) -> list[str]:
    if not raw:
        return []
    arguments = raw.split(b'\0')
    if arguments[-1] == b'':
        arguments.pop()  # Remove delimiter, not legitimate empty argv values.
    return [argument.decode(errors='replace') for argument in arguments]


def read_process(pid: int) -> Process | None:
    base = Path("/proc") / str(pid)
    try:
        fields = (base / "stat").read_text().rsplit(")", 1)[1].split()
        if fields[0] in {"Z", "X"}:
            return None
        argv = decode_cmdline((base / "cmdline").read_bytes())
        try:
            executable = os.readlink(base / "exe")
        except OSError:
            executable = ""
        name = tool_name(argv, executable)
        return Process(pid, int(fields[19]), name) if name else None
    except (OSError, IndexError, ValueError):
        return None


def cgroup_path(pid: int) -> Path:
    for row in (Path("/proc") / str(pid) / "cgroup").read_text().splitlines():
        if row.startswith("0::"):
            return Path("/sys/fs/cgroup") / row[3:].lstrip("/")
    raise RuntimeError("EDA monitor requires Linux cgroup v2")


def sample(group: Path) -> list[Process]:
    processes = []
    # Include any nested cgroups. cgroup.procs excludes threads, avoiding double counts.
    for file in group.rglob("cgroup.procs"):
        try:
            pids = file.read_text().split()
        except OSError:
            continue
        for pid in pids:
            proc = read_process(int(pid))
            if proc:
                processes.append(proc)
    return processes


class Accounting:
    def __init__(self, interval: float, started: float):
        self.interval = interval
        self.started = started
        self.last = started
        self.busy = False
        self.wall = 0.0
        self.active: dict[Process, float] = {}
        self.calls: list[dict] = []
        self.max_gap = 0.0

    def update(self, now: float, processes: list[Process], finishing: bool = False) -> list[dict]:
        # Trapezoidal integration of a boolean busy signal: overlapping and nested
        # processes count only once toward aggregate wall time.
        gap = now - self.last
        self.max_gap = max(self.max_gap, gap)
        present = set(processes)
        self.wall += gap * (int(self.busy) + int(bool(present))) / 2
        boundary = max(self.started, (now + self.last) / 2)
        events = []
        for proc in list(self.active):
            if proc not in present:
                began = self.active.pop(proc)
                record = {
                    "pid": proc.pid, "process_start_ticks": proc.start_ticks,
                    "tool": proc.tool, "start_offset_seconds": began - self.started,
                    "end_offset_seconds": boundary - self.started,
                    "elapsed_seconds": max(0.0, boundary - began),
                    "right_censored": finishing,
                }
                self.calls.append(record)
                events.append(record)
        for proc in present - self.active.keys():
            self.active[proc] = boundary
        self.last, self.busy = now, bool(present)
        return events

    def report(self) -> dict:
        return {
            "schema_version": 1, "method": "host_proc_sampling",
            "sampling_interval_seconds": self.interval,
            "max_observed_sample_gap_seconds": self.max_gap,
            "observed_seconds": self.last - self.started,
            "eda_wall_seconds_estimate": self.wall,
            "observed_call_count": len(self.calls) + len(self.active),
            "active_calls": [{"pid": p.pid, "tool": p.tool} for p in self.active],
            "process_seconds_sum_estimate": sum(c["elapsed_seconds"] for c in self.calls)
                + sum(self.last - began for began in self.active.values()),
            "limitations": [
                "Processes shorter than the polling interval may be missed.",
                "Timing starts at monitor attachment; prior activity is not reconstructed.",
                "Unrecognized custom simulator names require --extra-tool.",
                "Build tools in the candidate container are included regardless of purpose.",
                "Observed call count describes processes, not Agent Bash/tool requests.",
            ],
        }


def discover(prefixes: list[str]) -> dict[str, int]:
    result = subprocess.run(["docker", "ps", "--format", "{{.Names}}"],
                            check=True, text=True, capture_output=True)
    names = [n for n in result.stdout.splitlines() if any(n.startswith(p) for p in prefixes)]
    if not names:
        return {}
    details = subprocess.run(["docker", "inspect", "--format", "{{.Name}} {{.State.Pid}}", *names],
                             text=True, capture_output=True, check=True)
    return {name.lstrip("/"): int(pid) for name, pid in
            (line.split() for line in details.stdout.splitlines())}


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container-prefix", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--interval", type=float, default=0.1)
    parser.add_argument("--idle-stop-seconds", type=float, default=3600)
    parser.add_argument("--extra-tool", action="append", default=[])
    args = parser.parse_args()
    if args.interval <= 0 or args.idle_stop_seconds <= 0:
        parser.error("interval and idle-stop-seconds must be positive")
    EDA.update(args.extra_tool)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stop = False

    def request_stop(*_):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    # Key by name + container-init PID, so a restart cannot merge observations.
    sessions = {}
    active = set()
    last_discovery = 0.0
    last_write = 0.0
    last_active = time.monotonic()
    while not stop:
        now = time.monotonic()
        if now - last_discovery >= 2:
            try:
                running = discover(args.container_prefix)
                active = set()
                for name, pid in running.items():
                    key = (name, pid)
                    active.add(key)
                    if key not in sessions:
                        group = cgroup_path(pid)
                        output = args.output_dir / f"{name}_{pid}"
                        output.mkdir()
                        sessions[key] = {
                            "group": group, "output": output,
                            "accounting": Accounting(args.interval, now),
                            "attached_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                        print(f"Monitoring {name} -> {output}", flush=True)
                last_discovery = now
            except (subprocess.SubprocessError, OSError, ValueError) as error:
                print(f"Discovery failed; retrying: {error}", flush=True)
        if active:
            last_active = now
        for key, session in sessions.items():
            accounting = session["accounting"]
            if session.get("finished"):
                continue
            is_active = key in active and session["group"].is_dir()
            events = accounting.update(time.monotonic(), sample(session["group"]) if is_active else [],
                                       finishing=not is_active)
            if events:
                with (session["output"] / "calls.jsonl").open("a") as log:
                    for event in events:
                        log.write(json.dumps(event) + "\n")
            session["finished"] = not is_active
            if now - last_write >= 5 or not is_active:
                write_report(session["output"] / "eda_time.json", {
                    **accounting.report(), "container": key[0], "container_init_pid": key[1],
                    "attached_utc": session["attached_utc"], "finished": not is_active,
                })
        if now - last_write >= 5:
            last_write = now
        if now - last_active > args.idle_stop_seconds:
            break
        time.sleep(args.interval)
    for key, session in sessions.items():
        if not session.get("finished"):
            accounting = session["accounting"]
            events = accounting.update(time.monotonic(), [], finishing=True)
            with (session["output"] / "calls.jsonl").open("a") as log:
                for event in events:
                    log.write(json.dumps(event) + "\n")
            write_report(session["output"] / "eda_time.json", {
                **accounting.report(), "container": key[0], "container_init_pid": key[1],
                "attached_utc": session["attached_utc"], "finished": True,
                "monitor_stopped": True,
            })


if __name__ == "__main__":
    main()
