# V1 — vLLM Adaptive Prefill Scheduling Optimization

更新：2026-09-22。本文件按用户最新要求替换原多副本路由主线；旧四周路线及 checkpoint 中的“随后实现 Least Queue / Prefix Routing”不再作为执行范围。既有代码和实验继续复用。

**Current Objective:** 在 2–3 周内完成第一个可写入 AI Infra / LLM Inference 实习简历、能经受源码与性能追问的 V1 项目。完成下述 gate 后立即开始投递，不等待 P1/P2。

**V1 Main Feature:** vLLM Adaptive Prefill Scheduling。唯一核心优化问题是：在真实长短请求竞争下，能否通过小幅调整长 prefill 的 token 分配改善短请求响应，同时控制长请求完成时间和吞吐代价？收益与具体策略均待源码及实验验证。

**Current Stage:** [已验证][h] S0 最小串行 benchmark 与 S1 双真实副本 RR smoke 均有原始结果；Router 已冻结。Scheduler 优化尚未开始，当前是 P0.1 可重放长短混合 workload 的实现与校准阶段。

**Resume-ready Gate:** 以下各项全部通过才将 V1 标记为完成；不是获得面试或录用的保证。

- [x] S0 最小串行测量有正常结果：warmup/repeat、JSONL、TTFT、TPOT estimate；并发 scheduler benchmark 仍需补齐。
- [ ] S0 扩展后支持稳定的长短混合并发与可重放到达序列。
- [ ] S1 两个真实 vLLM replica 经 RR Router 正常流式响应，基本 benchmark 可运行。
- [ ] 能沿固定版本源码讲清 vLLM V1 Scheduler 核心路径，完成 `doc/scheduler-notes.md`。
- [ ] 有可复现的 contention workload、baseline 数据及问题归因，不仅有“长请求很慢”的现象。
- [ ] 已核验当前 upstream/main 与相关 open PR，明确真实缺口，无同功能重复实现。
- [ ] 修改 vLLM core scheduler，开关关闭保留 baseline 行为，patch 小且可审查。
- [ ] 对应 unit/regression tests 通过，未破坏 token/KV 分配及请求完成语义。
- [ ] 相同 workload、环境和基准 commit 上完成 Baseline vs Optimized 测量。
- [ ] 报告 TTFT p50/p95/p99、TPOT（注明估计口径）、吞吐、short-request TTFT、long-request completion time，以及波动和失败数。
- [ ] 能解释收益来源、退化场景与 latency-throughput tradeoff。
- [ ] README 与本 guide 的结果索引可追溯真实实验；形成 2–3 条可信简历 bullet。

负结果如实记录，不能填成“性能提升”。若未找到收益，保留分析成果但不虚报达到优化版 gate；按时间盒缩小同一问题内的实验/策略范围，不新增另一条开发线，也不自动延期。

## 1. 当前仓库事实与复用边界

本次为文档改写与只读核验，未运行 GPU 实验、未修改实现、未重新执行历史测试。

| 项目 | 2026-09-22 核对结果 | 证据 |
|---|---|---|
| Git | `main`，HEAD `b23ff00`；已有未提交文档/client 改动和未跟踪 Router 文件 | `git status --short`、`git log -1 --oneline` |
| 单请求 client | SSE 解析、首/末 content 与 DONE 时间、本地 tokenizer 重编码、TPOT estimate、有限 HTTP timeout | `src/single_request_client.py` |
| 串行 benchmark | 单 request body，串行 warmup/repeat；按 phase 落 JSONL，summary 只有有效数、mean、median | `src/run_benchmark.py` |
| S0 结果 | raw 中 12 条记录：2 warmup + 10 measure；有对应 summary，不能据此声称稳定 P99 或 scheduler 收益 | `results/s0/benchmark/benchmark_run_001.jsonl`、`benchmark_run_001_summary.json` |
| S1 Router | 单进程持锁 RR、SSE 转发、decision/terminal 日志；两个 replica 的启动入口已存在 | `src/round_robin_router.py`、`src/run_router.py` |
| S1 验证边界 | checkpoint 记载历史 mock 测试通过，但本次 `tests/` 目录不存在，不能宣称测试当前可复现；真实双副本成功证据未核验 | `doc/PROJECT_CHECKPOINT.md` 与目录核验 |
| 运行时/模型 | 项目记录为 vLLM 0.29.0、Qwen3-0.6B 固定 revision、bfloat16；本地已安装 scheduler 源文件存在 | `doc/s0/environment.md`、`doc/s0/baseline.md`、`.venv/lib/python3.11/site-packages/vllm/` |

[h] 现有串行 runner 不能制造并发竞争：只缺什么就补什么，不重写 S0、Router 或 tokenizer，也不为统一接口大规模抽象。
硬件为用户提供的 8 × RTX 5090；历史环境证据见 `doc/s0/environment.md`，当前占用不由历史记录推断。

## 2. P0 范围与执行顺序

P0 只有 Adaptive Prefill Scheduling 一个核心优化。S0 是测量设施，S1 是已有 serving infrastructure 的最小收尾。

实际先收口现有 S1，再补并发 workload，继而进入源码/问题复现/小 patch/对比实验；以下编号表示交付项，不要求推倒已完成项重做。

### P0.1 只补 scheduler benchmark 必需能力

复用 `src/single_request_client.py` 和 `src/run_benchmark.py`，保留现有串行调用方式。可增量扩展现有 runner 或增加一个薄的 workload runner，避免重写传输层。

必须补齐：

- 一份 workload 中有不同 prompt length、请求类别、稳定 request ID 和 `arrival_offset_ms`。
- 有限并发，按到达计划发请求；记录计划/实际提交时间与客户端调度延迟，避免将客户端排队误认为 engine 排队。
- 输入长度按固定 tokenizer 与 chat template 核对；固定输出预算并记录实际输出 token 数、stop/length。
- 从原始记录计算 TTFT p50/p95/p99、TPOT estimate、request/s 与 output tokens/s；分别汇总短/长请求。
- 记录 warmup、失败/超时、测试窗口和排空策略；失败数必须报告，不可仅留下成功样本。
- queue time 若能从固定版本服务端指标或少量埋点可靠获取则增加，否则 N/A；不得用客户端 E2E−计算估计冒充。

计时与计数沿用已验证定义；TPOT estimate 不冒充逐 token ITL。若后续改用服务端 usage，须在两组实验一致使用并注明来源。

### P0.2 S1 最小闭环，验收即停止

使用现有两个 Router 文件，不重写 Router：

```text
两个独立单卡 vLLM replicas → Round Robin → 完整 SSE → 基本 benchmark
```

至少四个串行请求证明交替路由，client 与 decision 日志按 request ID 关联；正常完成及一个 upstream 不可用场景结果可追溯，不做 retry/failover。
通过后冻结 Router 功能。Least Load/Least Queue、Prefix-aware Routing、复杂 health check、复杂恢复、Web UI、数据库、control plane 均不进入 P0。

Scheduler 核心实验直接访问同一个单卡 engine；不经 RR 把竞争请求分散到不同副本，也不把 Router 开销当作 Scheduler 收益。

### P0.3 只读实验所需的 V1 Scheduler 调用链

入口（相对于后续固定的 vLLM 源码 checkout，不是 infra 根目录）：

- `vllm/v1/core/sched/scheduler.py`：`Scheduler.schedule()`，running/waiting 分配路径。
- `vllm/config/scheduler.py`：相关配置的真实语义、默认值及校验。
- 必要时追到请求入队、KV allocation、`SchedulerOutput` 和实际 worker/model runner 消费点；不通读整个 vLLM。

覆盖 running/waiting queue、token budget、`num_scheduled_tokens`、prefill/decode、chunked/partial prefill、`max_num_batched_tokens`、`long_prefill_token_threshold`、KV block allocation、preemption。

产出 `doc/scheduler-notes.md`（计划文件，本次未创建），按固定 commit+文件+行号回答：

1. request 如何进入 waiting queue？
2. 何时进入 running，失败或推迟 admission 时发生什么？
3. prefill 与 decode 如何竞争 token budget？不能假定源码按两个独立阶段实现。
4. 长 prefill 为何跨多个 step，哪些状态保留已计算进度？
5. chunk 大小在哪些路径受到哪些约束？
6. `max_num_batched_tokens` 及版本中其他预算如何限制 step？
7. KV capacity 如何影响 admission/preemption？
8. `SchedulerOutput` 经哪条实际调用链交给 worker/model runner？

### 版本与 upstream 查重门槛

[h] 本地安装源码不是已固定的 upstream main checkout。本次可见本地 `schedule(..., throttle_prefills=False)`、`max_num_scheduled_tokens` 和 `max_num_batched_tokens` 两类预算，且配置注释说明 `long_prefill_token_threshold=0` 关闭 cap。不能预设“默认固定 threshold 总在浪费预算”，也不能把已有节流逻辑视为尚未实现。

以查阅时的官方 main 为设计依据，开始实验前固定到 SHA，并记录它与本地安装版本的差异：

- [官方 Scheduler main](https://github.com/vllm-project/vllm/blob/main/vllm/v1/core/sched/scheduler.py)
- [官方 SchedulerConfig main](https://github.com/vllm-project/vllm/blob/main/vllm/config/scheduler.py)

上述页面本次已访问；尚未完成 main SHA 固定、相关实现的完整比较或 open PR 查重，不能宣称没有重复功能。
在设计 patch 前搜索官方仓库的 adaptive/chunked prefill、prefill throttling、waiting demand 相关已合并及 open PR，记录日期、链接、状态和语义差异。

若已有同功能实现或 open PR 正在做同功能，不重复实现；只能在可复现证据支持下选择同一调度问题中的具体未覆盖缺口。没有缺口时停止该候选方案，不改名包装已有逻辑。
运行时使用可追溯源码 checkout 与隔离环境；验证实际 import 路径与构建版本。Baseline 和 Optimized 必须来自同一 SHA 加开关/patch，不能用旧 wheel 对比新 main 把版本变化算作优化。

### P0.4 先复现问题，后设计 feature

先做 smoke 校准，再固定 trace；模型、上下文和输出预算必须适配实际显存及 engine 配置。现有 S0 小模型可以先复用；若运行太快难以稳定制造竞争，先调整长度/到达密度，确有必要才换一个模型并重建两组基线。不要求 100k context。

| Case | workload | 用途 |
|---|---|---|
| A | 1 个长 prompt、无其他请求 | 观察无竞争时长 prefill 的预算与完成时间 |
| B | 1 个长 prompt + 8 个延迟到达的短 prompt（初始方案） | 验证短请求是否确实在长 prefill 尚未结束时进入队列 |
| C | 一组持续 decode 的请求 + 新长 prompt | 观察加入 prefill 后 decode 延迟是否受影响 |
| D | 对 A–C 扫描少量固定 `max_num_batched_tokens` 值 | 区分配置效果和策略效果 |

长度、到达偏移和 token budget 先校准后冻结；所有数值是实验参数，不预填未经运行的有效配置。Case B/C 必须验证实际重叠，不凭提交顺序推断竞争。
基线同时包含 upstream/default、合理固定阈值/预算配置；不能只挑一个刻意劣化的固定配置来证明 adaptive 更好。

必报 TTFT p50/p95/p99、TPOT estimate、throughput、短请求 TTFT 和长请求完成时间。可取得时增加 queueing time、step token allocation、prefill chunk size、waiting/running 数量和 GPU utilization。
若没有足够证据区分 HOL、单 step 执行时间、KV 压力或客户端排队，写“原因待验证”，补最小观测，不直接把所有尾延迟称为 HOL blocking。
只有稳定复现问题并解释现有策略的不足，才进入 P0.5。

### P0.5 一个最小 Adaptive Chunked Prefill 策略

[m] 候选假设：依据当前可调度的 waiting demand 和 decode 需求调整长 prefill 的有效 budget，可能在无竞争时利用余量、有竞争时改善短请求响应。不是已证实算法。

设计必须从固定 main 的实际行为出发：

- 无 waiting demand 时，判断放宽 chunk 是否确有价值，不能无视全局预算、KV 或其他路径限制。
- 存在短 waiting 请求时，只为能实际 admission 的需求考虑预留；不能仅因 waiting 非空就浪费预算。
- 存在 decode 时，先确认 upstream 已有优先级和节流；不要重复已有保护，也不把所有 running 请求都当成 decode。
- 明确长请求持续进展的条件，避免饥饿；不得读取未来到达或真实未来输出长度。

只选择一种观测与决策规则，并保留可关闭开关。对默认阈值、固定阈值和自适应行为进行解释，不建立通用 policy framework。

### P0.6 小 patch 与有意义的测试

主要改动限于固定 checkout 的 `vllm/v1/core/sched/scheduler.py`；必要时修改 `vllm/config/scheduler.py` 及对应 `tests/v1/core/`。实际测试文件名、配置入口与 CLI 支持必须以固定版本为准，不创造不存在的接口。

开关关闭 → 同版本 upstream/default 行为；开关开启 → adaptive 行为。避免直接长期修改 site-packages 而没有可审查 patch。

至少覆盖：

- disabled 回归：同一队列与配置得到等价调度输出。
- 无竞争与有短请求竞争：token 分配符合设计，预算不超限。
- decode 混合与长 prefill：短请求受保护且长请求能持续进展。
- KV 容量不足、preemption 或 admission 失败时保留原有正确性。
- 请求完成/取消后的状态，以及不依赖未来信息的确定性行为。

测试验证行为与不变量，不只镜像实现；再执行与 patch 相关的上游回归测试。本地 S1 mock 测试与 vLLM core regression 是不同证据。

### P0.7 Baseline vs Optimized 闭环

固定同一 GPU、模型/revision、dtype、vLLM SHA、trace、arrival、输出配置、缓存状态及 engine 参数；除策略开关外保持一致。调参 trace 与最终评估 trace 分开。

- 至少 3 次独立运行；交错运行 baseline/optimized，记录设备干扰、错误和波动。
- 预热与前缀缓存策略保持一致，避免已缓存长 prompt 抹掉 prefill；原始请求实际 token 长度可追溯。
- 报告全部请求和短/长分组。8 个短请求只是 smoke，不足以支撑稳定 P99；正式实验扩充重复到达序列，注明样本数与分位数算法，样本不足则明确限制。
- throughput 同时报 request/s 与 output tokens/s，定义起止窗口和排空行为，不把串行单请求 token/s 当系统吞吐。
- TPOT 平均可能掩盖 decode 停顿；Case C 若需要逐 token/stream 间隔观测，明确粒度，不把 SSE chunk 当 token。
- profiling/埋点诊断与低开销正式性能运行分开；没有 queue-time 指标就标 N/A。
- 同时看短请求 TTFT、长请求 completion、TPOT 与 throughput；不隐瞒吞吐下降来突出尾延迟。

结果以原始 JSONL、trace、环境/启动命令、配置、源码 SHA+patch、统计脚本和 summary 保存到计划目录 `results/p0/scheduler/`。README 与本 guide 链接最终结果；尚未产生的数据留空。

## 3. GPU 与时间预算

Scheduler 首先在 **1 × RTX 5090** 上跑清楚；S1 最小闭环使用两个独立单卡副本。
主体稳定后，TP=2/4 可作为后续不同 engine configuration 验证，不属于 P0 gate。P0 不要求 TP8、DP8、EP、PP、CP，也不因资源充足扩张范围。

[m] 以 2026-09-22 为本次调整起点，2–3 周约为 10-06 至 10-13；此前每周约 35 小时的预算对应约 70–105 小时，不是保证工期。优先两周形成闭环，第三周用于必要复测与整理，不等到 Day 21 才判断能否投递。

| 时间盒 | 唯一阶段产出 |
|---|---|
| Day 1–3 | 收尾现有 S0/S1；准备可重放的并发长短请求 workload |
| Day 4–7 | 固定 main SHA、查重、scheduler-notes、稳定复现 baseline 问题 |
| Day 8–12 | 最小 adaptive patch 与伴随单测，不新增调度框架 |
| Day 13–16 | 回归、对比 benchmark、修正实现；若 gate 已满足即投递 |
| Day 17–21 | 必要补实验、README、2–3 条简历 bullet、源码及 tradeoff 讲解 |

超时先砍可选观测、模型数量、参数组合与扩展规模；保留正确性、源码改动、对照实验和最小 S1 gate。若查重或复现失败，只允许在同一调度问题内缩小候选方案，明确报告缺口，不自动延长 roadmap。
每次仍是约 2–4 小时工作包，一次给齐设计/实现/运行约束，核心代码由用户实现，模块交付后集中审查；不恢复逐字段或逐句过关。

## 4. P0 完成后才考虑的增强

| 阶段 | 候选范围 | 边界 |
|---|---|---|
| P1 / V2 | KVCacheManager、BlockPool、prefix caching、LRU/eviction；选 Session-aware retention | 第二个核心优化只做 Retain/Evict；不同时加入 Prefetch、CPU Offload、Remote KV 或通用 framework |
| P1.5 / V3 | Cost-aware KV Offload | KV 基础完成后，比较 estimated load cost 与 recompute cost，再决定 reload/recompute；不阻塞 V1 投递 |
| P2 / V4 | Prefix-aware/Session-aware Router、Least Load、Cache-aware Multi-replica Serving | 不把路由策略扩展带回 P0 |
| P2 / V5 | TP/DP scaling、TP×DP、EP/MoE | 按具体问题选一个，不要求全实现 |
| P2 / V6 | CUDA SGEMM、Triton LLM kernel | 独立后续深度，不作为 V1 前置条件 |
| P2 其他 | Speculative Decoding、P/D Disaggregation、PP、CP | 仅保留候选，不预排完整课程 |

V1 完成即投递；V2–V6 均边投边迭代，不是“完成项目之前必须做”的清单。

P0 明确禁止：重写 Router、完整 KV Framework、所有并行策略、大规模 refactor、为架构美观增加抽象、先开发后找 benchmark、重复上游 feature、强行 TP8、同时开 Scheduler/KV/CUDA 三条线。

## 5. 项目结果与简历描述

当前 scheduler baseline / optimized 结果：**Not measured**。本次只修改路线，不声称完成 Scheduler 阅读、patch、单测或收益验证。

| 结果索引 | 状态 |
|---|---|
| S0 原始串行 benchmark | 已有：`results/s0/benchmark/benchmark_run_001.jsonl` 及对应 summary |
| S1 双真实副本 RR | 已验收：`results/s1/rr_smoke/run_001/`（四请求严格 RR、完整 SSE、受控 502/no-failover；非性能实验） |
| Scheduler 调用链和 upstream 差异 | 待建立：`doc/scheduler-notes.md` |
| 固定 trace、baseline、optimized、回归与比较 | 待建立：`results/p0/scheduler/` |
| README 实验表和复现入口 | 待形成，不预填性能数字 |

最终叙事（模板，不是已完成事实）：

1. 基于固定版本 vLLM V1 Scheduler，定位长短混合请求下具体 token-budget 分配问题，并用源码路径与请求/step 记录建立归因。
2. 实现可关闭的 adaptive prefill 调整，说明本人修改的路径、实际观测量、预算约束和回归覆盖；不将上游 chunked prefill 写成本人实现。
3. 用可重放 streaming benchmark 对比 TTFT p50/p95/p99、TPOT、吞吐、短请求响应及长请求完成时间；只填真实数字，并报告 tradeoff 和适用范围。

## 6. Next immediate task（仅一个）

**S1 已验收并冻结；建立单卡长短混合 Scheduler workload 的最小可重放 smoke。** 不修改 Router，不增加 Least Load。

涉及现有文件：`src/run_benchmark.py`、`src/single_request_client.py`；可新增薄的 workload runner 和 trace 文件。实验直接访问同一个单卡 engine，不经 Router。

实验：先以固定 tokenizer 和 chat template 构造一份含 1 个长请求、少量延迟短请求、稳定 request ID 与 `arrival_offset_ms` 的 trace。有限并发按计划提交，记录计划/实际提交、客户端调度延迟和每请求 SSE 结果；校准并验证实际重叠后才冻结长度和偏移。保留失败/超时，按短/长类别汇总；无可靠服务端指标时 queue time 标 `N/A`。

产出计划目录 `results/p0/scheduler/`：trace、启动配置、原始 JSONL、summary 与简短说明。S1 结果固定于 `results/s1/rr_smoke/run_001/`。本包只补 workload 与测量设施，不声称 Scheduler 根因或优化收益。
