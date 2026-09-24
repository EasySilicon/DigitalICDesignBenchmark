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
