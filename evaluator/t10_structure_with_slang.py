"""Keep existing T10 graph elaboration and retry unsupported SV through slang."""
if __package__:
    from . import t10_structure_check as frozen
    from .slang_frontend import yosys_command
else:
    import t10_structure_check as frozen
    from slang_frontend import yosys_command


def inspect(submission):
    command = yosys_command()
    original = frozen.subprocess.run
    used_slang = False

    def run(args, *values, **options):
        nonlocal used_slang
        if args and args[0] == 'yosys' and '-p' in args:
            first = original(args, *values, **options)
            if first.returncode == 0:
                return first
            used_slang = True
            args = list(args)
            index = args.index('-p') + 1
            args[index] = args[index].replace('read_verilog -sv ',
                'read_slang --keep-hierarchy --top ' + frozen.TOP +
                ' --compat=vcs -D SYNTHESIS --ignore-assertions ', 1)
            args = [*command, *args[1:]]
        return original(args, *values, **options)

    try:
        frozen.subprocess.run = run
        result = frozen.inspect(submission)
        result['hdl_frontend'] = 'slang' if used_slang else 'builtin'
        result['slang_available'] = True
        return result
    finally:
        frozen.subprocess.run = original
