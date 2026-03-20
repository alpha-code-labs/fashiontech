# Things Not Working

## Production Ready Garments
1. Dress
2. Top
3. Skirt
4. Pants
5. Jumpsuit
6. Shirts
7. Coord sets

---

## 1) Length — SOLVED ✅

Gemini cannot reliably extend garment length. Shortening works, extending does not.

**Solution**: Moved length selection to the buy flow. User picks length via WhatsApp buttons with descriptions at checkout. MHK sees the length choice in the order. Already deployed to production. Length removed from AI modification menu for all garment types.

## 2) Waist rise — not working

Gemini cannot reliably render the difference between high/mid/low waist rise. The waistband position does not visibly change.

Affected garment types:
- Skirt (waist_rise: High, Mid, Low)
- Pants (rise: High, Mid, Low)
- Coord bottoms (same class of problem — bottoms are skirts/pants)

**Solution**: Not yet fixed.

## 3) Fit — going to slim not working

Gemini can make garments oversized (adding looseness), but cannot reliably make them slim/fitted (tightening requires reshaping fabric around the body).

Affected garment types:
- Top (fit: Slim, Regular, Oversized)
- Shirts (fit: Slim, Regular, Oversized)
- Pants (fit: Slim, Regular, Palazzo)
- Coord upper (same class of problem — tops are tops/shirts)
- Coord bottoms (bottom_fit: Slim for pants-type bottoms)

**Solution**: Not yet fixed.

## 4) Waist fit / Waist definition — not reliably working

Gemini struggles to reliably change the waist fit/definition style. It may partially apply the change but results are inconsistent. Same class of problem across both garment types.

Affected garment types:
- Dress (waist_fit: Cinched, Empire, Dropped, Relaxed)
- Jumpsuit (waist_definition: Belted, Cinched, Straight)

**Solution**: Not yet fixed.

## 5) Shirts — cuff style unreliable

Gemini inconsistently renders sleeve length (rolled vs full) depending on occasion. Cuff modifications (buttoned vs elastic) only work when sleeves are full length, which Gemini doesn't guarantee. We cannot dynamically control whether the base image shows cuffs or not.

Affected garment types:
- Shirts (cuff_style: Buttoned, Elastic)

**Solution**: Not yet fixed.
