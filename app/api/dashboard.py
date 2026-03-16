from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

SESSIONS_DIR = Path("app/data/sessions")


def _load_confirmed_orders() -> list[dict]:
    """Scan all session log folders, return orders with reason=order_confirmed."""
    orders: list[dict] = []

    if not SESSIONS_DIR.exists():
        return orders

    for date_dir in sorted(SESSIONS_DIR.iterdir(), reverse=True):
        if not date_dir.is_dir():
            continue

        for json_file in sorted(date_dir.glob("session_*.json"), reverse=True):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if data.get("reason") == "order_confirmed":
                    orders.append(data)
            except Exception:
                continue

    return orders


def _format_ts(ts: int | str) -> str:
    try:
        return time.strftime("%d %b %Y, %I:%M %p", time.localtime(int(ts)))
    except Exception:
        return str(ts)


def _build_html(orders: list[dict]) -> str:
    # Build order cards
    cards_html = ""
    for order in orders:
        # Use local /static/ path — served by FastAPI's StaticFiles mount
        image_rel = (order.get("generated_image") or "").strip()
        image_url = image_rel if image_rel else ""

        wa_id = order.get("wa_id", "")
        category = (order.get("design_category") or "").strip().title()
        fabric = (order.get("design_fabric") or "").strip().title()
        color = (order.get("design_color") or "").strip().title()
        occasion = (order.get("design_occasion") or "").strip()
        size = (order.get("buy_size") or "").strip()
        flow = (order.get("flow") or "design").strip()
        logged_ts = order.get("logged_at_ts", "")
        formatted_time = _format_ts(logged_ts) if logged_ts else ""

        # Modifications (if any)
        mod_kv_raw = (order.get("design_mod_kv") or "{}").strip()
        try:
            mod_kv = json.loads(mod_kv_raw) if mod_kv_raw else {}
        except Exception:
            mod_kv = {}
        mod_lines = ""
        if mod_kv and any(v for v in mod_kv.values()):
            mod_items = "".join(
                f"<li><strong>{k.replace('_', ' ').title()}:</strong> {v}</li>"
                for k, v in mod_kv.items()
                if v
            )
            if mod_items:
                mod_lines = f'<div class="mods"><strong>Modifications:</strong><ul>{mod_items}</ul></div>'

        image_block = (
            f'<img src="{image_url}" alt="Design" loading="lazy" />'
            if image_url
            else '<div class="no-img">No image</div>'
        )

        cards_html += f"""
        <div class="card">
            <div class="img-wrap">{image_block}</div>
            <div class="details">
                <div class="field"><strong>Phone:</strong> +{wa_id}</div>
                <div class="field"><strong>Category:</strong> {category}</div>
                <div class="field"><strong>Fabric:</strong> {fabric}</div>
                <div class="field"><strong>Color:</strong> {color}</div>
                <div class="field"><strong>Occasion:</strong> {occasion}</div>
                <div class="field"><strong>Size:</strong> {size}</div>
                <div class="field"><strong>Flow:</strong> {flow}</div>
                {mod_lines}
                <div class="timestamp">{formatted_time}</div>
            </div>
        </div>
        """

    count = len(orders)
    empty_msg = '<p class="empty">No confirmed orders yet.</p>' if count == 0 else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Empressa Orders Dashboard</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f5f5f5;
    color: #333;
    padding: 20px;
  }}
  header {{
    text-align: center;
    margin-bottom: 30px;
  }}
  header h1 {{
    font-size: 28px;
    color: #222;
  }}
  header .count {{
    font-size: 16px;
    color: #666;
    margin-top: 6px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
    gap: 20px;
    max-width: 1400px;
    margin: 0 auto;
  }}
  .card {{
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    overflow: hidden;
  }}
  .img-wrap {{
    width: 100%;
    aspect-ratio: 3/4;
    overflow: hidden;
    background: #eee;
  }}
  .img-wrap img {{
    width: 100%;
    height: 100%;
    object-fit: cover;
  }}
  .no-img {{
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #999;
    font-size: 14px;
  }}
  .details {{
    padding: 16px;
  }}
  .field {{
    font-size: 14px;
    margin-bottom: 6px;
  }}
  .field strong {{
    color: #555;
  }}
  .mods {{
    margin-top: 10px;
    font-size: 13px;
    background: #f9f9f9;
    padding: 10px;
    border-radius: 6px;
  }}
  .mods ul {{
    margin-top: 4px;
    padding-left: 18px;
  }}
  .mods li {{
    margin-bottom: 2px;
  }}
  .timestamp {{
    margin-top: 10px;
    font-size: 12px;
    color: #999;
  }}
  .empty {{
    text-align: center;
    color: #999;
    font-size: 18px;
    margin-top: 60px;
  }}
</style>
</head>
<body>
  <header>
    <h1>Empressa Orders Dashboard</h1>
    <div class="count">{count} confirmed order{'s' if count != 1 else ''}</div>
  </header>
  {empty_msg}
  <div class="grid">
    {cards_html}
  </div>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    orders = _load_confirmed_orders()
    return _build_html(orders)
