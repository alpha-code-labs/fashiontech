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

## 1) Length — not working for all garments

Gemini cannot reliably extend garment length. Shortening works, extending does not.

Affected garment types:
- Dress
- Top
- Skirt
- Pants
- Jumpsuit
- Shirts
- Coord sets

**Solution**: Moved length selection to the buy flow. User picks length via WhatsApp buttons with descriptions at checkout. MHK sees the length choice in the order. Already deployed to production.

## 2) Waist rise — not working

Gemini cannot reliably render the difference between high/mid/low waist rise. The waistband position does not visibly change.

Affected garment types:
- Skirt (waist_rise: High, Mid, Low)
- Pants (rise: High, Mid, Low)

**Solution**: Not yet fixed.

## 3) Fit — going to slim not working

Gemini can make garments oversized (adding looseness), but cannot reliably make them slim/fitted (tightening requires reshaping fabric around the body — same structural problem as length and waist rise).

Affected garment types:
- Top (fit: Slim, Regular, Oversized)
- Pants (fit: Slim, Regular, Oversized)
- Shirts (fit: Slim, Regular, Oversized)

**Solution**: Not yet fixed.

## 4) Waist fit — not reliably working

Gemini struggles to reliably change the waist fit style. It may partially apply the change but results are inconsistent.

Affected garment types:
- Dress (waist_fit: Cinched, Empire, Dropped, Relaxed)

**Solution**: Not yet fixed.

## 5) Waist definition — not reliably working

Same class of problem as waist fit. Gemini struggles to visually differentiate between belted, cinched, and straight waist definitions.

Affected garment types:
- Jumpsuit (waist_definition: Belted, Cinched, Straight)

**Solution**: Not yet fixed.
