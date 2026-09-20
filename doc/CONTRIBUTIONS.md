# 贡献与理解记录

更新：2026-09-20。只记录实际工作；计划不计入已完成贡献。

## 当前记录

| 模块 | 来源 / 底座已有能力 | 用户贡献 | AI 辅助范围 | 验证证据 | 理解状态 | 简历表述 |
|---|---|---|---|---|---|---|
| 带教和项目规划文档 | 原 guide 与 mentor_prompt，来源未追溯 | 明确期限、投入、GPU 资源、目标岗位，授权调整规则与交接 | 修改指导文档，建立入口、checkpoint 和贡献表 | 本目录对应文档；历史 guide 见 archive/guide_before_month_plan.md | 技术理解尚未验收 | 文档规划不计作推理系统实现成果 |
| 单请求记录 schema 与客户端 | 无底座实现；基于当前 vLLM SSE 行为与测量口径 | 提出初始字段和设计尝试；实现 SSE 解析、状态与 record 返回；扩展本地 tokenizer 重编码、末个非空 content 时间和 TPOT estimate | 用户明确要求后直接改写 schema；审查计时/计数口径、静态编译和结果一致性，未代写 SSE 主逻辑 | `doc/s0/request_record_schema.md`、`src/single_request_client.py`、`results/s0/client_record_001.json`、`client_record_error_001.json`、benchmark raw JSONL | 已通过 wall/monotonic、TPOT 近似口径与连接失败隔离 | 不将本地重编码 TPOT 写为服务端逐 token 指标 |
| 单请求 CLI | 无底座实现；复用用户实现的 single request client | 实现 `src/run_single_cli.py`：参数解析、request 文件读取、UUID、client 调用、JSONL 追加与 0/1/2 退出码 | 审查设计与静态编译；按用户“直接继续”授权执行 CLI 的 0/1/2 验收命令，未代写 CLI | `src/run_single_cli.py`、`results/s0/cli_records.jsonl`、`cli_error_records.jsonl`；0/1/2 路径均通过 | TTFT/TPOT 基本口径已在 S0 对话检查；尚待计时功能扩展运行 | 不计作已实现的测量/路由成果 |
| 最小串行 benchmark | vLLM 的 OpenAI-compatible SSE 服务、Transformers tokenizer；未实现或改造 vLLM 内部计时 | 实现 `src/run_benchmark.py`：一次加载 tokenizer/request、串行 warmup/measure、逐请求 JSONL、汇总统计与 0/1/2 退出码；亲自运行 2 warmup + 10 measure 与 runner 连接失败路径 | 一次性给出工作包范围和验收口径；审查并独立重算 raw/summary 和零测量拒绝，未代写 runner | `src/run_benchmark.py`、`results/s0/benchmark/benchmark_run_001.jsonl`、`benchmark_run_001_summary.json`、`benchmark_run_error_001.*` | S0 工程验收通过 | 可表述为实现并验证单卡流式请求测量 harness；不能宣称性能提升或服务端原生 token 时延 |

## 待项目实现后填写

底座已选择 vLLM 0.29.0 与固定 Qwen3-0.6B 模型；版本与来源详见 doc/s0/baseline.md。
用户已实现单请求 client/CLI，详见上表；多副本路由尚未实现。
已有单请求/CLI 验证及 2 warmup + 10 measure 的单卡 benchmark 成功/失败/零测量参数路径。
可验证的结果：该固定小请求下的客户端测量流程与 raw-summary 一致；不是吞吐、尾延迟或策略效果结论。

后续每个模块按 mentor_prompt 第 15 节填写，明确沿用能力、本人改动、AI 代写范围、代码与结果路径。
