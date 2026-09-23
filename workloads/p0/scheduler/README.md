# P0.1 静态 workload fixture

此目录保存可版本控制的 trace 与 prompt 文本；运行产生的 JSONL、summary、engine 启动配置和 README 副本应保存到忽略的 `results/p0/scheduler/<run-id>/`。

`p0_1_long_short_smoke_candidate.json` 是候选 smoke trace，不是已经校准的性能 workload。它的 prompt 文本由 AI 辅助生成后冻结；runner 运行期间不会调用模型来生成请求。每个 entry 都以相对路径引用 UTF-8 prompt，并保存内容 SHA-256 与本地 chat-template token 数。改动文本、tokenizer 或模板后，先更新 trace 的可验证字段，再运行。

先做无网络校验：

```bash
PYTHONPATH=src .venv/bin/python src/run_scheduler_workload.py \
  --trace-file workloads/p0/scheduler/p0_1_long_short_smoke_candidate.json \
  --tokenizer-path models/Qwen3-0.6B-c1899de \
  --validate-trace
```

校验通过后，使用单卡 engine 的直连 URL 运行。`max-in-flight` 是客户端同步 HTTP 请求上限，不是 vLLM 的 scheduler 配置。输出路径必须尚不存在，避免混合不同 run。

运行前将 `engine_config.template.json` 复制到新的
`results/p0/scheduler/<run-id>/engine_config.json`，填入实际启动命令和观测到的
engine 配置。runner 会拒绝缺少该文件的运行，并在每条 raw record 和 summary 中
保存它的路径与 SHA-256；它不自行启动或修改 engine。

示例（`<run-id>` 必须是新的目录名，endpoint 必须是同一单卡 engine 的直连地址）：

```bash
PYTHONPATH=src .venv/bin/python src/run_scheduler_workload.py \
  --trace-file workloads/p0/scheduler/p0_1_long_short_smoke_candidate.json \
  --tokenizer-path models/Qwen3-0.6B-c1899de \
  --endpoint http://127.0.0.1:8000/v1/chat/completions \
  --replica-id single-gpu-0 \
  --engine-config-file results/p0/scheduler/<run-id>/engine_config.json \
  --max-in-flight 2 \
  --timeout-s 120 \
  --raw-jsonl results/p0/scheduler/<run-id>/raw.jsonl \
  --summary-json results/p0/scheduler/<run-id>/summary.json
```

该命令只在 engine 已由用户按填写后的配置启动时使用。100/200/300 ms 是候选
offset；真实 raw record 尚未证明它们会形成重叠，不应把本 trace 当作已冻结的
contention workload。
