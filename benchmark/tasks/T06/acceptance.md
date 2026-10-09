# T06 · AXI4-Lite/APB4 桥

| 组 ID | 刺激与期望 | 关联分项 |
| --- | --- | --- |
| AC-32 | 全 strobe/部分 strobe/零 strobe 写；APB 侧记录地址、数据、PSTRB、PPROT | F 写 |
| AC-33 | 读合法 aperture，APB 返回不同数据；AXI RDATA、PPROT、响应恰一次 | F 读 |
| AC-34 | 合法成功、PSLVERR、未对齐、越界分别映射 OKAY/SLVERR/DECERR；错误时无错误 APB 副作用 | F 响应 |
| AC-35 | AW 先 W、W 先 AW、同拍到达，夹杂 AR；服务顺序遵循轮询且不饥饿 | P 通道并发 |
| AC-36 | APB PREADY 延迟 0–15 拍，BREADY/RREADY 任意阻塞；所有等待期间载荷保持 | P 背压 |
| AC-37 | 在 AW 单独缓存、APB SETUP/ACCESS、响应阻塞中分别复位；释放后无幽灵事务 | P 复位 |

APB 从设备模型按 `PSEL && PENABLE && PREADY` 接受一笔，记录完整事务；AXI 主模型独立驱动五个通道。变异体包含假定 AW/W 同拍、SETUP 即提交、PSTRB 错映、响应被背压覆盖、PSLVERR 丢失。
