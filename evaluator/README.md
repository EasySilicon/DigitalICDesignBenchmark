# 独立端口验收器的公开可执行样例

`public_check.py` 只读取参赛提交的 `rtl/files.f` 和 RTL 源码，使用**评测方自己的** T01–T09 的测试平台编译并检查固定 DUT 端口。它不会调用提交内的 `run.sh`、`verif/` 或 `results.json`。例如：

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

编译与仿真在独立临时目录执行，失败以非零退出码和 JSON 摘要报告。T07 公开样例覆盖 AW/W 两种先后顺序、APB SETUP/ACCESS、部分/零字节使能、读写及错误响应、有限等待和 B/R 背压，尚未覆盖同时读写争用和运行中复位。T08 公开样例覆盖命中、干净/脏替换、整行写回、部分写、后端与 CPU 背压，以及空闲时复位。T09 公开样例只检查 64 条无相关 ADDI 的取指至退休延时和退休观察口；它不运行 ELF 或覆盖完整 ISA。这里的用例都是**公开冒烟样例**，不用于正式评分；全套隐藏验收器、参考实现和变异体仍待实现。隐藏验收器将使用相同连接原则，但存放在不暴露给参赛工作区的评测服务中。

`cpu_elf_check.py` 是另一个评测方入口。它解析符合任务卡内存布局的 RV32 ELF，把 `PT_LOAD` 段装入评测方的 256 KiB 镜像，通过固定 CPU 端口提供一周期取指和有界数据端等待，直到已提交的 `tohost=1` 写入或超时。例如：

```bash
python3 evaluator/cpu_elf_check.py /path/to/submission /path/to/program.elf
python3 evaluator/make_cpu_smoke.py /tmp/ic_bcmk_cpu_programs
python3 evaluator/cpu_elf_check.py /path/to/submission /tmp/ic_bcmk_cpu_programs/basic.elf
```

这个入口只检查 ELF 装载、总线基本握手和 `tohost` 完成条件；**没有 Sail 逐条参考轨迹，不产生 CPU 架构功能分**。目前的最小程序已用独立测试 CPU 桩跑通入口。[`act4_elfs/`](act4_elfs/) 包含按本题 256 KiB 布局生成的 45 个公开 RV32I/Zicsr ACT4 ELF，可用 `python3 evaluator/verify_act4_artifacts.py` 核对清单与内存边界。正式 CPU 验收还须让参考 CPU 跑通全部 ELF，实现 54 个定向模板、100 个随机差分程序、错误/精确异常和流水线结构检查。

`score_rules.json` 将九题的 F=60/P=15 分项逐一映射到验收组，`score_run.py` 将评测方生成的组内通过数、严重安全缺陷、PPA 三元组和完成时间转成分层分数。它**不调用**公开冒烟测试来制造正式分数。输入须包含 `task_id`、`groups`、`delivery_qualified`、`elapsed_seconds`、`time_limit_seconds`，可含 `ppa_measurement` 和 `ppa_reference`。每个验收组必须有 `cases_passed`、`cases_total`，安全缺陷另标 `safety_violation`。缺少应有验收组直接报错，不推断为通过；所有组全过得子项满分，无安全缺陷且各组通过比例的等权平均至少一半得半分，其余得零分。真正的隐藏组执行器和 PPA 测量器尚未接入。

## T06 双级同步结构检查原型

`cdc_2ff_check.py` 读取 [Yosys `write_json`](https://yosyshq.readthedocs.io/projects/yosys/en/0.46/cmd/write_json.html) 导出的展平网表，按触发器 `CLK/D/Q` 连线检查 `wr_clk→rd_clk` 和 `rd_clk→wr_clk` 两方向是否各有至少 `$clog2(DEPTH)+1` 条**直接、隔离的双级寄存器链**。第一级只能连到同目的时钟、同异步复位的第二级；跨域组合逻辑或第一级扇出到功能逻辑会报错。运行入口：

```bash
python3 evaluator/cdc_2ff_check.py /path/to/t06_yosys.json --depth 8
python3 -m unittest evaluator.test_cdc_2ff_check -v
```

回归用 Yosys 生成多种网表：分离寄存器和 packed 移位寄存器的双级链通过；一级链和第一级直接暴露给输出的变异体失败。本工具**尚非完整 CDC 签核**：未覆盖所有存储体边界、Gray 码生成和一次只翻转一位的证明、异步复位释放、MTBF 及物理实现。正式 AC-31 需要在多种等价 RTL 写法和缺陷变异体上校准这些规则，不能直接以本原型的 PASS 给满分。可参考开源 [rtl-buddy-cdc 规则集](https://github.com/rtl-buddy/rtl-buddy-cdc) 扩展，但需固定版本并处理误报与豁免。

## T09 取指至退休延时检查原型

`cpu_latency_check.py` 接收**评测方测试平台**记录的逐周期 JSONL，参赛 Agent 无需提交此文件；每行的 `imem_valid_pre/imem_addr_pre` 是上升沿前的取指请求，`commit_valid_post/commit_pc_post` 是同一上升沿后稳定的提交观察。测试程序为从 `0x8000_0000` 起连续 64 条无相关 ADDI。每个 PC 的提交须比对应取指边沿晚四个完整周期；检查器拒绝提前、迟到、重复取指、乱序和漏提交。

```bash
python3 evaluator/cpu_latency_check.py /path/to/evaluator-captured-trace.jsonl
python3 -m unittest evaluator.test_cpu_latency_check -v
```

合成轨迹回归已覆盖正常、早一拍、晚一拍、漏提交、重复取指和重复退休。T09 公开 RTL 测试已经连接一周期指令存储器来检查这一延时，但 CPU ELF 装载器、数据总线仿真和提交差分仍待实现，因此当前没有可正式评分的 T09 验收器。Agent 自带的 `run.sh`/UT 输出不能直接作为这个 trace 的评分输入。
