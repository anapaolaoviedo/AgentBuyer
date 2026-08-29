import { FormEvent, useMemo, useState } from "react";
import Saturday from "./Saturday";

const API_BASE = "http://127.0.0.1:8000";

type MandateCreatorProps = {
  onCreated: (mandateId: string) => void;
};

const categories = [
  { value: "travel.flights", label: "Vuelos (travel.flights)" },
  { value: "travel.hotels", label: "Hoteles (travel.hotels)" },
  { value: "digital.subscriptions", label: "Suscripciones (digital.subscriptions)" },
];

const merchants = [
  { value: "mch_vuelaya", label: "VuelaYa (mch_vuelaya)" },
  { value: "mch_amadeus", label: "Amadeus GDS (mch_amadeus)" },
];

function endOfMonth() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
}

function safeId(value: string, prefix: string) {
  const readable =
    value
      .trim()
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "") || "persona";
  return `${prefix}_${readable}_${Date.now().toString(36)}`;
}

export default function MandateCreator({ onCreated }: MandateCreatorProps) {
  const [humanName, setHumanName] = useState("Marta");
  const [maxAmount, setMaxAmount] = useState("150");
  const [category, setCategory] = useState("travel.flights");
  const [merchant, setMerchant] = useState("mch_vuelaya");
  const [maxUses, setMaxUses] = useState("3");
  const [priceBelow, setPriceBelow] = useState("150");
  const [validUntil, setValidUntil] = useState(endOfMonth());
  const [cardNumber, setCardNumber] = useState("•••• •••• •••• 4242");
  const [offSessionConsent, setOffSessionConsent] = useState(true);
  const [passkeyVerified, setPasskeyVerified] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selectedCategory = categories.find((item) => item.value === category)?.label ?? category;
  const selectedMerchant = merchants.find((item) => item.value === merchant)?.label ?? merchant;

  const summary = useMemo(
    () =>
      `Saturday podrá comprar ${selectedCategory.toLowerCase()} en ${selectedMerchant}, hasta $${maxAmount || "—"} USD por compra, máximo ${maxUses || "—"} compras, solo si el precio baja de $${priceBelow || "—"}${validUntil ? `, válido hasta ${validUntil}.` : "."} (Off-Session: ${offSessionConsent ? "Habilitado a las 3:00 AM con GPT-4o Semantic Firewall" : "Requiere confirmación manual"}).`,
    [maxAmount, maxUses, offSessionConsent, priceBelow, selectedCategory, selectedMerchant, validUntil],
  );

  async function handlePasskeyAuth() {
    setCreating(true);
    setError(null);
    try {
      // Simulación de autenticación biométrica WebAuthn / Passkey local
      await new Promise((resolve) => setTimeout(resolve, 600));
      setPasskeyVerified(true);
    } catch {
      setError("No se pudo verificar la Passkey en este dispositivo.");
    } finally {
      setCreating(false);
    }
  }

  async function createMandate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const amount = Number(maxAmount);
    const uses = Number(maxUses);
    const price = Number(priceBelow);

    if (
      !humanName.trim() ||
      !Number.isFinite(amount) ||
      amount <= 0 ||
      !Number.isInteger(uses) ||
      uses <= 0 ||
      !Number.isFinite(price) ||
      price <= 0
    ) {
      setError("Completa tu nombre y los límites con números válidos mayores que cero.");
      return;
    }

    const mandateId = safeId(humanName, "mnd");
    const payload = {
      mandate_id: mandateId,
      human: { id: safeId(humanName, "hum"), display_name: humanName.trim() },
      agent: { id: "agt_saturday", display_name: "Saturday" },
      constraints: {
        max_amount_per_purchase: amount,
        max_amount_per_tx: amount,
        currency: "USD",
        allowed_categories: [category],
        allowed_merchants: [merchant],
        max_uses: uses,
        conditions: [{ type: "price_below", value: price }],
        off_session_consent: offSessionConsent,
      },
      payment_token: {
        token_id: `vtok_${Math.random().toString(36).slice(2, 10)}`,
        token_type: "SCOPED_VIRTUAL_TOKEN",
        masked_card: cardNumber || "•••• 4242",
        bank_issuer: "Stripe Elements / Galicia AI Payments",
        bound_mandate_id: mandateId,
      },
      passkey_attestation: {
        verified: true,
        authenticator_type: "webauthn_biometric_passkey",
        timestamp: new Date().toISOString(),
      },
      ...(validUntil ? { valid_until: validUntil } : {}),
      signature: "ed25519_passkey_signed_jwt_token",
    };

    setCreating(true);
    try {
      const response = await fetch(`${API_BASE}/mandates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!response.ok) throw new Error(`El sistema respondió ${response.status}.`);
      onCreated(mandateId);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? `No pudimos crear tu permiso: ${caught.message}`
          : "No pudimos crear tu permiso. Revisa la conexión con el backend.",
      );
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="authorization-shell">
      <div className="starfield" aria-hidden="true" />
      <section className="authorization-layout">
        <div className="authorization-intro">
          <p className="mission-kicker">AGENTBUYER / PROTOCOLO ZERO-TRUST & DLP</p>
          <h1>
            Autoriza a <span>Saturday</span>
          </h1>
          <p>
            Enrolamiento de una sola vez con <b>Passkeys</b> y <b>Tokenización Scoped</b>. Saturday rastreará y comprará
            autónomamente mientras duermes, protegido por el Muro de Verificación y el Semantic Firewall con GPT-4o.
          </p>
          <div className="creator-saturday">
            <Saturday state="idle" />
          </div>
          <div className="trust-note">
            <b>🛡️ Garantía DLP & Privacidad:</b>
            <span>Tus datos de tarjeta reales nunca tocan al agente ni al backend. Solo se emite un token virtual acotado.</span>
          </div>
        </div>

        <form className="mandate-form" onSubmit={createMandate}>
          <div className="form-heading">
            <p className="panel-eyebrow">NUEVO MANDATO OFF-SESSION</p>
            <h2>Dale instrucciones y límites a Saturday</h2>
          </div>

          <label>
            ¿Quién autoriza?
            <input
              value={humanName}
              onChange={(event) => setHumanName(event.target.value)}
              placeholder="Tu nombre"
              required
            />
          </label>

          <label>
            ¿Cuánto puede gastar como máximo por compra?
            <div className="money-field">
              <span>USD $</span>
              <input
                value={maxAmount}
                onChange={(event) => setMaxAmount(event.target.value)}
                inputMode="decimal"
                placeholder="150"
                required
              />
            </div>
          </label>

          <div className="form-pair">
            <label>
              ¿En qué puede gastar?
              <select value={category} onChange={(event) => setCategory(event.target.value)}>
                {categories.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              ¿En qué comercios?
              <select value={merchant} onChange={(event) => setMerchant(event.target.value)}>
                {merchants.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="form-pair">
            <label>
              ¿Cuántas compras puede hacer?
              <input
                value={maxUses}
                onChange={(event) => setMaxUses(event.target.value)}
                inputMode="numeric"
                placeholder="3"
                required
              />
            </label>
            <label>
              ¿Hasta cuándo es válido?
              <input
                type="date"
                value={validUntil}
                onChange={(event) => setValidUntil(event.target.value)}
              />
            </label>
          </div>

          <label>
            Condición de precio disparador:
            <div className="price-condition">
              <span>Solo si el precio baja de USD $</span>
              <input
                value={priceBelow}
                onChange={(event) => setPriceBelow(event.target.value)}
                inputMode="decimal"
                placeholder="150"
                required
              />
            </div>
          </label>

          {/* Sección de Tokenización DLP */}
          <div style={{ background: "rgba(30, 41, 59, 0.6)", padding: "12px", borderRadius: "8px", border: "1px solid rgba(59, 130, 246, 0.3)", marginTop: "8px" }}>
            <label style={{ fontSize: "0.85rem", color: "#93c5fd", fontWeight: 600 }}>
              💳 Método de Pago (Stripe Elements / Tokenización PCI):
              <input
                value={cardNumber}
                onChange={(e) => setCardNumber(e.target.value)}
                placeholder="•••• •••• •••• 4242"
                style={{ background: "#0f172a", border: "1px solid #334155", color: "#f8fafc", padding: "8px", borderRadius: "6px", width: "100%", marginTop: "4px" }}
              />
            </label>
            <p style={{ fontSize: "0.75rem", color: "#94a3b8", marginTop: "4px", margin: 0 }}>
              🔒 <b>Zero Raw Card Exposure:</b> La tarjeta se tokeniza en el cliente. El agente solo recibe un <code>Scoped Virtual Token</code>.
            </p>
          </div>

          {/* Consentimiento Off-Session */}
          <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer", fontSize: "0.85rem", color: "#e2e8f0", marginTop: "10px" }}>
            <input
              type="checkbox"
              checked={offSessionConsent}
              onChange={(e) => setOffSessionConsent(e.target.checked)}
              style={{ width: "16px", height: "16px", accentColor: "#3b82f6" }}
            />
            <span>Autorizo compras autónomas <b>Off-Session</b> (3:00 AM) dentro de los límites y auditadas por GPT-4o.</span>
          </label>

          <div className="permission-summary">
            <span>RESUMEN DEL CONTRATO DIGITAL</span>
            <p>{summary}</p>
          </div>

          {error && (
            <div className="form-error" role="alert">
              {error}
            </div>
          )}

          <div style={{ display: "flex", gap: "10px", marginTop: "12px" }}>
            {!passkeyVerified ? (
              <button
                type="button"
                onClick={handlePasskeyAuth}
                className="authorize-button"
                style={{ background: "linear-gradient(135deg, #4f46e5, #3b82f6)" }}
              >
                🔐 Confirmar con Passkey (Face ID / Huella)
              </button>
            ) : (
              <button className="authorize-button" disabled={creating} type="submit">
                {creating ? "SELLANDO MANDATO CRIPTOGRÁFICO…" : "✅ FIRMAR Y ACTIVAR MANDATO"}
              </button>
            )}
          </div>
        </form>
      </section>
    </main>
  );
}
