# pytest — the 5 contract test cases (mandate: max 150, travel.flights, mch_vuelaya, max 3 uses, price_below 150):
#   A: 130 / travel.flights / mch_vuelaya / uses 0 -> APPROVE   (everything fits)
#   B: 300 / travel.flights / mch_vuelaya / uses 0 -> ESCALATE  (amount exceeds cap)
#   C: 130 / hotel          / mch_vuelaya / uses 0 -> ESCALATE  (category not allowed)
#   D: 130 / travel.flights / mch_vuelaya / uses 3 -> ESCALATE  (uses exhausted)
#   E: 130 / travel.flights / otro_comercio / uses 0 -> ESCALATE (merchant not allowed)
# All 5 must pass before telling the team "engine is ready".
