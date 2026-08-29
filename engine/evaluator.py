# evaluate(mandate, live_state, attempt) -> dict — THE contracted entry point.
# Orchestrates: amount → category → merchant → uses → each condition →
# assemble checks[] → assign verdict (APPROVE / ESCALATE; REJECT only on internal error) → reason.
# Never raises, never returns None — always the full dict shape.
