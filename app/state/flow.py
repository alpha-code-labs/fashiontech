# app/state/flow.py
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.services.gemini_client import GeminiClient, DesignBrief
from app.services.whatsapp_client import WhatsAppClient
from app.services.catalog_service import CatalogService
from app.services.session_logger import SessionLogger
from app.services.print_service import PrintService
from app.state.store import SessionStore

STATE_NONE = "NONE"
STATE_START = "START"

# --- CATALOG STATES (UNCHANGED) ---
STATE_CATALOG_OCCASION = "CATALOG_OCCASION"
STATE_CATALOG_BUDGET = "CATALOG_BUDGET"

# --- DESIGN STATES (UPDATED) ---
STATE_DESIGN_OCCASION = "DESIGN_OCCASION"
# NOTE: budget removed as per requirement #1
STATE_DESIGN_CATEGORY = "DESIGN_CATEGORY"
STATE_DESIGN_FABRIC = "DESIGN_FABRIC"
STATE_DESIGN_COLOR = "DESIGN_COLOR"
STATE_DESIGN_COLOR_TEXT = "DESIGN_COLOR_TEXT"
STATE_DESIGN_PRINT_CATEGORY = "DESIGN_PRINT_CATEGORY"
STATE_DESIGN_PRINT_PICK = "DESIGN_PRINT_PICK"
STATE_DESIGN_POST = "DESIGN_POST"  # after image comes back, show buttons

# --- DESIGN MODIFY STATES (UPDATED) ---
STATE_DESIGN_MODIFY_MENU = "DESIGN_MODIFY_MENU"                 # conditional list based on category
STATE_DESIGN_MODIFY_FIELD_TEXT = "DESIGN_MODIFY_FIELD_TEXT"     # kept for backward compatibility (e.g., color free-text)
STATE_DESIGN_MODIFY_FIELD_CHOICE = "DESIGN_MODIFY_FIELD_CHOICE" # user picks from preset options for a field
STATE_DESIGN_MODIFY_WAIT_PATTERN = "DESIGN_MODIFY_WAIT_PATTERN" # user uploads print/pattern image

# --- UPLOAD & DESIGN STATES ---
STATE_UPLOAD_WAIT_IMAGE = "UPLOAD_WAIT_IMAGE"
STATE_UPLOAD_PICK_OPTION = "UPLOAD_PICK_OPTION"

# --- SHARED BUY STATES (used by Design "Buy now"; catalog uses this now too) ---
STATE_BUY_NAME = "BUY_NAME"
STATE_BUY_EMAIL = "BUY_EMAIL"
STATE_BUY_SIZE = "BUY_SIZE"
STATE_BUY_CONFIRM = "BUY_CONFIRM"

MAX_GENERATIONS = 10
MAX_MODIFICATIONS = 10

ERROR_MSG_HIGH_VOLUME = (
    "We're experiencing unusually high volumes right now. "
    "Please try again in about 30 minutes — we'll be ready for you! 💖"
)


class FlowEngine:
    def __init__(
        self,
        wa: WhatsAppClient,
        store: SessionStore,
        catalog: CatalogService,
        logger: SessionLogger,
        gemini: GeminiClient,
        print_service: PrintService | None = None,
    ):
        self.wa = wa
        self.store = store
        self.catalog = catalog
        self.logger = logger
        self.gemini = gemini
        self.print_service = print_service or PrintService()

    async def send_start_menu(self, wa_id: str) -> None:
        await self.store.set_fields(wa_id, {"state": STATE_START, "nudge_count": "0"})
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_START)
        await self.wa.send_buttons(
            wa_id,
            "Heyy 💖 Love it!\nWhat do you want to do today? ✨",
            [
                ("DESIGN_YOUR_OWN", "Design Your Own"),
            ],
        )

    async def handle_start_design_keyword(self, wa_id: str) -> None:
        await self.send_start_menu(wa_id)

    async def force_timeout(self, wa_id: str) -> None:
        sess = await self.store.get(wa_id)
        if not sess:
            return

        nudge_count = int(sess.get("nudge_count", "0"))

        if nudge_count < 2:
            # Nudge: resend last step, increment counter, reset timer
            await self.store.set_fields(wa_id, {"nudge_count": str(nudge_count + 1)})
            await self.store.touch(wa_id)
            state = sess.get("state", STATE_START)
            await self._resend_current_step(wa_id, state, sess)
            return

        # 2 nudges done — silently expire
        sess["reason"] = "timeout"
        self.logger.log_step(wa_id, "SESSION_TIMEOUT")
        self.logger.write(wa_id, sess)
        await self.store.delete(wa_id)

    async def _resend_current_step(self, wa_id: str, state: str, sess: dict) -> None:
        """Resend the prompt for the user's current step as a nudge."""

        if state == STATE_START:
            await self.wa.send_buttons(
                wa_id,
                "Still there? 💖 What do you want to do today? ✨",
                [("DESIGN_YOUR_OWN", "Design Your Own")],
            )

        elif state == STATE_DESIGN_OCCASION:
            await self.wa.send_list(
                wa_id,
                "Still there? 😊 What's the occasion?",
                "Choose",
                sections=[{"title": "Occasion", "rows": [
                    {"id": "D_OCC_PARTY", "title": "Party/Date"},
                    {"id": "D_OCC_OFFICE", "title": "Office"},
                    {"id": "D_OCC_CASUAL", "title": "Casual"},
                    {"id": "D_OCC_VACATION", "title": "Vacation"},
                ]}],
            )

        elif state == STATE_DESIGN_CATEGORY:
            await self.wa.send_list(
                wa_id,
                "Still there? 💖 What are we designing?",
                "Choose",
                sections=[{"title": "Category", "rows": [
                    {"id": "D_CAT_DRESS", "title": "Dress"},
                    {"id": "D_CAT_TOP", "title": "Top"},
                    {"id": "D_CAT_SKIRT", "title": "Skirt"},
                    {"id": "D_CAT_PANTS", "title": "Pants"},
                    {"id": "D_CAT_JUMPSUIT", "title": "Jumpsuit"},
                    {"id": "D_CAT_SHIRTS", "title": "Shirts"},
                    {"id": "D_CAT_COORDS", "title": "Coord sets"},
                ]}],
            )

        elif state == STATE_DESIGN_FABRIC:
            await self.wa.send_list(
                wa_id,
                "Still there? 😌 What fabric?",
                "Choose",
                sections=[{"title": "Fabric", "rows": [
                    {"id": "D_FAB_COTTON", "title": "Cotton"},
                    {"id": "D_FAB_VISCOSE_LINEN", "title": "Viscose linen"},
                    {"id": "D_FAB_COTTON_LINEN", "title": "Cotton linen"},
                    {"id": "D_FAB_RAYON", "title": "Rayon"},
                    {"id": "D_FAB_POLYCREPE", "title": "Polycrepe"},
                    {"id": "D_FAB_DENIM", "title": "Denim"},
                ]}],
            )

        elif state == STATE_DESIGN_COLOR:
            await self.wa.send_list(
                wa_id,
                "Still there? ✨ What color?",
                "Choose",
                sections=[{"title": "Color", "rows": [
                    {"id": "D_CLR_BLACK", "title": "Black"},
                    {"id": "D_CLR_WHITE", "title": "White"},
                    {"id": "D_CLR_RED", "title": "Red"},
                    {"id": "D_CLR_NAVY", "title": "Navy Blue"},
                    {"id": "D_CLR_BEIGE", "title": "Beige"},
                    {"id": "D_CLR_PINK", "title": "Pink"},
                    {"id": "D_CLR_GREEN", "title": "Emerald Green"},
                    {"id": "D_CLR_MAROON", "title": "Maroon"},
                    {"id": "D_CLR_CUSTOM", "title": "Type my own color"},
                ]}],
            )

        elif state == STATE_DESIGN_COLOR_TEXT:
            await self.wa.send_text(
                wa_id,
                "Still there? 💖 Type any color you like!\n"
                "E.g. coral, sage green, dusty rose…",
            )

        elif state == STATE_DESIGN_PRINT_CATEGORY:
            await self._start_print_selection(wa_id, return_to=sess.get("print_return_to", "generate"))

        elif state == STATE_DESIGN_PRINT_PICK:
            category = sess.get("print_page_category", "")
            page = int(sess.get("print_page", "0"))
            if category:
                await self._send_print_page(wa_id, category, page)
            else:
                await self._start_print_selection(wa_id, return_to=sess.get("print_return_to", "generate"))

        elif state == STATE_DESIGN_POST:
            await self._send_design_post(wa_id)

        elif state == STATE_DESIGN_MODIFY_MENU:
            await self._send_design_modify_menu(wa_id)

        elif state == STATE_DESIGN_MODIFY_FIELD_CHOICE:
            # Re-show the field options — handled by resending the modify menu
            await self._send_design_modify_menu(wa_id)

        elif state == STATE_DESIGN_MODIFY_FIELD_TEXT:
            field = sess.get("design_mod_field", "")
            await self.wa.send_text(
                wa_id,
                f"Still there? 💖 Please type the {field.replace('_', ' ')} you'd like.",
            )

        elif state == STATE_UPLOAD_WAIT_IMAGE:
            await self.wa.send_text(
                wa_id,
                "Still there? 💖 Please upload a photo of the outfit you like.",
            )

        elif state == STATE_UPLOAD_PICK_OPTION:
            await self._send_design_post(wa_id)

        elif state == STATE_BUY_SIZE:
            await self._send_size_selection(wa_id, intro="Still there? 💖 What's your size?")

        elif state == STATE_BUY_CONFIRM:
            await self.wa.send_text(
                wa_id,
                "Still there? 💖 Please confirm your order above.",
            )

        elif state == STATE_BUY_NAME:
            await self.wa.send_text(wa_id, "Still there? 🙂 Please type your name.")

        elif state == STATE_BUY_EMAIL:
            await self.wa.send_text(wa_id, "Still there? 🙂 Please type your email address.")

        elif state == STATE_CATALOG_OCCASION:
            await self.wa.send_list(
                wa_id,
                "Still there? 😍 What are you shopping for?",
                "Choose",
                sections=[{"title": "Occasion", "rows": [
                    {"id": "OCCASION_PARTY", "title": "Party/Date"},
                    {"id": "OCCASION_OFFICE", "title": "Office"},
                    {"id": "OCCASION_CASUAL_VAC", "title": "Vacation / Casual"},
                ]}],
            )

        elif state == STATE_CATALOG_BUDGET:
            await self.wa.send_list(
                wa_id,
                "Still there? 💸 What's your budget?",
                "Choose",
                sections=[{"title": "Budget", "rows": [
                    {"id": "BUDGET_1K_2K", "title": "1k to 2k"},
                    {"id": "BUDGET_2K_3K", "title": "2k to 3k"},
                    {"id": "BUDGET_3K_4K", "title": "3k to 4k"},
                    {"id": "BUDGET_4K_5K", "title": "4k to 5k"},
                ]}],
            )

        else:
            # Unknown state — silently expire
            sess["reason"] = "timeout"
            self.logger.log_step(wa_id, "SESSION_TIMEOUT")
            self.logger.write(wa_id, sess)
            await self.store.delete(wa_id)

    # -------------------------
    # START menu handlers
    # -------------------------
    async def handle_start_button(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        if bid == "SHOP_CATALOG":
            await self._start_catalog(wa_id)
            return

        if bid == "DESIGN_YOUR_OWN":
            await self._start_design(wa_id)
            return

        if bid == "UPLOAD_DESIGN":
            await self._start_upload_design(wa_id)
            return

        await self.send_start_menu(wa_id)

    # -------------------------
    # SHOP FROM CATALOG (ONLY BUY FLOW ADDED)
    # -------------------------
    async def _start_catalog(self, wa_id: str) -> None:
        await self.store.set_fields(wa_id, {"state": STATE_CATALOG_OCCASION})
        await self.store.touch(wa_id)

        await self.wa.send_list(
            wa_id,
            "Nice 😍 — what are you shopping for?",
            "Choose",
            sections=[
                {
                    "title": "Occasion",
                    "rows": [
                        {"id": "OCCASION_PARTY", "title": "Party/Date"},
                        {"id": "OCCASION_OFFICE", "title": "Office"},
                        {"id": "OCCASION_CASUAL_VAC", "title": "Vacation / Casual"},
                    ],
                }
            ],
        )

    async def handle_catalog_occasion(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        occasion = {
            "OCCASION_PARTY": "Party/date",
            "OCCASION_OFFICE": "Office",
            # ✅ FIX: match your JSON convention "Vacation/Casual"
            "OCCASION_CASUAL_VAC": "Vacation/Casual",
        }.get(bid)

        if not occasion:
            await self._start_catalog(wa_id)
            return

        await self.store.set_fields(wa_id, {"occasion": occasion, "state": STATE_CATALOG_BUDGET})
        await self.store.touch(wa_id)

        await self.wa.send_list(
            wa_id,
            "What’s your budget looking like? 💸✨",
            "Choose",
            sections=[
                {
                    "title": "Budget",
                    "rows": [
                        {"id": "BUDGET_1K_2K", "title": "1k to 2k"},
                        {"id": "BUDGET_2K_3K", "title": "2k to 3k"},
                        {"id": "BUDGET_3K_4K", "title": "3k to 4k"},
                        {"id": "BUDGET_4K_5K", "title": "4k to 5k"},
                    ],
                }
            ],
        )

    async def handle_catalog_budget(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        budget = {
            "BUDGET_1K_2K": "1k-2k",
            "BUDGET_2K_3K": "2k-3k",
            "BUDGET_3K_4K": "3k-4k",
            "BUDGET_4K_5K": "4k-5k",
        }.get(bid)

        if not budget:
            await self._start_catalog(wa_id)
            return

        await self.store.set_fields(wa_id, {"budget": budget, "state": "CATALOG_RESULTS", "offset": "0"})
        await self.store.touch(wa_id)

        await self._send_catalog_batch(wa_id)

    def _match_item(self, item: Dict[str, Any], occasion: str, budget: str) -> bool:
        occ_list = item.get("occasion_ranked") or []
        budget_band = (item.get("budget_band") or "").strip()

        occ_ok = False

        # ✅ FIX: treat BOTH "Casual/Vacation" and "Vacation/Casual" as the same combined filter
        if occasion in {"Casual/Vacation", "Vacation/Casual"}:
            # accept either combined token OR individual tokens, depending on how your catalog.json is authored
            occ_ok = (
                ("Casual" in occ_list)
                or ("Vacation" in occ_list)
                or ("Casual/Vacation" in occ_list)
                or ("Vacation/Casual" in occ_list)
            )
        else:
            occ_ok = any(o.lower() == occasion.lower() for o in occ_list)

        budget_ok = budget_band.lower().replace(" ", "") == budget.lower().replace(" ", "")
        return occ_ok and budget_ok

    def _rank_items(self, items: List[Dict[str, Any]], occasion: str) -> List[Dict[str, Any]]:
        def score(it: Dict[str, Any]) -> int:
            occ_list = it.get("occasion_ranked") or []

            # ✅ FIX: rank combined occasion robustly (handles either combined token or individual tokens)
            if occasion in {"Casual/Vacation", "Vacation/Casual"}:
                idxs: List[int] = []

                # prefer combined token if present
                for key in ("Vacation/Casual", "Casual/Vacation"):
                    if key in occ_list:
                        idxs.append(occ_list.index(key))

                # else fall back to individual tokens
                for key in ("Vacation", "Casual"):
                    if key in occ_list:
                        idxs.append(occ_list.index(key))

                return min(idxs) if idxs else 999

            try:
                return occ_list.index(occasion)
            except Exception:
                return 999

        return sorted(items, key=score)

    async def _send_catalog_batch(self, wa_id: str) -> None:
        """
        REQUIRED OUTPUT (per item):
          1) Image
          2) Price text (original / discount / final)
          3) Material + description card
          4) Ready to buy? + ONLY Buy button

        After 3 items:
          - Show more + End Buy (if more exist)
          - End Buy only (if no more exist)
        """
        sess = await self.store.get(wa_id) or {}
        occasion = sess.get("occasion", "")
        budget = sess.get("budget", "")
        offset = int(sess.get("offset", "0"))

        all_items = self.catalog.load()
        filtered = [it for it in all_items if self._match_item(it, occasion, budget)]
        ranked = self._rank_items(filtered, occasion)

        ranked_ids = [it["image_id"] for it in ranked if "image_id" in it]
        await self.store.set_fields(wa_id, {"ranked_ids": ",".join(ranked_ids)})

        batch = ranked[offset : offset + 3]
        public_base_url = settings.PUBLIC_BASE_URL.rstrip("/")

        for it in batch:
            image_id = it["image_id"]
            image_url = f"{public_base_url}/static/catalog/{image_id}.png"

            # 1) Image (no pricing in caption; keep it clean)
            await self.wa.send_image(wa_id, image_url=image_url, caption="")

            # 2) Price text
            await self.wa.send_text(
                wa_id,
                f"₹{it['original_price']}  ➜  {it['discount_percentage']} OFF  ➜  ₹{it['final_price']}",
            )

            # 3) Material + description card
            material = (it.get("material") or "").strip()
            desc = (it.get("one_line_description") or "").strip()

            # Keep formatting stable even if material is empty
            if material:
                card = f"Material: {material}\n{desc}" if desc else f"Material: {material}"
            else:
                card = desc if desc else "Details coming soon ✨"

            await self.wa.send_text(wa_id, card)

            # 4) Ready to buy? + ONLY Buy button (NO End Buy here)
            await self.wa.send_buttons(
                wa_id,
                "Ready to buy? 💖",
                [
                    (f"CAT_BUY_{image_id}", "Buy"),
                ],
            )

        new_offset = offset + len(batch)
        await self.store.set_fields(wa_id, {"offset": str(new_offset)})

        # Nav buttons AFTER the 3 items
        if new_offset < len(ranked):
            await self.wa.send_buttons(
                wa_id,
                "Want more options? ✨",
                [
                    ("SHOW_MORE", "Show more"),
                    ("END_BUY", "End Buy"),
                ],
            )
        else:
            await self.wa.send_buttons(
                wa_id,
                "That’s all I have in this filter 💖",
                [
                    ("END_BUY", "End Buy"),
                ],
            )

    async def handle_catalog_nav(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        # ✅ CATALOG BUY HANDLER (unchanged)
        if bid.startswith("CAT_BUY_"):
            image_id = bid.replace("CAT_BUY_", "", 1).strip()
            await self.store.set_fields(
                wa_id,
                {
                    "state": STATE_BUY_NAME,
                    "buy_flow": "catalog",
                    "buy_image_id": image_id,
                },
            )
            await self.store.touch(wa_id)
            await self.wa.send_text(wa_id, "Plese tell us your name 🙂")
            return

        if bid == "SHOW_MORE":
            await self._send_catalog_batch(wa_id)
            return

        if bid == "END_BUY":
            sess = await self.store.get(wa_id) or {"wa_id": wa_id, "reason": "end_buy"}
            self.logger.write(wa_id, sess)

            await self.store.delete(wa_id)
            await self.send_start_menu(wa_id)
            return

        await self.send_start_menu(wa_id)

    # -------------------------
    # DESIGN YOUR OWN (UPDATED)
    # -------------------------
    async def _start_design(self, wa_id: str) -> None:
        # Quick cap check (non-blocking — real enforcement is at generation time)
        count = await self.store.get_gen_count(wa_id)
        if count >= MAX_GENERATIONS:
            await self._send_generation_limit_reached(wa_id)
            return

        await self.store.set_fields(
            wa_id,
            {
                "state": STATE_DESIGN_OCCASION,
                "design_occasion": "",
                "design_category": "",
                "design_fabric": "",
                "design_color": "",
                "generated_image": "",
                "flow": "design",
                "steps": "",
                # modify fields
                "design_mod_field": "",
                "design_mod_print": "",
                "design_mod_kv": "{}",
                "design_print_ref": "",
                # print library fields
                "design_print_id": "",
                "design_print_name": "",
                "print_return_to": "",
                "print_page": "0",
                "print_page_category": "",
                "nudge_count": "0",
            },
        )
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_DESIGN_OCCASION)

        await self.wa.send_list(
            wa_id,
            "Yesss 😍 Let’s design it.\nFirst — what’s the occasion?",
            "Choose",
            sections=[
                {
                    "title": "Occasion",
                    "rows": [
                        {"id": "D_OCC_PARTY", "title": "Party/Date"},
                        {"id": "D_OCC_OFFICE", "title": "Office"},
                        {"id": "D_OCC_CASUAL", "title": "Casual"},
                        {"id": "D_OCC_VACATION", "title": "Vacation"},
                    ],
                }
            ],
        )

    async def handle_design_occasion(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        occ = {
            "D_OCC_PARTY": "Party/Date",
            "D_OCC_OFFICE": "Office",
            "D_OCC_CASUAL": "Casual",
            "D_OCC_VACATION": "Vacation",
        }.get(bid)
        if not occ:
            await self._start_design(wa_id)
            return

        await self.store.set_fields(wa_id, {"design_occasion": occ, "state": STATE_DESIGN_CATEGORY})
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_DESIGN_CATEGORY)

        # ✅ UPDATED categories (10 total)
        await self.wa.send_list(
            wa_id,
            "Love it 💖 What are we designing?",
            "Choose",
            sections=[
                {
                    "title": "Category",
                    "rows": [
                        {"id": "D_CAT_DRESS", "title": "Dress"},
                        {"id": "D_CAT_TOP", "title": "Top"},
                        {"id": "D_CAT_SKIRT", "title": "Skirt"},
                        {"id": "D_CAT_PANTS", "title": "Pants"},
                        {"id": "D_CAT_JUMPSUIT", "title": "Jumpsuit"},
                        {"id": "D_CAT_SHIRTS", "title": "Shirts"},
                        {"id": "D_CAT_COORDS", "title": "Coord sets"},
                    ],
                }
            ],
        )

    async def handle_design_category(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        cat = {
            "D_CAT_DRESS": "dress",
            "D_CAT_TOP": "top",
            "D_CAT_SKIRT": "skirt",
            "D_CAT_PANTS": "pants",
            "D_CAT_JUMPSUIT": "jumpsuit",
            "D_CAT_JACKET": "jacket",
            "D_CAT_SHIRTS": "shirts",
            "D_CAT_COORDS": "coord sets",
            "D_CAT_BLOUSE": "blouse",
            "D_CAT_TSHIRTS": "t-shirts",
        }.get(bid)
        if not cat:
            await self._start_design(wa_id)
            return

        await self.store.set_fields(wa_id, {"design_category": cat, "state": STATE_DESIGN_FABRIC})
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_DESIGN_FABRIC)

        await self.wa.send_list(
            wa_id,
            "Quick one 😌 What fabric?",
            "Choose",
            sections=[
                {
                    "title": "Fabric",
                    "rows": [
                        {"id": "D_FAB_COTTON", "title": "Cotton"},
                        {"id": "D_FAB_VISCOSE_LINEN", "title": "Viscose linen"},
                        {"id": "D_FAB_COTTON_LINEN", "title": "Cotton linen"},
                        {"id": "D_FAB_RAYON", "title": "Rayon"},
                        {"id": "D_FAB_POLYCREPE", "title": "Polycrepe"},
                        {"id": "D_FAB_DENIM", "title": "Denim"},
                    ],
                }
            ],
        )

    async def handle_design_fabric_button(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        fab = {
            "D_FAB_COTTON": "cotton",
            "D_FAB_VISCOSE_LINEN": "viscose linen",
            "D_FAB_COTTON_LINEN": "cotton linen",
            "D_FAB_RAYON": "rayon",
            "D_FAB_POLYCREPE": "polycrepe",
            "D_FAB_DENIM": "denim",
        }.get(bid)
        if not fab:
            await self._start_design(wa_id)
            return

        await self.store.set_fields(wa_id, {"design_fabric": fab, "state": STATE_DESIGN_COLOR})
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_DESIGN_COLOR)

        await self.wa.send_list(
            wa_id,
            "Perfect ✨ What color?",
            "Choose",
            sections=[
                {
                    "title": "Color",
                    "rows": [
                        {"id": "D_CLR_BLACK", "title": "Black"},
                        {"id": "D_CLR_WHITE", "title": "White"},
                        {"id": "D_CLR_RED", "title": "Red"},
                        {"id": "D_CLR_NAVY", "title": "Navy Blue"},
                        {"id": "D_CLR_BEIGE", "title": "Beige"},
                        {"id": "D_CLR_PINK", "title": "Pink"},
                        {"id": "D_CLR_GREEN", "title": "Emerald Green"},
                        {"id": "D_CLR_MAROON", "title": "Maroon"},
                        {"id": "D_CLR_CUSTOM", "title": "Type my own color"},
                    ],
                }
            ],
        )

    async def handle_design_color_button(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        # "Type my own color" → ask for free-text input
        if bid == "D_CLR_CUSTOM":
            await self.store.set_fields(wa_id, {"state": STATE_DESIGN_COLOR_TEXT})
            await self.store.touch(wa_id)
            await self.wa.send_text(
                wa_id,
                "Type any color you like! 💖\n"
                "E.g. coral, sage green, dusty rose, olive, teal, burnt orange…",
            )
            return

        clr = {
            "D_CLR_BLACK": "black",
            "D_CLR_WHITE": "white",
            "D_CLR_RED": "red",
            "D_CLR_NAVY": "navy blue",
            "D_CLR_BEIGE": "beige",
            "D_CLR_PINK": "pink",
            "D_CLR_GREEN": "emerald green",
            "D_CLR_MAROON": "maroon",
        }.get(bid)
        if not clr:
            await self._start_design(wa_id)
            return

        await self.store.set_fields(wa_id, {"design_color": clr})
        await self.store.touch(wa_id)
        await self._start_print_selection(wa_id, return_to="generate")

    async def handle_design_color_text(self, wa_id: str, text: str) -> None:
        """Handle free-text color input from 'Type my own color'."""
        await self.store.touch(wa_id)
        color = text.strip()
        if not color:
            await self.wa.send_text(wa_id, "Please type a color 🙂")
            return

        await self.store.set_fields(wa_id, {"design_color": color})
        await self.store.touch(wa_id)
        await self._start_print_selection(wa_id, return_to="generate")

    # -------------------------
    # PRINT LIBRARY SELECTION
    # -------------------------
    async def _start_print_selection(self, wa_id: str, return_to: str = "generate") -> None:
        """
        Show print category list.
        return_to: 'generate' for initial flow, 'modify' for modify flow.
        """
        await self.store.set_fields(wa_id, {
            "state": STATE_DESIGN_PRINT_CATEGORY,
            "print_return_to": return_to,
            "print_page": "0",
            "print_page_category": "",
        })
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_DESIGN_PRINT_CATEGORY)

        await self.wa.send_list(
            wa_id,
            "Want a print on your outfit? 💖",
            "Choose",
            sections=[
                {
                    "title": "Print Style",
                    "rows": [
                        {"id": "PRINT_CAT_FLORAL", "title": "Floral"},
                        {"id": "PRINT_CAT_ABSTRACT", "title": "Abstract"},
                        {"id": "PRINT_CAT_GEOMETRIC", "title": "Geometric"},
                        {"id": "PRINT_CAT_ANIMAL_PRINT", "title": "Animal Print"},
                        {"id": "PRINT_CAT_IKAT", "title": "Ikat"},
                        {"id": "PRINT_CAT_PATCHWORK", "title": "Patchwork"},
                        {"id": "PRINT_CAT_POLKA_DOT", "title": "Polka Dot"},
                        {"id": "PRINT_CAT_TIE_DYE", "title": "Tie & Dye"},
                        {"id": "PRINT_CAT_TRADITIONAL_BLOCK", "title": "Block Print"},
                        {"id": "PRINT_CAT_NONE", "title": "No Print (Solid)"},
                    ],
                }
            ],
        )

    async def handle_design_print_category(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        cat_map = {
            "PRINT_CAT_FLORAL": "floral",
            "PRINT_CAT_ABSTRACT": "abstract",
            "PRINT_CAT_GEOMETRIC": "geometric",
            "PRINT_CAT_ANIMAL_PRINT": "animal_print",
            "PRINT_CAT_IKAT": "ikat",
            "PRINT_CAT_PATCHWORK": "patchwork",
            "PRINT_CAT_POLKA_DOT": "polka_dot",
            "PRINT_CAT_TIE_DYE": "tie_dye",
            "PRINT_CAT_TRADITIONAL_BLOCK": "traditional_block",
        }

        if bid == "PRINT_CAT_NONE":
            await self.store.set_fields(wa_id, {"design_print_id": ""})
            sess = await self.store.get(wa_id) or {}
            return_to = sess.get("print_return_to", "generate")
            if return_to == "modify":
                # Cancel — go back to design post screen
                await self._send_design_post(wa_id)
            else:
                await self._generate_design(wa_id)
            return

        category = cat_map.get(bid)
        if not category:
            await self._start_print_selection(wa_id)
            return

        # Store the category and reset page to 0
        await self.store.set_fields(wa_id, {
            "print_page_category": category,
            "print_page": "0",
        })

        await self._send_print_page(wa_id, category, page=0)

    async def _send_print_page(self, wa_id: str, category: str, page: int) -> None:
        """Send a paginated collage + list picker for prints in the given category."""
        page_prints, has_more = self.print_service.get_page(category, page)

        if not page_prints:
            await self.wa.send_text(wa_id, "No prints found in that category. Let's try again.")
            await self._start_print_selection(wa_id)
            return

        # Calculate start number for continuous numbering across pages
        start_number = page * 6 + 1

        # Generate and send collage
        collage_path = self.print_service.generate_collage(
            page_prints, wa_id=wa_id, start_number=start_number,
        )
        public_base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        collage_url = f"{public_base_url}{collage_path}"

        pretty_cat = category.replace("_", " ").title()
        page_label = f" (Page {page + 1})" if page > 0 else ""
        await self.wa.send_image(
            wa_id, image_url=collage_url,
            caption=f"{pretty_cat} prints{page_label} 💖",
        )

        # Store state and page info
        await self.store.set_fields(wa_id, {
            "state": STATE_DESIGN_PRINT_PICK,
            "print_page": str(page),
            "print_page_category": category,
        })
        await self.store.touch(wa_id)

        # Build list rows — numbered continuously
        rows = []
        for i, p in enumerate(page_prints):
            num = start_number + i
            rows.append({
                "id": f"PRINT_PICK_{p['id'].upper()}",
                "title": f"{num}. {p['name']}",
            })

        # Navigation rows
        if has_more:
            rows.append({"id": "PRINT_PICK_MORE", "title": "More Prints ➡️"})
        if page > 0:
            rows.append({"id": "PRINT_PICK_BACK", "title": "⬅️ Previous Prints"})

        # Always offer "No Print" as an escape hatch
        rows.append({"id": "PRINT_PICK_NONE", "title": "No Print (Solid)"})

        await self.wa.send_list(
            wa_id,
            "Pick a print 💖",
            "Choose",
            sections=[{"title": "Prints", "rows": rows}],
        )

    async def handle_design_print_pick(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        sess = await self.store.get(wa_id) or {}
        return_to = sess.get("print_return_to", "generate")

        # --- PAGINATION: "Show More" ---
        if bid == "PRINT_PICK_MORE":
            category = sess.get("print_page_category", "")
            current_page = int(sess.get("print_page", "0"))
            if category:
                await self._send_print_page(wa_id, category, page=current_page + 1)
            else:
                await self._start_print_selection(wa_id)
            return

        # --- PAGINATION: "Previous" ---
        if bid == "PRINT_PICK_BACK":
            category = sess.get("print_page_category", "")
            current_page = int(sess.get("print_page", "0"))
            new_page = max(0, current_page - 1)
            if category:
                await self._send_print_page(wa_id, category, page=new_page)
            else:
                await self._start_print_selection(wa_id)
            return

        if bid == "PRINT_PICK_NONE":
            await self.store.set_fields(wa_id, {"design_print_id": ""})
            if return_to == "modify":
                await self._send_design_post(wa_id)
            else:
                await self._generate_design(wa_id)
            return

        if not bid.startswith("PRINT_PICK_"):
            await self._start_print_selection(wa_id)
            return

        print_id = bid.replace("PRINT_PICK_", "", 1).strip().lower()

        # Validate the print exists
        print_entry = self.print_service.get_by_id(print_id)
        if not print_entry:
            await self.wa.send_text(wa_id, "Couldn't find that print. Let's try again.")
            await self._start_print_selection(wa_id)
            return

        await self.store.set_fields(wa_id, {
            "design_print_id": print_id,
            "design_print_name": print_entry.get("name", ""),
        })

        if return_to == "modify":
            # Set up for _regenerate_design_with_modifications
            await self.store.set_fields(wa_id, {
                "design_mod_print": f"local:{print_id}",
                "design_mod_field": "",
                "design_mod_kv": "{}",
            })
            await self._regenerate_design_with_modifications(wa_id)
        else:
            await self._generate_design(wa_id)

    async def _send_generation_limit_reached(self, wa_id: str) -> None:
        self.logger.log_step(wa_id, "GEN_LIMIT_REACHED")
        await self.wa.send_text(
            wa_id,
            "You've used all your free designs! 💖\n\n"
            "Love what you see? Book any design for just ₹199 👇\n"
            "https://rzp.io/rzp/9uvSpR0\n\n"
            "₹199 books your design — rest on delivery ✨",
        )
        await self.store.set_fields(wa_id, {"state": STATE_START})
        await self.store.touch(wa_id)

    async def _send_modification_limit_reached(self, wa_id: str) -> None:
        self.logger.log_step(wa_id, "MOD_LIMIT_REACHED")
        await self.wa.send_text(
            wa_id,
            "You've reached the modification limit for this design 💖\n\n"
            "Tap *Design Another* to start a fresh design, or *Buy now* to book this one! ✨",
        )
        await self.store.set_fields(wa_id, {"state": STATE_DESIGN_POST})
        await self.store.touch(wa_id)

    async def _generate_design(self, wa_id: str) -> None:
        # Atomic generation cap: reserve a slot or reject
        reserved = await self.store.try_reserve_generation(wa_id, MAX_GENERATIONS)
        if not reserved:
            await self._send_generation_limit_reached(wa_id)
            return

        sess = await self.store.get(wa_id) or {}
        brief = DesignBrief(
            occasion=sess.get("design_occasion", ""),
            budget="",
            category=sess.get("design_category", ""),
            fabric=sess.get("design_fabric", ""),
            color=sess.get("design_color", ""),
            notes="",
            size="",
        )

        await self.wa.send_text(wa_id, "Okayyy 😍 Designing now… give me a sec ✨")

        # Load print bytes from library if a print was selected
        print_id = (sess.get("design_print_id") or "").strip()
        pattern_bytes = None
        if print_id:
            entry = self.print_service.get_by_id(print_id)
            if entry:
                pattern_bytes = self.print_service.get_print_image_bytes(entry)

        try:
            rel_image_path = await self.gemini.generate_image_only(
                wa_id=wa_id, brief=brief, pattern_image_bytes=pattern_bytes,
            )
        except Exception as e:
            print(f"[generate_design] FAILED wa_id={wa_id} error={repr(e)}")
            await self.wa.send_text(wa_id, ERROR_MSG_HIGH_VOLUME)
            return

        # New design created — reset modification counter
        await self.store.reset_mod_count(wa_id)

        await self.store.set_fields(
            wa_id,
            {
                "generated_image": rel_image_path,
                "generated_image_front": rel_image_path,
                "state": STATE_DESIGN_POST,
                "design_mod_field": "",
                "design_mod_print": "",
                "design_mod_kv": "{}",
                "design_print_ref": f"local:{print_id}" if print_id else "",
            },
        )
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_DESIGN_POST)

        await self._send_design_post(wa_id)

    async def _send_design_post(self, wa_id: str) -> None:
        sess = await self.store.get(wa_id) or {}
        rel_image_path = sess.get("generated_image", "")

        public_base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        image_url = f"{public_base_url}{rel_image_path}" if rel_image_path else ""

        if image_url:
            await self.wa.send_image(wa_id, image_url=image_url, caption="Here's your design visual 💖")
        else:
            await self.wa.send_text(wa_id, "Here's your design visual 💖")

        # Build counter info line
        designs_used = await self.store.get_gen_count(wa_id)
        mods_used = await self.store.get_mod_count(wa_id)
        designs_left = MAX_GENERATIONS - designs_used
        mods_left = MAX_MODIFICATIONS - mods_used

        body = f"What do you want to do? ✨\n\n{designs_left} designs remaining · {mods_left} modifications left"

        await self.wa.send_buttons(
            wa_id,
            body,
            [
                ("DESIGN_MODIFY", "Modify"),
                ("DESIGN_ANOTHER", "Design Another"),
                ("DESIGN_BUY_NOW", "Buy now"),
            ],
        )

    async def handle_design_post_button(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        if bid == "DESIGN_ANOTHER":
            self.logger.log_step(wa_id, "DESIGN_ANOTHER")
            await self._start_design(wa_id)
            return

        if bid == "DESIGN_BUY_NOW":
            self.logger.log_step(wa_id, "BUY_TAPPED")
            await self._send_size_selection(wa_id, intro="Amazing 💖 What's your size?")
            return

        if bid == "DESIGN_MODIFY":
            self.logger.log_step(wa_id, "DESIGN_MODIFY")
            await self.store.set_fields(
                wa_id,
                {
                    "state": STATE_DESIGN_MODIFY_MENU,
                    "design_mod_field": "",
                    "design_mod_print": "",
                    "design_mod_kv": "{}",
                },
            )
            await self.store.touch(wa_id)
            await self._send_design_modify_menu(wa_id)
            return

        await self.send_start_menu(wa_id)

    # -------------------------
    # DESIGN MODIFY FLOW (UPDATED: conditional list + preset choices)
    # -------------------------
    def _safe_load_kv(self, sess: Dict[str, Any]) -> Dict[str, str]:
        try:
            raw = (sess.get("design_mod_kv") or "{}").strip()
            obj = json.loads(raw) if raw else {}
            if isinstance(obj, dict):
                return {str(k): str(v) for k, v in obj.items() if v is not None}
            return {}
        except Exception:
            return {}

    async def _save_kv(self, wa_id: str, kv: Dict[str, str]) -> None:
        await self.store.set_fields(wa_id, {"design_mod_kv": json.dumps(kv, ensure_ascii=False)})

    def _category_key(self, cat: str) -> str:
        return (cat or "").strip().lower()

    def _size_chart_text(self, cat: str) -> str:
        """Return the relevant size chart text for the given garment category."""
        c = self._category_key(cat)

        dress_chart = (
            "👗 *Dress Size Chart*\n"
            "\n"
            "*XS*\n"
            "Bust 82 cm / 32.3 in\n"
            "Waist 62 cm / 24.4 in\n"
            "Hips 90 cm / 35.4 in\n"
            "\n"
            "*S*\n"
            "Bust 86.5 cm / 34 in\n"
            "Waist 66 cm / 26 in\n"
            "Hips 94 cm / 37 in\n"
            "\n"
            "*M*\n"
            "Bust 90 cm / 35.4 in\n"
            "Waist 70 cm / 27.6 in\n"
            "Hips 98 cm / 38.6 in\n"
            "\n"
            "*L*\n"
            "Bust 96 cm / 37.8 in\n"
            "Waist 76 cm / 29.9 in\n"
            "Hips 104 cm / 40.9 in\n"
            "\n"
            "*XL*\n"
            "Bust 102 cm / 40.2 in\n"
            "Waist 82 cm / 32.3 in\n"
            "Hips 110 cm / 43.3 in\n"
            "\n"
            "*XXL*\n"
            "Bust 108 cm / 42.5 in\n"
            "Waist 88 cm / 34.6 in\n"
            "Hips 116 cm / 45.7 in"
        )

        top_chart = (
            "👚 *Top Size Chart*\n"
            "\n"
            "*XS*\n"
            "Bust 82 cm / 32.3 in\n"
            "Waist 62 cm / 24.4 in\n"
            "\n"
            "*S*\n"
            "Bust 86 cm / 33.9 in\n"
            "Waist 66 cm / 26 in\n"
            "\n"
            "*M*\n"
            "Bust 90 cm / 35.4 in\n"
            "Waist 70 cm / 27.6 in\n"
            "\n"
            "*L*\n"
            "Bust 96 cm / 37.8 in\n"
            "Waist 76 cm / 29.9 in\n"
            "\n"
            "*XL*\n"
            "Bust 102 cm / 40.2 in\n"
            "Waist 82 cm / 32.3 in\n"
            "\n"
            "*XXL*\n"
            "Bust 108 cm / 42.5 in\n"
            "Waist 88 cm / 34.6 in"
        )

        bottom_chart = (
            "👖 *Bottom Size Chart*\n"
            "\n"
            "*XS*\n"
            "Waist 62 cm / 24.4 in\n"
            "Hips 90 cm / 35.4 in\n"
            "\n"
            "*S*\n"
            "Waist 66 cm / 26 in\n"
            "Hips 94 cm / 37 in\n"
            "\n"
            "*M*\n"
            "Waist 70 cm / 27.6 in\n"
            "Hips 98 cm / 38.6 in\n"
            "\n"
            "*L*\n"
            "Waist 76 cm / 29.9 in\n"
            "Hips 104 cm / 40.9 in\n"
            "\n"
            "*XL*\n"
            "Waist 82 cm / 32.3 in\n"
            "Hips 110 cm / 43.3 in\n"
            "\n"
            "*XXL*\n"
            "Waist 88 cm / 34.6 in\n"
            "Hips 116 cm / 45.7 in"
        )

        if c in {"dress", "jumpsuit"}:
            return dress_chart
        if c in {"top", "blouse", "shirts", "t-shirts", "jacket"}:
            return top_chart
        if c in {"skirt", "pants"}:
            return bottom_chart
        if c == "coord sets":
            return f"{top_chart}\n\n{bottom_chart}"
        # fallback
        return dress_chart

    async def _send_size_selection(self, wa_id: str, intro: str = "Amazing 💖 What's your size?") -> None:
        """Send the size chart for the user's category, then the size picker list."""
        sess = await self.store.get(wa_id) or {}
        cat = (sess.get("design_category") or "").strip()

        if cat:
            chart = self._size_chart_text(cat)
            await self.wa.send_text(wa_id, chart)

        await self.store.set_fields(wa_id, {"state": STATE_BUY_SIZE})
        await self.store.touch(wa_id)
        await self.wa.send_list(
            wa_id,
            intro,
            "Choose",
            sections=[
                {
                    "title": "Size",
                    "rows": [
                        {"id": "SIZE_XS", "title": "XS"},
                        {"id": "SIZE_S", "title": "S"},
                        {"id": "SIZE_M", "title": "M"},
                        {"id": "SIZE_L", "title": "L"},
                        {"id": "SIZE_XL", "title": "XL"},
                        {"id": "SIZE_XXL", "title": "XXL"},
                    ],
                }
            ],
        )

    def _modify_fields_for_category(self, cat: str) -> List[Tuple[str, str]]:
        """
        Returns [(field_key, field_title)] for the conditional menu.
        Color is always present.
        """
        c = self._category_key(cat)

        base = [("color", "Color")]

        if c == "dress":
            base += [
                ("length", "Length"),
                ("sleeves", "Sleeves"),
                ("neckline", "Neckline"),
                ("waist_fit", "Waist fit"),
                ("silhouette", "Silhouette"),
                ("hem_shape", "Hem shape"),
                ("back_detail", "Back detail"),
            ]
        elif c == "top":
            base += [
                ("length", "Length"),
                ("sleeves", "Sleeves"),
                ("neckline", "Neckline"),
                ("fit", "Fit"),
                ("hem", "Hem"),
                ("back_detail", "Back detail"),
            ]
        elif c == "skirt":
            base += [
                ("length", "Length"),
                ("waist_rise", "Waist rise"),
                ("silhouette", "Silhouette"),
                ("slit", "Slit"),
                ("hem_shape", "Hem shape"),
            ]
        elif c == "pants":
            base += [
                ("length", "Length"),
                ("fit", "Fit"),
                ("rise", "Rise"),
                ("waistband_style", "Waistband style"),
                ("leg_opening", "Leg opening"),
            ]
        elif c == "jumpsuit":
            base += [
                ("length", "Length"),
                ("sleeves", "Sleeves"),
                ("neckline", "Neckline"),
                ("fit", "Fit"),
                ("waist_definition", "Waist definition"),
                ("leg_fit", "Leg fit"),
                ("back_detail", "Back detail"),
            ]
        elif c == "jacket":
            base += [
                ("length", "Length"),
                ("fit", "Fit"),
                ("collar_neck", "Collar/neck style"),
                ("sleeves", "Sleeves"),
                ("closure", "Closure"),
                ("pocket_style", "Pocket style"),
            ]
        elif c == "shirts":
            base += [
                ("sleeves", "Sleeves"),
                ("collar_type", "Collar type"),
                ("fit", "Fit"),
                ("length", "Length"),
                ("cuffs", "Cuffs"),
                ("hem", "Hem"),
            ]
        elif c == "coord sets":
            base += [
                ("top_type", "Top type"),
                ("top_sleeves", "Top sleeves"),
                ("top_neckline", "Top neckline"),
                ("top_length", "Top length"),
                ("bottom_type", "Bottom type"),
                ("bottom_length", "Bottom length"),
                ("bottom_fit", "Bottom fit"),
                ("color_top", "Top color"),
                ("color_bottom", "Bottom color"),
            ]
            # Note: For coord sets, we keep both Top color & Bottom color.
            # The generic "Color" still exists, but we will not show it to avoid confusion.
            base = [x for x in base if x[0] != "color"]
        elif c == "blouse":
            base += [
                ("sleeves", "Sleeves"),
                ("neckline", "Neckline"),
                ("fit", "Fit"),
                ("length", "Length"),
                ("front_detail", "Front detail"),
                ("back_detail", "Back detail"),
            ]
        elif c == "t-shirts":
            base += [
                ("sleeve_length", "Sleeve length"),
                ("neckline", "Neckline"),
                ("fit", "Fit"),
                ("length", "Length"),
                ("hem", "Hem"),
            ]
        else:
            # unknown -> keep safe minimal
            base += [("length", "Length"), ("fit", "Fit"), ("neckline", "Neckline"), ("sleeves", "Sleeves")]

        return base

    def _field_options(self, cat: str, field: str) -> List[Tuple[str, str]]:
        """
        Returns [(option_value, option_title)] for preset lists.
        For "color"/"color_top"/"color_bottom" we keep it free-text (handled separately).
        """
        c = self._category_key(cat)
        f = (field or "").strip().lower()

        # Common presets
        if f == "sleeves":
            return [
                ("sleeveless", "Sleeveless"),
                ("cap", "Cap sleeves"),
                ("short", "Short sleeves"),
                ("three_quarter", "3/4 sleeves"),
                ("long", "Long sleeves"),
                ("puff", "Puff sleeves"),
            ]
        if f == "neckline":
            return [
                ("round", "Round"),
                ("v", "V-neck"),
                ("square", "Square"),
                ("halter", "Halter"),
                ("high", "High neck"),
                ("off_shoulder", "Off-shoulder"),
            ]
        if f == "fit":
            # category-specific fit set
            if c in {"top", "shirts", "t-shirts"}:
                return [("slim", "Slim"), ("regular", "Regular"), ("oversized", "Oversized")]
            if c in {"jumpsuit", "blouse"}:
                return [("tailored", "Tailored"), ("relaxed", "Relaxed")]
            if c == "jacket":
                return [("structured", "Structured"), ("relaxed", "Relaxed"), ("oversized", "Oversized")]
            if c == "pants":
                return [("skinny", "Skinny"), ("straight", "Straight"), ("wide", "Wide"), ("bootcut", "Bootcut")]
            return [("regular", "Regular"), ("tailored", "Tailored"), ("relaxed", "Relaxed")]

        # Per-category fields
        if c == "dress":
            if f == "length":
                return [("mini", "Mini"), ("midi", "Midi"), ("maxi", "Maxi")]
            if f == "waist_fit":
                return [("cinched", "Cinched"), ("straight", "Straight"), ("empire", "Empire")]
            if f == "silhouette":
                return [("a_line", "A-line"), ("bodycon", "Bodycon"), ("wrap", "Wrap"), ("shift", "Shift")]
            if f == "hem_shape":
                return [("straight", "Straight"), ("high_low", "High-low"), ("slit", "Slit")]
            if f == "back_detail":
                return [("open_back", "Open-back"), ("zip", "Zip"), ("tie", "Tie")]

        if c == "top":
            if f == "length":
                return [("crop", "Crop"), ("regular", "Regular"), ("shirt", "Shirt")]
            if f == "hem":
                return [("straight", "Straight"), ("curved", "Curved"), ("peplum", "Peplum")]
            if f == "back_detail":
                return [("tie", "Tie"), ("cutout", "Cutout"), ("zip", "Zip")]

        if c == "skirt":
            if f == "length":
                return [("mini", "Mini"), ("midi", "Midi"), ("maxi", "Maxi")]
            if f == "waist_rise":
                return [("high", "High"), ("mid", "Mid"), ("low", "Low")]
            if f == "silhouette":
                return [("pencil", "Pencil"), ("a_line", "A-line"), ("pleated", "Pleated")]
            if f == "slit":
                return [("none", "None"), ("side", "Side"), ("front", "Front"), ("back", "Back"), ("front_and_back", "Front & Back")]
            if f == "hem_shape":
                return [("straight", "Straight"), ("asym", "Asymmetric")]

        if c == "pants":
            if f == "length":
                return [("full", "Full length"), ("ankle", "Ankle"), ("cropped", "Cropped")]
            if f == "rise":
                return [("high", "High"), ("mid", "Mid"), ("low", "Low")]
            if f == "waistband_style":
                return [("elastic", "Elastic"), ("button", "Button"), ("pleated", "Pleated")]
            if f == "leg_opening":
                return [("tapered", "Tapered"), ("flared", "Flared")]

        if c == "jumpsuit":
            if f == "length":
                return [("full", "Full length"), ("cropped", "Cropped")]
            if f == "waist_definition":
                return [("belted", "Belted"), ("cinched", "Cinched"), ("straight", "Straight")]
            if f == "leg_fit":
                return [("wide", "Wide"), ("straight", "Straight"), ("tapered", "Tapered")]
            if f == "back_detail":
                return [("zip", "Zip"), ("open_back", "Open-back"), ("tie", "Tie")]

        if c == "jacket":
            if f == "length":
                return [("cropped", "Cropped"), ("waist", "Waist"), ("hip", "Hip"), ("longline", "Longline")]
            if f == "collar_neck":
                return [("lapel", "Lapel"), ("mandarin", "Mandarin"), ("hooded", "Hooded")]
            if f == "closure":
                return [("zip", "Zip"), ("buttons", "Buttons"), ("open_front", "Open-front")]
            if f == "pocket_style":
                return [("none", "None"), ("patch", "Patch"), ("zip", "Zip")]

        if c == "shirts":
            if f == "collar_type":
                return [("classic", "Classic"), ("mandarin", "Mandarin"), ("spread", "Spread")]
            if f == "length":
                return [("tucked", "Tucked"), ("untucked", "Untucked"), ("longline", "Longline")]
            if f == "cuffs":
                return [("buttoned", "Buttoned"), ("elastic", "Elastic")]
            if f == "hem":
                return [("straight", "Straight"), ("curved", "Curved")]

        if c == "coord sets":
            if f == "top_type":
                return [("shirt", "Shirt"), ("crop", "Crop"), ("tee", "Tee"), ("blouse", "Blouse")]
            if f == "top_sleeves":
                return [("sleeveless", "Sleeveless"), ("short", "Short"), ("three_quarter", "3/4"), ("long", "Long")]
            if f == "top_neckline":
                return [("crew", "Crew"), ("v", "V-neck"), ("square", "Square"), ("halter", "Halter")]
            if f == "top_length":
                return [("crop", "Crop"), ("waist", "Waist"), ("hip", "Hip")]
            if f == "bottom_type":
                return [("pants", "Pants"), ("skirt", "Skirt"), ("shorts", "Shorts")]
            if f == "bottom_length":
                return [("short", "Short"), ("midi", "Midi"), ("full", "Full")]
            if f == "bottom_fit":
                return [("wide", "Wide"), ("straight", "Straight"), ("pencil", "Pencil"), ("a_line", "A-line")]

        if c == "blouse":
            if f == "sleeves":
                return [("puff", "Puff"), ("bell", "Bell"), ("straight", "Straight")]
            if f == "fit":
                return [("tailored", "Tailored"), ("relaxed", "Relaxed")]
            if f == "length":
                return [("crop", "Crop"), ("waist", "Waist"), ("hip", "Hip")]
            if f == "front_detail":
                return [("tie", "Tie"), ("pleats", "Pleats"), ("buttons", "Buttons")]
            if f == "back_detail":
                return [("zip", "Zip"), ("tie", "Tie"), ("cutout", "Cutout")]

        if c == "t-shirts":
            if f == "sleeve_length":
                return [("cap", "Cap"), ("half", "Half"), ("long", "Long")]
            if f == "fit":
                return [("slim", "Slim"), ("regular", "Regular"), ("oversized", "Oversized")]
            if f == "length":
                return [("crop", "Crop"), ("regular", "Regular"), ("longline", "Longline")]
            if f == "hem":
                return [("straight", "Straight"), ("curved", "Curved")]

        # Fallback presets
        if f == "length":
            return [("shorter", "Shorter"), ("longer", "Longer")]

        return []

    def _pretty_field_label(self, field: str) -> str:
        m = {
            "length": "length",
            "sleeves": "sleeves",
            "neckline": "neckline",
            "waist_fit": "waist fit",
            "waist_rise": "waist rise",
            "silhouette": "silhouette",
            "hem_shape": "hem shape",
            "hem": "hem",
            "back_detail": "back detail",
            "front_detail": "front detail",
            "rise": "rise",
            "waistband_style": "waistband style",
            "leg_opening": "leg opening",
            "waist_definition": "waist definition",
            "leg_fit": "leg fit",
            "collar_neck": "collar/neck style",
            "collar_type": "collar type",
            "cuffs": "cuffs",
            "pocket_style": "pocket style",
            "closure": "closure",
            "top_type": "top type",
            "top_sleeves": "top sleeves",
            "top_neckline": "top neckline",
            "top_length": "top length",
            "bottom_type": "bottom type",
            "bottom_length": "bottom length",
            "bottom_fit": "bottom fit",
            "sleeve_length": "sleeve length",
            "color": "color",
            "color_top": "top color",
            "color_bottom": "bottom color",
        }
        return m.get(field, field)

    async def _send_design_modify_menu(self, wa_id: str) -> None:
        await self.store.set_fields(wa_id, {"state": STATE_DESIGN_MODIFY_MENU})
        await self.store.touch(wa_id)

        sess = await self.store.get(wa_id) or {}
        cat = (sess.get("design_category") or "").strip()

        fields = self._modify_fields_for_category(cat)
        rows = []
        for fkey, ftitle in fields:
            rows.append({"id": f"D_CHG_{fkey.upper()}", "title": ftitle})

        # WhatsApp list row limit is 10 per section; our per-category designs respect this.
        await self.wa.send_list(
            wa_id,
            "What are we changing? 💖✨",
            "Choose",
            sections=[
                {
                    "title": "Modify",
                    "rows": rows,
                }
            ],
        )

    async def handle_design_modify_menu(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        sess = await self.store.get(wa_id) or {}
        cat = (sess.get("design_category") or "").strip()

        if not bid or not bid.startswith("D_CHG_"):
            await self._send_design_modify_menu(wa_id)
            return

        field = bid.replace("D_CHG_", "", 1).strip().lower()
        field = field.lower()

        # Normalize (ids are uppercase)
        field = field.lower()

        # Color stays free-text (better than presets)
        if field in {"color", "color_top", "color_bottom"}:
            await self.store.set_fields(wa_id, {"state": STATE_DESIGN_MODIFY_FIELD_TEXT, "design_mod_field": field})
            await self.store.touch(wa_id)

            if field == "color_top":
                await self.wa.send_text(wa_id, "What color for the TOP? 💖")
            elif field == "color_bottom":
                await self.wa.send_text(wa_id, "What color for the BOTTOM? 💖")
            else:
                await self.wa.send_text(wa_id, "What color are you thinking? 💖")
            return

        options = self._field_options(cat, field)
        if not options:
            # If we don't have presets for this field, fall back to text input safely
            await self.store.set_fields(wa_id, {"state": STATE_DESIGN_MODIFY_FIELD_TEXT, "design_mod_field": field})
            await self.store.touch(wa_id)
            await self.wa.send_text(wa_id, f"How would you like to change the {self._pretty_field_label(field)}?")
            return

        # preset list
        await self.store.set_fields(wa_id, {"state": STATE_DESIGN_MODIFY_FIELD_CHOICE, "design_mod_field": field})
        await self.store.touch(wa_id)

        rows = [{"id": f"D_OPT_{field.upper()}__{oval}", "title": otitle} for (oval, otitle) in options][:10]

        await self.wa.send_list(
            wa_id,
            f"Choose the {self._pretty_field_label(field)} 💖",
            "Choose",
            sections=[{"title": "Options", "rows": rows}],
        )

    async def handle_design_modify_field_text(self, wa_id: str, text: str) -> None:
        await self.store.touch(wa_id)
        value = text.strip()
        if not value:
            await self.wa.send_text(wa_id, "Please type the change 🙂")
            return

        sess = await self.store.get(wa_id) or {}
        field = (sess.get("design_mod_field") or "").strip().lower()
        if not field:
            await self._send_design_modify_menu(wa_id)
            return

        # Store into KV for prompt conversion
        kv = self._safe_load_kv(sess)
        kv[field] = value
        await self._save_kv(wa_id, kv)

        await self._regenerate_design_with_modifications(wa_id)

    async def handle_design_modify_field_choice(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)
        sess = await self.store.get(wa_id) or {}
        field = (sess.get("design_mod_field") or "").strip().lower()
        if not field:
            await self._send_design_modify_menu(wa_id)
            return

        if not bid or not bid.startswith(f"D_OPT_{field.upper()}__"):
            await self._send_design_modify_menu(wa_id)
            return

        value = bid.split("__", 1)[-1].strip()
        if not value:
            await self._send_design_modify_menu(wa_id)
            return

        # store in KV
        kv = self._safe_load_kv(sess)
        kv[field] = value
        await self._save_kv(wa_id, kv)

        await self._regenerate_design_with_modifications(wa_id)

    async def handle_design_modify_print_image(self, wa_id: str, pattern_ref: str) -> None:
        """
        pattern_ref: keep it generic so webhook can pass:
          - media id, or
          - a link/url, or
          - any identifier you decide
        We store it as-is and use it for image editing (downloaded into bytes).
        """
        await self.store.touch(wa_id)
        if not pattern_ref:
            await self.wa.send_text(wa_id, "Please upload a clear pattern image 🙂")
            return

        await self.store.set_fields(
            wa_id,
            {
                "design_mod_print": pattern_ref,
                "design_mod_field": "",
            },
        )
        await self.store.touch(wa_id)

        await self._regenerate_design_with_modifications(wa_id)

    async def _download_pattern_bytes_if_possible(self, media_id: str) -> Optional[bytes]:
        """
        Best-effort: load pattern bytes from local print library or WhatsApp media.
        Handles:
          - "local:<print_id>" -> loads from print library on disk
          - WhatsApp media ID or URL -> downloads via WhatsAppClient
        """
        media_id = (media_id or "").strip()
        if not media_id:
            return None

        # Handle local print library references
        if media_id.startswith("local:"):
            print_id = media_id[len("local:"):]
            entry = self.print_service.get_by_id(print_id)
            if entry:
                try:
                    return self.print_service.get_print_image_bytes(entry)
                except Exception:
                    return None
            return None

        fn = getattr(self.wa, "download_media_bytes", None)
        if not fn:
            return None

        try:
            return await fn(media_id)
        except Exception:
            return None

    def _kv_to_precise_modifications(self, category: str, kv: Dict[str, str]) -> Dict[str, str]:
        """
        Convert preset selections into precise prompt instructions.
        We return a dict (same shape as before) that Gemini edit prompt will include.
        """
        c = self._category_key(category)
        out: Dict[str, str] = {}

        for k, v in (kv or {}).items():
            kk = (k or "").strip().lower()
            vv = (v or "").strip()

            if not vv:
                continue

            # handle colors — be explicit about which part for multi-part garments
            if kk == "color":
                if c == "jumpsuit":
                    out[kk] = f"Change the color of the ENTIRE jumpsuit (both top and bottom) to {vv}."
                elif c == "coord sets":
                    out[kk] = f"Change the color of BOTH pieces of the coord set to {vv}."
                else:
                    out[kk] = f"Set color to {vv}."
                continue
            if kk == "color_top":
                out[kk] = f"Change the TOP piece color to {vv}. Keep the bottom piece color unchanged."
                continue
            if kk == "color_bottom":
                out[kk] = f"Change the BOTTOM piece color to {vv}. Keep the top piece color unchanged."
                continue

            # general phrasing: "Set <field> to <value>"
            label = self._pretty_field_label(kk)

            # add a bit more precision for key fields
            if kk == "length" and c in {"dress", "skirt"}:
                if vv == "mini":
                    out[kk] = f"CRITICAL CHANGE: Shorten the {c} to MINI length — hemline must end at mid-thigh, well above the knee. Remove all fabric below mid-thigh. The model's legs from mid-thigh down must be fully visible."
                elif vv == "midi":
                    out[kk] = f"CRITICAL CHANGE: Adjust the {c} to MIDI length — hemline must end below the knee, around mid-calf. The model's lower legs (below mid-calf) must be visible."
                elif vv == "maxi":
                    out[kk] = f"CRITICAL CHANGE: Extend the {c} to MAXI length — hemline must reach the ankles or floor. No leg should be visible below the garment."
                else:
                    out[kk] = f"CRITICAL CHANGE: Set {c} length to {vv}."
                continue

            if kk == "length" and c == "pants":
                if vv == "cropped":
                    out[kk] = "CRITICAL CHANGE: Convert to cropped pants — hemline must end at mid-calf, clearly above the ankle. The model's lower legs from mid-calf down must be visible."
                elif vv == "ankle":
                    out[kk] = "Adjust pants length to ankle-length; hem visible; keep everything else identical."
                else:
                    out[kk] = "Set pants to full-length; hem visible; keep everything else identical."
                continue

            if kk == "length" and c == "jumpsuit":
                if vv == "cropped":
                    out[kk] = "CRITICAL CHANGE: Convert to a cropped jumpsuit — legs must end at mid-calf, clearly above the ankle. The model's lower legs from mid-calf down must be fully visible."
                else:
                    out[kk] = "CRITICAL CHANGE: Convert to full-length jumpsuit reaching the ankles."
                continue

            if kk == "length" and c == "jacket":
                if vv == "cropped":
                    out[kk] = "CRITICAL CHANGE: Shorten the jacket to CROPPED length — hemline must end well above the waist, showing the midriff or waistline clearly. It must be visibly shorter than a waist-length jacket."
                elif vv == "waist":
                    out[kk] = "CRITICAL CHANGE: Adjust the jacket to WAIST length — hemline must end exactly at the waist."
                elif vv == "hip":
                    out[kk] = "CRITICAL CHANGE: Extend the jacket to HIP length — hemline must end at the hip."
                elif vv == "longline":
                    out[kk] = "CRITICAL CHANGE: Extend the jacket to LONGLINE length — hemline must end at mid-thigh or below."
                else:
                    out[kk] = f"CRITICAL CHANGE: Set jacket length to {vv}."
                continue

            if kk == "length" and c == "top":
                if vv == "crop":
                    out[kk] = "CRITICAL CHANGE: Shorten the top to CROP length — hemline must end at mid-ribcage, well above the navel. The navel and significant midriff must be clearly visible."
                elif vv == "regular":
                    out[kk] = "CRITICAL CHANGE: Adjust the top to REGULAR length — hemline must end across the hip, below the navel, covering the waistband of the pants/jeans."
                elif vv == "shirt":
                    out[kk] = "CRITICAL CHANGE: Extend the top to SHIRT length — hemline must end well below the hip, similar to a long untucked shirt. It should be noticeably longer than hip length."
                else:
                    out[kk] = f"CRITICAL CHANGE: Set top length to {vv}."
                continue

            if kk == "length" and c == "shirts":
                if vv == "tucked":
                    out[kk] = "CRITICAL CHANGE: Adjust the shirt to TUCKED length — short enough to be tucked into bottoms cleanly."
                elif vv == "untucked":
                    out[kk] = "CRITICAL CHANGE: Adjust the shirt to UNTUCKED length — hemline ending at the hip."
                elif vv == "longline":
                    out[kk] = "CRITICAL CHANGE: Extend the shirt to LONGLINE length — hemline ending at mid-thigh."
                else:
                    out[kk] = f"CRITICAL CHANGE: Set shirt length to {vv}."
                continue

            if kk == "length" and c == "blouse":
                if vv == "crop":
                    out[kk] = "CRITICAL CHANGE: Shorten the blouse to CROP length — hemline must end at mid-ribcage, well above the navel. The navel and significant midriff must be clearly visible."
                elif vv == "waist":
                    out[kk] = "CRITICAL CHANGE: Adjust the blouse to WAIST length — hemline must end exactly at the waist."
                elif vv == "hip":
                    out[kk] = "CRITICAL CHANGE: Extend the blouse to HIP length — hemline must reach the hip."
                else:
                    out[kk] = f"CRITICAL CHANGE: Set blouse length to {vv}."
                continue

            if kk == "length" and c == "t-shirts":
                if vv == "crop":
                    out[kk] = "CRITICAL CHANGE: Shorten the t-shirt to CROP length — hemline must end at mid-ribcage, well above the navel. The navel and significant midriff must be clearly visible."
                elif vv == "regular":
                    out[kk] = "CRITICAL CHANGE: Adjust the t-shirt to REGULAR length — hemline ending at the hip."
                elif vv == "longline":
                    out[kk] = "CRITICAL CHANGE: Extend the t-shirt to LONGLINE length — hemline ending at mid-thigh."
                else:
                    out[kk] = f"CRITICAL CHANGE: Set t-shirt length to {vv}."
                continue

            if kk in {"top_length", "bottom_length"} and c == "coord sets":
                piece = "top" if kk == "top_length" else "bottom"
                out[kk] = f"CRITICAL CHANGE: Set the {piece} of the coord set to {vv} length. Keep the other piece unchanged."
                continue

            if kk == "slit":
                if vv == "none":
                    out[kk] = "Remove any slit; keep hem clean; keep everything else identical."
                elif vv == "back":
                    out[kk] = "Add a back slit. Show the garment from the BACK view so the slit is clearly visible. Keep everything else identical."
                elif vv == "front_and_back":
                    out[kk] = "Add slits at both front and back of the skirt. Show the garment from the FRONT view. Keep everything else identical."
                else:
                    out[kk] = f"Add a {vv.replace('_', ' ')} slit; keep everything else identical."
                continue

            if kk == "back_detail":
                out[kk] = f"Add a {vv} detail to the BACK of the garment. Show the garment from the BACK view so the {vv} is clearly visible. Keep everything else identical."
                continue

            if kk == "front_detail":
                out[kk] = f"Add a {vv} detail to the FRONT of the garment. Keep the back unchanged. Keep everything else identical."
                continue

            # --- Multi-part garment awareness ---
            # Jumpsuit is ONE piece — modifications apply to the entire garment
            if c == "jumpsuit":
                if kk == "fit":
                    out[kk] = f"Change the fit of the ENTIRE jumpsuit (both top and bottom) to {vv}. Keep everything else identical."
                elif kk == "neckline":
                    out[kk] = f"Change the neckline of the jumpsuit to {vv}. Keep the rest of the jumpsuit identical."
                elif kk == "sleeves":
                    out[kk] = f"Change the sleeves of the jumpsuit to {vv}. Keep the rest of the jumpsuit identical."
                elif kk == "leg_fit":
                    out[kk] = f"Change the leg fit of the jumpsuit to {vv} legs. Keep the top half and everything else identical."
                elif kk == "waist_definition":
                    out[kk] = f"Change the waist definition of the jumpsuit to {vv}. Keep everything else identical."
                else:
                    out[kk] = f"Set {label} to {vv} on the jumpsuit. Keep everything else identical."
                continue

            # Coord sets — fields prefixed with top_/bottom_ target specific pieces
            if c == "coord sets":
                if kk.startswith("top_"):
                    piece_field = kk.replace("top_", "")
                    out[kk] = f"Change the TOP piece's {piece_field} to {vv}. Keep the bottom piece unchanged. Keep everything else identical."
                elif kk.startswith("bottom_"):
                    piece_field = kk.replace("bottom_", "")
                    out[kk] = f"Change the BOTTOM piece's {piece_field} to {vv}. Keep the top piece unchanged. Keep everything else identical."
                elif kk == "color_top":
                    out[kk] = f"Change the TOP piece color to {vv}. Keep the bottom piece color unchanged."
                elif kk == "color_bottom":
                    out[kk] = f"Change the BOTTOM piece color to {vv}. Keep the top piece color unchanged."
                else:
                    out[kk] = f"Set {label} to {vv} on BOTH pieces of the coord set. Keep everything else identical."
                continue

            # default — single-piece garments
            out[kk] = f"Set {label} to {vv}. Keep everything else identical."

        return out

    async def _regenerate_design_with_modifications(self, wa_id: str) -> None:
        # Atomic modification cap: reserve a slot or reject
        reserved = await self.store.try_reserve_modification(wa_id, MAX_MODIFICATIONS)
        if not reserved:
            await self._send_modification_limit_reached(wa_id)
            return

        sess = await self.store.get(wa_id) or {}

        base_occ = sess.get("design_occasion", "")
        base_cat = sess.get("design_category", "")
        base_fabric = sess.get("design_fabric", "")
        base_color = sess.get("design_color", "")
        mod_print_media_id = (sess.get("design_mod_print") or "").strip()
        persistent_print_ref = (sess.get("design_print_ref") or "").strip()

        # Always use the front image as base for modifications
        base_image_rel_path = (sess.get("generated_image_front") or sess.get("generated_image") or "").strip()

        # KV-based modifications
        kv = self._safe_load_kv(sess)
        modifications: Dict[str, str] = self._kv_to_precise_modifications(base_cat, kv)

        # ---- Pattern / print handling ----
        # Two cases:
        #   1) User uploaded a NEW print this cycle (design_mod_print) → mode="apply"
        #   2) Garment already has a print from a previous cycle (design_print_ref) → mode="preserve"
        pattern_image_bytes: Optional[bytes] = None
        pattern_mode = "apply"
        save_print_ref = ""

        if mod_print_media_id:
            # Case 1: NEW print being applied this cycle
            pattern_image_bytes = await self._download_pattern_bytes_if_possible(mod_print_media_id)
            pattern_mode = "apply"
            save_print_ref = mod_print_media_id  # persist for future cycles
            c = self._category_key(base_cat)

            color_anchor = (
                f"MANDATORY COLOR RULE: The {base_cat}'s base/background fabric color is {base_color}. "
                f"It MUST stay {base_color}. The {base_color} fabric must be clearly visible between and around the pattern motifs. "
                f"Do NOT replace {base_color} with the pattern image's own background color."
            )

            if c == "coord sets":
                modifications["print"] = (
                    f"Extract ONLY the motif/design shapes from the pattern reference image. "
                    f"Apply them as if screen-printed onto BOTH pieces of the coord set (top and bottom). "
                    f"{color_anchor} "
                    f"Keep everything else identical."
                )
            elif c == "jumpsuit":
                modifications["print"] = (
                    f"Extract ONLY the motif/design shapes from the pattern reference image. "
                    f"Apply them as if screen-printed onto the ENTIRE jumpsuit — both the top half and the bottom half uniformly. "
                    f"{color_anchor} "
                    f"Do NOT apply the print to any other clothing piece. Keep everything else identical."
                )
            else:
                modifications["print"] = (
                    f"Extract ONLY the motif/design shapes from the pattern reference image. "
                    f"Apply them as if screen-printed onto the {base_cat} fabric ONLY. "
                    f"{color_anchor} "
                    f"Do NOT apply the print to any other clothing piece. Keep everything else identical."
                )

        elif persistent_print_ref:
            # Case 2: Garment already has a print — reinforce it so Gemini doesn't lose it
            pattern_image_bytes = await self._download_pattern_bytes_if_possible(persistent_print_ref)
            if pattern_image_bytes:
                pattern_mode = "preserve"
                modifications["print_preservation"] = (
                    "The garment currently has a print/pattern on it (visible in the base image). "
                    "PRESERVE this print/pattern EXACTLY — same motifs, same placement, same detail. "
                    "Do NOT remove, fade, or simplify the print while applying other changes."
                )

        brief = DesignBrief(
            occasion=base_occ,
            budget="",
            category=base_cat,
            fabric=base_fabric,
            color=base_color,
            notes="",
            size="",
        )

        await self.store.set_fields(wa_id, {"state": STATE_DESIGN_POST})
        await self.store.touch(wa_id)

        await self.wa.send_text(wa_id, "Got it 💖 Updating your design… give me a sec ✨")

        rel_image_path: str
        try:
            if modifications and base_image_rel_path:
                try:
                    print(
                        f"[MODIFY] attempting EDIT path | wa_id={wa_id} base_image_rel_path={base_image_rel_path} modifications={modifications} pattern_mode={pattern_mode} has_pattern={bool(pattern_image_bytes)}"
                    )
                    rel_image_path = await self.gemini.generate_modified_image(
                        wa_id=wa_id,
                        base_image_rel_path=base_image_rel_path,
                        brief=brief,
                        modifications=modifications,
                        pattern_image_bytes=pattern_image_bytes,
                        pattern_mode=pattern_mode,
                    )
                except Exception as e:
                    print(
                        f"[MODIFY] EDIT FAILED -> FALLBACK to NEW generation | wa_id={wa_id} error={repr(e)}"
                    )
                    import traceback

                    traceback.print_exc()
                    rel_image_path = await self.gemini.generate_image_only(
                        wa_id,
                        DesignBrief(
                            occasion=base_occ,
                            budget="",
                            category=base_cat,
                            fabric=base_fabric,
                            color=(kv.get("color") or base_color),
                            notes="",
                            size="",
                        ),
                    )
            else:
                rel_image_path = await self.gemini.generate_image_only(
                    wa_id,
                    DesignBrief(
                        occasion=base_occ,
                        budget="",
                        category=base_cat,
                        fabric=base_fabric,
                        color=(kv.get("color") or base_color),
                        notes="",
                        size="",
                ),
            )
        except Exception as e:
            print(f"[regenerate_design] ALL PATHS FAILED wa_id={wa_id} error={repr(e)}")
            await self.wa.send_text(wa_id, ERROR_MSG_HIGH_VOLUME)
            return

        # Count already incremented atomically by try_reserve_modification

        # Determine if this was a back-facing modification
        is_back_mod = "back_detail" in kv

        result_fields: Dict[str, str] = {
            "generated_image": rel_image_path,
            "state": STATE_DESIGN_POST,
        }
        # Only update the front base image for non-back modifications
        if not is_back_mod:
            result_fields["generated_image_front"] = rel_image_path

        # Persist print reference if a new print was applied
        if save_print_ref:
            result_fields["design_print_ref"] = save_print_ref

        # Update design_color if user changed color during this modify cycle
        new_color = kv.get("color") or kv.get("color_top") or ""
        if new_color:
            result_fields["design_color"] = new_color

        await self.store.set_fields(wa_id, result_fields)
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, "DESIGN_POST_MODIFIED")

        await self._send_design_post(wa_id)

    # -------------------------
    # UPLOAD & DESIGN (decoupled — can be removed without breaking existing code)
    # -------------------------

    async def _start_upload_design(self, wa_id: str) -> None:
        # Quick cap check (non-blocking — real enforcement at generation time)
        count = await self.store.get_gen_count(wa_id)
        if count + 3 > MAX_GENERATIONS:
            await self._send_generation_limit_reached(wa_id)
            return

        await self.store.set_fields(
            wa_id,
            {
                "state": STATE_UPLOAD_WAIT_IMAGE,
                "flow": "upload_design",
                "upload_ref_media_id": "",
                "upload_option_1": "",
                "upload_option_2": "",
                "upload_option_3": "",
                "design_occasion": "",
                "design_category": "",
                "design_fabric": "",
                "design_color": "",
                "generated_image": "",
                "generated_image_front": "",
                "design_mod_field": "",
                "design_mod_print": "",
                "design_mod_kv": "{}",
                "design_print_ref": "",
                "design_print_id": "",
                "print_return_to": "",
                "nudge_count": "0",
            },
        )
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, STATE_UPLOAD_WAIT_IMAGE)

        await self.wa.send_text(
            wa_id,
            "Upload a picture of the outfit you love 💖\n(A clear photo works best!)",
        )

    async def handle_upload_image(self, wa_id: str, media_id: str) -> None:
        await self.store.touch(wa_id)

        # Download image bytes
        ref_bytes = await self._download_pattern_bytes_if_possible(media_id)
        if not ref_bytes:
            await self.wa.send_text(wa_id, "Couldn't download that image. Please try uploading again 🙂")
            return

        await self.store.set_fields(wa_id, {"upload_ref_media_id": media_id})

        await self.wa.send_text(wa_id, "Love it! Analyzing your style... 💖")

        # Step 1: Analyze the image
        try:
            analysis = await self.gemini.analyze_image(ref_bytes)
        except Exception as e:
            print(f"[upload] analyze_image failed: {e}")
            await self.wa.send_text(wa_id, ERROR_MSG_HIGH_VOLUME)
            return

        category = analysis.get("category", "dress")
        occasion = analysis.get("occasion", "Casual")
        fabric = analysis.get("fabric", "cotton")
        color = analysis.get("color", "black")
        style_notes = analysis.get("style_notes", "")

        await self.store.set_fields(
            wa_id,
            {
                "design_category": category,
                "design_occasion": occasion,
                "design_fabric": fabric,
                "design_color": color,
            },
        )

        # Atomic cap: reserve 3 slots before generating
        slots_reserved = 0
        for _ in range(3):
            if await self.store.try_reserve_generation(wa_id, MAX_GENERATIONS):
                slots_reserved += 1
            else:
                break
        if slots_reserved == 0:
            await self._send_generation_limit_reached(wa_id)
            return

        await self.wa.send_text(
            wa_id,
            f"I see a {color} {category}! Creating 3 inspired options... ✨\n(This takes a moment)",
        )

        # Step 2: Generate 3 options in parallel
        brief = DesignBrief(
            occasion=occasion,
            budget="",
            category=category,
            fabric=fabric,
            color=color,
            notes=style_notes,
            size="",
        )

        variations = [
            f"Closest match: Keep the same {color} color and similar style/silhouette. Stay very close to the reference.",
            f"Color twist: Keep the same style and silhouette, but change the color to something complementary (NOT {color}).",
            "Silhouette twist: Keep the same color palette, but change the silhouette or key structural element (e.g. neckline, length, or fit).",
        ]

        tasks = [
            self.gemini.generate_inspired_image(
                wa_id=wa_id,
                brief=brief,
                ref_bytes=ref_bytes,
                variation=var,
                index=i + 1,
            )
            for i, var in enumerate(variations)
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect successful results
        options: list[tuple[int, str]] = []
        for i, result in enumerate(results):
            if isinstance(result, str) and result:
                options.append((i + 1, result))
                # Count already reserved atomically above

        if not options:
            # All 3 failed
            print(f"[upload] all 3 generations failed for wa_id={wa_id}")
            await self.wa.send_text(wa_id, ERROR_MSG_HIGH_VOLUME)
            return

        # Store option paths in session
        option_fields: Dict[str, str] = {}
        for idx, path in options:
            option_fields[f"upload_option_{idx}"] = path

        await self.store.set_fields(wa_id, option_fields)

        # Send images with captions
        public_base_url = settings.PUBLIC_BASE_URL.rstrip("/")
        for idx, path in options:
            image_url = f"{public_base_url}{path}"
            await self.wa.send_image(wa_id, image_url=image_url, caption=f"Option {idx}")

        # Build buttons for only the successful options
        buttons = [(f"UPLOAD_PICK_{idx}", f"Option {idx}") for idx, _ in options]

        await self.store.set_fields(wa_id, {"state": STATE_UPLOAD_PICK_OPTION})
        await self.store.touch(wa_id)

        await self.wa.send_buttons(
            wa_id,
            "Which one speaks to you? 💖",
            buttons,
        )

    async def handle_upload_pick_option(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        if not bid or not bid.startswith("UPLOAD_PICK_"):
            await self.send_start_menu(wa_id)
            return

        pick_num = bid.replace("UPLOAD_PICK_", "", 1).strip()
        sess = await self.store.get(wa_id) or {}

        selected_path = (sess.get(f"upload_option_{pick_num}") or "").strip()
        if not selected_path:
            await self.wa.send_text(wa_id, "Hmm, that option isn't available. Let's start over!")
            await self.send_start_menu(wa_id)
            return

        # Set selected image as the generated image, enter modify flow
        await self.store.reset_mod_count(wa_id)
        await self.store.set_fields(
            wa_id,
            {
                "generated_image": selected_path,
                "generated_image_front": selected_path,
                "state": STATE_DESIGN_POST,
                "design_mod_field": "",
                "design_mod_print": "",
                "design_mod_kv": "{}",
                "design_print_ref": "",
                # Clean up upload option fields
                "upload_option_1": "",
                "upload_option_2": "",
                "upload_option_3": "",
                "upload_ref_media_id": "",
            },
        )
        await self.store.touch(wa_id)
        self.logger.log_step(wa_id, "UPLOAD_OPTION_SELECTED")

        await self._send_design_post(wa_id)

    # -------------------------
    # DESIGN BUY FLOW (size → confirm → order logged)
    # -------------------------

    async def handle_buy_size(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        size = {
            "SIZE_XS": "XS",
            "SIZE_S": "S",
            "SIZE_M": "M",
            "SIZE_L": "L",
            "SIZE_XL": "XL",
            "SIZE_XXL": "XXL",
        }.get(bid)

        if not size:
            # Unrecognized — re-send size chart + list
            await self._send_size_selection(wa_id, intro="Please pick a size 💖")
            return

        await self.store.set_fields(wa_id, {"buy_size": size, "state": STATE_BUY_CONFIRM})
        await self.store.touch(wa_id)

        # Build confirmation summary from session
        sess = await self.store.get(wa_id) or {}
        category = (sess.get("design_category") or "").strip().title()
        fabric = (sess.get("design_fabric") or "").strip().title()
        color = (sess.get("design_color") or "").strip().title()
        occasion = (sess.get("design_occasion") or "").strip()

        # Send the design image first
        rel_image_path = (sess.get("generated_image") or "").strip()
        if rel_image_path:
            public_base_url = settings.PUBLIC_BASE_URL.rstrip("/")
            image_url = f"{public_base_url}{rel_image_path}"
            await self.wa.send_image(wa_id, image_url=image_url, caption="Your design 💖")

        summary = (
            f"Your order summary 📋\n\n"
            f"Category: {category}\n"
            f"Fabric: {fabric}\n"
            f"Color: {color}\n"
            f"Occasion: {occasion}\n"
            f"Size: {size}\n\n"
            f"Confirm your order? 💖"
        )

        await self.wa.send_buttons(
            wa_id,
            summary,
            [
                ("BUY_CONFIRM_YES", "Confirm"),
                ("BUY_CONFIRM_NO", "Start Over"),
            ],
        )

    async def handle_buy_confirm(self, wa_id: str, bid: str) -> None:
        await self.store.touch(wa_id)

        if bid == "BUY_CONFIRM_YES":
            self.logger.log_step(wa_id, "ORDER_CONFIRMED")

            sess = await self.store.get(wa_id) or {"wa_id": wa_id}
            sess["reason"] = "order_confirmed"
            sess["wa_id"] = wa_id
            self.logger.write(wa_id, sess)

            await self.wa.send_text(
                wa_id,
                "Thank you! Your order is confirmed 💖\n"
                "We'll reach out to you shortly to get this made! ✨",
            )

            await self.store.delete(wa_id)
            return

        if bid == "BUY_CONFIRM_NO":
            self.logger.log_step(wa_id, "BUY_CANCELLED")
            await self.store.delete(wa_id)
            await self.send_start_menu(wa_id)
            return

        await self.send_start_menu(wa_id)

    # -------------------------
    # SHARED BUY FLOW (catalog — unchanged)
    # -------------------------
    async def handle_buy_name_text(self, wa_id: str, text: str) -> None:
        await self.store.touch(wa_id)
        name = text.strip()
        if not name:
            await self.wa.send_text(wa_id, "Please type your name 🙂")
            return

        await self.store.set_fields(wa_id, {"customer_name": name, "state": STATE_BUY_EMAIL})
        await self.store.touch(wa_id)
        await self.wa.send_text(wa_id, "Please tell us your email address 🙂")

    async def handle_buy_email_text(self, wa_id: str, text: str) -> None:
        await self.store.touch(wa_id)
        email = text.strip()

        if ("@" not in email) or ("." not in email):
            await self.wa.send_text(wa_id, "That doesn’t look like an email 😅 Please type it again.")
            return

        await self.store.set_fields(wa_id, {"customer_email": email})
        await self.store.touch(wa_id)

        sess = await self.store.get(wa_id) or {"wa_id": wa_id}
        sess["reason"] = "buy_completed"
        self.logger.write(wa_id, sess)

        await self.wa.send_text(wa_id, "Thank you for your order 💖 Someone will contact you shortly ✨")

        await self.store.delete(wa_id)
