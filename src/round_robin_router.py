from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse


@dataclass(frozen=True)
class Replica:
    """The stable router identity and chat-completions endpoint of one replica."""

    replica_id: str
    upstream_endpoint: str


class RoundRobinState:
    """Single-process Round Robin state.

    The index advances when a valid streaming request is assigned, before any
    upstream I/O. Thus an unavailable replica consumes its turn and S1 never
    silently retries the request on a different replica.
    """

    def __init__(self, replicas: tuple[Replica, ...]) -> None:
        if not replicas:
            raise ValueError("At least one replica is required.")
        self._replicas = replicas
        self._next_replica_index = 0
        self._lock = asyncio.Lock()

    async def choose(self) -> tuple[int, Replica]:
        async with self._lock:
            index = self._next_replica_index
            replica = self._replicas[index]
            self._next_replica_index = (index + 1) % len(self._replicas)
            return index, replica


class DecisionLogger:
    """Append complete JSON objects one-per-line without interleaving writes."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def write(self, record: dict[str, object]) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        async with self._lock:
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write(line)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _request_id(request: Request) -> str:
    incoming_request_id = request.headers.get("x-request-id", "").strip()
    return incoming_request_id or f"router-{uuid.uuid4()}"


def _error_response(
    *, request_id: str, status_code: int, message: str, error_type: str
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers={"X-Request-ID": request_id},
        content={
            "error": {
                "message": message,
                "type": error_type,
                "code": None,
            }
        },
    )


def create_app(
    *,
    replicas: tuple[Replica, ...],
    decision_jsonl: Path,
    connect_timeout_s: float = 5.0,
    upstream_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    """Create the S1 Router app.

    ``upstream_transport`` exists only to allow the no-GPU tests to substitute
    an in-process upstream. Production leaves it as ``None``.
    """

    if connect_timeout_s <= 0:
        raise ValueError("connect_timeout_s must be positive.")

    state = RoundRobinState(replicas)
    logger = DecisionLogger(decision_jsonl)
    timeout = httpx.Timeout(
        connect=connect_timeout_s,
        read=None,
        write=connect_timeout_s,
        pool=connect_timeout_s,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with httpx.AsyncClient(
            timeout=timeout, transport=upstream_transport
        ) as upstream_client:
            app.state.upstream_client = upstream_client
            yield

    app = FastAPI(lifespan=lifespan)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        request_id = _request_id(request)
        body = await request.body()
        try:
            request_body = json.loads(body)
        except json.JSONDecodeError:
            return _error_response(
                request_id=request_id,
                status_code=400,
                message="Request body must be a JSON object.",
                error_type="invalid_request_error",
            )

        if not isinstance(request_body, dict):
            return _error_response(
                request_id=request_id,
                status_code=400,
                message="Request body must be a JSON object.",
                error_type="invalid_request_error",
            )
        if request_body.get("stream") is not True:
            return _error_response(
                request_id=request_id,
                status_code=400,
                message="S1 Router only accepts requests with stream=true.",
                error_type="invalid_request_error",
            )

        route_index, replica = await state.choose()
        route_fields: dict[str, object] = {
            "request_id": request_id,
            "replica_id": replica.replica_id,
            "upstream_endpoint": replica.upstream_endpoint,
            "route_policy": "round_robin",
            "rr_index": route_index,
        }
        await logger.write(
            {
                "event": "route_decision",
                "timestamp": _utc_now(),
                **route_fields,
                "upstream_http_status": None,
                "upstream_success": None,
                "terminal_state": None,
                "error_type": None,
                "error": None,
            }
        )

        async def log_terminal(
            *,
            terminal_state: str,
            upstream_http_status: int | None,
            upstream_success: bool,
            error: BaseException | None = None,
        ) -> None:
            await logger.write(
                {
                    "event": "route_terminal",
                    "timestamp": _utc_now(),
                    **route_fields,
                    "upstream_http_status": upstream_http_status,
                    "upstream_success": upstream_success,
                    "terminal_state": terminal_state,
                    "error_type": type(error).__name__ if error else None,
                    "error": str(error) if error else None,
                }
            )

        upstream_headers = {
            "accept": "text/event-stream",
            "content-type": request.headers.get("content-type", "application/json"),
            "x-request-id": request_id,
        }
        upstream_request = request.app.state.upstream_client.build_request(
            "POST",
            replica.upstream_endpoint,
            content=body,
            headers=upstream_headers,
        )
        try:
            upstream_response = await request.app.state.upstream_client.send(
                upstream_request, stream=True
            )
        except asyncio.CancelledError:
            await asyncio.shield(
                log_terminal(
                    terminal_state="client_disconnected",
                    upstream_http_status=None,
                    upstream_success=False,
                )
            )
            raise
        except httpx.RequestError as exc:
            await log_terminal(
                terminal_state="upstream_connection_failed",
                upstream_http_status=None,
                upstream_success=False,
                error=exc,
            )
            return _error_response(
                request_id=request_id,
                status_code=502,
                message="Unable to connect to the selected upstream replica.",
                error_type="upstream_connection_error",
            )

        if not 200 <= upstream_response.status_code < 300:
            try:
                upstream_error_body = await upstream_response.aread()
            finally:
                await upstream_response.aclose()
            await log_terminal(
                terminal_state="upstream_http_error",
                upstream_http_status=upstream_response.status_code,
                upstream_success=False,
            )
            response_headers = {"X-Request-ID": request_id}
            content_type = upstream_response.headers.get("content-type")
            if content_type:
                response_headers["content-type"] = content_type
            return Response(
                content=upstream_error_body,
                status_code=upstream_response.status_code,
                headers=response_headers,
            )

        async def stream_upstream() -> AsyncIterator[bytes]:
            done_marker = b"data: [DONE]"
            marker_tail = b""
            saw_done = False
            terminal_state = "upstream_stream_failed"
            terminal_error: BaseException | None = None
            try:
                async for chunk in upstream_response.aiter_raw():
                    if chunk:
                        combined = marker_tail + chunk
                        saw_done = saw_done or done_marker in combined
                        marker_tail = combined[-(len(done_marker) - 1) :]
                        yield chunk
                terminal_state = (
                    "completed" if saw_done else "upstream_stream_ended_without_done"
                )
            except asyncio.CancelledError:
                terminal_state = "client_disconnected"
                raise
            except httpx.HTTPError as exc:
                terminal_error = exc
            except Exception as exc:  # noqa: BLE001
                terminal_error = exc
            finally:
                try:
                    await upstream_response.aclose()
                finally:
                    await log_terminal(
                        terminal_state=terminal_state,
                        upstream_http_status=upstream_response.status_code,
                        upstream_success=terminal_state == "completed",
                        error=terminal_error,
                    )

        stream_headers = {
            "X-Request-ID": request_id,
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
        upstream_content_type = upstream_response.headers.get("content-type")
        if upstream_content_type:
            stream_headers["content-type"] = upstream_content_type
        return StreamingResponse(
            stream_upstream(),
            status_code=upstream_response.status_code,
            headers=stream_headers,
        )

    return app
