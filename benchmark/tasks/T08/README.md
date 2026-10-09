# T08：1GbE MAC 修复与 VLAN 准入

[English](README.en.md)

长规格 + 既有 RTL：完成一个多处耦合的 TX/RX 帧事务回归修复工单，新增一个 RX VLAN admission
特性，包含逐帧配置快照、原子丢弃和终拍 metadata。限时 120 分钟。

`starter/rtl` 是考生可见的有缺陷起点，不是参考答案。准备器将它复制到
工作目录 rtl。上游八个真实模块超过 3,800 行，保留 MIT 许可证。
规格版本 `3.0-frame-transactions`：task.md 超过 4,000 行，单文件自包含；
包括完整协议、39 个端口、CRC/TCI 数值向量、81 个 RX 和 22 个 TX 场景、
时序轨迹与验证义务。不是把标准全文贴入题目，也不要求自行查外部标准。
精确定义以 task.md 为准：IEEE 802.3 GMII 子集 + IEEE 802.1Q C-tag，
不要求 PHY/驱动，不声称完整标准认证。

本题已作为 v0.3 套件 T08 冻结；计分为功能 /50 + PPA /50 + 时间 /5。三种子 1 GHz 参考基线已于 2026-10-08 冻结。
物理策略为 `2.0-lambdapdk-tdp-1ghz`：三域独立 1 GHz，评测方自动将
适用的同步读 FIFO 数组映射为固定双时钟 SRAM 研究宏。考生不必手工实例化
宏、不必下载库；仍须交完整可综合 RTL，保留两侧 4,096 深度和全部 metadata。
同步读周期、反压保持和 CDC 语义见 task.md §1.5。SRAM 全面积/功耗计入，
WC 标准单元与 TT SRAM 是混合角研究模型，不是硅签核；DRC 仅检查宏外布线
及引脚接入。参考已在该模型下满足 1 GHz；这不改变功能验收频率，也不代表硅签核。
新版起点改为重叠帧、丢弃回滚、背压恢复及地址回绕下的原子性修复；
附录 G 规定外部行为，不提供修改位置。一个工单不代表一行代码错误。VLAN 的接口和
宽 metadata FIFO 已预接，特性仍需自行实现，不以新增 RTL 行数评难度。

先完整阅读 task.md 和 acceptance.md，再修改工作目录 rtl/。
starter.sha256 记录起始材料，不约束修改后 RTL 的哈希。
`python3 evaluator/public_check.py T08 .` 是公开 smoke test，不是完整验收。
应自行补充独立 scoreboard、边界、随机和回归测试，并提交可执行 run.sh、
results.json、README.md 和 verif/；不要依赖外部缓存参数或网络下载。
无累计 token 硬上限；120 分钟是考生的实际执行时间预算。
