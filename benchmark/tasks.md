# 任务卡：共享规则与任务索引

每项工作都要求 Agent 自行完成**可综合 RTL、自带验证环境、缺陷修复和 PPA 优化迭代**；交付格式、固定顶层名及评测方独立验收方式见[验证与交付契约](verification-contract.md)。每项的 F/P 子分合计 75，构成[功能正确性主指标](methodology.md#分层评分与排名)；正确的设计再进入[PPA 测量](ppa.md)，完成时间排最后。自带验证与可复现交付另设准入要求及诊断报告。接口名称和位宽是验收接口，不得擅改。原创题统一使用上升沿触发、异步低有效复位 `rst_n`（T06 为每时钟域各自复位）。所有 ready/valid 传输均以同一上升沿 `valid && ready` 为成功；发送方在 `valid && !ready` 时须保持 `valid` 与载荷，接收方可以改变 `ready`。测试仅驱动符合所写环境假设的输入。

每个任务目录中的 `task.md` 是该任务的冻结行为规范；本文件只保留跨题共享规则和任务索引。

| 任务 | 冻结任务卡 | 验收计划 |
| --- | --- | --- |
| T01 | [8 位串入并出寄存器](tasks/T01/task.md) | [T01 验收](tasks/T01/acceptance.md) |
| T02 | [SerDes RX comma aligner](tasks/T02/task.md) | [T02 验收](tasks/T02/acceptance.md) |
| T03 | [参数化同步 FIFO](tasks/T03/task.md) | [T03 验收](tasks/T03/acceptance.md) |
| T04 | [APB4 定时器](tasks/T04/task.md) | [T04 验收](tasks/T04/acceptance.md) |
| T05 | [轮询仲裁器](tasks/T05/task.md) | [T05 验收](tasks/T05/acceptance.md) |
| T06 | [异步 FIFO](tasks/T06/task.md) | [T06 验收](tasks/T06/acceptance.md) |
| T07 | [AXI4-Lite/APB4 桥](tasks/T07/task.md) | [T07 验收](tasks/T07/acceptance.md) |
| T08 | [直接映射写回缓存](tasks/T08/task.md) | [T08 验收](tasks/T08/acceptance.md) |
| T09 | [RV32I 五级流水线 CPU](tasks/T09/task.md) | [T09 CPU 验收](tasks/T09/acceptance.md) |
| T10 | [多精度脉动阵列矩阵乘法](tasks/T10/task.md) | [T10 验收](tasks/T10/acceptance.md) |
