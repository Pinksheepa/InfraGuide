from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

# from pathlib import Path
import requests
import json


# 将 wall_timestamp转换为ISO 8601格式的字符串
def _utc_wall_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def run_one_request(
    endpoint: str, request_body: dict[str, Any], request_id: str, replica_id: str
) -> dict[str, Any]:
    submit_wall_ts = _utc_wall_timestamp()
    submit_monotonic_ns = time.monotonic_ns()

    first_content_wall_ts: str | None = None
    first_content_monotonic_ns: int | None = None
    completed_wall_ts: str | None = None
    completed_monotonic_ns: int | None = None

    output_parts: list[str] = []
    finish_reason: str | None = None
    done_seen = False

    success = False
    error: str | None = None
    http_status: int | None = None

    try:
        with requests.post(endpoint, json=request_body, stream=True) as response:
            response.raise_for_status()
            http_status = response.status_code

            # 处理流式响应SSE的一行
            for line in response.iter_lines(decode_unicode=True):
                line = line.strip()

                # 处理SSE的空行
                if not line:
                    continue

                # 处理data行
                if not line.startswith("data: "):
                    continue

                data = line[len("data: ") :].strip()

                # 处理结束标志[DONE]
                if data == "[DONE]":
                    done_seen = True
                    completed_wall_ts = _utc_wall_timestamp()
                    completed_monotonic_ns = time.monotonic_ns()
                    break

                # 开始解析JSON数据
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(
                        f"Failed to decode JSON from data: {data}"
                    ) from exc

                # 只要data中的choices字段
                choices = chunk.get("choices", [])
                if not choices:
                    continue
                choice = choices[0]

                # 留下choices中的delta字段中的content内容...
                delta = choice.get("delta", {})
                content = delta.get("content")

                # 记录首个content的时间戳
                if content:
                    if first_content_monotonic_ns is None:
                        first_content_wall_ts = _utc_wall_timestamp()
                        first_content_monotonic_ns = time.monotonic_ns()

                    output_parts.append(content)  # 追加到输出列表

                # 记录结束原因finish_reason
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]

            if not done_seen:
                raise RuntimeError("Stream ended without receiving [DONE] signal.")

            success = True

    except requests.HTTPError as e:
        error = f"HTTP error: {str(e)}"

    except requests.RequestException as e:
        error = f"Request failed: {str(e)}"

    except Exception as e:  # noqa: BLE001
        error = rf"JSON\SSE error: {str(e)}"

    # 返回结果字典, 在CLI层输出为JSONL

    return {
        "request_id": request_id,
        "replica_id": replica_id,
        "model_id": request_body.get("model"),
        "request": request_body,
        "endpoint": endpoint,
        "http_status": http_status,
        "timing": {
            "submit_wall_ts": submit_wall_ts,
            "first_content_wall_ts": first_content_wall_ts,
            "completed_wall_ts": completed_wall_ts,
            "submit_monotonic_ns": submit_monotonic_ns,
            "first_content_monotonic_ns": first_content_monotonic_ns,
            "completed_monotonic_ns": completed_monotonic_ns,
            "ttft_ms": (
                (first_content_monotonic_ns - submit_monotonic_ns) / 1_000_000
                if first_content_monotonic_ns is not None
                else None
            ),
            "e2e_ms": (
                (completed_monotonic_ns - submit_monotonic_ns) / 1_000_000
                if completed_monotonic_ns is not None
                else None
            ),
        },
        "output": {
            "text": "".join(output_parts),
            "prompt_tokens": None,
            "completion_tokens": None,
            "finish_reason": finish_reason,
        },
        "done_seen": done_seen,
        "success": success,
        "error": error,
        "validation": {
            "passed": None,
            "expected": None,
            "detail": None,
        },
    }
