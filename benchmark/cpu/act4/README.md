# T09 的 ACT4 生成配置

本目录固定 RV32I + Zicsr、单 hart、M-mode 启动、256 KiB 外部镜像和 `0x8003_F000` 的 `tohost`。`include_priv_tests=false`：题卡只实现有限 M-mode CSR/异常集合，完整 Sm 测试的前提不成立；该集合另由独立定向和差分用例验收。Sail 配置由锁定 ACT4 修订中的 CV32E20 样例改造，链接脚本也源自该样例；其原始许可为 Apache-2.0 WITH SHL-2.1。公开生成 ELF 的来源及哈希见[制品清单](../../../evaluator/act4_elfs/MANIFEST.json)。

已验证的生成命令，在 ACT4 锁定检出目录执行：

```bash
act /absolute/path/to/ic_bcmk/benchmark/cpu/act4/test_config.yaml \
  --test-dir /absolute/path/to/riscv-arch-test/tests \
  --coverpoint-dir /absolute/path/to/riscv-arch-test/coverpoints \
  --workdir /tmp/ic_bcmk_act4_work \
  --extensions I,Zicsr --jobs 8
python3 /absolute/path/to/ic_bcmk/evaluator/verify_act4_artifacts.py
```

生成所用工具为锁定 ACT4 `4a42cbd3756259bbc1f92a7d816bc2fd2bd551cb`、Sail 0.14.1、RV32 GCC 16.1.0、uv 0.11.33、Ruby 3.4.10 和 Bundler 4.0.21。环境准备见[依赖清单](../../../env/README.md)。该命令成功生成 45 个 ELF，最大 `PT_LOAD` 结束偏移为 `0x342c0`。仅生成并验证装载边界还不足以给 CPU 功能分；发布前须用完整参考 CPU 跑完这些 ELF，并建立提交差分、定向用例及变异体回归。
