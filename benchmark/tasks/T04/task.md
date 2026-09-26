# T04 · APB4 定时器与中断外设

**设计需求**：32-bit APB4 从设备。端口：`clk,rst_n`、`PSEL,PENABLE,PWRITE,PADDR[11:0],PWDATA[31:0],PSTRB[3:0],PPROT[2:0]`；`PRDATA[31:0],PREADY,PSLVERR,irq`。本外设不做访问权限区分，合法 `PPROT` 值的功能相同。只接受 4 字节对齐地址，寄存器偏移如下。`PREADY` 在 `PSEL && PENABLE` 的 access 阶段为 1，其余为 0；一笔写入只在该阶段的成功上升沿生效。`PSLVERR` 仅在 access 阶段对无效地址或未对齐地址为 1；对合法地址的保留位写入被忽略。有效读的 `PRDATA` 是该沿前的寄存器值；无效读返回 0。

| 偏移 | 名称 | 行为 |
| --- | --- | --- |
| `0x000` | CTRL | RW，bit0 `enable`，bit1 `auto_reload`，bit2 `irq_enable`，其余读 0 |
| `0x004` | LOAD | RW，32-bit 装载值 |
| `0x008` | COUNT | RW，当前 32-bit 倒计数值；可由软件预装 |
| `0x00C` | STATUS | bit0 `pending`，读出；对 bit0 写 1 清除，写 0 不变 |

部分写按 `PSTRB` 逐字节合并；`PSTRB=0` 的写入不更新任何寄存器，也不阻止同沿的计数事件；对 STATUS 只有 `PSTRB[0] && PWDATA[0]` 才清除。`irq = pending && irq_enable`。复位使所有寄存器为 0。每个非复位上升沿，如果沿前 `enable=1` 且 `COUNT>0`，`COUNT` 减 1；如果沿前 `enable=1` 且 `COUNT=0`，置 `pending=1`，`auto_reload=1` 时把 `LOAD` 写入 `COUNT`，否则清 `enable`。同一沿 APB 有非零字节使能的写入字段优先于计数事件对**该字段**的更新；其余字段继续按沿前值运行。因此非零 `PSTRB` 写 COUNT 会覆盖该沿的减 1，写 STATUS 清除会覆盖该沿的置 pending。

**资源边界**：四个寄存器及小型解码/计数逻辑；无 FIFO、ROM 或未声明等待状态。APB4 `PSTRB` 是规格的一部分，不以 APB3 替代。

**验收与分值**：F=60：寄存器读写与字节写 20；计数、终点和重装 20；中断及 W1C 20。P=15：setup/access 时序与 back-to-back 10；复位、非法地址和同时事件优先级 5。
