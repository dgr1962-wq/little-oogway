# TokenSense research infrastructure

This directory contains infrastructure for synthetic LoRA/QLoRA experiments.
It does **not** implement TokenSense, alter TokenSpace, or select an adapter for
Little Oogway.

## Boundaries

- Production Oogway environments and services are never modified or stopped.
- Private datasets, model weights, checkpoints, and reports live below
  `/mnt/storage/tokensense`, not in this repository or a web-served directory.
- Validation uses generated token IDs and a miniature Qwen3 configuration.
- Adapter promotion changes registry metadata only. Runtime integration is a
  separate, reviewed project.
- No adapter becomes production without an exact operator confirmation.

## Layout

- `configuration/` reproducible workspace and evaluation configuration
- `schemas/` adapter, memory-proposal, and experiment metadata contracts
- `scripts/` bootstrap, validation, registry, evaluation, and preflight tools
- `tests/` infrastructure tests that require no model download
- `datasets/`, `checkpoints/`, `adapters/`, `experiments/`, and `reports/` are
  repository placeholders; their private counterparts are on the storage disk

## Environment choice

The baseline deliberately follows the CUDA stack already proven on this RTX
3060: PyTorch 2.6.0 CUDA 12.4, Transformers 4.56.2, PEFT 0.17.1,
Accelerate 1.10.1, bitsandbytes 0.47.0, TRL 0.23.1, and Datasets 4.1.1.
TRL 0.23.1 declares Transformers 4.56.1 or newer, so these pins are mutually
compatible. Unsloth is kept out of the baseline because its current release
requires newer PEFT and other dependency changes; it should receive a separate
optional environment after the reference path is stable.

## Commands

```bash
./scripts/bootstrap-environment.sh
/home/darren/venvs/tokensense-qlora/bin/python scripts/preflight.py
/home/darren/venvs/tokensense-qlora/bin/python scripts/validate_stack.py
/home/darren/venvs/tokensense-qlora/bin/python -m unittest discover -s tests -v
```

The optional Qwen3-8B 4-bit loader is deliberately separate because it may
download roughly 16 GB of upstream weights and use most available VRAM:

```bash
/home/darren/venvs/tokensense-qlora/bin/python scripts/validate_qwen3_4bit.py --download
```

It checks that no Ollama model or competing compute process is active and
refuses to run when the configured free-VRAM floor is not met.
