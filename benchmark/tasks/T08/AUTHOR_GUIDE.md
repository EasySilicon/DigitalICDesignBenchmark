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
仓库外的测量目录，公开任务冻结清单为 `FREEZE.json`。
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

## 准备和运行

使用[通用启动器](../../runner/README.md)准备单题或套题试验，启动、认证和恢复均由同一 runner 配置管理，不再维护按模型命名的脚本。作者检查与发布门禁见 [benchmark/AGENTS.md](../../AGENTS.md)。

单独准备公开 T08 工作区及 EDA 工具包：

```sh
python3 benchmark/prepare_trial.py T08 /path/to/trial/workspace --orfs-root /path/to/ORFS
```

独立功能验收入口为 `python3 -m evaluator.t08_check /path/to/submission --output /path/outside/repo/functional.json`。候选交付、参考资格和模型场次分别保存，历史试验只查阅其原冻结版本，不与新试验混用。
