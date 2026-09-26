# Vendored ASAP7 platform

[中文](README.md)

`asap7/` is a byte-for-byte copy of `flow/platforms/asap7/` from [OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) revision `1ec57da7bf0f1491190cbea2673c2c01fb3bc3ae`. It contains the 7.5T standard-cell Liberty, LEF, GDS, gate-level Verilog, routing/extraction rules, and ORFS configuration used by the benchmark's Yosys + ASAP7 + OpenROAD flow.

`asap7/SHA256SUMS` records a hash for each vendored source file. From the repository root:

```bash
cd vendor/asap7
sha256sum -c SHA256SUMS
```

Set `PLATFORM_DIR=/absolute/path/to/repo/vendor/asap7` to use it with ORFS. Licenses stay adjacent to their components: ASAP7, ORFS, and FakeRAM2.0 use their respective BSD-3-Clause notices in `LICENSES/`; `drc/asap7.lydrc` retains its BSD-2-Clause header. See [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) for the complete provenance and license mapping.
