#!/usr/bin/env python3
"""Experimental Gemma -> TFLite exporter for Android (MediaPipe/LiteRT path).

This script uses ai-edge-torch and only works for models that the stack currently
supports. For many LLM checkpoints this can fail due to unsupported ops.

Recommended in production:
- Prefer prevalidated LiteRT/MediaPipe model artifacts when available.
- Use GGUF + llama.cpp on Android as the primary reliable path.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Experimental Gemma to TFLite export")
    parser.add_argument(
        "--model-id",
        default="google/gemma-2-2b-it",
        help="HF model id (gated models require huggingface login)",
    )
    parser.add_argument(
        "--output",
        default="models/tflite/gemma2-2b-it/model.tflite",
        help="Output TFLite file path",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=128,
        help="Dummy input token length for conversion graph tracing",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "Missing dependencies. Install with: pip install -U torch transformers"
        ) from exc

    try:
        import ai_edge_torch
    except ImportError as exc:
        if "torch_xla" in str(exc):
            raise SystemExit(
                "ai-edge-torch requires torch_xla in this environment. On Windows this is often unsupported. "
                "Use GGUF + llama.cpp on Android, or run TFLite export in a supported Linux setup."
            ) from exc
        raise SystemExit(
            "ai-edge-torch is not installed. Install with: pip install ai-edge-torch"
        ) from exc

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading tokenizer: {args.model_id}")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id)

    print(f"Loading model: {args.model_id}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    model.eval()

    sample = tokenizer(
        "대한민국 교육 관련 법령을 간단히 설명해줘.",
        return_tensors="pt",
        max_length=args.max_length,
        truncation=True,
    )

    input_ids = sample["input_ids"]
    attention_mask = sample.get("attention_mask")

    if attention_mask is None:
        # Some tokenizers may not return attention masks in specific configurations.
        attention_mask = torch.ones_like(input_ids)

    print("Converting to TFLite (experimental)...")
    edge_model = ai_edge_torch.convert(model, (input_ids, attention_mask))
    edge_model.export(str(output))

    print("\n=== DONE ===")
    print(f"model_id={args.model_id}")
    print(f"tflite={output}")


if __name__ == "__main__":
    main()
