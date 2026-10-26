"""Keep existing T10 graph elaboration and retry unsupported SV through slang."""
import re
import shlex
from pathlib import Path
if __package__:
    from . import t10_structure_check as frozen
    from .slang_frontend import yosys_command
else:
    import t10_structure_check as frozen
    from slang_frontend import yosys_command


_READ_VERILOG = re.compile(
    r"read_verilog -sv (?P<sources>.*?)(?=; hierarchy -top )")
_MODULE = re.compile(r"^\s*module\s+(?:automatic\s+)?([A-Za-z_][A-Za-z0-9_$]*)\b",
                     re.MULTILINE)


def _staged_slang_reads(script: str) -> str | None:
    """Keep source-level PE identities when Slang can load one module per file.

    Slang's monolithic ``--keep-hierarchy`` elaboration specializes a generated
    leaf once for every hierarchical path.  That is correct elaboration, but
    it hides the fact that 256 generated instances came from one PE module.
    Loading a leaf file before its parent makes the already-loaded leaf an
    external module during parent elaboration, preserving its common identity
    for the structural checker.  Restrict this path to the unambiguous,
    conventional one-module-per-file layout; all other layouts retain the
    conservative monolithic fallback below.
    """
    match = _READ_VERILOG.search(script)
    if match is None:
        return None
    try:
        sources = [Path(source) for source in shlex.split(match.group("sources"))]
        modules = []
        for source in sources:
            names = _MODULE.findall(source.read_text())
            if len(names) != 1:
                return None
            modules.append((names[0], source))
    except (OSError, ValueError):
        return None
    if len({name for name, _ in modules}) != len(modules):
        return None
    reads = []
    for index, (name, source) in enumerate(modules):
        keep = "--keep-hierarchy " if index else ""
        reads.append("read_slang " + keep + "--top " + name +
                     " --compat=vcs -D SYNTHESIS --ignore-assertions " +
                     shlex.quote(str(source)))
    return "; ".join(reads) + script[match.end():]


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
            staged = _staged_slang_reads(args[index])
            if staged is not None:
                args[index] = staged
            else:
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
