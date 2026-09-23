from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

# from pathlib import Path
import requests
from transformers import PreTrainedTokenizerBase


# 将 wall_timestamp转换为ISO 8601格式的字符串
def _utc_wall_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


# tokenizer 用于重编码输出的文本, 用于估算TPOT, 实际应该使用vllm中记录的tokenID
def tokenize_text(tokenizer: PreTrainedTokenizerBase, text: str) -> list[int]:
    return tokenizer.encode(text, add_special_tokens=False)


def run_one_request(
    endpoint: str,
    request_body: dict[str, Any],
    request_id: str,
    replica_id: str,
    tokenizer: PreTrainedTokenizerBase,
    timeout: float,
) -> dict[str, Any]:
    submit_wall_ts = _utc_wall_timestamp()
    submit_monotonic_ns = time.monotonic_ns()

    first_content_wall_ts: str | None = None
    first_content_monotonic_ns: int | None = None
    completed_wall_ts: str | None = None
    completed_monotonic_ns: int | None = None
    # 新增last_content_wall_ts和last_content_monotonic_ns
    # 用于估算TPOT
    last_content_wall_ts: str | None = None
    last_content_monotonic_ns: int | None = None

    output_parts: list[str] = []
    output_text = ""
    completion_tokens: int | None = None
    completion_token_count_source: str | None = None
    tokenization_error: str | None = None
    finish_reason: str | None = None
    done_seen = False

    success = False
    error: str | None = None
    http_status: int | None = None

    try:
        with requests.post(
            endpoint,
            json=request_body,
            headers={"X-Request-ID": request_id},
            stream=True,
            timeout=timeout,
        ) as response:
            http_status = response.status_code
            response.raise_for_status()

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

                    # 记录最后一个content的时间戳
                    last_content_wall_ts = _utc_wall_timestamp()
                    last_content_monotonic_ns = time.monotonic_ns()

                    output_parts.append(content)  # 追加到输出列表

                # 记录结束原因finish_reason
                if choice.get("finish_reason") is not None:
                    finish_reason = choice["finish_reason"]

            if not done_seen:
                raise RuntimeError("Stream ended without receiving [DONE] signal.")

            # 重编码输出文本, 用于估算TPOT
            output_text = "".join(output_parts)
            try:
                completion_tokens = len(tokenize_text(tokenizer, output_text))
                completion_token_count_source = "local_reencode_output_text"
            except Exception as e:  # noqa: BLE001
                tokenization_error = f"Tokenization error: {e!s}"

            success = True

    except requests.HTTPError as e:
        error = f"HTTP error: {e!s}"

    except requests.RequestException as e:
        error = f"Request failed: {e!s}"

    except Exception as e:  # noqa: BLE001
        error = f"SSE/JSON error: {e!s}"

    # Preserve content already received when an SSE stream fails before [DONE].
    if not output_text:
        output_text = "".join(output_parts)

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
            # 估算用
            "last_content_wall_ts": last_content_wall_ts,
            "submit_monotonic_ns": submit_monotonic_ns,
            "first_content_monotonic_ns": first_content_monotonic_ns,
            "completed_monotonic_ns": completed_monotonic_ns,
            # 估算用
            "last_content_monotonic_ns": last_content_monotonic_ns,
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
            "tpot_ms": (
                (last_content_monotonic_ns - first_content_monotonic_ns)
                / (completion_tokens - 1)
                / 1_000_000
                if (
                    last_content_monotonic_ns is not None
                    and first_content_monotonic_ns is not None
                    and completion_tokens is not None
                    and completion_tokens >= 2
                )
                else None
            ),
        },
        "output": {
            "text": output_text,
            "prompt_tokens": None,
            "completion_tokens": completion_tokens,
            "completion_token_count_source": completion_token_count_source,
            "tokenization_error": tokenization_error,
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
