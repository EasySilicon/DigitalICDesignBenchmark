# 独立端口验收器的公开可执行样例

当前 T01–T10 物理评估每种子共用 **60 分钟墙钟时限**，超时保留结果并继续其余种子。有效已完成种子仍可计分；没有完整有效测量时 PPA 和时间分计零。详见[物理评估时限与超时判分](../benchmark/physical-runtime-policy.md)。

[English](README.en.md)

## T08 SRAM 物理资格流程

`PYTHONPATH=evaluator python3 evaluator/run_t08_sram_ppa.py /path/to/reference --orfs-root /path/to/ORFS --output-dir /path/to/fresh-evidence`
使用独立新目录，依次运行宏模型自检、自动存储映射、111 次功能验收、
270 次并发压力回归、seed11 布局及带宏 Liberty 的门级功耗。默认只跑
一个种子用于优化；setup/hold/DRC 全通过后，再用
`--qualify-from /path/to/seed11/aggregate.json` 复用 seed11 并追加 29/47。
三域均为 1 GHz，宏为固定 lambdapdk `fakeram7_tdp_4096x32`；不修改
原 RTL，保持存储容量，并要求完成显式 SRAM 映射。
标准单元 WC 与 SRAM TT 的混合时序模型、完整宏面积、逐实例非零动态
功耗及宏引脚连接都留有审计证据。DRC 限于布线及引脚接入，非宏内部
DRC/LVS。只有三种子 setup/hold/DRC 全满足且重新回归通过，才冻结参考。
应在受内存约束的进程组中运行；每个物理种子启动前等待可用内存至少
50 GiB。阶段、错误和已完成种子在 `state.json`，不改历史模型成绩。
完整策略及模型限制见 [T08 作者指南](../benchmark/tasks/T08/AUTHOR_GUIDE.md)。

## T08：VLAN 验收与作者侧负向回归

`python3 -m evaluator.t08_check /path/to/submission --output /tmp/t08.json`
运行 37 个场景入口 × 3 个种子，功能上限为 50；三种子 SRAM PPA 参考已冻结。
验收器 `3.1-boundary-crosses` 分别改变 VID 值、有效位、untagged 与 priority，
覆盖首个 raw 解码字节之后、header 判定之前的双向更新及下一帧应用。
配置快照组的 4 分在六个入口之间等权分配，不额外增加总分。

```sh
python3 -m evaluator.t08_mutation_check --baseline /path/to/correct/submission --output-dir /tmp/t08-qualification --jobs 3
python3 -m unittest evaluator.test_t08_mutation_check benchmark.test_t08_spec benchmark.test_prepare_trial
```

负向回归先要求正例完整通过，再编译 14 个临时错误版本；编译失败、锚点
失配、漏掉任何指定种子的见证用例，都不能算检出。脚本不会修改正例，
也不内置正确 RTL；当前变异锚点针对 pilot streaming parser，其他结构需
显式适配。脚本、独立验收器与 qualification 记录均不进入考生输入包。
有限变异集不是任意 RTL 错误必然检出的证明。旧试做仍保留原冻结验收器。

本文档属于 **Digital IC Design Benchmark for Agents**。

`public_check.py` 只读取参赛提交的 `rtl/files.f` 和 RTL 源码，使用**评测方自己的** T01–T10 的测试平台编译并检查固定 DUT 端口。它不会调用提交内的 `run.sh`、`verif/` 或 `results.json`。例如：

```bash

python3 evaluator/public_check.py T01 /path/to/submission --seed 1234
python3 evaluator/public_check.py T02 /path/to/submission --width 32 --depth 16
python3 evaluator/public_check.py T03 /path/to/submission
python3 evaluator/public_check.py T04 /path/to/submission --n-inputs 8 --width 32
python3 evaluator/public_check.py T05 /path/to/submission --depth 16 --width 32
python3 evaluator/public_check.py T06 /path/to/submission
python3 evaluator/public_check.py T07 /path/to/submission
python3 evaluator/public_check.py T09 /path/to/submission
```

编译与仿真在独立临时目录执行，失败以非零退出码和 JSON 摘要报告。T06 公开样例覆盖 AW/W 两种先后顺序、APB SETUP/ACCESS、部分/零字节使能、读写及错误响应、有限等待和 B/R 背压，尚未覆盖同时读写争用和运行中复位。T07 公开样例覆盖命中、干净/脏替换、整行写回、部分写、后端与 CPU 背压，以及空闲时复位。T09 公开样例只检查 64 条无相关 ADDI 的取指至退休延时和退休观察口；它不运行 ELF 或覆盖完整 ISA。T10 公开样例覆盖十种模式共 248 个无间隔块、逐拍双 1024-bit 输入、四个带块 ID 的行槽、4/2/1 行每拍的稳态吞吐及输出背压；T10 对所有提交统一使用 Verilator `--hierarchical` 编译选项，允许大型同型 PE 由提交者标注 `/* verilator hier_block */` 来缩短编译，极值数值与复杂流式场景由正式验收器执行。这里的用例都是**公开冒烟样例**，不用于正式评分；正式验收器、参考实现和变异体的源码随完整仓库公开，但不会复制进被测 Agent 的工作区。T10 独立参考的连续流功能回归已通过；V1.0 的物理交付范围为单 PE，完整 DUT 的功能、结构和吞吐要求不变。v15 的单 PE 三种子时序、完整 DRC/连通及正式活动功耗已通过，详见[三种子测量说明](t10_backend/v1/README.md)。上下文裁剪误报由评测器处理，不允许被测 Agent 忽略 PE 内的某片区域；见[修复与检查说明](t10_backend/README.md)。

`cpu_elf_check.py` 是另一个评测方入口。它解析符合任务卡内存布局的 RV32 ELF，把 `PT_LOAD` 段装入评测方的 256 KiB 镜像，通过固定 CPU 端口提供一周期取指和有界数据端等待，直到已提交的 `tohost=1` 写入或超时。例如：

```bash
python3 evaluator/cpu_elf_check.py /path/to/submission /path/to/program.elf
python3 evaluator/make_cpu_smoke.py /tmp/ic_bcmk_cpu_programs
python3 evaluator/cpu_elf_check.py /path/to/submission /tmp/ic_bcmk_cpu_programs/basic.elf
```

这个入口检查 ELF 装载、总线基本握手和 `tohost` 完成条件；可加 `--trace-output /tmp/dut.jsonl`，由**评测方测试平台**采集 DUT 提交/异常端口。`sail_commit.py` 将 Sail 0.14.1 的 `--trace-instr --trace-gpr --trace-mem` 轨迹转换为相同语义的逐条预期，并可用 `--dut-trace` 比较 PC、指令、寄存器写回与对齐后的 store 地址/字节使能/有效写入字节。Agent 不需产生 trace 文件。评测方五级参考 CPU 已通过 ACT4 45/45、定向 108/108、随机长程序 100/100 和题卡专属异常 4/4；这个公开入口本身仍不产生正式 CPU 架构分。[`act4_elfs/`](act4_elfs/) 包含按本题 256 KiB 布局生成的 45 个公开 RV32I/Zicsr ACT4 ELF，可用 `python3 evaluator/verify_act4_artifacts.py` 核对清单与内存边界。45 个 ELF 已由 `check_act4_sail.py` 在锁定 Sail 配置下逐一运行到 `tohost=1`，逐项哈希、步数和轨迹哈希见[参考结果](act4_elfs/SAIL_RESULTS.json)：

```bash
python3 evaluator/check_act4_sail.py \
  --sail /path/to/sail_riscv_sim \
  --nm /path/to/riscv32-unknown-elf-nm \
  --output /tmp/act4_sail_results.json
```

统一正式评分入口还运行总线等待、运行中复位、取指至退休延时与自动时序组合门禁；参考 CPU 的原始功能成绩为 75/75，归一化功能分为 50/50。当前 T09 参考的功能、周期与三种子 1 GHz PPA 资格已重新冻结；套题正式发布仍需统一工具镜像与整套证据审核。

`score_rules.json` 将默认 F=60/P=15 原始权重逐一映射到验收组；T09 单独采用 F=48/P=27，为周期组保留归一化 10 分，再按 `50/75` 归一为 50 分功能分；PPA 为 50 分，时间为 5 分，显示总分上限为 105。套题显示分按难度权重作非归一化加权：T01/T02 各 0.03，T03--T05 各 0.06，T06/T07 各 0.10，T08 为 0.11，T09 为 0.20，T10 为 0.25；缺失分量不计入且不重新放大其余权重。`score_run.py` 将评测方生成的组内通过数、严重安全缺陷、PPA 三元组和完成时间转成分层分数。它**不调用**公开冒烟测试来制造正式分数。输入须包含 `task_id`、`groups`、`delivery_qualified`、`elapsed_seconds`、`time_limit_seconds`，可含 `ppa_measurement`、`ppa_reference` 和由评测方裁定的 `candidate_delivery_error_count`。当前候选使用 `score_with_power_budget.py`：交付扣分每题最多 10 分，单项缺件或一处运行错误扣 5 分，缺少两项及以上或两个不同交付错误扣 10 分；同一根因重复失败只计一次，基础设施故障不扣分，已验证的功能、PPA 和时间分保留。交付检查输出完整的 `delivery_assessment`，运行错误须完成归因再扣分。详见[交付扣分规则](../benchmark/delivery-policy.md)。`score_run.py` 保留历史规则，供旧成绩复现。每个验收组必须有 `cases_passed`、`cases_total`，安全缺陷另标 `safety_violation`。缺少应有验收组直接报错，不推断为通过；所有组全过得子项满分，无安全缺陷且各组通过比例的等权平均至少一半得半分，其余得零分。T10 的九项按各自用例比例计分：数值、协议和角例不因脉动吞吐失败被抹除；吞吐或结构失败仍使 `MM-SYSTOLIC` 为零，并取消 PPA 和时间分。正式分组执行器随仓库公开，但从参赛工作区隔离；T10 参考已通过功能回归及单 PE 三种子物理与活动功耗资格验证。

候选完成布线后，setup 违例除进入实测关键路径延迟外，再按最差 seed 的 `D_worst=T_target+max(0,-setup_slack)` 乘 `(T_target/D_worst)^4`，使实际最高频率越偏离目标，得分越快但连续地下降；负 hold slack 的绝对值仍加入评分用等效延迟。DRC 不把 PPA 直接清零：任一布线种子存在 DRC 时，最终 PPA 分统一乘 0.5。参考基线自身仍必须满足 setup/hold 且 DRC 为零；无法完成合法布线、缺少受约束路径或缺少有效活动功耗时才记 PPA=0。

`ppa_aggregate.py` 是公开的三种子 PPA 记录聚合入口。它校验布局与功耗记录来自同一路由结果、固定工艺参数、活动标注、工作负载哈希以及种子 `{11,29,47}`，并保留 setup、hold 和 DRC 原始测量供评分。全仓库唯一的权威参考基线是 [`benchmark/ppa-baselines.json`](../benchmark/ppa-baselines.json)；评测脚本不得维护另一份基线副本。

**所有题目的功耗编译时限：** 新候选统一通过 `power_probe_with_budget.py`、
`aggregate_with_power_budget.py`、`score_with_power_budget.py` 收集功耗、聚合记录和评分，T10 专用候选入口使用同一实现。
每个布局种子的完整功耗仿真编译共用 1,200 秒墙钟预算，包括 Verilator、C++、
链接和 SAIF 运行库构建；任一种子超时则该题 PPA/耗时加分为 0，功能分保留。
超时会终止进程树并保留日志和 `power_compile.json`；普通编译错误、工具缺失及
无效证据仍需归因，不自动判超时。独立功能测试的时限不变。
详见[统一规则与入口参数](../benchmark/power-compile-policy.md)。旧冻结脚本仅用于
复现历史基线，其字节、工作负载哈希和历史成绩不因新增时限而改写。
T09 功能验收与 PPA 一并计分时使用 `check_t09_with_power_budget.py`，另通过可重复的
`--power-compile-record` 传入编译记录。两套 T10 候选调度器都会在超时后跳过
该提交剩余功耗种子。当前评分和发布默认要求编译记录，只有显式 `--legacy-replay`
才允许核验政策生效前的旧测量。成绩重算工具校验并保留编译时限记录。

`t10_structure_check.py` 是 T10 的公开结构验收入口。它在 Yosys 展开网表上检查固定流接口、256 个 PE、16×16 横纵寄存链和累加反馈；检查支持显式层次及 Yosys 保留层次后产生的递归实例，不要求把 256 个 PE 全部直接实例化在顶层。回归入口：

```bash
PYTHONPATH=evaluator python3 -m unittest \
  evaluator.test_ppa_aggregate evaluator.test_t10_structure_check -v
```

带日期的 `t*_pilot_*.json` 是历史试跑证据，其中的旧时限和旧分数单位按实际运行原样保留，不是当前配置。当前时限只以 [`benchmark/manifest.yaml`](../benchmark/manifest.yaml) 和各题 `task.yaml` 为准。

T10 的[任务包内公开数值 oracle](../benchmark/tasks/T10/public/matmul_oracle.py)定义精确格式解码、MX scale 和数值误差界，可供参赛者复核题意；`tb_T10.sv` 是固定流接口的 248 块持续吞吐公开冒烟，并额外检查一个背压块。T10 的 PPA 计分要求功能、结构与持续吞吐全通过，并具备合格的三种子测量记录。

`delivery_check.py` 是交付入口的可执行检查：确认 `rtl/files.f`、`verif/`、`README.md`、可执行 `run.sh`，同一 `BENCH_SEED` 连续运行两次并校验 `results.json` 的测试行和版本字段。它只检查自带验证入口的交付形式，**不将其 PASS 当作 DUT 正确性**；PPA 探索记录与变异检出率仍需独立审计。


T01 的独立功能入口为 `python3 evaluator/t01_check.py /path/to/submission`。它用 Python bit-stream oracle 生成逐周期向量，并检查 `AC-05` 至 `AC-08B`；`--reference` 可回归评测方参考 RTL。`python3 evaluator/t01_mutation_check.py` 重建并运行十个可综合缺陷变异体；`make_t01_power_vectors.py` 生成固定的自检功耗负载，`ppa_probe.py` 与 `ppa_power_probe.py` 分别采集每个布局种子的布线后面积/时序和 1 GHz 门级活动功耗。资格记录见 `t01_qualification.json`。这些文件随仓库公开，但 `prepare_trial.py` 不会把参考 RTL、隐藏向量生成器或变异逻辑复制到参赛工作区。

T02 的独立功能入口为 `python3 evaluator/t02_check.py /path/to/submission`，会对 `WIDTH={8,32}`、`DEPTH={3,8,16}` 六种组合汇总 `AC-09` 至 `AC-15`；`--reference` 回归评测方参考 RTL。`python3 evaluator/t02_mutation_check.py` 确定性生成并验证九个可综合缺陷变异体。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t02_qualification.json`。

T03 的独立功能入口为 `python3 evaluator/t03_check.py /path/to/submission`，以逐拍 APB4/定时器模型检查 `AC-16` 至 `AC-20`；`--reference` 回归评测方参考 RTL。`python3 evaluator/t03_mutation_check.py` 确定性生成并验证十个可综合缺陷变异体。功耗平台以 1000 ps 周期运行同一自检负载，并按完成的 APB 访问计数。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t03_qualification.json`。

T04 的独立功能入口为 `python3 evaluator/t04_check.py /path/to/submission`，会对 `N={4,8}`、`WIDTH={8,32}` 四种组合汇总 `AC-21` 至 `AC-25`；`--reference` 回归评测方参考 RTL。`python3 evaluator/t04_mutation_check.py` 确定性生成并验证九个可综合缺陷变异体。功耗平台以 1000 ps 周期运行同一自检仲裁负载，并按完成的流传输计数。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t04_qualification.json`。

T05 的独立功能入口为 `python3 evaluator/t05_check.py /path/to/submission`，会对 `WIDTH={8,32}`、`DEPTH={8,16}` 四种组合和多组非锁相读写时钟比汇总 `AC-26` 至 `AC-31`；`--reference` 回归评测方参考 RTL。除逐拍外部记分板外，AC-31 还对每种参数组合运行 Yosys 网表双向 2FF/本地复位结构检查。`python3 evaluator/t05_mutation_check.py` 确定性生成并验证十三个可综合缺陷变异体，包括二进制指针直接跨域和满判 Gray 码极性错误。PPA 平台将 `wr_clk`、`rd_clk` 都约束为 1000 ps、声明为异步时钟组，功耗负载按成功读出计数。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t05_qualification.json`。

T06 的独立功能入口为 `python3 evaluator/t06_check.py /path/to/submission`，汇总 `AC-32` 至 `AC-37`，覆盖 AXI 写地址/数据任意先后、APB SETUP/ACCESS、读写响应、并发仲裁、等待/返回背压与复位；`--reference` 回归评测方参考 RTL。`python3 evaluator/t06_mutation_check.py` 确定性生成并验证十五个可综合缺陷变异体。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t06_qualification.json`。

T07 的独立功能入口为 `python3 evaluator/t07_check.py /path/to/submission`，汇总 `AC-38` 至 `AC-43`，覆盖读写命中、干净/脏替换、写分配、全部字节使能、双侧背压、复位和命中时延；`--reference` 回归评测方参考 RTL。`python3 evaluator/t07_mutation_check.py` 确定性生成并验证十六个可综合缺陷变异体。三种子 1 GHz 参考基线、冻结 hash 和资格结果见 `t07_qualification.json`。

T09 的独立功能入口为 `python3 evaluator/check_t09_with_power_budget.py /path/to/submission --elapsed-seconds SECONDS`。它运行 45 个 ACT4、108 个定向、100 个差分随机、80 个总线等待、4 个运行中复位、4 个题卡专项异常和 64 条取指至退休延时检查，再交给统一评分器汇总。冻结 ELF、汇编源和压缩提交 oracle 位于 `t09_data/`，可用 `python3 evaluator/verify_t09_artifacts.py` 校验清单、SHA-256、压缩 JSONL 和事件数。`python3 evaluator/t09_mutation_check.py` 在临时目录生成并验证二十一个可综合缺陷变异体。当前参考 RTL 的归一化功能分为 50/50，新增周期检查 22/22 通过；2026-10-09 重新冻结的资格记录见 `t09_qualification.json`。T09 的三种子 ASAP7 WC 1 GHz 参考物理基线已完成，全部 setup/hold/DRC 通过；最薄的 seed 47 setup 裕量为 +9.008 ps，详见 `benchmark/ppa-baselines.json`。

`port_timing_v1` 通过 `t09_timing_check.py` 运行 22 项固定端口周期检查，在 `t09_group_cycles10_v1` 中组成独立的 `CPU-PIPE-CYCLES` 组：22 项全过得 10 分，通过 11–21 项得 5 分，通过 0–10 项得 0 分，其余验收组共 40 分。检查涵盖独立 ADDI 的四拍延时和 IPC=1、ALU 前递、load-use 气泡及直线程序退休跨度预算，使用三种固定 ready/response 时序。分支/JAL/JALR 罚拍作为诊断记录。具体规则见 `benchmark/tasks/T09/acceptance.md`；参考资格见 `t09_timing_qualification.json` 和 `fixtures/t09_cpu_20261009_cycles10/`。

参考重新冻结入口为 `python3 evaluator/t09_reference_freeze.py --measurement /path/to/three_seed_measurement.json --evidence-dir evaluator/fixtures/NEW_T09_EVIDENCE`。它重新汇总三种子，逐一核对实际 RTL、1 GHz SDC、最终报告和功耗 workload，并重新运行全部功能、22 项周期与 21 个变异体；任一种子 setup/hold/DRC 不过、证据不全或源代码不一致都会拒绝。证据目录须为新目录，PPA 基线最后原子更新，不自动重算历史候选成绩。

## T08/T09 已冻结资格与结果

T08 使用 `python3 -m evaluator.t08_check /path/to/submission --output functional.json`，
37 个计分场景各跑三种子，共 111 次。`t08_stress_check.py` 另跑 270 次并发资格回归，
不额外加功能分。参考的原始及 SRAM 映射版本均全过；三种子 1 GHz 研究 PPA
资格与原始报告见 `t08_qualification.json`、`fixtures/t08_reference_20261008/`。
旧 T11 标签仅保留在历史原始证据内；当前题号是 T08。唯一评分基线仍是
`benchmark/ppa-baselines.json`，不使用私有基线副本。

正式成绩位于 `results/<model>/summary.json`。T08/T09 冻结清单通过
`python3 benchmark/freeze_tasks.py` 校验；原始答卷、预算与测量记录保持归档。

## T05 双级同步结构检查实现

`cdc_2ff_check.py` 读取 [Yosys `write_json`](https://yosyshq.readthedocs.io/projects/yosys/en/0.46/cmd/write_json.html) 导出的展平网表，按触发器 `CLK/D/Q` 连线检查 `wr_clk→rd_clk` 和 `rd_clk→wr_clk` 两方向是否各有至少 `$clog2(DEPTH)+1` 条**直接、隔离的双级寄存器链**。第一级只能连到同目的时钟、同异步复位的第二级；跨域组合逻辑、第一级扇出到功能逻辑、`wr_ready/rd_valid` 直接依赖异域触发器都会报错。运行入口：

```bash
python3 evaluator/cdc_2ff_check.py /path/to/t05_yosys.json --depth 8
python3 -m unittest evaluator.test_cdc_2ff_check -v
```

回归用 Yosys 生成多种网表：分离寄存器和 packed 移位寄存器的双级链通过；一级链和第一级直接暴露给输出的变异体失败。检查还确认前两级异步复位连接目的域本地低有效复位。该工具**并非完整 CDC 签核**：Gray 码生成、每次只翻转一位、存储体边界、复位释放、MTBF 与物理实现不由它证明。AC-31 分数按四组参数下的自动网表规则产生；其他可观察 FIFO 行为由独立端口长流检查。

## T09 取指至退休延时检查原型

`cpu_latency_check.py` 接收**评测方测试平台**记录的逐周期 JSONL，参赛 Agent 无需提交此文件；每行的 `imem_valid_pre/imem_addr_pre` 是上升沿前的取指请求，`commit_valid_post/commit_pc_post` 是同一上升沿后稳定的提交观察。测试程序为从 `0x8000_0000` 起连续 64 条无相关 ADDI。每个 PC 的提交须比对应取指边沿晚四个完整周期；检查器拒绝提前、迟到、重复取指、乱序和漏提交。

```bash
python3 evaluator/cpu_latency_check.py /path/to/evaluator-captured-trace.jsonl
python3 -m unittest evaluator.test_cpu_latency_check -v
```

合成轨迹回归已覆盖正常、早一拍、晚一拍、漏提交、重复取指和重复退休。T09 公开 RTL 测试连接一周期指令存储器检查这一延时；正式评分入口另用自己的 ELF 装载器、数据总线、Sail 提交差分、精确异常测试和自动时序评分。Agent 自带的 `run.sh`/UT 输出不能直接作为这个 trace 的评分输入。

现行物理入口为 `route_with_slang.py`。Yosys 须提供可用的 `read_slang`，内置或插件均可；前端缺失或配置错误属于评测环境问题，不作为候选的综合失败。`ppa_probe.py` 保留旧测量的复现入口。

冻结清单：[T08](../benchmark/tasks/T08/FREEZE.json)、[T09](../benchmark/tasks/T09/FREEZE.json)。T10 单 PE 参考测量见[后端说明](t10_backend/v1/README.md)。
