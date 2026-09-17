# S0 Single-Replica Baseline Plan

Part of the [S0 documentation set](README.md).

Approved: 2026-09-15. This is a model-selection decision, not a record of a completed model download, engine startup, or inference result.

## Fixed model candidate

| Field | Value |
|---|---|
| Hugging Face model ID | `Qwen/Qwen3-0.6B` |
| Revision | `c1899de289a04d12100db370d81485cdf75e47ca` |
| Weight dtype | `bfloat16` |
| Serving runtime | vLLM 0.29.0 |
| PyTorch runtime | 2.13.0+cu130 |

Source: https://huggingface.co/Qwen/Qwen3-0.6B/tree/c1899de289a04d12100db370d81485cdf75e47ca

## Rationale and boundaries

- User rationale: the approximately 0.6B-parameter model is appropriate for rapid S0 iteration.
- [verified from source][h] The revision's `model.safetensors` is about 1.5 GB. That is the model weight artifact, not the total serving-memory requirement.
- [planned][h] A 32 GiB RTX 5090 leaves a substantial but unmeasured budget for the KV cache, model runtime, and temporary allocations. The actual engine configuration must set and record a finite context/cache budget.

## Risks to test

1. Installed vLLM/PyTorch may still fail during engine initialization or kernel selection.
2. The model snapshot download may fail or be incomplete.
3. Results from a 0.6B model may not extrapolate to larger models; they establish the router/measurement loop first.

## Approved first engine configuration

This is a conservative startup configuration for a single idle RTX 5090, not a performance-tuned configuration:

| Parameter | Value | Limit imposed |
|---|---:|---|
| `gpu_memory_utilization` | `0.5` | vLLM executor's target budget is about half the GPU memory |
| `max_model_len` | `2048` | maximum prompt plus output tokens per sequence |
| request `max_tokens` | `128` | maximum generated tokens per request |
| `max_num_seqs` | `2` | sequences simultaneously admitted by one engine |

User explanation accepted on 2026-09-15: context, output, and concurrent-sequence caps reduce the KV cache and supporting runtime allocation required by the first engine run, reducing (but not eliminating) OOM risk.

Important correction: `gpu_memory_utilization=0.5` caps vLLM's overall target executor budget; the KV cache must fit within that budget. The unused share is headroom for CUDA/runtime allocations, other permitted work, and measurement variability.

## First server-start attempt

The user attempted the approved `vllm serve` command on 2026-09-15. Engine startup failed before the server became available. The root traceback ended with:

```text
FileNotFoundError: [Errno 2] No such file or directory: 'ninja'
RuntimeError: Engine core initialization failed
```

Local verification found `ninja 1.13.2` installed at `.venv/bin/ninja`. The failed command invoked `.venv/bin/vllm` directly without activating the virtual environment, so FlashInfer's subprocess did not inherit `.venv/bin` in `PATH` and could not find `ninja` for its JIT sampling-kernel build.

- [verified][h] The immediate blocker is the virtual-environment `PATH`, not an absent `ninja` package, OOM, model-file checksum failure, or a proven GPU incompatibility.
- [planned][h] Retry after `source .venv/bin/activate`, which makes `ninja` available to the spawned subprocess. No dependency installation is required for this retry.

## Server startup evidence

The user retried after activating `.venv` and reported the following successful server-log evidence on 2026-09-15:

```text
Started server process [2172312]
Waiting for application startup.
Application startup complete.
```

The recorded launch configuration binds the API server to `127.0.0.1:8000` and masks physical GPU 4 with `CUDA_VISIBLE_DEVICES=4`; inside the server process it therefore appears as CUDA device 0. The server exposes `/v1/chat/completions`, `/v1/completions`, and related routes.

The reported `GET /` and `GET /favicon.ico` returned HTTP 404. This is expected because no root route was configured; it is not an engine failure.

- [verified from user-provided log][h] API server and engine startup completed.
- [unverified][h] No completion request has been sent; output correctness, first-token delivery, generation completion, cancellation/error handling, prefix-cache behavior, and all metrics remain untested.

## First streaming request attempt

The user supplied an SSE transcript for a streamed request asking `3+9等于几`, with `temperature=0`, `max_tokens=16`, and `stream=true`.

- [verified from user-provided transcript][h] The API emitted incremental `data:` chunks and ended with `data: [DONE]`; the stream transport and completion lifecycle therefore worked.
- [verified from user-provided transcript][h] The final chunk reported `finish_reason: "length"`. The generated content entered `<think>` and was truncated before answering `12`; this request did not pass answer-correctness validation.
- [verified][h] `results/s0/single_chat_stream.raw` exists in the project workspace (3961 bytes). Its full contents match the 16-token transcript: it is a reproducible truncation-scenario artifact, not an answer-correctness artifact. The request body is preserved in `results/s0/request_001.json`.
- [verified from local vLLM source][h] Request-level `chat_template_kwargs` can set `{"enable_thinking": false}` for Qwen3, avoiding the reasoning preamble for this short correctness check. The engine/server need not restart.

The user subsequently supplied the final SSE chunks from a different request (reported by the user as using a larger `max_tokens` bound). They include the content `结果是12。没错` and then:

```json
{"finish_reason":"length"}
```

followed by `data: [DONE]`.

- [verified from user-provided transcript][h] The response contains the correct arithmetic answer, `12`.
- [verified from user-provided transcript][h] The generation still ended because it reached its configured token cap. `data: [DONE]` marks the end of the SSE transport; it does not mean the model chose a natural stop.
- [unverified][h] The full request body, exact `max_tokens` value, prompt-to-response association, and a project-local artifact for this second request were not provided; do not label it a fully reproducible correctness baseline.

## Successful minimal streaming request

`results/s0/request_002.json` and `results/s0/single_chat_nothink.raw` form the first fully project-local functional request artifact.

```text
generated content: 3 + 9 等于 12。
finish_reason: stop
stream terminator: data: [DONE]
```

- [verified][h] The request used `chat_template_kwargs.enable_thinking=false`, `temperature=0`, `max_tokens=16`, and `stream=true`.
- [verified][h] This verifies one simple output-correctness path, streamed content chunks, a natural model stop, and SSE completion.
- [unverified][h] It does not measure TTFT, TPOT, throughput, cache hits, queueing, cancellation, or error handling. A server-side per-request log was not saved as an artifact.

## Current status

[verified][h] Downloaded on 2026-09-15 to `models/Qwen3-0.6B-c1899de/` with:

```bash
.venv/bin/hf download Qwen/Qwen3-0.6B \
  --revision c1899de289a04d12100db370d81485cdf75e47ca \
  --local-dir models/Qwen3-0.6B-c1899de \
  --max-workers 4
```

`model.safetensors` facts:

```text
size: 1503300328 bytes
sha256: f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b
```

The local SHA-256 matches the remote file's published SHA-256 for this revision.

[verified][h] The model was loaded sufficiently for the running server to produce a successful answer-correctness artifact: `results/s0/request_002.json` and `single_chat_nothink.raw`. Client timing, server request log, cache observation, and performance metrics do not yet exist.
