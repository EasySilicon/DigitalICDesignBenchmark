"""Locate the required Yosys SystemVerilog frontend, builtin or plugin."""
from functools import lru_cache
from pathlib import Path
import os
import shutil
import subprocess


@lru_cache(maxsize=None)
def yosys_command():
    executable = shutil.which('yosys')
    if executable is None:
        raise RuntimeError('Required Yosys executable is missing')
    for extra in ((), ('-m', 'slang')):
        result = subprocess.run([executable, *extra, '-Q', '-T', '-p', 'help read_slang'],
                                text=True, capture_output=True, check=False)
        if result.returncode == 0 and 'Read SystemVerilog sources' in result.stdout:
            return (executable, *extra)
    raise RuntimeError('Required Yosys read_slang frontend is unavailable; install or enable slang')


def executable():
    yosys_command()
    return Path(__file__).with_name('yosys_slang.py')


def main():
    import sys
    command = [*yosys_command(), *sys.argv[1:]]
    os.execvp(command[0], command)
