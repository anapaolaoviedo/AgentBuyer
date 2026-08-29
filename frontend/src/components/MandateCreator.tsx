import { FormEvent, useMemo, useState } from "react";
import Saturday from "./Saturday";

const API_BASE = "http://127.0.0.1:8000";

type MandateCreatorProps = {
  onCreated: (mandateId: string) => void;
};

const categories = [
  { value: "travel.flights", label: "Vuelos" },
  { value: "travel.hotels", label: "Hoteles" },
  { value: "digital.subscriptions", label: "Suscripciones" },
];

const merchants = [{ value: "mch_vuelaya", label: "VuelaYa" }];

function endOfMonth() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
}

function safeId(value: string, prefix: string) {
  const readable = value.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "persona";
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
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selectedCategory = categories.find((item) => item.value === category)?.label ?? category;
  const selectedMerchant = merchants.find((item) => item.value === merchant)?.label ?? merchant;
  const summary = useMemo(
    () => `Saturday podrá comprar ${selectedCategory.toLowerCase()} en ${selectedMerchant}, hasta $${maxAmount || "—"} por compra, máximo ${maxUses || "—"} veces, solo si el precio baja de $${priceBelow || "—"}${validUntil ? `, válido hasta ${validUntil}.` : "."}`,
    [humanName, maxAmount, maxUses, priceBelow, selectedCategory, selectedMerchant, validUntil],
  );

  async function createMandate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const amount = Number(maxAmount);
    const uses = Number(maxUses);
    const price = Number(priceBelow);
    if (!humanName.trim() || !Number.isFinite(amount) || amount <= 0 || !Number.isInteger(uses) || uses <= 0 || !Number.isFinite(price) || price <= 0) {
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
        currency: "USD",
        allowed_categories: [category],
        allowed_merchants: [merchant],
        max_uses: uses,
        conditions: [{ type: "price_below", value: price }],
      },
      ...(validUntil ? { valid_until: validUntil } : {}),
      signature: "firma-de-prueba",
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
      setError(caught instanceof Error ? `No pudimos crear tu permiso: ${caught.message}` : "No pudimos crear tu permiso. Revisa la conexión con el sistema.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="authorization-shell">
      <div className="starfield" aria-hidden="true" />
      <section className="authorization-layout">
        <div className="authorization-intro">
          <p className="mission-kicker">AGENTBUYER / TU PERMISO, TUS LÍMITES</p>
          <h1>Autoriza a <span>Saturday</span></h1>
          <p>Tu agente puede ayudarte a comprar, pero tú defines cada límite. Nada ocurre fuera de este permiso.</p>
          <div className="creator-saturday"><Saturday state="idle" /></div>
          <div className="trust-note"><b>Tu control sigue primero.</b><span>Podrás revocar este permiso cuando quieras.</span></div>
        </div>

        <form className="mandate-form" onSubmit={createMandate}>
          <div className="form-heading"><p className="panel-eyebrow">NUEVO PERMISO</p><h2>Dale instrucciones claras a Saturday</h2></div>
          <label>¿Quién autoriza?<input value={humanName} onChange={(event) => setHumanName(event.target.value)} placeholder="Tu nombre" required /></label>
          <label>¿Cuánto puede gastar como máximo en cada compra?<div className="money-field"><span>USD $</span><input value={maxAmount} onChange={(event) => setMaxAmount(event.target.value)} inputMode="decimal" placeholder="150" required /></div></label>
          <div className="form-pair">
            <label>¿En qué puede gastar?<select value={category} onChange={(event) => setCategory(event.target.value)}>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label>¿En qué comercios?<select value={merchant} onChange={(event) => setMerchant(event.target.value)}>{merchants.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          </div>
          <div className="form-pair">
            <label>¿Cuántas compras puede hacer como máximo?<input value={maxUses} onChange={(event) => setMaxUses(event.target.value)} inputMode="numeric" placeholder="3" required /></label>
            <label>¿Hasta cuándo es válido este permiso?<input type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} /></label>
          </div>
          <label>¿Alguna condición de precio?<div className="price-condition"><span>Solo si el precio baja de USD $</span><input value={priceBelow} onChange={(event) => setPriceBelow(event.target.value)} inputMode="decimal" placeholder="150" required /></div></label>
          <div className="permission-summary"><span>ASÍ SE VERÁ TU PERMISO</span><p>{summary}</p></div>
          {error && <div className="form-error" role="alert">{error}</div>}
          <button className="authorize-button" disabled={creating} type="submit">{creating ? "CREANDO TU PERMISO…" : "AUTORIZAR A SATURDAY"}</button>
        </form>
      </section>
    </main>
  );
}
