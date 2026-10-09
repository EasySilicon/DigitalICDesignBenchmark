# Benchmark 候选题

本文记录尚未进入正式 manifest 的候选题。候选编号不代表最终题号，接口、资源上限、时限和权重须在参考实现与独立验收器收敛后冻结。

## 候选 A：2 路组相联非阻塞写回缓存

目标是补充一题主要由并发状态正确性拉开模型差距、又能连续给出部分功能分的缓存题。

- 1 KiB、2-way、16 B cache line、32 sets，write-back、write-allocate、LRU。
- CPU 每拍最多接受一笔带唯一 `req_id` 的请求，最多 8 笔在途，响应允许乱序。
- 4 个 MSHR，支持 hit-under-miss、同 line miss 合并，以及 load/store 合并到等待回填的 line。
- 后端 line 接口携带事务 ID，响应允许乱序；两项 writeback buffer 允许脏行写回与 refill 并发。
- CPU、请求后端和响应后端均允许独立 backpressure。
- 支持写回并失效全部 cache line 的 flush；运行中复位须隔离复位前的迟到响应。
- 验收重点：同 set 冲突、way 预留、字节写合并、脏 victim、乱序 refill、恰好一次响应、flush/reset 与在途事务交错。

建议功能 50 分：基本命中/替换 10，脏行写回 8，hit-under-miss 7，多 MSHR 7，同 line 合并 6，乱序 ID 路由 5，load/store 顺序 4，backpressure/flush/reset 3。

## 候选 B：4×4 多事务 AXI4 crossbar

目标是以协议并发而非算术规模制造功能难度，集中测试五个解耦通道、burst 所有权、ID 路由和任意背压下的稳定性。

- 4 个 AXI4 slave-facing 上游端口连接 4 个 AXI4 master-facing 下游端口，64-bit data、32-bit address。
- 支持每个上游最多 4 笔未完成读事务和 4 笔未完成写事务；读写并行。
- 支持长度 1--16 beat 的对齐 INCR burst；不要求 FIXED、WRAP、exclusive、atomic 或窄传输。
- AW 与 W 完全解耦；一个 write burst 获得下游端口后，W 所有权保持到被接受的 `WLAST`，不得把两个上游的 W beat 混合。
- AR 可以逐事务轮询仲裁；R/B 根据内部扩展 ID 正确路由回原上游。
- 下游允许跨 ID 乱序返回；同一上游、同一原始 ID 的响应必须保持发出顺序。
- 地址跨越 4 KiB、跨越下游窗口或无映射时，由 crossbar 本地产生 DECERR；错误写仍须完整吸收规定数量的 W beat，且不得产生下游副作用。
- 五个通道均接受任意 backpressure；所有 `VALID && !READY` 的载荷必须稳定。
- 每个下游分别进行读、写 round-robin 仲裁，持续请求不得饥饿；运行中复位清除所有所有权、路由表和未完成计数。

建议功能 50 分：单拍读写及地址路由 8，读 burst 7，AW/W 解耦与写 burst 所有权 8，B/R ID 回送 7，跨 ID 乱序返回 6，同 ID 顺序 5，全通道背压稳定 5，DECERR 与错误 burst 吸收 3，公平性及复位 1。

隐藏验收应包含：多个上游同时访问同一下游、AW 顺序与 W 到达节奏错开、读写响应反序返回、同 ID 与不同 ID 混合、每个通道独立随机阻塞、错误 burst 后立即接合法 burst，以及复位前迟到响应隔离。测试记分牌按已接受事务建立所有权和 ID 映射，不能依赖候选内部层次或信号名。

## 候选 C：长规格四通道 Scatter-Gather DMA 子系统

目标是增加一题长规格、大代码量、跨模块状态高度耦合的从零设计任务，测试 Agent 在长上下文中保持接口、错误处理、顺序和资源规则全局一致的能力。参考 RTL 目标为 3,000--5,000 行有效可综合代码，规格目标为 15--25 页高信息密度内容；代码行数只用于控制任务规模，不直接参与评分。

- 4 个独立 DMA channel，具有 descriptor ring、completion ring、通道优先级和公平仲裁。
- 使用完整定义且自包含的 AXI4 子集作为读写 master，支持多个 outstanding transaction、不同 ID 间乱序响应和通道内有序提交。
- 支持非对齐首尾、长度为零和最大长度边界、burst 拆分及 4 KiB 边界处理。
- descriptor、payload 和 completion 分别具有明确的可见性、提交与错误语义；abort 后已经发出的请求仍须被安全回收。
- 提供每通道地址保护窗口、pause/resume、软复位、中途取消、错误状态、计数器和中断聚合。
- 冻结错误优先级以及 error、abort、pause、completion 同周期发生时的行为。
- 全部命令、数据和 completion 通路支持任意 backpressure；运行中复位与迟到响应不得污染新任务。

验收重点包括：非对齐跨 4 KiB 传输、响应乱序、descriptor completion 顺序、部分写 strobe、通道饥饿、错误恢复、abort 后迟到响应、ring wrap、pause/resume 和复位隔离。建议时限 4 小时；必须先冻结独立内存模型、事务级 scoreboard、错误注入矩阵和结构门禁，再决定其是否进入正式前十。

当前决定：用户已同意采用该方向，待编写完整规格、参考 RTL 和验收器。

## 候选 D：Brownfield Cache 增量开发

目标是测试 Agent 阅读既有 RTL、识别隐含不变量、在保持全部旧回归的前提下实现相互作用的新功能。起点是一份已经验证通过的二级组相联写回 Cache，而不是空目录。

- 基线 RTL 约 1,500--2,500 行，已有 blocking miss、dirty eviction、refill、replacement、backpressure 和完整基础回归。
- Feature 1：增加 2 个 MSHR，允许不同 cache line 的 miss 并发，并合并相同 line 的等待请求。
- Feature 2：增加运行时 `flush/invalidate range`，正确处理 dirty line、正在 writeback/refill 的 line、合并请求及后端 backpressure。
- 新功能必须保持原接口、原命中延迟和所有既有测试行为；不得破坏原 replacement、错误响应和复位语义。
- 重点交互包括 flush 命中在途 refill、invalidate 遇到 dirty victim、同 line 合并跨越 flush 边界，以及 reset/flush 与迟到响应交错。

验收分为旧功能回归、新功能基本行为和交互竞态三部分。基础存储阵列、协议 primitive 和测试环境可冻结为只读并校验哈希；允许修改指定控制模块并新增文件，不采用容易被格式化或重构干扰的简单 diff 行数限制。

## 候选 E：Brownfield 4×4 AXI4 Crossbar 故障隔离与在线重映射

目标是测试 Agent 在一套已经支持 burst、多 outstanding ID、乱序响应和五通道独立背压的成熟 crossbar 中，修改完整事务生命周期而不破坏既有协议行为。起点 RTL 约 2,000--3,000 行并带有全套基础回归。

- Feature 1：为每个下游 slave 增加可配置 transaction timeout、合成 `SLVERR`、quarantine 和软件恢复。
- 超时后必须安全吸收或隔离迟到的 R/B 响应，保持 burst、ID、同 ID 顺序和恰好一次响应；故障 slave 不得继续阻塞其他 slave。
- Feature 2：增加 shadow address map、逐 master R/W 权限和原子 `commit`。新事务使用新 generation，已接受事务必须完整沿用旧映射。
- 非法或重叠映射必须拒绝；权限失败返回 DECERR 且不得向真实 slave 泄漏请求。
- 重点交互包括 AW 已接受而 W 未完成时 commit、timeout 与 commit 同周期、旧 slave 迟到响应在地址已重映射后到达、相同 master ID 跨 generation 复用，以及 read/write 分别跨越重配置边界。

旧 crossbar 回归必须全部保持通过。建议冻结基础 FIFO、skid buffer 和 channel primitive，只开放 decode、tracking、fault-control、CSR 模块及新增文件；hidden test 对五个通道分别施加随机背压，并独立建模事务 generation、超时、迟到响应和访问权限。建议时限 2.5--3 小时。

## 候选 F：1GbE MAC Post-silicon RTL Bug Repair

目标是提供真实长 RTL 的 brownfield 修复与扩展任务。此方向原作为实验 T11，现已冻结并加入 v0.3 套件，编号为 T08：一个 TX/RX 帧事务回归修复工单 + 新增 RX 单 C-tag VLAN admission。修复工单包含多处耦合控制回归。

- 起点基于 MIT verilog-ethernet 的八个真实模块，超过 3,800 行；完整任务含固定 top、未实现 feature stub、配置快照、原子丢弃及 terminal metadata。
- 协议范围明确为 IEEE 802.3 1Gbps 全双工 GMII 子集及 IEEE 802.1Q C-tag，不要求 PHY/驱动或完整 IEEE 认证。
- 当前 `3.0-frame-transactions` 自包含规格超过 4,000 行，公开输入包位于 `benchmark/tasks/T08/`；限时 120 分钟，功能 /50 + PPA /50 + 时间 /5，三种子 SRAM 参考与物理 workload 已冻结。
- 考生只看到有缺陷起点、规格和公开 smoke；独立验收在容器外运行，无 Skill、无黄金补丁。
- 首次可行性试做使用 Codex + gpt-6.1-sol，保留旧版输入；计时与 EDA 采集独立于作者准备工作，新版不在运行中覆盖旧版。

## 原 T11 候选：3×3 双虚通道 wormhole NoC mesh（保留）

目标是用分布式流控、packet 资源预留和多点竞争制造功能难度，检查局部正确的 router 在组合为网络后能否保持端到端无丢失、无重复、无串包和无死锁。

- 顶层包含坐标固定为 `(x,y)∈{0,1,2}²` 的 9 个节点，每个节点有一个本地注入端口和一个本地接收端口；内部必须由 9 个同型五端口 router 组成，边界上不存在的方向端口固定为不可发送且不接收。
- flit 为 64 bit；packet 长度为 1--8 flit，包含 head/tail、目标坐标、packet ID 和 payload。单 flit packet 同时置 head/tail。
- 每个物理输入端口具有 2 个独立 virtual channel，每 VC 深度为 4；不同 VC 可以独立前进，单个 VC 内保持 flit 顺序。
- 使用确定性 XY routing：先走 X 维，再走 Y 维；到达目标坐标后送本地端口。禁止绕路或把目标信息用于测试特化。
- head flit 完成 route/VC allocation 后，body 和 tail 必须沿相同输出 VC 前进；预留保持到 tail 成功离开。不同 packet 不得在同一已预留输出 VC 内交织。
- 每个输出端口每拍最多发送一个 flit，对竞争的输入 VC 做 packet-aware round-robin 仲裁；持续可发送的请求不得永久饥饿。
- 链路采用 ready/valid 或等价信用流控。若采用信用，计数必须精确覆盖同拍发送与信用返回，不能下溢、溢出或超发；若采用 ready/valid，阻塞期间 flit 及 VC 选择必须稳定。
- 一个 VC 的 head 被阻塞时，另一个 VC 若有可用路由必须能够继续，作为避免不必要 head-of-line blocking 的功能门禁。
- 允许 tail 离开与下一 packet 的 head 在同拍安全复用相关资源；运行中复位丢弃所有在途 packet，并恢复 FIFO、allocator、reservation 和 credit 的一致初始状态。
- 资源边界为 9 个 router、12 组相邻节点双向链路、每输入 VC 四项 flit buffer 和有限仲裁/预留状态；不得使用中央 packet 存储、全局 crossbar 或完整 packet 重排 RAM 冒充 mesh。

建议功能 50 分：单 packet 路由及九节点覆盖 8，多 flit packet 完整性 7，输入 VC FIFO 与顺序 6，wormhole 输出预留 7，多输入热点仲裁 6，双 VC 独立进展 5，端到端 backpressure/credit 5，tail/head 同拍边界 3，公平性及运行中复位 3。

隐藏验收应使用独立端到端 packet scoreboard，并覆盖：九节点全部 72 个有向源宿组合、所有外围节点向中心节点和角节点持续发送、最长 4-hop 对角路径、环形与交叉流量、随机 packet 长度、两个 VC 的相反阻塞状态、尾 flit 长时间阻塞、信用归还与新发送同拍、tail/head 同拍复用，以及满网络运行时的复位。除逐包内容与顺序外，还应监测有限时间进展、buffer/credit 守恒和任何非目标节点误收。

当前状态：公开原型资料此前已从旧 T11 迁至 `benchmark/candidates/noc_mesh_3x3/`，没有丢弃。2026-10-05 的参考原型通过 lint、Yosys check、公开 smoke、20 个冻结种子 × 1080 packet 及拥塞复位回归；评测侧历史 RTL/日志保留。它仍是候选，不占用 MAC T08。
