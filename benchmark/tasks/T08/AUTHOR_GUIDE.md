# T08 作者/主机侧发布说明

此文件和 SPEC_CHANGELOG.md 不进入考生包。考生包由 prepare_trial.py 的
显式白名单生成；包含有缺陷的 starter，不包含修复答案、独立验收器或 Skill。

## 本轮冻结版本

- 功能规格：`3.0-frame-transactions`，自包含长篇 GMII 子集与 VLAN 准入规格。
- 起始 RTL：`3.0-coalesced-commit-regression`，10 个模块，共 3,977 行。
- 验收器：`3.1-boundary-crosses`，37 case × 3 seed，功能最高 50 分。
- 每模型 120 分钟实际执行时间，无累计 token / cost 硬停。
- PPA：三种子 1 GHz SRAM 参考已冻结；T08 已进入 v0.3 的十题套件。
- PPA 时钟目标沿用旧策略 `1.0-uniform-1ghz`；logic_clk / tx_clk / rx_clk 均为
  1,000 ps，仍视为三个异步时钟域。功能验收频率和已有冻结试验不改。
  参考和功耗 workload 已于 2026-10-08 冻结，三个种子 setup/hold 均非负且布线 DRC 为零。
- 新物理流程版本：`2.0-lambdapdk-tdp-1ghz`，使用固定双时钟研究 SRAM。
  时钟仍为三域 1 GHz；旧标准单元尝试不覆盖、不混入新聚合结果。
- 旧 gpt-6.1-sol 试做是短规格旧版；保留其原输入、验收器和分数，不能
  冒充本轮新版的对照模型。原 3×3 NoC 存在 benchmark/candidates/noc_mesh_3x3/。
- 已完成 Kimi/GLM 的 `2.0-long-form` / `2.1-early-snapshot` 试验同样
  保留冻结输入、验收器和原始分数；本轮只升级未来新试验的题卡和起点。

## 1 GHz PPA 参考资格与冻结流程

`evaluator/ppa_probe.py T08` 使用三组独立的 1,000 ps 时钟；端口延迟按
所属域约束。旧标准单元资格流程不缩小 FIFO，不 mock 存储；专用
综合容量保护为 262,144 bit/array，不是新增可用 RTL 存储预算。SRAM
替换由下述新策略定义匹配的双时钟端口、模型和公平映射流程，不能将
本平台现有单端口 fakeram 直接冒充异步 FIFO 的双时钟 RAM。

新 SRAM 流程由 `evaluator/run_t08_sram_ppa.py` 编排，
`evaluator/t11_sram.py` 使用 Yosys `memory_libmap` 和通用技术映射，
不按候选文件名或作者实现做字符串替换、不修改提交的 RTL。
宏为 `vendor/lambdapdk_fakeram7` 中固定上游 commit 的
`fakeram7_tdp_4096x32`，A 端写、B 端读，各自独立时钟；完整保留容量。
读端常使能，原 RTL 的有条件读输出保持由 Yosys 外部逻辑实现，不能
把上游 `ce=0` 输出无效误当成时钟使能保持。上游仿真文件仅修正端口
列表尾逗号及重复 integer 声明；原文件、修订文件和 SHA-256 均保留。

优化阶段只用 seed11：宏全地址/掩码/并发自检；映射后 111 功能和 270
压力回归；单种子布局布线/寄生/时序；对应网表自检和 VCD 功耗。
seed11 setup/hold/DRC 全通过后，才追加 seed29/47，形成三种子资格；
原始及映射后 RTL 的最终新鲜回归。映射不支持时报告具体错误，不能
偷偷缩小内存、删除功能或伪造宏。宏读延迟与功能不合格不得进入冻结。
诊断编译失败不是考生功能扣分，也不修改历史 summary。

标准单元时序使用 WC，宏使用原始 TT 0.7 V/25 C 近似 Liberty；
这是 **混合角研究 PPA**，不是全设计 WC 签核，不能伪造 SRAM SS/FF。
功耗为标准单元 TT + 宏 TT。面积为标准单元面积加实际放置的全部宏
LEF 面积，包括未用位；总功耗必须含宏，单独保存每实例宏功耗证据。
`DRC=0` 指 OpenROAD 详细布线规则检查（宏外互连和引脚访问），不包括
SRAM 内部晶体管版图；不要求宏 GDS 或完整 DRC/LVS。模型假设、时序
窗口、布线与宏输入连通性、版本/哈希和检查范围必须写入每次结果。
参考与考生统一映射、同一物理参数，不仅给参考使用宏；历史功能成绩
不因后端改动重算，新的 PPA 只能与相同版本的冻结基线比较。

可复现入口（建议在 MemoryMax=24G、MemorySwapMax=0 的 systemd scope
内运行；布局前等待 MemAvailable 至少 50 GiB）：

```sh
PYTHONPATH=evaluator python3 evaluator/run_t08_sram_ppa.py /path/to/submission \
  --orfs-root /path/to/ORFS --output-dir /path/to/seed11-optimization

# Only after that seed11 aggregate passes setup, hold and DRC:
PYTHONPATH=evaluator python3 evaluator/run_t08_sram_ppa.py /path/to/submission \
  --orfs-root /path/to/ORFS --output-dir /path/to/three-seed-qualification \
  --prepared-mapping /path/to/seed11-optimization/mapped \
  --qualify-from /path/to/seed11-optimization/aggregate.json
```

整个流程没有累计 token/cost 停止或整体运行时限；单次仿真保留原有
防死锁 watchdog。阶段日志与 `state.json` 保留进度/错误；默认只有
seed11，不达标就回到 RTL 优化，不自动消耗另外两种子。单种子不是冻结
结果；`--qualify-from` 必须重新核对原始工件、相同源码及通过的物理门禁，
复用 seed11 后只追加 29/47。不得覆盖已有冻结参考。

`evaluator/t08_power_probe.py` 使用固定 `T11-power-v1` 全双工 workload，
三时钟均 1 GHz、相位不同，检查字节、CRC、元数据和拒绝恢复；有用单位
为接收的 TX body octet 与交付的 RX body octet，合计 4,296。仅 RTL
仿真成功不产生功耗评分；需在各布线网表上自检、加载 SPEF 并取得 TT
功耗与至少 95% 的 VCD 标注。此脚本独立于旧 T01–T10 的 workload 哈希。

`evaluator/ppa_aggregate.py T08` 聚合 11/29/47 三种子；正式冻结入口为
`evaluator/t08_reference_freeze.py`，需要三种子 setup/hold 非负、DRC=0，
功耗资格通过，以及同一 RTL 的新一轮 111 正式/270 压力回归全部通过。
它在仓库之外保留只读原始物理工件与 freeze.json；公开参考 RTL 位于
`evaluator/reference/T08/rtl/`，公开资格报告位于
`evaluator/fixtures/t08_reference_20261008/`，公开任务冻结清单为 `FREEZE.json`。
唯一评分基线为 `benchmark/ppa-baselines.json`，不存在额外私有评分基线。
本参考资格已完成，不修改考生输入或历史成绩；未来新参考资格完成前保持 pending，
不得将“已设为 1 GHz”“综合完成”或单种子结果写成已冻结。

隔离冻结主机脚本时，必须带齐 `evaluator/`、`env/asap7_seq_sim.v`、
ASAP7 平台与固定 SRAM 模型，另带 `benchmark/tasks/T10/public/matmul_oracle.py`。
这是共享功耗辅助模块的传递导入依赖，不包含 T10 参考 RTL或验收向量，
也不会加入考生输入。运行器先执行功耗入口 `--help` 的导入预检，
避免花完布局时间才发现缺少 Python 依赖。
中断后可在相同入口加 `--resume`：持有互斥锁，核对模型、源代码、
映射回归证据及已完成布局的参数和工件，复用已完成的映射及 route，
继续功耗和剩余种子。原失败 state/log 保留，重试功耗写入独立目录。
修改 RTL、模型或物理参数必须另开测量目录，不能借续跑混用旧工件。

参考冻结的严格物理门槛不同于考生连续评分：考生 setup/hold 违例仍
按既定连续策略处理，不因参考资格门槛而被一刀切判零。

## 新修复工单的设计边界

移除旧版容易局部定位的 TX CRC/补零故障，改为帧边界批量发布重构后的
事务生命周期回归：完整但未发布的帧、正在接收的帧与 CDC 通知邮箱不是
同一个检查点。缺陷分布于延迟发布、坏帧回滚、溢出回滚和通知保留路径。
触发需要帧重叠、未排空的已发布批次及后继丢弃或背压释放；普通孤立
报文与原有 CRC/补零验收可全部通过。地址回绕另用持续流量验收。

公开规格只提供外部症状和原子性要求，不给内部位置、补丁或正确 RTL。
不通过模糊规则、取消可观测状态或非确定性亚稳态模拟来制造难度。
无新增接口、协议特性、存储豁免或预算变化。公开 smoke 仍提供仿真帮助
函数；不是完全没有验证脚手架，但不包含新增压力用例或独立计分器。
是否比上一版显著更难定位，必须由新冻结试验验证，作者负例不能替代。

## 准备同题输入

在仓库根目录运行，目标必须是一个尚不存在的主机目录：

```sh
python3 -m benchmark.prepare_t08_comparison /path/to/new/t08-comparison
```

脚本只准备、不启动模型、不复制凭据、不启动计时。两个子目录分别为
`kimi-k3-256k` 和 `glm-5.3-flash`；公开输入逐文件相同，主机侧验收器也相同。
release.json、starting_inventory.json、judge_inventory.json 记录 SHA-256。
共享 README 由 candidate-rules.md 生成，不复制包含其他题目接口/参数/结果
的整套 benchmark README；不发其他题目的题卡或正式结果 schema。
不要将整个 trial 根目录挂进容器，只挂当前模型 workspace、全新 agent_home、
tmp 和只读 empty_skills。frozen_judge、grading、telemetry_eda 留在主机上。
启动前复核清单；运行中的输入和验收器不随仓库后续变更升级。

主机侧启动器为 benchmark/run_t08_comparison.py，准备器将它及其依赖冻结在
frozen_runner/，不挂给考生。各模型先 --preflight，确认工具链、目录可见性、
空 Skill、干净 HOME；再分别在新 tmux 中运行。两者 ready.json 均出现后，
才创建公共主机 start_both gate，同步开始两份 7,200 秒的候选时钟。
每个模型退出后自动保留现场，串行取得评分锁运行冻结功能验收及综合检查。

## 启动策略（不是已执行状态）

Kimi：使用 kimi CLI、`kimi-code/k3-256k`，空只读 skills-dir，并禁用
Skill/WebSearch/FetchURL；只复制模型连接/认证必需设置，不带旧 session、
插件、MCP、Skill 或项目记忆。GLM：使用 Claude Code、`glm-5.3-flash`，
新配置目录、disableBundledSkills，禁用 Skill/WebSearch/WebFetch；保留普通
commands，不加 --disable-slash-commands、--no-session-persistence 或成本硬停。
GLM 沿用用户指定的 128000 output-token 设置，这是单次响应请求上限，
不是整题 token 预算，是否实际支持应从模型端响应核实。

只准备一个模型并覆盖本次试验预算（不改变仓库默认 120 分钟）：

```sh
python3 -m benchmark.prepare_t08_comparison /path/to/new/glm-v3-trial \
  --models glm-5.3-flash --time-limit-minutes 90
```

准备器同步覆盖候选题面、题卡、README、acceptance、PROMPT 与主机 manifest，
冻结 runner 使用 manifest 的 5,400 秒，不再固定为 7,200 秒。单模型就绪
且 EDA 已附加后，释放父目录 start_single gate；双模型默认仍用 start_both。
2026-10-07 按用户明确要求，旧 GLM T08 已移入主机私有回收目录，可恢复；
Kimi 的旧试验不动。旧版作者验证哈希仍是当时的历史证据，不是当前模型成绩。

两者独立 tmux / Docker，按之前每容器 32 GiB、16 CPU 的限制运行。主机
内存不足时等待，不改变考生时钟。先附加 100 ms EDA 监控，再释放 gate
并写 TRIAL_CLOCK.json 的开始/截止时间；总预算 7,200 秒。
编译、仿真、EDA 的重叠进程按忙碌区间并集计时，不把父子进程重复相加。
保留完整 session、CLI 精确参数、stdout/stderr、退出原因、交付 RTL、耗时。
Claude init 必须确认模型正确、skills=[]、Web 工具不可用且普通 commands
仍在。仅有提示词声明不能当作完成运行时隔离检查。
禁止直接 Web 工具不等于全面断网；模型 API 必须联网，shell 联网不是
网络层强制封锁。不得声称达到完全离线或消除一切检索途径。

## 独立验收

停止考生容器后，在该 trial 的 frozen_judge 目录运行：

```sh
python3 -m evaluator.t08_check ../workspace --output ../grading/functional.json
```

另做 Yosys hierarchy/proc/opt/check 可综合性检查，检查 run.sh/results.json/
README.md 等交付物。功能按独立验收器分组计分；PPA 保持 pending；EDA
监控仅采考生容器，作者准备、独立验收和后续物理实现不计入考生耗时。
评分失败必须区分候选 RTL 错误和基础设施/验收器错误，不拿 smoke 或
候选自报分数代替独立验收结果。未交卷/中断保留现场，不自动清零重做。

## 作者侧负向回归

```sh
python3 -m evaluator.t08_mutation_check --baseline /path/to/correct/submission \
  --output-dir /path/to/qualification --jobs 3
```

先要求正确正例 111/111；18 个可编译错误变异需在所有指定 witness/seed
触发失败，编译失败/跳过不算检出。正确 RTL 不打包进仓库脚本或考生输入。
脚本只修改临时副本；变异锚点针对已验证的 streaming parser，换结构要
显式适配。原 feature_mutation_qualification.json 是旧 2.1 版本的历史证据，
不能把它标成新版验证；新版需单独记录版本、输入/验收器哈希与结果。
当前证据：evaluator/fixtures/t11_mac/feature_mutation_qualification_v31.json；
v3.json 保留为旧验收器的历史证据，不重写旧版本的验证结论。
有限负例不能保证捕获所有未知实现错误。

```sh
python3 -m evaluator.t08_repair_qualification --baseline /path/to/correct/submission \
  --output-dir /path/to/repair-qualification --jobs 2
```

该主机侧脚本要求旧继承 FIFO 结构的正确正例，绝不修改原提交。先验完整
111/111，再验“仅批量通知优化”的正确对照；完整故障注入必须逐字匹配
公开 starter FIFO。分别留下发布、回滚、通知取消中的一种漏修，以及
截断环形检查点高位的错误修复，均须可编译且所有指定种子触发失败。
TX 后继好帧有时会重新触发通知，因此通知漏修的直接 witness 是 RX
溢出/策略丢弃场景；不能硬要求每一种故障在所有场景都失败。
当前证据记录于 evaluator/fixtures/t11_mac/repair_mutation_qualification_v31.json。

## 3.0 版历史作者验证（不是新模型成绩）

- 分别只读重放旧 gpt-6.1-sol、Kimi 与 GLM 已修好 RTL，三份正例各通过
  28×3=84 场验收。输出另存于 /mnt/ubu_3T/ic_bcmk_trials/t11_v3_author_20261007/，
  原 trial 的 summary、提交、冻结输入与验收器不写入。
- 仅批量发布调度、无事务故障的对照也通过 84/84；完整故障起点保留
  旧 0–22 case 的通过结果，只在新增 23–27 压力 case 失败。
- 五种帧事务负例与十四种特性负例均可编译，并在各指定 witness 的
  三种子都失败；编译失败不作为检出证据。
- 新起点经 Yosys hierarchy/proc/opt/check -assert，报告 0 problems。
  此项只说明结构可综合，不是完整综合/PPA 流程。
- 39 项规格、冻结包装、隔离、启动器、耗时采样及负例脚本单元测试通过。
  耗时采样单元测试不追溯证明旧 trial 的 EDA 数值完整准确。
- 两份新包装只用于一致性检查：公开输入/冻结验收器一致、无凭据、
  无 Skill/修复答案/主机验收器挂载，状态 prepared_not_started。
- 作者侧 RTL/验证技能用于事务不变量、独立计分板与负向回归设计；
  不进入候选 workspace，不作为被测模型的额外上下文。

## 3.1 边界与交叉回归

规格和有缺陷起点不变，只升级验收器。原 3.0 正例通过有限用例并不
代表已经证明完整功能正确；新发现 GLM 在首字节同时为末字节时使用
旧快照/旧报头，说明先前覆盖遗漏。不得据旧 84/84 声称其无任何功能 bug。

新增 28–36 case：全长 1–18 的新帧启用/旁路、带标签前帧后的旁路及
启用短帧、旁路到启用、短帧 MAC 错误优先级及后继恢复、192 组独立
策略 oracle、混合 TCI/无标签帧的队列和环形复用、带待输出元数据的
协调复位。新增 case 三种子分别用 80/100/160 MHz 系统时钟和不同 RX
相位，TX/RX 保持 125 MHz。全程只观察外部端口，不读取 DUT 内部信号。
MAC 错误事件在 system 域计数，VLAN drop 在 RX 域计数；短帧 GMII ER
真正注入有效字节，不能沿用超出短帧长度的固定 offset 22。

作者侧验证技能用于先登记预期、独立策略模型、背压稳定性和正负对照。
考生包不包含这些 host-only 用例、oracle、变异脚本或技能。

实际验证：streaming parser 正确对照与另一结构的 Kimi RTL 重放均通过
111/111；18 种特性负例和 5 种帧事务负例均可编译、且每个指定 witness
的全部种子失败；仅 coalescing 的正例通过。已知 GLM v3 原提交在
28/30/31/33/35/36 六组全部三种子失败，旧 0–27 仍通过；新判据的
作者侧重放功能分为 44/50，不覆盖其旧 trial summary。紧凑证据保存于
boundary_regression_qualification_v31.json，原 RTL 和冻结验收器不改。

## 独立并发、资源竞争与恢复回归

`evaluator.t08_stress_check` 是新增的主机侧资格检查，不进入考生包，不
修改已冻结 3.1 验收器、原 trial summary 或计分权重。发布新试验前应
同时跑正式功能验收与此资格检查；若将压力用例纳入正式计分，须另行
升级验收器版本、冻结输入并说明对应计分分组，不能静默改历史成绩。

历史作者资格检查先使用 gpt-6.1-sol 修复版及 Kimi 提交交叉校准。当前
已独立冻结完整 MAC 参考 RTL：`evaluator/reference/T08/rtl/`，包括
111 次映射功能回归、270 次并发回归和 11/29/47 三种子 1 GHz PPA。
公开证据见 `evaluator/fixtures/t08_reference_20261008/` 与任务 `FREEZE.json`。
故意带缺陷的 starter 仍不是参考答案；有限回归通过不等于证明无 bug。
考生包不包含参考答案、隐藏验收或冻结清单；旧 NoC 只保留为历史候选。

```sh
python3 -m evaluator.t08_stress_check /path/to/submission \
  --output /path/outside-submission/stress.json
python3 -m evaluator.t08_stress_qualification --baseline /path/to/passing-control \
  --output-dir /path/outside-control/stress-qualification --jobs 2
```

六组稳定编号，每组独立遍历 3 seed × 5 系统时钟 × 3 RX 相位，即每份
RTL 共 270 场。系统时钟为 80/100/120/125/160 MHz；TX/RX 均为 125 MHz，
RX 初相位为 0.01/2.3/7.99 ns。种子、频率、相位不是相互绑定的选项。

| case | 验证内容 | 必须观察的结果 |
| --- | --- | --- |
| 0 | TX 连续逐拍输入，32 个最大帧压满，再排空、重启、好坏帧交错 | 160 MHz 实际出现 ready 背压；每个好帧完整发出，坏帧不发布，无下溢或不恢复 |
| 1 | 持续全双工，RX 周期停顿、TCI/无标签交错、策略拒绝和坏 FCS | 输入和双向线端确实重叠；逐帧身份、CRC、边界、元数据、错误计数一致，无虚假溢出 |
| 2 | A/B 保留，C 溢出；C 尚未结束时释放空间，再发送 D | A/B 保留，C 不因空间回收而“复活”，D 可继续；六轮回绕每轮仅一次溢出 |
| 3 | 好帧/坏 FCS/策略拒绝，与消费者启动的十二个相位窗口交叉 | 仅完整好帧按序发布；拒绝不丢掉已保留批次，不串元数据或重复事件 |
| 4 | 已排队 RX 与正在补零/FCS 的 TX 同时协调复位，六种释放顺序 | 复位释放/稳定期无旧帧字节泄漏；新 epoch 全双工可继续，不保留旧元数据 |
| 5 | 保留 3,936 字节，在后继帧写入期间边读边回收空间，持续复用环形存储 | 所有预登记帧完整按序到达；不假定精确外部 full 点，无丢帧或不必要溢出 |

计分板只观察顶层外部端口；预期字节、帧长、完成资格与元数据在刺激前
登记。TX 不允许在好帧终止握手前出线，RX 不允许在物理报文完成前
提前交付。RX 背压期间 valid/data/last/user/tagged/TCI 必须稳定，状态
事件按各端口所属时钟域统计。协调复位明确清空被中止的计分板 epoch，
但不会忽略复位释放期间的旧帧泄漏。进展超时是诊断保护，不是新增
协议精确延迟指标。只有退出码、通过标记与指标记录同时满足才算通过。

负例只作用于临时 RTL 副本：TX 首次满后永久卡住、RX 溢出后误恢复写入、
RX 干扰 TX 线端、热复位后泄漏旧 TX 字节。每个负例必须可编译且所有
指定频率/种子/相位都产生明确断言失败；编译失败、进程超时或全局
watchdog 不算检出。TX 满载 witness 仅要求 160 MHz，低频输入未必压满。
另验只改变 coalescing 调度而无功能错误的完整 270 场正例。

本轮紧凑证据保存于 `evaluator/fixtures/t11_mac/stress_qualification_v1.json`。
原始日志位于证据所列作者 trial 目录；候选原提交/旧评分不变，作者重放
不计入候选 EDA 时间。GLM 通过这些正常长度并发用例不能推翻 3.1 已
检出的短帧缺陷。有限动态测试也不能证明全部死/活锁不存在、亚稳态
安全或穷尽内部 ACK 同拍优先级；当前没有新增形式验证或模拟亚稳态。
不引入规格外的单域复位、停 GMII 时钟、PAUSE/PFC、多队列或半双工仲裁。

此后新建 comparison 包会冻结 `t08_stress_check.py` 和 `tb_stress.sv` 于
主机 `frozen_judge`，不挂给考生。启动器在候选退出、结束 EDA 采样后，
持同一评分锁自动运行补充检查，保存 `grading/concurrency.json`，并在
summary 中记录 `concurrency_qualification`。它不改变正式功能 /50 的
分组权重；报告失败应单独调查，不能靠正式分数掩盖补充检查失败。
历史冻结 runner 不更新，不会追溯自动重评。

作者侧 SystemVerilog Verification / Testbench Patterns / Development 技能
只用于上述计分板、握手、复位与故障注入设计，不进入被测模型环境。
