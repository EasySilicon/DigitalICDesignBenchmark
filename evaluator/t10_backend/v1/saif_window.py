"""Locally correct delayed-open residency and initial-value TC in pinned SAIF.

Only the native writer is rebuilt. The mapped model, its objects and the
installed Verilator remain untouched. Keep the original executable as a
negative control. Reject any different writer revision rather than applying
text replacements to an unreviewed implementation.
"""
import hashlib
from pathlib import Path
import re

POLICY = "delayed_open_real_time_no_initial_value_toggle_v1"
NATIVE_SHA256 = "8d2827886d59ef9080a908d19b948268476c65c2a8a0ef05f8af5f03375b3b58"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def corrected(source):
    if hashlib.sha256(source.encode()).hexdigest() != NATIVE_SHA256:
        raise ValueError("unreviewed native SAIF writer revision")
    replacements = [
        ("    bool m_lastVal = false;  // Last emitted activity bit value",
         "    bool m_initialized = false;  // First sample is a value, not an edge\n"
         "    bool m_lastVal = false;  // Last emitted activity bit value"),
        ("    void aggregateVal(uint64_t dt, bool newVal) {\n",
         "    void aggregateVal(uint64_t dt, bool newVal) {\n"
         "        if (!m_initialized) {\n"
         "            m_initialized = true;\n"
         "            m_lastVal = newVal;\n"
         "            return;\n"
         "        }\n"),
        ("    m_startTime = currentTime();\n",
         "    m_time = Verilated::threadContextp()->time();\n"
         "    m_startTime = currentTime();\n"),
    ]
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("ambiguous SAIF writer patch")
        source = source.replace(before, after)
    return source


def build(out, top, run, cwd):
    directory = out / "build"
    makefile = directory / f"V{top}.mk"
    match = re.search(r"^VERILATOR_ROOT = (.+)$", makefile.read_text(), re.M)
    if not match:
        raise ValueError("generated makefile lacks VERILATOR_ROOT")
    original = Path(match[1]) / "include/verilated_saif_c.cpp"
    local = out / "saif_window"
    local.mkdir(exist_ok=True)
    source = local / "t10_saif_window.cpp"
    source.write_text(corrected(original.read_text()))
    override = local / "runtime.mk"
    executable = directory / f"V{top}_windowed"
    # A separate runtime object and executable preserve the original build.
    override.write_text(
        f"t10_saif_window.o: {source}\n"
        "\t$(OBJCACHE) $(CXX) $(OPT_GLOBAL) $(CXXFLAGS) $(CPPFLAGS) -c -o $@ $<\n"
        f"{executable.name}: $(filter-out verilated_saif_c.o,$(VK_GLOBAL_OBJS)) t10_saif_window.o $(VM_PREFIX)__ALL.a\n"
        "\t$(LINK) $(LDFLAGS) $^ $(LOADLIBES) $(LDLIBS) $(LIBS) $(SC_LIBS) -o $@\n")
    run(["make", "-C", str(directory), "-f", makefile.name, "-f", str(override),
         "-j4", executable.name], local / "build.log", cwd)
    return executable, dict(policy=POLICY, native_source=str(original),
                            native_sha256=sha(original), corrected_sha256=sha(source),
                            adapter_sha256=sha(Path(__file__)), executable_sha256=sha(executable))
