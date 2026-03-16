from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATALOG_PATH = Path("app/data/catalog/catalog.json")

class CatalogService:
    def load(self) -> list[dict[str, Any]]:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("catalog.json must be a list")
        return data
