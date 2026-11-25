# T10 v16 参考实现

v16 根据最新 AI 前沿能力更新参考实现，以获得更准确的 PPA 评估分数。
冻结材料包含四份 RTL 和 `rtl/files.f`；逻辑、流水线与接口按本版本固定。按
`evaluator/ppa_aggregate.py` 的 `source_hash()` 计算，源码身份为
`423e718efeec3f55f7f4857ee570df46f27584b090f0a133174e355c23e07670`；
逐文件 SHA-256 见 [`reference.json`](reference.json)。

该参考实现已有 V1 严格精度的 2,898 块功能验收、运行中复位和 256-PE 结构检查
通过记录。v16 继续使用 `exact-dot-v1`，不采用 MMA 放宽精度。

v16 作为[全设计成本与 PE 内部时序评测](../../../benchmark/tasks/T10/ppa.md)的参考：
面积计入全部外围单元和 256 个 PE 的实际叶单元；能耗使用相同的 200 块门级
激励，计入外围、PE 和输入负载充放电；时序只采用 PE 内部寄存器路径的
布线后 setup/hold，不混入外围或跨边界的理想连线时序。

外围采用映射后、引脚电容和零线长的功耗模型，没有全阵列 CTS 或布局布线。
三种子参考资格已由 `evaluator/t10_hybrid_measure.py` 核验，正式数值登记在
唯一的 [`benchmark/ppa-baselines.json`](../../../benchmark/ppa-baselines.json)
的 `tasks.T10`；原始证据保存在仓库外。参考自评分为 35/50，计分公式不变。
历史单 PE 成绩保持其原测量口径，不能与 v16 面积或能耗交叉归一化。
