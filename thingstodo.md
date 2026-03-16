# Things To Do — Production Readiness

## 1. ~~Error Handling (Critical)~~ — DONE
- ~~Wrap `_generate_design()` with try/catch — currently if Gemini fails, the bot goes completely silent on the user with no feedback or retry option~~
- ~~Add user-facing error messages on failure~~
- ~~Cover all critical paths: design generation, WhatsApp send failures, image upload processing~~
- ~~The webhook catch-all currently swallows all exceptions silently — needs per-path recovery~~
- All paths now send: "We're experiencing unusually high volumes right now. Please try again in about 30 minutes" on failure. User session state preserved.

## 2. ~~GeminiPool — Multi-Key Rotation~~ — DONE
- ~~Create 4 additional Gemini API keys from Google AI Studio~~
- ~~Build GeminiPool with round-robin rotation across all keys~~
- ~~Auto-failover: on 429 rate limit, automatically switch to the next key~~
- ~~Add concurrency semaphore to cap simultaneous Gemini image generation calls~~
- ~~Store keys as comma-separated in `.env`: `GEMINI_API_KEYS=key1,key2,key3,key4,key5`~~
- 5 keys configured. GeminiPool with round-robin, 429 failover across all keys, semaphore (max 8 concurrent image calls).

## 3. ~~Split Generation Limits — New Designs vs Modifications~~ — DONE
- ~~Currently a single counter (max 10) covers both new designs and modifications — too restrictive for POC~~
- ~~Split into two separate Redis counters~~
- ~~Gives users up to 110 total images (10 designs × 10 modifications each) instead of 10 flat~~
- New designs use `gen_limit:{wa_id}` (max 10), modifications use `gen_mod:{wa_id}` (max 10 per design, resets on new design).

## 4. ~~Show Remaining Limits to User~~ — DONE
- ~~User has no way of knowing how many designs or modifications they have left~~
- ~~Add counter info to the existing button message in `_send_design_post()` (no extra messages)~~
- Counter line appended to button message: "9 designs remaining · 10 modifications left". Unlimited numbers skip the line.

## 5. ~~Persistent httpx Client~~ — DONE
- ~~Currently creating and tearing down a new `httpx.AsyncClient` on every single WhatsApp send and Gemini call~~
- ~~Replace with a shared persistent `httpx.AsyncClient` singleton with built-in connection pooling~~
- Single `self._client` created in WhatsAppClient.__init__(), reused for all sends and media downloads.
