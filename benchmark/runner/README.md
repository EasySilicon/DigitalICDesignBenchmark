# 正式试验启动器

`benchmark.runner` 用一套固定状态机运行整套题目，把模型做题与主机评分拆成两条流水线：候选任务始终逐题串行，已经交卷的任务进入独立的单路评分队列。评分进程即使在全局物理实现锁上等待，也不会阻塞下一题启动。

## 设计边界

- 时间、CPU、内存、磁盘和 token 策略只读取 `benchmark/manifest.yaml`。本地配置不能增加 token、轮次、费用或模型响应时限。
- 每题使用新工作区、新 Agent home、新容器和新会话；只挂载本题工作区、公开 EDA 工具包和显式声明的工具路径。
- 仓库、验收器、参考 RTL、其他提交和历史会话不得挂入候选容器。
- 交卷后立即保存不可变 `submission/`；重启时已有 `agent_result.json` 的题目不会再次调用模型。
- 评分器只在主机运行，并通过全局文件锁保持物理流程单路串行。
- `grading/Txx/job_status.json` 明确区分等待全局锁、正在评分、失败与完成；长任务每分钟留下评分心跳。
- 配置、冻结输入或模型绑定发生变化时拒绝续跑，不自动“修补”证据。
- 认证值不写入 trial。Kimi 只把同一个可轮换 OAuth 目录直接挂入各题，避免多个凭证副本形成相互失效的刷新链。

CLI 专属的用户目录、启动参数、事件解析、模型/思考强度校验和认证处理都留在 `adapters.py`；任务编排、容器、计时、归档和评分队列不依赖具体模型。

Codex 每题启动新的 `exec` 进程，并在该题独立的私有 CLI home 中保留原生会话记录，以便核对中断任务的用量。下一题使用新的 home，不继承上一题记录；这些记录留在仓库外。

用户或外部 Skill 当前一律拒绝挂载。官方内置 Skill 可在配置中明确启用。若今后需要比较外部 Skill，必须新增经过审查的只读挂载策略，不能复用宿主全局目录。

## 本地配置

复制 `benchmark/runner.example.yaml` 到仓库外，填写本机路径。配置文件只保存路径和政策，不保存 API Key 或 OAuth 内容。不同 CLI 的关键字段如下：

| 适配器 | `binary` | `profile` / `options` |
|---|---|---|
| `kimi` | Kimi 可执行文件 | `profile` 指向 `.kimi-code`，并填写 `model_alias` |
| `codex` | Codex 可执行文件 | `profile` 指向 `.codex` |
| `claude` | Claude Code 可执行文件 | `profile` 指向宿主 `settings.json` |
| `zcode` | `zcode.cjs` | `options.provider_config` 指向用户管理的 provider JSON |
| `antigravity` | 固定版本的 `agy` | `profile` 指向仓库和 trial 之外的私有 OAuth 文件 |

`task_language: en` 使用各题完整的 `README.en.md` 生成英文题面和验收入口；默认保留原始题面。
Codex 可设置 `agent.options.network_access: false`，同时设置 `agent.tools.web: false`，
通过 CLI 的命令沙箱禁止工具进程创建网络连接；CLI 本身仍可连接模型服务。
该模式使用支持权限 profile 的 Codex CLI，文件访问继续由外层 Docker 挂载隔离。
Antigravity 的 `model` 使用包含思考强度后缀的完整 CLI 模型 ID。答题命令由 Antigravity 的终端沙箱执行，
宿主需支持其嵌套命名空间及 `linux-sandbox` AppArmor 配置。
`proxy_url: http://127.0.0.1:7897` 显式覆盖容器中大小写的 HTTP/HTTPS/ALL_PROXY，
避免继承宿主上另一套代理。容器使用 host 网络，因此该地址指向宿主的代理监听口。
Claude 的 `options.oauth_credentials` 可指向仓库和 trial 之外的专用 OAuth 凭证文件；
每题只复制该凭证到独立私有 home，交卷后将更新的凭证传给下一题，不挂载宿主插件、skills 或历史会话。
使用该选项时不要同时运行共用同一凭证链的其他 Claude 会话。

通过 Claude Code 接入第三方 API 时，可在 `agent.options.provider_capabilities` 显式声明服务端的
`context_window`（输入与输出合计）和 `response_window`（单次输出），单位均为 token。
适配器据此设置 CLI 上下文、单次响应和自动压缩窗口，不继承宿主配置中的输出限制。
这些值必须对应已确认的服务端能力并保存在试验配置中，不是整题 token 预算；总用量仍只记录、不截停。
提供商自行生成思考时使用 `reasoning_effort: auto`，不发送 Anthropic 专属的 effort 或扩展思考预算。
API 认证 profile 应独立于 OAuth profile；协议转换服务使用独立实例和端口，不切换另一场试验的全局配置。

初始化会把配置指定的仓库文件复制到 trial 的 `frozen/ic_bcmk/`，并在
`snapshot_inventory.json` 中逐文件记录哈希。`run_manifest.json` 的 `frozen_sha256`
标识这份初始文件快照；`source_commit` 仅记录来源仓库的 Git 基线，
`source_worktree_dirty: true` 表示快照还包含未提交改动，不能把它当成纯提交版本。
不同模型可以使用相同快照，但各自的题目工作区、私有 CLI home、会话和交付 RTL 独立。
模型容器只接收准备后的公共材料，不挂载私有评估器。trial 外层的额外监控、续跑或
评估修复脚本不自动属于初始快照，使用时应另存来源及哈希。

`grader.command` 是主机评分适配层，必须写出 `{task_id}`，并在 `{grading}/report.json` 生成符合仓库报告格式的结果。可用占位符为：`{task_id}`、`{trial_root}`、`{task_root}`、`{submission}`、`{grading}`、`{repo_root}`、`{frozen_repo}` 和 `{elapsed_seconds}`。认证、模型调用与评分命令互不共享目录。

T10 的分组评分可通过 `score_run.py score_input.json --t10-functional-report functional.json`
或 `build_t10_score_input()` 绑定独立验收证据。该入口分别判断持续流安全门槛和其他组的数值通过情况，
保留通过的 MM-SYSTOLIC 分数；完整数值验收仍是 PPA 与时间分的前提。

共享主机可显式设置 `grader.cpu_weight`（1–10000），由评分启动器在独立的 systemd 用户 scope
中执行评分，并记录实际 cgroup、CPU 时间、节流和压力信息到外部评分目录的 `resource_usage.json`。
权重只影响调度优先级，不增加线程、模型资源或评估时限，也不代表独占 CPU。配置后若不能应用该权重，
评分会报基础设施错误，不静默退回普通优先级。复核墙钟超时前，应检查资源竞争；恢复测量使用新目录并保留旧现场。

先进行只读预检：

```bash
python3 -m benchmark.runner /path/to/local-runner.yaml --preflight-only
```

确认生成的 `run_manifest.json` 后启动：

```bash
tmux new-session -s ic-bcmk-run \
  "cd /path/to/ic_bcmk && python3 -m benchmark.runner /path/to/local-runner.yaml"
```

向 trial 根目录写入 `STOP` 只会阻止下一道题启动，不会抹除正在运行或已经交卷的现场。

## 必须保持的回归性质

测试覆盖以下不变量：

- 上一题评分被阻塞时，下一题仍然启动；
- 评分器自身永远只有一个并发实例；
- 未显式声明 Skill/联网/多 Agent 政策时拒绝配置；
- 任意隐藏 token、轮次或费用限制均被拒绝；
- 容器使用清单中的资源，允许交换空间，不增加 PID 上限；
- 私有评分目录不能挂进候选容器；
- Kimi OAuth 直接共用一条可轮换认证链，密钥不复制进 trial；
- 配置或冻结输入变化后不能冒充原试验续跑。

运行回归：

```bash
python3 -m unittest \
  benchmark.test_runner_config \
  benchmark.test_runner_container \
  benchmark.test_runner_pipeline \
  benchmark.test_runner_adapters \
  benchmark.test_runner_orchestrator
```
