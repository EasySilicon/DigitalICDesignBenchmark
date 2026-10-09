# T07 · 256 B 直接映射写回数据缓存

**设计需求**：端口还包括 `clk,rst_n`。32-bit 地址/数据，16 条 cache line，每条 16 B、4 个 32-bit word，容量 256 B；直接映射，write-back、write-allocate、little-endian。CPU 侧：`req_valid,req_ready,req_addr[31:0],req_write,req_wdata[31:0],req_wstrb[3:0]`；`rsp_valid,rsp_ready,rsp_rdata[31:0]`。CPU 地址始终 4 字节对齐；读忽略 `req_wstrb`，写以每个字节 strobe 更新目标 word，写响应数据为 0。一次只接受一笔尚未响应完成的 CPU 请求，响应顺序与请求顺序一致。复位使所有 valid/dirty 位为 0；复位只在缓存空闲时施加，不要求清零数据阵列。复位前尚未写回的脏数据按丢弃处理；验收器在检查持久数据的场景里会先驱逐脏行，再施加复位。

**后端 line 接口**：`mem_req_valid,mem_req_ready,mem_req_write,mem_req_addr[31:0],mem_req_wdata[127:0]`；`mem_rsp_valid,mem_rsp_ready,mem_rsp_rdata[127:0]`。地址按 16 B 对齐；写请求为整行写回，读请求为整行回填；每个已接受请求恰有一个响应，写响应忽略数据。后端一次最多一笔未完成请求、按序返回且无错误，响应可能等待 0–7 周期；`mem_rsp_valid` 及数据保持至 `mem_rsp_ready` 握手。未命中且牺牲行为脏时先写回原行，再读新行；写未命中先回填再合并字节。命中不得访问后端；从接受 CPU 请求到给出 `rsp_valid` 不超过两个时钟周期（后端无关）。每笔被接受的 CPU 请求恰有一次响应。

**资源边界**：仅 16×128-bit 数据阵列、16 个 tag、valid/dirty 位及小型控制状态；不得绕过缓存直接把每个命中请求送到后端。不得引入额外被测容量或预取器。所有状态可综合。

**资源与时限**：16 vCPU、32 GiB RAM、100 GiB 可写盘；开发时限 1 小时，同模型 token 上限 48 万。

**验收原始权重**（75 点按比例归一为功能 50 分）：F=60：读写命中 15；干净未命中与回填 15；脏行替换及写回地址/数据 15；部分写与 write-allocate 15。P=15：后端和 CPU 侧背压稳定 10；复位、命中时延与命中无后端流量 5。独立 byte-addressable 内存模型比对所有读结果和后端事务；仅在对各 index 的脏行执行冲突地址驱逐并等待全部响应后，才比对外部内存最终内容。
