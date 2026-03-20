#!/usr/bin/env python3
"""Local test script — generate designs via GeminiClient using PRODUCTION code paths.

This script replicates the EXACT same logic as production flow.py:
- _kv_to_precise_modifications() for modification prompts
- pattern_image_bytes + pattern_mode="preserve" for printed garments
- Print preservation prompt text identical to production line 1851-1854
"""

import asyncio
import json
import os
import sys
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.gemini_client import GeminiClient, DesignBrief
from app.state.flow import FlowEngine


OUTPUT_ROOT = Path("app/static/generated/test_outputs")
SESSION_FILE = OUTPUT_ROOT / "_session.json"

# We only need _kv_to_precise_modifications and _category_key from FlowEngine.
_flow = FlowEngine.__new__(FlowEngine)


# ---------------------------------------------------------------------------
# Session tracking — mirrors production's Redis session for print persistence
# ---------------------------------------------------------------------------

def _load_session() -> dict:
    if SESSION_FILE.exists():
        return json.loads(SESSION_FILE.read_text())
    return {}


def _save_session(sess: dict) -> None:
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(sess, indent=2))


def production_modifications(category: str, field: str, value: str) -> dict:
    """
    Run the modification through the SAME _kv_to_precise_modifications
    that production uses, so test prompts match real user experience.
    """
    raw_kv = {field: value}
    return _flow._kv_to_precise_modifications(category, raw_kv)


# ---------------------------------------------------------------------------
# Base generation
# ---------------------------------------------------------------------------

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

    # Save session — mirrors production Redis state (including generated_image_front)
    _save_session({
        "generated_image": rel_path,
        "generated_image_front": rel_path,  # production tracks front image separately
        "design_category": category,
        "design_fabric": fabric,
        "design_color": color,
        "design_occasion": occasion,
        "design_print_ref": pattern_path or "",  # mirrors design_print_ref in production
    })

    return rel_path


# ---------------------------------------------------------------------------
# Modification — EXACT production logic from flow.py _regenerate_design_with_modifications
# ---------------------------------------------------------------------------

async def generate_modified(category: str, color: str, base_rel_path: str,
                            field: str, value: str,
                            fabric: str = "crepe", occasion: str = "Casual",
                            notes: str = "", dest_name: str = None) -> str:
    """
    Modify using the PRODUCTION code path:
    1. field + value go through _kv_to_precise_modifications
    2. If session has a print ref (from generate_base), automatically
       loads pattern bytes and adds print_preservation prompt
       (mirrors production flow.py lines 1846-1855)
    3. Result is passed to GeminiClient.generate_modified_image
    """
    client = GeminiClient()

    # Load session — use stored values like production does
    sess = _load_session()
    base_cat = sess.get("design_category", category)
    base_fabric = sess.get("design_fabric", fabric)
    base_color = sess.get("design_color", color)
    base_occasion = sess.get("design_occasion", occasion)
    persistent_print_ref = (sess.get("design_print_ref") or "").strip()

    # Production line 1797: always use front image as base for modifications
    base_rel_path = (sess.get("generated_image_front") or sess.get("generated_image") or base_rel_path).strip()

    brief = DesignBrief(
        occasion=base_occasion, budget="", category=base_cat,
        fabric=base_fabric, color=base_color,
        notes="", size="",
    )

    # Use production modification logic
    modifications = production_modifications(base_cat, field, value)

    # Print preservation — EXACT production logic (flow.py lines 1846-1855)
    pattern_bytes: Optional[bytes] = None
    pattern_mode = "apply"

    if persistent_print_ref:
        p = Path(persistent_print_ref)
        if p.exists():
            pattern_bytes = p.read_bytes()
        # Production guard: only set preserve mode if bytes were loaded (flow.py line 1849)
        if pattern_bytes:
            pattern_mode = "preserve"
            # Length modifications have print handling baked into the length prompt — skip separate key
            if field != "length":
                modifications["print_preservation"] = (
                    "The garment currently has a print/pattern on it (visible in the base image). "
                    "PRESERVE this print/pattern EXACTLY — same motifs, same placement, same detail. "
                    "Do NOT remove, fade, or simplify the print while applying other changes."
                )

    print(f"Production prompt: {modifications}")
    if persistent_print_ref:
        print(f"Print preservation: ON (pattern_mode={pattern_mode})")

    rel_path = await client.generate_modified_image(
        wa_id="test_local",
        base_image_rel_path=base_rel_path,
        brief=brief,
        modifications=modifications,
        pattern_image_bytes=pattern_bytes,
        pattern_mode=pattern_mode,
    )
    print(f"Generated: {rel_path}")

    src = Path("app" + rel_path) if rel_path.startswith("/static") else Path(rel_path)
    cat_folder = OUTPUT_ROOT / base_cat.lower().replace(" ", "_")
    cat_folder.mkdir(parents=True, exist_ok=True)

    fname = dest_name or f"{base_color.lower().replace(' ', '_')}_{base_cat.lower()}_{field}_{value}.png"
    dest = cat_folder / fname
    shutil.copy2(src, dest)
    print(f"Saved to: {dest}")

    # Update session — EXACT production logic (flow.py lines 1927-1944)
    sess["generated_image"] = rel_path

    # Production line 1927: detect back-facing modification
    is_back_mod = field == "back_detail"

    # Production lines 1934-1935: only update front image for non-back modifications
    if not is_back_mod:
        sess["generated_image_front"] = rel_path

    # Production lines 1942-1944: update color for both "color" and "color_top"
    if field in ("color", "color_top"):
        sess["design_color"] = value

    _save_session(sess)

    return rel_path


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
