# S0 Environment Evidence

Part of the [S0 documentation set](README.md).

Captured: 2026-09-14T17:01:42+08:00 from the current terminal. This is a point-in-time, read-only inventory; it neither establishes that a GPU is reserved for this project nor proves any inference framework is compatible.

## Commands run

```bash
hostname
date -Is
nvidia-smi
nvidia-smi topo -m
python --version
python - <<'PY'
try:
    import torch
    print('torch:', torch.__version__)
    print('torch.cuda.is_available:', torch.cuda.is_available())
    print('torch.version.cuda:', torch.version.cuda)
    print('torch.cuda.device_count:', torch.cuda.device_count())
except ModuleNotFoundError:
    print('torch: not installed in this Python environment')
PY
```

## Observed output

```text
hostname: amax
Python: 3.13.13
NVIDIA-SMI: 580.65.06
Driver Version: 580.65.06
Reported CUDA Version: 13.0
GPU count: 8
GPU model: NVIDIA GeForce RTX 5090
Per-GPU reported memory: 32607 MiB
PyTorch import with `python`: ModuleNotFoundError
```

`nvidia-smi` snapshot at capture time:

| GPU | PCI bus ID | Memory used / total | GPU utilization | Observed state |
|---:|---|---:|---:|---|
| 0 | 16:00.0 | 5251 / 32607 MiB | 59% | active Python process present |
| 1 | 27:00.0 | 6839 / 32607 MiB | 66% | active Python process present |
| 2 | 38:00.0 | 12685 / 32607 MiB | 91% | active Python process present |
| 3 | 5A:00.0 | 15 / 32607 MiB | 0% | display/Xorg only in snapshot |
| 4 | 98:00.0 | 15 / 32607 MiB | 0% | display/Xorg only in snapshot |
| 5 | A8:00.0 | 15 / 32607 MiB | 0% | display/Xorg only in snapshot |
| 6 | B8:00.0 | 14439 / 32607 MiB | 83% | active Python process present |
| 7 | D8:00.0 | 13505 / 32607 MiB | 14% | active Python processes present |

Topology excerpt: GPUs 0–2 share NUMA affinity 0; GPU 3 uses NUMA 1; GPUs 4–6 share NUMA affinity 2; GPU 7 uses NUMA 3. The report contains `NODE`/`SYS` interconnect paths and no `NV#` link labels. This will matter only if the project later uses multiple replicas; S0 does not infer performance from it.

## Status and limits

- [verified][h] The terminal is on host `amax` with eight visible RTX 5090 GPUs.
- [verified][h] The default `python` interpreter is 3.13.13 and has no importable PyTorch package.
- [verified][h] GPUs 0, 1, 2, 6, and 7 were occupied at the capture instant; GPUs 3, 4, and 5 had no compute process listed.
- [unverified][h] Whether GPUs 3–5 are allocated/approved for this project remains unknown; low utilization is not authorization.
- [unverified][h] No framework, model, dtype, package environment, or inference command has been selected or tested.

## Project virtual environment

Created 2026-09-14 with the user-selected `uv` workflow:

```bash
uv --version
uv venv .venv
.venv/bin/python --version
```

Observed output:

```text
uv 0.11.14 (x86_64-unknown-linux-gnu)
Using CPython 3.11.15
Creating virtual environment at: .venv
Python 3.11.15
executable: /nfsdata/nHome/chenjunkun/project/infra/.venv/bin/python
torch: not installed
```

- [verified][h] `.venv` exists and is isolated at the project root.
- [verified][h] `uv` selected CPython 3.11.15 for this environment; it did not use the shell's `python` 3.13.13.
- [verified][h] PyTorch is not installed in `.venv`.
- [unverified][h] This Python version and empty environment do not establish compatibility with any serving framework or model.

## Deferred vLLM installation attempt

After the user confirmed the vLLM runtime / nano-vllm reading split, the following installation was started on 2026-09-14:

```bash
uv pip install --python .venv/bin/python 'vllm==0.29.0' --torch-backend=cu130
```

The resolver selected 195 packages and began downloading the vLLM, PyTorch, and CUDA wheels. It was stopped by the mentor with `SIGINT` (exit code 130) after a prolonged download phase because the user had confirmed the architecture choice, not explicitly authorized a multi-GiB dependency download. At cancellation, `.venv` was still 54 KiB and did not contain installed vLLM or PyTorch packages. The existing uv download cache was deliberately retained for a future, explicitly authorized retry.

- [verified][h] vLLM 0.29.0 was the current upstream release selected for the prospective pinned installation; it was not installed when this first attempt was cancelled.
- [verified][h] The attempted `--torch-backend=cu130` selection did not run a CUDA self-check and did not execute any GPU work.

## Installed vLLM environment

The user reported on 2026-09-14 that a separate coding agent completed the installation. Local read-only verification found:

```text
Python 3.11.15
vllm=0.29.0
torch=2.13.0+cu130
uv pip check: Checked 195 packages; all installed packages are compatible
```

Package locations are under `.venv/lib/python3.11/site-packages`. `.venv/bin/pip` is absent because this uv-created environment was not seeded with pip; `uv pip check --python .venv/bin/python` is the recorded dependency consistency check.

- [verified][h] vLLM 0.29.0 and CUDA 13.0 PyTorch 2.13.0 are installed in `.venv`.
- [verified][h] Dependency metadata is internally consistent at the time of check.
- [unverified][h] Importing/launching vLLM and CUDA operation on an authorized RTX 5090 have not yet been tested.

## CUDA runtime self-check

The user stated that any currently idle GPU may be used. A fresh `nvidia-smi` snapshot showed GPUs 2, 3, and 4 at 0% utilization and 15 MiB display-memory use; GPU 3 was selected. Immediately before the test, the script checked that GPU 3 had no listed compute process.

Executed 2026-09-14:

```bash
CUDA_VISIBLE_DEVICES=3 .venv/bin/python -
```

The Python self-check imported PyTorch, required one visible CUDA device, reported its identity and compute capability, allocated a one-element CUDA tensor, added one, then synchronized.

```text
torch: 2.13.0+cu130
torch.version.cuda: 13.0
cuda_available: True
visible_device_count: 1
device_name: NVIDIA GeForce RTX 5090
compute_capability: (12, 0)
scalar_kernel_result: 1.0
```

- [verified][h] With physical GPU 3 selected at the time of test, PyTorch CUDA initialization and a synchronized scalar kernel succeeded on an RTX 5090.
- [verified][h] Within this process, `CUDA_VISIBLE_DEVICES=3` made the selected physical GPU appear as visible device 0.
- [unverified][h] vLLM import, vLLM engine initialization, model download/load, generation, prefix caching, and HTTP serving remain untested.

## vLLM import self-check

Executed after the CUDA self-check, with the same device mask but without creating an engine or loading a model:

```bash
CUDA_VISIBLE_DEVICES=3 .venv/bin/python -
```

```text
torch: 2.13.0+cu130
vllm: 0.29.0
vllm_import: success
```

- [verified][h] vLLM 0.29.0 imports successfully with the selected CUDA environment.
- [unverified][h] Package import does not validate vLLM engine startup, supported attention kernels, model loading, generation, prefix caching, streaming, or serving.

## vLLM installation completed (2026-09-14, authorized retry)

The user explicitly authorized the multi-GiB download. The same command was re-run and completed with exit code 0:

```bash
uv pip install --python .venv/bin/python 'vllm==0.29.0' --torch-backend=cu130
```

The uv cache resumed from the retained partial download; the run took roughly 50 minutes and grew `.venv` from 54 KiB to 7.6 GiB.

Installed versions, read back from `.venv` metadata:

```text
vllm 0.29.0
torch 2.13.0+cu130
triton 3.7.1
transformers 5.17.0
xformers MISSING (not pulled in by vLLM 0.29.0)
```

CUDA self-check via `.venv/bin/python`:

```text
torch: 2.13.0+cu130
torch.version.cuda: 13.0
cuda.is_available: True
device_count: 8
device 0: NVIDIA GeForce RTX 5090
capability: (12, 0)
```

`import vllm` and `from vllm import LLM, SamplingParams` both succeed.

- [verified][h] vLLM 0.29.0 and PyTorch 2.13.0+cu130 are installed in `.venv` and importable.
- [verified][h] PyTorch detects 8 RTX 5090 GPUs over CUDA 13.0; the driver's reported CUDA version matches the wheel's `cu130` build tag.
- [verified][h] The installed torch build targets compute capability 12.0, matching the RTX 5090 (sm_120) — the earlier "no framework selected or tested" gap is closed at the import/toolkit level.
- [unverified][h] No model has been loaded and no inference or serving request has been run. Import success and `cuda.is_available` do not prove that a kernel will execute correctly on sm_120, only that the toolkit and device enumeration work.
- [unverified][m] No GPU was reserved or allocated for this project; the CUDA check enumerated devices already visible to the host, it did not claim any of them.
- [unverified][m] `vllm==0.29.0` is pinned, but its transitive dependencies are resolved freely. A reproducible rebuild would need a lockfile (`uv pip compile` / `uv lock`); none exists yet.

## Required user reproduction

Run the following read-only command in the environment you intend to use and return its output plus a one- or two-sentence explanation of what it proves and what it does not prove:

```bash
nvidia-smi
```

Minimum expected distinction: the command reports a point-in-time view of visible GPUs and processes; it does not itself prove that an idle-looking GPU is reserved or that a serving framework will run.

## User reproduction and interpretation

Completed in the project conversation on 2026-09-14. The user reported seeing eight RTX 5090 GPUs and identified GPU indices 3–5 as having no listed compute task, then correctly explained that this neither assigns those GPUs to the project nor turns the observed process list into resource-allocation evidence. The user also noted the non-compute display-memory use. The raw repeated command output was not retained because the user chose not to paste it; the earlier agent-collected snapshot above remains the only preserved raw environment evidence.
