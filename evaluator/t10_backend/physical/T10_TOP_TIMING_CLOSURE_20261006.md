# T10 从完整 DUT 关键路径推进时序收敛

## 决策规则

按完整 16×16 / 256 PE DUT 的真实起点、终点和组合锥推进。
每次修改必须关联已报告路径，并写明要消除的物理往返或寄存器间依赖。
禁止仅凭 PE 内部 WNS 宣称完整 DUT 通过。禁止在当前控制路径仍远超周期时继续 CTS/布线。
RTL 改动先过原始独立 2752-case、复位、结构、吞吐与延时验收，再进入物理诊断。
之后同时检查旧瓶颈、全局最差裕量和其他路径类别，不能只追一个变正的局部路径。

## 固定分析条件

- 完整十六个 tile 宏，层级内共 256 PE；1000 ps 两个时钟、200 ps I/O 延时。
- 未构建父层时钟树时使用理想父时钟和真实布局寄生，明确不作为 CTS/路由发布证据。
- RVT SS 标准单元和已有 v54 宏模型保持一致。v54 尚不具备正式基线准入资格。
- 六类 setup 各取 100 个不同 endpoint 样本，hold 各取 10 个；报告不是全部违例计数或 TNS。
- 保留 SDC、七个库、ODB、setRC、分析脚本的 SHA-256。不同口径的 WNS 不直接相减。
- 一个自有 OpenROAD；启动遵守共享主机内存/优先级规则；时钟层 M6/M7。

分析脚本：`run_t10_full_dut_path_audit.sh`、`t10_full_dut_path_audit.tcl`、
`t10_summarize_top_paths.py`。记录保存在对应完整 DUT checkpoint 的 `top_path_audit/`。

## v114 → v117：端到端路径变化

v117 根据 v114 的具体匿名 valid/mask/accept 门往返位置，锚定输出接口组合锥。
相同 v108 网表和原功能合格 RTL，完整信号缓冲后两版均通过 native 放置与独立零重叠检查。

| 路径类别 | v114 setup WNS ps | v117 setup WNS ps |
| --- | ---: | ---: |
| 寄存器 → 寄存器 | −22336.2695 | −15825.9180 |
| 输入 → 内部 | −14230.9590 | −18581.0078 |
| 内部 → 输出 | −17920.9824 | −7472.8208 |
| 寄存器 → 宏 | −8967.6953 | −8968.2119 |
| 宏 → 寄存器 | −1962.4054 | −1962.4054 |
| 宏 → 宏 | −389.7318 | −389.7318 |

v117 全局 setup WNS −18581.01 ps，hold −363.59 ps。全局改善，但输入类变差；
不是 1 GHz 收敛。需要同时观察六类，不能只引用改善的寄存器路径。

### 最高优先级：接受控制往返

起点 `out_ready`，终点
`distributed_output_row[3].tile_column[3].egress/local_column[3].local_queue/read_select`。
200 ps 外部延时后，经第 0 列附近的 `_4142_` AND 门生成公共 accept，再返回第 3 列。
到达时间 19536.6523 ps；原生报告累计分解：

| 组成 | 延时 ps | 原因 |
| --- | ---: | --- |
| 正极性缓冲 | 12465.4796 | 160 级，长距离转发 |
| 线 | 6770.4273 | 164 段，包含右侧输入至第 0 列及返回第 3 列的往返 |
| 逻辑 | 100.7452 | 仅 AND2、XNOR2 两级 |
| 外部输入延时 | 200.0000 | 固定 I/O 约束 |

因此不能靠调整同一长链的几个间距宣称解决。v118 的 RTL 修改把 accept 计算移入
每个 `keep_hierarchy` 的 tile egress 控制器：
`ready_in && (output_mask_locked ? locked_valid : offered_valid)`。
每个列控制器已有独立且事务相同的队列、退休和资格状态；以本地 offered_valid 形成接受，
移除 canonical 第 0 列的 combinational valid/accept 再向其他列分发的往返。
公共 held mask 仍保留，维持背压时整个输出 valid mask 不变。

v118 未增加拍数、未改变验收延时、未解除全局背压约束；现已通过原始独立 2752-case
验收、全部九组、reset、256 PE 结构以及14个 phase 的零输入气泡门禁。
非 PE 状态245588 bit，仍低于306304 bit上限；RTL SHA-256：
`8041f712f432ed2ff982b88836b6ed389b723625760713bd15ca8be1105d501d`。
v119–v122 正在验证该明确路径假设，固定与 v117 相同的缓冲间距和阈值；
跳过已知无意义的未缓冲 STA，仅保留前后放置检查及缓冲后的六类路径报告。

v122 的假设验证已完成，完整 DUT native/独立零重叠通过，1 GHz pre-CTS setup WNS
从 v117 的 −18581.01 ps 改善到 −15953.89 ps，hold 仍 −363.59 ps。
输入类 worst 从 −18581.0078 改善到 −14147.1055 ps；寄存器类 worst 从
−15825.9180 变为 −15953.8906 ps。六类报告共同表明：旧 canonical accept
绕行已删除，但整体仍严重不达标，不能把一次改进当成收敛。

新的首要路径为 row 2 `retired[3]` → row 3 资格 → 全局 any-valid/mask enable
→ `locked_output_mask[3]`，到达16906.1895 ps，含127级缓冲10116.4950 ps、
线5805.3454 ps、逻辑与反相器984.3500 ps。v123 改为 unlocked 时直接捕获
每个 offered 位，`output_mask_locked <= |offered_output_mask`；个别 held-mask
寄存器不再等待全局 any-valid 决定 enable。零 mask 时继续 unlocked，非零
mask 在同一拍锁存，因此公开背压保持/首次 valid 语义不变。先跑原始功能验收，
v123 已通过原始2752-case、全部九组、reset、256 PE结构及14个phase的零输入气泡门禁。
状态245588 bit，RTL SHA-256
`6601f244693bf0a4b3c890164c34f3c64cf12f5705c2b7bc82a7a0256c4915c7`。
v124–v127 已完成相同物理参数验证：完整 DUT pre-CTS setup WNS 为 −14106.48 ps，
hold 为 −363.59 ps。输入类 worst 为 −14106.4756 ps，寄存器类 worst 为
−13070.7559 ps。相对 v122 全局改善1847.42 ps，但仍严重不满足1 GHz。
最新报告目录：
`${T10_ORFS_ROOT}/flow/results/asap7/npu_systolic_matmul_16x16/ic_t10_candidate_top_v127_mask_capture_signals_m7_wc_p1000_seed11/top_path_audit/`。

实际最差三条 endpoint 路径（按 setup slack 排序，不把同一家族合并）：
起点均为 `out_ready`，终点共同前缀为
`distributed_output_row[3].tile_column[0].egress/`。

| 终点 | 到达时间 ps（含200 ps外部输入延时） | setup slack ps |
| --- | ---: | ---: |
| `local_column[3].local_queue/read_select` | 15059.2803 | −14106.4756 |
| `local_column[0].local_queue/read_select` | 15039.9160 | −14088.0752 |
| `local_column[2].local_queue/read_select` | 15034.0273 | −14081.2607 |

第一条含118级缓冲9352.1161 ps、线5138.6692 ps、三个逻辑单元368.4963 ps。
因此这里暴露的是父层 ready/输出队列控制的物理实现问题，而非 tile 内部乘加路径。
当前长距离组合控制和长串缓冲均必须整改；单 tile 内部时序正不能替代这些父层路径的验收。
这一步只消除已证实的额外往返，不能据此保证 remaining ready 广播满足 1 GHz。
后续若单向控制传播仍超过周期，需要明确的注册式 ready/accept 分发与可吸收延迟确认的
弹性结果缓冲设计，数据、块 ID、行号和 valid 必须一起保持对齐。不能只延迟 ready 而沿用原队列弹出语义。

### 后续独立瓶颈

- `retired` → 邻行资格 → queue pointer、count 和 held mask：即使本地 accept 成立，
  跨 tile 行资格与全局 mask 仍可能是下一最差路径，需按实际新报告确定流水切分。
- `a_ctrl_valid[15]` → `tile_row[3].tile_col[0].tile`：v117 为 −8968.21 ps，
  79 级缓冲、6091.36 ps 缓冲与3452.81 ps 线延时；其数值解码逻辑只有单个反相门。
  需要检查反相门与真实 lane 15 token pin 的布局/连接，不能把它当成 PE 算术问题。
- 宏结果 → 本地选择：−1962.41 ps。包含宏内部时钟插入模型和本地数据传输，
  后续检查 capture/selection 流水及对应元数据对齐，不要直接删除模型的插入延时。
- 宏 → 宏：−389.73 ps。必须在一致的宏模型、父 CTS clock latency 与最终寄生条件下
  检查；不能用理想父时钟诊断替代完整 CTS 通过。

任何候选都不得修改 fixed DUT 端口、1 GHz 目标、原始吞吐门禁或功能判据来取得通过。
