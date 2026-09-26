# T07 · AXI4-Lite 到 APB4 桥

**设计需求**：一个时钟域，顶层输入包含 `clk,rst_n`；AXI4-Lite 32-bit 从接口连接 APB4 32-bit 主接口。AXI 端具有完整 `AWADDR[31:0]/AWPROT[2:0]/AWVALID/AWREADY`、`WDATA[31:0]/WSTRB[3:0]/WVALID/WREADY`、`BRESP[1:0]/BVALID/BREADY`、`ARADDR[31:0]/ARPROT[2:0]/ARVALID/ARREADY`、`RDATA[31:0]/RRESP[1:0]/RVALID/RREADY`；APB 端具有 `PADDR[15:0],PSEL,PENABLE,PWRITE,PWDATA[31:0],PSTRB[3:0],PPROT[2:0],PRDATA[31:0],PREADY,PSLVERR`。合法写把 `AWPROT` 传到 `PPROT`，合法读把 `ARPROT` 传到 `PPROT`。AW 与 W 可任意先后到达，各缓存一项，组成一笔写；AR 可独立缓存一项。每个方向最多一笔尚未返回的事务；APB 同时只能执行一笔。读写同时待发时按读写交替轮询，第一次优先写。APB 必须有至少一拍 SETUP，之后保持 ACCESS 到 `PREADY=1`，在等待期间控制、地址和写数据稳定。

**地址和响应**：合法 aperture 为 `0x0000_0000..0x0000_FFFF` 且 4 字节对齐；不合法请求不访问 APB，返回 AXI `DECERR`。合法 APB `PSLVERR=1` 映射为 `SLVERR`，否则 `OKAY`；出错读数据为 0。写 `WSTRB=0` 返回 `OKAY`，不访问 APB；其余写的 `PSTRB=WSTRB`。读时 `PSTRB=0`。B/R 响应在本端 ready 前保持 valid、resp、data 稳定。复位丢弃未完成请求和响应，不产生复位后的幽灵传输。

**环境假设**：AXI 主设备遵守各通道 valid 保持；APB 从设备最终给出 `PREADY`，可延迟 0–15 个 ACCESS 周期；在 `PREADY` 为 1 的 ACCESS 拍采样 `PRDATA/PSLVERR`。

**资源边界**：仅一深度 AW、W、AR 缓存和必要响应寄存器；不得引入大 FIFO、外部协议转换黑盒或改变总线语义。

**验收与分值**：F=60：写事务及字节使能 20；读事务及数据 20；OKAY/SLVERR/DECERR 映射 20。P=15：AW/W 任意先后及读写公平性 5；APB 等待与 AXI 返回背压稳定 5；复位清空 5。隐藏测试使用独立 AXI 主、APB 从记分牌和随机化时延。
