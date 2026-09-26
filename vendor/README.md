# 随仓库提供的 ASAP7 平台

`asap7/` 是从 [OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) 修订 `1ec57da7bf0f1491190cbea2673c2c01fb3bc3ae` 的 `flow/platforms/asap7/` **原样复制**的完整平台目录，约 222 MB、208 个原始文件。包含 7.5T 标准单元的 Liberty、LEF、GDS、门级 Verilog 模型、布线/寄生规则与 ORFS 配置，供本 benchmark 的 Yosys + ASAP7 + OpenROAD 流程直接使用。复制日期：2026-09-25。正式评分仍需冻结全部工具和参数。

`asap7/SHA256SUMS` 为复制后的 208 个原始文件提供逐文件校验；在仓库根目录运行：

```bash
cd vendor/asap7
sha256sum -c SHA256SUMS
```

ORFS 可通过 `PLATFORM_DIR=/absolute/path/to/this/repo/vendor/asap7` 直接引用本目录，无需再次下载 ASAP7。许可证按组件就近保留：ASAP7 PDK/标准单元按 [ASAP7 BSD 3-Clause 许可](LICENSES/ASAP7-BSD-3-Clause.txt)再分发，ORFS 平台脚本按 [ORFS BSD 3-Clause 许可](LICENSES/ORFS-BSD-3-Clause.txt)再分发，FakeRAM2.0 生成的宏按 [FakeRAM2.0 BSD 3-Clause 许可](LICENSES/FakeRAM2.0-BSD-3-Clause.txt)再分发；drc/asap7.lydrc 的 BSD-2-Clause 许可保留在文件头。完整的路径、上游和版权映射见仓库根目录的 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
