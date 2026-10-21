# T10 独立验收包

本包提供 T10 的独立数值、协议、结构及持续吞吐验收。候选 DUT 从自身
`rtl/files.f` 加载，测试通过题目固定的顶层端口进行。

## 依赖与入口

依赖 Python 3.10+（标准库）、支持 SystemVerilog timing/assertions 与
hierarchical 编译的 Verilator、Yosys、C++ 编译器和 make。
工具安装方式见仓库的环境安装文档。模块路径按当前 checkout 自动确定。

```bash
# 独立结构检查，以及 2752 个连续输入/混合精度/背压用例与独立复位探针
python3 evaluator/runner_t10_stream.py /path/to/submission \
  --seed 20260925 --output-dir work/T10_qualification

# 功能试评分；PPA 由独立候选后端测量
python3 evaluator/grade_t10_pilot.py --help

# 固定 200-block 功耗工作负载；生成前验证 51200 个输出点均为有限结果
python3 evaluator/make_t10_power_vectors.py work/T10_power --seed 20260925

# 数值/协议/结构/持续吞吐/负载生成回归
PYTHONPATH=evaluator python3 -m unittest \
  evaluator.test_runner_t10_generation evaluator.test_t10_structure_check \
  evaluator.test_ppa_power_t10 -q
```

`runner_t10.py` 保留旧单块验收入口，主要为连续输入验收器提供矩阵生成和
结果解析；正式连续吞吐验证使用 `runner_t10_stream.py` 与 streaming/reset
两个独立 testbench。`t10_fast_oracle.py` 用整数和精确二进制有理数判定结果，
包含 MX scale 极值、溢出及异号抵消，不以参考 RTL 的输出作为 golden。

`grade_t10_pilot.py` 按公共计分规则汇总功能分。PPA/time 发布资格及持续吞吐
状态必须单独检查；其 pilot 报告不代表正式全量评分。候选测试失败仍保留
已完成用例的报告；基础设施失败、用例未完成与功能通过不得混淆。streaming CLI 仅在所有
数值/协议/结构/复位用例及持续吞吐均通过时返回 0，并输出 `functional_passed`。

`hidden/` 表示评测方拥有的测试资料；目录可以随评测仓库发布，但必须由
trial 准备流程排除在被测 Agent 的工作区之外。`t10_mutation_regression.py`
用于验证特定参考 RTL 的故障注入能否被独立验收捕获，不是候选结构门禁。

## PPA 测量与编译时限

新候选的功耗仿真编译受[所有题目统一的 20 分钟时限](../benchmark/power-compile-policy.md)
约束：每个布局种子的分层代码生成、C++ 编译、链接与 SAIF 运行库构建共用
1,200 秒预算。超时停止编译进程树，PPA/耗时加分归零，已验证的功能分保留；
环境错误和缺失记录不计作编译超时。`t10_candidate_power.py`、串行调度器
和结果发布器共同执行该规则。冻结的 v1 参考复现脚本不作历史性改写。

[v1 后端](t10_backend/v1/README.md)提供单 PE 三种子参考测量；
`t10_candidate_physical.py`、`t10_candidate_power.py` 与
`grade_t10_candidate_ppa.py` 负责候选物理、活动功耗和评分。完整 DUT 的
功能、结构及持续吞吐资格与单 PE 测量分别校验。正式结果基线见
[`ppa-baselines.json`](../benchmark/ppa-baselines.json)。

## 验证记录

[T10_PACKAGE_VERIFICATION.json](T10_PACKAGE_VERIFICATION.json) 记录独立入口的功能回归结果：2752 个用例、独立复位探针、256-PE
结构与 14 个无输入气泡阶段均通过，包含工具版本、RTL 与向量 SHA256。
该记录涵盖功能、结构与吞吐；物理及功耗资格由后端报告独立记录。
