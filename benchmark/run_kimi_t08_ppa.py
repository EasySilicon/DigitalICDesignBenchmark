#!/usr/bin/env python3
"""Run the isolated one-hour continuation, then host-only independent scoring."""
import argparse
import subprocess
import sys
from pathlib import Path

from benchmark.run_t08_comparison import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--orfs', type=Path, required=True)
    parser.add_argument('--publish-repo', type=Path, required=True)
    args = parser.parse_args()
    run(args.root)
    scorer = args.root.parent / 'frozen_scoring/evaluator/grade_t08_candidate_ppa.py'
    command = ['systemd-run', '--user', '--scope', '--quiet', '-p', 'MemoryHigh=20G',
               '-p', 'MemoryMax=24G', '-p', 'MemorySwapMax=0', '-p', 'CPUQuota=400%',
               '-p', 'TasksMax=512', sys.executable, str(scorer), '--root', str(args.root),
               '--orfs', str(args.orfs), '--publish-repo', str(args.publish_repo)]
    subprocess.run(command, check=True)


if __name__ == '__main__':
    main()
