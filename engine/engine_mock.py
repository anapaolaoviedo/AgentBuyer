"""Mock temporal del motor simbólico acordado por el equipo."""


def evaluate(mandate: dict, live_state: dict, attempt: dict) -> dict:
    """Simula una aprobación mientras se integra el engine real."""
    return {
        "verdict": "APPROVE",
        "checks": [
            {
                "rule": "mock_engine_available",
                "pass": True,
                "detail": "Mock temporal: el engine real se integrará después.",
            }
        ],
        "reason": "Aprobado por el mock del engine.",
    }
