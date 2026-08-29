import streamlit as st
import pandas as pd
import json
import uuid
from datetime import datetime, timezone
import sys
import os

# Include parent directory in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from shared.schemas import MandateStatus, VerificationStatus, EventType, ActorType
from mandate.sign import generate_keypair
from mandate.issue import create_mandate
from core.mandate_store import mandate_store
from core.agent_loop import PurchasingAgent
from core.merchant import vuelaya_merchant
from core.verify import get_pending_escalations, resolve_escalation, verify_purchase
from core.dispute import dispute_arbiter
from audit.log import audit_ledger
from mandate.adversarial_tests import run_adversarial_suite

# Page Config
st.set_page_config(
    page_title="AgentBuyer // Safe Agentic Purchasing Protocol",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS for styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        letter-spacing: -0.02em;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #6c757d;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.2rem;
        border: 1px solid #e9ecef;
        margin-bottom: 1rem;
    }
    .trial-box {
        background: #fff3cd;
        border-left: 5px solid #ffc107;
        padding: 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .success-box {
        background: #d1e7dd;
        border-left: 5px solid #198754;
        padding: 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .danger-box {
        background: #f8d7da;
        border-left: 5px solid #dc3545;
        padding: 1rem;
        border-radius: 4px;
        margin-bottom: 1rem;
    }
    .code-chip {
        font-family: monospace;
        background: #e9ecef;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 0.88rem;
    }
</style>
""", unsafe_allow_html=True)

# Initialize Session State Keys & Demo State
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    # Keys for Marta & Agent
    h_priv, h_pub = generate_keypair()
    a_priv, a_pub = generate_keypair()
    st.session_state.human_keys = {"priv": h_priv, "pub": h_pub, "id": "marta_traveler"}
    st.session_state.agent_keys = {"priv": a_priv, "pub": a_pub, "id": "agent_marta"}
    
    # Pre-populate Marta's Fictional Mandate (Córdoba Flight <= $150)
    marta_mandate = create_mandate(
        human_id=st.session_state.human_keys["id"],
        human_privkey=st.session_state.human_keys["priv"],
        human_pubkey=st.session_state.human_keys["pub"],
        agent_id=st.session_state.agent_keys["id"],
        agent_pubkey=st.session_state.agent_keys["pub"],
        max_amount_per_tx=150.0,
        monthly_budget=500.0,
        allowed_categories=["travel", "flights"],
        allowed_merchants=["merch_vuelaya", "*"],
        conditions_expression="price <= 150 AND destination == 'COR'",
        currency="USD",
        max_executions_per_month=3,
        allow_hitl_escalation=True,
        validity_days=30,
        masked_card="•••• 4242",
        bank_issuer="Galicia AI Payments",
    )
    mandate_store.save_mandate(marta_mandate)
    
    audit_ledger.append_entry(
        event_type=EventType.MANDATE_CREATED,
        actor_type=ActorType.HUMAN,
        actor_id=st.session_state.human_keys["id"],
        mandate_id=marta_mandate.mandate_id,
        details={
            "summary": "Mandate created: Flight to Córdoba <= $150",
            "max_amount": 150.0,
            "monthly_budget": 500.0,
            "conditions": "price <= 150 AND destination == 'COR'",
            "payment_token": marta_mandate.payment_token.token_id,
        },
        signature=marta_mandate.human_signature,
    )
    
    st.session_state.active_mandate_id = marta_mandate.mandate_id

# Sidebar Navigation & System Status
st.sidebar.markdown("### 🛡️ **AgentBuyer Circuit**")
st.sidebar.markdown("**Safe Agentic Purchase Protocol**")
st.sidebar.markdown("---")

integrity_ok, integrity_msg = audit_ledger.verify_chain_integrity()
if integrity_ok:
    st.sidebar.success(f"🔒 **Ledger Integrity:** Verified\n\nBlocks: {len(audit_ledger._entries)}")
else:
    st.sidebar.error(f"⚠️ **Ledger Alert:** {integrity_msg}")

st.sidebar.markdown("---")
st.sidebar.markdown("#### 🔑 **Cryptographic Identities**")
st.sidebar.markdown(f"**Human (Marta):** `{st.session_state.human_keys['id']}`")
st.sidebar.markdown(f"**Pubkey:** `{st.session_state.human_keys['pub'][:16]}...`")
st.sidebar.markdown(f"**Agent:** `{st.session_state.agent_keys['id']}`")
st.sidebar.markdown(f"**Pubkey:** `{st.session_state.agent_keys['pub'][:16]}...`")
st.sidebar.markdown(f"**Merchant:** `merch_vuelaya` (VuelaYa)")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reset Demo State"):
    mandate_store.clear()
    audit_ledger.clear()
    st.session_state.clear()
    st.rerun()

# Top Header
st.markdown("<div class='main-header'>AgentBuyer // El comprador que no es humano</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Cryptographic purchase mandates, real-time merchant verification, live revocation trial-by-fire & tamper-evident dispute arbitration.</div>", unsafe_allow_html=True)

# Main Multi-Perspective Tabs
tab_human, tab_agent, tab_merchant, tab_auditor, tab_presentation = st.tabs([
    "👤 1. Human (Marta)",
    "🤖 2. Autonomous Agent",
    "🏪 3. Merchant (VuelaYa)",
    "⚖️ 4. Auditor & Disputes",
    "📊 5. Pitch & Architecture",
])

# -------------------------------------------------------------
# TAB 1: HUMAN INTERFACE (MARTA)
# -------------------------------------------------------------
with tab_human:
    st.markdown("### 👤 **Human Command Center (Marta)**")
    st.markdown("Define what your AI agent can buy, set non-negotiable boundaries, manage scoped virtual cards, and execute **Live Revocations**.")

    col1, col2 = st.columns([1.2, 1])

    with col1:
        st.markdown("#### 📜 **Active Purchase Mandates**")
        mandates = mandate_store.list_mandates(st.session_state.human_keys["id"])
        
        if not mandates:
            st.info("No active mandates found. Create one below.")
        else:
            for m in mandates:
                with st.container():
                    st.markdown(f"""
                    <div class='metric-card'>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <span style='font-size:1.15rem; font-weight:700;'>Mandate ID: <code>{m.mandate_id}</code></span>
                            <span style='padding:4px 10px; border-radius:12px; font-weight:bold; font-size:0.85rem; background:{
                                "#198754" if m.status == MandateStatus.ACTIVE else "#dc3545" if m.status == MandateStatus.REVOKED else "#6c757d"
                            }; color:white;'>{m.status.value}</span>
                        </div>
                        <hr style='margin:0.6rem 0;'>
                        <div><b>Max por Compra:</b> ${m.scope.max_amount_per_tx:.2f} {m.scope.currency} | <b>Presupuesto Mensual:</b> ${m.scope.monthly_budget:.2f}</div>
                        <div><b>Regla de Condición:</b> <code>{m.scope.conditions_expression or 'Ninguna'}</code></div>
                        <div><b>Categorías Autorizadas:</b> {', '.join(m.scope.allowed_categories)} | <b>Comercios:</b> {', '.join(m.scope.allowed_merchants)}</div>
                        
                        <div style='margin-top:10px; background:#e8f4fd; border:1px solid #b6d4fe; border-radius:8px; padding:8px 12px;'>
                            <div style='font-weight:700; color:#084298;'>🛡️ Garantía DLP (Data Loss Prevention):</div>
                            <div style='font-size:0.88rem; color:#084298;'>• <b>Tarjeta Real Aislada:</b> El agente no conoce tu PAN ni CVV.</div>
                            <div style='font-size:0.88rem; color:#084298;'>• <b>Token Scoped:</b> <code>{m.payment_token.token_id}</code> ({m.payment_token.masked_card} - {m.payment_token.bank_issuer})</div>
                        </div>

                        <div style='margin-top:8px; background:#f0fdf4; border:1px solid #bbf7d0; border-radius:8px; padding:8px 12px;'>
                            <div style='font-weight:700; color:#166534;'>🔐 Sello Criptográfico & Integración Pieza 6:</div>
                            <div style='font-size:0.88rem; color:#166534;'>• <b>Firma Digital Humana:</b> <code title='{m.human_signature}'>{m.human_signature[:28]}...</code></div>
                            <div style='font-size:0.88rem; color:#166534;'>• <b>Registro Inmutable:</b> Enlazado al Merkle Ledger SHA-256 para resolución de disputas.</div>
                        </div>

                        {f"<div style='color:#dc3545; margin-top:8px; font-weight:bold;'>🚨 Revocado en Vivo: {m.revoked_at} (Motivo: {m.revocation_reason})</div>" if m.revoked_at else ""}
                    </div>
                    """, unsafe_allow_html=True)

                    # Action buttons per mandate
                    btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
                    with btn_col1:
                        if m.status == MandateStatus.ACTIVE:
                            if st.button("🚨 Revoke Mandate (Trial by Fire)", key=f"rev_{m.mandate_id}", type="primary"):
                                mandate_store.revoke_mandate(m.mandate_id, reason="Revoked live by Marta via Human Portal")
                                audit_ledger.append_entry(
                                    event_type=EventType.MANDATE_REVOKED,
                                    actor_type=ActorType.HUMAN,
                                    actor_id=st.session_state.human_keys["id"],
                                    mandate_id=m.mandate_id,
                                    details={"reason": "Revoked live by Marta via Human Portal"},
                                )
                                st.warning(f"Mandate {m.mandate_id} has been LIVE REVOKED! Any subsequent purchase will be immediately rejected.")
                                st.rerun()
                    with btn_col2:
                        if m.status == MandateStatus.ACTIVE:
                            if st.button("⏸️ Pause Mandate", key=f"pause_{m.mandate_id}"):
                                mandate_store.pause_mandate(m.mandate_id)
                                st.rerun()
                        elif m.status == MandateStatus.PAUSED:
                            if st.button("▶️ Resume Mandate", key=f"res_{m.mandate_id}"):
                                mandate_store.resume_mandate(m.mandate_id)
                                st.rerun()

    with col2:
        st.markdown("#### ⚡ **HITL Escalation Inbox (Human-in-the-Loop)**")
        pending_escalations = get_pending_escalations()
        
        if not pending_escalations:
            st.success("✅ Inbox zero: No pending escalations requiring human approval.")
        else:
            for esc in pending_escalations:
                st.markdown(f"""
                <div class='trial-box'>
                    <h5 style='margin-bottom:5px; color:#856404;'>⚠️ Approval Requested: ${esc.requested_amount:.2f}</h5>
                    <div><b>Item:</b> {esc.attempt.item_title}</div>
                    <div><b>Reason:</b> {esc.reason}</div>
                    <div><b>Mandate Limit:</b> ${esc.mandate_limit:.2f}</div>
                    <div><b>Attempt Nonce:</b> <code>{esc.attempt.nonce}</code></div>
                </div>
                """, unsafe_allow_html=True)
                
                note = st.text_input("Decision Note", value="Approved for urgent travel", key=f"note_{esc.escalation_id}")
                e_col1, e_col2 = st.columns(2)
                with e_col1:
                    if st.button("✅ Approve Purchase", key=f"app_{esc.escalation_id}", type="primary"):
                        res = resolve_escalation(
                            escalation_id=esc.escalation_id,
                            approved=True,
                            human_privkey=st.session_state.human_keys["priv"],
                            human_pubkey=st.session_state.human_keys["pub"],
                            note=note,
                        )
                        st.success(f"Approved! Settlement ID: {res.settlement_id}")
                        st.rerun()
                with e_col2:
                    if st.button("❌ Deny Purchase", key=f"deny_{esc.escalation_id}"):
                        resolve_escalation(
                            escalation_id=esc.escalation_id,
                            approved=False,
                            human_privkey=st.session_state.human_keys["priv"],
                            human_pubkey=st.session_state.human_keys["pub"],
                            note=note,
                        )
                        st.error("Purchase attempt denied.")
                        st.rerun()

    st.markdown("---")
    st.markdown("#### 🧠 **Emisión Inteligente de Mandatos con IA (Lenguaje Natural)**")
    st.caption("El humano no llena casillas rígidas: habla en lenguaje natural. El Agente Emisor de IA razona los matices y sella el mandato criptográfico con Scoped Virtual Tokens (DLP).")
    
    prompt_mandato = st.text_area(
        "Directiva en Lenguaje Natural para el Agente Emisor:",
        value="Cómprame un vuelo a Córdoba para el fin de semana, pero no me dejes sin presupuesto para cenar, usa tu juicio",
        height=80,
    )
    
    if st.button("🤖 Razonar Intención & Emitir Mandato Criptográfico", type="primary"):
        from mandate.intelligent_issuer import emitir_mandato_inteligente
        with st.spinner("Agente Emisor de IA razonando directiva y deduciendo restricciones..."):
            nuevo_mandato, estructura_ia = emitir_mandato_inteligente(
                directiva_humana=prompt_mandato,
                presupuesto_referencia=500.0,
                human_privkey=st.session_state.human_keys["priv"],
                human_pubkey=st.session_state.human_keys["pub"],
                agent_pubkey=st.session_state.agent_keys["pub"],
            )
            mandate_store.save_mandate(nuevo_mandato)
            audit_ledger.append_entry(
                event_type=EventType.MANDATE_CREATED,
                actor_type=ActorType.HUMAN,
                actor_id=st.session_state.human_keys["id"],
                mandate_id=nuevo_mandato.mandate_id,
                details={
                    "summary": estructura_ia.get("intent_summary"),
                    "chain_of_thought": estructura_ia.get("chain_of_thought"),
                    "max_amount": nuevo_mandato.scope.max_amount_per_tx,
                    "payment_token": nuevo_mandato.payment_token.token_id,
                },
                signature=nuevo_mandato.human_signature,
            )
        st.success(f"Mandato `{nuevo_mandato.mandate_id}` emitido con éxito.")
        st.info(f"🧠 **Cadena de Pensamiento del Agente Emisor:**\n\n{estructura_ia.get('chain_of_thought')}")
        st.rerun()

    st.markdown("---")
    st.markdown("#### ➕ **Crear Mandato Manual (Configuración Avanzada)**")
    with st.form("create_mandate_form"):
        f_col1, f_col2, f_col3 = st.columns(3)
        with f_col1:
            max_amount = st.number_input("Max Amount Per Purchase ($)", min_value=10.0, max_value=5000.0, value=150.0, step=10.0)
            monthly_budget = st.number_input("Monthly Budget ($)", min_value=50.0, max_value=20000.0, value=500.0, step=50.0)
        with f_col2:
            categories_str = st.text_input("Allowed Categories (comma-separated)", value="travel, flights, hospitality")
            merchants_str = st.text_input("Allowed Merchants (comma-separated or *)", value="merch_vuelaya, *")
        with f_col3:
            conditions_expr = st.text_input("Condition Expression (DSL)", value="price <= 150 AND destination == 'COR'")
            allow_hitl = st.checkbox("Allow Human Escalation (HITL)", value=True)
            validity_days = st.slider("Validity (Days)", min_value=1, max_value=90, value=30)
        
        submitted = st.form_submit_button("✍️ Sign & Issue Cryptographic Mandate", type="primary")
        if submitted:
            cats = [c.strip() for c in categories_str.split(",") if c.strip()]
            merchs = [m.strip() for m in merchants_str.split(",") if m.strip()]
            new_m = create_mandate(
                human_id=st.session_state.human_keys["id"],
                human_privkey=st.session_state.human_keys["priv"],
                human_pubkey=st.session_state.human_keys["pub"],
                agent_id=st.session_state.agent_keys["id"],
                agent_pubkey=st.session_state.agent_keys["pub"],
                max_amount_per_tx=max_amount,
                monthly_budget=monthly_budget,
                allowed_categories=cats,
                allowed_merchants=merchs,
                conditions_expression=conditions_expr if conditions_expr.strip() else None,
                currency="USD",
                max_executions_per_month=5,
                allow_hitl_escalation=allow_hitl,
                validity_days=validity_days,
            )
            mandate_store.save_mandate(new_m)
            audit_ledger.append_entry(
                event_type=EventType.MANDATE_CREATED,
                actor_type=ActorType.HUMAN,
                actor_id=st.session_state.human_keys["id"],
                mandate_id=new_m.mandate_id,
                details={
                    "summary": f"Created mandate for ${max_amount:.2f}",
                    "conditions": conditions_expr,
                    "payment_token": new_m.payment_token.token_id,
                },
                signature=new_m.human_signature,
            )
            st.success(f"Mandate {new_m.mandate_id} successfully signed and registered!")
            st.rerun()

# -------------------------------------------------------------
# TAB 2: AUTONOMOUS AGENT INTERFACE
# -------------------------------------------------------------
with tab_agent:
    st.markdown("### 🤖 **Autonomous Purchasing Agent Workspace**")
    st.markdown("The agent observes market deals, matches them against Marta's active mandate, constructs cryptographic purchase attempts, and executes.")

    agent = PurchasingAgent(
        agent_id=st.session_state.agent_keys["id"],
        agent_privkey=st.session_state.agent_keys["priv"],
        agent_pubkey=st.session_state.agent_keys["pub"],
    )

    mandates = mandate_store.list_mandates(st.session_state.human_keys["id"])
    if not mandates:
        st.warning("No mandates registered. Please create a mandate in Tab 1.")
    else:
        mandate_options = {f"{m.mandate_id} (Limit ${m.scope.max_amount_per_tx} | {m.status.value})": m for m in mandates}
        selected_label = st.selectbox("Select Active Mandate to Execute Against", list(mandate_options.keys()))
        selected_mandate = mandate_options[selected_label]

        st.markdown("#### ✈️ **Live Flight Deals & Catalog Scanner (VuelaYa)**")
        catalog = vuelaya_merchant.get_catalog()
        
        c_cols = st.columns(len(catalog))
        for idx, item in enumerate(catalog):
            with c_cols[idx]:
                st.markdown(f"""
                <div class='metric-card'>
                    <div style='font-weight:700; min-height:45px;'>{item.title}</div>
                    <div style='font-size:1.4rem; font-weight:800; color:#0d6efd; margin:5px 0;'>${item.price:.2f} <span style='font-size:0.8rem; color:#6c757d;'>USD</span></div>
                    <div style='font-size:0.85rem;'><b>Category:</b> {item.category}</div>
                    <div style='font-size:0.85rem;'><b>Destination:</b> {item.metadata.get('destination', 'N/A')}</div>
                </div>
                """, unsafe_allow_html=True)
                
                if st.button(f"🛒 Autonomous Buy", key=f"buy_{item.item_id}", type="primary"):
                    with st.spinner(f"Agent signing attempt for {item.title}..."):
                        attempt, result = agent.attempt_purchase(
                            mandate=selected_mandate,
                            item=item,
                            merchant=vuelaya_merchant,
                        )
                    
                    if result.authorized:
                        st.success(f"🎉 **PURCHASE SUCCESSFUL!**\n\n- Settlement: `{result.settlement_id}`\n- Token: `{result.dispute_token}`\n- Reason: {result.reason}")
                    elif result.status == VerificationStatus.ESCALATED_HITL:
                        st.warning(f"⚠️ **ESCALATED TO HUMAN (HITL)**\n\n{result.reason}\n\nCheck Human Tab to review and approve.")
                    else:
                        st.error(f"❌ **PURCHASE REJECTED**\n\n{result.reason}")

        st.markdown("---")
        st.markdown("#### 🎯 **Simular Escenarios y Auditoría Cognitiva en Vivo**")
        sc_col1, sc_col2, sc_col3, sc_col4 = st.columns(4)
        
        with sc_col1:
            st.markdown("##### 🟢 Escenario 1: Vuelo Limpio ($130)")
            st.caption("Vuelo a Córdoba ($130 <= $150). Pasa automáticamente.")
            if st.button("▶️ Ejecutar ($130)", key="sc1_btn"):
                flight = vuelaya_merchant.get_item("FLIGHT_COR_130")
                attempt, result = agent.attempt_purchase(selected_mandate, flight)
                st.rerun()

        with sc_col2:
            st.markdown("##### 🟡 Escenario 2: Vuelo Excedido ($300)")
            st.caption("Vuelo a Córdoba ($300 > $150). Escala al humano (HITL).")
            if st.button("▶️ Ejecutar ($300)", key="sc2_btn"):
                flight = vuelaya_merchant.get_item("FLIGHT_COR_300")
                attempt, result = agent.attempt_purchase(selected_mandate, flight)
                st.rerun()

        with sc_col3:
            st.markdown("##### 🔴 Escenario 3: Kill Switch (Revocado)")
            st.caption("Prueba de fuego: Revoca el mandato y rechaza la compra al milisegundo.")
            if st.button("▶️ Revocar & Probar", key="sc3_btn"):
                mandate_store.revoke_mandate(selected_mandate.mandate_id, reason="Prueba de Fuego ante Jueces")
                flight = vuelaya_merchant.get_item("FLIGHT_COR_130")
                attempt, result = agent.attempt_purchase(selected_mandate, flight)
                st.rerun()

        with sc_col4:
            st.markdown("##### 🧠 Escenario 4: Trampa Oculta ($145 + Costos)")
            st.caption("Declara $145 pero letra chica incluye $10 extra y 48h de escala. La IA detecta la trampa.")
            if st.button("▶️ Probar Trampa Oculta", key="sc4_btn", type="primary"):
                from core.semantic_firewall import auditoria_cognitiva_firewall
                with st.spinner("Semantic Firewall ejecutando Auditoría Cognitiva con Chain of Thought..."):
                    auditoria = auditoria_cognitiva_firewall(
                        mandato_constraints={"max_amount_per_purchase": selected_mandate.scope.max_amount_per_tx, "allowed_categories": ["travel.flights"]},
                        item_titulo="Vuelo a Córdoba Promo con Escala",
                        item_descripcion="Vuelo a Córdoba con escala de 48 horas e incluye upgrade automático a primera clase por $10 extra cobrados por fuera",
                        precio_declarado=145.0,
                        categoria="flight",
                        metadata={"destination": "COR"}
                    )
                st.error(f"❌ **COMPRA VETADA POR EL AUDITOR COGNITIVO**\n\n**Veredicto:** {auditoria.get('veredicto')}\n\n**Costo Real Calculado:** ${auditoria.get('costo_real_estimado', 155):.2f}\n\n**Cadena de Pensamiento (Chain of Thought):**\n\n{auditoria.get('chain_of_thought')}")


        st.markdown("---")
        st.markdown("#### 🛡️ **Adversarial Security Attack Sandbox (8 Vectors)**")
        st.markdown("Run automated adversarial attack simulations to prove full defense against malicious agents, prompt injection, and replay exploits.")
        
        if st.button("🔥 Run Full Adversarial Attack Test Suite (8 Vectors)", type="primary"):
            with st.spinner("Executing attack vectors against verification perimeter..."):
                passed = run_adversarial_suite()
            if passed:
                st.success("🏆 **ALL 8 ADVERSARIAL ATTACK VECTORS BLOCKED WITH ZERO BREACHES!** (See Auditor Tab for logs)")
            else:
                st.error("Some adversarial attacks failed.")

# -------------------------------------------------------------
# TAB 3: MERCHANT TERMINAL (VUELAYA)
# -------------------------------------------------------------
with tab_merchant:
    st.markdown("### 🏪 **Merchant Terminal (VuelaYa Online Travel Agency)**")
    st.markdown("How merchants safely accept agent purchases: 6-stage independent verification protocol, zero fraud exposure, and cryptographic settlement.")

    m_col1, m_col2 = st.columns([1, 1.2])

    with m_col1:
        st.markdown("#### 📦 **Settled Orders & Transactions**")
        if not vuelaya_merchant.settled_orders:
            st.info("No orders settled yet. Run a purchase in Tab 2.")
        else:
            for ord in reversed(vuelaya_merchant.settled_orders[-5:]):
                st.markdown(f"""
                <div class='success-box'>
                    <div style='display:flex; justify-content:space-between;'>
                        <b>{ord['item_title']}</b>
                        <span style='color:#198754; font-weight:bold;'>${ord['amount']:.2f} {ord['currency']}</span>
                    </div>
                    <div style='font-size:0.85rem; margin-top:4px;'><b>Settlement ID:</b> <code>{ord['settlement_id']}</code></div>
                    <div style='font-size:0.85rem;'><b>Dispute Token:</b> <code>{ord['dispute_token']}</code></div>
                    <div style='font-size:0.8rem; color:#6c757d;'>Time: {ord['timestamp']}</div>
                </div>
                """, unsafe_allow_html=True)

    with m_col2:
        st.markdown("#### 🔍 **Merchant Verification Protocol Diagnostic**")
        merchant_trail = audit_ledger.get_trail_for("merchant")
        if not merchant_trail:
            st.info("No verification attempts logged yet.")
        else:
            for entry in reversed(merchant_trail[-6:]):
                auth = entry.get("authorized", False)
                st.markdown(f"""
                <div class='metric-card' style='border-left: 5px solid {"#198754" if auth else "#dc3545"};'>
                    <div style='display:flex; justify-content:space-between;'>
                        <b>Event: {entry.get("event")}</b>
                        <span style='font-weight:bold; color:{"#198754" if auth else "#dc3545"};'>{"APPROVED" if auth else "REJECTED/ESCALATED"}</span>
                    </div>
                    <div style='font-size:0.85rem; margin-top:4px;'><b>Attempt ID:</b> <code>{entry.get("attempt_id")}</code></div>
                    <div style='font-size:0.85rem;'><b>Mandate ID:</b> <code>{entry.get("mandate_id")}</code></div>
                    <div style='font-size:0.85rem;'><b>Checks Passed:</b> <code>{json.dumps(entry.get("verification_checks", {}))}</code></div>
                    <div style='font-size:0.8rem; color:#6c757d;'>Time: {entry.get("time")}</div>
                </div>
                """, unsafe_allow_html=True)

# -------------------------------------------------------------
# TAB 4: AUDITOR & DISPUTES
# -------------------------------------------------------------
with tab_auditor:
    st.markdown("### ⚖️ **Auditor & Chargeback Dispute Court**")
    st.markdown("Immutable SHA-256 Merkle chain explorer, deterministic liability attribution, and role-based audit logs.")

    d_col1, d_col2 = st.columns([1.2, 1])

    with d_col1:
        st.markdown("#### 🏛️ **File & Resolve a Chargeback Dispute**")
        st.markdown("When a human cardholder denies a charge (*'I never authorized this'*), the court replays the cryptographic audit trail to prove who is liable.")
        
        all_attempts = [e for e in audit_ledger.get_all_entries() if e.event_type == EventType.PURCHASE_ATTEMPTED.value]
        
        if not all_attempts:
            st.info("No purchase attempts available to dispute yet. Execute a purchase first.")
        else:
            attempt_opts = {f"Attempt {e.attempt_id} (Mandate {e.mandate_id})": e for e in all_attempts}
            sel_attempt_label = st.selectbox("Select Purchase Attempt to Dispute", list(attempt_opts.keys()))
            sel_attempt_entry = attempt_opts[sel_attempt_label]
            
            dispute_reason = st.text_input("Cardholder Dispute Reason", value="I did not authorize my agent to purchase this flight!")
            
            if st.button("⚖️ File Dispute & Execute Mathematical Arbitration", type="primary"):
                claim = dispute_arbiter.file_dispute(
                    attempt_id=sel_attempt_entry.attempt_id,
                    mandate_id=sel_attempt_entry.mandate_id,
                    claimant_id=st.session_state.human_keys["id"],
                    reason=dispute_reason,
                )
                st.rerun()

        # Display Filed Disputes
        disputes = dispute_arbiter.list_disputes()
        if disputes:
            st.markdown("##### **Arbitration Verdicts & Proofs**")
            for d in reversed(disputes):
                st.markdown(f"""
                <div class='metric-card' style='border-left: 5px solid {"#198754" if d.liable_party == "HUMAN" else "#dc3545"};'>
                    <div style='display:flex; justify-content:space-between;'>
                        <b>Dispute ID: <code>{d.dispute_id}</code></b>
                        <span style='padding:3px 8px; border-radius:8px; font-weight:bold; background:#e9ecef;'>Status: {d.status}</span>
                    </div>
                    <div style='margin-top:6px;'><b>Liable Party:</b> <span style='font-size:1.1rem; font-weight:bold; color:{"#dc3545" if d.liable_party != "HUMAN" else "#198754"};'>{d.liable_party}</span></div>
                    <div><b>Verdict Code:</b> <code>{d.verdict}</code></div>
                    <div><b>Refund Issued:</b> {'YES' if d.refund_issued else 'NO (Chargeback Dismissed)'}</div>
                    <div style='margin-top:6px; background:#ffffff; padding:8px; border-radius:6px; border:1px solid #dee2e6;'>
                        <b>Mathematical Determination:</b><br>{d.explanation}
                    </div>
                </div>
                """, unsafe_allow_html=True)

    with d_col2:
        st.markdown("#### 📜 **Cryptographic Merkle Hash Chain**")
        all_entries = audit_ledger.get_all_entries()
        st.metric(label="Total Hash-Chained Blocks", value=len(all_entries), delta="100% Tamper Evident")
        
        if all_entries:
            df_entries = pd.DataFrame([
                {
                    "Index": e.index,
                    "Event": e.event_type,
                    "Actor": f"{e.actor_type} ({e.actor_id})",
                    "Hash": e.hash[:12] + "...",
                    "Prev Hash": e.prev_hash[:12] + "...",
                    "Time": e.timestamp.split("T")[1][:8],
                }
                for e in all_entries
            ])
            st.dataframe(df_entries, use_container_width=True, hide_index=True)

# -------------------------------------------------------------
# TAB 5: PITCH DECK & ARCHITECTURE
# -------------------------------------------------------------
with tab_presentation:
    st.markdown("### 📊 **Hackathon Pitch Deck & Architecture Overview**")
    st.markdown("Everything needed to defend the project before the jury.")

    p_col1, p_col2 = st.columns([1, 1])

    with p_col1:
        st.markdown("""
        #### 🎯 **1. The Problem: The Non-Human Buyer Dilemma**
        - Payment systems assume a human is clicking 'Pay'.
        - AI agents are now making purchases autonomously (flights, restocking, subscriptions).
        - **Current broken status quo:**
          - Merchants either block all bots (losing legitimate revenue) or treat them as humans (eating chargebacks and fraud).
          - Users are terrified of giving raw card numbers to autonomous agents.
        
        #### 🛡️ **2. The Solution: AgentBuyer Protocol**
        - **Verifiable Cryptographic Mandates:** Human delegates precise purchasing authority with Ed25519 digital signatures.
        - **Zero Raw Card Exposure:** Payments use cryptographically bound scoped virtual tokens.
        - **Independent Merchant Verification:** 6-stage fail-closed validation pipeline checking live status, limits, and AST grammar.
        - **Trial by Fire Live Revocation:** Synchronous authoritative state registry terminates mandates instantly.
        - **Mathematical Dispute Arbitration:** SHA-256 hash chains resolve liability unequivocally.
        """)

    with p_col2:
        st.markdown("""
        #### 🏗️ **3. 4-Party Cryptographic Circuit**
        ```
        [ Human (Marta) ] 
               │ (1. Ed25519 Mandate + Scoped Token)
               ▼
        [ Mandate Registry ] ◄─── (4. Live Status / Revocation Check)
               ▲                                │
               │                                ▼
        [ AI Purchasing Agent ] ──(3. Signed Attempt)──► [ Merchant (VuelaYa) ]
               │                                                │
               ▼                                                ▼
        [ 📜 SHA-256 Merkle Audit Chain & Dispute Arbiter ] ◄────┘
        ```
        
        #### 🏆 **4. Key Achievements & Differentiators**
        - **Zero Breaches:** 8/8 adversarial attack vectors blocked in test suite.
        - **Human-In-The-Loop:** Graceful escalation for borderline deals instead of silent failure.
        - **Court-Ready Evidence:** Immutable append-only audit trail with role-customized views.
        """)
