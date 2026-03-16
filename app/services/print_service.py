from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont


PRINTS_DIR = Path("app/static/prints")
COLLAGE_DIR = Path("app/static/generated")
PAGE_SIZE = 6


class PrintService:
    def __init__(self) -> None:
        COLLAGE_DIR.mkdir(parents=True, exist_ok=True)
        self._cache: Optional[List[Dict[str, Any]]] = None
        self._cache_mtime: float = 0.0

    def load_all(self) -> List[Dict[str, Any]]:
        json_path = PRINTS_DIR / "prints.json"
        mtime = json_path.stat().st_mtime
        if self._cache is not None and mtime == self._cache_mtime:
            return self._cache
        data = json.loads(json_path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("prints.json must be a list")
        self._cache = data
        self._cache_mtime = mtime
        return data

    def get_by_category(self, category: str) -> List[Dict[str, Any]]:
        return [p for p in self.load_all() if p["category"] == category]

    def get_by_id(self, print_id: str) -> Optional[Dict[str, Any]]:
        for p in self.load_all():
            if p["id"] == print_id:
                return p
        return None

    def get_print_image_path(self, print_entry: Dict[str, Any]) -> Path:
        return PRINTS_DIR / print_entry["file"]

    def get_print_image_bytes(self, print_entry: Dict[str, Any]) -> bytes:
        return self.get_print_image_path(print_entry).read_bytes()

    def get_page(self, category: str, page: int = 0) -> tuple:
        """
        Return (prints_for_page, has_more).
        page is 0-indexed. Returns up to PAGE_SIZE prints.
        """
        all_prints = self.get_by_category(category)
        offset = page * PAGE_SIZE
        page_prints = all_prints[offset:offset + PAGE_SIZE]
        has_more = (offset + PAGE_SIZE) < len(all_prints)
        return page_prints, has_more

    def generate_collage(self, prints: List[Dict[str, Any]], wa_id: str = "", start_number: int = 1) -> str:
        """
        Generate a 3x2 collage of print swatches with numbered labels.
        Returns relative static path like /static/generated/collage_xxx.png
        """
        cols, rows = 3, 2
        cell_w, cell_h = 340, 440
        padding = 15
        label_h = 40

        canvas_w = cols * cell_w + (cols + 1) * padding
        canvas_h = rows * (cell_h + label_h) + (rows + 1) * padding

        canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)

        # Try to load a clean font; fall back to default
        font = None
        for font_path in [
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]:
            try:
                font = ImageFont.truetype(font_path, 22)
                break
            except (OSError, IOError):
                continue
        if font is None:
            font = ImageFont.load_default()

        for i, p in enumerate(prints[:6]):
            row = i // cols
            col = i % cols

            x = padding + col * (cell_w + padding)
            y = padding + row * (cell_h + label_h + padding)

            # Load and resize image to fit cell
            img_path = self.get_print_image_path(p)
            img = Image.open(img_path)
            img = img.resize((cell_w, cell_h), Image.LANCZOS)

            canvas.paste(img, (x, y))

            # Draw numbered label below the image
            label = f"{start_number + i}. {p['name']}"
            draw.text((x + 5, y + cell_h + 8), label, fill=(0, 0, 0), font=font)

        fname = f"collage_{wa_id}_{uuid.uuid4().hex[:12]}.png"
        out_path = COLLAGE_DIR / fname
        canvas.save(out_path)

        return f"/static/generated/{fname}"
