#!/usr/bin/env python3
"""Local test script — generate designs via GeminiClient using PRODUCTION code paths."""

import asyncio
import os
import sys
import shutil
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.gemini_client import GeminiClient, DesignBrief
from app.state.flow import FlowEngine


OUTPUT_ROOT = Path("app/static/generated/test_outputs")

# We only need _kv_to_precise_modifications and _category_key from FlowEngine.
# Create a minimal instance without Redis/WhatsApp dependencies.
_flow = FlowEngine.__new__(FlowEngine)


def production_modifications(category: str, field: str, value: str) -> dict:
    """
    Run the modification through the SAME _kv_to_precise_modifications
    that production uses, so test prompts match real user experience.
    """
    raw_kv = {field: value}
    return _flow._kv_to_precise_modifications(category, raw_kv)


async def generate_base(category: str, color: str, fabric: str = "crepe",
                        occasion: str = "Casual", notes: str = "",
                        pattern_path: str = None) -> str:
    client = GeminiClient()
    brief = DesignBrief(
        occasion=occasion, budget="", category=category,
        fabric=fabric, color=color,
        notes=notes or "premium, stylish, modern", size="M",
    )

    pattern_bytes = None
    if pattern_path:
        pattern_bytes = Path(pattern_path).read_bytes()

    rel_path = await client.generate_image_only(
        wa_id="test_local", brief=brief, pattern_image_bytes=pattern_bytes,
    )
    print(f"Generated: {rel_path}")

    src = Path("app" + rel_path) if rel_path.startswith("/static") else Path(rel_path)
    cat_folder = OUTPUT_ROOT / category.lower().replace(" ", "_")
    cat_folder.mkdir(parents=True, exist_ok=True)

    suffix = "_printed" if pattern_path else ""
    dest = cat_folder / f"{color.lower().replace(' ', '_')}_{category.lower()}{suffix}.png"
    shutil.copy2(src, dest)
    print(f"Saved to: {dest}")
    return rel_path  # return the rel_path for chaining modifications


async def generate_modified(category: str, color: str, base_rel_path: str,
                            field: str, value: str,
                            fabric: str = "crepe", occasion: str = "Casual",
                            notes: str = "", dest_name: str = None) -> str:
    """
    Modify using the PRODUCTION code path:
    1. field + value go through _kv_to_precise_modifications
    2. Result is passed to GeminiClient.generate_modified_image
    """
    client = GeminiClient()
    brief = DesignBrief(
        occasion=occasion, budget="", category=category,
        fabric=fabric, color=color,
        notes=notes or "premium, stylish, modern", size="M",
    )

    # Use production modification logic
    modifications = production_modifications(category, field, value)
    print(f"Production prompt: {modifications}")

    rel_path = await client.generate_modified_image(
        wa_id="test_local",
        base_image_rel_path=base_rel_path,
        brief=brief,
        modifications=modifications,
    )
    print(f"Generated: {rel_path}")

    src = Path("app" + rel_path) if rel_path.startswith("/static") else Path(rel_path)
    cat_folder = OUTPUT_ROOT / category.lower().replace(" ", "_")
    cat_folder.mkdir(parents=True, exist_ok=True)

    fname = dest_name or f"{color.lower().replace(' ', '_')}_{category.lower()}_{field}_{value}.png"
    dest = cat_folder / fname
    shutil.copy2(src, dest)
    print(f"Saved to: {dest}")
    return rel_path  # return for chaining


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="top")
    parser.add_argument("--color", default="pink")
    parser.add_argument("--fabric", default="crepe")
    parser.add_argument("--occasion", default="Casual")
    parser.add_argument("--pattern", default=None, help="Path to pattern image")
    args = parser.parse_args()

    asyncio.run(generate_base(args.category, args.color, args.fabric, args.occasion,
                              pattern_path=args.pattern))
