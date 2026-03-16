# app/services/whatsapp_client.py
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings


class WhatsAppClient:
    """
    Backward-compatible WhatsApp Cloud API client.

    Fixes added (no call-site changes required):
    - Per-recipient throttle to prevent burst sends (pair rate limit).
    - Backoff/cooldown when Meta returns error code 131056.
    - Small, safe retry on transient network errors (does NOT retry 131056).

    Added (for Design->Modify->Print upload):
    - download_media_bytes(media_id): fetches inbound media bytes from Graph API.

    ✅ Updated for your current issue:
    - download_media_bytes now accepts EITHER:
        a) a WhatsApp media_id, OR
        b) a direct URL (http/https) to the media
      (so the rest of your flow can stay unchanged and nothing breaks)
    """

    _MIN_GAP_SECONDS = 0.6
    _MAX_RETRIES = 2
    _RETRY_BASE_SLEEP = 0.6
    _COOLDOWN_SECONDS = 8.0
    _MAX_COOLDOWN_SECONDS = 60.0

    def __init__(self):
        self.token = settings.WHATSAPP_TOKEN
        self.phone_number_id = settings.PHONE_NUMBER_ID
        self.api_version = settings.GRAPH_API_VERSION

        self._client = httpx.AsyncClient(timeout=30)

        self._locks: Dict[str, asyncio.Lock] = {}
        self._last_sent_ts: Dict[str, float] = {}
        self._cooldown_until: Dict[str, float] = {}
        self._cooldown_hits: Dict[str, int] = {}
        self._max_tracked_users = 10000  # prevent unbounded growth

    def _url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def _auth_headers_only(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
        }

    def _evict_stale_entries(self) -> None:
        """Remove oldest entries when tracking dicts exceed max size."""
        if len(self._last_sent_ts) <= self._max_tracked_users:
            return
        # Sort by last-sent timestamp, keep the most recent half
        keep = self._max_tracked_users // 2
        sorted_ids = sorted(self._last_sent_ts, key=self._last_sent_ts.get, reverse=True)
        evict = set(sorted_ids[keep:])
        for wa_id in evict:
            self._last_sent_ts.pop(wa_id, None)
            self._cooldown_until.pop(wa_id, None)
            self._cooldown_hits.pop(wa_id, None)
            lock = self._locks.get(wa_id)
            if lock and not lock.locked():
                self._locks.pop(wa_id, None)

    def _lock_for(self, to_wa_id: str) -> asyncio.Lock:
        lock = self._locks.get(to_wa_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[to_wa_id] = lock
        return lock

    async def _throttle(self, to_wa_id: str) -> None:
        now = time.time()
        cd_until = self._cooldown_until.get(to_wa_id, 0.0)
        if cd_until > now:
            await asyncio.sleep(cd_until - now)
            now = time.time()

        last = self._last_sent_ts.get(to_wa_id, 0.0)
        gap = now - last
        if gap < self._MIN_GAP_SECONDS:
            await asyncio.sleep(self._MIN_GAP_SECONDS - gap)

    @staticmethod
    def _extract_wa_error_code(body: str) -> Optional[int]:
        try:
            import json

            j = json.loads(body)
            err = j.get("error") or {}
            code = err.get("code")
            if isinstance(code, int):
                return code
        except Exception:
            return None
        return None

    def _register_cooldown(self, to_wa_id: str) -> None:
        hits = self._cooldown_hits.get(to_wa_id, 0) + 1
        self._cooldown_hits[to_wa_id] = hits

        cooldown = min(self._COOLDOWN_SECONDS * (2 ** (hits - 1)), self._MAX_COOLDOWN_SECONDS)
        until = time.time() + cooldown
        self._cooldown_until[to_wa_id] = until

        print(f"[wa_client] rate-limited (131056) to={to_wa_id} cooldown={cooldown:.1f}s hits={hits}")

    async def _post(self, to_wa_id: str, payload: dict, label: str) -> None:
        async with self._lock_for(to_wa_id):
            await self._throttle(to_wa_id)

            url = self._url()
            headers = self._headers()

            attempt = 0
            while True:
                attempt += 1
                try:
                    r = await self._client.post(url, headers=headers, json=payload)

                    print(f"{label}_PAYLOAD=", payload)
                    print(f"{label}_ERR=", r.status_code, r.text)

                    if 200 <= r.status_code < 300:
                        self._last_sent_ts[to_wa_id] = time.time()
                        if to_wa_id in self._cooldown_hits:
                            self._cooldown_hits[to_wa_id] = 0
                        self._evict_stale_entries()
                        return

                    err_code = self._extract_wa_error_code(r.text)
                    if err_code == 131056:
                        self._register_cooldown(to_wa_id)
                        self._last_sent_ts[to_wa_id] = time.time()
                        return

                    if 400 <= r.status_code < 500:
                        r.raise_for_status()

                    if 500 <= r.status_code < 600 and attempt <= self._MAX_RETRIES:
                        await asyncio.sleep(self._RETRY_BASE_SLEEP * attempt)
                        continue

                    r.raise_for_status()

                except httpx.HTTPStatusError:
                    raise
                except (httpx.TimeoutException, httpx.NetworkError) as e:
                    if attempt <= self._MAX_RETRIES:
                        await asyncio.sleep(self._RETRY_BASE_SLEEP * attempt)
                        continue
                    raise e

    async def send_text(self, to_wa_id: str, text: str) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "text",
            "text": {"body": text},
        }
        await self._post(to_wa_id, payload, label="TEXT")

    async def send_buttons(self, to_wa_id: str, body: str, buttons: list[tuple[str, str]]) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body},
                "action": {
                    "buttons": [
                        {"type": "reply", "reply": {"id": bid, "title": title}}
                        for (bid, title) in buttons
                    ]
                },
            },
        }
        await self._post(to_wa_id, payload, label="BUTTONS")

    async def send_list(self, to_wa_id: str, body: str, button_text: str, sections: list[dict]) -> None:
        payload = {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": body},
                "action": {"button": button_text, "sections": sections},
            },
        }
        await self._post(to_wa_id, payload, label="LIST")

    async def send_image(self, to_wa_id: str, image_url: str, caption: str | None = None) -> None:
        payload: Dict[str, Any] = {
            "messaging_product": "whatsapp",
            "to": to_wa_id,
            "type": "image",
            "image": {"link": image_url},
        }
        if caption:
            payload["image"]["caption"] = caption
        await self._post(to_wa_id, payload, label="IMAGE")

        # Give Meta time to download & cache the image from our server
        # before we send the next message (text/buttons deliver instantly,
        # images need a server-side fetch first).
        await asyncio.sleep(2)

    async def download_media_bytes(self, media_id: str) -> bytes:
        """
        For inbound media:
          - If caller passes a direct URL (http/https), we download it directly.
          - Otherwise:
              1) GET /{media_id} -> returns a JSON with "url"
              2) GET {url} with Authorization header -> bytes
        """
        media_id = (media_id or "").strip()
        if not media_id:
            raise ValueError("media_id is required")

        # ✅ Accept direct URL references too (keeps existing call sites unchanged)
        if media_id.startswith("http://") or media_id.startswith("https://"):
            r = await self._client.get(media_id, headers=self._auth_headers_only())
            r.raise_for_status()
            return r.content

        meta_url = f"https://graph.facebook.com/{self.api_version}/{media_id}"

        r = await self._client.get(meta_url, headers=self._auth_headers_only())
        r.raise_for_status()
        j = r.json()

        url = (j or {}).get("url")
        if not url:
            raise RuntimeError(f"Media lookup did not return url for media_id={media_id}")

        r2 = await self._client.get(url, headers=self._auth_headers_only())
        r2.raise_for_status()
        return r2.content
