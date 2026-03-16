from __future__ import annotations

import time
from typing import Any, Dict
import redis.asyncio as redis

from app.core.config import settings

SESSION_KEY_PREFIX = "sess:"
EXPIRY_ZSET = "sess_expiry_zset"

# Inbound message dedupe (idempotency)
PROCESSED_MSG_PREFIX = "processed_msg:"
PROCESSED_MSG_TTL_SECONDS = 60 * 60  # 1 hour

# Generation cap (persists independently of session lifecycle)
GEN_COUNT_PREFIX = "gen_limit:"
GEN_MOD_COUNT_PREFIX = "gen_mod:"


class SessionStore:
    def __init__(self):
        self.r = redis.from_url(settings.REDIS_URL, decode_responses=True)

    def _key(self, wa_id: str) -> str:
        return f"{SESSION_KEY_PREFIX}{wa_id}"

    async def get(self, wa_id: str) -> Dict[str, Any] | None:
        data = await self.r.hgetall(self._key(wa_id))
        if not data:
            return None
        return dict(data)

    async def set_fields(self, wa_id: str, fields: Dict[str, Any]) -> None:
        str_fields = {k: str(v) for k, v in fields.items()}
        await self.r.hset(self._key(wa_id), mapping=str_fields)

    async def touch(self, wa_id: str) -> None:
        now = int(time.time())
        expiry_at = now + settings.SESSION_TIMEOUT_SECONDS

        key = self._key(wa_id)
        await self.r.hset(key, mapping={"last_activity_ts": str(now)})

        await self.r.expire(key, settings.SESSION_TIMEOUT_SECONDS)
        await self.r.zadd(EXPIRY_ZSET, {wa_id: expiry_at})

        # Debug (helps confirm what Redis thinks expiry is)
        print(
            f"[touch] wa_id={wa_id} now={now} expiry_at={expiry_at} timeout={settings.SESSION_TIMEOUT_SECONDS}"
        )

    async def pop_expired_sessions(self) -> list[str]:
        now = int(time.time())
        candidates = await self.r.zrangebyscore(EXPIRY_ZSET, min=0, max=now)
        if not candidates:
            return []

        expired: list[str] = []
        for wa_id in candidates:
            key = self._key(wa_id)
            last_ts = await self.r.hget(key, "last_activity_ts")

            if last_ts is None:
                expired.append(wa_id)
                continue

            try:
                last_ts_i = int(last_ts)
            except ValueError:
                last_ts_i = now  # do NOT expire early

            delta = now - last_ts_i

            # Debug (this is the important line)
            print(
                f"[expiry_check] wa_id={wa_id} now={now} last={last_ts_i} delta={delta} timeout={settings.SESSION_TIMEOUT_SECONDS}"
            )

            if delta >= settings.SESSION_TIMEOUT_SECONDS:
                expired.append(wa_id)
            else:
                await self.r.zadd(EXPIRY_ZSET, {wa_id: last_ts_i + settings.SESSION_TIMEOUT_SECONDS})

        if expired:
            await self.r.zrem(EXPIRY_ZSET, *expired)

        return expired

    async def delete(self, wa_id: str) -> None:
        await self.r.delete(self._key(wa_id))
        await self.r.zrem(EXPIRY_ZSET, wa_id)

    # -------------------------
    # Inbound message idempotency
    # -------------------------
    async def mark_inbound_message_once(self, msg_id: str) -> bool:
        """
        Returns True if this msg_id is seen for the first time.
        Returns False if this msg_id was already processed.

        Uses SET NX with TTL to dedupe Meta webhook retries.
        """
        key = f"{PROCESSED_MSG_PREFIX}{msg_id}"
        # SET key "1" EX ttl NX => returns True if set, None/False if already exists
        ok = await self.r.set(key, "1", ex=PROCESSED_MSG_TTL_SECONDS, nx=True)
        return bool(ok)

    # -------------------------
    # Generation cap
    # -------------------------
    async def get_gen_count(self, wa_id: str) -> int:
        val = await self.r.get(f"{GEN_COUNT_PREFIX}{wa_id}")
        return int(val) if val else 0

    async def incr_gen_count(self, wa_id: str) -> int:
        return await self.r.incr(f"{GEN_COUNT_PREFIX}{wa_id}")

    # Lua script: atomic check-and-increment for generation cap
    _RESERVE_GEN_LUA = """
    local key = KEYS[1]
    local limit = tonumber(ARGV[1])
    local current = tonumber(redis.call("GET", key) or "0")
    if current < limit then
        redis.call("INCR", key)
        return 1
    end
    return 0
    """

    async def try_reserve_generation(self, wa_id: str, limit: int) -> bool:
        """
        Atomically check if generation count < limit and increment.
        Returns True if a slot was reserved, False if limit reached.
        """
        key = f"{GEN_COUNT_PREFIX}{wa_id}"
        result = await self.r.eval(self._RESERVE_GEN_LUA, 1, key, limit)
        return bool(result)

    # -------------------------
    # Modification cap (per-design, resets on new design)
    # -------------------------
    async def get_mod_count(self, wa_id: str) -> int:
        val = await self.r.get(f"{GEN_MOD_COUNT_PREFIX}{wa_id}")
        return int(val) if val else 0

    async def reset_mod_count(self, wa_id: str) -> None:
        await self.r.delete(f"{GEN_MOD_COUNT_PREFIX}{wa_id}")

    async def try_reserve_modification(self, wa_id: str, limit: int) -> bool:
        """
        Atomically check if modification count < limit and increment.
        Returns True if a slot was reserved, False if limit reached.
        """
        key = f"{GEN_MOD_COUNT_PREFIX}{wa_id}"
        result = await self.r.eval(self._RESERVE_GEN_LUA, 1, key, limit)
        return bool(result)
