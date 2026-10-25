"""Current single-PE physical path with the required slang frontend."""
import shutil

if __package__:
    from .slang_frontend import executable
else:
    from slang_frontend import executable


def physical(*args, **kwargs):
    import run_t10_candidate_40g as backend
    import t10_candidate_physical as frozen
    yosys = str(executable())
    original_seed, original_write, original_which = backend.run_seed, frozen.write_new_or_same, shutil.which

    def write(path, text):
        if path.name == 'config.mk':
            text += 'export SYNTH_HDL_FRONTEND = slang\n'
        return original_write(path, text)

    def which(name, *a, **kw):
        return yosys if name == 'yosys' else original_which(name, *a, **kw)

    try:
        frozen.write_new_or_same, shutil.which = write, which
        return backend.physical(*args, **kwargs)
    finally:
        backend.run_seed = original_seed
        frozen.write_new_or_same, shutil.which = original_write, original_which
