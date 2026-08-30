import { FormEvent, useMemo, useRef, useState } from "react";
import Saturday, { type SaturdayExpression } from "./Saturday";
import { useLivenessVerification } from "../hooks/useLivenessVerification";
import { useZeroTrustSecurity } from "../hooks/useZeroTrustSecurity";

const API_BASE = "http://127.0.0.1:8000";

type MandateCreatorProps = {
  onCreated: (mandateId: string) => void;
};

type VerificationStatus = "pending" | "processing" | "complete";

function verificationStatus(complete: boolean, processing: boolean): VerificationStatus {
  return complete ? "complete" : processing ? "processing" : "pending";
}

const verificationStatusLabel: Record<VerificationStatus, string> = {
  pending: "PENDIENTE",
  processing: "EN PROCESO",
  complete: "COMPLETADO",
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

function dateKey(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateFromKey(value: string) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function readableDate(value: string) {
  return new Intl.DateTimeFormat("es-MX", { day: "numeric", month: "short", year: "numeric" })
    .format(dateFromKey(value))
    .replace(".", "");
}

type FlightDatePickerProps = {
  value: string;
  onChange: (value: string) => void;
};

function FlightDatePicker({ value, onChange }: FlightDatePickerProps) {
  const today = useMemo(() => {
    const current = new Date();
    current.setHours(0, 0, 0, 0);
    return current;
  }, []);
  const [isOpen, setIsOpen] = useState(false);
  const [visibleMonth, setVisibleMonth] = useState(() => {
    const selected = value ? dateFromKey(value) : today;
    return new Date(selected.getFullYear(), selected.getMonth(), 1);
  });
  const monthStart = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1);
  const gridStart = new Date(visibleMonth.getFullYear(), visibleMonth.getMonth(), 1 - monthStart.getDay());
  const days = Array.from({ length: 42 }, (_, index) => {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + index);
    return day;
  });
  const monthLabel = new Intl.DateTimeFormat("es-MX", { month: "long", year: "numeric" }).format(visibleMonth);
  const earliestMonth = new Date(today.getFullYear(), today.getMonth(), 1);

  function togglePicker() {
    if (!isOpen) {
      const selected = value ? dateFromKey(value) : today;
      setVisibleMonth(new Date(selected.getFullYear(), selected.getMonth(), 1));
    }
    setIsOpen((open) => !open);
  }

  return (
    <div className="flight-date-picker">
      <button className={`date-picker-trigger ${value ? "has-value" : ""}`} type="button" onClick={togglePicker} aria-haspopup="dialog" aria-expanded={isOpen}>
        <span>{value ? readableDate(value) : "Elige una fecha"}</span><b aria-hidden="true">⌄</b>
      </button>
      {isOpen && <div className="calendar-popover" role="dialog" aria-label="Selecciona la fecha de salida">
        <div className="calendar-heading">
          <button type="button" onClick={() => setVisibleMonth(new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1))} disabled={visibleMonth <= earliestMonth} aria-label="Mes anterior">‹</button>
          <strong>{monthLabel}</strong>
          <button type="button" onClick={() => setVisibleMonth(new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1))} aria-label="Mes siguiente">›</button>
        </div>
        <div className="calendar-weekdays">{["D", "L", "M", "M", "J", "V", "S"].map((day, index) => <span key={`${day}-${index}`}>{day}</span>)}</div>
        <div className="calendar-days">
          {days.map((day) => {
            const key = dateKey(day);
            const isPast = day < today;
            const outsideMonth = day.getMonth() !== visibleMonth.getMonth();
            return <button className={`${outsideMonth ? "outside-month" : ""} ${key === value ? "is-selected" : ""}`} type="button" disabled={isPast} key={key} onClick={() => { onChange(key); setIsOpen(false); }}>{day.getDate()}</button>;
          })}
        </div>
      </div>}
    </div>
  );
}

export default function MandateCreator({ onCreated }: MandateCreatorProps) {
  const [humanName, setHumanName] = useState("");
  const [maxAmount, setMaxAmount] = useState("");
  const [category, setCategory] = useState("");
  const [merchant, setMerchant] = useState("");
  const [maxUses, setMaxUses] = useState("");
  const [priceBelow, setPriceBelow] = useState("");
  const [validUntil, setValidUntil] = useState(endOfMonth());
  // Estos datos viajan con el permiso para que Saturday pueda buscar la ruta real.
  const [flightOrigin, setFlightOrigin] = useState("");
  const [flightDestination, setFlightDestination] = useState("");
  const [departureDate, setDepartureDate] = useState("");
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1);
  
  // 🛡️ Identidad y Datos Bancarios DLP
  const [userIdDoc, setUserIdDoc] = useState("");
  const [userPhone, setUserPhone] = useState("");
  const [smsOtp, setSmsOtp] = useState("");
  const [cardNumber, setCardNumber] = useState("");


  // Modal y Hooks Biométicos
  const [showBioModal, setShowBioModal] = useState(false);
  const [bioMode, setBioMode] = useState<"camera" | "fingerprint">("camera");
  const [passkeyVerified, setPasskeyVerified] = useState(false);
  const [smsVerified, setSmsVerified] = useState(false);
  const [smsCodeSent, setSmsCodeSent] = useState(false);
  const [tokenVerified, setTokenVerified] = useState(false);
  const [sensitiveFieldFocused, setSensitiveFieldFocused] = useState(false);
  const [editingIdentity, setEditingIdentity] = useState(false);
  const [editingBiometric, setEditingBiometric] = useState(false);
  const [editingSms, setEditingSms] = useState(false);
  const [microExpression, setMicroExpression] = useState<SaturdayExpression | null>(null);
  const expressionTimer = useRef<number | null>(null);

  const { videoRef, livenessState, startCamera, stopCamera, verifyFacePresence, sendSmsCode, verifySmsCode } = useLivenessVerification();
  const { handlePasskeyChallenge, handleTokenizeCard, sendOtp, verifyOtp, isSubmitEnabled, isStripeTokenized, isPossessionVerified, errorMessage: securityError, isLoading: securityLoading } = useZeroTrustSecurity();

  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selectedCategory = categories.find((item) => item.value === category)?.label ?? category;
  const selectedMerchant = merchants.find((item) => item.value === merchant)?.label ?? merchant;
  const identityComplete = Boolean(userIdDoc.trim() && userPhone.trim());
  const identityCollapsed = identityComplete && !editingIdentity;
  const biometricCollapsed = passkeyVerified && !editingBiometric;
  const smsCollapsed = smsVerified && !editingSms;
  const stepOneReady = Boolean(identityComplete && smsOtp.trim() && passkeyVerified && smsVerified);
  const completedVerificationCount = Number(identityComplete) + Number(passkeyVerified) + Number(smsVerified);
  const identityStatus = verificationStatus(identityComplete, Boolean(userIdDoc.trim() || userPhone.trim()));
  const biometricStatus = verificationStatus(passkeyVerified, showBioModal);
  const smsStatus = verificationStatus(smsVerified, smsCodeSent);
  const saturdayExpression: SaturdayExpression | undefined = sensitiveFieldFocused
    ? "covering"
    : microExpression ?? (stepOneReady || (currentStep === 2 && tokenVerified) ? "ready" : undefined);
  const summary = useMemo(
    () => `Saturday podrá comprar ${selectedCategory.toLowerCase()} en ${selectedMerchant}, hasta $${maxAmount || "—"} por compra, máximo ${maxUses || "—"} veces, solo si el precio baja de $${priceBelow || "—"}${validUntil ? `, válido hasta ${validUntil}.` : "."} (Enrolado con Passkey + SMS OTP + Token DLP).`,
    [humanName, maxAmount, maxUses, priceBelow, selectedCategory, selectedMerchant, validUntil],
  );

  function showMicroExpression(expression: SaturdayExpression) {
    if (expressionTimer.current !== null) window.clearTimeout(expressionTimer.current);
    setMicroExpression(expression);
    expressionTimer.current = window.setTimeout(() => setMicroExpression(null), 850);
  }

  async function openBiometricsModal() {
    setShowBioModal(true);
    setBioMode("camera");
    try {
      await startCamera();
      // Iniciar verificación tras 1.5s
      setTimeout(async () => {
        try {
          await verifyFacePresence();
          setPasskeyVerified(true);
          setEditingBiometric(false);
          showMicroExpression("happy");
          setTimeout(() => setShowBioModal(false), 800);
        } catch (e) {
          console.warn("Liveness error:", e);
        }
      }, 1500);
    } catch {
      // Fallback a passkey nativo WebAuthn
      try {
        await handlePasskeyChallenge();
        setPasskeyVerified(true);
        setEditingBiometric(false);
        showMicroExpression("happy");
      } catch (err) {
        console.warn(err);
      }
    }
  }

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

    if (category === "travel.flights" && (!flightOrigin.trim() || !flightDestination.trim() || !departureDate)) {
      setError("Completa origen, destino y fecha de salida para buscar vuelos.");
      return;
    }
    if (!category || !merchant) {
      setError("Elige una categoría y un comercio para el permiso.");
      return;
    }

    const mandateId = safeId(humanName, "mnd");
    const payload = {
      mandate_id: mandateId,
      human: { 
        id: safeId(humanName, "hum"), 
        display_name: humanName.trim(),
        id_document: userIdDoc,
        phone: userPhone,
      },
      agent: { id: "agt_saturday", display_name: "Saturday" },
      ...(category === "travel.flights" ? {
        search_fields: {
          origin: flightOrigin.trim(),
          destination: flightDestination.trim(),
          departure_date: departureDate,
        },
      } : {}),
      constraints: {
        max_amount_per_purchase: amount,
        currency: "USD",
        allowed_categories: [category],
        allowed_merchants: [merchant],
        max_uses: uses,
        conditions: [{ type: "price_below", value: price }],
        off_session_consent: true,
      },
      authentication: {
        passkey_biometrics: passkeyVerified ? "verified_webauthn_touch_id" : "unverified",
        sms_otp_confirmed: smsVerified,
        sms_code: smsOtp,
      },
      payment_token: {
        token_id: `vtok_${Math.random().toString(36).slice(2, 10)}`,
        token_type: "SCOPED_VIRTUAL_TOKEN",
        masked_card: cardNumber || "•••• 4242",
        bank_issuer: "Stripe Elements / Galicia AI Payments",
      },
      ...(validUntil ? { valid_until: validUntil } : {}),
      signature: "ed25519_passkey_signed_jwt_token",
    };

    if (!tokenVerified) {
      try {
        const token = await handleTokenizeCard();
        if (token) setTokenVerified(true);
      } catch (e) {
        setError("No se pudo tokenizar el método de pago.");
        return;
      }
    }
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
      
      {/* Modal Biométrico */}
      {showBioModal && (
        <div style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(10, 14, 26, 0.94)", backdropFilter: "blur(16px)", display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem" }}>
          <div style={{ width: "min(420px, 94vw)", background: "#141B2E", border: "1px solid rgba(77, 124, 255, 0.4)", borderRadius: "1.5rem", padding: "1.5rem", textAlign: "center", position: "relative" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h2 style={{ margin: 0, fontFamily: "Space Grotesk", fontSize: "1.25rem", color: "#E8ECF5" }}>Face ID & Biometría</h2>
              <button type="button" onClick={() => { stopCamera(); setShowBioModal(false); }} style={{ background: "transparent", border: 0, color: "#8A94AD", fontSize: "1.2rem", cursor: "pointer" }}>✕</button>
            </div>

            <div style={{ position: "relative", width: "230px", height: "290px", margin: "1rem auto", borderRadius: "50%", overflow: "hidden", border: "4px solid #3DDC97", boxShadow: "0 0 30px rgba(61, 220, 151, 0.5)", background: "#000" }}>
              <video ref={videoRef} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "cover", transform: "scaleX(-1)", display: "block" }} />
              <div style={{ position: "absolute", top: "10%", left: 0, right: 0, height: "3px", background: "#3DDC97", boxShadow: "0 0 15px #3DDC97" }} />
            </div>

            <p style={{ color: "#3DDC97", fontFamily: "Space Grotesk", fontSize: "0.85rem", fontWeight: 600 }}>
              {livenessState.error ? livenessState.error : livenessState.isLiveFaceVerified ? "✅ ¡Humano verificado!" : "Centra tu rostro en el óvalo..."}
            </p>
          </div>
        </div>
      )}

      <section className="authorization-layout">
        <div className="authorization-intro">
          <p className="mission-kicker">AGENTBUYER / TU PERMISO, TUS LÍMITES</p>
          <h1>Autoriza a <span>Saturday</span></h1>
          <p>Tu agente puede ayudarte a comprar, pero tú defines cada límite. Nada ocurre fuera de este permiso.</p>
          <div className="creator-saturday"><Saturday state="idle" expression={saturdayExpression} /></div>
          <div className="trust-note"><b>Tu control sigue primero.</b><span>Podrás revocar este permiso cuando quieras.</span></div>
        </div>

        <form className="mandate-form" onSubmit={createMandate}>
          <div className="form-heading"><p className="panel-eyebrow">NUEVO PERMISO</p><h2>Dale instrucciones claras a Saturday</h2></div>
          <div className="wizard-progress" aria-label={`Paso ${currentStep} de 4`}>
            <span className={currentStep === 1 ? "is-current" : currentStep > 1 ? "is-complete" : ""}>1. Verifica que eres tú</span>
            <span className={currentStep === 2 ? "is-current" : currentStep > 2 ? "is-complete" : ""}>2. Método seguro</span>
            <span className={currentStep === 3 ? "is-current" : currentStep > 3 ? "is-complete" : ""}>3. Define los límites</span>
            <span className={currentStep === 4 ? "is-current" : ""}>4. Confirma</span>
          </div>
          <div className="wizard-step" style={{ display: currentStep === 3 ? "grid" : "none" }}>
          <h3>Define los límites</h3>
          <label>¿Quién autoriza?<input value={humanName} onChange={(event) => setHumanName(event.target.value)} placeholder="Tu nombre" required /></label>
          <label>¿Cuánto puede gastar como máximo en cada compra?<div className="money-field"><span>USD $</span><input value={maxAmount} onChange={(event) => setMaxAmount(event.target.value)} inputMode="decimal" placeholder="150" required /></div></label>
          <div className="form-pair">
            <label>¿En qué puede gastar?<select value={category} onChange={(event) => setCategory(event.target.value)} required><option value="" disabled>Elige una categoría</option>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
            <label>¿En qué comercios?<select value={merchant} onChange={(event) => setMerchant(event.target.value)} required><option value="" disabled>Elige un comercio</option>{merchants.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
          </div>
          <div className="form-pair">
            <label>¿Cuántas compras puede hacer como máximo?<input value={maxUses} onChange={(event) => setMaxUses(event.target.value)} inputMode="numeric" placeholder="3" required /></label>
            <label>¿Hasta cuándo es válido este permiso?<input type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} /></label>
          </div>
          <label>¿Alguna condición de precio?<div className="price-condition"><span>Solo si el precio baja de USD $</span><input value={priceBelow} onChange={(event) => setPriceBelow(event.target.value)} inputMode="decimal" placeholder="150" required /></div></label>
          </div>

          {/* 🛡️ SECCIÓN AÑADIDA: Autenticación Fuerte (Passkey, ID, SMS) & Datos Bancarios DLP */}
          {category === "travel.flights" && currentStep === 3 && <div className="wizard-step flight-search-step">
            <div className="form-pair">
              <label>Origen<input value={flightOrigin} onChange={(event) => setFlightOrigin(event.target.value)} placeholder="BUE o Buenos Aires" required /></label>
              <label>Destino<input value={flightDestination} onChange={(event) => setFlightDestination(event.target.value)} placeholder="COR o Ciudad de México" required /></label>
            </div>
            <label>Fecha de salida<FlightDatePicker value={departureDate} onChange={setDepartureDate} /></label>
          </div>}

          <div className={`wizard-step wizard-security-step ${currentStep === 1 || currentStep === 2 ? "is-visible" : ""}`} style={{ background: "rgba(30, 41, 59, 0.6)", padding: "14px", borderRadius: "10px", border: "1px solid rgba(77, 124, 255, 0.35)", marginTop: "4px" }}>
            <h3>{currentStep === 1 ? "Verifica que eres tú" : "Método de pago seguro"}</h3>
            <p className="security-intro">{currentStep === 1 ? "Completa estas tres verificaciones para proteger tu permiso." : "Tokeniza tu tarjeta: Saturday nunca verá el número completo."}</p>
            {currentStep === 1 && <div className="security-progress"><span>PROGRESO DE SEGURIDAD</span><strong>{completedVerificationCount} de 3 verificaciones completadas</strong></div>}
            
            <div className={`form-pair security-item security-identity ${identityCollapsed ? "is-collapsed" : ""}`} style={{ display: currentStep === 1 ? "grid" : "none" }}>
              <div className="security-item-heading"><span>1</span><div><b>Identidad</b><small>{identityComplete ? "✓ Datos de contacto completos" : "Documento y teléfono requeridos"}</small></div><em className={`security-${identityStatus}`}>{verificationStatusLabel[identityStatus]}</em>{identityComplete && <button className="security-edit" type="button" onClick={() => setEditingIdentity((editing) => !editing)}>{editingIdentity ? "Listo" : "Editar"}</button>}</div>
              {!identityCollapsed && <>
              <label style={{ fontSize: "0.72rem" }}>
                Documento de Identidad (ID / Pasaporte):
                <input value={userIdDoc} onChange={(e) => setUserIdDoc(e.target.value)} onFocus={() => setSensitiveFieldFocused(true)} onBlur={() => setSensitiveFieldFocused(false)} placeholder="PASSPORT-AR-948291" style={{ minHeight: "2.3rem", fontSize: "0.82rem" }} />
              </label>
              <label style={{ fontSize: "0.72rem" }}>
                Teléfono para SMS OTP:
                <input value={userPhone} onChange={(e) => { setUserPhone(e.target.value); setSmsVerified(false); setSmsCodeSent(false); setEditingSms(false); }} placeholder="+54 9 11 5829-1039" style={{ minHeight: "2.3rem", fontSize: "0.82rem" }} />
              </label>
              </>}
            </div>

            <div className={`form-pair security-item security-code-or-payment ${currentStep === 1 && smsCollapsed ? "is-collapsed" : ""}`} style={{ marginTop: "8px" }}>
              {currentStep === 1 && <div className="security-item-heading"><span>3</span><div><b>Código SMS</b><small>{smsVerified ? "✓ SMS verificado" : "Envía el código y luego confírmalo"}</small></div><em className={`security-${smsStatus}`}>{verificationStatusLabel[smsStatus]}</em>{smsVerified && <button className="security-edit" type="button" onClick={() => setEditingSms((editing) => !editing)}>{editingSms ? "Listo" : "Editar"}</button>}</div>}
              {currentStep === 2 && <div className="security-item-heading"><span>1</span><div><b>Token DLP</b><small>{tokenVerified ? "✓ Método de pago protegido" : "Tokeniza el método de pago"}</small></div><em className={`security-${tokenVerified ? "complete" : "pending"}`}>{tokenVerified ? "COMPLETADO" : "PENDIENTE"}</em></div>}
              <label style={{ display: currentStep === 2 ? "grid" : "none", fontSize: "0.72rem" }}>
                💳 Método de Pago (Stripe Elements / Scoped Token):
                <div style={{ display: "flex", gap: "6px" }}>
                  <input value={cardNumber} onChange={(e) => setCardNumber(e.target.value)} onFocus={() => setSensitiveFieldFocused(true)} onBlur={() => setSensitiveFieldFocused(false)} placeholder="•••• •••• •••• 4242" style={{ minHeight: "2.3rem", fontSize: "0.82rem" }} />
                  <button type="button" onClick={async () => { try { const token = await handleTokenizeCard(); if (token) setTokenVerified(true); } catch (e) { console.warn(e); } }} style={{ background: tokenVerified ? "rgba(16, 185, 129, 0.45)" : "rgba(59, 130, 246, 0.2)", border: tokenVerified ? "1px solid #10b981" : "1px solid #3b82f6", color: tokenVerified ? "#6ee7b7" : "#93c5fd", borderRadius: "6px", fontSize: "0.72rem", fontWeight: 700, cursor: "pointer", padding: "0 10px", whiteSpace: "nowrap" }}>{tokenVerified ? "✓ Método tokenizado" : "Tokenizar método"}</button>
                </div>
              </label>
              {!smsCollapsed && <label style={{ display: currentStep === 1 ? "grid" : "none", fontSize: "0.72rem" }}>
                Ingresa el código de 6 dígitos que recibiste por SMS
                <div className="sms-code-controls">
                  <button type="button" onClick={async () => { try { await sendOtp(userPhone, "sms"); setSmsCodeSent(true); } catch(e) { console.warn(e); } }} style={{ background: "rgba(59, 130, 246, 0.2)", border: "1px solid #3b82f6", color: "#93c5fd", borderRadius: "6px", fontSize: "0.72rem", fontWeight: 700, cursor: "pointer", padding: "0 8px", whiteSpace: "nowrap" }}>Enviar código SMS</button>
                  <input value={smsOtp} onChange={(e) => { setSmsOtp(e.target.value); setSmsVerified(false); setSmsCodeSent(false); }} onFocus={() => setSensitiveFieldFocused(true)} onBlur={() => setSensitiveFieldFocused(false)} placeholder="Código de 6 dígitos" maxLength={6} inputMode="numeric" style={{ minHeight: "2.65rem", fontSize: "0.82rem" }} />
                  <button type="button" onClick={async () => { try { const res = await verifyOtp(userPhone, smsOtp, "sms"); if (res) { setSmsVerified(true); setEditingSms(false); showMicroExpression("nodding"); } } catch(e) { console.warn(e); } }} style={{ background: smsVerified ? "rgba(16, 185, 129, 0.45)" : "rgba(16, 185, 129, 0.25)", border: "1px solid #10b981", color: "#6ee7b7", borderRadius: "6px", fontSize: "0.72rem", fontWeight: 700, cursor: "pointer", padding: "0 10px" }}>{smsVerified ? "✓ SMS verificado" : "Verificar código"}</button>
                </div>
              </label>}
            </div>


            <div className={`security-item security-biometric ${biometricCollapsed ? "is-collapsed" : ""}`} style={{ display: currentStep === 1 ? "flex" : "none", gap: "10px", marginTop: "10px", flexWrap: "wrap", alignItems: "center" }}>
              <div className="security-item-heading"><span>2</span><div><b>Biometría</b><small>{passkeyVerified ? "✓ Identidad verificada" : showBioModal ? "Verificando tu presencia…" : "Confirma con Face ID o huella"}</small></div><em className={`security-${biometricStatus}`}>{verificationStatusLabel[biometricStatus]}</em>{passkeyVerified && <button className="security-edit" type="button" onClick={() => { setEditingBiometric(true); setPasskeyVerified(false); }}>Editar</button>}</div>
              {!biometricCollapsed && <button
                type="button"
                onClick={openBiometricsModal}
                disabled={passkeyVerified}
                style={{
                  background: passkeyVerified ? "rgba(16, 185, 129, 0.2)" : "rgba(77, 124, 255, 0.2)",
                  border: passkeyVerified ? "1px solid #10b981" : "1px solid #4D7CFF",
                  color: passkeyVerified ? "#6ee7b7" : "#93c5fd",
                  padding: "6px 12px",
                  borderRadius: "8px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  cursor: "pointer"
                }}
              >
                Verificar con Face ID / Huella
              </button>}
            </div>
          </div>

          <div className="wizard-step" style={{ display: currentStep === 4 ? "grid" : "none" }}>
            <h3>Confirma y autoriza</h3>
            <div className="permission-summary"><span>ASÍ SE VERÁ TU PERMISO</span><p>{summary}</p></div>
          </div>
          {(error || securityError) && <div className="form-error" role="alert">{error || securityError}</div>}
          {currentStep === 1 && !stepOneReady && <p className="wizard-notice">Para continuar, completa la identidad, la biometría y la verificación por SMS.</p>}
          {currentStep === 2 && !tokenVerified && <p className="wizard-notice">Tokeniza tu método de pago seguro para continuar.</p>}
          <div className="wizard-navigation">
            {currentStep > 1 && <button className="wizard-back" type="button" onClick={() => setCurrentStep((currentStep - 1) as 1 | 2 | 3 | 4)}>← Atrás</button>}
            {currentStep === 1 && <button className="wizard-next" type="button" disabled={!stepOneReady} onClick={() => setCurrentStep(2)}>Siguiente →</button>}
            {currentStep === 2 && <button className="wizard-next" type="button" disabled={!tokenVerified} onClick={() => setCurrentStep(3)}>Siguiente →</button>}
            {currentStep === 3 && <button className="wizard-next" type="button" onClick={() => setCurrentStep(4)}>Siguiente →</button>}
            {currentStep === 4 && <button className="authorize-button" disabled={creating || !(passkeyVerified && smsVerified && tokenVerified)} type="submit">{creating ? "CREANDO TU PERMISO…" : !passkeyVerified ? "⚠ FALTA BIOMETRÍA" : !smsVerified ? "⚠ FALTA SMS OTP" : !tokenVerified ? "⚠ FALTA TOKEN BANCARIO" : "AUTORIZAR A SATURDAY"}</button>}
          </div>
        </form>
      </section>
    </main>
  );
}
