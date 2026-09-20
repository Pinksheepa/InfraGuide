from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

from single_request_client import run_one_request
from transformers import AutoTokenizer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a single request to the specified endpoint, and save as JSONL."
    )
    parser.add_argument(
        "--endpoint",
        required=True,
        type=str,
        help="The endpoint URL to send the request to.",
    )
    parser.add_argument(
        "--request-file",
        required=True,
        type=Path,
        help="Path to the JSON file containing the request body.",
    )
    # parser.add_argument("--request-id", type=str, default=str(uuid.uuid4()), help="Optional request ID.")
    parser.add_argument(
        "--replica-id",
        required=True,
        type=str,
        # default="default-replica",
        help="Optional replica ID.",
    )
    parser.add_argument(
        "--jsonl-file", required=True, type=Path, help="Path to the output JSONL file."
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=30.0,
        help="Timeout in seconds for the request.",
    )
    parser.add_argument(
        "--tokenizer-path",
        type=Path,
        required=True,
        help="Path to the local fixed tokenizer snapshot.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        # 1. Load the request body from the specified JSON file
        with open(args.request_file, "r", encoding="utf-8") as f:
            request_body = json.load(f)

    except (OSError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error reading request file: {e}", file=sys.stderr)
        return 2

    # load tokenizer
    try:
        tokenizer = AutoTokenizer.from_pretrained(
            str(args.tokenizer_path),
            local_files_only=True,
            trust_remote_code=False,
        )

    except (OSError, ValueError) as e:
        print(f"Error loading tokenizer: {e}", file=sys.stderr)
        return 2

    # 2. Generate a unique request ID for this request
    request_id = f"s0-{uuid.uuid4()}"

    # 3. Run the request and handle any exceptions

    response = run_one_request(
        endpoint=args.endpoint,
        request_body=request_body,
        request_id=request_id,
        replica_id=args.replica_id,
        timeout=args.timeout_s,
        tokenizer=tokenizer,
    )

    # 4. 写入 JSONL 文件, 无论成功与否
    try:
        output_path = Path(args.jsonl_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(args.jsonl_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(response, ensure_ascii=False) + "\n")

    except OSError as e:
        print(f"Error writing to JSONL file: {e}", file=sys.stderr)
        return 2

    if response.get("success"):
        return 0
    else:
        print(
            f"Request failed: {response.get('error', 'Unknown error')}", file=sys.stderr
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
