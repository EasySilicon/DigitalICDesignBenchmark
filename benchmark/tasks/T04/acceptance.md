# T04 · APB4 定时器

| 组 ID | 刺激与期望 | 关联分项 |
| --- | --- | --- |
| AC-16 | 四个偏移读写、保留位、PSTRB 组合、PPROT 各值以及 STATUS W1C | F 寄存器 |
| AC-17 | COUNT 从 3 到 0、LOAD 为 0/1/任意值、auto reload 开/关；对照逐拍模型 | F 计数 |
| AC-18 | pending 设置、保持、清除，irq_en 切换时 irq 组合响应 | F 中断 |
| AC-19 | setup 保持多拍不产生副作用；access 才提交；连续两笔 APB 不丢写 | P 总线时序 |
| AC-20 | 复位、未对齐/未知偏移、终点与 COUNT/STATUS 同沿写入的优先级 | P 边界 |

软件模型先根据沿前值计算 timer 变化，再按非零 `PSTRB` 的写入字节和 STATUS W1C 覆盖同名字段；零 `PSTRB` 写入不得阻止该沿的计数事件。变异体包含 setup 提前写、STATUS 写 0 清除、PSTRB 忽略、终点迟一拍、无效地址误答成功。
