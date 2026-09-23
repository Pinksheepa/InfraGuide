# Project Checkpoint

更新：2026-09-23（S1 双真实副本 RR smoke 已验收并冻结；进入 P0.1 Scheduler benchmark）。

## Current Stage / Goal

S0 已完成单卡运行、单请求 client/CLI 功能验证及最小串行 benchmark 的成功/连接失败/零测量参数路径。S1 已完成两个真实单卡 replica、完整 SSE、四请求 Round Robin 与一个无 failover 的 502 验收，Router 功能从此冻结。当前进入 P0.1：为单卡 Scheduler 实验建立可重放的长短混合并发 workload；尚未阅读/修改 Scheduler 或声称性能收益。
本月主线与投递目标不变；实际累计投入未知，不能按日历或对话时间推算。
执行约 2–4 小时可运行工作包，集中审查，不逐字段或逐句验收。

## Workspace / Version

- 工作目录：`/nfsdata/nHome/chenjunkun/project/infra`。
- 本次已读取实现：`src/single_request_client.py`、`src/run_single_cli.py`、`src/run_benchmark.py`、`src/round_robin_router.py`、`src/run_router.py`。
- Git 已初始化；当前为 `main`，HEAD 为 `b23ff00 s0: single replica with stream client`。未提交改动为文档、`src/single_request_client.py`，且 `src/round_robin_router.py`、`src/run_router.py` 未跟踪；不包含 checkpoint 所称的 `tests/test_round_robin_router.py`。
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

## Learning State / Contributions

S0 对话已检查：GPU 快照边界、设备重编号、SSE/length/DONE、prefill/decode/KV cache、wall/monotonic、TPOT 基本分母、文本重编码局限、tokenizer 一次加载与 fake 注入、transport 与后处理错误区分。
这些属于对话理解证据，不等同于扩展代码已通过；不再逐项重复口述。
S0 已集中检查：token 来源/TPOT 端点与说明一致，warmup 未计入 measure 指标，runner 的连接失败记录不进入指标，零测量被拒绝。工程验收通过；既有对话与代码/结果共同构成理解证据，不再重复口述。
贡献明细：`doc/CONTRIBUTIONS.md`。

## Next Task — P0.1 工作包 1：可重放长短混合 Scheduler workload

预计用户工作量 2–4 小时，属于规划估计；若明显超出，导师收缩范围或直接解释阻塞，不增加口述关卡。

目标：直接访问一个单卡 vLLM engine，建立可重放的长短 prompt 并发到达 trace 与最小 workload runner；不经 Router 分散请求，不修改 vLLM Scheduler。

用户实现范围：基于 `src/single_request_client.py` 与 `src/run_benchmark.py` 增量扩展或增加一个薄 runner。trace 至少含稳定 request ID、类别、prompt 来源/实际 token 数、`arrival_offset_ms`、固定输出配置；runner 按计划有限并发提交，记录计划/实际提交时间及客户端调度延迟，并保留每请求 SSE 结果。不得把 client E2E 差值伪装为 server queue time。

产出计划目录：`results/p0/scheduler/` 下的 trace、原始 JSONL、启动配置和简短说明。先完成 1 长 + 少量延迟短请求的 smoke，验证实际时间重叠；本包不报告优化收益，也不写 Adaptive Scheduler patch。

通过标准：同一 trace 可重复运行；每条记录可追溯到请求/到达计划/实际提交/成功或失败；结果可区分短与长请求；失败和超时不被静默丢弃。具体模型长度、到达偏移与并发度必须先由实际 token 计数和 engine 行为校准后冻结。

## Session Handoff

已有 S0 会话：`01a09f25-acb3-7943-8750-72676d6fc5da`；不必新建或重启项目。
本次复盘读取了 read_thread 元数据；其消息 items 为空，随后核对了该 task 对应 09-16/09-17 本地 session 原文及当前代码。
旧 checkpoint 备份：`doc/archive/checkpoint_before_pacing_2026-09-17.md`，其中矛盾状态仅供历史追溯。

进入 P0.1 的启动语：

> 读取更新后的 AGENTS.md、guide 和 PROJECT_CHECKPOINT.md。S1 已冻结；我开始 P0.1 的单卡长短混合 Scheduler workload。请先审查我一次性给出的 trace 和 runner 设计，再由我实现并运行最小重放 smoke。
