"""
PYTHONPATH=src .venv/bin/python src/run_benchmark.py \
  --endpoint http://127.0.0.1:8000/v1/chat/completions \
  --request-file results/s0/request/request_002.json \
  --tokenizer-path models/Qwen3-0.6B-c1899de \
  --replica-id replica-0 \
  --warmup 2 \
  --repeat 10 \
  --timeout-s 30 \
  --raw-jsonl results/s0/benchmark/benchmark_run_001.jsonl \
  --summary-json results/s0/benchmark/benchmark_run_001_summary.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import uuid
from pathlib import Path
from typing import Any

from single_request_client import run_one_request
from transformers import AutoTokenizer, PreTrainedTokenizerBase


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a serial streaming benchmark and write request records plus a summary."
    )
    parser.add_argument(
        "--endpoint", required=True, help="Streaming chat-completions URL."
    )
    parser.add_argument(
        "--request-file",
        required=True,
        type=Path,
        help="JSON file containing one request body.",
    )
    parser.add_argument(
        "--tokenizer-path",
        required=True,
        type=Path,
        help="Local fixed tokenizer snapshot used to re-encode output text.",
    )
    parser.add_argument(
        "--replica-id", required=True, help="Identifier recorded for this replica."
    )
    parser.add_argument(
        "--raw-jsonl",
        required=True,
        type=Path,
        help="Append one record per request to this JSONL file.",
    )
    parser.add_argument(
        "--summary-json",
        required=True,
        type=Path,
        help="Write benchmark summary JSON to this path.",
    )

    # # warmup >= 0
    # def non_negative_int(x: str) -> int:
    #     try:
    #         x = int(x)
    #     except ValueError:
    #         raise argparse.ArgumentTypeError(f"{x} is not an integer")
    #     if x < 0:
    #         raise argparse.ArgumentTypeError("must be >= 0")
    #     return x

    parser.add_argument(
        "--warmup",
        type=int,
        default=2,
        help="Serial warmup request count (default: 2).",
    )

    # # repeat > 0
    # def positive_int(value: str) -> int:
    #     try:
    #         ivalue = int(value)
    #     except ValueError:
    #         raise argparse.ArgumentTypeError(f"{value} is not an integer")
    #     if ivalue <= 0:
    #         raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
    #     return ivalue

    parser.add_argument(
        "--repeat",
        type=int,
        default=10,
        help="Serial measured request count (default: 10).",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        help="Per-request HTTP timeout in seconds.",
    )
    return parser.parse_args()


def _load_request_body(request_file: Path) -> dict[str, Any]:
    with request_file.open("r", encoding="utf-8") as request_stream:
        request_body = json.load(request_stream)
    if not isinstance(request_body, dict):
        raise TypeError("Request JSON must contain an object.")
    return request_body


def _load_tokenizer(tokenizer_path: Path) -> PreTrainedTokenizerBase:
    return AutoTokenizer.from_pretrained(
        str(tokenizer_path),
        local_files_only=True,
        trust_remote_code=False,
    )


def _prepare_output_path(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Check permissions before requests are sent. Do not truncate either output.
    with path.open("a", encoding="utf-8"):
        pass


def _append_record(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as output_stream:
        output_stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _numeric_measure_samples(
    measure_records: list[dict[str, Any]], metric_name: str
) -> list[float]:
    samples: list[float] = []
    for record in measure_records:
        if record.get("success") is not True:
            continue
        value = record.get("timing", {}).get(metric_name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            samples.append(float(value))
    return samples


def _metric_summary(samples: list[float]) -> dict[str, int | float | None]:
    if not samples:
        return {"valid_samples": 0, "mean": None, "median": None}
    return {
        "valid_samples": len(samples),
        "mean": statistics.fmean(samples),
        "median": statistics.median(samples),
    }


def build_summary(
    *,
    run_id: str,
    endpoint: str,
    request_file: Path,
    tokenizer_path: Path,
    replica_id: str,
    request_body: dict[str, Any],
    warmup: int,
    repeat: int,
    timeout_s: float,
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    warmup_records = [record for record in records if record.get("phase") == "warmup"]
    measure_records = [record for record in records if record.get("phase") == "measure"]
    success_count = sum(record.get("success") is True for record in records)
    failure_count = len(records) - success_count

    def phase_counts(phase_records: list[dict[str, Any]]) -> dict[str, int]:
        phase_success_count = sum(
            record.get("success") is True for record in phase_records
        )
        return {
            "total": len(phase_records),
            "success": phase_success_count,
            "failure": len(phase_records) - phase_success_count,
        }

    return {
        "run_id": run_id,
        "config": {
            "endpoint": endpoint,
            "request_file": str(request_file),
            "tokenizer_path": str(tokenizer_path),
            "replica_id": replica_id,
            "request_body": request_body,
            "warmup": warmup,
            "repeat": repeat,
            "timeout_s": timeout_s,
        },
        "request_counts": {
            "warmup": len(warmup_records),
            "measure": len(measure_records),
            "total": len(records),
        },
        "phase_counts": {
            "warmup": phase_counts(warmup_records),
            "measure": phase_counts(measure_records),
        },
        "success_count": success_count,
        "failure_count": failure_count,
        "measure_metrics": {
            "ttft_ms": _metric_summary(
                _numeric_measure_samples(measure_records, "ttft_ms")
            ),
            "e2e_ms": _metric_summary(
                _numeric_measure_samples(measure_records, "e2e_ms")
            ),
            "tpot_ms": _metric_summary(
                _numeric_measure_samples(measure_records, "tpot_ms")
            ),
        },
    }


def _write_summary(path: Path, summary: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as summary_stream:
        json.dump(summary, summary_stream, ensure_ascii=False, indent=2)
        summary_stream.write("\n")


def main() -> int:
    args = parse_args()
    if args.warmup < 0 or args.repeat <= 0 or args.timeout_s <= 0:
        print(
            "warmup/repeat must be non-negative and timeout-s must be positive.",
            file=sys.stderr,
        )
        return 2
    if args.raw_jsonl.resolve() == args.summary_json.resolve():
        print("raw-jsonl and summary-json must be different paths.", file=sys.stderr)
        return 2

    try:
        request_body = _load_request_body(args.request_file)
        tokenizer = _load_tokenizer(args.tokenizer_path)
        _prepare_output_path(args.raw_jsonl)
        _prepare_output_path(args.summary_json)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Benchmark setup failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # AutoTokenizer emits several dependency-specific errors.
        print(f"Tokenizer load failed: {exc}", file=sys.stderr)
        return 2

    run_id = str(uuid.uuid4())
    records: list[dict[str, Any]] = []
    for phase, count in (("warmup", args.warmup), ("measure", args.repeat)):
        for _ in range(count):
            record = run_one_request(
                endpoint=args.endpoint,
                request_body=request_body,
                request_id=str(uuid.uuid4()),
                replica_id=args.replica_id,
                tokenizer=tokenizer,
                timeout=args.timeout_s,
            )
            record["run_id"] = run_id
            record["phase"] = phase
            try:
                _append_record(args.raw_jsonl, record)
            except OSError as exc:
                print(f"Raw JSONL write failed: {exc}", file=sys.stderr)
                return 2
            records.append(record)

    summary = build_summary(
        run_id=run_id,
        endpoint=args.endpoint,
        request_file=args.request_file,
        tokenizer_path=args.tokenizer_path,
        replica_id=args.replica_id,
        request_body=request_body,
        warmup=args.warmup,
        repeat=args.repeat,
        timeout_s=args.timeout_s,
        records=records,
    )
    try:
        _write_summary(args.summary_json, summary)
    except OSError as exc:
        print(f"Summary JSON write failed: {exc}", file=sys.stderr)
        return 2

    measure_succeeded = all(
        record.get("success") is True
        for record in records
        if record.get("phase") == "measure"
    )
    return 0 if measure_succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
