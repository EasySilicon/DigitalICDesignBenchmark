# 数字芯片设计交付 Benchmark v0.2

本目录是一套正在校准的数字芯片交付 benchmark，用于比较多 Agent 系统与通用 coding agent 的完整 RTL 交付质量。它包含 10 个任务，覆盖组合逻辑、时序控制、片上总线、CDC、缓存、五级流水线 CPU 和多精度 NPU 矩阵乘法。每题要求 Agent 自行完成 RTL、可运行验证环境和 PPA 优化迭代。旧版 T01–T09 均有公开冒烟、私有隐藏验收器和 75/75 的参考功能分；统一 ASAP7 最坏角、2500 ps 的三种子布线和长负载功耗试跑也已完成，[九题参考三元组](ppa-baselines.json)作为试评分记录。**新增 T10 已有题卡、数值 oracle 和公开冒烟，但没有隐藏验收器、参考 RTL、变异体或 PPA 基线，不能给正式分数。**工具镜像 digest、不同 RTL 写法的公平性检查、交付质量门禁和完整试做报告仍须按[发布门禁](methodology.md#发布门禁)校准。

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
| T10 | 10 | 4×4 多精度脉动阵列矩阵乘法 | 原创 | 48 小时 |

难度序号是设计时的覆盖假设，不是 CVDP 官方难度，也不是已测得的等距难度。发布前应依照[校准流程](methodology.md#难度校准)用试运行数据调整或替换题目。两道 CVDP 题应单独报告，避免公开题的训练数据污染影响原创题结论。

## 规范入口

- [任务卡](tasks.md)：每题的设计需求、接口、合法环境、硬件资源边界、验收点及分值。
- [十题验收组](acceptance.md)：测试组 ID、参考模型与可检出的典型缺陷。
- [独立端口公开冒烟](../evaluator/README.md)：T01–T10 可执行测试与提交接口样例。
- [验证与交付契约](verification-contract.md)：参赛 Agent 的自带 UT、固定 DUT 接口、独立验收与 CPU ELF 入口。
- [评测与评分方法](methodology.md)：运行资源、可比性、通用门禁、分数计算、校准和发布条件。
- [PPA 测量方法](ppa.md)：统一工艺、约束、工作负载、功耗估计和排序规则。
- [试评分 PPA 参考值](ppa-baselines.json)：九题三种子布线与门级活动功耗的中位数和重复性记录。
- [领域与难度覆盖](coverage.md)：逐题设计领域、工程能力、难度来源和未覆盖范围。
- [CPU 验收计划](cpu-validation.md)：ACT4 接入、流水线专项程序、差分测试和通过条件。
- [NPU 验收计划](npu-validation.md)：T10 的格式边界、命令规模、数值 oracle、结构与物理发布门禁。
- [来源锁定](sources.lock.yaml)：CVDP 的修订、数据文件及题面哈希。
- [机器可读清单](manifest.yaml)：题目 ID、时限、模型 token 上限及分值，供评测器读取。
- [运行报告 schema](report.schema.json)：统一记录功能、PPA、完成时间和交付诊断。
- [安装与依赖清单](../env/README.md)：分阶段安装、版本锁定要求与离线自检。
- [仓库内 ASAP7 平台](../vendor/README.md)：工艺平台来源、许可与逐文件哈希。

本地设计一致性检查：`python3 benchmark/validate_spec.py`；加 `--verify-source` 可在线核对锁定的 CVDP 数据文件与两道题的题面哈希。2026-09-25 的在线核对已通过。

每题可用 `python3 benchmark/prepare_trial.py T04 /path/to/empty/T04` 生成仅含公开材料的独立参赛工作区及 `PROMPT.md`。比较不同 Agent 时，每题均从新对话和空工作区开始，锁定相同的任务材料、模型配置、工具环境及计时起止；不要复用上一题的会话或产物。Codex 试跑为每题启动新的 `codex exec --ephemeral` 进程，不使用 `resume`；评测方保存每题的启动、结束时间戳和退出码。私有验收器和参考 RTL 只保存在评测方环境，不进入参赛工作区。

本机预发布试跑只验证了新会话和独立目录，使用 full access 时没有操作系统级目录隔离。正式横向比较须按[评测与评分方法](methodology.md)为每题建立独立容器或等效权限边界；否则不得把试跑分数作为严格隔离的正式排名。

## 范围与工具

功能验收使用预装的 Verilator、Yosys、Python/cocotb、RISC-V 裸机工具链及 Sail/ACT4；PPA 评估使用 Yosys + ASAP7 + OpenROAD，不单独依赖其他 STA 程序。不以商用 EDA 许可为参赛前提。本机已安装 OpenROAD 26Q2-1164-g08f67ee5ec 和 Yosys 0.69+150，并用仓库内 ASAP7 跑通九题参考设计的三种子详细布线与活动功耗链。当前参考三元组只用于试评分，尚无正式榜单。SystemVerilog testbench、适用的 SVA 和 Verilator 覆盖率均可作为参赛交付物。评测器必须先用实际固定版本运行每项语法、覆盖率和 UVM 依赖的冒烟测试；不能仅凭工具名称假定所有语法都可运行。

本规范评估可综合 RTL 的功能正确性、统一开源物理流程下的 PPA 估计及完成时间，也记录验证交付质量；不声称流片签核、模拟电路或正式 RISC-V 认证。PPA 只有在工具镜像、工艺、约束、活动负载和参考值校准完成后才参与正式排名。

## 来源

- [NVIDIA CVDP 数据与运行框架](https://github.com/NVlabs/cvdp_benchmark)
- [CVDP 数据集](https://huggingface.co/datasets/nvidia/cvdp-benchmark-dataset)
- [RISC-V Architectural Certification Tests](https://github.com/riscv/riscv-arch-test)
- [RISC-V ISA 手册](https://github.com/riscv/riscv-isa-manual)
- [Verilator 官方语言支持范围](https://verilator.org/guide/latest/languages.html)
- [OCP OFP8 1.0](https://www.opencompute.org/documents/ocp-8-bit-floating-point-specification-ofp8-revision-1-0-2023-06-20-pdf)
- [OCP MX 1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf)
