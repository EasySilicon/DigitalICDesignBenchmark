# T10 v15 单 PE 手工修复与检查

V1.0 的物理交付范围见[单 PE PPA 契约](../../benchmark/tasks/T10/ppa.md)。完整 DUT 的数值、结构、持续吞吐、背压和复位要求不变。这里保存 v15、seed 11 的定点修复与复核工具，不是适用于任意候选的自动修复器。其余历史实验及内部宏构建流程保留在 `systolic_burnish` 分支。

## seed 11 的历史修复结果

原版的 5 条宏边界金属间距违例已手工修复，未更改 RTL、逻辑连接、单元位置、宏形状、管脚或障碍物。仅 5 个网络的布线几何改变；修复网络的几何连通和端点覆盖均通过检查。

| 检查项 | 修复后结果 |
| --- | --- |
| 整个 PE 的有效 DRC | 0 |
| 提取后 setup / hold 最差裕量 | +22.243984 / +18.913870 ps |
| setup / hold TNS | 0 / 0 |
| 约束覆盖检查、天线检查 | 无报告项 |
| 总实例面积 | 60,069.8 µm²，未变 |

现有报告仍有 756 条最大转换时间违例；当前 Benchmark 的时序和几何门槛不等于全部电气规则、LVS 或量产签核通过。`power_vectorless.rpt` 没有活动注释，且宏内部功耗为 0，只能作为 PE 外层的诊断数据，不能用作完整单 PE 的功耗或正式分数。这份 seed 11 历史修复记录本身不是正式基线。2026-10-20，种子 11/29/47 已全部通过物理与正式活动功耗检查，详见[三种子测量、固定坐标修复及报告说明](v1/README.md)。机器记录见 [`t10_pe_manual_closure.json`](../t10_pe_manual_closure.json)。

## 658 条为什么是误报

“窗口”指检查器内部的分块，不是 PE 边界。固定版本 `TritonRoute::getDRCMarkers` 调用原生 `FlexGCWorker` 检查每个分块，却把该 worker 实际检查范围以外、上下文裁剪边缘产生的标记也收进报告。那些位置仍可能在 PE 内，不能让候选设计忽略它们所在的区域。

`physical/t10_manual_v15_gc_diag.cc` 保留相同工艺规则、导入几何、原生检查内核、网格及上下文，只在收集结果时要求标记与**产生它的 worker 的实际 DRC 范围**相交。该版本使用 15,376 个分块，检查范围向外扩展 500 nm，上下文扩展 4,000 nm；重叠的检查范围仍覆盖整个 PE。没有屏蔽任何网络、层或规则。

| 对照 | 原始全量标记 | 有效检查范围内标记 | 仅上下文标记 |
| --- | ---: | ---: | ---: |
| 原版 v15 | 663 | 5 | 658 |
| 手工修复版 | 658 | 0 | 658 |

未限定收集范围时，该工具生成的 `.raw` 报告与原生独立检查器报告逐字节一致。限定后，原版准确保留历史详细布线的 5 条违例；修复版为 0。两版剔除的 658 条标记集合完全一致，未新增标记。例如 `net13604` 某条所谓“间隙”位于导入后的完整 M2 矩形内部，局部完整上下文复查也为 0。

因此，**由评测器纠正报告收集范围，不给被测 Agent 区域豁免**。这份代码固定校验 v15 的网格，不能直接用于任意候选。通用评测器须按实际网格确保全覆盖，并对每个候选应用同一收集原则；不能拿这 658 条的数量或坐标作全局忽略清单。

## 核对已保存的报告

在仓库根目录执行，无须安装 OpenROAD：

```bash
python3 evaluator/t10_backend/physical/t10_manual_v15_compare_drc.py \
  evaluator/fixtures/t10_v15_manual/historical.drc.rpt \
  evaluator/fixtures/t10_v15_manual/original_full.drc.rpt \
  evaluator/fixtures/t10_v15_manual/repaired_full.drc.rpt \
  evaluator/fixtures/t10_v15_manual/original_scoped.drc.rpt \
  evaluator/fixtures/t10_v15_manual/repaired_scoped.drc.rpt
```

脚本验证原始报告仅相差那 5 条、原生报告复现一致、原版负对照为 5、修复版为 0，以及两版的上下文标记集合一致。小型原始报告、时序路径、连通与几何审计保存在 [`fixtures/t10_v15_manual/`](../fixtures/t10_v15_manual/)。较大的 ODB/SPEF 不放进 Git，机器记录保存其位置、长度和 SHA-256。

## 从历史检查点重新应用修复

需要 OpenROAD `26Q2-1164-g08f67ee5ec` 及其对应源码和 ABI 一致的依赖头文件，另需 C++20 编译器、Python 3、历史 ORFS 流程目录及其中的原始 v15 检查点、内部宏、库与日志。原始 route ODB 的 SHA-256 必须为 `76cb0aafa5ef8f94bbe7551314a90ab43426b1a8323a236023967c0481a7158b`；历史产物目前不是仓库内自包含下载包。

设置以下环境变量，再运行 `bash evaluator/t10_backend/physical/t10_manual_v15_reproduce.sh`：

- `T10_ORFS_FLOW`：保留原版 v15 的 ORFS `flow` 目录。
- `T10_OPENROAD_SRC`：与固定二进制匹配的 OpenROAD 源码目录。
- `T10_WORK_DIR`：新的输出目录；不要指向原始产物目录。
- `T10_THIRDPARTY_INCLUDE`、`T10_BOOST_INCLUDE`、`T10_ORTOOLS_INCLUDE`：匹配依赖的 include 目录。
- 可选 `OPENROAD`、`CXX`：二进制和编译器路径。

历史 `6_report.log` 中的库路径必须可访问。脚本编译三个修复插件和一个检查插件，应用定点修改，审计全部 60,651 个网络，检查修复网络的连通性，依次复核原版与修复版整个 PE 的 DRC，最后从原版 final 检查点应用相同修改，重新提取寄生参数并检查时序、约束覆盖和天线。它不会启动详细布线搜索，也不会修改历史检查点。完整检查耗时及内存较高；八线程串行处理两版以控制峰值。

修复方法：两处 VIA23 包围金属在保留完整切孔覆盖的前提下缩短；一处 VIA34/VIA45 接入改为局部低层绕接并补足最小面积；一处 VIA56 下层金属补成规则允许的矩形；一处 M7 整段移到已核对的空闲轨道。所有结果均由同一规则内核重新检查，不依赖人工豁免。
