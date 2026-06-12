#!/usr/bin/env python3
"""Convert a HF CausalLM model to GGUF and quantize to 4-bit for Android.

Typical usage (Windows PowerShell):
python scripts/quantize_to_gguf.py --model-id Qwen/Qwen2.5-3B-Instruct --quant-type Q4_K_M

Notes:
- If the model is gated (Llama/Gemma), run `huggingface-cli login` first.
- Requires: git, cmake, a C++ compiler, and Python.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("[run]", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def safe_model_dir_name(model_id: str) -> str:
    return model_id.replace("/", "__").replace(":", "_")


def ensure_command_exists(command: str, hint: str) -> None:
    if shutil.which(command) is None:
        raise SystemExit(f"Missing command: {command}. {hint}")


def ensure_cpp_compiler() -> None:
    system = platform.system().lower()
    if system.startswith("win"):
        has_cl = shutil.which("cl") is not None
        has_clang = shutil.which("clang") is not None or shutil.which("clang++") is not None
        has_gpp = shutil.which("g++") is not None
        if not (has_cl or has_clang or has_gpp):
            raise SystemExit(
                "No C/C++ compiler found. Install Visual Studio Build Tools (Desktop development with C++) "
                "or LLVM/MinGW, then reopen terminal."
            )
    else:
        has_cc = shutil.which("cc") is not None or shutil.which("gcc") is not None
        has_cxx = shutil.which("c++") is not None or shutil.which("g++") is not None
        if not (has_cc and has_cxx):
            raise SystemExit("No C/C++ compiler found. Install build-essential/clang before running.")


def resolve_cmake_command() -> str:
    cmake_path = shutil.which("cmake")
    if cmake_path:
        return cmake_path

    try:
        import cmake  # type: ignore
    except ImportError as exc:
        raise SystemExit("Missing CMake. Install system CMake or `pip install cmake`.") from exc

    exe_name = "cmake.exe" if platform.system().lower().startswith("win") else "cmake"
    candidate = Path(cmake.CMAKE_BIN_DIR) / exe_name
    if not candidate.exists():
        raise SystemExit("Could not resolve cmake executable path from python package.")
    return str(candidate)


def ensure_llama_cpp(llama_cpp_dir: Path) -> None:
    if llama_cpp_dir.exists() and (llama_cpp_dir / "convert_hf_to_gguf.py").exists():
        return

    llama_cpp_dir.parent.mkdir(parents=True, exist_ok=True)
    run([
        "git",
        "clone",
        "https://github.com/ggml-org/llama.cpp.git",
        str(llama_cpp_dir),
    ])


def build_llama_cpp(llama_cpp_dir: Path, cmake_cmd: str) -> tuple[Path, Path]:
    build_dir = llama_cpp_dir / "build"

    cmake_config_cmd = [cmake_cmd, "-S", ".", "-B", str(build_dir), "-DLLAMA_CURL=ON"]
    run(cmake_config_cmd, cwd=llama_cpp_dir)

    cmake_build_cmd = [cmake_cmd, "--build", str(build_dir), "--config", "Release", "-j"]
    run(cmake_build_cmd, cwd=llama_cpp_dir)

    exe_suffix = ".exe" if platform.system().lower().startswith("win") else ""

    quant_candidates = [
        build_dir / "bin" / f"llama-quantize{exe_suffix}",
        build_dir / "bin" / "Release" / f"llama-quantize{exe_suffix}",
        build_dir / "bin" / f"quantize{exe_suffix}",
        build_dir / "bin" / "Release" / f"quantize{exe_suffix}",
    ]

    quantize_bin = next((p for p in quant_candidates if p.exists()), None)
    if quantize_bin is None:
        raise SystemExit(
            "Could not find llama quantize binary. Build may have failed or binary path changed."
        )

    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    if not convert_script.exists():
        raise SystemExit("convert_hf_to_gguf.py not found in llama.cpp directory")

    return convert_script, quantize_bin


def download_hf_model(model_id: str, local_dir: Path, python_bin: str) -> None:
    if local_dir.exists() and any(local_dir.iterdir()):
        print(f"[skip] model already exists: {local_dir}")
        return

    local_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        python_bin,
        "-m",
        "huggingface_hub.commands.huggingface_cli",
        "download",
        model_id,
        "--local-dir",
        str(local_dir),
        "--local-dir-use-symlinks",
        "False",
    ]

    if os.getenv("HF_TOKEN"):
        cmd.extend(["--token", os.environ["HF_TOKEN"]])

    run(cmd)


def convert_and_quantize(
    python_bin: str,
    convert_script: Path,
    quantize_bin: Path,
    model_dir: Path,
    out_dir: Path,
    quant_type: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    f16_gguf = out_dir / "model-f16.gguf"
    q4_gguf = out_dir / f"model-{quant_type.lower()}.gguf"

    if not f16_gguf.exists():
        run(
            [
                python_bin,
                str(convert_script),
                str(model_dir),
                "--outtype",
                "f16",
                "--outfile",
                str(f16_gguf),
            ]
        )
    else:
        print(f"[skip] exists: {f16_gguf}")

    if not q4_gguf.exists():
        run(
            [
                str(quantize_bin),
                str(f16_gguf),
                str(q4_gguf),
                quant_type,
            ]
        )
    else:
        print(f"[skip] exists: {q4_gguf}")

    return f16_gguf, q4_gguf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HF -> GGUF -> 4bit quantization pipeline")
    parser.add_argument(
        "--model-id",
        default="Qwen/Qwen2.5-3B-Instruct",
        help="Hugging Face model ID (example: meta-llama/Llama-3.2-3B-Instruct)",
    )
    parser.add_argument(
        "--quant-type",
        default="Q4_K_M",
        help="GGUF quantization type (default: Q4_K_M)",
    )
    parser.add_argument(
        "--models-root",
        default="models",
        help="Root directory for model artifacts (default: models)",
    )
    parser.add_argument(
        "--llama-cpp-dir",
        default="vendor/llama.cpp",
        help="Local llama.cpp directory (default: vendor/llama.cpp)",
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used to run converter scripts",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    ensure_command_exists("git", "Install Git and make sure it is in PATH.")
    ensure_cpp_compiler()
    cmake_cmd = resolve_cmake_command()

    root = Path.cwd()
    models_root = (root / args.models_root).resolve()
    llama_cpp_dir = (root / args.llama_cpp_dir).resolve()

    model_name = safe_model_dir_name(args.model_id)
    hf_dir = models_root / "hf" / model_name
    gguf_dir = models_root / "gguf" / model_name

    ensure_llama_cpp(llama_cpp_dir)
    convert_script, quantize_bin = build_llama_cpp(llama_cpp_dir, cmake_cmd=cmake_cmd)

    download_hf_model(args.model_id, hf_dir, python_bin=args.python_bin)
    f16_gguf, q4_gguf = convert_and_quantize(
        python_bin=args.python_bin,
        convert_script=convert_script,
        quantize_bin=quantize_bin,
        model_dir=hf_dir,
        out_dir=gguf_dir,
        quant_type=args.quant_type,
    )

    print("\n=== DONE ===")
    print(f"model_id={args.model_id}")
    print(f"hf_dir={hf_dir}")
    print(f"f16_gguf={f16_gguf}")
    print(f"quantized_gguf={q4_gguf}")


if __name__ == "__main__":
    main()
