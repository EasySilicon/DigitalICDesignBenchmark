# 随仓库提供的 ASAP7 平台

T11 新物理流程另外使用 `lambdapdk_fakeram7/` 中固定版本的双时钟
FakeRAM 研究模型；它不是上述原样 ASAP7 副本的一部分，不修改原平台
SHA256SUMS。上游 commit、原始三视图、最小仿真修订及哈希保存在
`lambdapdk_fakeram7/manifest.json`，授权文本为其中 `LICENSE.apache`。
宏不提供晶体管 GDS，PPA 使用明确标注的混合角与宏外布线 DRC 范围；
详见 `benchmark/tasks/T11/AUTHOR_GUIDE.md`。不是硅验证或流片签核库。

[English](README.en.md)

`asap7/` 是从 [OpenROAD Flow Scripts](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts) 修订 `1ec57da7bf0f1491190cbea2673c2c01fb3bc3ae` 的 `flow/platforms/asap7/` **原样复制**的完整平台目录，约 222 MB、208 个原始文件。包含 7.5T 标准单元的 Liberty、LEF、GDS、门级 Verilog 模型、布线/寄生规则与 ORFS 配置，供本 benchmark 的 Yosys + ASAP7 + OpenROAD 流程直接使用。复制日期：2026-09-25。正式评分仍需冻结全部工具和参数。

`asap7/SHA256SUMS` 为复制后的 208 个原始文件提供逐文件校验；在仓库根目录运行：

```bash
cd vendor/asap7
sha256sum -c SHA256SUMS
```

ORFS 可通过 `PLATFORM_DIR=/absolute/path/to/this/repo/vendor/asap7` 直接引用本目录，无需再次下载 ASAP7。许可证按组件就近保留：ASAP7 PDK/标准单元按 [ASAP7 BSD 3-Clause 许可](LICENSES/ASAP7-BSD-3-Clause.txt)再分发，ORFS 平台脚本按 [ORFS BSD 3-Clause 许可](LICENSES/ORFS-BSD-3-Clause.txt)再分发，FakeRAM2.0 生成的宏按 [FakeRAM2.0 BSD 3-Clause 许可](LICENSES/FakeRAM2.0-BSD-3-Clause.txt)再分发；drc/asap7.lydrc 的 BSD-2-Clause 许可保留在文件头。完整的路径、上游和版权映射见仓库根目录的 [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md)。
