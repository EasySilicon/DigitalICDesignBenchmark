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

当前适配器包括 Kimi CLI、Codex CLI、Claude Code 和 ZCode CLI。CLI 专属的用户目录、启动参数、事件解析、模型/思考强度校验和认证处理都留在 `adapters.py`；任务编排、容器、计时、归档和评分队列不依赖具体模型。

用户或外部 Skill 当前一律拒绝挂载。官方内置 Skill 可在配置中明确启用。若今后需要比较外部 Skill，必须新增经过审查的只读挂载策略，不能复用宿主全局目录。

## 本地配置

复制 `benchmark/runner.example.yaml` 到仓库外，填写本机路径。配置文件只保存路径和政策，不保存 API Key 或 OAuth 内容。不同 CLI 的关键字段如下：

| 适配器 | `binary` | `profile` / `options` |
|---|---|---|
| `kimi` | Kimi 可执行文件 | `profile` 指向 `.kimi-code`，并填写 `model_alias` |
| `codex` | Codex 可执行文件 | `profile` 指向 `.codex` |
| `claude` | Claude Code 可执行文件 | `profile` 指向宿主 `settings.json` |
| `zcode` | `zcode.cjs` | `options.provider_config` 指向用户管理的 provider JSON |

`grader.command` 是主机评分适配层，必须写出 `{task_id}`，并在 `{grading}/report.json` 生成符合仓库报告格式的结果。可用占位符为：`{task_id}`、`{trial_root}`、`{task_root}`、`{submission}`、`{grading}`、`{repo_root}`、`{frozen_repo}` 和 `{elapsed_seconds}`。认证、模型调用与评分命令互不共享目录。

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
