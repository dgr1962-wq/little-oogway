# TokenSense infrastructure installation report — 2026-10-14

## Installed

- Dedicated Python 3.12 virtual environment:
  `/home/darren/venvs/tokensense-qlora`
- PyTorch 2.6.0+cu124, Transformers 4.56.2, PEFT 0.17.1,
  Accelerate 1.10.1, bitsandbytes 0.47.0, TRL 0.23.1,
  Datasets 4.1.1, Safetensors 0.6.2, Tokenizers 0.22.1, and
  SentencePiece 0.2.1.
- Private workspace: `/mnt/storage/tokensense`.
- Immutable upstream training reference: `Qwen/Qwen3-8B` revision
  `b968826d9c46dd6066d109eabc6255188de91218`.
- Resolved environment freeze SHA-256:
  `f6fa2d27799fed5f8a94778191d22d58b65d5c361135ccd07fd4d08256ae8fd0`.
- Direct dependency lock SHA-256:
  `0fa8fa6f057dfd9dac8951c12effcf00fee8ab2f12dd324da57e06167e39c7cd`.

The existing NVIDIA driver, system CUDA configuration, old
`/home/darren/Documents/ougway_venv`, and all production environments were
preserved.

## Tested

- PyTorch detected the RTX 3060 through CUDA 12.4 with compute capability 8.6.
- bitsandbytes completed an NF4 quantized matrix operation.
- A 94,080-parameter miniature `Qwen3ForCausalLM` received one synthetic LoRA
  training step.
- The adapter saved as Safetensors, reloaded into a deterministic fresh base,
  and completed inference.
- Duration: 0.564 seconds.
- Peak allocated VRAM: 17,905,152 bytes; peak reserved: 23,068,672 bytes.
- Synthetic loss was recorded only as a machinery diagnostic; it is not a
  learning-quality result.
- The adapter remains `experimental`; unconfirmed production promotion was
  explicitly refused.
- Upstream configuration-only retrieval verified a 36-layer Qwen3 architecture
  at the pinned revision without downloading model weights.
- Six typed registry contracts, controlled evaluation planning, Atlas snapshot
  classification, permission gating, and contradiction non-resolution passed
  their infrastructure tests.
- Existing Atlas export hashes were recorded and no upload was performed.
- `pip check` reported no broken requirements.

## Scaffolded but inactive

- Memory relationship, hypothesis, contradiction, training-candidate, adapter,
  and experiment registries.
- Proposed-memory and training-data manifests.
- Versioned experimental/validated/production/archived adapter layout.
- Exact-confirmation promotion and rollback metadata procedures.
- Baseline-versus-adapter evaluation plan generation with identical prompts,
  context, parameters, and empty result fields.
- Private, immutable Atlas snapshots for approved-memory embeddings and
  experimental-response embeddings.
- A GPU preflight that checks VRAM, Ollama residency, GPU compute processes,
  storage, and exact authorization without stopping other workloads.
- An optional pinned Qwen3-8B four-bit load test with an explicit large-download
  acknowledgement. It has not been invoked.

## Deliberately unimplemented

- TokenSense reasoning behavior.
- Production or private-data training.
- Automatic memory creation or rewriting.
- Autonomous training or scheduling.
- Automatic adapter validation or promotion.
- Oogway Core or Ollama adapter loading.
- Merging, GGUF conversion, quantization, or replacement of production
  `qwen3:8b`.
- Production Atlas uploads.
- A production evaluation corpus or any claim that TokenSense has learned.
- Unsloth in the reference environment. Its current dependency lane was
  evaluated and deferred to a separate optional environment.

## Production impact

No Oogway Core, TokenSpace, Roundtable, Open WebUI, Ollama, Stable Diffusion,
public website, legacy database, or production memory configuration was
modified. No production service was stopped.
