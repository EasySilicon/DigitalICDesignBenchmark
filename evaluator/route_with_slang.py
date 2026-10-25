#!/usr/bin/env python3
"""Current physical entry: required slang support, frozen routing constraints."""
import shutil
import sys

if __package__:
    from . import ppa_probe as frozen
    from .slang_frontend import executable
else:
    import ppa_probe as frozen
    from slang_frontend import executable


def main():
    yosys = str(executable())
    original_config, original_which = frozen.write_config, shutil.which

    def write_config(path, *args, **kwargs):
        original_config(path, *args, **kwargs)
        # The SRAM path reads an already generated Verilog netlist rather than
        # the candidate SystemVerilog; retain its explicit Verilog reader.
        if not kwargs.get('t11_sram'):
            path.write_text(path.read_text() + 'export SYNTH_HDL_FRONTEND = slang\n')

    def which(name, *args, **kwargs):
        return yosys if name == 'yosys' else original_which(name, *args, **kwargs)

    try:
        frozen.write_config, shutil.which = write_config, which
        return frozen.main()
    finally:
        frozen.write_config, shutil.which = original_config, original_which


if __name__ == '__main__':
    raise SystemExit(main())
