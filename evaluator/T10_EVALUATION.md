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

## 单 PE 物理与功耗评估

[v1 参考后端](t10_backend/v1/README.md)用于复现冻结基线。候选流程由
`t10_candidate_physical.py`、`t10_power_with_slang.py` 和
`grade_t10_candidate_ppa.py` 完成；单 PE 测量的具体范围和约束见
[PPA 契约](../benchmark/tasks/T10/ppa.md)。

候选调度和发布使用显式 `--trial LABEL=TRIAL_DIR`，可重复指定多个候选。
`LABEL` 是安全的目录标签；trial 目录包含 `workspaces/T10/` 的原始交付、
开发计时文件，以及 `grading/T10/functional.json` 和 `delivery.json`。
该接口用于保留上述交付结构的 trial，不内置模型名单或本机历史目录。

```bash
python3 evaluator/run_t10_candidate_40g.py \
  --trial model-a=/path/to/trial-a --trial model-b=/path/to/trial-b \
  --work /path/to/fresh-measurements --orfs /path/to/OpenROAD-flow-scripts

# 只复核已有缓存并发布最终 summary；不启动 EDA
python3 evaluator/publish_t10_candidate_ppa.py \
  --trial model-a=/path/to/trial-a \
  --work /path/to/measurements --orfs /path/to/OpenROAD-flow-scripts --write
```

流程串行运行并记录实际资源使用。T10 每布局种子的物理实现累计限时
7,200 秒，功耗仿真编译另限 2,400 秒，编译预算覆盖规划、代码生成、C++
编译、链接和 SAIF 运行库构建。超时、普通工具错误和 OOM 分别保留证据，
基础设施错误保持待评；终态失败不会自动重试。完整规则见
[物理预算](../benchmark/physical-runtime-policy.md)和
[编译预算](../benchmark/power-compile-policy.md)。

发布器验证源码、缓存和测量来源，最终只更新模型的 `summary.json`；原始
报告和备份保存在调用者指定的测量目录。`--legacy-replay` 仅用于复核历史
测量记录，不放宽新候选的编译预算或交付检查。

## 参考资格

冻结功能与物理资格见 [t10_qualification.json](t10_qualification.json)，
正式参考值来自唯一的 [ppa-baselines.json](../benchmark/ppa-baselines.json)。
单 PE 的 PPA 资格与完整 DUT 的功能、结构及持续吞吐资格分别检查。
