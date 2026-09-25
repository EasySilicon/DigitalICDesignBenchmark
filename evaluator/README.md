# 独立端口验收器的公开可执行样例

`public_check.py` 只读取参赛提交的 `rtl/files.f` 和 RTL 源码，使用**评测方自己的** T01–T06 的测试平台编译并检查固定 DUT 端口。它不会调用提交内的 `run.sh`、`verif/` 或 `results.json`。例如：

```bash
python3 evaluator/public_check.py T01 /path/to/submission
python3 evaluator/public_check.py T02 /path/to/submission --seed 1234
python3 evaluator/public_check.py T03 /path/to/submission --width 32 --depth 16
python3 evaluator/public_check.py T04 /path/to/submission
python3 evaluator/public_check.py T05 /path/to/submission --n-inputs 8 --width 32
python3 evaluator/public_check.py T06 /path/to/submission --depth 16 --width 32
```

编译与仿真在独立临时目录执行，失败以非零退出码和 JSON 摘要报告。这里的用例是**公开冒烟样例**，不用于正式评分；T07–T09 的公开测试、全套隐藏验收器、参考实现和变异体仍待实现。隐藏验收器将使用相同连接原则，但存放在不暴露给参赛工作区的评测服务中。

## T06 双级同步结构检查原型

`cdc_2ff_check.py` 读取 [Yosys `write_json`](https://yosyshq.readthedocs.io/projects/yosys/en/0.46/cmd/write_json.html) 导出的展平网表，按触发器 `CLK/D/Q` 连线检查 `wr_clk→rd_clk` 和 `rd_clk→wr_clk` 两方向是否各有至少 `$clog2(DEPTH)+1` 条**直接、隔离的双级寄存器链**。第一级只能连到同目的时钟、同异步复位的第二级；跨域组合逻辑或第一级扇出到功能逻辑会报错。运行入口：

```bash
python3 evaluator/cdc_2ff_check.py /path/to/t06_yosys.json --depth 8
python3 -m unittest evaluator.test_cdc_2ff_check -v
```

回归用 Yosys 生成多种网表：分离寄存器和 packed 移位寄存器的双级链通过；一级链和第一级直接暴露给输出的变异体失败。本工具**尚非完整 CDC 签核**：未覆盖所有存储体边界、Gray 码生成和一次只翻转一位的证明、异步复位释放、MTBF 及物理实现。正式 AC-31 需要在多种等价 RTL 写法和缺陷变异体上校准这些规则，不能直接以本原型的 PASS 给满分。可参考开源 [rtl-buddy-cdc 规则集](https://github.com/rtl-buddy/rtl-buddy-cdc) 扩展，但需固定版本并处理误报与豁免。
