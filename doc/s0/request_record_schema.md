# Single-Request Record Schema (Draft)

Part of the [S0 documentation set](README.md).

Status: AI-written design draft at the user's explicit request on 2026-09-16. It is not client implementation code and has not recorded a real request yet.

Each completed request will eventually occupy one JSON line. Before a request, initialize fields whose values are unknown as `null`; fill them only from captured client events or a documented token-counting method.

```json
{
  "request_id": "s0-001",
  "model_id": "qwen3-0.6b-s0",
  "replica_id": "replica-0",
  "request": {
    "messages": [
      {"role": "user", "content": "3+9等于几"}
    ],
    "temperature": 0,
    "max_tokens": 16,
    "stream": true,
    "chat_template_kwargs": {
      "enable_thinking": false
    }
  },
  "timing": {
    "submit_wall_ts": null,
    "first_content_wall_ts": null,
    "completed_wall_ts": null,
    "submit_monotonic_ns": null,
    "first_content_monotonic_ns": null,
    "completed_monotonic_ns": null,
    "ttft_ms": null,
    "e2e_ms": null
  },
  "output": {
    "text": null,
    "prompt_tokens": null,
    "completion_tokens": null,
    "finish_reason": null,
    "tokenization_error": null
  },
  "error": null,
  "success": null,
  "validation": {
    "passed": null,
    "expected": null,
    "detail": null
  }
}
```

## Fill rules

- `*_wall_ts`: RFC 3339 / ISO-8601 UTC string with microseconds, for example `2026-09-17T20:30:11.123456Z`. It supports direct correlation with server logs.
- `submit_*`: immediately before the HTTP request is submitted.
- `first_content_*`: at the first SSE chunk with a non-empty generated `delta.content`; do not use the initial assistant-role chunk with empty content.
- `completed_*`: when the terminal SSE event is observed.
- `ttft_ms`: `(first_content_monotonic_ns - submit_monotonic_ns) / 1_000_000`.
- `e2e_ms`: `(completed_monotonic_ns - submit_monotonic_ns) / 1_000_000`.
- `prompt_tokens` and `completion_tokens`: remain `null` until the client has a specified, reproducible counting source. Never estimate and store a guessed value.
- `output.tokenization_error`: `null` when client-side output-text encoding succeeds or is not requested; otherwise the caught encoding error string. A tokenization failure is a post-processing failure, not an HTTP/SSE transport error.
- `success`: transport/protocol success only: the HTTP request succeeded, SSE data parsed without client error, a terminal `[DONE]` was observed, and `error` is `null`. A `finish_reason` such as `length` can still be transport-successful.
- `validation`: populated by a separate test/evaluation layer, not by `run_one_request`. The evaluator reads `output.text` and records whether a stated expected answer or assertion passed. Leave all validation fields `null` when no evaluation criterion was supplied.

Wall-clock timestamps support correlation with server logs. Monotonic timestamps are the measurement source for durations because wall time can jump or be adjusted. Existing `results/s0/client_record_*.json` artifacts retain their original epoch-float wall-clock values as historical evidence; newly generated records use the ISO-8601 convention above.
