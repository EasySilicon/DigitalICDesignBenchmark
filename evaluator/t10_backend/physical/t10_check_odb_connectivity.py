"""Compare two OpenDB databases while deliberately ignoring physical geometry.

The gate binds both inputs by SHA-256 and compares the complete logical view of
the top block: instance masters, every instance terminal connection, top-level
terminal attributes/connections, and net attributes.  Wire shapes, placement,
rows, tracks, obstructions, and pin geometry are intentionally outside scope.
"""

import argparse
import gc
import hashlib
import json
from pathlib import Path

import odb


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def enum_text(value):
    return str(value) if value is not None else None


def net_name(terminal):
    net = terminal.getNet()
    return net.getName() if net is not None else None


def digest_records(records):
    digest = hashlib.sha256()
    for record in sorted(records):
        digest.update(json.dumps(record, ensure_ascii=True,
                                 separators=(",", ":")).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def logical_view(path):
    database = odb.dbDatabase.create()
    odb.read_db(database, str(path))
    chip = database.getChip()
    if chip is None or chip.getBlock() is None:
        raise RuntimeError(f"{path}: missing chip/block")
    block = chip.getBlock()

    instances = []
    instance_terminals = []
    for inst in block.getInsts():
        instances.append((inst.getName(), inst.getMaster().getName()))
        for term in inst.getITerms():
            mterm = term.getMTerm()
            instance_terminals.append((
                inst.getName(),
                mterm.getName(),
                enum_text(mterm.getIoType()),
                enum_text(mterm.getSigType()),
                net_name(term),
            ))

    block_terminals = []
    for term in block.getBTerms():
        block_terminals.append((
            term.getName(),
            enum_text(term.getIoType()),
            enum_text(term.getSigType()),
            net_name(term),
        ))

    nets = []
    for net in block.getNets():
        special = net.isSpecial() if hasattr(net, "isSpecial") else None
        wild_connected = (net.isWildConnected()
                          if hasattr(net, "isWildConnected") else None)
        nets.append((
            net.getName(),
            enum_text(net.getSigType()),
            special,
            wild_connected,
        ))

    categories = {
        "instances": instances,
        "instance_terminals": instance_terminals,
        "block_terminals": block_terminals,
        "nets": nets,
    }
    result = {
        "block_name": block.getName(),
        "counts": {name: len(records) for name, records in categories.items()},
        "category_sha256": {
            name: digest_records(records) for name, records in categories.items()
        },
    }
    result["logical_sha256"] = digest_records([
        ("block_name", result["block_name"]),
        *[(name, result["counts"][name], result["category_sha256"][name])
          for name in sorted(categories)],
    ])
    del categories, instances, instance_terminals, block_terminals, nets
    del block, chip, database
    gc.collect()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline_odb", type=Path)
    parser.add_argument("candidate_odb", type=Path)
    parser.add_argument("output_json", type=Path)
    parser.add_argument("--expected-baseline-sha256", required=True)
    parser.add_argument("--expected-candidate-sha256", required=True)
    args = parser.parse_args()

    baseline_file_sha = sha256(args.baseline_odb)
    candidate_file_sha = sha256(args.candidate_odb)
    errors = []
    if baseline_file_sha != args.expected_baseline_sha256:
        errors.append("baseline ODB SHA-256 mismatch")
    if candidate_file_sha != args.expected_candidate_sha256:
        errors.append("candidate ODB SHA-256 mismatch")

    baseline = logical_view(args.baseline_odb)
    candidate = logical_view(args.candidate_odb)
    if baseline["block_name"] != candidate["block_name"]:
        errors.append("block name differs")
    for category in sorted(baseline["category_sha256"]):
        if baseline["counts"][category] != candidate["counts"][category]:
            errors.append(f"{category} count differs")
        if (baseline["category_sha256"][category]
                != candidate["category_sha256"][category]):
            errors.append(f"{category} connectivity digest differs")
    if baseline["logical_sha256"] != candidate["logical_sha256"]:
        errors.append("complete logical digest differs")

    report = {
        "status": "PASS" if not errors else "FAIL",
        "scope": {
            "compared": [
                "block name",
                "instance name and master",
                "instance terminal name, direction, signal type, and net",
                "block terminal name, direction, signal type, and net",
                "net name, signal type, special flag, and wild-connect flag",
            ],
            "excluded": [
                "wire and via geometry",
                "placement and orientation",
                "rows, tracks, obstructions, and terminal geometry",
            ],
        },
        "baseline": {
            "path": str(args.baseline_odb.resolve()),
            "file_sha256": baseline_file_sha,
            **baseline,
        },
        "candidate": {
            "path": str(args.candidate_odb.resolve()),
            "file_sha256": candidate_file_sha,
            **candidate,
        },
        "errors": errors,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2) + "\n",
                                encoding="utf-8")
    if errors:
        raise SystemExit("FAIL: " + "; ".join(errors))
    print("PASS: ODB logical connectivity and object attributes are identical")


if __name__ == "__main__":
    main()
