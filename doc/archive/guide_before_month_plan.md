> 历史快照：2026-09-11 调整前的路线，仅供参考。当前计划以 ../guide.md 为准；以下优先级、工期和简历判断不再作为执行依据。

# AI Infra 推理侧实习项目 Guide

> 目标：在时间紧张的前提下，优先做出**可以写进简历、可以跑 benchmark、可以在面试中讲清楚**的项目，再逐步补齐分布式、调度与 CUDA Kernel 深度。

---

# 0. 最终作品集目标

建议最终保留两个主项目：

## Project A — Distributed LLM Serving Engine

主线能力：

- LLM inference engine
- Continuous batching
- KV Cache / Prefix Cache
- Tensor Parallel
- Data Parallel
- Expert Parallel
- NCCL communication
- Prefix-aware / load-aware scheduler
- Multi-GPU benchmark

最终目标不是“实现一个 nano-vLLM”，而是：

> **基于轻量推理框架实现多 GPU 分布式 Serving，并针对调度、KV Cache 与通信进行优化。**

---

## Project B — CUDA GEMM & LLM Kernel Optimization

主线能力：

- CUDA programming
- Memory coalescing
- Shared-memory tiling
- Register tiling
- Vectorized access
- Tensor Core / WMMA
- Nsight profiling
- Transformer fused kernel

最终目标不是：

> 实现一个 SGEMM。

而是：

> **从 Naive CUDA GEMM 出发，通过 shared memory、register tiling、vectorized memory access 和 Tensor Core 优化矩阵乘，并将方法迁移到 Transformer inference kernel。**

---

# 1. 总原则

## 1.1 优先级

时间紧张时严格遵循：

```text
能跑
↓
能测
↓
能解释
↓
能优化
↓
再增加功能
```

不要反过来。

---

## 1.2 什么叫“可以写进简历”

一个功能至少满足：

- 有代码
- 有 README
- 有 benchmark
- 有 baseline
- 有至少一个量化结果
- 能解释设计原因
- 能解释瓶颈
- 能解释失败方案

否则暂时不算完成。

---

# 2. 推荐执行顺序

```text
P0  最小可用 Serving
↓
P1  TP + DP
↓
P2  Scheduler / Prefix Cache
↓
P3  EP
↓
P4  CUDA GEMM
↓
P5  Tensor Core + Transformer Kernel
↓
P6  可选：CP / PP / P-D 分离
```

其中：

- P0-P2 做完：已经可以投实习
- P3-P4 做完：简历开始有明显区分度
- P5 做完：具备较完整 inference infra + kernel profile
- P6 属于加分项

---

# 3. 第一阶段：P0 最小可用 LLM Serving

## 目标

先得到一个真正能工作的 inference engine baseline。

底座可选：

- nano-vLLM
- InfiniLM
- 启元训练营框架
- 自己实现的轻量 engine

不要把时间浪费在从零实现 tokenizer、模型加载等低价值模块。

---

## 最小功能

必须有：

- 模型加载
- Prefill
- Decode
- KV Cache
- Sampling
- Batch inference
- 基础 benchmark

建议模型：

- Qwen2.5-0.5B
- Qwen2.5-1.5B
- Qwen2.5-3B

先保证快速开发。

---

## Benchmark

至少记录：

```text
TTFT
TPOT / ITL
tokens/s
request throughput
GPU memory usage
GPU utilization
```

测试 workload：

```text
Input / Output
128 / 128
512 / 128
2048 / 128
4096 / 128
```

并测试并发：

```text
1
4
8
16
32
```

---

## 完成判据

以下全部满足才进入下一阶段：

- 单卡推理正确
- 能连续生成
- KV Cache 正确
- benchmark 可重复运行
- 能输出 CSV/JSON
- 有 baseline 数据

---

## 第一版简历已经可以写

> 基于轻量级 LLM inference engine 搭建完整 Prefill/Decode 推理链路，实现 KV Cache、Batch Decode 与推理 benchmark，测量 TTFT、TPOT、吞吐与 GPU 利用率，为后续多 GPU 和调度优化建立性能基线。

这只是保底版本，不建议最终只停在这里。

---

# 4. 第二阶段：P1 Tensor Parallel

这是第一优先级最高的分布式能力。

---

## 4.1 先实现 Linear TP

先只做：

```text
Column Parallel Linear
Row Parallel Linear
```

### Column Parallel

```text
W = [W0 W1 W2 W3]

GPU0: XW0
GPU1: XW1
GPU2: XW2
GPU3: XW3
```

需要理解：

- weight shard
- output shard
- AllGather 是否需要

---

### Row Parallel

```text
X0W0 ─┐
X1W1 ─┤
X2W2 ─┼─ AllReduce → Y
X3W3 ─┘
```

必须理解：

```text
为什么需要 AllReduce
什么时候可以延迟通信
通信量是多少
```

---

## 4.2 扩展到 Transformer

逐步支持：

- QKV projection
- Attention head partition
- O projection
- MLP up/gate/down projection

最终：

```text
TP=1
TP=2
TP=4
```

都可以运行。

---

## Benchmark

测：

```text
TP = 1 / 2 / 4
```

指标：

- latency
- tokens/s
- scaling efficiency
- NCCL communication time
- GPU utilization

定义：

```text
Scaling Efficiency
= Throughput(TP=N) / (N × Throughput(TP=1))
```

---

## 完成判据

- 2 卡正确
- 4 卡正确
- 单卡输出和 TP 输出数值基本一致
- 有 NCCL profiling
- 知道性能不线性扩展的原因

---

## 简历表述升级

> 实现 Transformer Tensor Parallel，包括 Column/Row Parallel Linear、Attention Head Partition 与 NCCL AllReduce；支持 TP=1/2/4，在 4×V100 环境下分析计算/通信比例、Scaling Efficiency 与 collective communication 开销。

---

# 5. 第三阶段：P1 Data Parallel + Request Router

推理 DP 不要做成训练 DP。

核心是：

```text
多个 Model Replica
+
Request Routing
```

---

## 最小实现

```text
Router

├── Worker0 → GPU0
├── Worker1 → GPU1
├── Worker2 → GPU2
└── Worker3 → GPU3
```

先实现：

```text
Round Robin
Least Queue
```

---

## Benchmark

Workload 使用随机 request arrival：

```text
Poisson arrival
```

观察：

```text
P50 TTFT
P95 TTFT
P99 TTFT
throughput
queue length
GPU utilization
```

---

## 完成判据

能证明：

```text
Round Robin
vs
Least Queue
```

在 burst workload 下的区别。

---

# 6. 第四阶段：P2 Prefix-aware Scheduler

这是建议你真正打造“个人特色”的地方。

---

## 6.1 Prefix Cache

实现：

```text
system prompt
conversation prefix
shared prompt prefix
```

对应 KV reuse。

---

## 6.2 Prefix-aware Routing

Router 不再单纯看 queue length。

定义简单 cost：

```text
cost_i
=
α × queue_length
+
β × kv_memory_pressure
-
γ × prefix_hit_ratio
```

选择：

```text
worker = argmin(cost_i)
```

第一版不要追求复杂 ML scheduler。

---

## 对比 baseline

至少：

```text
Round Robin
Least Queue
Prefix Only
Prefix + Load Aware
```

---

## Workload

重点构造：

### Shared System Prompt

```text
System Prompt = 2K / 4K token
User Prompt = 128 token
```

### Multi-turn Chat

大量共享历史前缀。

### Coding Agent

共享：

```text
repository context
system prompt
tool definition
```

---

## 核心指标

除了：

```text
TTFT
TPOT
throughput
```

增加：

```text
Prefix Cache Hit Rate
Recomputed Prefill Tokens
KV Memory Usage
P99 TTFT
Goodput
```

---

## Goodput

建议定义：

```text
满足 TTFT/TPOT SLO 的 request / second
```

不要只展示 raw throughput。

---

## 完成判据

你必须回答：

```text
为什么 Prefix Only 不够？
为什么 cache locality 和 load balancing 会冲突？
GPU0 cache 命中最高但已经很忙怎么办？
```

---

## 到这里项目已经足够作为简历主项目

推荐最终项目名：

```text
SLO-aware Multi-GPU LLM Serving Engine
```

或者：

```text
Prefix-aware Distributed LLM Serving System
```

---

# 7. 第五阶段：P2 Chunked Prefill

有时间就加。

---

## 最小实现

设置：

```text
max_num_batched_tokens
prefill_chunk_size
```

优先保证 Decode request。

例如：

```text
Decode
Decode
Decode
+
512-token Prefill Chunk
```

而不是：

```text
一次 Prefill 4096 token
```

---

## 实验

长 prompt：

```text
4K
8K
16K
```

同时混合 short decode requests。

比较：

```text
No Chunking
Fixed Chunk = 256
Fixed Chunk = 512
Fixed Chunk = 1024
```

---

## 再做 Adaptive Chunk Size

简单规则即可：

```text
decode queue 高
→ 减小 chunk

decode queue 低
→ 增大 chunk
```

不要一开始搞强化学习调度。

---

## 指标

重点看：

```text
P99 TPOT
P99 TTFT
Throughput
GPU utilization
```

---

# 8. 第六阶段：P3 Expert Parallel

如果时间不足，可以停在这里之前。

EP 是“高价值加分项”，不是投实习前的硬门槛。

---

## 最小目标

选择小型 MoE 模型。

实现：

```text
Router
↓
Token Dispatch
↓
All-to-All
↓
Local Experts
↓
All-to-All
↓
Combine
```

重点理解：

```text
token imbalance
expert load imbalance
All-to-All overhead
straggler
```

---

## 第一版只做

```text
Static Expert Placement
```

4 GPU：

```text
GPU0 → Expert 0,1
GPU1 → Expert 2,3
GPU2 → Expert 4,5
GPU3 → Expert 6,7
```

---

## 第二版优化

做：

```text
Hot Expert Replication
```

或者：

```text
Load-aware Expert Placement
```

---

## Benchmark

记录：

```text
Tokens per Expert
GPU load imbalance
All-to-All time
Iteration latency
Throughput
```

---

# 9. CP / PP 怎么处理

优先级降低。

---

## Context Parallel

只有当你决定强调：

```text
Long Context Serving
```

再做。

关注：

```text
Prefill TTFT
KV cache capacity
long sequence partition
```

---

## Pipeline Parallel

只建议：

- 能运行
- 能讲 stage partition
- 能讲 pipeline bubble

不要投入大量优化时间。

---

# 10. CUDA 项目：P4 SGEMM Optimization

CUDA 项目应独立成仓库。

推荐仓库：

```text
cuda-gemm-lab
```

---

# 11. CUDA SGEMM 优化路线

严格按照版本迭代。

---

## V0 CPU

用于 correctness baseline。

---

## V1 Naive CUDA

每个 thread：

```text
负责一个 C[i,j]
```

目标：

- 正确
- 理解 grid/block/thread

---

## V2 Memory Coalescing

优化 global memory access。

重点掌握：

```text
coalesced access
global memory transaction
```

---

## V3 Shared Memory Tiling

核心：

```text
A Tile
B Tile
↓
Shared Memory
↓
Compute Tile
```

必须理解：

```text
为什么减少 global memory access
arithmetic intensity 如何提升
```

---

## V4 Register Tiling

一个线程算多个 output elements。

例如：

```text
1×4
4×4
8×8
```

研究：

```text
register reuse
register pressure
occupancy
```

---

## V5 Vectorized Load

例如：

```text
float4
```

分析：

```text
memory instruction count
alignment
bandwidth
```

---

## V6 Double Buffering

做：

```text
load tile N+1
while
compute tile N
```

重点理解：

```text
memory/computation overlap
```

---

# 12. P5 Tensor Core

V100 是 Volta，支持 Tensor Core。

不要停在 FP32 SGEMM。

继续做：

```text
FP16 GEMM
+
WMMA
```

对比：

```text
CUDA Core
vs
Tensor Core
```

---

## Benchmark

矩阵尺寸：

```text
512
1024
2048
4096
8192
```

矩阵形状也要增加 LLM 风格：

```text
M = batch × tokens
K = hidden size
N = hidden size / intermediate size
```

例如：

```text
M=128, K=4096, N=4096
M=512, K=4096, N=11008
M=1, K=4096, N=4096
```

注意：

```text
大方阵 benchmark
!=
LLM inference workload
```

这一点面试非常值得讲。

---

## 指标

记录：

```text
Latency
GFLOPS / TFLOPS
Bandwidth
Occupancy
SM utilization
Register usage
Shared memory usage
```

并与：

```text
cuBLAS
```

对比。

---

# 13. Nsight 必须使用

不要只有 wall-clock latency。

至少使用：

```text
Nsight Systems
Nsight Compute
```

会看：

```text
kernel timeline
SM utilization
achieved occupancy
DRAM throughput
L2 hit rate
register usage
shared memory
warp stall
```

---

# 14. P5 再补一个 LLM-specific Kernel

推荐只选一个。

优先级：

```text
RMSNorm
> SwiGLU
> RoPE
> Softmax
```

---

## 推荐：Fused RMSNorm + Residual

原因：

- 实现难度适中
- memory-bound 特征明显
- 很适合解释 kernel fusion
- 和 LLM inference 强相关

比较：

```text
PyTorch baseline
CUDA unfused
CUDA fused
```

记录：

```text
kernel launch 数
HBM traffic
latency
```

---

# 15. 项目融合

最终不要让两个项目互相完全独立。

最好把 CUDA kernel 接回 Serving Engine。

例如：

```text
Serving Engine
↓
原始 RMSNorm
↓
替换为 Custom CUDA RMSNorm
↓
测 E2E TPOT
```

这样你可以回答：

```text
Microbenchmark 快 30%
为什么 E2E 只快 4%？
```

这正是很好的性能工程问题。

---

# 16. 最终 Benchmark Matrix

最终至少准备以下实验。

---

## Experiment 1：TP Scaling

```text
TP=1
TP=2
TP=4
```

记录：

```text
throughput
latency
NCCL time
scaling efficiency
```

---

## Experiment 2：Router

```text
Round Robin
Least Queue
Prefix-aware
Prefix + Load-aware
```

---

## Experiment 3：Prefix Cache

测试不同共享前缀比例：

```text
0%
25%
50%
75%
100%
```

---

## Experiment 4：Concurrent Serving

并发：

```text
1 / 4 / 8 / 16 / 32 / 64
```

---

## Experiment 5：Long Prompt

```text
512
2K
4K
8K
```

---

## Experiment 6：GEMM

```text
Naive
Coalesced
Shared Memory
Register Tiling
Vectorized
Tensor Core
cuBLAS
```

---

# 17. 时间极紧时怎么裁剪

如果只有很短时间：

## 必做

```text
1. inference baseline
2. TP
3. DP router
4. Prefix-aware routing
5. CUDA SGEMM 到 shared-memory/register tiling
6. benchmark
```

做到这里立即开始投递。

---

## 第二优先级

```text
7. Chunked Prefill
8. Tensor Core
9. Nsight 深度 profiling
```

---

## 第三优先级

```text
10. EP
11. Fused RMSNorm
12. Adaptive scheduler
```

---

## 最后再做

```text
13. CP
14. PP
15. P/D disaggregation
```

---

# 18. 推荐的最小投递版本

最少完成：

```text
Distributed Serving
├── baseline engine
├── TP=2/4
├── DP workers
├── request router
├── prefix-aware routing
└── benchmark

CUDA
├── naive GEMM
├── coalescing
├── shared memory tiling
├── register tiling
└── vs cuBLAS
```

这个版本已经比：

```text
复现 nano-vLLM
+
写几个 Triton kernel
```

强很多。

---

# 19. 简历推荐表述

## Distributed LLM Serving

建议按实际完成内容删减：

> **Distributed LLM Serving Engine**  
> 基于轻量级 LLM inference runtime 实现多 GPU 推理系统，支持 KV Cache、Continuous Batching、Tensor Parallel 和多副本 Data Parallel；基于 NCCL 实现 Transformer Row/Column Parallel 通信，并设计 Prefix-aware + Load-aware request routing，联合考虑共享前缀 KV locality、worker queue 与 cache pressure。构建多并发、多 prompt 长度 benchmark，使用 TTFT、TPOT、P99 latency、Throughput、Goodput 与 KV Cache Hit Rate 分析系统性能。

---

## CUDA Kernel

> **CUDA GEMM & Transformer Kernel Optimization**  
> 从 Naive CUDA SGEMM 出发，依次实现 memory coalescing、shared-memory tiling、register blocking、vectorized memory access 等优化，并使用 Nsight Compute 分析 memory bandwidth、occupancy 与 warp stall；进一步实现基于 Tensor Core/WMMA 的 FP16 GEMM，并与 cuBLAS 进行性能对比，同时将 kernel 优化方法迁移至 Transformer inference operator。

不要写没完成的部分。

---

# 20. 面试必须能回答的问题

---

## Serving

- Prefill 和 Decode 的计算特征有什么区别？
- 为什么 TTFT 主要受 Prefill 影响？
- 为什么 Decode 更容易 memory-bound？
- Continuous Batching 为什么有效？
- Paged KV Cache 解决什么问题？
- Prefix Cache 什么时候收益最高？
- Prefix Cache 为什么会和负载均衡冲突？
- Chunked Prefill 为什么可以降低 tail TPOT？

---

## TP

- Row Parallel 和 Column Parallel 有什么区别？
- 哪一步需要 AllReduce？
- 哪一步需要 AllGather？
- TP 为什么不是越大越好？
- V100 PCIe / NVLink 对 TP 有什么影响？
- TP 通信量如何估算？

---

## DP

- 推理 DP 和训练 DP 有什么区别？
- Round Robin 为什么可能表现差？
- 为什么需要 load-aware routing？

---

## EP

- Expert Parallel 为什么需要 All-to-All？
- Hot Expert 为什么导致 straggler？
- Expert replication 的代价是什么？

---

## CUDA

- 为什么 shared memory tiling 有效？
- 什么叫 coalesced memory access？
- register tiling 为什么有效？
- register 太多为什么反而变慢？
- occupancy 是越高越好吗？
- arithmetic intensity 是什么？
- GEMM 为什么适合 Tensor Core？
- 为什么你的 kernel 比 cuBLAS 慢？
- 为什么 microbenchmark 提升不一定等于 E2E 提升？

---

# 21. GitHub 仓库结构建议

## Serving

```text
distributed-llm-serving/
├── README.md
├── docs/
│   ├── architecture.md
│   ├── tensor_parallel.md
│   ├── scheduler.md
│   └── benchmark.md
├── engine/
├── distributed/
│   ├── tp/
│   ├── dp/
│   └── ep/
├── scheduler/
├── cache/
├── benchmark/
├── scripts/
└── results/
```

---

## CUDA

```text
cuda-gemm-lab/
├── README.md
├── kernels/
│   ├── gemm_v1_naive.cu
│   ├── gemm_v2_coalesced.cu
│   ├── gemm_v3_tiled.cu
│   ├── gemm_v4_register.cu
│   ├── gemm_v5_vectorized.cu
│   └── gemm_v6_wmma.cu
├── benchmark/
├── scripts/
├── profile/
└── results/
```

---

# 22. README 必须体现的东西

首页不要先讲实现细节。

第一屏就放：

```text
Problem
Architecture
Key Optimizations
Benchmark Results
```

然后放一张核心表：

| Version      | TTFT | TPOT | Throughput | P99 |
| ------------ | ---: | ---: | ---------: | --: |
| Baseline     |    - |    - |          - |   - |
| TP           |    - |    - |          - |   - |
| Prefix-aware |    - |    - |          - |   - |
| Optimized    |    - |    - |          - |   - |

CUDA 项目同理：

| Kernel | Latency | TFLOPS | vs cuBLAS |
|---|---:|---:|---:|
| Naive | - | - | - |
| Tiled | - | - | - |
| Register | - | - | - |
| WMMA | - | - | - |

---

# 23. 最重要的执行原则

每增加一个新功能前先问：

```text
它解决什么系统问题？
怎么测？
baseline 是谁？
指标是什么？
面试时我能不能解释 trade-off？
```

如果答不上来，就不要优先做。

最终你需要展示的不是：

```text
我实现了
TP / PP / DP / EP / CP
CUDA
Triton
vLLM
NCCL
```

而是：

```text
我发现一个推理系统瓶颈
↓
分析原因
↓
选择并实现优化
↓
通过 benchmark 验证
↓
解释收益与 trade-off
```

这才是 AI Infra 推理侧项目真正有区分度的地方。
