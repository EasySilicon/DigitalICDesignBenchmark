# 原 T08 候选 · 3×3 双虚通道 wormhole NoC mesh

**设计需求**：交付可综合顶层模块 `noc_mesh_3x3`、自检测试和运行脚本。顶层由坐标固定为 `(x,y)∈{0,1,2}²` 的 9 个节点组成，节点编号为 `node=3*y+x`。实现内部必须例化 9 个同型 router，通过相邻节点间的双向链路组成真实 3×3 mesh；不得用中央 packet RAM、9×9 全局 crossbar 或行为级目的端队列替代网络。

**顶层接口**：输入 `clk,rst_n`；注入侧 `in_valid[8:0]`、`in_ready[8:0]`、`in_vc[8:0]`、`in_flit[8:0][63:0]`；接收侧 `out_valid[8:0]`、`out_ready[8:0]`、`out_vc[8:0]`、`out_flit[8:0][63:0]`。每个节点每拍最多注入一个 flit、接收一个 flit。传输仅在对应 `valid && ready` 的上升沿发生；阻塞期间 valid、VC 和 flit 必须保持稳定。注入方可逐拍切换 VC，在两个 VC 间交错不同 packet，但每个源节点的同一 VC 内必须按 packet 顺序、packet 内按 flit 顺序发送。

**flit 编码**：`bit63=head`、`bit62=tail`、`bits61:60=dst_x`、`bits59:58=dst_y`、`bits57:42=packet_id`、`bits41:0=payload`。合法目的坐标为 0--2。packet 长度为 1--8 flit；首 flit 仅 `head=1`，末 flit仅 `tail=1`，单 flit packet 同时置 head/tail。一个 packet 的目的坐标、packet ID 和 VC 在所有 flit 中保持不变。不同未完成 packet 的 ID 全局唯一。DUT 必须原样传送 64-bit flit 和 VC；到达顺序只要求每个 packet 内保持，packet 之间允许重排与交织。

**路由与 wormhole 行为**：采用确定性 XY routing，先沿 X 维到达目标列，再沿 Y 维到达目标行，最后送本地端口。head flit 获得输出 VC 后，该输入 VC 对应的 packet 保持同一路由和输出 VC 预留，直到 tail flit 成功离开该 router。不同 packet 不得在同一已预留输出 VC 内交织。每个物理输出每拍最多发送一个 flit；竞争者使用 packet-aware round-robin 或具备等价有限等待保证的公平仲裁。

**双 VC 与流控**：每个有效物理输入方向具有两个独立 VC，每 VC 至少 4 个 flit 的存储容量。内部链路可使用逐 VC ready/valid 或精确信用流控；不得在接收 VC 无容量时超发。一个 VC 因下游容量或 packet 预留阻塞时，同一物理输入的另一个 VC 若存在可用合法路由，必须能够独立取得进展。tail 离开和后续 head 可以安全地连续复用资源，但不得丢 flit、重复 flit、改变 payload、误投节点或破坏 packet 边界。

**复位与进展**：`rst_n` 为异步低有效，至少保持两个时钟周期。复位期间 `in_ready=0`、`out_valid=0`；复位清除全部 FIFO、route/VC allocation、输出保持和仲裁状态，复位前在途 packet 全部丢弃，释放后不得出现旧 flit。合法有限输入停止后，若所有 `out_ready` 最终持续为 1，则所有已接受且未被复位丢弃的 packet 必须在有限时间内完整到达；持续可发送的竞争者不得永久饥饿。

**资源与时限**：仅允许 9 个同型五端口 router、12 组相邻节点双向链路、每个物理输入每 VC 四项 64-bit flit buffer，以及有限 route、reservation、仲裁和输出保持状态。边界上不存在的方向不得收发。开发资源为 16 vCPU、32 GiB RAM、100 GiB 可写盘；开发时限 2 小时，同模型 token 上限 120 万。正式 PPA 目标为 ASAP7/WC、1.0 GHz。

**验收原始权重**（75 点按比例归一为功能 50 分）：F=60：九节点 XY 路由与 72 个有向源宿组合 12；多 flit packet 完整性 12；输入 VC FIFO 与 packet 内顺序 9；wormhole 输出预留 10；多输入热点公平仲裁 9；双 VC 独立进展 8。P=15：端到端 backpressure/信用守恒 7；tail/head 资源边界 3；运行中复位与无旧 flit 5。隐藏验收使用独立端到端 scoreboard，不依赖候选内部信号名。
