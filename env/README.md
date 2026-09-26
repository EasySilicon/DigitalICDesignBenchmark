# 安装与依赖清单

[English](README.en.md)

本页给下载者提供**分阶段**环境准备方法。仓库当前为 `design_only`：规范校验和十题独立端口公开冒烟可运行（T10 为设计稿级公开样例），ACT4 RV32I/Zicsr 的 45 个生成 ELF 也已提供；T01–T09 的隐藏验收器和 CPU 差分已在评测方环境试跑；T10 的隐藏验收及正式 PPA 评分仍待实现与冻结。运行 `check_env.py` 只能检查依赖是否存在，不能代替[发布门禁](../benchmark/methodology.md#发布门禁)。推荐 Linux x86-64、Docker/OCI 与至少 16 vCPU、32 GiB RAM、100 GiB 空间；正式榜单应发布单一镜像 digest，避免依赖用户系统版本。

## 依赖分组

| 层级 | 必需依赖 | 用途与状态 |
| --- | --- | --- |
| 规范检查 | Python ≥3.10、PyYAML、jsonschema | [requirements-spec.txt](requirements-spec.txt) 锁定了本地已验证版本；现在可用 |
| RTL 功能预检 | Verilator、Yosys、C++ 编译器、Python/cocotb | 编译/仿真及综合合法性；UVM/SVA 语法须在锁定镜像内按实际测试做冒烟验证；评测器尚未实现 |
| ASAP7 PPA | Yosys ≥0.58、OpenROAD、GNU make、ORFS 流程脚本、[仓库内 ASAP7 平台](../vendor/README.md) | 映射、放置、时钟树、布线、RC 与 OpenROAD 自身的时序/功耗报告；不单独安装另一套 STA 工具；参数和镜像 digest 待校准 |
| CPU 验收 | RV32 bare-metal GCC ≥15/objdump、Sail RISC-V 0.14.1、ACT4 锁定修订及 uv ≥0.11.33、Ruby ≥3.4.10、Bundler ≥4.0.21 | 编译 ELF、生成适用 ACT4 与参考轨迹；`check_env.py --profile cpu` 检查这些命令，I/Zicsr 配置与生成 ELF 已提供，完整 CPU 验收未完成 |
| 可选 | KLayout、波形查看器、综合可视化工具 | 调试或 GDS/DRC；目前 PPA 分数不要求 GDS/DRC，不进入参赛工具清单 |

所有参赛系统在同一预装镜像运行。参赛者的模型 API 与费用配置属于[评测资源规则](../benchmark/methodology.md#资源约束)，不应写入公开镜像。ASAP7 已随仓库提供，无需另行下载；ACT4、Sail 和 ORFS 的修订见[来源锁定](../benchmark/sources.lock.yaml)；正式版还需锁定二进制、Python/C++ 包及工具镜像 digest。

## 现在可运行：规范校验

在仓库根目录：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r env/requirements-spec.txt
.venv/bin/python env/check_env.py --profile spec
.venv/bin/python benchmark/validate_spec.py --verify-source
```

`--verify-source` 会下载并核对锁定的 CVDP 数据文件；离线时改为不带该参数。完整本地依赖报告：

```bash
.venv/bin/python env/check_env.py --profile all --orfs-root /path/to/OpenROAD-flow-scripts --act4-root /path/to/riscv-arch-test --verify-platform-hashes
```

`INCOMPLETE` 和非零退出码会指出缺项。工具存在也不能证明版本兼容或十题都可通过物理流程，须再做下述冒烟和[参数校准](../benchmark/ppa.md#参数探索与冻结门禁)。

如需先取得**锁定源码**以准备镜像，可在仓库根目录执行：

```bash
mkdir -p third_party
git clone https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts.git third_party/OpenROAD-flow-scripts
git -C third_party/OpenROAD-flow-scripts checkout 1ec57da7bf0f1491190cbea2673c2c01fb3bc3ae
git -C third_party/OpenROAD-flow-scripts submodule update --init --recursive
git clone https://github.com/riscv/riscv-arch-test.git third_party/riscv-arch-test
git -C third_party/riscv-arch-test checkout 4a42cbd3756259bbc1f92a7d816bc2fd2bd551cb
.venv/bin/python env/check_env.py --profile ppa --orfs-root third_party/OpenROAD-flow-scripts --verify-platform-hashes
```

ORFS 仓库提供流程脚本；ASAP7 工艺文件直接读取本仓库 `vendor/asap7/`。最后一行在尚未安装 Yosys/OpenROAD 时报告 `INCOMPLETE`。`third_party/` 已被 Git 忽略；Sail 发布包和 RISC-V 工具链的二进制版本、hash 需在正式镜像构建时冻结。

### Ubuntu 24.04 的 OpenROAD 本机安装

本机使用的官方预编译包是 `openroad_26Q2-1164-g08f67ee5ec_amd64-ubuntu-24.04.deb`，SHA-256 为 `f3f1eeaa18f327503f72cc45dcef5b1514ec2e89726ec53b4553bf4f951168a3`。Ubuntu 24.04 用户可下载并交给 apt 安装依赖：

```bash
curl -fL 'https://vaultlink.precisioninno.com/api/releases/26Q2-1164-g08f67ee5ec/openroad_26Q2-1164-g08f67ee5ec_amd64-ubuntu-24.04.deb/download' -o /tmp/ic_bcmk_openroad.deb
echo 'f3f1eeaa18f327503f72cc45dcef5b1514ec2e89726ec53b4553bf4f951168a3  /tmp/ic_bcmk_openroad.deb' | sha256sum -c -
sudo apt install /tmp/ic_bcmk_openroad.deb
openroad -version
```

Yosys 可从上述 OSS CAD Suite 的固定发布页选择相应 Linux 架构包；本机所用包的 SHA-256 为 `fec0e57d9e2a87f218f4ed83f1e10a495c5263fb20e3b40dd8b57fe5ec563197`。发行包解压后按其环境脚本加入 `PATH`，`yosys -V` 应报告 0.69+150。本机因无 sudo，把 OpenROAD 及依赖解压到用户目录并用 `~/.local/bin/openroad` 包装启动；这不改变仓库内的工艺文件。

## 正式镜像构建路线

1. **ASAP7 物理流程**：从[ORFS 官方 Docker 安装说明](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/docs/user/BuildWithDocker.md)建立镜像，在镜像内检出 `sources.lock.yaml` 指定的 ORFS 修订并初始化其子模块。官方[预编译安装说明](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/master/docs/user/BuildWithPrebuilt.md)要求 Yosys 至少 0.58；可用 [OSS CAD Suite 发布包](https://github.com/YosysHQ/oss-cad-suite-build/releases/tag/2026-09-24)安装兼容 Yosys，OpenROAD 可用[官方预编译包入口](https://vaultlink.precisioninno.com/)安装。`PLATFORM_DIR` 必须指向本仓库的 `vendor/asap7`。用 ORFS 自带 ASAP7 `gcd` 例子先跑通综合到布线，再跑已有九题参考实现；T10 的参考实现和物理校准尚待补齐。使用浮动 `latest` 镜像只能做探索，不得用于榜单。
2. **功能仿真**：在同一镜像安装 Verilator、C++ 编译器、Python/cocotb，并锁定版本。运行具体 SystemVerilog、UVM、SVA、覆盖率及门级单元模型的冒烟测试；工具只在已确认的子集内使用。Verilator 的[官方语言支持说明](https://verilator.org/guide/latest/languages.html)可作能力索引，实际版本的运行结果才是准入证据。
3. **CPU 验收**：按锁定的 [ACT4 README](https://github.com/riscv/riscv-arch-test/blob/act4/README.md)准备 `uv`、Ruby/Bundler、RISC-V GCC/objdump 与 Sail 0.14.1；固定 ACT4、Sail 修订以及本项目的 UDB、`rvmodel_macros.h`、linker script。ACT4 锁定修订的说明指定 Sail 0.14.1。先编译一条最小 ELF，分别交给 Sail 和 CPU 参考实现运行，再生成全套适用测试。不要从系统软件仓库自动拿不同版本替换。
4. **发布制品**：把所有 apt/pip/uv/Bundler 包版本、ORFS/ACT4/Sail/GCC/Verilator 修订、ASAP7 文件 hash、镜像 digest、`check_env.py --json` 输出和十题冒烟日志一并发布。正式安装应使用该镜像 digest；本页的源构建路线用于复现与移植。

本机已验证的探索环境：OpenROAD `26Q2-1164-g08f67ee5ec`、Yosys `0.69+150`、锁定 ORFS 修订 `1ec57da7bf0f1491190cbea2673c2c01fb3bc3ae` 和仓库内 ASAP7。在 ORFS 的 `flow/` 下，以本仓库绝对路径替换下列示例路径，可做 GCD 冒烟：

```bash
make DESIGN_CONFIG=./designs/asap7/gcd/config.mk \
  PLATFORM_DIR=/absolute/path/to/ic_bcmk/vendor/asap7 \
  YOSYS_EXE="$(command -v yosys)" \
  OPENROAD_EXE="$(command -v openroad)" \
  SYNTH_USE_SYN=0 NUM_CORES=8 route
```

本机该流程已成功生成 `5_route.odb`。正式榜单仍需统一约束、十题参考实现和功耗校准（T10 待完成）。

CPU 依赖探索已在 `/tmp` 检出 ACT4 锁定修订 `4a42cbd3756259bbc1f92a7d816bc2fd2bd551cb`，并安装 Sail 0.14.1 的 Linux x86-64 发布包，下载包 SHA-256 为 `de45a89748ca67a8a522b3ac0924c303b5609a16bb50d759bbd08c4d440df0eb`。ACT4 对 GCC 13 报版本错误后，改用 RISC-V GNU Toolchain 上游 `2026.07.15` 的 RV32 裸机 GCC 16.1.0 发布包，SHA-256 为 `ae36abbec394b29643154c1b4a1322e829937d04e82f41b47f9c27d3bd68e543`；其完整 ACT4 I/Zicsr 配置构建已成功。uv 0.11.33 发布包 SHA-256 为 `aa9fca823c03289fb6e3460b3dc864f3ea895cafaf9b99247701a67b17d1b018`，另用 mise 安装 Ruby 3.4.10、Bundler 4.0.21 并安装 ACT4 锁定 Ruby gems。带这些路径的 `check_env.py --profile cpu` 已返回 `ok=true`。45 个生成 ELF 已随[评测器制品](../evaluator/act4_elfs/)提供，且由[Sail 参考运行器](../evaluator/check_act4_sail.py)逐一验证到 `tohost=1`；这些 `/tmp` 工具路径不属于发布制品。

### ORFS 与本机 OpenROAD 26Q2 的探索兼容补丁

锁定 ORFS 修订 `1ec57da7bf0f1491190cbea2673c2c01fb3bc3ae` 的最终报告脚本使用 `set_extraction_rules_file`，本机 OpenROAD 26Q2-1164 不接受此命令。探索阶段在**干净的锁定 ORFS 检出**应用[兼容补丁](orfs-26q2-compat.patch)，改由 `extract_parasitics -ext_model_file` 加载本仓库 ASAP7 规则，并禁用无图形显示环境中的最终截图：

```bash
git -C third_party/OpenROAD-flow-scripts apply \
  /absolute/path/to/ic_bcmk/env/orfs-26q2-compat.patch
```

此补丁只解决本机这组工具的试跑兼容性；正式镜像须锁定补丁 hash 与工具版本，重新完成全题布线、RC、功耗和参考设计回归。探索入口为 `evaluator/ppa_probe.py`，它只产出面积与布线后时序诊断，不产生正式 PPA 分数。

当前不提供声称“一键安装完整 benchmark”的脚本，因为参考实现、测试器和 PPA 参数尚未冻结。先发布可核对的依赖与自检入口，完整镜像须随可执行评测器一起发布。
