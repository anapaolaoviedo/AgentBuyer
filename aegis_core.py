import jwt
import time
import sys
import os
import json

# Compatibilidad con consolas Windows (UTF-8)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from mandate.intelligent_issuer import emitir_mandato_inteligente
from core.semantic_firewall import auditoria_cognitiva_firewall

# ==========================================
# CONFIGURACIÓN DE SEGURIDAD (TÚ DOMINIO)
# ==========================================
LLAVE_SECRETA = "aegis_zero_trust_2026_super_secret"

# Simulamos la Base de Datos ultrarrápida (Redis/SQL) para el "Kill Switch"
base_de_datos_mandatos = {
    "M-001": "ACTIVE",
    "M-002": "ACTIVE"
}

# ==========================================
# PIEZA 2: EMISIÓN DEL MANDATO INTELIGENTE (IA + CRIPTOGRAFÍA + DLP)
# ==========================================
def emitir_mandato_lenguaje_natural(directiva_humana: str, mandate_id="M-001"):
    """
    El humano habla en lenguaje natural.
    El Agente Emisor de IA razona matices, deduce límites implícitos y sella el JWT.
    """
    mandate_obj, estructura_ia = emitir_mandato_inteligente(
        directiva_humana=directiva_humana,
        presupuesto_referencia=500.0,
    )
    
    # Extraemos el payload estructurado por la IA
    payload = {
        "mandate_id": mandate_id,
        "human_directive": directiva_humana,
        "ai_intent_summary": estructura_ia.get("intent_summary"),
        "constraints": {
            "max_amount": estructura_ia.get("max_amount_per_purchase", 150.0),
            "category": "flight",
            "allowed_categories": estructura_ia.get("allowed_categories", ["travel.flights", "travel"]),
            "conditions_expression": estructura_ia.get("conditions_expression", "price <= 150"),
        },
        "payment_token": mandate_obj.payment_token.token_id,  # DLP Token
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600
    }

    token_firmado = jwt.encode(payload, LLAVE_SECRETA, algorithm="HS256")
    return token_firmado, estructura_ia


# ==========================================
# PIEZA 3: LA PASARELA DE VERIFICACIÓN / SEMANTIC FIREWALL (AUDITOR COGNITIVO)
# ==========================================
def pasarela_verificacion_cognitiva(
    token_agente: str,
    item_titulo: str,
    item_descripcion: str,
    intento_precio: float,
    intento_categoria: str,
    metadata: dict = None
):
    """
    Intercepta la compra, valida la firma, checa el Kill Switch en vivo
    y ejecuta la Auditoría Cognitiva con Chain-of-Thought para detectar trampas ocultas.
    """
    if metadata is None:
        metadata = {}

    # 1. Verificación Criptográfica (Tamper-proofing)
    try:
        mandato_decodificado = jwt.decode(token_agente, LLAVE_SECRETA, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return {"status": "REJECTED", "mensaje": "❌ 403 RECHAZADO: El mandato ha expirado."}
    except jwt.InvalidSignatureError:
        return {"status": "REJECTED", "mensaje": "❌ 403 RECHAZADO: Firma inválida. Posible manipulación del agente."}
    except Exception as e:
        return {"status": "REJECTED", "mensaje": f"❌ 403 RECHAZADO: Token corrupto ({str(e)})."}

    mandate_id = mandato_decodificado["mandate_id"]
    reglas = mandato_decodificado["constraints"]

    # 2. El "Kill Switch" (Verificación en vivo en Base de Datos)
    estado_actual = base_de_datos_mandatos.get(mandate_id, "UNKNOWN")
    if estado_actual == "REVOKED":
        return {
            "status": "REJECTED",
            "mensaje": f"❌ 403 RECHAZADO: El mandato {mandate_id} fue REVOCADO por el usuario en tiempo real."
        }

    # 3. Auditoría Cognitiva & Cadena de Pensamiento (Semantic Firewall)
    print("\n🧠 [SEMANTIC FIREWALL] Desplegando Cadena de Pensamiento (Chain of Thought)...")
    auditoria = auditoria_cognitiva_firewall(
        mandato_constraints={
            "max_amount_per_purchase": reglas["max_amount"],
            "allowed_categories": reglas.get("allowed_categories", [reglas["category"]]),
            "conditions_expression": reglas.get("conditions_expression"),
        },
        item_titulo=item_titulo,
        item_descripcion=item_descripcion,
        precio_declarado=intento_precio,
        categoria=intento_categoria,
        metadata=metadata,
    )

    cot = auditoria.get("chain_of_thought", "")
    costo_real = auditoria.get("costo_real_estimado", intento_precio)
    veredicto = auditoria.get("veredicto", "APPROVE")
    resumen = auditoria.get("resumen_para_humano", "")

    print(f"--- CADENA DE PENSAMIENTO DEL AUDITOR ---")
    print(f"{cot}")
    print(f"Costo real calculado: ${costo_real:.2f} | Veredicto: {veredicto}")
    print(f"-----------------------------------------\n")

    if veredicto == "REJECT":
        return {
            "status": "REJECTED",
            "mensaje": f"❌ 403 RECHAZADO POR TRAMPA OCULTA: {resumen} (Costo real: ${costo_real:.2f})",
            "auditoria": auditoria
        }
    elif veredicto == "ESCALATE":
        return {
            "status": "ESCALATED",
            "mensaje": f"⚠️ 300 ESCALADO APROBACIÓN HUMANA (HITL): {resumen}",
            "auditoria": auditoria
        }

    return {
        "status": "APPROVED",
        "mensaje": f"✅ 200 APROBADO: Compra legítima de ${intento_precio:.2f} en '{item_titulo}' autorizada.",
        "auditoria": auditoria
    }


# ==========================================
# DEMOSTRACIÓN COMPLETA PARA LOS JUECES
# ==========================================
if __name__ == "__main__":
    print("=" * 75)
    print("🛡️ AEGIS: ZERO-TRUST AGENTIC COMMERCE & COGNITIVE AUDITOR")
    print("=" * 75)

    # -------------------------------------------------------------
    # 1. PIEZA 2: EMISIÓN INTELIGENTE EN LENGUAJE NATURAL
    # -------------------------------------------------------------
    print("\n--- 1. PIEZA 2: HUMANO EMITE MANDATO EN LENGUAJE NATURAL ---")
    directiva = "Cómprame un vuelo a Córdoba para el fin de semana, pero no me dejes sin presupuesto para cenar, usa tu juicio"
    print(f"🗣️ Directiva Humana: \"{directiva}\"")
    
    mi_token, estructura_ia = emitir_mandato_lenguaje_natural(directiva, mandate_id="M-001")
    print(f"🤖 Razonamiento del Agente Emisor:\n   {estructura_ia.get('chain_of_thought')}")
    print(f"📋 Contrato Deducido: Tope por compra: ${estructura_ia.get('max_amount_per_purchase', 150):.2f} | Categorías: {estructura_ia.get('allowed_categories')}")
    print(f"🔐 Sello Criptográfico: JWT generado y blindado con token DLP.\n")

    # -------------------------------------------------------------
    # 2. PIEZA 3: CASO LIMPIO (Vuelo de $130 a Córdoba)
    # -------------------------------------------------------------
    print("--- 2. PIEZA 3: AGENTE INTENTA COMPRA VÁLIDA Y LIMPIA ($130) ---")
    res1 = pasarela_verificacion_cognitiva(
        token_agente=mi_token,
        item_titulo="Vuelo Buenos Aires (AEP) -> Córdoba (COR) Directo",
        item_descripcion="Vuelo regular sin cargos ocultos, incluye equipaje de mano.",
        intento_precio=130.0,
        intento_categoria="flight",
        metadata={"destination": "COR", "stops": 0}
    )
    print(f"Resultado: {res1['mensaje']}\n")

    # -------------------------------------------------------------
    # 3. PIEZA 3: CASO TRAMPA OCULTA ($145 en pasarela pero con cargos por fuera y escala de 48h)
    # -------------------------------------------------------------
    print("--- 3. PIEZA 3: AGENTE INTENTA COMPRA CON TRAMPA OCULTA ($145 en pasarela) ---")
    print("ℹ️ Nota: Matemáticamente $145 <= $150, pero la letra chica contiene costos y condiciones abusivas.")
    res2 = pasarela_verificacion_cognitiva(
        token_agente=mi_token,
        item_titulo="Vuelo a Córdoba Promo",
        item_descripcion="Vuelo a Córdoba con escala de 48 horas e incluye upgrade automático a primera clase por $10 extra cobrados por fuera",
        intento_precio=145.0,
        intento_categoria="flight",
        metadata={"destination": "COR", "stops": 2}
    )
    print(f"Resultado: {res2['mensaje']}\n")

    # -------------------------------------------------------------
    # 4. PIEZA 3: AGENTE INTENTA FALSIFICAR FIRMA
    # -------------------------------------------------------------
    print("--- 4. PIEZA 3: AGENTE INTENTA ALTERAR LA FIRMA CRIPTOGRÁFICA ---")
    token_falsificado = mi_token[:-6] + "bad123"
    res3 = pasarela_verificacion_cognitiva(
        token_agente=token_falsificado,
        item_titulo="Vuelo a Córdoba",
        item_descripcion="Vuelo regular",
        intento_precio=130.0,
        intento_categoria="flight"
    )
    print(f"Resultado: {res3['mensaje']}\n")

    # -------------------------------------------------------------
    # 5. PIEZA 3: LA PRUEBA DE FUEGO (Live Revocation Kill Switch)
    # -------------------------------------------------------------
    print("--- 5. PIEZA 3: LA PRUEBA DE FUEGO (KILL SWITCH REVOCACIÓN EN VIVO) ---")
    print("🔴 El humano presiona el botón 'REVOCAR MANDATO M-001' en el panel.")
    base_de_datos_mandatos["M-001"] = "REVOKED"
    print("El agente comprador intenta comprar un vuelo válido ($120) un milisegundo después...")
    res4 = pasarela_verificacion_cognitiva(
        token_agente=mi_token,
        item_titulo="Vuelo Buenos Aires -> Córdoba",
        item_descripcion="Vuelo regular directo",
        intento_precio=120.0,
        intento_categoria="flight"
    )
    print(f"Resultado: {res4['mensaje']}\n")

    print("=" * 75)
    print("🏆 DEMOSTRACIÓN DE PIEZA 2 & PIEZA 3 CONCLUIDA CON ÉXITO")
    print("=" * 75)
