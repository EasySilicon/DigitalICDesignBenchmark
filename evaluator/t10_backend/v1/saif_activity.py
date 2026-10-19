"""Import averaged SAIF through exact physical-net-to-pin mapping.

Pinned OpenSTA SaifLex accepts neither '/' in a NET identifier nor a quoted
NET identifier. Its reader also resolves NET records as pins. Physical flat
net names need not be pin names. Use the same user-pin activity API with the
actual connected pins, preserving zero TC and duty exactly, not propagation.
"""
from pathlib import Path
import re

from merge_pe_saif import STAT

POLICY = "exact_physical_net_connected_pin_activity_v1"
TCL = Path(__file__).with_name("import_saif_activity.tcl")


def export_scope(source, scope, output):
    scopes, stack, records = [], [], {}
    duration = scale = None
    for line in source.read_text().splitlines():
        line = line.strip()
        if line.startswith("(DURATION "):
            duration = int(line[10:-1])
        elif line.startswith("(TIMESCALE "):
            match = re.fullmatch(r"\(TIMESCALE (\d+)\s*(ps|ns|us|fs)\)", line)
            if not match:
                raise ValueError("unsupported SAIF timescale")
            scale = int(match[1])*dict(ps=1e-12,ns=1e-9,us=1e-6,fs=1e-15)[match[2]]
        elif line.startswith("(INSTANCE "):
            scopes.append(line[10:].replace("\\", ""))
            stack.append("INSTANCE")
        elif line in ("(NET", "(SAIFILE"):
            stack.append(line[1:])
        elif line == ")":
            if stack.pop() == "INSTANCE":
                scopes.pop()
        elif scopes == scope and line.startswith("("):
            match = STAT.fullmatch(line)
            if not match or not duration or not scale:
                raise ValueError("invalid averaged SAIF record")
            name, t0, t1, tz, tx, tb, tc = match.groups()
            name = name.replace("\\", "")
            if name in records or any(c in name for c in "{}\n\r"):
                raise ValueError("ambiguous or unsupported physical net name")
            if int(t0)+int(t1) != duration or any(int(v) for v in (tz,tx,tb)):
                raise ValueError("invalid residency in averaged SAIF")
            records[name] = (int(tc)/(duration*scale), int(t1)/duration)
    if stack or not records:
        raise ValueError("missing/incomplete SAIF scope")
    with output.open("w") as stream:
        for name,(density,duty) in sorted(records.items()):
            # Tcl list data, not Tcl source. Braces preserve slash, brackets,
            # dollar signs and spaces; unsupported braces are rejected above.
            stream.write(f"{{{name}}} {density:.17g} {duty:.17g}\n")
    return dict(policy=POLICY, scope=scope, activity_nets=len(records))
