# Project Checkpoint

更新：2026-09-14。

## Current Stage / Goal

规划文档已落地；下一阶段 S0：环境与单卡基线。
目标：四周约 140 小时，形成面向推理系统岗位的多副本路由项目。具体预算、裁剪条件见 guide。
实际学习/实现投入：未知，尚未记录；不能由聊天经过时间推算。

## Workspace / Version

- 工作目录：`/nfsdata/nHome/chenjunkun/project/infra`。
- [已验证][h] 当前目录只含带教/规划文档，未发现实现代码。
- [已验证][h] `git status --short` 返回 `fatal: not a git repository`。未初始化 Git；无已知 branch/commit/diff。
- 本次变动：新增根目录 AGENTS.md、checkpoint、贡献表；修改 guide 与 mentor_prompt；原 guide 保存为 archive/guide_before_month_plan.md。S0 文档统一归档至 `doc/s0/`。
- 尚无实现源码、依赖环境、模型或运行结果。规划目录/未来功能不等于已存在。

## User-provided Constraints

- 一个月投递，每周约 35 小时，推理系统岗位。
- 8 张 5090；另一个服务器 4 张 V100-32G。
- GPU 访问方式、实际型号/显存、拓扑、驱动、兼容性和空闲状态待现场验证；不确定当前终端是否位于任一 GPU 服务器。

## Completed / Evidence

- 文档准备：已建立本月计划、三个带教约束、证据分类、贡献边界和阶段交接流程。
- 证据：AGENTS.md、doc/guide.md、doc/mentor_prompt.md、doc/CONTRIBUTIONS.md。
- S0 环境快照：已完成只读核验，证据见 `doc/s0/environment.md`。
- S0 CUDA 自检：在物理 GPU 3 当时无计算进程的前提下，以 `CUDA_VISIBLE_DEVICES=3` 成功初始化 PyTorch CUDA 并同步一个标量 kernel。证据见 `doc/s0/environment.md`。
- S0 vLLM 导入自检：以相同设备掩码成功导入 vLLM 0.29.0，未创建 engine 或加载模型；证据见 `doc/s0/environment.md`。
- 工程验收：环境清单、PyTorch CUDA 自检、vLLM 导入和单卡 API server/engine 启动通过。`results/s0/request_001.json` 与 `single_chat_stream.raw` 保留 `length` 截断场景；`request_002.json` 与 `single_chat_nothink.raw` 证明流式单请求正确输出 `12`、`finish_reason=stop` 和 `[DONE]`；用户实现的 client 成功/连接失败 record 分别保存为 `client_record_001.json`、`client_record_error_001.json`。CLI 0/1/2 路径均通过，证据见 `results/s0/cli_records.jsonl`、`cli_error_records.jsonl` 与 README；TPOT/性能基线尚未完成。
- 理解验收：用户已正确解释 `nvidia-smi` 的可见 GPU/进程快照不能证明项目 GPU 授权或框架兼容性，并通过 CUDA 可见设备重编号、首个 engine 资源上限、SSE 的传输结束/`length` 截断语义、prefill/decode/KV cache 基础、两副本缓存局部性、“单副本成功不等于多副本路由实现”、wall-clock/monotonic 计时边界、连接失败隔离、TPOT 口径、本地 tokenizer 派生计数边界及 tokenizer 生命周期/可测试性检查；尚待验收客户端计时扩展。

## Environment / Experiments / Metrics

[已验证][h] 当前终端为 `amax`，可见 8 张 RTX 5090（每张报告 32607 MiB）；NVIDIA 驱动 580.65.06，`nvidia-smi` 报告 CUDA 13.0。时间、占用快照与拓扑见 `doc/s0/environment.md`。
[已验证][h] 默认 `python` 为 3.13.13，无法导入 PyTorch。该结果只适用于此解释器。
[已验证][h] `.venv` 创建时由 `uv 0.11.14` 选用 CPython 3.11.15，初始为空环境；后续安装与当前状态见下一条及 `doc/s0/environment.md`。
[已验证][h] `.venv` 后续已安装 vLLM 0.29.0、PyTorch 2.13.0+cu130；`CUDA_VISIBLE_DEVICES=3` 下，PyTorch 检出 1 张可见 RTX 5090（计算能力 12.0）并完成标量 kernel。该结果不代表 vLLM/模型服务已通过。
[已验证][h] S0 基线模型 `Qwen/Qwen3-0.6B` at `c1899de289a04d12100db370d81485cdf75e47ca`、dtype `bfloat16` 已下载至 `models/Qwen3-0.6B-c1899de/`；`model.safetensors` 为 1503300328 bytes，SHA-256 与远端公布值一致。选择、命令和哈希见 `doc/s0/baseline.md`。尚未加载。
[用户提供，未现场核验][h] 用户允许使用任一当时空闲 GPU；每次 GPU 操作前仍须重新检查占用，空闲快照不代表排他分配或性能测试授权。
框架/版本、模型/revision、dtype 与 Python 依赖环境均已选择并局部核验；vLLM engine、模型快照、实际推理行为仍未核验。
推理命令、engine 配置、trace、原始结果路径：未建立；模型快照路径见 `doc/s0/baseline.md`。
TTFT、TPOT、throughput、goodput、显存及缓存命中：Not measured。

## Decisions / Unverified Hypotheses

- 按四周计划集中做多副本前缀与负载路由；先验证 1 卡，再做 2 副本。
- TP/CUDA/8 卡实验不作为本月必做。先从 5090 环境做兼容性验证，V100 是待验证备选。
- 联合策略可能在部分 workload 改善指标：[待验证][m]，不得预填收益。
- 前缀缓存是否可以直接观测、底座是否适合改造：未知，需要源码及运行核验。
- 用户提出 `nano-vllm` 作为候选，但未给出仓库 URL/commit；该名称对应多个不同项目，尚未形成可复现的底座选择。[待验证][h]
- 若用户指的是 `https://github.com/WhiteJonas/nano-vllm`，其 README 声明为单卡单进程、只支持 Qwen3 的教学引擎，已有前缀缓存和连续批处理；它适合作为原理阅读参考，但不能直接满足双副本服务与路由项目的运行时边界。[已查资料，未现场验证][h]
- [已确认][h] 用户选择官方 vLLM 作为实际 serving runtime，nano-vllm 仅作原理阅读参考。vLLM 官方资料声明支持 Linux、Python 3.10--3.13、计算能力 7.5+ GPU、OpenAI 兼容服务和自动前缀缓存；当前 `.venv` 仅满足 Python 版本，尚未验证安装或运行。
- [已验证][h] 导师的首次 `uv` 安装尝试曾在大体积下载阶段以 SIGINT 退出（130）。之后用户委托另一编码代理完成安装；现场核验 `.venv` 含 vLLM 0.29.0、PyTorch 2.13.0+cu130，`uv pip check` 对 195 个包通过。详情见 `doc/s0/environment.md`。
- [已确认][h] S0 采用 `Qwen/Qwen3-0.6B`、revision `c1899de289a04d12100db370d81485cdf75e47ca`、bfloat16；模型小服务于快速验证，不把结果外推为大模型性能。权重、KV cache 和运行时预算分开记录。详情见 `doc/s0/baseline.md`。
- [已确认][h] 首个单卡 engine 计划使用 `gpu_memory_utilization=0.5`、`max_model_len=2048`、请求 `max_tokens=128` 和 `max_num_seqs=2`；参数边界与用户理解验收见 `doc/s0/baseline.md`。尚未实际启动。
- [已验证][h] 用户首次直接执行 `.venv/bin/vllm` 的 server 启动在 FlashInfer JIT 采样 kernel 阶段失败，报 `FileNotFoundError: ninja`。`ninja 1.13.2` 实际存在于 `.venv/bin`；推测并经 PATH 核验，子进程未继承 venv `PATH` 是直接原因。激活 venv 后重试即可验证。详见 `doc/s0/baseline.md`。
- [用户提供启动日志][h] 激活 `.venv` 后，单卡 server 以物理 GPU 4 的设备掩码启动完成，绑定 `127.0.0.1:8000`；日志含 `Application startup complete`。对 `/` 的 404 为预期，详情见 `doc/s0/baseline.md`。
- [已验证][h] 首个 `3+9` 流式请求的 body 与完整 SSE 响应已保存为 `results/s0/request_001.json` 和 `results/s0/single_chat_stream.raw`。它以 `finish_reason=length` 截断，未回答 `12`，是可复现的截断场景；下次正确性请求应在项目根目录保存原始响应，并用 `chat_template_kwargs.enable_thinking=false` 做短答案检查。详见 `doc/s0/baseline.md`。
- [用户提供响应][h] 后续 SSE chunks 包含 `结果是12。没错`，证明该次输出内容答对；最后仍为 `finish_reason=length` 后跟 `[DONE]`。它验证内容正确但不是自然停止；没有完整 request body、确切 token 上限或项目内原始 artifact。详见 `doc/s0/baseline.md`。
- [已验证][h] `results/s0/request_002.json` + `single_chat_nothink.raw` 记录关闭思考模式后的最小流式请求：输出 `3 + 9 等于 12。`，以 `finish_reason=stop` 后跟 `[DONE]` 正常结束。未采集任何 timing/cache/性能结果，详见 `doc/s0/baseline.md`。
- [已验证][h] 用户 CLI 实现路径为 `src/run_single_cli.py`，实际参数名为 `--endpoint`、`--request-file`、`--replica-id`、`--jsonl-file`；静态编译通过。运行验收尚未完成。
- [已验证][h] 2026-09-17 `ss` 显示 127.0.0.1:8000 无监听进程；此前 server 启动证据仅代表历史运行，当前必须重启才可验收 CLI 成功路径。
- [已验证][h] 随后 `/v1/models` 现场返回 `qwen3-0.6b-s0`、本地模型路径与 `max_model_len=2048`，8000 可用于 CLI 验收；CLI 0/1/2 结果见 `results/s0/README.md`。

## Learning State / Contributions

用户已经解释的核心概念：尚未验收。
需在 S0 检查：请求生命周期、prefill/decode、KV cache、客户端计时与内部计时。
理解小变式：S0 基线形成后布置；尚未通过。
贡献索引：doc/CONTRIBUTIONS.md。

## Next Task

唯一任务：用户扩展 client/CLI，加载一次 tokenizer 并记录 completion token 数；暂不做多请求或性能统计。

- 输入：更新后的 schema、固定本地 tokenizer 路径 `models/Qwen3-0.6B-c1899de/`，当前 client/CLI 实现。
- 操作：用户修改 `src/single_request_client.py`，显式接收已加载 tokenizer，并在 transport 成功后对 `output.text` 编码；修改 `src/run_single_cli.py`，新增必填 `--tokenizer-path`，用 `AutoTokenizer.from_pretrained` 一次加载后传给 client。tokenizer 加载失败为 CLI exit 2；编码失败保留 transport success 并写 `output.tokenization_error`。不得写多请求循环、路由或统计。
- 产出：更新后的两份用户实现和待运行命令。
- 通过标准：completion token 成功计数来自传入 tokenizer；真实/ fake tokenizer 都可注入 client；tokenization 错误不被顶层 error 混淆；模块导入无网络/GPU/模型加载副作用。

## Session Handoff

当前会话：带教规则与本月路线落地。可留在当前会话继续 S0。
建议下一阶段会话主题：S0 环境核验与单卡推理基线。
尚未创建新会话。

启动语：

> 按 AGENTS.md 读取带教规则、guide 和 checkpoint，核对当前实现及实验版本。接续 Next Task：先确认执行服务器与 GPU/软件环境，形成环境记录，再选底座。一次只推进一个最小任务；核心设计和实现由我完成，你负责审查、验收、文档与会话交接。
