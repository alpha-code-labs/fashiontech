from __future__ import annotations

from fastapi import APIRouter, Request, Response

from app.core.config import settings
from app.state.store import SessionStore
from app.services.whatsapp_client import WhatsAppClient
from app.services.catalog_service import CatalogService
from app.services.session_logger import SessionLogger
from app.services.gemini_client import GeminiClient
from app.services.print_service import PrintService
from app.state.flow import (
    FlowEngine,
    STATE_START,
    STATE_CATALOG_OCCASION,
    STATE_CATALOG_BUDGET,
    STATE_DESIGN_OCCASION,
    STATE_DESIGN_CATEGORY,
    STATE_DESIGN_FABRIC,
    STATE_DESIGN_COLOR,
    STATE_DESIGN_PRINT_CATEGORY,
    STATE_DESIGN_PRINT_PICK,
    STATE_DESIGN_POST,
    STATE_BUY_NAME,
    STATE_BUY_EMAIL,
    STATE_DESIGN_MODIFY_MENU,
    STATE_DESIGN_COLOR_TEXT,
    STATE_DESIGN_MODIFY_FIELD_TEXT,
    STATE_DESIGN_MODIFY_FIELD_CHOICE,
    STATE_DESIGN_MODIFY_WAIT_PATTERN,
    STATE_UPLOAD_WAIT_IMAGE,
    STATE_UPLOAD_PICK_OPTION,
    STATE_BUY_SIZE,
    STATE_BUY_CONFIRM,
)

router = APIRouter()

store = SessionStore()
wa = WhatsAppClient()
catalog = CatalogService()
logger = SessionLogger()
gemini = GeminiClient()
print_service = PrintService()
flow = FlowEngine(wa=wa, store=store, catalog=catalog, logger=logger, gemini=gemini, print_service=print_service)


@router.get("/webhook")
async def verify_webhook(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.VERIFY_TOKEN and challenge:
        return Response(content=challenge, media_type="text/plain")

    return Response(
        content='{"detail":"Webhook verification failed"}',
        media_type="application/json",
        status_code=403,
    )


@router.post("/webhook")
async def receive_webhook(request: Request) -> dict:
    payload = await request.json()
    wa_id = None

    # Meta retries; always return 200 quickly even if we ignore
    try:
        entry = (payload.get("entry") or [])[0]
        changes = (entry.get("changes") or [])[0]
        value = changes.get("value") or {}

        messages = value.get("messages") or []
        if not messages:
            return {"ok": True}

        msg = messages[0]
        wa_id = msg.get("from")
        if not wa_id:
            return {"ok": True}

        # ---- Idempotency / dedupe ----
        msg_id = msg.get("id")
        if msg_id:
            first_time = await store.mark_inbound_message_once(msg_id)
            if not first_time:
                return {"ok": True}

        await store.touch(wa_id)

        sess = await store.get(wa_id) or {}
        state = sess.get("state", STATE_START)

        mtype = msg.get("type")

        # ----- TEXT messages -----
        if mtype == "text":
            text = (msg.get("text") or {}).get("body", "").strip()

            if text.upper().startswith("START_DESIGN"):
                await flow.handle_start_design_keyword(wa_id)
                return {"ok": True}

            # Fabric and Print selection are list-only; nudge user to pick from list
            if state in {STATE_DESIGN_FABRIC, STATE_DESIGN_COLOR, STATE_DESIGN_PRINT_CATEGORY, STATE_DESIGN_PRINT_PICK}:
                await wa.send_text(wa_id, "Please pick from the list above 🙂")
                return {"ok": True}

            if state == STATE_DESIGN_COLOR_TEXT:
                await flow.handle_design_color_text(wa_id, text)
                return {"ok": True}

            if state == STATE_DESIGN_MODIFY_FIELD_TEXT:
                await flow.handle_design_modify_field_text(wa_id, text)
                return {"ok": True}

            if state == STATE_BUY_NAME:
                await flow.handle_buy_name_text(wa_id, text)
                return {"ok": True}

            if state == STATE_BUY_EMAIL:
                await flow.handle_buy_email_text(wa_id, text)
                return {"ok": True}

            await flow.send_start_menu(wa_id)
            return {"ok": True}

        # ----- IMAGE messages -----
        if mtype == "image":
            image_obj = msg.get("image") or {}
            media_id = (image_obj.get("id") or "").strip()

            # Upload & Design -> reference image
            if state == STATE_UPLOAD_WAIT_IMAGE:
                if media_id:
                    await flow.handle_upload_image(wa_id, media_id)
                    return {"ok": True}

                await wa.send_text(wa_id, "Please upload a clear outfit image 🙂")
                return {"ok": True}

            # Modify -> Print upload
            if state == STATE_DESIGN_MODIFY_WAIT_PATTERN:
                if media_id:
                    await flow.handle_design_modify_print_image(wa_id, media_id)
                    return {"ok": True}

                await wa.send_text(wa_id, "Please upload a clear pattern image 🙂")
                return {"ok": True}

            await flow.send_start_menu(wa_id)
            return {"ok": True}

        # ----- INTERACTIVE (buttons / list) -----
        if mtype == "interactive":
            interactive = msg.get("interactive") or {}
            itype = interactive.get("type")

            bid = None
            if itype == "button_reply":
                bid = (interactive.get("button_reply") or {}).get("id")
            elif itype == "list_reply":
                bid = (interactive.get("list_reply") or {}).get("id")

            if not bid:
                await flow.send_start_menu(wa_id)
                return {"ok": True}

            if state == STATE_START:
                await flow.handle_start_button(wa_id, bid)
                return {"ok": True}

            # CATALOG
            if state == STATE_CATALOG_OCCASION:
                await flow.handle_catalog_occasion(wa_id, bid)
                return {"ok": True}

            if state == STATE_CATALOG_BUDGET:
                await flow.handle_catalog_budget(wa_id, bid)
                return {"ok": True}

            if state == "CATALOG_RESULTS":
                await flow.handle_catalog_nav(wa_id, bid)
                return {"ok": True}

            # DESIGN
            if state == STATE_DESIGN_OCCASION:
                await flow.handle_design_occasion(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_CATEGORY:
                await flow.handle_design_category(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_FABRIC:
                await flow.handle_design_fabric_button(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_COLOR:
                await flow.handle_design_color_button(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_PRINT_CATEGORY:
                await flow.handle_design_print_category(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_PRINT_PICK:
                await flow.handle_design_print_pick(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_POST:
                await flow.handle_design_post_button(wa_id, bid)
                return {"ok": True}

            # UPLOAD & DESIGN
            if state == STATE_UPLOAD_PICK_OPTION:
                await flow.handle_upload_pick_option(wa_id, bid)
                return {"ok": True}

            # BUY (design flow)
            if state == STATE_BUY_SIZE:
                await flow.handle_buy_size(wa_id, bid)
                return {"ok": True}

            if state == STATE_BUY_CONFIRM:
                await flow.handle_buy_confirm(wa_id, bid)
                return {"ok": True}

            # MODIFY
            if state == STATE_DESIGN_MODIFY_MENU:
                await flow.handle_design_modify_menu(wa_id, bid)
                return {"ok": True}

            if state == STATE_DESIGN_MODIFY_FIELD_CHOICE:
                await flow.handle_design_modify_field_choice(wa_id, bid)
                return {"ok": True}

            await flow.send_start_menu(wa_id)
            return {"ok": True}

        await flow.send_start_menu(wa_id)
        return {"ok": True}

    except Exception as e:
        print(f"[webhook] error: {e}")
        import traceback
        traceback.print_exc()
        try:
            if wa_id:
                await wa.send_text(
                    wa_id,
                    "We're experiencing unusually high volumes right now. "
                    "Please try again in about 30 minutes — we'll be ready for you! 💖",
                )
        except Exception:
            pass
        return {"ok": True}
