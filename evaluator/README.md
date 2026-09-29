# 独立端口验收器的公开可执行样例

[English](README.en.md)

本文档属于 **Digital IC Design Benchmark for Agents**。

`public_check.py` 只读取参赛提交的 `rtl/files.f` 和 RTL 源码，使用**评测方自己的** T01–T10 的测试平台编译并检查固定 DUT 端口。它不会调用提交内的 `run.sh`、`verif/` 或 `results.json`。例如：

```bash
python3 evaluator/public_check.py T01 /path/to/submission
python3 evaluator/public_check.py T02 /path/to/submission --seed 1234
python3 evaluator/public_check.py T03 /path/to/submission --width 32 --depth 16
python3 evaluator/public_check.py T04 /path/to/submission
python3 evaluator/public_check.py T05 /path/to/submission --n-inputs 8 --width 32
python3 evaluator/public_check.py T06 /path/to/submission --depth 16 --width 32
python3 evaluator/public_check.py T07 /path/to/submission
python3 evaluator/public_check.py T08 /path/to/submission
python3 evaluator/public_check.py T09 /path/to/submission
```

编译与仿真在独立临时目录执行，失败以非零退出码和 JSON 摘要报告。T07 公开样例覆盖 AW/W 两种先后顺序、APB SETUP/ACCESS、部分/零字节使能、读写及错误响应、有限等待和 B/R 背压，尚未覆盖同时读写争用和运行中复位。T08 公开样例覆盖命中、干净/脏替换、整行写回、部分写、后端与 CPU 背压，以及空闲时复位。T09 公开样例只检查 64 条无相关 ADDI 的取指至退休延时和退休观察口；它不运行 ELF 或覆盖完整 ISA。T10 公开样例覆盖十种模式共 248 个无间隔块、逐拍双 1024-bit 输入、四个带块 ID 的行槽、4/2/1 行每拍的稳态吞吐及输出背压；T10 对所有提交统一使用 Verilator `--hierarchical` 编译选项，允许大型同型 PE 由提交者标注 `/* verilator hier_block */` 来缩短编译，极值数值与复杂流式场景由正式验收器执行。这里的用例都是**公开冒烟样例**，不用于正式评分；正式验收器、参考实现和变异体的源码随完整仓库公开，但不会复制进被测 Agent 的工作区。T10 独立参考的连续流功能回归已通过，但 PPA 基线尚未完成。

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

统一正式评分入口还运行总线等待、运行中复位、取指至退休延时与自动时序组合门禁；参考 CPU 的 F/P 为 75/75。正式排名仍等待 PPA 参数和交付资格冻结。

`score_rules.json` 将十题的 F=60/P=15 分项逐一映射到验收组，`score_run.py` 将评测方生成的组内通过数、严重安全缺陷、PPA 三元组和完成时间转成分层分数。它**不调用**公开冒烟测试来制造正式分数。输入须包含 `task_id`、`groups`、`delivery_qualified`、`elapsed_seconds`、`time_limit_seconds`，可含 `ppa_measurement` 和 `ppa_reference`。每个验收组必须有 `cases_passed`、`cases_total`，安全缺陷另标 `safety_violation`。缺少应有验收组直接报错，不推断为通过；所有组全过得子项满分，无安全缺陷且各组通过比例的等权平均至少一半得半分，其余得零分。正式分组执行器随仓库公开，但从参赛工作区隔离；T10 独立参考的功能回归已通过，物理 PPA 基线仍在准备。

T10 的[任务包内公开数值 oracle](../benchmark/tasks/T10/public/matmul_oracle.py)定义精确格式解码、MX scale 和数值误差界，可供参赛者复核题意；`tb_T10.sv` 是固定流接口的 248 块持续吞吐公开冒烟，并额外检查一个背压块。`score_run.py` 在 T10 隐藏验收和 PPA 参考值校准完成前会拒绝为 T10 输出正式分数；试评入口对持续吞吐失败的提交将 PPA 与时间分置零。

`delivery_check.py` 是交付入口的可执行检查：确认 `rtl/files.f`、`verif/`、`README.md`、可执行 `run.sh`，同一 `BENCH_SEED` 连续运行两次并校验 `results.json` 的测试行和版本字段。T09 另需评测方提供正反两个 ELF，检查 `--elf` 的文件哈希、`tohost`、超时字段与退出码。它只检查自带验证入口的交付形式，**不将其 PASS 当作 DUT 正确性**；PPA 探索记录与变异检出率仍需独立审计。

T01 的独立功能入口为 `python3 evaluator/t01_check.py /path/to/submission`；`--reference` 回归评测方参考 RTL。它在连续 1000 ps 时钟上检查 `AC-01` 至 `AC-04`，忽略无复位接口的前七次未知输出，并在之后逐沿检查 8-bit 滑动窗口、下降沿行为和沿间保持。`python3 evaluator/t01_mutation_check.py` 确定性生成并验证八个可综合缺陷变异体。资格记录见 `t01_qualification.json`，`gpt-6-sol` 盲测记录见 `t01_pilot_gpt6sol.json`。参考 RTL 的三种子 1 GHz 布线、时序及门级活动功耗基线已经合格。

T02 的独立功能入口为 `python3 evaluator/t02_check.py /path/to/submission`。它用 Python bit-stream oracle 生成逐周期向量，并检查 `AC-05` 至 `AC-08B`；`--reference` 可回归评测方参考 RTL。`python3 evaluator/t02_mutation_check.py` 重建并运行十个可综合缺陷变异体；`make_t02_power_vectors.py` 生成固定的自检功耗负载，`ppa_probe.py` 与 `ppa_power_probe.py` 分别采集每个布局种子的布线后面积/时序和 1 GHz 门级活动功耗。资格记录见 `t02_qualification.json`，`gpt-6-sol` 的公开材料盲测记录见 `t02_pilot_gpt6sol.json`。这些文件随仓库公开，但 `prepare_trial.py` 不会把参考 RTL、隐藏向量生成器或变异逻辑复制到参赛工作区。

T03 的独立功能入口为 `python3 evaluator/t03_check.py /path/to/submission`，会对 `WIDTH={8,32}`、`DEPTH={3,8,16}` 六种组合汇总 `AC-09` 至 `AC-15`；`--reference` 回归评测方参考 RTL。`python3 evaluator/t03_mutation_check.py` 确定性生成并验证九个可综合缺陷变异体。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t03_qualification.json`，`gpt-6-sol` 盲测及正式 PPA 结果见 `t03_pilot_gpt6sol.json`。

T04 的独立功能入口为 `python3 evaluator/t04_check.py /path/to/submission`，以逐拍 APB4/定时器模型检查 `AC-16` 至 `AC-20`；`--reference` 回归评测方参考 RTL。`python3 evaluator/t04_mutation_check.py` 确定性生成并验证十个可综合缺陷变异体。功耗平台以 1000 ps 周期运行同一自检负载，并按完成的 APB 访问计数。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t04_qualification.json`，`gpt-6-sol` 盲测及正式 PPA 结果见 `t04_pilot_gpt6sol.json`。

T05 的独立功能入口为 `python3 evaluator/t05_check.py /path/to/submission`，会对 `N={4,8}`、`WIDTH={8,32}` 四种组合汇总 `AC-21` 至 `AC-25`；`--reference` 回归评测方参考 RTL。`python3 evaluator/t05_mutation_check.py` 确定性生成并验证九个可综合缺陷变异体。功耗平台以 1000 ps 周期运行同一自检仲裁负载，并按完成的流传输计数。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t05_qualification.json`，`gpt-6-sol` 盲测及正式 PPA 结果见 `t05_pilot_gpt6sol.json`。

T06 的独立功能入口为 `python3 evaluator/t06_check.py /path/to/submission`，会对 `WIDTH={8,32}`、`DEPTH={8,16}` 四种组合和多组非锁相读写时钟比汇总 `AC-26` 至 `AC-31`；`--reference` 回归评测方参考 RTL。除逐拍外部记分板外，AC-31 还对每种参数组合运行 Yosys 网表双向 2FF/本地复位结构检查。`python3 evaluator/t06_mutation_check.py` 确定性生成并验证十三个可综合缺陷变异体，包括二进制指针直接跨域和满判 Gray 码极性错误。PPA 平台将 `wr_clk`、`rd_clk` 都约束为 1000 ps、声明为异步时钟组，功耗负载按成功读出计数。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t06_qualification.json`，`gpt-6-sol` 盲测及正式 PPA 结果见 `t06_pilot_gpt6sol.json`。

T07 的独立功能入口为 `python3 evaluator/t07_check.py /path/to/submission`，汇总 `AC-32` 至 `AC-37`，覆盖 AXI 写地址/数据任意先后、APB SETUP/ACCESS、读写响应、并发仲裁、等待/返回背压与复位；`--reference` 回归评测方参考 RTL。`python3 evaluator/t07_mutation_check.py` 确定性生成并验证十五个可综合缺陷变异体。三种子 1 GHz 基线、冻结 hash 和资格结果见 `t07_qualification.json`，`gpt-6-sol` 盲测及正式 PPA 结果见 `t07_pilot_gpt6sol.json`。

T08 的独立功能入口为 `python3 evaluator/t08_check.py /path/to/submission`，汇总 `AC-38` 至 `AC-43`，覆盖读写命中、干净/脏替换、写分配、全部字节使能、双侧背压、复位和命中时延；`--reference` 回归评测方参考 RTL。`python3 evaluator/t08_mutation_check.py` 确定性生成并验证十六个可综合缺陷变异体。三种子 1 GHz 参考基线、冻结 hash 和资格结果见 `t08_qualification.json`；`gpt-6-sol` 盲测功能为 75/75，但其候选未通过 1 GHz 物理门禁，详见 `t08_pilot_gpt6sol.json`。

T09 的独立功能入口为 `python3 evaluator/t09_check.py /path/to/submission --elapsed-seconds SECONDS`。它运行 45 个 ACT4、108 个定向、100 个差分随机、80 个总线等待、4 个运行中复位、4 个题卡专项异常和 64 条取指至退休延时检查，再交给统一评分器汇总。冻结 ELF、汇编源和压缩提交 oracle 位于 `t09_data/`，可用 `python3 evaluator/verify_t09_artifacts.py` 校验清单、SHA-256、压缩 JSONL 和事件数；其中 `programs/random/diff_mem_seed035_v0.elf` 与 `programs/delivery_bad_tohost.elf` 可作为 `delivery_check.py T09` 的公开正反探针。`python3 evaluator/t09_mutation_check.py` 在临时目录生成并验证二十一个可综合缺陷变异体。参考 RTL 在公开入口中为 75/75，资格记录见 `t09_qualification.json`。`gpt-6-sol` 盲测为 60.5/75 功能分，因异常/陷阱组未全过而不具备 PPA 与时间排名资格，详见 `t09_pilot_gpt6sol.json`。T09 的三种子 ASAP7 WC 1 GHz 参考物理基线已完成，全部 setup/hold/DRC 通过；最薄的 seed 29 setup 裕量仅 +0.316 ps，详见 `benchmark/ppa-baselines.json`。

## T06 双级同步结构检查原型

`cdc_2ff_check.py` 读取 [Yosys `write_json`](https://yosyshq.readthedocs.io/projects/yosys/en/0.46/cmd/write_json.html) 导出的展平网表，按触发器 `CLK/D/Q` 连线检查 `wr_clk→rd_clk` 和 `rd_clk→wr_clk` 两方向是否各有至少 `$clog2(DEPTH)+1` 条**直接、隔离的双级寄存器链**。第一级只能连到同目的时钟、同异步复位的第二级；跨域组合逻辑、第一级扇出到功能逻辑、`wr_ready/rd_valid` 直接依赖异域触发器都会报错。运行入口：

```bash
python3 evaluator/cdc_2ff_check.py /path/to/t06_yosys.json --depth 8
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
