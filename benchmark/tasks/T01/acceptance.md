# T01 · SerDes RX comma aligner

| 组 ID | 刺激与期望 | 关联分项 |
| --- | --- | --- |
| AC-05 | 初始错位 0–9；正/负 comma 的三符号训练可跨任意输入切片边界；接受第三个 comma 末 bit 后立即锁定 | F 训练锁定 |
| AC-06 | 锁定后输入多帧固定种子 payload；逐符号比较 bit 序、边界和完整性 | F 持续重组 |
| AC-07 | 混合极性训练、随机 `rx_valid` 间隙、所有初始相位与不含 comma 的 payload | F 相位与间隙 |
| AC-08A | 连续两个预期 marker 被替换或发生 bit slip 后及时失锁；任意新相位的三 comma 训练后重新锁定 | P 失锁与重锁 |
| AC-08B | 锁定、输出及重新训练期间异步复位；立即清除 `locked/symbol_valid`，释放后不得输出复位前残留符号 | P 复位 |

独立 oracle 维护串行 bit 队列、扫描窗口、训练相位和帧 marker，不读取 DUT 内部状态。变异体至少包括 bit 序反转、只扫描切片内 comma、锁定相位偏一、输出跨边界拼接错误、将 `rx_valid=0` 当作 0 bit、遗漏负 comma、marker 失配后不失锁。
