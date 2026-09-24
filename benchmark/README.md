# 数字芯片设计交付 Benchmark v0.1

本目录是一套**待实现完整评测器的设计规范**，用于比较多 Agent 交付系统与通用 coding agent 的完整 RTL 交付质量。它包含 9 个任务，覆盖组合逻辑、时序控制、片上总线、CDC、缓存和五级流水线 CPU。每题要求 Agent 自行完成 RTL、可运行验证环境和 PPA 优化迭代。`v0.1` 写定了题面、资源边界、验收分配和评分方法；T01–T06 已有独立端口公开冒烟；ASAP7 PPA 参数、九题参考实现和封闭测试仍须按[发布门禁](methodology.md#发布门禁)制作并校准，不能把本文档误报为已经可正式评分的 benchmark。

| ID | 难度假设 | 任务 | 来源 | 开发时限 |
| --- | ---: | --- | --- | ---: |
| T01 | 1 | 8×3 优先编码器 | CVDP easy | 30 分钟 |
| T02 | 2 | 8 位串入并出移位寄存器 | CVDP easy | 75 分钟 |
| T03 | 3 | 参数化同步 FIFO | 原创 | 2 小时 |
| T04 | 4 | APB4 定时器外设 | 原创 | 3 小时 |
| T05 | 5 | ready/valid 轮询仲裁器 | 原创 | 4 小时 |
| T06 | 6 | 异步 FIFO | 原创 | 6 小时 |
| T07 | 7 | AXI4-Lite 到 APB4 桥 | 原创 | 8 小时 |
| T08 | 8 | 直接映射写回数据缓存 | 原创 | 12 小时 |
| T09 | 9 | RV32I 五级流水线 CPU | 原创 | 24 小时 |

难度序号是设计时的覆盖假设，不是 CVDP 官方难度，也不是已测得的等距难度。发布前应依照[校准流程](methodology.md#难度校准)用试运行数据调整或替换题目。两道 CVDP 题应单独报告，避免公开题的训练数据污染影响原创题结论。

## 规范入口

- [任务卡](tasks.md)：每题的设计需求、接口、合法环境、硬件资源边界、验收点及分值。
- [T01–T08 验收器设计](acceptance.md)：测试组 ID、参考模型与可检出的典型缺陷。
- [独立端口公开冒烟](../evaluator/README.md)：T01–T06 可执行测试与提交接口样例。
- [验证与交付契约](verification-contract.md)：参赛 Agent 的自带 UT、固定 DUT 接口、独立验收与 CPU ELF 入口。
- [评测与评分方法](methodology.md)：运行资源、可比性、通用门禁、分数计算、校准和发布条件。
- [PPA 测量方法](ppa.md)：统一工艺、约束、工作负载、功耗估计和排序规则。
- [领域与难度覆盖](coverage.md)：逐题设计领域、工程能力、难度来源和未覆盖范围。
- [CPU 验收计划](cpu-validation.md)：ACT4 接入、流水线专项程序、差分测试和通过条件。
- [来源锁定](sources.lock.yaml)：CVDP 的修订、数据文件及题面哈希。
- [机器可读清单](manifest.yaml)：题目 ID、时限、模型 token 上限及分值，供评测器读取。
- [运行报告 schema](report.schema.json)：统一记录功能、PPA、完成时间和交付诊断。
- [安装与依赖清单](../env/README.md)：分阶段安装、版本锁定要求与离线自检。
- [仓库内 ASAP7 平台](../vendor/README.md)：工艺平台来源、许可与逐文件哈希。

本地设计一致性检查：`python3 benchmark/validate_spec.py`；加 `--verify-source` 可在线核对锁定的 CVDP 数据文件与两道题的题面哈希。

## 范围与工具

功能验收计划使用预装的 Verilator、Yosys、Python/cocotb、RISC-V 裸机工具链及 Sail/ACT4；PPA 评估使用 Yosys + ASAP7 + OpenROAD，不单独依赖其他 STA 程序。不以商用 EDA 许可为参赛前提。本机已安装 OpenROAD 26Q2-1164-g08f67ee5ec 和 Yosys 0.69+150，并用仓库内 ASAP7 跑通 ORFS 的 `gcd` 综合至详细布线冒烟。九题参考实现、统一约束、功耗及重复性尚待校准，因此尚无正式 PPA 分数。SystemVerilog testbench、适用的 SVA 和 Verilator 覆盖率均可作为参赛交付物。评测器必须先用实际固定版本运行每项语法、覆盖率和 UVM 依赖的冒烟测试；不能仅凭工具名称假定所有语法都可运行。

本规范评估可综合 RTL 的功能正确性、统一开源物理流程下的 PPA 估计及完成时间，也记录验证交付质量；不声称流片签核、模拟电路或正式 RISC-V 认证。PPA 只有在工具镜像、工艺、约束、活动负载和参考值校准完成后才参与正式排名。

## 来源

- [NVIDIA CVDP 数据与运行框架](https://github.com/NVlabs/cvdp_benchmark)
- [CVDP 数据集](https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset)
- [RISC-V Architectural Certification Tests](https://github.com/riscv/riscv-arch-test)
- [RISC-V ISA 手册](https://github.com/riscv/riscv-isa-manual)
- [Verilator 官方语言支持范围](https://verilator.org/guide/latest/languages.html)
