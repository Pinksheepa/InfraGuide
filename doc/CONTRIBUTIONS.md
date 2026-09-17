# 贡献与理解记录

更新：2026-09-11。只记录实际工作；计划不计入已完成贡献。

## 当前记录

| 模块 | 来源 / 底座已有能力 | 用户贡献 | AI 辅助范围 | 验证证据 | 理解状态 | 简历表述 |
|---|---|---|---|---|---|---|
| 带教和项目规划文档 | 原 guide 与 mentor_prompt，来源未追溯 | 明确期限、投入、GPU 资源、目标岗位，授权调整规则与交接 | 修改指导文档，建立入口、checkpoint 和贡献表 | 本目录对应文档；历史 guide 见 archive/guide_before_month_plan.md | 技术理解尚未验收 | 文档规划不计作推理系统实现成果 |
| 单请求记录 schema 与客户端 | 无底座实现；基于当前 vLLM SSE 行为与测量口径 | 提出初始字段和设计尝试；实现 `src/single_request_client.py` 的 SSE 解析、状态与 record 返回；亲自运行成功和连接失败路径各一次 | 用户明确要求后直接改写 schema；按用户明确要求修改 monotonic 时间字段/毫秒换算与 wall-clock ISO-8601 表示，未代写 SSE 主逻辑或 CLI/benchmark | `doc/s0/request_record_schema.md`、`src/single_request_client.py`、`results/s0/client_record_001.json`、`client_record_error_001.json` | 已通过 wall/monotonic 与连接失败隔离；尚待 CLI/JSONL、TTFT/TPOT 口径 | 不计作已实现的测量/路由成果 |
| 单请求 CLI | 无底座实现；复用用户实现的 single request client | 实现 `src/run_single_cli.py`：参数解析、request 文件读取、UUID、client 调用、JSONL 追加与 0/1/2 退出码 | 审查设计与静态编译；按用户“直接继续”授权执行 CLI 的 0/1/2 验收命令，未代写 CLI | `src/run_single_cli.py`、`results/s0/cli_records.jsonl`、`cli_error_records.jsonl`；0/1/2 路径均通过 | 尚待 TTFT/TPOT 口径与计时功能扩展 | 不计作已实现的测量/路由成果 |

## 待项目实现后填写

底座 URL、固定版本和代码路径：未选择。
用户核心实现、修改、集成/验证：尚未开始。
测试与 benchmark：尚未建立。
可验证的性能结果：Not measured。

后续每个模块按 mentor_prompt 第 15 节填写，明确沿用能力、本人改动、AI 代写范围、代码与结果路径。
