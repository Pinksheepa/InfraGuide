# Project Checkpoint

更新：2026-09-20（S0 收口，进入 S1 准备）。

## Current Stage / Goal

S0 已完成单卡运行、单请求 client/CLI 功能验证及最小串行 benchmark 的成功/连接失败/零测量参数路径；可以进入 S1。S1 尚未开始实现。
本月主线与投递目标不变；实际累计投入未知，不能按日历或对话时间推算。
执行约 2–4 小时可运行工作包，集中审查，不逐字段或逐句验收。

## Workspace / Version

- 工作目录：`/nfsdata/nHome/chenjunkun/project/infra`。
- 本次已读取实现：`src/single_request_client.py`、`src/run_single_cli.py`、`src/run_benchmark.py`。
- Git 已初始化；当前为 `main`，基准实现与文档均有未提交改动。最近提交为 `2e47d8947a1192f3279a2847e64bdc2f9c97fd61`，但本次结果不能绑定到该提交。
- 本轮审查执行了语法编译、`--help`、原始数据独立重算和一个不发出 HTTP 请求的配置错误检查；没有向 vLLM 发送请求或核验 GPU 当前状态。

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

## Learning State / Contributions

S0 对话已检查：GPU 快照边界、设备重编号、SSE/length/DONE、prefill/decode/KV cache、wall/monotonic、TPOT 基本分母、文本重编码局限、tokenizer 一次加载与 fake 注入、transport 与后处理错误区分。
这些属于对话理解证据，不等同于扩展代码已通过；不再逐项重复口述。
S0 已集中检查：token 来源/TPOT 端点与说明一致，warmup 未计入 measure 指标，runner 的连接失败记录不进入指标，零测量被拒绝。工程验收通过；既有对话与代码/结果共同构成理解证据，不再重复口述。
贡献明细：`doc/CONTRIBUTIONS.md`。

## Next Task — S1 工作包 1：双副本启动与流式 Round Robin

预计用户工作量 2–4 小时，属于规划估计；若明显超出，导师收缩范围或直接解释阻塞，不增加口述关卡。

目标：在同一主机上启动两个独立单卡 vLLM replica，并由用户实现一个能转发流式 chat-completions 的 Round Robin router。该包只建立正确路由闭环，不测性能优势。

用户先提交一次 5–10 行设计：public router endpoint、两个 replica 的物理 GPU/端口/ID、RR 状态与并发保护位置、路由 decision 记录、上游失败或客户端断开时的语义，以及验证办法。开始启动前重新核验选定 GPU 的瞬时占用；历史 S0 使用物理 GPU 4/端口 8000，不能将它视为当前空闲或复用该端口的授权。

实现约束：

1. 两个 vLLM 进程各以一个单独的 `CUDA_VISIBLE_DEVICES=<physical-id>` 启动，各自会将该卡映射为其进程内 logical device 0；使用不同端口和稳定 replica ID。
2. Router 只在每个新请求入站时选择一个 upstream，并完整转发该 upstream 的 SSE 流。S1-RR 不做跨副本 retry：流开始后重试会造成重复文本或重复副作用。
3. 写一份 router decision JSONL，至少记录 router request ID、选择的 replica ID、入站/完成或失败状态。S0 client 记录与 router decision 通过该 ID 或一次性关联字段对应，不猜测选中的副本。
4. 用至少四个串行相同请求证明 `replica-0, replica-1, replica-0, replica-1` 的选择顺序，并保存 upstream/decision 证据；再验证一个不可用 upstream 返回明确失败且没有重复投递。

通过标准：两卡独立启动、SSE 不丢失/不重复、RR 顺序和失败语义可追溯。Least Queue、并发负载、前缀缓存、性能比较留给后续工作包。

## Session Handoff

已有 S0 会话：`01a09f25-acb3-7943-8750-72676d6fc5da`；不必新建或重启项目。
本次复盘读取了 read_thread 元数据；其消息 items 为空，随后核对了该 task 对应 09-16/09-17 本地 session 原文及当前代码。
旧 checkpoint 备份：`doc/archive/checkpoint_before_pacing_2026-09-17.md`，其中矛盾状态仅供历史追溯。

进入 S1 的启动语：

> 读取更新后的 AGENTS.md、mentor_prompt 第 5 节和 PROJECT_CHECKPOINT.md，开始 S1 的双副本启动与流式 Round Robin 工作包。我先给一次整体设计，核心代码由我写，完成后你集中 review。
