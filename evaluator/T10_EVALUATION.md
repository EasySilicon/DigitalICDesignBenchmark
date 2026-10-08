# T10 独立验收包

本目录的验收包属于 `main`，不依赖 `systolic_burnish`、私有兄弟仓库、
本机绝对路径或参考实现的 16-tile 层次。候选 DUT 从自身 `rtl/files.f`
加载；测试通过题目固定的顶层端口进行。

## 依赖与入口

依赖 Python 3.10+（标准库）、支持 SystemVerilog timing/assertions 与
hierarchical 编译的 Verilator、Yosys、C++ 编译器和 make。
工具安装方式见仓库的环境安装文档。模块路径按当前 checkout 自动确定。

```bash
# 独立结构检查，以及 2752 个连续输入/混合精度/背压用例与独立复位探针
python3 evaluator/runner_t10_stream.py /path/to/submission \
  --seed 20260925 --output-dir work/T10_qualification

# 功能试评分（正式 routed PPA 基线尚未通过发布门禁）
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

## 后端的分支边界

`systolic_burnish` 的 `evaluator/t10_backend/` 提供实验物理流程、宏模型
生成/导出与参考层次组装。PE/tile Liberty、LEF、ODB 是这些流程的生成产物；
ASAP7 库本身不包含我们的自定义 PE/tile 宏。端到端物理流程及正式 PPA 基线
发布状态由该分支单独记录，不在本功能包提交中宣称收敛。
