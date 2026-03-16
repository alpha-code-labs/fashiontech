# Empressa — Product Bible

## What we are testing

The plan: put the bot in the hands of a local influencer. She promotes the experience on her story, women message the bot, we watch what happens.

The influencer says something like "This AI designs custom outfits for you — try it" and we measure behavior.

Two questions in one test:

1. **Does the design experience hook them?** (measured by drop-off curve through the flow)
2. **Would they actually pay?** (measured by conversion on a real payment step)

Structure: engagement data is captured regardless of whether anyone pays. The payment step comes at the end, after all engagement signals are already logged. One influencer push answers both questions.

## Why engagement alone isn't enough

Engagement proves we built something fun. It doesn't prove we built a business. Indian women will engage with anything novel for 5 minutes — especially if an influencer told them to try it. The gap between "wow cool image" and "I'll pay real money for this as a physical garment" is massive. That gap IS the business question.

The risk of testing only engagement: the test goes great, everyone loves it, we celebrate. Then we add payment next month, run another influencer push, and nobody pays. Two rounds of influencer capital burned to learn what we could have learned in one.

## What we are NOT testing

- Shop from catalog (parked for later)

## Metrics that matter

- How many women message the bot after seeing the story
- How many complete the flow and see their generated design
- How many hit Modify (they cared enough to refine it)
- How many design a second outfit (they're hooked)
- How many tap Buy (strong signal)
- How many actually pay the booking amount (strongest signal)

The metric that matters most is the **drop-off curve**. If 100 women message the bot and 80 pick an occasion but only 15 see the image — the intake is killing you. If 70 see the image but only 2 modify — the generation quality isn't exciting them. The shape of that curve tells you everything.

## Design principles for this test

### 1. Intake has to be ruthlessly fast
Every tap before the image is a tax on curiosity. Four structured taps max. No free text. No typing. Just lists.

### 2. The image quality is everything
That's the "holy shit" moment. If the image is mid, nothing else matters.

### 3. After the image, priority is "design another" not "buy"
We want them to stay and play. Buy exists but the energy should push toward more engagement.

### 4. Buy = real payment, minimal friction
User taps "Buy now", bot sends a UPI payment link for a booking amount (₹199-299 range — low enough for impulse, high enough to filter casual taps). Framing: "₹199 to book your design, rest on delivery." If they pay, strongest possible signal — log it, follow up manually via WhatsApp. If they don't pay, that's still data — interested enough to tap Buy but not enough to spend ₹199. After the payment step (paid or not), offer them to design another outfit. Keep them in the experience.

### 5. The influencer's promise and the bot's experience must be aligned
She's promising a fun, personalized design experience. That's exactly what the bot delivers. Buy isn't the pitch — the design experience is.

## Flow redesign direction

### Intake (all structured lists, no free text)
1. Occasion (list)
2. Category (list)
3. Fabric (list)
4. Color (list)
5. Generate image

### Removed from intake
- Notes (vague, causes friction — modify flow handles customization)
- Prints (power-user feature — available in modify only)
- Size (doesn't affect the image — move to buy flow if needed later)

### Post-generation
- Show image + price
- Buttons: Modify / Design Another / Buy
- Buy = show UPI payment link (₹199 booking) + offer to design another after
- Modify = existing category-conditional flow (already well designed)
- Design Another = restart the intake

### Tracking
- Every state transition must be logged (not just completions)
- Step-level drop-off data is critical
- Session timeout should be increased (120s is too aggressive)
