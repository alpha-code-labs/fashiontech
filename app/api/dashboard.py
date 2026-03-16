from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

SESSIONS_DIR = Path("app/data/sessions")
PRINTS_JSON = Path("app/static/prints/prints.json")


def _load_prints_map() -> dict[str, dict]:
    """Load prints.json into a dict keyed by print id."""
    if not PRINTS_JSON.exists():
        return {}
    try:
        data = json.loads(PRINTS_JSON.read_text(encoding="utf-8"))
        return {p["id"]: p for p in data}
    except Exception:
        return {}


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
    prints_map = _load_prints_map()

    cards_html = ""
    for idx, order in enumerate(orders, 1):
        image_rel = (order.get("generated_image") or "").strip()
        image_url = image_rel if image_rel else ""

        wa_id = order.get("wa_id", "")
        category = (order.get("design_category") or "").strip().title()
        fabric = (order.get("design_fabric") or "").strip().title()
        color = (order.get("design_color") or "").strip().title()
        size = (order.get("buy_size") or "").strip().upper()
        logged_ts = order.get("logged_at_ts", "")
        formatted_time = _format_ts(logged_ts) if logged_ts else ""

        # Print / pattern info
        print_id = (order.get("design_print_id") or "").strip()
        print_name = (order.get("design_print_name") or "").strip()
        print_swatch_url = ""
        print_category = ""

        if print_id and print_id in prints_map:
            entry = prints_map[print_id]
            print_name = print_name or entry.get("name", print_id)
            print_category = entry.get("category", "").replace("_", " ").title()
            print_swatch_url = f'/static/prints/{entry.get("file", "")}'
        elif print_id:
            print_name = print_name or print_id.replace("_", " ").title()
            print_category = (order.get("print_page_category") or "").replace("_", " ").title()

        if print_id:
            print_block = f"""
                <div class="spec-row print-row">
                    <span class="spec-label">Print</span>
                    <span class="spec-value print-info">
                        {'<img src="' + print_swatch_url + '" class="swatch" alt="Swatch" />' if print_swatch_url else ''}
                        <span>{print_name}{' (' + print_category + ')' if print_category else ''}</span>
                    </span>
                </div>"""
        else:
            print_block = """
                <div class="spec-row">
                    <span class="spec-label">Print</span>
                    <span class="spec-value subdued">Solid / No print</span>
                </div>"""

        # Modifications
        mod_kv_raw = (order.get("design_mod_kv") or "{}").strip()
        try:
            mod_kv = json.loads(mod_kv_raw) if mod_kv_raw else {}
        except Exception:
            mod_kv = {}
        mod_block = ""
        if mod_kv and any(v for v in mod_kv.values()):
            mod_items = "".join(
                f'<li><span class="mod-key">{k.replace("_", " ").title()}</span> {v}</li>'
                for k, v in mod_kv.items()
                if v
            )
            if mod_items:
                mod_block = f'<div class="mods-section"><div class="section-title">Modifications</div><ul>{mod_items}</ul></div>'

        image_block = (
            f'<img src="{image_url}" alt="Design" loading="lazy" />'
            if image_url
            else '<div class="no-img">No design image</div>'
        )

        cards_html += f"""
        <div class="order-card">
            <div class="order-header">
                <span class="order-num">#{idx}</span>
                <span class="order-date">{formatted_time}</span>
            </div>
            <div class="order-body">
                <div class="design-img">{image_block}</div>
                <div class="order-details">
                    <div class="section-title">Manufacturing Specs</div>
                    <div class="specs">
                        <div class="spec-row">
                            <span class="spec-label">Category</span>
                            <span class="spec-value">{category}</span>
                        </div>
                        <div class="spec-row">
                            <span class="spec-label">Fabric</span>
                            <span class="spec-value">{fabric}</span>
                        </div>
                        <div class="spec-row">
                            <span class="spec-label">Color</span>
                            <span class="spec-value">{color}</span>
                        </div>
                        <div class="spec-row">
                            <span class="spec-label">Size</span>
                            <span class="spec-value size-badge">{size}</span>
                        </div>
                        {print_block}
                    </div>
                    {mod_block}
                    <div class="customer-section">
                        <div class="section-title">Customer</div>
                        <div class="spec-row">
                            <span class="spec-label">Phone</span>
                            <span class="spec-value">+{wa_id}</span>
                        </div>
                    </div>
                </div>
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
<meta http-equiv="refresh" content="60">
<title>Empressa — Manufacturing Orders</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #f0f2f5;
    color: #1a1a1a;
    min-height: 100vh;
  }}
  .top-bar {{
    background: #1a1a2e;
    color: #fff;
    padding: 20px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .top-bar h1 {{
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.3px;
  }}
  .top-bar .brand {{
    font-weight: 300;
    opacity: 0.7;
  }}
  .top-bar .order-count {{
    background: rgba(255,255,255,0.15);
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 14px;
  }}
  .container {{
    max-width: 1200px;
    margin: 0 auto;
    padding: 24px 20px;
  }}
  .order-card {{
    background: #fff;
    border-radius: 10px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    margin-bottom: 20px;
    overflow: hidden;
    border: 1px solid #e8e8e8;
  }}
  .order-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 20px;
    background: #fafafa;
    border-bottom: 1px solid #eee;
  }}
  .order-num {{
    font-weight: 700;
    font-size: 16px;
    color: #1a1a2e;
  }}
  .order-date {{
    font-size: 13px;
    color: #888;
  }}
  .order-body {{
    display: flex;
    gap: 24px;
    padding: 20px;
  }}
  .design-img {{
    flex: 0 0 280px;
    aspect-ratio: 3/4;
    border-radius: 8px;
    overflow: hidden;
    background: #f5f5f5;
    border: 1px solid #eee;
  }}
  .design-img img {{
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
    color: #bbb;
    font-size: 14px;
  }}
  .order-details {{
    flex: 1;
    min-width: 0;
  }}
  .section-title {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: #888;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid #f0f0f0;
  }}
  .specs {{
    margin-bottom: 18px;
  }}
  .spec-row {{
    display: flex;
    align-items: center;
    padding: 5px 0;
    font-size: 14px;
  }}
  .spec-label {{
    width: 80px;
    flex-shrink: 0;
    color: #999;
    font-size: 13px;
  }}
  .spec-value {{
    font-weight: 500;
    color: #333;
  }}
  .spec-value.subdued {{
    color: #aaa;
    font-weight: 400;
    font-style: italic;
  }}
  .size-badge {{
    display: inline-block;
    background: #1a1a2e;
    color: #fff;
    padding: 2px 10px;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 600;
  }}
  .print-info {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .swatch {{
    width: 36px;
    height: 36px;
    border-radius: 4px;
    object-fit: cover;
    border: 1px solid #ddd;
  }}
  .mods-section {{
    margin-bottom: 18px;
  }}
  .mods-section ul {{
    list-style: none;
    padding: 0;
  }}
  .mods-section li {{
    font-size: 13px;
    padding: 4px 0;
    color: #555;
  }}
  .mod-key {{
    display: inline-block;
    background: #f0f0f0;
    padding: 1px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: 600;
    color: #666;
    margin-right: 6px;
  }}
  .customer-section {{
    margin-top: 4px;
  }}
  .empty {{
    text-align: center;
    color: #aaa;
    font-size: 16px;
    margin-top: 80px;
  }}

  @media (max-width: 700px) {{
    .order-body {{
      flex-direction: column;
    }}
    .design-img {{
      flex: none;
      width: 100%;
      max-width: 320px;
    }}
  }}

  @media print {{
    .top-bar {{ background: #fff; color: #000; border-bottom: 2px solid #000; }}
    .order-card {{ break-inside: avoid; box-shadow: none; border: 1px solid #ccc; }}
    body {{ background: #fff; }}
  }}
</style>
</head>
<body>
  <div class="top-bar">
    <h1><span class="brand">Empressa</span> — Manufacturing Orders</h1>
    <div class="order-count">{count} order{'s' if count != 1 else ''}</div>
  </div>
  <div class="container">
    {empty_msg}
    {cards_html}
  </div>
</body>
</html>"""


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    orders = _load_confirmed_orders()
    return _build_html(orders)
