# Setup, isolation, and recovery

## Setup

1. Confirm production is healthy and `ollama ps` reports no loaded model.
2. Run `scripts/bootstrap-environment.sh` once. It refuses to overwrite an
   existing environment.
3. Run the synthetic validation script. It uses random token IDs only.
4. Keep Hugging Face weights in `/mnt/storage/tokensense/models/huggingface`.
5. Pin full model and dataset revisions in every experiment record.

The standalone NVIDIA CUDA toolkit is not required. PyTorch supplies the CUDA
runtime while the existing NVIDIA driver supplies kernel support.

## Starting a future training job

Run the preflight with the exact authorization phrase printed by the tool. A
failed preflight is a refusal, not a suggestion to terminate another service.
Ollama, Stable Diffusion, Wan, Blender, and other GPU users must never be
stopped automatically.

## Adapter lifecycle

Adapters begin in `experimental`. Evidence-backed review may move metadata to
`validated`. `production` requires the exact phrase `PROMOTE ADAPTER_ID`.
This only changes the inactive registry pointer; no current Oogway runtime
reads it. Runtime activation requires a separate implementation and review.

Rollback writes a registry pointer after `ROLL BACK TO ADAPTER_ID`. It does not
rewrite weights, merge adapters, or modify Ollama.

## Recovery

- Remove a broken experimental virtual environment only after recording its
  freeze and failure report; rerun bootstrap to create a fresh one.
- Never repair an experiment by modifying Oogway Core, Open WebUI, TokenSpace,
  Roundtable, Ollama, Stable Diffusion, or their environments.
- Preserve unsuccessful experiment directories and record the failure.
- A partially written metadata file ends in `.partial` and is not authoritative.
- Base checkpoints are immutable cached inputs. Adapters and checkpoints are
  separate and must remain linked by metadata hashes.

## Full removal

The infrastructure is deliberately detached. Removing the TokenSense virtual
environment and `/mnt/storage/tokensense` does not alter any production
service. Preserve reports and metadata before removal if they are still useful.
