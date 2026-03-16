# Empressa — Pre-Test Build Plan

## Context

Before the full influencer launch (described in PRODUCT_BIBLE.md), we're running a smaller validation test first.

**Core question:** When a woman designs an outfit through the bot and receives the physical garment — does the real thing match what she imagined from the AI image?

This is the hardest gap in the business. If AI image → manufactured garment fidelity doesn't hold, nothing else matters.

## The Pre-Test

- **20 women** go through the bot and place an order
- **No payment integration** — orders are captured, not paid for
- **Manufacturing partner** produces the 20 outfits based on the order details
- **Ship physical garments** to the 20 women
- **Collect feedback** — did what they received match what they saw on screen?

## What's Already Built

The backend is fully functional for this test:

### Intake Flow (4 structured taps, no free text)
1. **Occasion** — Party/Date, Office, Casual, Vacation
2. **Category** — Dress, Top, Skirt, Pants, Jumpsuit, Shirts, Coord sets, etc.
3. **Fabric** — Cotton, Viscose linen, Cotton linen, Rayon, Polycrepe, Denim
4. **Color** — 10 presets + "You choose a color" (AI picks)

### Image Generation
- Gemini API generates photorealistic outfit on a South Asian female model
- Modify flow supports 8+ category-specific fields (length, sleeves, neckline, fit, etc.)
- Pattern/print upload supported in modify

### Post-Generation Actions
- **Modify** — category-conditional field editing, regenerates image
- **Design Another** — restart intake
- **Buy Now** — size selection → order confirmation

### Order Capture
- Size selection (XS–XXL)
- Session logged as JSON with all design details (occasion, category, fabric, color, modifications)
- Generated image saved to `/app/static/generated/`
- Orders visible on `/dashboard` endpoint

### Tracking
- Every state transition logged to `steps.csv` (drop-off curve)
- Session JSONs stored in `/app/data/sessions/{YYYYMMDD}/`

### Infrastructure
- WhatsApp Cloud API integration (buttons, lists, images)
- Redis session management with TTL
- Generation cap (10 free per user)
- Message deduplication

## What the Pre-Test Needs (Gaps to Fill)

### Must Have
- [ ] **Order forwarding to manufacturer** — Auto-forward order details (AI image + specs + user phone) to manufacturer via WhatsApp the moment an order is confirmed. Supports multiple recipient numbers via `MANUFACTURER_WA_IDS` in `.env`. **⚠️ DECISION PENDING:** Confirming with manufacturing partner which WhatsApp numbers to use and whether they prefer receiving orders this way vs. another format.
- [ ] **Order dashboard improvements** — Dashboard currently shows orders but may need: order status tracking, easy image download
- [ ] **Feedback collection mechanism** — After delivery, a way to collect feedback from the 20 women (could be a simple WhatsApp follow-up message from the bot, or manual)

### Not Needed (Pre-Test Simplification)
- **Shipping details capture** — All 20 women are known contacts, addresses can be collected offline

### Nice to Have
- [ ] **Order ID generation** — Unique order IDs for tracking between us and the manufacturer
- [ ] **Order status updates** — Ability to update order status (confirmed → in production → shipped → delivered) and notify the user via WhatsApp
- [ ] **Manufacturer-friendly spec sheet** — Auto-generated per order: image + occasion + category + fabric + color + size + all modifications in a clean format

### Not Needed for Pre-Test
- Payment integration (no payment happening)
- Catalog shopping flow (only "Design Your Own" matters)
- Upload & Design flow (keep it simple — structured intake only)
- Analytics beyond drop-off CSV
- CRM integration

## Success Criteria

1. **20 women complete the full flow** — from first message to order confirmed
2. **Manufacturing partner can produce from the specs** — order details + AI image are clear enough to manufacture from
3. **Garment matches expectation** — women's feedback confirms the physical outfit matches what they saw in the AI image

## What This Validates

- **AI → Physical fidelity** — The big unknown. Can a manufacturer look at our AI image + specs and produce something the customer recognizes?
- **Intake flow UX** — Do women complete the flow or drop off? Where?
- **Image quality** — Are the AI images compelling enough that women want the outfit?
- **Spec clarity** — Are occasion + category + fabric + color + size + modifications enough for a manufacturer to work with?

## What Comes After

If the pre-test validates AI → physical fidelity:
→ Add payment integration (UPI, ₹199 booking amount)
→ Run the full influencer launch (as described in PRODUCT_BIBLE.md)
→ Measure engagement + conversion at scale
