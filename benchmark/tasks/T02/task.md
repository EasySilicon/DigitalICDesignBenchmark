# T02 · CVDP 8 位串入并出寄存器

**来源与许可**：本题是 NVIDIA CVDP Benchmark Dataset 中 `cvdp_copilot_serial_in_parallel_out_0004`（类别 `cid003/easy`）的**修改衍生题**。原始题面、`docs/Documentation.md`、锁定修订和哈希见[sources.lock.yaml](../../sources.lock.yaml)；原数据集的非代码内容按 [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) 许可。相对于原题面，本题补充了无复位初始化不计分、连续滑动窗口、资源边界、交付格式和独立评分规则；完整署名、许可证与无背书声明见[第三方声明](../../../THIRD_PARTY_NOTICES.md#nvidia-cvdp-benchmark-dataset)。**交付**：模块 `serial_in_parallel_out_8bit`、自检测试和运行脚本。

**接口与需求**：输入 `clock`、`serial_in`，输出 `parallel_out[7:0]`。每个 `clock` 上升沿执行 `parallel_out <= {parallel_out[6:0], serial_in}`；两沿之间保持。此题**没有复位端口**，因此上电后的前 7 次沿输出不验收；从第 8 次沿起，结果必须等于最近 8 个采样 bit，最早采样 bit 位于 bit 7。

**资源边界**：8 位状态寄存器；不得增加隐藏初始化端口、数据表或外部辅助模块。

**验收与分值**：F=60：首个完整 8-bit 字 20；连续至少 256 个采样 bit 的滑动窗口结果 40。P=15：只在上升沿采样 10；沿间输出保持 5。原始 CVDP harness 作为兼容性检查；隐藏验收避免对未规定的初始值打分。
