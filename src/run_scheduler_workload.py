"""Run a replayable, bounded-concurrency streaming scheduler workload.

This runner intentionally stays on the client side.  It records planned and
actual client submission times, but never infers a vLLM server queue time from
them.  The existing synchronous ``run_one_request`` function remains the only
HTTP/SSE implementation; worker threads only provide bounded concurrency.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import BoundedSemaphore
from typing import Any

from single_request_client import run_one_request
from transformers import AutoTokenizer, PreTrainedTokenizerBase


PROMPT_TOKEN_SOURCE = (
    "local_apply_chat_template(messages, add_generation_prompt=True)"
)
VALID_CLASSES = {"short", "long"}
VALID_PHASES = {"warmup", "measure"}


@dataclass(frozen=True)
class TraceRequest:
    """One fully resolved request from a trace file."""

    index: int
    request_id: str
    request_class: str
    phase: str
    arrival_offset_ms: float
    prompt_file: str
    prompt_sha256: str
    expected_prompt_tokens: int
    actual_prompt_tokens: int
    request_body: dict[str, Any]


@dataclass(frozen=True)
class PreparedTrace:
    trace_id: str
    trace_path: str
    trace_sha256: str
    tokenizer_chat_template_sha256: str
    requests: list[TraceRequest]


def _utc_wall_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_fingerprint(value: Any) -> str:
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(serialized.encode("utf-8"))


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} must be positive")
    return parsed


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(f"{value!r} must be a positive finite number")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay a static long/short streaming trace with bounded client "
            "concurrency and write raw JSONL plus a grouped summary."
        )
    )
    parser.add_argument(
        "--trace-file",
        required=True,
        type=Path,
        help="Static JSON trace. Prompt paths inside it are relative to this file.",
    )
    parser.add_argument(
        "--tokenizer-path",
        required=True,
        type=Path,
        help="Local fixed tokenizer snapshot used for prompt and output counting.",
    )
    parser.add_argument(
        "--validate-trace",
        action="store_true",
        help="Validate prompt hashes/token counts and print them without network I/O.",
    )
    parser.add_argument(
        "--endpoint",
        help="Direct single-engine streaming chat-completions URL.",
    )
    parser.add_argument(
        "--replica-id",
        help="Engine identifier recorded in each existing client result.",
    )
    parser.add_argument(
        "--engine-config-file",
        type=Path,
        help=(
            "JSON record of the direct engine launch/configuration; required in run "
            "mode and fingerprinted in raw records plus the summary."
        ),
    )
    parser.add_argument(
        "--max-in-flight",
        type=_positive_int,
        help="Maximum requests concurrently executing the synchronous HTTP client.",
    )
    parser.add_argument(
        "--timeout-s",
        type=_positive_float,
        help="Per-request HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--raw-jsonl",
        type=Path,
        help="New raw JSONL output path; existing files are rejected.",
    )
    parser.add_argument(
        "--summary-json",
        type=Path,
        help="New summary JSON output path; existing files are rejected.",
    )
    return parser.parse_args()


def _load_tokenizer(tokenizer_path: Path) -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(
        str(tokenizer_path),
        local_files_only=True,
        trust_remote_code=False,
    )


def _resolve_prompt_path(trace_path: Path, relative_path: str) -> Path:
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError("prompt_file must be relative to the trace file")
    trace_root = trace_path.parent.resolve()
    resolved = (trace_root / candidate).resolve()
    if not resolved.is_relative_to(trace_root):
        raise ValueError(f"prompt_file escapes trace directory: {relative_path}")
    if not resolved.is_file():
        raise ValueError(f"prompt_file does not exist: {relative_path}")
    return resolved


def _count_prompt_tokens(
    tokenizer: PreTrainedTokenizerBase,
    messages: list[dict[str, str]],
    chat_template_kwargs: dict[str, Any],
) -> int:
    rendered = tokenizer.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        **chat_template_kwargs,
    )
    # Transformers versions differ here: this environment returns a
    # BatchEncoding by default, while other supported versions return a list.
    if hasattr(rendered, "get"):
        token_ids = rendered.get("input_ids")
    else:
        token_ids = rendered
    if not isinstance(token_ids, list):
        raise TypeError("Tokenizer returned no list-valued input_ids for the chat template")
    if token_ids and isinstance(token_ids[0], list):
        if len(token_ids) != 1:
            raise TypeError("Expected exactly one chat-template input sequence")
        token_ids = token_ids[0]
    return len(token_ids)


def _validate_defaults(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("trace.request_defaults must be an object")
    if "messages" in value:
        raise ValueError("trace.request_defaults must not contain messages")
    if value.get("stream") is not True:
        raise ValueError("trace.request_defaults.stream must be true")
    if not isinstance(value.get("model"), str) or not value["model"]:
        raise ValueError("trace.request_defaults.model must be a non-empty string")
    if not _is_number(value.get("max_tokens")) or int(value["max_tokens"]) <= 0:
        raise ValueError("trace.request_defaults.max_tokens must be a positive integer")
    if int(value["max_tokens"]) != value["max_tokens"]:
        raise ValueError("trace.request_defaults.max_tokens must be an integer")
    template_kwargs = value.get("chat_template_kwargs", {})
    if not isinstance(template_kwargs, dict):
        raise ValueError("trace.request_defaults.chat_template_kwargs must be an object")
    return copy.deepcopy(value)


def _load_trace(trace_path: Path, tokenizer: PreTrainedTokenizerBase) -> PreparedTrace:
    raw_trace = trace_path.read_bytes()
    try:
        trace = json.loads(raw_trace)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid trace JSON: {exc}") from exc
    if not isinstance(trace, dict):
        raise ValueError("trace must contain an object")
    trace_id = trace.get("trace_id")
    if not isinstance(trace_id, str) or not trace_id:
        raise ValueError("trace.trace_id must be a non-empty string")
    request_defaults = _validate_defaults(trace.get("request_defaults"))
    raw_requests = trace.get("requests")
    if not isinstance(raw_requests, list) or not raw_requests:
        raise ValueError("trace.requests must be a non-empty array")

    request_ids: set[str] = set()
    requests: list[TraceRequest] = []
    for index, raw_request in enumerate(raw_requests):
        if not isinstance(raw_request, dict):
            raise ValueError(f"trace.requests[{index}] must be an object")
        request_id = raw_request.get("request_id")
        if not isinstance(request_id, str) or not request_id:
            raise ValueError(f"trace.requests[{index}].request_id must be a non-empty string")
        if request_id in request_ids:
            raise ValueError(f"duplicate trace request_id: {request_id}")
        request_ids.add(request_id)

        request_class = raw_request.get("request_class")
        if request_class not in VALID_CLASSES:
            raise ValueError(
                f"trace.requests[{index}].request_class must be short or long"
            )
        phase = raw_request.get("phase", "measure")
        if phase not in VALID_PHASES:
            raise ValueError(f"trace.requests[{index}].phase must be warmup or measure")
        arrival_offset_ms = raw_request.get("arrival_offset_ms")
        if not _is_number(arrival_offset_ms) or not math.isfinite(arrival_offset_ms):
            raise ValueError(
                f"trace.requests[{index}].arrival_offset_ms must be a finite number"
            )
        if float(arrival_offset_ms) < 0:
            raise ValueError(f"trace.requests[{index}].arrival_offset_ms must be >= 0")

        prompt_file = raw_request.get("prompt_file")
        expected_prompt_sha256 = raw_request.get("prompt_sha256")
        if not isinstance(prompt_file, str) or not prompt_file:
            raise ValueError(f"trace.requests[{index}].prompt_file must be a string")
        if (
            not isinstance(expected_prompt_sha256, str)
            or len(expected_prompt_sha256) != 64
        ):
            raise ValueError(
                f"trace.requests[{index}].prompt_sha256 must be a SHA-256 hex string"
            )
        expected_prompt_tokens = raw_request.get("expected_prompt_tokens")
        if (
            not isinstance(expected_prompt_tokens, int)
            or isinstance(expected_prompt_tokens, bool)
            or expected_prompt_tokens <= 0
        ):
            raise ValueError(
                f"trace.requests[{index}].expected_prompt_tokens must be a positive integer"
            )

        prompt_path = _resolve_prompt_path(trace_path, prompt_file)
        prompt_bytes = prompt_path.read_bytes()
        actual_prompt_sha256 = _sha256_bytes(prompt_bytes)
        if actual_prompt_sha256 != expected_prompt_sha256:
            raise ValueError(
                f"prompt SHA-256 mismatch for {prompt_file}: expected "
                f"{expected_prompt_sha256}, got {actual_prompt_sha256}"
            )
        try:
            prompt_text = prompt_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"prompt_file must be UTF-8 text: {prompt_file}") from exc
        messages = [{"role": "user", "content": prompt_text}]
        chat_template_kwargs = request_defaults.get("chat_template_kwargs", {})
        actual_prompt_tokens = _count_prompt_tokens(
            tokenizer, messages, chat_template_kwargs
        )
        if actual_prompt_tokens != expected_prompt_tokens:
            raise ValueError(
                f"prompt token mismatch for {request_id}: expected "
                f"{expected_prompt_tokens}, got {actual_prompt_tokens}"
            )

        request_body = copy.deepcopy(request_defaults)
        request_body["messages"] = messages
        requests.append(
            TraceRequest(
                index=index,
                request_id=request_id,
                request_class=request_class,
                phase=phase,
                arrival_offset_ms=float(arrival_offset_ms),
                prompt_file=prompt_file,
                prompt_sha256=actual_prompt_sha256,
                expected_prompt_tokens=expected_prompt_tokens,
                actual_prompt_tokens=actual_prompt_tokens,
                request_body=request_body,
            )
        )

    return PreparedTrace(
        trace_id=trace_id,
        trace_path=str(trace_path),
        trace_sha256=_sha256_bytes(raw_trace),
        tokenizer_chat_template_sha256=_json_fingerprint(tokenizer.chat_template),
        requests=requests,
    )


def _trace_validation_view(trace: PreparedTrace) -> dict[str, Any]:
    return {
        "trace_id": trace.trace_id,
        "trace_path": trace.trace_path,
        "trace_sha256": trace.trace_sha256,
        "tokenizer_chat_template_sha256": trace.tokenizer_chat_template_sha256,
        "prompt_token_count_source": PROMPT_TOKEN_SOURCE,
        "requests": [
            {
                "request_id": request.request_id,
                "request_class": request.request_class,
                "phase": request.phase,
                "arrival_offset_ms": request.arrival_offset_ms,
                "prompt_file": request.prompt_file,
                "prompt_sha256": request.prompt_sha256,
                "expected_prompt_tokens": request.expected_prompt_tokens,
                "actual_prompt_tokens": request.actual_prompt_tokens,
            }
            for request in trace.requests
        ],
    }


def _prepare_new_output_paths(raw_jsonl: Path, summary_json: Path) -> None:
    if raw_jsonl.resolve() == summary_json.resolve():
        raise ValueError("raw-jsonl and summary-json must be different paths")
    for path in (raw_jsonl, summary_json):
        if path.exists():
            raise FileExistsError(
                f"refusing to mix runs by overwriting existing output: {path}"
            )
        path.parent.mkdir(parents=True, exist_ok=True)


def _load_engine_config(path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    try:
        config = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid engine config JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("engine config must contain a JSON object")
    return {
        "path": str(path),
        "sha256": _sha256_bytes(payload),
        "config": config,
    }


def _append_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as output_stream:
        output_stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _unexpected_failure_result(
    *,
    endpoint: str,
    request: TraceRequest,
    replica_id: str,
    submit_wall_ts: str,
    submit_monotonic_ns: int,
    error: Exception,
) -> dict[str, Any]:
    """Preserve one terminal record even if the existing client unexpectedly raises."""
    return {
        "request_id": request.request_id,
        "replica_id": replica_id,
        "model_id": request.request_body.get("model"),
        "request": request.request_body,
        "endpoint": endpoint,
        "http_status": None,
        "timing": {
            "submit_wall_ts": submit_wall_ts,
            "first_content_wall_ts": None,
            "completed_wall_ts": None,
            "last_content_wall_ts": None,
            "submit_monotonic_ns": submit_monotonic_ns,
            "first_content_monotonic_ns": None,
            "completed_monotonic_ns": None,
            "last_content_monotonic_ns": None,
            "ttft_ms": None,
            "e2e_ms": None,
            "tpot_ms": None,
        },
        "output": {
            "text": "",
            "prompt_tokens": None,
            "completion_tokens": None,
            "completion_token_count_source": None,
            "tokenization_error": None,
            "finish_reason": None,
        },
        "done_seen": False,
        "success": False,
        "error": f"workload worker error: {type(error).__name__}: {error}",
        "validation": {"passed": None, "expected": None, "detail": None},
    }


def _execute_request(
    *,
    endpoint: str,
    request: TraceRequest,
    trace: PreparedTrace,
    run_id: str,
    run_start_monotonic_ns: int,
    replica_id: str,
    tokenizer: PreTrainedTokenizerBase,
    timeout_s: float,
    planned_submit_monotonic_ns: int,
    in_flight_slots: BoundedSemaphore,
    engine_config: dict[str, Any],
) -> dict[str, Any]:
    worker_start_monotonic_ns = time.monotonic_ns()
    worker_start_wall_ts = _utc_wall_timestamp()
    try:
        result = run_one_request(
            endpoint=endpoint,
            request_body=request.request_body,
            request_id=request.request_id,
            replica_id=replica_id,
            tokenizer=tokenizer,
            timeout=timeout_s,
        )
    except Exception as exc:  # Preserve a record if a client contract unexpectedly breaks.
        result = _unexpected_failure_result(
            endpoint=endpoint,
            request=request,
            replica_id=replica_id,
            submit_wall_ts=worker_start_wall_ts,
            submit_monotonic_ns=worker_start_monotonic_ns,
            error=exc,
        )
    terminal_monotonic_ns = time.monotonic_ns()
    terminal_wall_ts = _utc_wall_timestamp()
    try:
        actual_submit_monotonic_ns = result.get("timing", {}).get(
            "submit_monotonic_ns", worker_start_monotonic_ns
        )
        if not _is_number(actual_submit_monotonic_ns):
            actual_submit_monotonic_ns = worker_start_monotonic_ns
        actual_submit_monotonic_ns = int(actual_submit_monotonic_ns)
        result.setdefault("output", {})["prompt_tokens"] = request.actual_prompt_tokens
        result["output"]["prompt_token_count_source"] = PROMPT_TOKEN_SOURCE
        return {
            "run_id": run_id,
            "engine_config": {
                "path": engine_config["path"],
                "sha256": engine_config["sha256"],
            },
            "trace": {
                "trace_id": trace.trace_id,
                "trace_path": trace.trace_path,
                "trace_sha256": trace.trace_sha256,
                "request_id": request.request_id,
                "request_class": request.request_class,
                "phase": request.phase,
                "arrival_offset_ms": request.arrival_offset_ms,
                "prompt_file": request.prompt_file,
                "prompt_sha256": request.prompt_sha256,
                "expected_prompt_tokens": request.expected_prompt_tokens,
                "actual_prompt_tokens": request.actual_prompt_tokens,
                "prompt_token_count_source": PROMPT_TOKEN_SOURCE,
            },
            "workload_timing": {
                "run_start_monotonic_ns": run_start_monotonic_ns,
                "planned_submit_monotonic_ns": planned_submit_monotonic_ns,
                "worker_start_monotonic_ns": worker_start_monotonic_ns,
                "actual_submit_monotonic_ns": actual_submit_monotonic_ns,
                "client_schedule_delay_ms": (
                    actual_submit_monotonic_ns - planned_submit_monotonic_ns
                )
                / 1_000_000,
                "terminal_monotonic_ns": terminal_monotonic_ns,
                "terminal_wall_ts": terminal_wall_ts,
            },
            "request_result": result,
        }
    finally:
        in_flight_slots.release()


def _sleep_until(deadline_monotonic_ns: int) -> None:
    while True:
        remaining_ns = deadline_monotonic_ns - time.monotonic_ns()
        if remaining_ns <= 0:
            return
        time.sleep(remaining_ns / 1_000_000_000)


def _numeric_samples(
    records: list[dict[str, Any]], metric_name: str
) -> list[float]:
    samples: list[float] = []
    for record in records:
        result = record["request_result"]
        if result.get("success") is not True:
            continue
        value = result.get("timing", {}).get(metric_name)
        if _is_number(value):
            samples.append(float(value))
    return samples


def _percentile(samples: list[float], percentile: float) -> float | None:
    if not samples:
        return None
    values = sorted(samples)
    index = (len(values) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return values[lower]
    fraction = index - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _metric_summary(samples: list[float]) -> dict[str, int | float | None]:
    if not samples:
        return {
            "valid_samples": 0,
            "mean": None,
            "p50": None,
            "p95": None,
            "p99": None,
        }
    return {
        "valid_samples": len(samples),
        "mean": statistics.fmean(samples),
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "p99": _percentile(samples, 0.99),
    }


def _output_tokens(records: list[dict[str, Any]]) -> tuple[int, int]:
    token_sum = 0
    valid_count = 0
    for record in records:
        result = record["request_result"]
        if result.get("success") is not True:
            continue
        token_count = result.get("output", {}).get("completion_tokens")
        if isinstance(token_count, int) and not isinstance(token_count, bool):
            token_sum += token_count
            valid_count += 1
    return token_sum, valid_count


def _group_summary(
    records: list[dict[str, Any]], throughput_window_s: float | None
) -> dict[str, Any]:
    success_count = sum(
        record["request_result"].get("success") is True for record in records
    )
    token_sum, token_sample_count = _output_tokens(records)
    return {
        "request_counts": {
            "total": len(records),
            "success": success_count,
            "failure": len(records) - success_count,
        },
        "metrics": {
            "ttft_ms": _metric_summary(_numeric_samples(records, "ttft_ms")),
            "e2e_ms": _metric_summary(_numeric_samples(records, "e2e_ms")),
            "tpot_ms": _metric_summary(_numeric_samples(records, "tpot_ms")),
        },
        "throughput": {
            "window_scope": "shared_all_request_window",
            "successful_requests_per_s": (
                success_count / throughput_window_s
                if throughput_window_s is not None and throughput_window_s > 0
                else None
            ),
            "output_tokens_per_s": (
                token_sum / throughput_window_s
                if throughput_window_s is not None and throughput_window_s > 0
                else None
            ),
            "output_token_sum": token_sum,
            "valid_output_token_samples": token_sample_count,
            "output_token_count_source": "local_reencode_output_text",
        },
    }


def _client_overlap_checks(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    longs = [
        record
        for record in records
        if record["trace"]["request_class"] == "long"
    ]
    shorts = [
        record
        for record in records
        if record["trace"]["request_class"] == "short"
    ]
    checks: list[dict[str, Any]] = []
    for long_record in longs:
        long_timing = long_record["workload_timing"]
        long_start = long_timing["actual_submit_monotonic_ns"]
        long_terminal = long_timing["terminal_monotonic_ns"]
        for short_record in shorts:
            short_submit = short_record["workload_timing"]["actual_submit_monotonic_ns"]
            checks.append(
                {
                    "long_request_id": long_record["trace"]["request_id"],
                    "short_request_id": short_record["trace"]["request_id"],
                    "long_actual_submit_monotonic_ns": long_start,
                    "short_actual_submit_monotonic_ns": short_submit,
                    "long_terminal_monotonic_ns": long_terminal,
                    "short_submitted_while_long_in_flight": (
                        long_start <= short_submit < long_terminal
                    ),
                }
            )
    return checks


def build_summary(
    *,
    run_id: str,
    endpoint: str,
    trace: PreparedTrace,
    tokenizer_path: Path,
    replica_id: str,
    max_in_flight: int,
    timeout_s: float,
    engine_config: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    if not records:
        raise ValueError("cannot summarize an empty workload")
    start_ns = min(
        record["workload_timing"]["actual_submit_monotonic_ns"] for record in records
    )
    end_ns = max(
        record["workload_timing"]["terminal_monotonic_ns"] for record in records
    )
    window_s = (end_ns - start_ns) / 1_000_000_000
    by_phase: dict[str, dict[str, Any]] = {}
    for phase in sorted({record["trace"]["phase"] for record in records}):
        phase_records = [record for record in records if record["trace"]["phase"] == phase]
        by_phase[phase] = {
            "all": _group_summary(phase_records, window_s),
            "short": _group_summary(
                [record for record in phase_records if record["trace"]["request_class"] == "short"],
                window_s,
            ),
            "long": _group_summary(
                [record for record in phase_records if record["trace"]["request_class"] == "long"],
                window_s,
            ),
        }
    return {
        "run_id": run_id,
        "config": {
            "endpoint": endpoint,
            "trace_id": trace.trace_id,
            "trace_path": trace.trace_path,
            "trace_sha256": trace.trace_sha256,
            "tokenizer_path": str(tokenizer_path),
            "tokenizer_chat_template_sha256": trace.tokenizer_chat_template_sha256,
            "replica_id": replica_id,
            "max_in_flight": max_in_flight,
            "timeout_s": timeout_s,
            "engine_config": engine_config,
        },
        "measurement_boundary": {
            "queue_time": None,
            "queue_time_status": "N/A",
            "queue_time_reason": (
                "Client planned/actual submission timestamps do not identify vLLM "
                "server queue time."
            ),
            "throughput_window": {
                "definition": (
                    "minimum actual_submit_monotonic_ns through maximum client terminal "
                    "timestamp across every request, including failures/timeouts"
                ),
                "start_monotonic_ns": start_ns,
                "end_monotonic_ns": end_ns,
                "duration_ms": (end_ns - start_ns) / 1_000_000,
            },
            "drain_rule": (
                "After the final planned trace arrival, wait for every submitted request "
                "to return a success or failure/timeout terminal record before summary."
            ),
            "percentile_method": "linear interpolation over sorted samples using index=(n-1)*p",
            "tpot_status": "client-side estimate; not server-native per-token ITL",
        },
        "request_counts": {
            "total": len(records),
            "success": sum(
                record["request_result"].get("success") is True for record in records
            ),
            "failure": sum(
                record["request_result"].get("success") is not True for record in records
            ),
        },
        "groups": {
            "all": _group_summary(records, window_s),
            "short": _group_summary(
                [record for record in records if record["trace"]["request_class"] == "short"],
                window_s,
            ),
            "long": _group_summary(
                [record for record in records if record["trace"]["request_class"] == "long"],
                window_s,
            ),
        },
        "by_phase": by_phase,
        "client_overlap_checks": _client_overlap_checks(records),
    }


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as summary_stream:
        json.dump(summary, summary_stream, ensure_ascii=False, indent=2)
        summary_stream.write("\n")


def _required_run_arguments(args: argparse.Namespace) -> list[str]:
    required = {
        "--endpoint": args.endpoint,
        "--replica-id": args.replica_id,
        "--engine-config-file": args.engine_config_file,
        "--max-in-flight": args.max_in_flight,
        "--timeout-s": args.timeout_s,
        "--raw-jsonl": args.raw_jsonl,
        "--summary-json": args.summary_json,
    }
    return [name for name, value in required.items() if value is None]


def main() -> int:
    args = parse_args()
    try:
        tokenizer = _load_tokenizer(args.tokenizer_path)
        trace = _load_trace(args.trace_file, tokenizer)
    except (OSError, ValueError, TypeError) as exc:
        print(f"Trace setup failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # AutoTokenizer can emit dependency-specific errors.
        print(f"Tokenizer load failed: {exc}", file=sys.stderr)
        return 2

    if args.validate_trace:
        print(json.dumps(_trace_validation_view(trace), ensure_ascii=False, indent=2))
        return 0

    missing = _required_run_arguments(args)
    if missing:
        print(
            f"Run mode requires: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 2
    assert args.endpoint is not None
    assert args.replica_id is not None
    assert args.max_in_flight is not None
    assert args.timeout_s is not None
    assert args.raw_jsonl is not None
    assert args.summary_json is not None
    assert args.engine_config_file is not None
    try:
        engine_config = _load_engine_config(args.engine_config_file)
        _prepare_new_output_paths(args.raw_jsonl, args.summary_json)
    except (OSError, ValueError) as exc:
        print(f"Output setup failed: {exc}", file=sys.stderr)
        return 2

    run_id = str(uuid.uuid4())
    run_start_monotonic_ns = time.monotonic_ns()
    in_flight_slots = BoundedSemaphore(args.max_in_flight)
    futures: list[Future[dict[str, Any]]] = []
    ordered_requests = sorted(trace.requests, key=lambda request: (request.arrival_offset_ms, request.index))

    try:
        with ThreadPoolExecutor(max_workers=args.max_in_flight) as executor:
            for request in ordered_requests:
                planned_submit_monotonic_ns = run_start_monotonic_ns + int(
                    request.arrival_offset_ms * 1_000_000
                )
                _sleep_until(planned_submit_monotonic_ns)
                # Waiting here is intentional client-side backlog, not server queue time.
                in_flight_slots.acquire()
                try:
                    future = executor.submit(
                        _execute_request,
                        endpoint=args.endpoint,
                        request=request,
                        trace=trace,
                        run_id=run_id,
                        run_start_monotonic_ns=run_start_monotonic_ns,
                        replica_id=args.replica_id,
                        tokenizer=tokenizer,
                        timeout_s=args.timeout_s,
                        planned_submit_monotonic_ns=planned_submit_monotonic_ns,
                        in_flight_slots=in_flight_slots,
                        engine_config=engine_config,
                    )
                except Exception:
                    in_flight_slots.release()
                    raise
                futures.append(future)

            records: list[dict[str, Any]] = []
            for future in as_completed(futures):
                record = future.result()
                _append_record(args.raw_jsonl, record)
                records.append(record)
        summary = build_summary(
            run_id=run_id,
            endpoint=args.endpoint,
            trace=trace,
            tokenizer_path=args.tokenizer_path,
            replica_id=args.replica_id,
            max_in_flight=args.max_in_flight,
            timeout_s=args.timeout_s,
            engine_config=engine_config,
            records=records,
        )
        _write_summary(args.summary_json, summary)
    except OSError as exc:
        print(f"Result write failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # Keep unexpected runner faults visible after raw records exist.
        print(f"Workload run failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    return 0 if all(record["request_result"].get("success") is True for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
