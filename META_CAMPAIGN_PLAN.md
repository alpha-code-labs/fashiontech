# Drape AI — Meta Campaign Design (7-Day Demand Validation)

## Task Checklist

- [x] **Task 1:** Build landing page + deploy to Azure — Live at https://ashy-sky-03b626b00.6.azurestaticapps.net
- [x] **Task 2:** Create 3 ad creatives (Variant A: The Process, Variant B: The Result, Variant C: The Problem)
- [ ] **Task 3:** Set up Meta lead form + configure campaign in Ads Manager + go live

## Objective

Test one thing: **Does "design your own outfit with AI on WhatsApp" as a concept attract Indian women enough to take action?**

We're not selling. We're measuring intent.

## Campaign Structure

**Campaign type:** Lead Generation (Meta lead form)

**Duration:** 7 days

**Budget:** ₹500/day × 7 days = ₹3,500 total

## Audience

**Demographics:**
- Women, age 22-35
- Language: English + Hindi

**Geography — Tier 1 + Tier 2 cities (15 cities):**
- Tier 1: Mumbai, Delhi NCR, Bangalore, Hyderabad, Chennai, Pune, Kolkata
- Tier 2: Jaipur, Chandigarh, Ahmedabad, Kochi, Lucknow, Indore, Coimbatore

Not pan India. These are the women most likely to pay ₹2,000-4,000 for custom AI-designed western wear. Tighter audience = cleaner signal.

**Interest targeting (layer 2-3 of these):**
- Online shopping / fashion ecommerce (Myntra, Ajio, Nykaa Fashion)
- Western wear / contemporary fashion
- Instagram shopping behavior
- Fashion influencers

**Exclude:**
- Men
- Age below 20, above 40

## Ad Placement

- **Instagram Stories** (primary)
- **Instagram Reels** (secondary)
- **Facebook Feed** (tertiary)

Skip Audience Network and Messenger.

## Creative Strategy (3 Variants)

### Variant A — "The Process"
- Format: 15-sec screen recording or animated mockup of the bot flow
- Show: The actual WhatsApp chat interface — pick occasion → pick category → pick fabric → pick color → AI generates outfit
- Hook (first 3 sec): "Design your own outfit on WhatsApp. No app. No website. Just chat."
- End frame: "Get early access"

### Variant B — "The Result"
- Format: Static image or carousel
- Show: 3-4 AI-generated outfit images with a WhatsApp chat bubble frame
- Hook: "These outfits were designed by AI inside WhatsApp. Took 60 seconds."
- Subtext: "No app download. Just message and design."
- End frame: "Get early access"

### Variant C — "The Problem"
- Format: Story-style text overlay on fashion imagery
- Hook: "Tired of scrolling through 500 dresses and buying none?"
- Follow-up: "What if you just told WhatsApp what you want and AI designed it for you?"
- End frame: "Get early access"

Run all 3, let Meta optimize toward the winner after day 2-3.

## Lead Capture — Two Steps

### Step 1: Meta Lead Form (in-app)

User taps CTA → Meta's native lead form opens inside Instagram/Facebook. No redirect.

**Form fields:**
- Name (auto-filled from profile)
- WhatsApp number (auto-filled from profile)

Two fields, both auto-filled. She just taps "Submit."

**Form headline:** "Get early access to AI outfit design on WhatsApp"

**Form description:** "We're opening access in small batches. Drop your details and we'll message you when it's your turn."

### Step 2: Post-Form Landing Page

After submitting, Meta redirects her to our landing page hosted on Azure (https://ashy-sky-03b626b00.6.azurestaticapps.net).

**What she sees:**

> **You're in!**
>
> We're opening WhatsApp access in small batches. Keep an eye on your messages.
>
> Here's a taste of what AI can design for you:

3-4 best AI-generated outfit images in a clean grid.

> **How it works:**
> 1. Message us on WhatsApp
> 2. Pick your occasion, fabric, and color
> 3. AI designs a custom outfit for you in 60 seconds
>
> No app. No downloads. Just WhatsApp.

**Purpose:** Confirms her action, sells the product again with visuals, sets expectation for WhatsApp message.

## Production Responsibilities

| Task | Owner |
|------|-------|
| Landing page (build + Azure hosting) | Claude |
| Ad creatives (3 variants) | Sandeep, with Claude's guidance |
| Meta lead form setup | Sandeep |
| Campaign configuration in Ads Manager | Sandeep |
| Day 3 + Day 5 optimization | Sandeep, with Claude's guidance |

## Metrics That Matter

| Metric | What it tells you | Good signal | Bad signal |
|--------|------------------|-------------|------------|
| **CTR** | Is the hook compelling? | >1.5% | <0.5% |
| **CPC** | Cost of attention | <₹5-8 | >₹20 |
| **Form open rate** | Did she care enough to look? | >30% of clicks | <10% |
| **Form completion rate** | Is the form frictionless? | >70% of opens | <40% |
| **Cost per lead** | What does a warm lead cost? | <₹30-50 | >₹100 |
| **Variant winner** | What messaging resonates | — | — |

**Single most important number:** cost per lead.

**Target:** 70-120 leads at ₹30-50 each.

## Day-by-Day Playbook

| Day | Action |
|-----|--------|
| **Day 0** | Build landing page, create 3 ad creatives, set up lead form, configure campaign |
| **Day 1-2** | Launch all 3 variants. Don't touch anything. Let Meta learn. |
| **Day 3** | Check data. Kill the worst performing variant. Reallocate budget to top 2. |
| **Day 5** | Check again. If one clear winner, shift 70% budget to it. |
| **Day 7** | Campaign ends. Analyze results. Export lead list. |

## What You'll Know at the End

- Does "design your own outfit with AI on WhatsApp" attract Indian women? (CTR + form completion)
- What messaging resonates — the process, the result, or the problem? (variant winner)
- How much does a warm lead cost? (unit economics)
- A list of real WhatsApp numbers of interested women to onboard into the bot

Combined with pre-test results: you'll know if you have both **demand** AND **delivery**.
