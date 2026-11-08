# 所有题目的功耗仿真编译时限

新候选评估按任务选择编译预算：

| 任务 | 每布局种子累计预算 | 政策 ID |
| --- | ---: | --- |
| T01–T09 | **1,200 秒（20 分钟）** | `power-compile-wall-1200s-v1` |
| T10 | **2,400 秒（40 分钟）** | `power-compile-wall-2400s-v2` |

- 每个种子的全部编译步骤共用该种子的一次累计墙钟预算，种子之间分别计时。
  预算覆盖分层规划、全部模块的 Verilator 代码生成、C++ 编译、链接和
  SAIF 运行库构建；多条命令共用一次预算，不能逐模块或逐命令重置。
- 超时即终止本次编译及其子进程，保留日志和 `power_compile.json`。
  任一种子超时，该题的 **PPA 分与耗时加分均为 0**，已验证的功能分保留；
  交付扣分仍按原规则计算。之后不再继续运行该提交剩余种子的功耗流程。
- 时限只约束收集功耗所需的编译，不包含综合、布局布线、工作负载仿真或
  OpenROAD 功耗计算，也不修改独立功能测试本身的编译/仿真时限。
- 缺工具、环境错误、普通编译报错、记录缺失或校验不通过，不计作编译超时。
  只有评测方生成、与任务、候选哈希及布局种子匹配的超时记录才可触发判零。

## 当前候选入口

T01–T07、T09 使用统一入口，原 `ppa_power_probe.py` 的其余参数原样转发：

```bash
python3 evaluator/power_probe_with_budget.py \
  --task T01 --candidate-source-sha256 <评测方计算的RTL哈希> --layout-seed 11 \
  --flow-result-dir <该种子的布线结果目录> --output-dir <功耗输出目录> \
  --vectors <向量文件> --case-count <数量> --testbench <评测方testbench> \
  --seed <工作负载种子>
```

T08 使用同一入口的 `--task T08` 分支，转发 `t08_power_probe.py` 的参数，
包括 `--sram-route`。`grade_t08_candidate_ppa.py` 已默认调用该入口；其隔离交付自检通过
`--runner-config` 读取与正式启动器相同的工具镜像和挂载配置，不再依赖历史模型启动脚本。

T10 的 `t10_candidate_power.py` 和串行评分调度器直接使用同一个预算实现。
统一入口也支持 `--task T10 --model-dir <候选评估目录> --orfs <ORFS目录>`；
此时 `--output-dir` 必须是该候选的 `activity_seed11/29/47`，且哈希必须匹配
目录中保留的原始提交。单 PE 测量与完整 DUT 的功能、吞吐和活动覆盖要求不变。

T01–T09 的新候选先通过 `aggregate_with_power_budget.py` 汇总物理、功耗和
编译记录，再通过 `score_with_power_budget.py` 评分。前者与旧聚合入口的
`TASK SUBMISSION --pair ROUTE_JSON POWER_JSON` 参数一致；编译超时时，即使
尚未生成功耗结果，也能根据同目录的 `power_compile.json` 汇总为判零记录。

```bash
python3 evaluator/score_with_power_budget.py --results <评测方评分输入.json>
```

评分输入沿用原有字段，另带 `candidate_source_sha256` 和
`power_compile_records`（读取各种子的 `power_compile.json` 后组成的列表）。
任何有效超时记录触发判零；正向 PPA 计分必须有种子 11/29/47 的成功编译记录，
T01–T09 的每条当前编译记录均不超过 1,200 秒，T10 不超过 2,400 秒。T10 的现行调度和发布入口单独校验相同记录。

T09 同时运行功能验收并计分时，使用 `check_t09_with_power_budget.py`，
其余参数与冻结功能入口一致，另用可重复的 `--power-compile-record` 传入记录。
没有功耗测量时可以只评功能；正向 PPA 计分不能省略三种子的编译记录。

T10 的两个候选调度入口均会在编译超时后停止该提交的剩余功耗种子。
当前评分与发布默认要求成功编译记录；只有显式指定 `--legacy-replay`
才能核验政策生效前的旧测量。历史重算工具保留旧记录的原政策；发现新政策
标记或编译记录时，必须校验并保留它们，不能把超时的 PPA/耗时加分重新加回。

## 与冻结材料和历史成绩的关系

旧 `ppa_power_probe.py`、`t08_power_probe.py`、`score_run.py` 和
`t10_backend/v1/` 保持字节不变，用于复现其哈希绑定的历史参考基线；
它们不是新候选评估的无时限替代入口。统一外层控制不会修改工作负载、
标准单元模型、仿真语义或旧测量数据。

历史运行按其原始政策 ID、预算和来源记录解释。已保存的 2,400 秒记录不被重新标成 1,200 秒，反之亦然；新编译由共享预算模块按任务选择时限。
