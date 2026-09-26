# 独立端口验收器的公开可执行样例

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

编译与仿真在独立临时目录执行，失败以非零退出码和 JSON 摘要报告。T07 公开样例覆盖 AW/W 两种先后顺序、APB SETUP/ACCESS、部分/零字节使能、读写及错误响应、有限等待和 B/R 背压，尚未覆盖同时读写争用和运行中复位。T08 公开样例覆盖命中、干净/脏替换、整行写回、部分写、后端与 CPU 背压，以及空闲时复位。T09 公开样例只检查 64 条无相关 ADDI 的取指至退休延时和退休观察口；它不运行 ELF 或覆盖完整 ISA。T10 公开样例覆盖十个模式、20 块连续双 1024-bit/拍输入、最高位、16 行输出及背压；数值特殊值和自动结构网表检查由私有评测器执行。这里的用例都是**公开冒烟样例**，不用于正式评分；T01–T09 的私有隐藏验收器、参考实现和变异体已在评测方仓库实现；T10 独立参考及 PPA 基线尚未完成。隐藏验收器使用相同连接原则，并保存在不暴露给参赛工作区的评测服务中。

`cpu_elf_check.py` 是另一个评测方入口。它解析符合任务卡内存布局的 RV32 ELF，把 `PT_LOAD` 段装入评测方的 256 KiB 镜像，通过固定 CPU 端口提供一周期取指和有界数据端等待，直到已提交的 `tohost=1` 写入或超时。例如：

```bash
python3 evaluator/cpu_elf_check.py /path/to/submission /path/to/program.elf
python3 evaluator/make_cpu_smoke.py /tmp/ic_bcmk_cpu_programs
python3 evaluator/cpu_elf_check.py /path/to/submission /tmp/ic_bcmk_cpu_programs/basic.elf
```

这个入口检查 ELF 装载、总线基本握手和 `tohost` 完成条件；可加 `--trace-output /tmp/dut.jsonl`，由**评测方测试平台**采集 DUT 提交/异常端口。`sail_commit.py` 将 Sail 0.14.1 的 `--trace-instr --trace-gpr --trace-mem` 轨迹转换为相同语义的逐条预期，并可用 `--dut-trace` 比较 PC、指令、寄存器写回与对齐后的 store 地址/字节使能/有效写入字节。Agent 不需产生 trace 文件。私有五级参考 CPU 已通过 ACT4 45/45、定向 108/108、随机长程序 100/100 和题卡专属异常 4/4；这个公开入口本身仍不产生正式 CPU 架构分。[`act4_elfs/`](act4_elfs/) 包含按本题 256 KiB 布局生成的 45 个公开 RV32I/Zicsr ACT4 ELF，可用 `python3 evaluator/verify_act4_artifacts.py` 核对清单与内存边界。45 个 ELF 已由 `check_act4_sail.py` 在锁定 Sail 配置下逐一运行到 `tohost=1`，逐项哈希、步数和轨迹哈希见[参考结果](act4_elfs/SAIL_RESULTS.json)：

```bash
python3 evaluator/check_act4_sail.py \
  --sail /path/to/sail_riscv_sim \
  --nm /path/to/riscv32-unknown-elf-nm \
  --output /tmp/act4_sail_results.json
```

私有统一评分入口还运行总线等待、运行中复位、取指至退休延时与自动时序组合门禁；参考 CPU 的 F/P 为 75/75。正式排名仍等待 PPA 参数和交付资格冻结。

`score_rules.json` 将十题的 F=60/P=15 分项逐一映射到验收组，`score_run.py` 将评测方生成的组内通过数、严重安全缺陷、PPA 三元组和完成时间转成分层分数。它**不调用**公开冒烟测试来制造正式分数。输入须包含 `task_id`、`groups`、`delivery_qualified`、`elapsed_seconds`、`time_limit_seconds`，可含 `ppa_measurement` 和 `ppa_reference`。每个验收组必须有 `cases_passed`、`cases_total`，安全缺陷另标 `safety_violation`。缺少应有验收组直接报错，不推断为通过；所有组全过得子项满分，无安全缺陷且各组通过比例的等权平均至少一半得半分，其余得零分。T01–T10 私有隐藏组执行器已接入；T10 独立参考及 PPA 基线仍在准备。

T10 的[`matmul_oracle.py`](matmul_oracle.py)公开了精确格式解码、MX scale 和数值误差界，可供参赛者复核题意；`tb_T10.sv` 是固定端口的 20 块流式公开冒烟。`score_run.py` 在 T10 隐藏验收和 PPA 参考值校准完成前会拒绝为 T10 输出正式分数。

`delivery_check.py` 是交付入口的可执行检查：确认 `rtl/files.f`、`verif/`、`README.md`、可执行 `run.sh`，同一 `BENCH_SEED` 连续运行两次并校验 `results.json` 的测试行和版本字段。T09 另需评测方提供正反两个 ELF，检查 `--elf` 的文件哈希、`tohost`、超时字段与退出码。它只检查自带验证入口的交付形式，**不将其 PASS 当作 DUT 正确性**；PPA 探索记录与变异检出率仍需独立审计。

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

合成轨迹回归已覆盖正常、早一拍、晚一拍、漏提交、重复取指和重复退休。T09 公开 RTL 测试连接一周期指令存储器检查这一延时；私有评分入口另用自己的 ELF 装载器、数据总线、Sail 提交差分、精确异常测试和自动时序评分。Agent 自带的 `run.sh`/UT 输出不能直接作为这个 trace 的评分输入。
