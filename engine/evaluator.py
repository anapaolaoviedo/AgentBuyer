import traceback
from typing import Dict, Any, List, Optional, Tuple, Union

from engine.grammar import parse_and_evaluate


def _category_matches(attempt_cat: str, allowed_cats: List[str]) -> bool:
    """Case-insensitive, hierarchical matching for categories."""
    if not allowed_cats or "*" in allowed_cats:
        return True
    
    clean_attempt = attempt_cat.strip().lower()
    for allowed in allowed_cats:
        clean_allowed = allowed.strip().lower()
        if clean_allowed == "*" or clean_allowed == clean_attempt:
            return True
        # Hierarchical prefix check: "travel.flights" matches "flight" or "flights" or "travel.flights"
        if clean_attempt.endswith(clean_allowed) or clean_allowed.endswith(clean_attempt):
            return True
        if clean_attempt in clean_allowed or clean_allowed in clean_attempt:
            return True
    return False


def _merchant_matches(attempt_merchant: str, allowed_merchants: List[str]) -> bool:
    """Merchant whitelist matching. Empty list or '*' allows any merchant."""
    if not allowed_merchants or "*" in allowed_merchants:
        return True
    
    clean_attempt = attempt_merchant.strip().lower()
    for allowed in allowed_merchants:
        clean_allowed = allowed.strip().lower()
        if clean_allowed == "*" or clean_allowed == clean_attempt:
            return True
    return False


def evaluate(mandate: dict, live_state: dict, attempt: dict) -> dict:
    """
    Punto de entrada único del Engine Simbólico de Restricciones.
    
    Parámetros:
        mandate: dict con las restricciones (constraints)
        live_state: dict con el estado fresco en vivo (uses_count, amount_spent)
        attempt: dict con los datos del intento de compra (category, merchant_id, amount, metadata)
        
    Retorna SIEMPRE:
        {
            "verdict": "APPROVE" | "ESCALATE" | "REJECT",
            "checks": [ {"rule": str, "pass": bool, "detail": str}, ... ],
            "reason": str
        }
    """
    try:
        checks: List[Dict[str, Any]] = []
        failed_reasons: List[str] = []

        # 1. Extraer constraints del mandato
        constraints = mandate.get("constraints") or mandate.get("scope") or {}
        
        # 2. Monto máximo por compra
        max_amount = constraints.get("max_amount_per_purchase")
        if max_amount is None:
            max_amount = constraints.get("max_amount")
        if max_amount is None:
            max_amount = constraints.get("max_amount_per_tx", float("inf"))
        
        attempt_amount = float(attempt.get("amount", 0.0))
        amount_pass = attempt_amount <= max_amount
        checks.append({
            "rule": "amount",
            "pass": amount_pass,
            "detail": f"{attempt_amount:.2f} <= {max_amount:.2f}" if amount_pass else f"{attempt_amount:.2f} > {max_amount:.2f}"
        })
        if not amount_pass:
            failed_reasons.append(f"Monto (${attempt_amount:.2f}) excede límite de ${max_amount:.2f}")

        # 3. Categoría permitida
        allowed_categories = constraints.get("allowed_categories", ["*"])
        attempt_category = str(attempt.get("category", ""))
        category_pass = _category_matches(attempt_category, allowed_categories)
        checks.append({
            "rule": "category",
            "pass": category_pass,
            "detail": f"{attempt_category} permitida" if category_pass else f"Categoría '{attempt_category}' no permitida"
        })
        if not category_pass:
            failed_reasons.append(f"Categoría '{attempt_category}' no permitida")

        # 4. Comercio permitido (allowed_merchants)
        allowed_merchants = constraints.get("allowed_merchants", ["*"])
        attempt_merchant = str(attempt.get("merchant_id", ""))
        merchant_pass = _merchant_matches(attempt_merchant, allowed_merchants)
        checks.append({
            "rule": "merchant",
            "pass": merchant_pass,
            "detail": f"{attempt_merchant} permitido" if merchant_pass else f"Comercio '{attempt_merchant}' no permitido"
        })
        if not merchant_pass:
            failed_reasons.append(f"Comercio '{attempt_merchant}' no permitido")

        # 5. Usos máximos (max_uses vs live_state.uses_count)
        max_uses = constraints.get("max_uses")
        if max_uses is None:
            max_uses = constraints.get("max_executions_per_month")
            
        current_uses = int(live_state.get("uses_count", 0))
        if max_uses is not None:
            uses_pass = current_uses < max_uses
            checks.append({
                "rule": "uses",
                "pass": uses_pass,
                "detail": f"{current_uses}/{max_uses}" if uses_pass else f"Usos agotados ({current_uses}/{max_uses})"
            })
            if not uses_pass:
                failed_reasons.append(f"Usos agotados ({current_uses}/{max_uses})")
        else:
            checks.append({
                "rule": "uses",
                "pass": True,
                "detail": "Sin límite de usos"
            })

        # 6. Evaluación de conditions (estructuradas o expresiones DSL)
        raw_conditions = constraints.get("conditions", [])
        
        # Si conditions es una lista de objetos o strings
        if isinstance(raw_conditions, list):
            for idx, cond in enumerate(raw_conditions):
                if isinstance(cond, dict):
                    cond_type = cond.get("type", "custom")
                    if cond_type == "price_below":
                        threshold = float(cond.get("value", max_amount))
                        price_val = float(attempt.get("metadata", {}).get("price", attempt_amount))
                        c_pass = price_val <= threshold
                        checks.append({
                            "rule": "condition.price_below",
                            "pass": c_pass,
                            "detail": f"{price_val:.2f} <= {threshold:.2f}" if c_pass else f"{price_val:.2f} > {threshold:.2f}"
                        })
                        if not c_pass:
                            failed_reasons.append(f"Condición price_below no cumplida ({price_val:.2f} > {threshold:.2f})")
                    elif cond_type == "price_above":
                        threshold = float(cond.get("value", 0))
                        price_val = float(attempt.get("metadata", {}).get("price", attempt_amount))
                        c_pass = price_val >= threshold
                        checks.append({
                            "rule": "condition.price_above",
                            "pass": c_pass,
                            "detail": f"{price_val:.2f} >= {threshold:.2f}" if c_pass else f"{price_val:.2f} < {threshold:.2f}"
                        })
                        if not c_pass:
                            failed_reasons.append(f"Condición price_above no cumplida ({price_val:.2f} < {threshold:.2f})")
                    else:
                        # Condición genérica por campo
                        field_name = cond.get("field", "destination")
                        expected_val = cond.get("value")
                        actual_val = attempt.get("metadata", {}).get(field_name)
                        c_pass = str(actual_val).lower() == str(expected_val).lower() if actual_val is not None else False
                        checks.append({
                            "rule": f"condition.{cond_type}",
                            "pass": c_pass,
                            "detail": f"{field_name}={actual_val} vs {expected_val}"
                        })
                        if not c_pass:
                            failed_reasons.append(f"Condición {cond_type} falló ({field_name} != {expected_val})")
                elif isinstance(cond, str):
                    context = {
                        "price": attempt_amount,
                        "amount": attempt_amount,
                        "category": attempt_category,
                        "merchant": attempt_merchant,
                        "merchant_id": attempt_merchant,
                        **attempt.get("metadata", {})
                    }
                    c_pass = parse_and_evaluate(cond, context)
                    checks.append({
                        "rule": f"condition.expr_{idx}",
                        "pass": c_pass,
                        "detail": f"Expresión: {cond}"
                    })
                    if not c_pass:
                        failed_reasons.append(f"Condición '{cond}' no cumplida")

        # Expresión DSL string (conditions_expression)
        conditions_expr = constraints.get("conditions_expression")
        if conditions_expr and isinstance(conditions_expr, str):
            context = {
                "price": attempt_amount,
                "amount": attempt_amount,
                "category": attempt_category,
                "merchant": attempt_merchant,
                "merchant_id": attempt_merchant,
                **attempt.get("metadata", {})
            }
            c_pass = parse_and_evaluate(conditions_expr, context)
            checks.append({
                "rule": "condition.expression",
                "pass": c_pass,
                "detail": f"Expresión: {conditions_expr}"
            })
            if not c_pass:
                failed_reasons.append(f"Expresión '{conditions_expr}' no cumplida")

        # 7. Veredicto Final
        all_passed = all(c["pass"] for c in checks)
        
        if all_passed:
            verdict = "APPROVE"
            reason = "Todas las restricciones satisfechas"
        else:
            verdict = "ESCALATE"
            reason = "; ".join(failed_reasons) if failed_reasons else "Restricciones no satisfechas"

        return {
            "verdict": verdict,
            "checks": checks,
            "reason": reason
        }

    except Exception as e:
        # Fail-closed seguro: Nunca reventar ni devolver None
        return {
            "verdict": "REJECT",
            "checks": [
                {
                    "rule": "internal_error",
                    "pass": False,
                    "detail": str(e)
                }
            ],
            "reason": f"Error interno en evaluador: {str(e)}"
        }


# =====================================================================
# Adaptador para compatibilidad con Pydantic / Core existente
# =====================================================================
def evaluate_mandate_constraints(mandate, attempt, state) -> Tuple[bool, str, Dict[str, bool], bool]:
    """
    Wrapper compatible con el pipeline de core/verify.py.
    """
    mandate_dict = mandate.model_dump() if hasattr(mandate, "model_dump") else mandate
    attempt_dict = attempt.model_dump() if hasattr(attempt, "model_dump") else attempt
    state_dict = {
        "uses_count": getattr(state, "count_this_month", 0),
        "amount_spent": getattr(state, "spent_this_month", 0.0),
    }

    result = evaluate(mandate_dict, state_dict, attempt_dict)
    
    authorized = (result["verdict"] == "APPROVE")
    reason = result["reason"]
    checks_dict = {c["rule"]: c["pass"] for c in result["checks"]}
    can_escalate = (result["verdict"] == "ESCALATE")

    return authorized, reason, checks_dict, can_escalate
