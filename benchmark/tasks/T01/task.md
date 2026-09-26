# T01 · CVDP 8×3 优先编码器

**来源与许可**：本题是 NVIDIA CVDP Benchmark Dataset 中 `cvdp_copilot_8x3_priority_encoder_0001`（类别 `cid003/easy`）的**修改衍生题**。原始 prompt、锁定修订和哈希见[sources.lock.yaml](../../sources.lock.yaml)；原数据集的非代码内容按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可。相对于原题面，本题补充了完整真值表验收、零输入语义、资源边界、交付格式和独立评分规则；完整署名、许可证与无背书声明见[第三方声明](../../../THIRD_PARTY_NOTICES.md#nvidia-cvdp-benchmark-dataset)。**交付**：可综合模块 `priority_encoder_8x3`、自检测试和运行脚本。

**接口与需求**：输入 `in[7:0]`，输出 `out[2:0]`；纯组合逻辑。`out` 等于最高置位输入的下标，优先级从 bit 7 降到 bit 0；输入为 0 时输出 0。不得引入时钟、状态或延迟。输入改变后的组合稳定值即为验收结果。

**资源边界**：无寄存器、RAM、ROM、黑盒或外部依赖。参考工具链下记录门数，但不按门数排名。

**验收与分值**：F=60：8 个单热输入 20；所有多热输入 40。P=15：零输入 10；同一次仿真中反复改变输入、无历史状态依赖 5。隐藏验收遍历全部 256 个输入，公开测试只放少量示例。原始 CVDP harness 作为兼容性检查；本题最终分数由本规范的完整真值表决定。
