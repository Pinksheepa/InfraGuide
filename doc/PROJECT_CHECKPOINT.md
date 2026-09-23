# Project Checkpoint

更新：2026-09-23（S1 双真实副本 RR smoke 已验收并冻结；P0.1 候选 trace 已完成真实单卡 smoke，进入 P0.3 源码调用链阅读）。

## Current Stage / Goal

S0 已完成单卡运行、单请求 client/CLI 功能验证及最小串行 benchmark 的成功/连接失败/零测量参数路径。S1 已完成两个真实单卡 replica、完整 SSE、四请求 Round Robin 与一个无 failover 的 502 验收，Router 功能从此冻结。P0.1 已完成候选 trace 的一次真实单卡 smoke：4/4 成功，两个 short 与 long 客户端 in-flight 重叠；它不是 cache-controlled baseline 或性能结论。当前进入 P0.3，只读建立固定版本 vLLM Scheduler 调用链；尚未修改 Scheduler 或声称性能收益。
本月主线与投递目标不变；实际累计投入未知，不能按日历或对话时间推算。
执行约 2–4 小时可运行工作包，集中审查，不逐字段或逐句验收。

## Workspace / Version

- 工作目录：`/nfsdata/nHome/chenjunkun/project/infra`。
- 本次已读取实现：`src/single_request_client.py`、`src/run_single_cli.py`、`src/run_benchmark.py`、`src/round_robin_router.py`、`src/run_router.py`、`src/run_scheduler_workload.py`。
- Git 已初始化；基准为 `main`/`origin/main` 的 `ae01111 s1: validate real round-robin streaming smoke`。本工作包开始时工作树干净；当前未提交 P0.1 新增 `src/run_scheduler_workload.py` 与 `workloads/p0/scheduler/`，以及本轮出现但不属于该 runner 的 `src/run_benchmark.py` 改动。尚未 commit/push。
- [已验证][h] 本轮 `py_compile` 覆盖现有四个 S1/S0 文件，且 `src/run_router.py --help` 可运行。当前目录没有 `tests/`；所以 checkpoint 中的 mock-upstream 测试只能作为历史记录，不能称当前可复现。
- [已验证][h] 2026-09-22 前置快照中 GPU 0--7 均有计算进程（利用率约 47--98%）；8000、8001、8080 当时未监听。端口空闲不构成 GPU 使用授权，也没有为本项目启动或停止任何进程。

## Completed / Evidence

- 环境及底座：历史核验与选择见 `doc/s0/environment.md`、`doc/s0/baseline.md`。
- vLLM 0.29.0 / PyTorch 2.13.0+cu130 / Qwen3-0.6B revision `c1899de289a04d12100db370d81485cdf75e47ca` / bfloat16；这些来自项目记录，本次未重测安装环境。
- 单卡 server 与自然停止流式请求已有记录：`results/s0/request_002.json`、`single_chat_nothink.raw`。不代表 server 现在仍在线。
- 用户已实现 SSE client 和 CLI；成功/连接失败原始记录及 CLI 0/1/2 验收见 `results/s0/README.md` 和对应 JSON/JSONL 文件。
- 用户已实现本地 tokenizer 输出文本重编码、首/末非空 content 与 DONE 时间、每请求 JSONL 记录、2 次 warmup + 10 次串行 measure 及 JSON summary，源码见 `src/single_request_client.py`、`src/run_benchmark.py`。
- [已验证][h] `results/s0/benchmark/benchmark_run_001.jsonl` 有同一 `run_id` 的 12 条记录（2 warmup、10 measure）；全为 HTTP 200、`done_seen=true`、`finish_reason="stop"`、`completion_tokens=12`，计数来源为 `local_reencode_output_text`。相应 summary 位于 `benchmark_run_001_summary.json`。
- [已验证][h] 审查从 raw JSONL 独立重算 measure 的 TTFT、E2E、TPOT 有效样本数、mean、median，与 summary 完全一致。raw SHA-256：`9654c945c8f8798be24fbc8f150d91ab8ec5cd5281c4155429f3df5d6441e12a`；summary SHA-256：`4f660ba86b588afaf15a220c7be1c646118df93b7f806ebaebfb72fc8b1005bc`。

## Metrics / Limitations

- [已验证][h] 本轮 10 个 measure 的 TTFT mean/median 为 15.1848714 / 15.0663135 ms，E2E 为 33.63764 / 33.3349055 ms，TPOT estimate 为 1.5191442 / 1.5124386 ms。数值只验证本地、小 prompt、串行测量流程，不能推导吞吐、稳定尾延迟或策略收益。
- [已验证][h] TPOT 的分子是首个至最后一个非空 `delta.content` 的客户端 monotonic 时间，分母是本地重新编码的输出 token 数减一。SSE chunk 不等同 decode token，重编码也不保证等同服务端 token ID；因此该字段是 estimate，不是逐 token ITL 或服务端原生 TPOT。
- 多副本性能、真实前缀命中、goodput 仍未验证。本次不对底座协议是否提供可靠 usage 字段作假设。
- [已验证][h] `benchmark_run_error_001.jsonl` 有一条针对未监听 18080 的 measure 失败记录：`success=false`、`http_status=null`、`done_seen=false`、first/completed/TPOT 时间均为 null，并保留连接拒绝错误；其 summary 只计 1 个 measure failure，三项 metric 均为 0 个有效样本和 null mean/median。该请求未访问 8000 的 vLLM server。raw SHA-256：`9361703468f4404fcac6012e135efe7286ea1e6acdb59187dacf87cc979aa932`；summary SHA-256：`9fbba416df170128913e41ac043dd17524e725d2eb3933199f03051c1eb9d40b`。
- [已验证][h] 当前 runner 将 `repeat <= 0` 作为参数错误。以 `warmup=0`、`repeat=0` 运行返回 exit 2，且在读取 request/tokenizer 或访问端点之前结束，未创建 raw/summary 输出文件。参数错误文本仍写为 “warmup/repeat must be non-negative”；其文字不精确，但不影响现有行为。
- [已验证][h] S1 Router 源码位于 `src/round_robin_router.py`，启动入口为 `src/run_router.py`。它在有效 `stream=true` 请求到达时、连接 upstream 前持锁选择一个 replica 并推进单进程 RR cursor；每个请求写 `route_decision` 与 `route_terminal` JSONL 事件，不做 retry/failover。
- [历史记录，当前不可复现][h] 2026-09-21 checkpoint 记载 `PYTHONPATH=src .venv/bin/python -m unittest -v tests/test_round_robin_router.py` 曾通过三项 mock-upstream 测试；但 2026-09-22 实际工作树中没有 `tests/` 目录，故该命令当前会因文件缺失失败。无论如何，它都不证明真实 vLLM、GPU、网络或客户端取消行为。
- [已验证][h] S1 真实验收位于 `results/s1/rr_smoke/run_001/`。两个 vLLM API/engine 使用独立 PID、port 8000/8001、`world_size=1`；两端 `/v1/models` 均返回固定模型。用户提供的物理配置为 `replica-0=GPU 5`、`replica-1=GPU 6`；log 未独立保存 `CUDA_VISIBLE_DEVICES`，但两端启动时均有约 30.85/31.36 GiB free memory，且整个请求窗口重叠。
- [已验证][h] 四个 normal client request ID 与 route decision/terminal 一一对应，严格为 `replica-0 -> replica-1 -> replica-0 -> replica-1`；均 HTTP 200、`done_seen=true`、`finish_reason=stop` 和 terminal `completed`。`sse_raw_005.body` 含且仅含一个 `[DONE]`。详见该目录 README。
- [已验证][h] 第五个 raw 请求后，下一请求唯一选择 `replica-1`；其 terminal 为 `upstream_connection_failed` / `ConnectError`，client 为 HTTP 502、exit 1，未产生 fallback decision。用户确认以 Ctrl-C 停止自己启动的 `replica-1`；停止动作本身未被 log 独立记录。
- [已验证][h] P0.1 薄 runner 位于 `src/run_scheduler_workload.py`。它复用同步 `run_one_request`，以 `max_in_flight` 限制并发；每条 raw record 保存 trace、计划/实际提交时间、客户端调度延迟、SSE 结果和 engine-config SHA-256。它将 server queue time 明确写为 `N/A`，并按 all/short/long 统计 TTFT p50/p95/p99、TPOT estimate、成功 request/s、output tokens/s 与失败数。
- [已验证][h] 静态候选 trace 位于 `workloads/p0/scheduler/p0_1_long_short_smoke_candidate.json`；`--validate-trace` 对当前固定 tokenizer/chat template 校验得到 1 条 long 为 1185、3 条 short 为 33/27/39 个本地 prompt tokens，prompt SHA-256 与 trace 相符。fixture 为 AI 辅助生成后冻结的文本，runner 运行时不生成 prompt。
- [已验证][h] `results/p0/scheduler/run_001/` 是直连 GPU 7 单卡 engine 的候选 smoke：raw 有 4 条 measure record，均 HTTP 200 / `success=true`；`p0-1-short-001`、`p0-1-short-002` 的实际提交均位于 long 的实际提交与 client terminal 之间，`short-003` 不在该区间。完整配置、命令、原始 JSONL、summary、README 与源码/trace SHA-256 见该目录。
- [已验证][h] run_001 的 long 请求以 `finish_reason="length"` 完成，本地重编码 completion token 为 64，等于固定输出预算；三个 short 为 `stop`。这只记录请求结果，不能推导回答质量、Scheduler 根因或策略收益。
- [待验证][h] run_001 前 prefix-cache 状态未知，且没有 P0.1 warmup；样本仅 4 条。因此候选 trace 有本次客户端重叠证据，但尚不是冻结的性能 workload，也不能用 summary 中的 p95/p99、throughput 作稳定比较。

## Learning State / Contributions

S0 对话已检查：GPU 快照边界、设备重编号、SSE/length/DONE、prefill/decode/KV cache、wall/monotonic、TPOT 基本分母、文本重编码局限、tokenizer 一次加载与 fake 注入、transport 与后处理错误区分。
这些属于对话理解证据，不等同于扩展代码已通过；不再逐项重复口述。
S0 已集中检查：token 来源/TPOT 端点与说明一致，warmup 未计入 measure 指标，runner 的连接失败记录不进入指标，零测量被拒绝。工程验收通过；既有对话与代码/结果共同构成理解证据，不再重复口述。
贡献明细：`doc/CONTRIBUTIONS.md`。

## Next Task — P0.3 工作包 2：固定版本 Scheduler 调用链（只读）

预计用户工作量 2–4 小时，属于规划估计；若明显超出，导师收缩范围或直接解释阻塞，不增加口述关卡。

目标：以 run_001 使用的 vLLM `0.29.0` 为当前运行时锚点，另固定可审查的 vLLM 源码 SHA；只读追踪 request 入队、`Scheduler.schedule()`、running/waiting、token budget、KV allocation、`SchedulerOutput` 至 worker/model runner 的调用链。不得修改 Scheduler。

输入：`results/p0/scheduler/run_001/`、实际 import 的 vLLM `0.29.0`、以及后续固定的 upstream checkout。产出：`doc/scheduler-notes.md`，每个核心判断绑定 SHA、文件和行号；明确本地运行时与 upstream SHA 的差异。不得把 client E2E 差值伪装为 server queue time。

需要回答：请求如何进入 waiting、何时进入 running、prefill/decode 如何共享预算、长 prefill 的进度状态、chunk 受哪些预算约束、KV capacity/admission/preemption 的关系、以及 `SchedulerOutput` 的实际消费点。先不写 patch、不解释 run_001 的原因、更不报告优化收益。

通过标准：`scheduler-notes.md` 的每条核心答案可从固定代码位置复查；清楚区分源码事实、run_001 客户端事实和待验证的服务端行为；没有新代码、Scheduler patch 或收益主张。

## Session Handoff

已有 S0 会话：`01a09f25-acb3-7943-8750-72676d6fc5da`；不必新建或重启项目。
本次复盘读取了 read_thread 元数据；其消息 items 为空，随后核对了该 task 对应 09-16/09-17 本地 session 原文及当前代码。
旧 checkpoint 备份：`doc/archive/checkpoint_before_pacing_2026-09-17.md`，其中矛盾状态仅供历史追溯。

进入 P0.1 的启动语：

> 读取更新后的 AGENTS.md、guide 和 PROJECT_CHECKPOINT.md。S1 已冻结，P0.1 run_001 已证明两个 short 的客户端 in-flight overlap，但不是性能基线。请固定 vLLM 源码版本并只读追踪 Scheduler 调用链，输出带 SHA/文件/行号的 scheduler-notes；不要修改 Router 或 Scheduler。
