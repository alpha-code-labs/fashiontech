from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from google import genai
from google.genai import types

from app.core.config import settings


@dataclass
class DesignBrief:
    occasion: str
    budget: str  # kept for backward compatibility; design flow passes ""
    category: str
    fabric: str
    color: str
    notes: str
    size: str


class GeminiPool:
    """Round-robin pool of Gemini clients with 429 failover."""

    def __init__(self, api_keys: List[str], max_concurrent: int = 8) -> None:
        self._clients = [genai.Client(api_key=k) for k in api_keys]
        self._count = len(self._clients)
        self._index = 0
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _next_client(self) -> genai.Client:
        async with self._lock:
            client = self._clients[self._index % self._count]
            self._index += 1
            return client

    async def generate(self, model: str, contents, config) -> object:
        """Try round-robin clients; on 429 failover to next key."""
        async with self._semaphore:
            last_err = None
            for attempt in range(self._count):
                client = await self._next_client()
                try:
                    return await client.aio.models.generate_content(
                        model=model, contents=contents, config=config,
                    )
                except Exception as e:
                    err_str = str(e).lower()
                    if "429" in err_str or "resource_exhausted" in err_str:
                        print(f"[GeminiPool] 429 on key #{(self._index - 1) % self._count}, trying next...")
                        last_err = e
                        continue
                    raise
            raise last_err or RuntimeError("All Gemini keys exhausted (429)")

    async def generate_text(self, model: str, contents) -> object:
        """Text generation (no semaphore needed, lighter calls)."""
        last_err = None
        for attempt in range(self._count):
            client = await self._next_client()
            try:
                return await client.aio.models.generate_content(
                    model=model, contents=contents,
                )
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "resource_exhausted" in err_str:
                    print(f"[GeminiPool] 429 on text call key #{(self._index - 1) % self._count}, trying next...")
                    last_err = e
                    continue
                raise
        raise last_err or RuntimeError("All Gemini keys exhausted (429)")


class GeminiClient:
    def __init__(self) -> None:
        # Build pool from GEMINI_API_KEYS (comma-separated), fallback to single GEMINI_API_KEY
        keys_str = os.getenv("GEMINI_API_KEYS") or getattr(settings, "GEMINI_API_KEYS", "")
        keys = [k.strip() for k in keys_str.split(",") if k.strip()] if keys_str else []

        if not keys:
            single_key = os.getenv("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", None)
            if not single_key:
                raise RuntimeError("GEMINI_API_KEY or GEMINI_API_KEYS missing in env")
            keys = [single_key]

        self.pool = GeminiPool(api_keys=keys)
        print(f"[GeminiClient] initialized with {len(keys)} API key(s)")

        # You can override in env/config if you want
        self.model = getattr(settings, "GEMINI_IMAGE_MODEL", None) or "gemini-2.0-flash-exp"
        self.text_model = getattr(settings, "GEMINI_TEXT_MODEL", None) or "gemini-2.0-flash"

        # where to save images so your existing /static mount serves them
        self.out_dir = Path("app/static/generated")
        self.out_dir.mkdir(parents=True, exist_ok=True)

    async def _generate_via_pool(self, model: str, contents, config=None) -> object:
        if config:
            return await self.pool.generate(model=model, contents=contents, config=config)
        return await self.pool.generate_text(model=model, contents=contents)

    # ✅ NEW: robust mime detection without imghdr (Python 3.13-safe)
    def _guess_mime(self, b: Optional[bytes]) -> str:
        if not b:
            return "application/octet-stream"

        head = b[:32]

        # PNG: 89 50 4E 47 0D 0A 1A 0A
        if head.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"

        # JPEG: FF D8 FF
        if head[:3] == b"\xff\xd8\xff":
            return "image/jpeg"

        # WEBP: "RIFF" .... "WEBP"
        if head.startswith(b"RIFF") and b"WEBP" in head[8:16]:
            return "image/webp"

        # GIF: "GIF87a" or "GIF89a"
        if head.startswith(b"GIF87a") or head.startswith(b"GIF89a"):
            return "image/gif"

        # Fallback: most WhatsApp images are jpeg
        return "image/jpeg"

    def _prompt(self, brief: DesignBrief, has_pattern: bool = False) -> str:
        vibe = brief.notes.strip() if brief.notes else "premium, stylish, modern"

        if has_pattern:
            print_rules = (
                "\n"
                "PRINT/PATTERN RULE (MUST FOLLOW):\n"
                "- A print/pattern reference image is provided.\n"
                f"- Apply ONLY the motif/pattern shapes from the reference image onto the {brief.color.upper()} garment fabric.\n"
                "- Keep everything else clean: no logos, no text, no brand marks.\n"
                "- Do NOT invent additional unrelated patterns beyond the reference.\n"
                "\n"
            )
        else:
            print_rules = (
                "\n"
                "IMPORTANT BASE-DESIGN RULE (MUST FOLLOW):\n"
                "- The outfit must be a plain SOLID color only.\n"
                "- Do NOT add any prints, patterns, motifs, graphics, embroidery, logos, text, or surface artwork.\n"
                "- No florals, stripes, checks, polka dots, animal print, abstract patterns.\n"
                "- Keep fabric surface visually uniform (minimal texture; no woven/patterned look).\n"
                "- Even if vibe/notes mention prints/patterns, IGNORE them for this first/base design.\n"
                "\n"
            )

        # Categories where full-length framing is critical
        cat_lower = (brief.category or "").lower()
        needs_full_body = any(
            kw in cat_lower
            for kw in ("pant", "skirt", "jumpsuit", "coord", "dress", "bottom")
        )
        framing = (
            "FRAMING: Full-body shot, head to toe including feet/shoes visible. "
            "Do NOT crop below the waist or at the knees.\n"
            if needs_full_body
            else "FRAMING: Show the full outfit from head to at least mid-calf.\n"
        )

        # For bottom-only categories, force a plain black top
        is_bottom_only = cat_lower in ("skirt", "pants")
        top_rule = (
            "\n"
            "UPPER BODY RULE (CRITICAL):\n"
            "- The model MUST wear a plain solid BLACK top on the upper body.\n"
            "- The top must be simple — no prints, no patterns, no embellishments, no design details.\n"
            "- The focus of this image is ONLY the " + brief.category + ". The top is just a neutral pairing.\n"
            "- Do NOT apply the garment's color, fabric, or print to the top. The top stays plain black.\n"
            "\n"
            if is_bottom_only
            else ""
        )

        return (
            "Create a high-quality fashion product-style image.\n"
            "Subject: a South Asian / Indian-looking female model wearing a women's western wear outfit.\n"
            "Style: premium, modern, Instagram-ready. Studio lighting.\n"
            "MODEL POSE & HAIR (CRITICAL):\n"
            "- Hair MUST be pulled back (bun, ponytail, or swept behind shoulders) so it does NOT cover any part of the garment.\n"
            "- Pose: front-facing, relaxed, arms slightly away from the body so the full garment silhouette is clearly visible.\n"
            "- Shoulders, neckline, sleeves, and all garment details must be fully unobstructed.\n"
            f"{framing}"
            "Do NOT add any text, logos, watermarks, brands.\n"
            f"{print_rules}"
            f"{top_rule}"
            f"Occasion: {brief.occasion}\n"
            f"Category: {brief.category}\n"
            f"Fabric: {brief.fabric}\n"
            f"Color: {brief.color}\n"
            "Fit: regular (not loose, not tight — standard body-skimming fit).\n"
            + (f"Size: {brief.size}\n" if brief.size else "")
            + (f"Vibe notes: {vibe}\n" if brief.notes else "")
            + "Output: ONE single image. Photorealistic."
        )

    def _modify_prompt(
        self,
        brief: DesignBrief,
        modifications: Dict[str, str],
        has_pattern: bool,
        pattern_mode: str = "apply",
    ) -> str:
        vibe = brief.notes.strip() if brief.notes else "premium, stylish, modern"
        changes_lines = []
        for k, v in modifications.items():
            if v:
                changes_lines.append(f"- {k}: {v}")
        changes = "\n".join(changes_lines) if changes_lines else "- (no changes provided)"

        if has_pattern and pattern_mode == "apply":
            color_anchor = f"The garment is currently {brief.color.upper()}." if brief.color else ""
            pattern_line = (
                "PATTERN REFERENCE IMAGE RULES (CRITICAL — FOLLOW EXACTLY):\n"
                "A pattern/print reference image is attached.\n"
                f"- {color_anchor} The garment color MUST stay EXACTLY {brief.color.upper()} — do NOT change it.\n"
                "- Extract ONLY the motif/design shapes from the reference image.\n"
                "- Apply those motifs as if screen-printed ONTO the garment's existing fabric.\n"
                "- IGNORE the reference image's background color completely — it is irrelevant.\n"
                "- The garment's base color must remain clearly visible between and around the motifs.\n"
                "- Think: stamping a pattern onto colored fabric. The fabric color stays, the motifs sit on top.\n"
                "- If the reference pattern has a background color different from the garment, discard that background."
            )
        elif has_pattern and pattern_mode == "preserve":
            pattern_line = (
                "PRINT PRESERVATION RULES:\n"
                "The garment in the base image already has a print/pattern on it.\n"
                "A pattern reference image is attached to show you what that print looks like.\n"
                "- You MUST preserve this print/pattern on the garment EXACTLY as it appears.\n"
                "- Do NOT remove, fade, simplify, or alter the print in any way.\n"
                "- Apply the requested modifications while keeping the print fully intact and visible.\n"
                "- If changing color, change the base fabric color but keep the pattern motifs clearly visible on top."
            )
        else:
            pattern_line = "No pattern/print reference image is provided."

        # If color is a concrete value, anchor it; otherwise omit the constraint
        is_concrete_color = brief.color and "best suits" not in brief.color.lower()
        if is_concrete_color:
            color_rule = f"- Unless a color change is explicitly requested, keep the garment color as {brief.color}.\n"
            color_ctx = f"- Color (current / base): {brief.color}\n"
        else:
            color_rule = "- Unless a color change is explicitly requested, keep the current garment color as seen in the image.\n"
            color_ctx = "- Color: as shown in the original image\n"

        # Full-body framing for categories where length matters
        cat_lower = (brief.category or "").lower()
        needs_full_body = any(
            kw in cat_lower
            for kw in ("pant", "skirt", "jumpsuit", "coord", "dress", "bottom")
        )
        framing = (
            "- FRAMING: Full-body shot, head to toe including feet/shoes visible. "
            "Do NOT crop below the waist or at the knees.\n"
            if needs_full_body
            else "- FRAMING: Show the full outfit from head to at least mid-calf.\n"
        )

        # Black top rule for bottom-only categories
        is_bottom_only = cat_lower in ("skirt", "pants")
        top_rule = (
            "- UPPER BODY RULE (CRITICAL): The model MUST keep wearing a plain solid BLACK top. "
            "No prints, no patterns, no embellishments on the top. "
            "Do NOT apply any modifications, color changes, or prints to the top — it stays plain black. "
            "All modifications apply ONLY to the " + brief.category + ".\n"
            if is_bottom_only
            else ""
        )

        return (
            "You are editing an existing fashion image.\n"
            "\n"
            "PRIORITY: The 'Requested modifications' below are the PRIMARY goal. Apply them fully and visibly.\n"
            "\n"
            "Other rules (secondary to the modifications above):\n"
            "- Keep the SAME model, same camera angle, same lighting.\n"
            "- Hair MUST stay pulled back (bun, ponytail, or swept behind shoulders) — do NOT let hair cover any part of the garment.\n"
            "- Pose: front-facing, arms slightly away from body so the full garment silhouette is visible.\n"
            + framing
            + top_rule
            + "- Attributes NOT mentioned in the modifications should stay as they are.\n"
            + color_rule
            + "- Do not add text, logos, watermarks.\n"
            "\n"
            "Base outfit context:\n"
            f"- Occasion: {brief.occasion}\n"
            f"- Category: {brief.category}\n"
            f"- Fabric: {brief.fabric}\n"
            + color_ctx
            + (f"- Size: {brief.size}\n" if brief.size else "")
            + (f"- Vibe notes: {vibe}\n" if brief.notes else "")
            + "\n"
            "Requested modifications (APPLY THESE FULLY):\n"
            f"{changes}\n"
            "\n"
            f"{pattern_line}\n"
            "\n"
            + (f"FINAL REMINDER — COLOR: The garment MUST remain {brief.color.upper()}. Do NOT shift the garment color to match any pattern reference image.\n\n" if has_pattern and is_concrete_color else "")
            + "Output: ONE single edited image, photorealistic."
        )

    def _rel_static_to_abs(self, rel_path: str) -> Path:
        rel_path = (rel_path or "").strip()
        if not rel_path.startswith("/static/"):
            raise ValueError(f"Expected rel static path like '/static/...', got: {rel_path}")

        sub = rel_path[len("/static/") :]
        return Path("app/static") / sub

    def _base_image_exists(self, base_image_rel_path: str) -> bool:
        try:
            if not base_image_rel_path:
                return False
            abs_path = self._rel_static_to_abs(base_image_rel_path)
            return abs_path.exists()
        except Exception:
            return False

    async def generate_image_only(
        self,
        wa_id: str,
        brief: DesignBrief,
        pattern_image_bytes: Optional[bytes] = None,
    ) -> str:
        """
        - If pattern_image_bytes is None -> generate a plain/solid base design (no prints).
        - If pattern_image_bytes is provided -> apply the print/pattern reference during generation.

        ✅ Key fix:
        - Use correct mime_type for the uploaded pattern bytes (WhatsApp uploads are usually JPEG).
        """
        has_pattern = bool(pattern_image_bytes)
        prompt = self._prompt(brief, has_pattern=has_pattern)

        if pattern_image_bytes:
            pattern_mime = self._guess_mime(pattern_image_bytes)
            parts = [
                types.Part.from_text(text=prompt),
                types.Part.from_bytes(data=pattern_image_bytes, mime_type=pattern_mime),
            ]
            resp = await self._generate_via_pool(
                model=self.model,
                contents=types.Content(role="user", parts=parts),
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )
        else:
            resp = await self._generate_via_pool(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )

        image_bytes = None
        for cand in (resp.candidates or []):
            if not cand.content or not cand.content.parts:
                print(f"[GeminiClient] candidate has no content/parts, finish_reason={getattr(cand, 'finish_reason', 'unknown')}")
                continue
            for part in (cand.content.parts or []):
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break
            if image_bytes:
                break

        if not image_bytes:
            raise RuntimeError("Gemini did not return image bytes")

        fname = f"design_{wa_id}_{uuid.uuid4().hex[:12]}.png"
        out_path = self.out_dir / fname
        out_path.write_bytes(image_bytes)

        return f"/static/generated/{fname}"

    async def generate_modified_image(
        self,
        wa_id: str,
        base_image_rel_path: str,
        brief: DesignBrief,
        modifications: Dict[str, str],
        pattern_image_bytes: Optional[bytes] = None,
        pattern_mode: str = "apply",
    ) -> str:
        base_abs = self._rel_static_to_abs(base_image_rel_path)
        if not base_abs.exists():
            raise RuntimeError(f"Base design image not found on disk: {base_abs}")

        base_bytes = base_abs.read_bytes()

        has_pattern = bool(pattern_image_bytes)
        if has_pattern:
            modifications = dict(modifications or {})
            if pattern_mode == "apply":
                modifications.setdefault(
                    "print",
                    "Apply the pattern motifs from the reference image onto the garment fabric. Keep the garment's current base color unchanged.",
                )
            else:
                modifications.setdefault(
                    "print_preservation",
                    "Preserve the existing print/pattern on the garment exactly as it appears.",
                )

        prompt = self._modify_prompt(brief, modifications, has_pattern=has_pattern, pattern_mode=pattern_mode)

        # Order: base image → pattern reference → text prompt
        # Text prompt LAST so text instructions carry the most weight
        parts = [
            types.Part.from_bytes(data=base_bytes, mime_type="image/png"),
        ]
        if pattern_image_bytes:
            pattern_mime = self._guess_mime(pattern_image_bytes)
            parts.append(types.Part.from_bytes(data=pattern_image_bytes, mime_type=pattern_mime))
        parts.append(types.Part.from_text(text=prompt))

        resp = await self._generate_via_pool(
            model=self.model,
            contents=types.Content(role="user", parts=parts),
            config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
        )

        image_bytes = None
        for cand in (resp.candidates or []):
            if not cand.content or not cand.content.parts:
                print(f"[GeminiClient] candidate has no content/parts, finish_reason={getattr(cand, 'finish_reason', 'unknown')}")
                continue
            for part in (cand.content.parts or []):
                if part.inline_data and part.inline_data.data:
                    image_bytes = part.inline_data.data
                    break
            if image_bytes:
                break

        if not image_bytes:
            raise RuntimeError("Gemini did not return modified image bytes")

        fname = f"design_modified_{wa_id}_{uuid.uuid4().hex[:12]}.png"
        out_path = self.out_dir / fname
        out_path.write_bytes(image_bytes)

        return f"/static/generated/{fname}"

    async def generate_modified_or_new(
        self,
        wa_id: str,
        base_image_rel_path: str,
        brief: DesignBrief,
        modifications: Dict[str, str],
        pattern_image_bytes: Optional[bytes] = None,
        pattern_mode: str = "apply",
    ) -> str:
        if self._base_image_exists(base_image_rel_path):
            return await self.generate_modified_image(
                wa_id=wa_id,
                base_image_rel_path=base_image_rel_path,
                brief=brief,
                modifications=modifications,
                pattern_image_bytes=pattern_image_bytes,
                pattern_mode=pattern_mode,
            )

        return await self.generate_image_only(
            wa_id=wa_id,
            brief=brief,
            pattern_image_bytes=pattern_image_bytes,
        )

    # -------------------------
    # UPLOAD & DESIGN — image analysis + inspired generation
    # -------------------------

    async def analyze_image(self, image_bytes: bytes) -> Dict[str, str]:
        """
        Uses the text model (with vision) to analyze a fashion image.
        Returns a dict with: category, occasion, fabric, color, style_notes.
        Category values map to our existing categories.
        """
        mime = self._guess_mime(image_bytes)
        prompt = (
            "You are a fashion expert. Analyze this clothing image and return a JSON object with these fields:\n"
            '- "category": one of: dress, top, skirt, pants, jumpsuit, jacket, shirts, coord sets, blouse, t-shirts\n'
            '- "occasion": one of: Party/Date, Office, Casual, Vacation\n'
            '- "fabric": one of: satin, crepe, cotton, linen, georgette, denim, silk, velvet\n'
            '- "color": the dominant color of the garment (e.g. "red", "navy blue", "black")\n'
            '- "style_notes": 1-2 sentence description of the style, silhouette, and key details\n'
            "\n"
            "If the image shows multiple garments (e.g. a top and pants together), classify as coord sets.\n"
            "Return ONLY the JSON object, no other text."
        )

        parts = [
            types.Part.from_bytes(data=image_bytes, mime_type=mime),
            types.Part.from_text(text=prompt),
        ]

        resp = await self._generate_via_pool(
            model=self.text_model,
            contents=types.Content(role="user", parts=parts),
        )

        raw_text = (resp.text or "").strip()

        # Clean markdown code blocks if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            raw_text = "\n".join(lines).strip()

        try:
            result = json.loads(raw_text)
        except json.JSONDecodeError:
            # Fallback: try to extract JSON from the response
            start = raw_text.find("{")
            end = raw_text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(raw_text[start:end])
            else:
                result = {
                    "category": "dress",
                    "occasion": "Casual",
                    "fabric": "cotton",
                    "color": "black",
                    "style_notes": "Unable to analyze image",
                }

        # Normalize category to our known values
        known_cats = {"dress", "top", "skirt", "pants", "jumpsuit", "jacket", "shirts", "coord sets", "blouse", "t-shirts"}
        cat = (result.get("category") or "dress").strip().lower()
        if cat not in known_cats:
            cat = "dress"
        result["category"] = cat

        return result

    async def generate_inspired_image(
        self,
        wa_id: str,
        brief: DesignBrief,
        ref_bytes: bytes,
        variation: str,
        index: int,
        pattern_image_bytes: Optional[bytes] = None,
        color_override: Optional[str] = None,
    ) -> Optional[str]:
        """
        Generate a NEW design INSPIRED by the reference image.
        If pattern_image_bytes is provided, include the pattern as a reference
        and add print preservation instructions to the prompt.
        If color_override is provided, use it instead of brief.color for the Color line.
        Returns relative image path on success, None on failure.
        """
        try:
            ref_mime = self._guess_mime(ref_bytes)

            pattern_instruction = ""
            if pattern_image_bytes:
                pattern_instruction = (
                    "\nPRINT/PATTERN RULE (MUST FOLLOW):\n"
                    "- A print/pattern reference image is also provided.\n"
                    "- The reference design has this print/pattern applied to the garment.\n"
                    "- You MUST preserve this exact print/pattern on the new design.\n"
                    "- Same motifs, same density, same placement.\n"
                    "- Only change what the VARIATION INSTRUCTION asks for.\n"
                    "\n"
                )

            color_line = color_override if color_override else brief.color

            prompt = (
                "Create a high-quality fashion product-style image.\n"
                "Subject: a South Asian / Indian-looking female model wearing a women's western wear outfit.\n"
                "Style: premium, modern, Instagram-ready. Natural pose. Studio lighting.\n"
                "Do NOT add any text, logos, watermarks, brands.\n"
                "\n"
                "A REFERENCE image is provided. Create a NEW design INSPIRED by it, NOT a copy.\n"
                f"Occasion: {brief.occasion}\n"
                f"Category: {brief.category}\n"
                f"Fabric: {brief.fabric}\n"
                f"Color: {color_line}\n"
                f"Style notes: {brief.notes}\n"
                f"{pattern_instruction}"
                "\n"
                f"VARIATION INSTRUCTION: {variation}\n"
                "\n"
                "Output: ONE single image. Photorealistic."
            )

            parts = [
                types.Part.from_bytes(data=ref_bytes, mime_type=ref_mime),
            ]
            if pattern_image_bytes:
                pattern_mime = self._guess_mime(pattern_image_bytes)
                parts.append(types.Part.from_bytes(data=pattern_image_bytes, mime_type=pattern_mime))
            parts.append(types.Part.from_text(text=prompt))

            resp = await self._generate_via_pool(
                model=self.model,
                contents=types.Content(role="user", parts=parts),
                config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
            )

            image_bytes = None
            for cand in (resp.candidates or []):
                if not cand.content or not cand.content.parts:
                    print(f"[GeminiClient] generate_inspired_image candidate has no content/parts, finish_reason={getattr(cand, 'finish_reason', 'unknown')}")
                    continue
                for part in (cand.content.parts or []):
                    if part.inline_data and part.inline_data.data:
                        image_bytes = part.inline_data.data
                        break
                if image_bytes:
                    break

            if not image_bytes:
                return None

            fname = f"design_upload_{wa_id}_{uuid.uuid4().hex[:12]}_{index}.png"
            out_path = self.out_dir / fname
            out_path.write_bytes(image_bytes)

            return f"/static/generated/{fname}"

        except Exception as e:
            print(f"[generate_inspired_image] option {index} failed: {e}")
            return None
