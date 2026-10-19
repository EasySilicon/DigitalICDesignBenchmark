"""Verify raw/scoped full-chip DRC against the historical five-marker control."""
import collections
import hashlib
import json
from pathlib import Path
import re
import sys


def require(condition, message):
    if not condition:
        raise ValueError(message)


def records(path):
    result = []
    for part in re.split(r"(?=^violation type:)", Path(path).read_text(), flags=re.M):
        if part.strip():
            lines = tuple(line.strip() for line in part.splitlines() if line.strip())
            require(len(lines) == 3 and lines[0].startswith("violation type:"), f"malformed record: {lines}")
            result.append(lines)
    return collections.Counter(result)


def check(paths):
    historical, before, after, before_scoped, after_scoped = paths
    h, b, a, bs, ass = map(records, paths)
    native_b, native_a = records(before_scoped+".raw"), records(after_scoped+".raw")
    require(sum(h.values()) == 5, "historical control must contain five markers")
    require(b-a == h and not a-b, "raw reports differ by more than the five original markers")
    require(native_b == b and native_a == a, "native unfiltered reproduction does not match stock checker")
    require(bs == h, "scoped checker fails the original five-marker negative control")
    require(not ass, "scoped checker still reports a real violation")
    require(b-bs == a-ass, "context-only marker sets changed")
    artifacts = []
    for path in paths + [before_scoped+".raw",after_scoped+".raw"]:
        blob = Path(path).read_bytes()
        artifacts.append(dict(path=path, bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest(),
                              marker_count=sum(records(path).values())))
    return dict(status="passed",historical_markers=5,raw_before=sum(b.values()),raw_after=sum(a.values()),
                scoped_before=sum(bs.values()),scoped_after=sum(ass.values()),
                unchanged_context_only=sum((b-bs).values()),new_markers=0,artifacts=artifacts)


if __name__ == "__main__":
    require(len(sys.argv) == 6, "expected historical, raw-before, raw-after, scoped-before, scoped-after reports")
    print(json.dumps(check(sys.argv[1:]),sort_keys=True))
