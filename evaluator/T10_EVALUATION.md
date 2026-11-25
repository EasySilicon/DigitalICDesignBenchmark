# T10 独立验收与测量

T10 通过题目固定端口检查数值、协议、结构和持续吞吐。验收器从候选的
`rtl/files.f` 加载源码，采用严格数值 oracle；评分规则见[任务验收计划](../benchmark/tasks/T10/acceptance.md)。

## 功能验收

```bash
python3 evaluator/runner_t10_stream.py /path/to/submission \
  --seed 11 --output-dir /path/to/scratch/T10_functional

PYTHONPATH=evaluator python3 -m unittest \
  evaluator.test_runner_t10_generation evaluator.test_t10_structure_check \
  evaluator.test_ppa_power_t10
```

`runner_t10_stream.py` 使用独立流式 testbench 和复位探针，覆盖完整矩阵结果、
双 1024-bit 输入、四槽输出、背压、块 ID、格式切换和持续吞吐。只有全部
数值、协议、结构、复位及吞吐检查通过时 CLI 才返回 0，并输出 `functional_passed`。
输出 JSON 保留分组计数、失败位置与结构结果。

`runner_t10.py` 提供公共向量生成和结果解析；`t10_fast_oracle.py` 使用精确
二进制数值计算，包含 MX scale 极值、溢出和抵消。`hidden/` 中的评测方
输入与 testbench 随完整仓库发布，由准备器隔离在候选工作区之外。
`t10_mutation_regression.py` 用于校准验收器的缺陷检出能力。

## v16 重评：全设计成本与 PE 内部时序

当前 T10 PPA 采用根据最新 AI 前沿能力更新的 v16 参考实现，精度仍为严格 V1。
面积和能耗覆盖全部外围与 256 个 PE；setup/hold 和延时只采用 PE 内部
寄存器路径的提取结果。[PPA 契约](../benchmark/tasks/T10/ppa.md)说明
外围零线长、理想顶层时钟及布局前功耗模型的边界。

```bash
python3 evaluator/t10_hybrid_measure.py --campaign /path/to/campaign.json

PYTHONPATH=evaluator python3 -m unittest evaluator.test_t10_hybrid_ppa
```

campaign 指定仓库外的 `output`、共享 `grade_lock`、`orfs`、可选
`compiler_root` 和 `jobs`。每个 job 显式绑定 `label`、
`model_dir`、`source_sha256`、`functional_report`、`shell` 和 `shell_proof`；
文件记录使用 `path/bytes/sha256`。`model_dir` 保留原始 submission 和三个
seed 的物理输入/完成记录。可用 `power_records` 按种子绑定已合格功耗，
以及 `peripheral_cache` 复用相同源码和映射网表的外围活动结果。
可选 `reference_measurement` 指向已完成、同口径的三种子参考测量。

新测量在独立本地副本中运行完整真实门级 DUT；复用前核对源码、网表、
工艺库、物理检查点、窗口和活动资格。输出分别保存 seed 测量、汇总、
分数和失败原因。普通工具失败保持待归因，不自动转成超时零分或重试。
正式参考已登记到 `benchmark/ppa-baselines.json` 的 `tasks.T10`。未指定
`reference_measurement` 或 `reference_label` 时，队列直接使用该权威基线；
通用 `score_run.py` 核对同一口径及逐种子成本账目后计分。模型成绩发布仍须
核对候选身份、完整测量和功能资格，不能将历史单 PE 结果套入新参考。

该入口通过 `t10_hybrid_scheduler.py` 为每份答卷派发独立的 40 GiB 评分
worker；控制进程不进入 worker 的资源组。worker 持有共享 EDA 锁，控制器
重启后接回原 worker，不重复启动。普通错误、超时、OOM 和报告解析失败
分别记录，单份失败不阻止后续派发。`queue_finished` 仅表示队列已走完；
只有每份答卷均有有效分数时 `all_scored` 才为真。八小时 worker watchdog
用于收回异常现场，触发时标为基础设施未完成，不按模型编译超时扣分。
PE 的 SS/TT Liberty 模型提取受上述 worker watchdog 保护，不再另设
15 分钟的导出上限；日志分别记录库、ODB、SDC、SPEF 读取和模型计算的
起止时间。该处理不改变物理实现和功耗编译预算，也不改变计分范围。

```bash
PYTHONPATH=evaluator python3 -m unittest evaluator.test_t10_hybrid_scheduler
```

已有全局布线检查点的 PE 可通过 `t10_route_resume.py` 在新实现目录继续详细
布线；续跑核对源码、种子、工具和检查点身份，保留此前累计物理时间。
降低布线线程数时记录实际并发，原资源上限不变，不能覆盖原失败现场。

## 历史单 PE 物理与功耗评估

[v1 参考后端](t10_backend/v1/README.md)用于复现冻结基线。候选流程由
`t10_candidate_physical.py`、`t10_power_with_slang.py` 和
`grade_t10_candidate_ppa.py` 完成；单 PE 测量的具体范围和约束见
[PPA 契约](../benchmark/tasks/T10/ppa.md)。

候选调度和发布使用显式 `--trial LABEL=TRIAL_DIR`，可重复指定多个候选。
`LABEL` 是安全的目录标签；trial 目录包含 `workspaces/T10/` 的原始交付、
开发计时文件，以及 `grading/T10/functional.json` 和 `delivery.json`。
该接口用于保留上述交付结构的 trial，不内置模型名单或本机历史目录。

这些工具保留用于复核匹配的历史冻结版本；当前检出的基线已改为 v16，
旧单 PE 入口会在执行测量前提示使用上面的 v16 campaign，避免按新参考
误算旧口径。历史原始报告及候选源码保持冻结。

## 参考资格

冻结功能与物理资格见 [t10_qualification.json](t10_qualification.json)，
正式参考值来自唯一的 [ppa-baselines.json](../benchmark/ppa-baselines.json)。
单 PE 的 PPA 资格与完整 DUT 的功能、结构及持续吞吐资格分别检查。
