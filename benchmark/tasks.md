# 任务卡：冻结行为规范

每项工作都要求 Agent 自行完成**可综合 RTL、自带验证环境、缺陷修复和 PPA 优化迭代**；交付格式、固定顶层名及评测方独立验收方式见[验证与交付契约](verification-contract.md)。每项的 F/P 子分合计 75，构成[功能正确性主指标](methodology.md#分层评分与排名)；正确的设计再进入[PPA 测量](ppa.md)，完成时间排最后。自带验证与可复现交付另设准入要求及诊断报告。接口名称和位宽是验收接口，不得擅改。原创题统一使用上升沿触发、异步低有效复位 `rst_n`（T06 为每时钟域各自复位）。所有 ready/valid 传输均以同一上升沿 `valid && ready` 为成功；发送方在 `valid && !ready` 时须保持 `valid` 与载荷，接收方可以改变 `ready`。测试仅驱动符合所写环境假设的输入。

## T01 · CVDP 8×3 优先编码器

**来源**：`cvdp_copilot_8x3_priority_encoder_0001`，类别 `cid003/easy`；使用[sources.lock.yaml](sources.lock.yaml)中锁定的原始题面。**交付**：可综合模块 `priority_encoder_8x3`、自检测试和运行脚本。

**接口与需求**：输入 `in[7:0]`，输出 `out[2:0]`；纯组合逻辑。`out` 等于最高置位输入的下标，优先级从 bit 7 降到 bit 0；输入为 0 时输出 0。不得引入时钟、状态或延迟。输入改变后的组合稳定值即为验收结果。

**资源边界**：无寄存器、RAM、ROM、黑盒或外部依赖。参考工具链下记录门数，但不按门数排名。

**验收与分值**：F=60：8 个单热输入 20；所有多热输入 40。P=15：零输入 10；同一次仿真中反复改变输入、无历史状态依赖 5。隐藏验收遍历全部 256 个输入，公开测试只放少量示例。原始 CVDP harness 作为兼容性检查；本题最终分数由本规范的完整真值表决定。

## T02 · CVDP 8 位串入并出寄存器

**来源**：`cvdp_copilot_serial_in_parallel_out_0004`，类别 `cid003/easy`；原始题面及 `docs/Documentation.md` 在锁定数据集中。**交付**：模块 `serial_in_parallel_out_8bit`、自检测试和运行脚本。

**接口与需求**：输入 `clock`、`serial_in`，输出 `parallel_out[7:0]`。每个 `clock` 上升沿执行 `parallel_out <= {parallel_out[6:0], serial_in}`；两沿之间保持。此题**没有复位端口**，因此上电后的前 7 次沿输出不验收；从第 8 次沿起，结果必须等于最近 8 个采样 bit，最早采样 bit 位于 bit 7。

**资源边界**：8 位状态寄存器；不得增加隐藏初始化端口、数据表或外部辅助模块。

**验收与分值**：F=60：首个完整 8-bit 字 20；连续至少 256 个采样 bit 的滑动窗口结果 40。P=15：只在上升沿采样 10；沿间输出保持 5。原始 CVDP harness 作为兼容性检查；隐藏验收避免对未规定的初始值打分。

## T03 · 参数化同步 FIFO

**设计需求**：单时钟顺序 FIFO，参数 `WIDTH` 与 `DEPTH`。端口：`clk,rst_n`；输入 `in_valid,in_data[WIDTH-1:0]`，输出 `in_ready`；输出 `out_valid,out_data[WIDTH-1:0]`，输入 `out_ready`。`DEPTH` 至少支持 3、8、16，`WIDTH` 至少支持 8、32。复位后空。存储容量恰为 `DEPTH` 项；写入按接受顺序读取。空时输入即使与 `out_ready` 同时出现，本周期 `out_valid=0`，新数据最早下一周期可读；无 fall-through。满时若同周期成功弹出，允许成功写入。`out_data` 在 `out_valid=0` 时不验收。

**环境假设**：输入方遵守 ready/valid 保持规则；`rst_n` 可在运行中异步拉低。成功写入定义为 `in_valid && in_ready`，成功读取定义为 `out_valid && out_ready`。输出载荷在阻塞期间稳定。

**资源边界**：不得超出 `DEPTH × WIDTH` 数据存储加有限指针/计数控制状态；不得借仿真队列实现 RTL。允许寄存器阵列或推断 RAM，禁止锁存器。

**验收与分值**：F=60：顺序与数据完整性 25；空/满和容量 15；满读写、普通同时读写 10；三组参数均有效 10。P=15：中途复位清空 5；输出阻塞保持 5；非 2 的幂深度回绕 5。隐藏随机流至少 10 万次成功事务，并用独立软件队列判定。

## T04 · APB4 定时器与中断外设

**设计需求**：32-bit APB4 从设备。端口：`clk,rst_n`、`PSEL,PENABLE,PWRITE,PADDR[11:0],PWDATA[31:0],PSTRB[3:0],PPROT[2:0]`；`PRDATA[31:0],PREADY,PSLVERR,irq`。本外设不做访问权限区分，合法 `PPROT` 值的功能相同。只接受 4 字节对齐地址，寄存器偏移如下。`PREADY` 在 `PSEL && PENABLE` 的 access 阶段为 1，其余为 0；一笔写入只在该阶段的成功上升沿生效。`PSLVERR` 仅在 access 阶段对无效地址或未对齐地址为 1；对合法地址的保留位写入被忽略。有效读的 `PRDATA` 是该沿前的寄存器值；无效读返回 0。

| 偏移 | 名称 | 行为 |
| --- | --- | --- |
| `0x000` | CTRL | RW，bit0 `enable`，bit1 `auto_reload`，bit2 `irq_enable`，其余读 0 |
| `0x004` | LOAD | RW，32-bit 装载值 |
| `0x008` | COUNT | RW，当前 32-bit 倒计数值；可由软件预装 |
| `0x00C` | STATUS | bit0 `pending`，读出；对 bit0 写 1 清除，写 0 不变 |

部分写按 `PSTRB` 逐字节合并；对 STATUS 只有 `PSTRB[0] && PWDATA[0]` 才清除。`irq = pending && irq_enable`。复位使所有寄存器为 0。每个非复位上升沿，如果沿前 `enable=1` 且 `COUNT>0`，`COUNT` 减 1；如果沿前 `enable=1` 且 `COUNT=0`，置 `pending=1`，`auto_reload=1` 时把 `LOAD` 写入 `COUNT`，否则清 `enable`。同一沿 APB 写入的字段优先于计数事件对**该字段**的更新；其余字段继续按沿前值运行。因此写 COUNT 会覆盖该沿的减 1，写 STATUS 清除会覆盖该沿的置 pending。

**资源边界**：四个寄存器及小型解码/计数逻辑；无 FIFO、ROM 或未声明等待状态。APB4 `PSTRB` 是规格的一部分，不以 APB3 替代。

**验收与分值**：F=60：寄存器读写与字节写 20；计数、终点和重装 20；中断及 W1C 20。P=15：setup/access 时序与 back-to-back 10；复位、非法地址和同时事件优先级 5。

## T05 · ready/valid 轮询仲裁器

**设计需求**：参数 `N=4/8`、`WIDTH=8/32`。端口：`clk,rst_n`，`in_valid[N-1:0]`、`in_ready[N-1:0]`、packed `in_data[N-1:0][WIDTH-1:0]`（第 `i` 个元素为第 `i` 路数据）；`out_valid,out_ready,out_data[WIDTH-1:0],out_id[$clog2(N)-1:0]`。逐**事务**仲裁，不能锁住一个输入通道直到它不再 valid。复位后搜索起点为 0；每次成功输出后，下次从刚服务的 `id+1` 环形搜索第一个 valid。无握手时起点不变。若已经选中且 `out_valid && !out_ready`，保持同一个 `out_id/out_data/out_valid` 直至握手；其他请求到达不得抢占。`in_ready` 仅在被选中且 `out_ready=1` 时为 1。

**环境假设**：每个输入源在其 `valid && !ready` 期间保持数据。输出接收方可任意背压；若 `out_ready` 永不为 1，不要求进展。无 `out_valid` 时 `out_data/out_id` 不验收。

**资源边界**：只允许一个仲裁指针和阻塞期间必要的持有状态；不得为每个输入私建数据 FIFO。无需吞吐缓存；无阻塞且有请求时，每周期可接受一笔。

**验收与分值**：F=60：请求选择 20；轮询顺序 20；数据/id 完整传输 20。P=15：阻塞稳定 10；持续请求在至多 `N` 次成功输出内得到服务 5。隐藏测试在 N=4/8 下混合独立输入、随机背压与长期竞争。

## T06 · 双时钟异步 FIFO

**设计需求**：参数 `WIDTH=8/32`、`DEPTH=8/16`，深度为 2 的幂。写域端口 `wr_clk,wr_rst_n,wr_valid,wr_ready,wr_data[WIDTH-1:0]`；读域 `rd_clk,rd_rst_n,rd_valid,rd_ready,rd_data[WIDTH-1:0]`。复位后空；按写入顺序输出，每项恰好一次。空时不做组合直通；读域在同步获知新写入后才允许 `rd_valid=1`。允许满/空状态保守延迟释放，但不得错收满写或错读空；当队列已有稳定写入且读时钟持续运行时，即使 `rd_ready=0`，最迟 200 个读域时钟内也须使 `rd_valid=1`。读域阻塞时保持 `rd_valid/rd_data`。写、读指针跨域使用 Gray 编码及每位至少两级目的域寄存器同步；多位数据只经双端口存储体传递，不能逐位 2FF 同步。复位必须同时异步拉低两个 `rst_n` 至少各两个本地域时钟，之后可分别释放；运行中重置遵循同一约定。

**环境假设**：两个时钟持续运行，周期、相位独立且可缓慢变化；输入遵守写域 ready/valid。存储体按一写端、一读端建模，禁止同地址未定义读写值被验收器使用。RTL 仿真不模拟模拟态亚稳态。

**资源边界**：容量恰为 `DEPTH × WIDTH`，指针及同步器为有限附加状态；不得使用异步组合多位指针跨域。只计功能/结构，不要求特定 FPGA RAM 原语。

**验收与分值**：F=60：顺序与恰好一次 25；满/空安全 15；快写慢读、慢写快读与相近频率 10；两组参数 10。P=15：双域复位及恢复 7；CDC 结构与 Gray 单步转换静态/断言检查 8。随机测试使用互质和动态变化的时钟周期，各不少于 10 万笔事务；CDC 结构检查是模拟测试的必要补充，但不宣称物理 CDC 签核。

## T07 · AXI4-Lite 到 APB4 桥

**设计需求**：一个时钟域，顶层输入包含 `clk,rst_n`；AXI4-Lite 32-bit 从接口连接 APB4 32-bit 主接口。AXI 端具有完整 `AWADDR[31:0]/AWPROT[2:0]/AWVALID/AWREADY`、`WDATA[31:0]/WSTRB[3:0]/WVALID/WREADY`、`BRESP[1:0]/BVALID/BREADY`、`ARADDR[31:0]/ARPROT[2:0]/ARVALID/ARREADY`、`RDATA[31:0]/RRESP[1:0]/RVALID/RREADY`；APB 端具有 `PADDR[15:0],PSEL,PENABLE,PWRITE,PWDATA[31:0],PSTRB[3:0],PPROT[2:0],PRDATA[31:0],PREADY,PSLVERR`。合法写把 `AWPROT` 传到 `PPROT`，合法读把 `ARPROT` 传到 `PPROT`。AW 与 W 可任意先后到达，各缓存一项，组成一笔写；AR 可独立缓存一项。每个方向最多一笔尚未返回的事务；APB 同时只能执行一笔。读写同时待发时按读写交替轮询，第一次优先写。APB 必须有至少一拍 SETUP，之后保持 ACCESS 到 `PREADY=1`，在等待期间控制、地址和写数据稳定。

**地址和响应**：合法 aperture 为 `0x0000_0000..0x0000_FFFF` 且 4 字节对齐；不合法请求不访问 APB，返回 AXI `DECERR`。合法 APB `PSLVERR=1` 映射为 `SLVERR`，否则 `OKAY`；出错读数据为 0。写 `WSTRB=0` 返回 `OKAY`，不访问 APB；其余写的 `PSTRB=WSTRB`。读时 `PSTRB=0`。B/R 响应在本端 ready 前保持 valid、resp、data 稳定。复位丢弃未完成请求和响应，不产生复位后的幽灵传输。

**环境假设**：AXI 主设备遵守各通道 valid 保持；APB 从设备最终给出 `PREADY`，可延迟 0–15 个 ACCESS 周期；在 `PREADY` 为 1 的 ACCESS 拍采样 `PRDATA/PSLVERR`。

**资源边界**：仅一深度 AW、W、AR 缓存和必要响应寄存器；不得引入大 FIFO、外部协议转换黑盒或改变总线语义。

**验收与分值**：F=60：写事务及字节使能 20；读事务及数据 20；OKAY/SLVERR/DECERR 映射 20。P=15：AW/W 任意先后及读写公平性 5；APB 等待与 AXI 返回背压稳定 5；复位清空 5。隐藏测试使用独立 AXI 主、APB 从记分牌和随机化时延。

## T08 · 256 B 直接映射写回数据缓存

**设计需求**：端口还包括 `clk,rst_n`。32-bit 地址/数据，16 条 cache line，每条 16 B、4 个 32-bit word，容量 256 B；直接映射，write-back、write-allocate、little-endian。CPU 侧：`req_valid,req_ready,req_addr[31:0],req_write,req_wdata[31:0],req_wstrb[3:0]`；`rsp_valid,rsp_ready,rsp_rdata[31:0]`。CPU 地址始终 4 字节对齐；读忽略 `req_wstrb`，写以每个字节 strobe 更新目标 word，写响应数据为 0。一次只接受一笔尚未响应完成的 CPU 请求，响应顺序与请求顺序一致。复位使所有 valid/dirty 位为 0；复位只在缓存空闲时施加，不要求清零数据阵列。复位前尚未写回的脏数据按丢弃处理；验收器在检查持久数据的场景里会先驱逐脏行，再施加复位。

**后端 line 接口**：`mem_req_valid,mem_req_ready,mem_req_write,mem_req_addr[31:0],mem_req_wdata[127:0]`；`mem_rsp_valid,mem_rsp_ready,mem_rsp_rdata[127:0]`。地址按 16 B 对齐；写请求为整行写回，读请求为整行回填；每个已接受请求恰有一个响应，写响应忽略数据。后端一次最多一笔未完成请求、按序返回且无错误，响应可能等待 0–7 周期；`mem_rsp_valid` 及数据保持至 `mem_rsp_ready` 握手。未命中且牺牲行为脏时先写回原行，再读新行；写未命中先回填再合并字节。命中不得访问后端；从接受 CPU 请求到给出 `rsp_valid` 不超过两个时钟周期（后端无关）。每笔被接受的 CPU 请求恰有一次响应。

**资源边界**：仅 16×128-bit 数据阵列、16 个 tag、valid/dirty 位及小型控制状态；不得绕过缓存直接把每个命中请求送到后端。不得引入额外被测容量或预取器。所有状态可综合。

**验收与分值**：F=60：读写命中 15；干净未命中与回填 15；脏行替换及写回地址/数据 15；部分写与 write-allocate 15。P=15：后端和 CPU 侧背压稳定 10；复位、命中时延与命中无后端流量 5。独立 byte-addressable 内存模型比对所有读结果和后端事务；仅在对各 index 的脏行执行冲突地址驱逐并等待全部响应后，才比对外部内存最终内容。

## T09 · RV32I 五级流水线 CPU

**设计需求**：单发射、顺序提交、32-bit RV32I 指令，明确分开的 IF/ID、ID/EX、EX/MEM、MEM/WB 四组级间寄存器；不允许以单指令多周期控制器冒充五级流水线。支持 RV32I 全部整数算术、逻辑、移位、分支、跳转、字节/半字/字访存、LUI/AUIPC、FENCE、ECALL、EBREAK；另支持 Zicsr 六种 CSR 操作及 MRET。无 M/A/F/D/C、无 MMU/缓存/中断，只有 M-mode。取指地址和访存地址按 ISA 要求检查对齐；不支持非对齐访存。`x0` 恒为 0。JALR 清目标 bit0。`FENCE` 对本题有序、一次一笔的数据端口无额外可见动作；`FENCE.I` 不支持并触发非法指令异常。

**复位与总线**：`clk,rst_n`，复位 PC=`0x8000_0000`。指令端 `imem_valid,imem_addr[31:0],imem_rdata[31:0]`；当周期的 `imem_valid/imem_addr` 在上升沿采样，下一周期给出对应 `imem_rdata`，每周期可接收一笔，响应严格顺序、无取指错误；没有前一周期有效请求时数据不验收。已发出的错误路径取指响应可以返回，但 CPU 必须丢弃。数据端 `dmem_req_valid,dmem_req_ready,dmem_req_write,dmem_req_addr[31:0],dmem_req_wdata[31:0],dmem_req_wstrb[3:0]` 与 `dmem_rsp_valid,dmem_rsp_ready,dmem_rsp_rdata[31:0],dmem_rsp_err`；每笔请求被接受后，在 1–8 周期内给一次保持型响应，单次只允许一笔未完成。数据端地址总是对齐的 32-bit word 地址：字节/半字访问由地址低位计算 byte lane、写掩码和放入对应 lane 的写数据；读响应返回完整 32-bit word，由 CPU 截取并符号扩展。非对齐访问须在发请求前报异常。错误响应表示该笔写入**没有内存副作用**。存储器与 CPU 一起复位，复位期间清空在途事务。指令、数据空间均指向外部 256 KiB 镜像；MMIO `0x8003_F000` 为 `tohost`，写入 1 表示程序通过，其余非零表示失败，CPU 不得硬编码此地址的行为。

**异常与 CSR**：非法指令、指令地址非对齐、load/store 非对齐、ECALL、EBREAK、数据端访问错误均为精确异常；faulting 指令不写回寄存器或内存，年轻指令全部冲刷。异常 `mcause` 编码：指令地址非对齐 0，非法指令 2，EBREAK 3，load 非对齐 4，load 访问错误 5，store 非对齐 6，store 访问错误 7，M-mode ECALL 11。若同一指令可能触发多个原因，先做地址对齐检查，再发总线请求，因此非对齐优先于访问错误。`mepc` 保存 faulting 指令 PC；`mtval` 对地址类异常保存故障地址，对非法指令保存 32-bit 指令编码，对 ECALL/EBREAK 为 0。

**CSR 的确切范围**：`mstatus(0x300)` 仅 MIE(bit3)、MPIE(bit7)、MPP(bits12:11) 可见；本题只有 M-mode，MPP 恒为 `2'b11`。复位值 `0x0000_1800`。进入异常时 `MPIE←MIE,MIE←0,MPP←3`；MRET 时 `MIE←MPIE,MPIE←1,MPP←3,PC←mepc`。`mtvec(0x305)` 仅 direct 模式，写入值低两位强制 0，复位值 `0x8000_0000`。`mscratch(0x340)`、`mepc(0x341)`、`mcause(0x342)`、`mtval(0x343)` 可读写，除 `mepc` 低两位强制 0 外复位为 0；只读 `misa(0x301)=0x4000_0100`、`mhartid(0xF14)=0`。其他 CSR 地址和对只读 CSR 的写操作触发非法指令异常；CSRRS/CSRRC 的源为 x0、立即数形式源为 0 时不写 CSR。所有未列的 `mstatus` 位读 0、写忽略。异常/CSR 编码遵循锁定的[RISC-V ISA/特权规范](https://github.com/riscv/riscv-isa-manual)；ACT4 配置必须与本任务范围一致。

**提交观察口**：每条正常退休指令输出一个周期的 `commit_valid,commit_pc[31:0],commit_insn[31:0],commit_rd[4:0],commit_wdata[31:0],commit_mem_addr[31:0],commit_mem_wstrb[3:0],commit_mem_wdata[31:0]`；无寄存器写回时 `commit_rd=0`，无存储写时 `commit_mem_wstrb=0`。异常事件输出独立 `trap_valid,trap_pc[31:0],trap_cause[31:0],trap_tval[31:0]`，不计为正常退休。这些是 CPU RTL 的轻量退休观察端口，供评测方自行采样；Agent **不需**生成 trace 文件或编写 trace 采集器。观察口只用于验收，不得成为执行功能的输入。

**取指至退休延时与资源边界**：寄存器文件仅 32×32 bit；程序/数据存储器均在核外。零等待、无相关的连续 64 条 ADDI 程序中，逐条记录取指请求被采样的上升沿 `n`；该指令须在 `n+4` 上升沿之后的稳定观察点输出 `commit_valid` 和对应 `commit_pc`。这表示从 IF 请求到 WB 观察跨越四个完整周期、经过 `n..n+4` 五个边沿；响应按本题一周期指令存储器时序提供。不得靠延迟 `commit_valid` 伪造流水级，后级的寄存器写回和存储器副作用也必须与提交轨迹一致。本门禁不作为 PPA 排名。实现须提供必要的旁路、load-use 停顿、分支/跳转冲刷、数据端等待停顿。无分支预测器、缓存、乘除法器或操作系统。

**验收与分值**：F=60：整数与控制流 25；大小端/字节使能、访存与符号扩展 15；CSR/异常/MRET 10；锁定配置的 ACT4 适用测试 10。P=15：数据相关与 load-use 6；随机数据等待及背压 5；冲刷、精确提交和取指至退休延时门禁 4。详细程序集、差分策略、超时与通过条件见[CPU 验收计划](cpu-validation.md)。ACT4 子集通过不等于 RISC-V 官方认证。
