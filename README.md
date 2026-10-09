# Digital IC Design Benchmark for Agents

[English](README.en.md)

**贴近数字芯片真实研发与交付流程的前沿模型能力评测。**

这套 benchmark 用来评测市面上流行的前沿模型，能否通过 coding agent 胜任数字芯片研发中的真实工作：在相同题面、工具、资源和开发预算下，交付**功能正确、可综合、有独立自检、经过 PPA 优化且可复现运行**的数字 IP。在此基础上，也可探索 Skill、多 Agent 编排、即时质量门禁等外部 harness 对模型最终表现的影响，并回归模型或系统版本的能力变化。

Agent 必须自行完成 RTL、验证环境、缺陷修复和 PPA 优化。评测方使用固定 DUT 端口和自己的参考模型重新验收；Agent 自报的 PASS、覆盖率或 PPA 报告不能直接成为评测分数。比较的优先级是 **功能正确性 → PPA → 完成时间**。

## 导航

- [设计出发点与评测哲学](#设计出发点与评测哲学)
- [题目与能力覆盖](#题目与能力覆盖)
- [已测模型与结果](#已测模型与结果)
- [环境准备](#环境准备)
- [推荐测试方式](#推荐测试方式)
- [如何验收与评分](#如何验收与评分)
- [目录与规范入口](#目录与规范入口)

## 设计出发点与评测哲学

这套 benchmark 的出发点是：**建立一套贴近数字芯片开发和交付真实业务流程的评测，检验市面上流行的前沿模型是否能胜任芯片研发中的真实工作。** 评测对象不只是模型能否写出一段 RTL，而是它能否理解需求、组织设计与验证、利用 EDA 工具分析问题、完成迭代优化，并交付可独立验收的工程产物。

因此，任务围绕工程闭环组织：**规格理解 → 架构与 RTL → 自建验证 → 缺陷定位与修复 → 时序与 PPA 优化 → 冻结交付**，既包含从零设计，也包含阅读、修复和扩展已有 RTL。我们关注的能力包括：

- **长上下文理解与需求分解**：从长规格、接口约定和已有 RTL 中提取要求，保持跨文件、跨模块约束的一致性。
- **逻辑电路与微架构设计**：正确实现状态机、流水线、缓存和协议控制，处理并发、背压、复位及参数化边界。
- **时序窗口与跨时钟域分析**：理解数据有效窗口、setup/hold 约束、同步器和 CDC 行为，区分逻辑正确与时序安全。
- **验证收敛**：建立独立参考模型与自检环境，覆盖 corner case、并发和性能要求，通过回归迭代发现并消除缺陷。
- **缺陷定位与存量工程修改**：定位低概率、跨模块耦合的错误；在修复缺陷和增加特性时保持既有行为与接口兼容。
- **时序收敛与性能权衡**：阅读时序报告、定位关键路径，调整逻辑和流水线，在满足周期与吞吐要求的同时改善时序。
- **物理实现与 PPA 优化**：使用综合、布局布线和存储宏，理解面积、功耗、时序及物理约束之间的权衡。
- **工具使用与工程交付**：正确组织 EDA 调用、诊断工具错误，管理时间和计算资源，交付可复现运行的 RTL、验证与脚本。

在模型能力评测的基础上，我们进一步探索：**Skill、多 Agent 编排、即时质量门禁等外部 harness，能在多大程度上提高前沿模型或性价比模型在数字芯片研发任务上的最终表现？** 这些机制是可选的实验变量，不是参加 benchmark 的前提。其作用应通过相同任务和受控条件下的对比来验证，而不预设某种架构必然更优；除最终质量外，也应观察取得改善所需的时间、推理费用和计算资源。

我们据此采用以下设计原则：

1. **以完整交付为评测单位。** 题面同时约束行为、接口、资源和交付方式。Agent 要交付可综合 RTL、自己编写的验证环境和可执行复现入口，并承担调试与优化工作。一次运行以最终冻结的工程快照验收，过程中做出的承诺和自报结果需要实际产物验证。

2. **正确性优先，随后优化物理成本，最后比较速度。** 功能错误在对应验收项记录失败，并阻止该题获得 PPA/时间排名资格，内在原因是如果功能未实现正确，再好的PPA也是空中楼阁，这是避免PPA畸形激励的方式。部分功能分保留用于诊断能力短板。功能全过后，比较统一流程下的面积、布线后延迟和能耗；在相近的 PPA 档位内，再比较完成时间。这体现了芯片工程中先满足规格、再满足成本与效率目标的顺序。

3. **验收独立，实现保留自由度。** 固定 DUT 接口、协议和题卡明确的架构边界；允许不同 RTL 写法、合法微架构和验证框架。评测方从端口事务与独立模型判断行为，必要的 CDC/脉动结构要求由自动网表规则检查。Agent 自带 UT 用来检验其验证交付能力，功能评分由评测方独立取得，因此不同系统可以采用各自的工程方法。

4. **质量门禁必须可执行、可追溯。** 每个要求应映射到验收组，每次失败应能追溯到种子、输入、期望值和实际值。验收器自身通过正确参考回归和已知缺陷变异体校准；评分脚本按冻结规则运行。题面、验收器或工具缺陷要单独归因，修正后对受影响的冻结提交统一重评，避免把评测系统的问题算到候选头上。

5. **PPA 衡量完整设计的代价。** 参考基线与候选采用一致的工艺、约束、活动负载和测量流程。输入传输、控制、缓存、输出与实际互连均计入完整 DUT 的成本，PE 或其他子模块的结果用于定位和优化。测量目标是可复现的相对 PPA，参考实现的交付范围由 benchmark 发布门禁确定。

6. **外部 harness 的收益必须通过受控对比验证。** Skill、编排策略和即时质量门禁应作为明确的实验变量。多 Agent 系统的所有内部角色共享时间、token、费用和计算资源预算，推理、验证和 PPA 迭代都计入开发时间。同模型控制轨道用于分析 harness 的影响；产品轨道用于比较模型与系统的实际使用效果。多次独立运行、通过率、耗时和成本共同构成证据，模型配置与预算差异必须随结果记录。

7. **用领域覆盖和工程耦合构造难度。** 题目涵盖状态控制、参数化、协议、CDC、缓存、流水线与空间阵列；难度来自边界条件、并发状态、数值语义和跨模块约束。通过不同规模的任务观察系统在哪些课题上可靠、在哪些课题上失效，再用试运行数据校准难度与预算。题量保持精简，使整套实验能够反复运行。

8. **开放材料，隔离试做，保留复现证据。** 公开规格、验收源码、参考实现与测量配置，使结果可以审计；试做时只向候选提供该题允许的材料，隔离答案和历史提交。记录版本、工具、种子、文件哈希和分项结果，并明确区分已判失败、尚待测量与基础设施异常。其他团队应能用相同条件复测并解释分数。

9. **题目与工艺材料自包含。** 本仓库已包含 T01–T10 的题面、验收计划、公开测试、独立验收代码与数据、评测配置，以及已完成的参考基线。ASAP7 的 Liberty、LEF、GDS、门级仿真模型及布线/寄生规则也已随仓库提供，附有来源、许可证和文件哈希；用户无需再下载 ASAP7 工艺包或标准单元 library。工艺输入直接从仓库读取，参赛所需公开材料由任务准备器复制到独立工作区。Verilator、Yosys、OpenROAD、ORFS 和 CPU 工具链按安装说明预装并锁定版本；模型 API 调用按实验轨道的网络策略配置。

我们希望最终报告能说明模型在真实芯片研发任务中的**能力边界、可靠交付能力、优化能力及工程成本**，并为模型选择和外部 harness 的设计提供可验证的依据。完整实验约定见 [评测与评分方法](benchmark/README.md#评测与评分方法)。

## 当前状态

当前主套件是 `ic-delivery-rtl-v0.3`，包含 **T01–T10 十道题**，仍处于预发布 `design_only` 状态。

| 范围 | 已具备的能力 | 尚待完成 |
| --- | --- | --- |
| T01–T09 | 任务规格、公开冒烟、独立验收器、参考 RTL、缺陷变异体，以及本地校准的三种子 1 GHz PPA 基线 | 统一工具镜像与整套发布证据冻结 |
| T10 | 持续流多精度矩阵验收、精确数值 oracle、复位/背压/吞吐检查、自动 PE 网格检查 | 完整 DUT 的正式三种子 PPA 基线；当前只报告功能试评分 |

T10 最近一次公开验收包复测通过 **2,752 个矩阵块、独立复位探针、256-PE 结构检查和 14 个无输入气泡阶段**，记录见 [T10_PACKAGE_VERIFICATION.json](evaluator/T10_PACKAGE_VERIFICATION.json)。这份记录证明功能验收包可运行，不代表完整物理基线已发布。

## 题目与能力覆盖

题目由基本时序逻辑逐步扩展到协议、跨时钟域、存储层次、CPU 和 NPU。每题都有明确需求、接口、资源约束、验收组和计分映射；点击题目查看完整题面。

| ID | 任务 | 主要 IC 设计领域 | 重点考察能力 | 开发时限 | 套题显示分权重 |
| --- | --- | --- | --- | ---: | ---: |

| T01 | [SerDes RX comma aligner](benchmark/tasks/T01/task.md) | 串行链路 PCS 与符号同步 | 跨切片 bit 窗口、对齐训练、字重组、失锁/重锁 | 30 分钟 | 3% |
| T02 | [参数化同步 FIFO](benchmark/tasks/T02/task.md) | 流式缓冲与存储 | ready/valid、同拍读写、空满边界、非 2 次幂回绕 | 60 分钟 | 3% |
| T03 | [APB4 定时器外设](benchmark/tasks/T03/task.md) | 寄存器外设与控制状态机 | APB 时序、字节写、W1C、中断和事件优先级 | 90 分钟 | 6% |
| T04 | [ready/valid 轮询仲裁器](benchmark/tasks/T04/task.md) | 多端口流控与资源调度 | 公平性、持续竞争、背压下数据保持、参数化 | 90 分钟 | 6% |
| T05 | [异步 FIFO](benchmark/tasks/T05/task.md) | CDC、双时钟缓冲与复位 | Gray 指针、双级同步、保守空满判断、跨域恢复 | 120 分钟 | 6% |
| T06 | [AXI4-Lite 到 APB4 桥](benchmark/tasks/T06/task.md) | 片上互连与协议转换 | AW/W 解耦、读写并发、等待、响应背压和错误映射 | 120 分钟 | 10% |
| T07 | [直接映射写回数据缓存](benchmark/tasks/T07/task.md) | 存储层次 | tag/index、脏行替换、写分配、字节使能、双侧背压 | 120 分钟 | 10% |
| T08 | [1GbE MAC 缺陷修复与 VLAN 准入](benchmark/tasks/T08/task.md) | Brownfield Ethernet MAC | Corner-case repair, VLAN admission, long specification | 120 min | 11% |
| T09 | [RV32I 五级流水线 CPU](benchmark/tasks/T09/task.md) | RTL design / verification | Frozen task-specific acceptance | 120 min | 20% |
| T10 | [多精度脉动阵列矩阵乘法](benchmark/tasks/T10/task.md) | RTL design / verification | Frozen task-specific acceptance | 240 min | 25% |

T10 计算 `16×64` 与 `64×16` 矩阵乘法，A/B **各每拍输入 1024 bit**；支持 INT8、INT16、FP16、BF16、FP8 E4M3/E5M2、FP4 E2M1、MXFP8 E4M3/E5M2 和 MXFP4。要求连续块流水，不能用单块突发带宽代替持续吞吐。

横向工程能力贯穿所有题目：读懂规格、设计可综合 RTL、建立独立 scoreboard、处理边界与复位、定位缺陷、测量并优化 PPA，以及交付可重复运行的工程。难度序号是设计假设，实际难度仍需通过预算内通过率和完成时间校准。

新 T08 已纳入主套件，考察长规格、既有 RTL 修复和新增特性。

## 已测模型与结果

下表来自 [2026-10-09 逐题评测结果](results/model-score-comparison.md)。各模型采用基本一致的时间预算与 Skill 设置，结果按统一评分规则汇总，用于比较功能正确性、PPA 和完成效率。表中小计仅包含已评分分项，尚未测量的部分明确标注。

| 模型 | 功能全通过 / 已验收题数 | 已评分部分的加权显示分 /105 | 结果文件 |
| --- | ---: | ---: | --- |
| GPT-6-Astra | 9/9 | 65.40 | [summary.json](results/gpt-6-astra/summary.json) |
| GPT-6.1-Sol | 9/9 | 64.25 | [summary.json](results/gpt-6.1-sol/summary.json) |
| GPT-6-Sol | 9/9 | 63.78 | [summary.json](results/gpt-6-sol/summary.json) |
| Kimi K3 | 7/10 | 58.94 | [summary.json](results/kimi-k3/summary.json) |
| DeepSeek Flash | 7/9 | 47.30 | [summary.json](results/deepseek-flash/summary.json) |
| GLM-5.3-Flash | 6/10 | 41.41 | [summary.json](results/glm-5.3-flash/summary.json) |

三个 GPT 模型的 T10 当前只计功能 50 分，PPA/时间为待评项；因此表中总分是已评分部分的小计。**`null` 表示尚无测量结论，`0` 表示已判失败**，两者不能混用。缺失分项不计入小计，也不重新放大其余题目的权重。GLM 等运行的合并重评和罚分调整以快照中的逐项说明为准。

结果分类、字段和可排名条件见 [结果归档说明](results/README.md) 与 [结果 schema](results/result.schema.json)。比较前须核对 `scoring_policy`、题面版本、实际时限和工具配置。

## 环境准备

功能验证和 PPA 评测采用开源工具，**不需要商用 EDA 许可**。ASAP7 平台已放在 [vendor/asap7/](vendor/asap7/)，自定义 PE/tile 宏模型则由后端流程生成。

| 用途 | 主要依赖 |
| --- | --- |
| 规范与报告校验 | Python ≥3.10、PyYAML、jsonschema |
| RTL 编译、仿真与结构检查 | Verilator、Yosys、C++ 编译器、make；部分独立验收器还调用 Icarus Verilog 的 `iverilog`/`vvp` |
| PPA | Yosys、OpenROAD、OpenROAD-flow-scripts（ORFS）、仓库内 ASAP7；时序/功耗由 OpenROAD 流程报告 |
| CPU 测试生成与参考校验 | RISC-V 裸机工具链、Sail、锁定的 ACT4/riscv-arch-test；仓库也提供已生成 ELF |
| Agent 自带验证 | 可选 SystemVerilog/UVM、SVA、cocotb 或 C++；所用语法须在实际工具版本验证 |

从仓库根目录开始：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r env/requirements-spec.txt
source .venv/bin/activate
python3 env/check_env.py --profile spec
python3 benchmark/validate_spec.py
```

这只安装规范校验的 Python 依赖。完整工具安装、锁定源码和 ORFS 兼容补丁见 [安装与依赖清单](env/README.md)。工具安装后，可检查功能环境和物理环境：

```bash
python3 env/check_env.py --profile functional
python3 env/check_env.py --profile ppa \
  --orfs-root third_party/OpenROAD-flow-scripts --verify-platform-hashes
```

默认评测资源为 **16 vCPU、32 GiB RAM、100 GiB 可写盘**，模型 token 与开发时限见 [manifest.yaml](benchmark/manifest.yaml)。大型仿真/物理构建建议把 `TMPDIR` 和 ORFS 工作树放到有足够空间的数据盘；依赖自检通过后仍需运行实际参考冒烟，确认版本兼容。

## 推荐测试方式

### 方式一：验证已有 RTL 或检查评测环境

适合 IP 开发者、验收器维护者和 CI 回归。提交目录应有符合题卡的 `rtl/files.f` 和顶层接口。在评测仓库根目录运行，例如 T03：

```bash
# 对已有提交做公开端口冒烟
python3 evaluator/public_check.py T03 /path/to/submission

# 独立功能验收与 Agent 自带自检的交付检查分别运行
python3 evaluator/t03_check.py /path/to/submission
python3 evaluator/delivery_check.py T03 /path/to/submission

# 用评测方参考 RTL 检查验收环境
python3 evaluator/t03_check.py --reference
```

公开冒烟用于快速定位接口或基础行为问题；独立验收提供分组结果；交付检查验证提交者的 `run.sh` 是否可运行。**命令退出成功不一定表示所有功能组通过**，须读取各组 `cases_passed/cases_total` 并交给评分器汇总。

T09 和 T10 有专用入口：

```bash
# SECONDS 应替换为候选从领取任务到冻结提交的实际秒数
python3 evaluator/t09_check.py /path/to/cpu --elapsed-seconds SECONDS

# T10 同时检查数值、连续吞吐、结构、背压和复位
python3 evaluator/runner_t10_stream.py /path/to/npu \
  --output-dir work/T10-acceptance
```

T09 的交付检查还包括 `run.sh --elf` 能力；逐指令 trace 由评测方平台采集，Agent 无需编写 trace 文件生成器。更多入口见 [评测器说明](evaluator/README.md) 和 [T10 验收包说明](evaluator/T10_EVALUATION.md)。

### 方式二：单题 Agent 试做

适合先测试一个模型、coding agent 或系统接入。准备一个**空的独立目录**：

```bash
python3 benchmark/prepare_trial.py T03 work/trials/my-system/run-01/T03
```

1. 在生成目录启动一个新 Agent 会话，将 `PROMPT.md` 作为任务输入；该目录只提供题面、公开冒烟和必要的公开材料。
2. 记录任务发放时刻，运行至 Agent 提交最终快照或题目截止；保留模型配置、token、成本、日志和最终文件 hash。
3. Agent 在时限内完成 RTL、自建验证和 PPA 探索，反复自检。推理、协作、编译、仿真和优化都计入开发时间。
4. 冻结提交后，由评测方在完整评测环境中运行独立验收、交付检查和可用的 PPA 流程；评测运行时间不计入候选完成时间。

正式比较应使用容器或等效权限边界，阻止候选访问宿主仓库的参考 RTL、独立验收器和其他提交。源码可以公开，但不进入被测 Agent 的工作区；仅创建新目录不能替代访问隔离。

### 方式三：整套重复横评或自动化实验

适合模型对比、多 Agent 系统实验和版本回归。首先批量生成任务工作区：

```bash
for task in T01 T02 T03 T04 T05 T06 T07 T08 T09 T10; do
  python3 benchmark/prepare_trial.py "$task" "work/trials/my-system/run-01/$task"
done
```

随后由你的 Agent CLI/API 或系统 runner 逐题消费 `PROMPT.md`，每题使用新会话和独立产物。仓库提供材料准备、验收和评分工具；模型调用、容器启动、计时及日志收集需由实验 runner 对接。

- **产品轨道**：比较各系统的原生模型与工程能力，冻结费用、时限和计算资源。
- **同模型控制轨道**：使用相同模型快照、采样配置、API 与总 token 预算，比较编排和工程流程。
- **重复运行**：主套件配置为每题至少 5 次独立试做，固定相同的验收种子，报告逐题通过率、中位数、耗时和成本，不只挑最好的一次。

当前准备器生成的是单 Agent 试跑 prompt。测试多 Agent 系统时，评测方须预先冻结并配置相应的协作、模型和 Skill 策略；所有内部角色共享同一题的时间、token 和计算资源预算。产品轨道与控制轨道分别报告，不能混成同一个榜单。完整实验规则见 [评测与评分方法](benchmark/README.md#评测与评分方法)。

## 如何验收与评分

### 提交契约

每题需要交付：

```text
submission/
├── rtl/             # 可综合 RTL；固定顶层和题卡接口
│   └── files.f      # 相对 rtl/ 的源码清单
├── verif/           # Agent 自建的可执行自检
├── run.sh           # 无交互入口；支持 BENCH_SEED
├── results.json     # 由实际自检生成的结构化结果
└── README.md        # 运行方法、验证范围、限制和 PPA 探索记录
```

`run.sh` 必须真实比较期望值与实际值，失败返回非零；相同种子应得到可重现结果。自带验证框架和内部 RTL 层次可以不同，验收接口固定。完整约定见 [验证与交付契约](benchmark/README.md#验证与交付契约)。

### 评测方的验收链

| 环节 | 检查内容 | 判定依据 |
| --- | --- | --- |
| 交付检查 | 文件、接口、自检入口、可重复运行、T09 ELF 加载、PPA 探索记录 | 提交契约；自带 UT 的运行结果不作为 RTL 正确性 oracle |
| 独立功能验收 | 定向边界、固定种子随机流、协议/复位/延时、CPU 架构与提交差分、NPU 精确数值 | 评测方 testbench 和独立行为模型，通过固定 DUT 端口观察 |
| 自动结构检查 | T05 双级同步链，T10 PE 邻接网格、局部累加和资源边界 | Yosys 网表规则；T09 通过取指至退休延时、相关与冲刷检查可观察流水线行为 |
| 验收器质量校准 | 正确参考必须通过，已知缺陷变异体应被检出 | 参考回归与缺陷注入；候选自带 UT 的变异检出率另作诊断 |
| 统一 PPA 重测 | 面积、布线后延迟与每有用操作能耗 | Yosys + ASAP7 + OpenROAD，固定工艺、约束、活动负载和三个布局种子 |

逐提交的功能和结构判分由脚本完成，不依赖人工双人复核。参考 PPA 基线可以在发布前工程复核。CPU 使用 ACT4/Sail 加题卡专项测试；ACT4 不替代总线、异常与流水线验收。NPU 覆盖所有要求格式，包括 MX 极值 scale、溢出与异号抵消。

### 分数与排序

当前计分配置见 [score_rules.json](evaluator/score_rules.json)，基线的唯一权威入口是 [ppa-baselines.json](benchmark/ppa-baselines.json)。

| 指标 | 显示分上限 | 条件与含义 |
| --- | ---: | --- |
| 功能正确性 | 50 | 题卡 F=60/P=15 是原始权重，按 `50/75` 归一；P 包括边界、协议、结构和题卡性能要求 |
| PPA | 50 | 功能全过且测量来源有效时启用；面积/延迟/能耗相对冻结参考归一，参考实现为 35/50 |
| 完成时间 | 5 | 功能全过且 PPA 有效；`5 × (1 − t/T_max)`，裁剪到 0–5 |

单题按 **功能分、PPA 分档、完成时间**依次排序。套题先看功能全通过题数和功能总分，再看 PPA，最后看归一化完成时间。105 分显示分与上述加权小计用于展示，不取代分层排序。

统一物理目标为 **ASAP7、1 GHz（1000 ps）**，布局种子为 `{11,29,47}`，有效活动标注率至少 95%。参考基线必须满足 setup/hold 且 DRC 为零。候选完成布线后的 setup/hold 违例按连续惩罚计分，存在 DRC 时乘 0.5；不能把任何负 WNS 都直接当成 PPA 零分。无法合法完成布线或取得有效活动测量的候选失败另行判定。具体公式与测量参数见 [PPA 测量与评分](benchmark/README.md#ppa-测量与评分)。

`ppa_probe.py` 提供物理探测，`ppa_power_probe.py` 提供门级活动功耗，`ppa_aggregate.py` 聚合三种子记录；最终由 `score_run.py` 读取**评测方生成**的组结果和测量，不读取候选自报分数。缺少合格基线记待评，工具/验收器故障修复后对冻结提交重评；独立裁定的候选失败记 0。候选原因的致命交付错误按独立根因扣显示分 5 分，保留已验证的分项成绩。

## 目录与规范入口

| 位置 | 用途 |
| --- | --- |
| [benchmark/README.md](benchmark/README.md) | 跨题规则、资源、完整验收/计分/PPA/覆盖与发布要求 |
| [benchmark/tasks/](benchmark/tasks/) | 每题 `task.md`、`acceptance.md`、`task.yaml` 和 `public/` |
| [benchmark/manifest.yaml](benchmark/manifest.yaml) | 套件任务、时限、token、资源与评分配置 |
| [evaluator/](evaluator/README.md) | 公开冒烟、独立验收、结构检查、交付检查和评分工具 |
| [results/](results/README.md) | 模型试跑说明、逐题成绩与机器可读归档 |
| [env/](env/README.md) | 依赖安装、自检与工具兼容补丁 |
| [vendor/](vendor/README.md) | ASAP7 平台、来源、许可证与文件哈希 |

任务行为以各题 `task.md` 的明确规定为准，公开冒烟只是示例。历史试跑记录不能覆盖当前题面或评分策略。`main` 承载通用规范与验收工具；`systolic_burnish` 保存 T10 实验后端流程、参考宏构建与物理诊断，说明见该分支的 `evaluator/t10_backend/README.md`。

## 许可证与来源

本仓库自有代码与文档采用 [Apache-2.0](LICENSE)。ACT4、ASAP7 和实验 starter 等第三方材料适用各自许可证，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；锁定修订与来源记录见 [sources.lock.yaml](benchmark/sources.lock.yaml)。本 benchmark 评估数字 RTL 交付与公开预测工艺上的相对 PPA，不声称真实流片签核或正式 RISC-V/以太网认证。

T08/T09 task-level freeze (2026-10-09): [T08 receipt](benchmark/tasks/T08/FREEZE.json), [T09 receipt](benchmark/tasks/T09/FREEZE.json). Run `python3 benchmark/freeze_tasks.py` from the repository root to verify specification, RTL, judge, scoring, baseline and portable evidence hashes. All six T09 archives have been regraded; untested T08 models remain null. Host-only receipts are excluded from candidate packages. T10 PPA and the suite-wide tool-image/release gates remain pending.
