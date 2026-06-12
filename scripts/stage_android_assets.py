#!/usr/bin/env python3
"""Stage model/database assets for Android edge app.

Default target is llama.cpp Android sample app in vendor directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def copy_file(src: Path, dst: Path) -> dict[str, object]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return {
        "source": str(src).replace("\\", "/"),
        "target": str(dst).replace("\\", "/"),
        "bytes": dst.stat().st_size,
        "sha256": sha256_of(dst),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage GGUF + school DB into Android app assets")
    parser.add_argument(
        "--model",
        required=True,
        help="Path to quantized GGUF model (example: models/gguf/.../model-q4_k_m.gguf)",
    )
    parser.add_argument(
        "--db",
        default="build/school_law.db",
        help="Path to SQLite DB (default: build/school_law.db)",
    )
    parser.add_argument(
        "--app-dir",
        default="vendor/llama.cpp/examples/llama.android/app",
        help="Android app module directory (default: vendor/llama.cpp/examples/llama.android/app)",
    )
    parser.add_argument(
        "--model-name",
        default="school-q4.gguf",
        help="Target model filename in assets/models (default: school-q4.gguf)",
    )
    parser.add_argument(
        "--db-name",
        default="school_law.db",
        help="Target db filename in assets/db (default: school_law.db)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    root = Path.cwd()
    model_src = (root / args.model).resolve()
    db_src = (root / args.db).resolve()
    app_dir = (root / args.app_dir).resolve()

    if not model_src.exists() or not model_src.is_file():
        raise SystemExit(f"Model file not found: {model_src}")
    if not db_src.exists() or not db_src.is_file():
        raise SystemExit(f"DB file not found: {db_src}")
    if not app_dir.exists() or not app_dir.is_dir():
        raise SystemExit(f"App dir not found: {app_dir}")

    assets_dir = app_dir / "src" / "main" / "assets"
    model_dst = assets_dir / "models" / args.model_name
    db_dst = assets_dir / "db" / args.db_name

    model_info = copy_file(model_src, model_dst)
    db_info = copy_file(db_src, db_dst)

    manifest = {
        "model": model_info,
        "database": db_info,
    }
    manifest_path = assets_dir / "edge_assets_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("=== ASSET STAGING COMPLETE ===")
    print(f"app_dir={app_dir}")
    print(f"assets_dir={assets_dir}")
    print(f"model={model_dst}")
    print(f"db={db_dst}")
    print(f"manifest={manifest_path}")


if __name__ == "__main__":
    main()
