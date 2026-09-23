from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

import uvicorn

from round_robin_router import Replica, create_app


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a number") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _port(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("must be in [1, 65535]")
    return number


def _parse_replica(value: str) -> Replica:
    replica_id, separator, endpoint = value.partition("=")
    replica_id = replica_id.strip()
    endpoint = endpoint.strip()
    parsed_endpoint = urlparse(endpoint)
    if (
        not separator
        or not replica_id
        or parsed_endpoint.scheme not in {"http", "https"}
        or not parsed_endpoint.netloc
    ):
        raise argparse.ArgumentTypeError(
            "replica must use the form REPLICA_ID=http://host:port/v1/chat/completions"
        )
    return Replica(replica_id=replica_id, upstream_endpoint=endpoint)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start the single-process S1 streaming Round Robin Router."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Router bind host.")
    parser.add_argument(
        "--port", type=_port, default=8080, help="Router bind port (default: 8080)."
    )
    parser.add_argument(
        "--replica",
        action="append",
        type=_parse_replica,
        required=True,
        metavar="ID=URL",
        help="Exactly two S1 replicas, specified once per replica.",
    )
    parser.add_argument(
        "--decision-jsonl",
        type=Path,
        required=True,
        help="Append route decision and terminal events here.",
    )
    parser.add_argument(
        "--connect-timeout-s",
        type=_positive_float,
        default=5.0,
        help="Selected-upstream connection timeout in seconds (default: 5).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    replicas = tuple(args.replica)
    if len(replicas) != 2:
        print("S1 requires exactly two --replica arguments.", file=sys.stderr)
        return 2
    if len({replica.replica_id for replica in replicas}) != len(replicas):
        print("Replica IDs must be unique.", file=sys.stderr)
        return 2
    if len({replica.upstream_endpoint for replica in replicas}) != len(replicas):
        print("Replica upstream endpoints must be unique.", file=sys.stderr)
        return 2

    try:
        args.decision_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.decision_jsonl.open("a", encoding="utf-8"):
            pass
    except OSError as exc:
        print(f"Unable to prepare decision JSONL: {exc}", file=sys.stderr)
        return 2

    app = create_app(
        replicas=replicas,
        decision_jsonl=args.decision_jsonl,
        connect_timeout_s=args.connect_timeout_s,
    )
    # Passing an app object starts uvicorn with its default single worker. The
    # in-memory Round Robin cursor is intentionally not shared across workers.
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
