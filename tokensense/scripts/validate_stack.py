#!/usr/bin/env python3
"""Bounded synthetic CUDA, bitsandbytes, LoRA, checkpoint, and inference test."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import bitsandbytes as bnb
import torch
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import Qwen3Config, Qwen3ForCausalLM


PRIVATE_ROOT = Path(os.environ.get("TOKENSENSE_PRIVATE_ROOT", "/mnt/storage/tokensense"))
REPORT_ROOT = PRIVATE_ROOT / "reports"
EXPERIMENT_ROOT = PRIVATE_ROOT / "experiments" / "synthetic-smoke-v1"
ADAPTER_ROOT = PRIVATE_ROOT / "adapters" / "experimental" / "synthetic-qwen3-lora-v1"


def package_versions() -> dict[str, str]:
    names = [
        "torch", "transformers", "peft", "accelerate", "bitsandbytes", "trl",
        "datasets", "safetensors", "tokenizers", "sentencepiece",
    ]
    return {name: importlib.metadata.version(name) for name in names}


def digest_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def tiny_config() -> Qwen3Config:
    return Qwen3Config(
        vocab_size=128,
        hidden_size=64,
        intermediate_size=128,
        num_hidden_layers=2,
        num_attention_heads=4,
        num_key_value_heads=2,
        head_dim=16,
        max_position_embeddings=128,
        tie_word_embeddings=False,
    )


def main() -> int:
    started = time.monotonic()
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable to PyTorch")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    EXPERIMENT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if ADAPTER_ROOT.exists():
        shutil.rmtree(ADAPTER_ROOT)
    torch.manual_seed(7311962)
    torch.cuda.manual_seed_all(7311962)
    torch.cuda.reset_peak_memory_stats()
    device = torch.device("cuda:0")

    # Exercise a real NF4 quantized matrix operation independently of the model.
    quantized = bnb.nn.Linear4bit(
        32, 16, bias=False, compute_dtype=torch.float16, quant_type="nf4",
        compress_statistics=True,
    ).to(device)
    quantized_output = quantized(torch.randn(2, 32, device=device, dtype=torch.float16))
    if quantized_output.shape != (2, 16):
        raise RuntimeError("bitsandbytes NF4 operation returned an unexpected shape")
    del quantized, quantized_output
    torch.cuda.empty_cache()

    synthetic_manifest = {
        "manifest_id": "synthetic-random-token-ids-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approval_status": "approved",
        "sources": [{"type": "deterministic-generator", "seed": 7311962}],
        "records_sha256": hashlib.sha256(b"torch.randint seed=7311962 shape=2x24 vocab=128").hexdigest(),
        "record_count": 2,
        "notes": "No natural language, transcript, customer, or TokenSpace data was used.",
    }
    synthetic_manifest_path = EXPERIMENT_ROOT / "synthetic-data-manifest.json"
    synthetic_manifest_path.write_text(json.dumps(synthetic_manifest, indent=2) + "\n", encoding="utf-8")
    os.chmod(synthetic_manifest_path, 0o600)
    synthetic_manifest_digest = hashlib.sha256(synthetic_manifest_path.read_bytes()).hexdigest()

    config = tiny_config()
    base = Qwen3ForCausalLM(config).to(device)
    adapter_config = LoraConfig(
        task_type="CAUSAL_LM",
        r=4,
        lora_alpha=8,
        lora_dropout=0.0,
        bias="none",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    )
    model = get_peft_model(base, adapter_config)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=1e-3)
    input_ids = torch.randint(0, config.vocab_size, (2, 24), device=device)
    labels = input_ids.clone()
    model.train()
    loss = model(input_ids=input_ids, labels=labels).loss
    loss.backward()
    optimizer.step()
    optimizer.zero_grad(set_to_none=True)
    loss_value = float(loss.detach().cpu())
    model.save_pretrained(ADAPTER_ROOT, safe_serialization=True)
    adapter_digest = digest_tree(ADAPTER_ROOT)
    del model, base, optimizer, trainable
    torch.cuda.empty_cache()

    torch.manual_seed(7311962)
    reloaded_base = Qwen3ForCausalLM(config).to(device)
    reloaded = PeftModel.from_pretrained(reloaded_base, ADAPTER_ROOT).to(device)
    reloaded.eval()
    with torch.inference_mode():
        logits = reloaded(input_ids=input_ids[:1]).logits
    if logits.shape != (1, 24, config.vocab_size):
        raise RuntimeError("reloaded adapter inference returned an unexpected shape")

    versions = package_versions()
    completed_at = datetime.now(timezone.utc).isoformat()
    adapter_metadata = {
        "schema_version": 1,
        "adapter_id": "synthetic-qwen3-lora-v1",
        "experiment_id": "synthetic-smoke-v1",
        "status": "experimental",
        "created_at": completed_at,
        "base_model": {
            "identifier": "synthetic-miniature-Qwen3ForCausalLM",
            "revision": "deterministic-config-v1",
            "sha256": None,
        },
        "framework": versions,
        "adapter": {
            "method": "lora",
            "configuration": {
                "r": 4, "lora_alpha": 8, "lora_dropout": 0.0,
                "target_modules": ["q_proj", "k_proj", "v_proj", "o_proj"],
            },
        },
        "training_data": {
            "manifest": str(synthetic_manifest_path),
            "sha256": synthetic_manifest_digest,
        },
        "training": {"steps": 1, "seed": 7311962, "loss": loss_value},
        "checkpoints": [{"path": str(ADAPTER_ROOT), "sha256": adapter_digest}],
        "evaluations": [{"kind": "load-and-inference-smoke-test", "passed": True}],
        "status_history": [{"status": "experimental", "at": completed_at}],
    }
    metadata_path = ADAPTER_ROOT / "metadata.json"
    metadata_path.write_text(json.dumps(adapter_metadata, indent=2) + "\n", encoding="utf-8")
    os.chmod(metadata_path, 0o600)

    report = {
        "schema_version": 1,
        "status": "passed",
        "synthetic_data_only": True,
        "completed_at": completed_at,
        "duration_seconds": round(time.monotonic() - started, 3),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": versions,
        "cuda": {
            "torch_build": torch.version.cuda,
            "device": torch.cuda.get_device_name(0),
            "compute_capability": list(torch.cuda.get_device_capability(0)),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        },
        "test": {
            "architecture": "miniature Qwen3ForCausalLM",
            "parameters": sum(parameter.numel() for parameter in reloaded.parameters()),
            "training_steps": 1,
            "loss": loss_value,
            "adapter_path": str(ADAPTER_ROOT),
            "adapter_sha256": adapter_digest,
            "adapter_metadata": str(metadata_path),
            "training_data_manifest_sha256": synthetic_manifest_digest,
            "checkpoint_reloaded": True,
            "adapter_inference_completed": True,
            "bitsandbytes_nf4_operation": True,
        },
        "claims": [
            "The local training machinery functions on synthetic data.",
            "This does not validate TokenSense behavior or learning quality.",
        ],
    }
    experiment_record = {
        "experiment_id": "synthetic-smoke-v1",
        "status": "complete",
        "baseline": {"architecture": "miniature Qwen3ForCausalLM", "adapter": None},
        "candidate": {"adapter_id": "synthetic-qwen3-lora-v1"},
        "resource_measurements": {
            "peak_vram_bytes": report["cuda"]["peak_allocated_bytes"],
            "duration_seconds": report["duration_seconds"],
        },
        "failures": [],
        "reproducibility": {
            "random_seed": 7311962,
            "synthetic_data_manifest_sha256": synthetic_manifest_digest,
            "framework": versions,
        },
        "limitations": ["Infrastructure smoke test only; no behavioral evaluation was performed."],
    }
    experiment_path = EXPERIMENT_ROOT / "experiment.json"
    experiment_path.write_text(json.dumps(experiment_record, indent=2) + "\n", encoding="utf-8")
    os.chmod(experiment_path, 0o600)
    target = REPORT_ROOT / "synthetic-stack-validation.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
