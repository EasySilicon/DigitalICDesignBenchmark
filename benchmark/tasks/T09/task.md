# T09 · RV32I 五级流水线 CPU

**设计需求**：单发射、顺序提交、32-bit RV32I 指令，明确分开的 IF/ID、ID/EX、EX/MEM、MEM/WB 四组级间寄存器；不允许以单指令多周期控制器冒充五级流水线。支持 RV32I 全部整数算术、逻辑、移位、分支、跳转、字节/半字/字访存、LUI/AUIPC、FENCE、ECALL、EBREAK；另支持 Zicsr 六种 CSR 操作及 MRET。无 M/A/F/D/C、无 MMU/缓存/中断，只有 M-mode。取指地址和访存地址按 ISA 要求检查对齐；不支持非对齐访存。`x0` 恒为 0。JALR 清目标 bit0。`FENCE` 对本题有序、一次一笔的数据端口无额外可见动作；`FENCE.I` 不支持并触发非法指令异常。

**复位与总线**：`clk,rst_n`，复位 PC=`0x8000_0000`。指令端 `imem_valid,imem_addr[31:0],imem_rdata[31:0]`；当周期的 `imem_valid/imem_addr` 在上升沿采样，下一周期给出对应 `imem_rdata`，每周期可接收一笔，响应严格顺序、无取指错误；没有前一周期有效请求时数据不验收。已发出的错误路径取指响应可以返回，但 CPU 必须丢弃。数据端 `dmem_req_valid,dmem_req_ready,dmem_req_write,dmem_req_addr[31:0],dmem_req_wdata[31:0],dmem_req_wstrb[3:0]` 与 `dmem_rsp_valid,dmem_rsp_ready,dmem_rsp_rdata[31:0],dmem_rsp_err`；每笔请求被接受后，在 1–8 周期内给一次保持型响应，单次只允许一笔未完成。数据端地址总是对齐的 32-bit word 地址：字节/半字访问由地址低位计算 byte lane、写掩码和放入对应 lane 的写数据；读响应返回完整 32-bit word，由 CPU 截取并符号扩展。非对齐访问须在发请求前报异常。错误响应表示该笔写入**没有内存副作用**。存储器与 CPU 一起复位，复位期间清空在途事务。指令、数据空间均指向外部 256 KiB 镜像；MMIO `0x8003_F000` 为 `tohost`，写入 1 表示程序通过，其余非零表示失败，CPU 不得硬编码此地址的行为。

**异常与 CSR**：非法指令、指令地址非对齐、load/store 非对齐、ECALL、EBREAK、数据端访问错误均为精确异常；faulting 指令不写回寄存器或内存，年轻指令全部冲刷。异常 `mcause` 编码：指令地址非对齐 0，非法指令 2，EBREAK 3，load 非对齐 4，load 访问错误 5，store 非对齐 6，store 访问错误 7，M-mode ECALL 11。若同一指令可能触发多个原因，先做地址对齐检查，再发总线请求，因此非对齐优先于访问错误。`mepc` 保存 faulting 指令 PC；`mtval` 对地址类异常保存故障地址，对非法指令保存 32-bit 指令编码，对 ECALL/EBREAK 为 0。

**CSR 的确切范围**：`mstatus(0x300)` 仅 MIE(bit3)、MPIE(bit7)、MPP(bits12:11) 可见；本题只有 M-mode，MPP 恒为 `2'b11`。复位值 `0x0000_1800`。进入异常时 `MPIE←MIE,MIE←0,MPP←3`；MRET 时 `MIE←MPIE,MPIE←1,MPP←3,PC←mepc`。`mtvec(0x305)` 仅 direct 模式，写入值低两位强制 0，复位值 `0x8000_0000`。`mscratch(0x340)`、`mepc(0x341)`、`mcause(0x342)`、`mtval(0x343)` 可读写，除 `mepc` 低两位强制 0 外复位为 0；只读 `misa(0x301)=0x4000_0100`、`mhartid(0xF14)=0`。其他 CSR 地址和对只读 CSR 的写操作触发非法指令异常；CSRRS/CSRRC 的源为 x0、立即数形式源为 0 时不写 CSR。所有未列的 `mstatus` 位读 0、写忽略。异常/CSR 编码遵循锁定的[RISC-V ISA/特权规范](https://github.com/riscv/riscv-isa-manual)；ACT4 配置必须与本任务范围一致。

**提交观察口**：每条正常退休指令输出一个周期的 `commit_valid,commit_pc[31:0],commit_insn[31:0],commit_rd[4:0],commit_wdata[31:0],commit_mem_addr[31:0],commit_mem_wstrb[3:0],commit_mem_wdata[31:0]`；无寄存器写回时 `commit_rd=0`，无存储写时 `commit_mem_wstrb=0`。异常事件输出独立 `trap_valid,trap_pc[31:0],trap_cause[31:0],trap_tval[31:0]`，不计为正常退休。这些是 CPU RTL 的轻量退休观察端口，供评测方自行采样；Agent **不需**生成 trace 文件或编写 trace 采集器。观察口只用于验收，不得成为执行功能的输入。

**取指至退休延时与资源边界**：寄存器文件仅 32×32 bit；程序/数据存储器均在核外。零等待、无相关的连续 64 条 ADDI 程序中，逐条记录取指请求被采样的上升沿 `n`；该指令须在 `n+4` 上升沿之后的稳定观察点输出 `commit_valid` 和对应 `commit_pc`。这表示从 IF 请求到 WB 观察跨越四个完整周期、经过 `n..n+4` 五个边沿；响应按本题一周期指令存储器时序提供。不得靠延迟 `commit_valid` 伪造流水级，后级的寄存器写回和存储器副作用也必须与提交轨迹一致。本门禁不作为 PPA 排名。实现须提供必要的旁路、load-use 停顿、分支/跳转冲刷、数据端等待停顿。无分支预测器、缓存、乘除法器或操作系统。

**验收与分值**：F=60：整数与控制流 25；大小端/字节使能、访存与符号扩展 15；CSR/异常/MRET 10；锁定配置的 ACT4 适用测试 10。P=15：数据相关与 load-use 6；随机数据等待及背压 5；冲刷、精确提交和取指至退休延时门禁 4。详细程序集、差分策略、超时与通过条件见[CPU 验收计划](acceptance.md)。ACT4 子集通过不等于 RISC-V 官方认证。
