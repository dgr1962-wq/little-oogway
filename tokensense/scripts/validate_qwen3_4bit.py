#!/usr/bin/env python3
"""Optional pinned Qwen3-8B 4-bit load test; it never trains or changes Ollama."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

from preflight import AUTHORIZATION, inspect


MODEL_ID = "Qwen/Qwen3-8B"
REVISION = "b968826d9c46dd6066d109eabc6255188de91218"
CACHE = Path("/mnt/storage/tokensense/models/huggingface")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--authorization", default="")
    args = parser.parse_args()
    if not args.download:
        print("Refusing: pass --download to acknowledge the large upstream checkpoint download.", file=sys.stderr)
        return 2
    if args.authorization != AUTHORIZATION:
        print(f"Refusing: use --authorization '{AUTHORIZATION}'", file=sys.stderr)
        return 2
    preflight = inspect()
    if not preflight["safe_to_start"]:
        print(json.dumps(preflight, indent=2), file=sys.stderr)
        return 2
    os.environ["HF_HOME"] = str(CACHE)
    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
    )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=REVISION, cache_dir=CACHE)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        revision=REVISION,
        cache_dir=CACHE,
        quantization_config=quantization,
        device_map={"": 0},
        low_cpu_mem_usage=True,
    )
    inputs = tokenizer("Synthetic infrastructure load test.", return_tensors="pt").to("cuda")
    with torch.inference_mode():
        output = model.generate(**inputs, max_new_tokens=2, do_sample=False)
    report = {
        "model": MODEL_ID,
        "revision": REVISION,
        "loaded_in_4bit": True,
        "inference_tokens": int(output.shape[-1] - inputs["input_ids"].shape[-1]),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "production_ollama_modified": False,
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
