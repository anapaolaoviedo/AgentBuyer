import { FormEvent, useMemo, useState, useEffect, useRef } from "react";
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
  pending: "PENDING",
  processing: "IN PROGRESS",
  complete: "COMPLETED",
};

const categories = [
  { value: "travel.flights", label: "Flights" },
  { value: "travel.hotels", label: "Hotels" },
  { value: "digital.subscriptions", label: "Subscriptions" },
];

const merchants = [
  { value: "mch_vuelaya", label: "VuelaYa" },
  { value: "mch_despegar", label: "Despegar" },
  { value: "mch_kayak", label: "Kayak" },
  { value: "mch_expedia", label: "Expedia" },
];

// La búsqueda web real devuelve ofertas de estos sitios de viajes; un mandato
// de vuelos debe permitirlos o toda compra real escalaría por comercio.
const FLIGHT_SEARCH_MERCHANTS = ["mch_vuelaya", "mch_despegar", "mch_kayak", "mch_expedia"];

function endOfMonth() {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth() + 1, 0).toISOString().slice(0, 10);
}

// Fecha cercana (~2 semanas) para que la búsqueda web real devuelva resultados
// de forma confiable — las fechas muy lejanas suelen no tener tarifas publicadas.
function nearTermDate() {
  const d = new Date();
  d.setDate(d.getDate() + 14);
  return d.toISOString().slice(0, 10);
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
  return new Intl.DateTimeFormat("en-US", { day: "numeric", month: "short", year: "numeric" })
    .format(dateFromKey(value))
    .replace(".", "");
}

type CalendarDatePickerProps = {
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
};

function CalendarDatePicker({ value, onChange, ariaLabel = "Pick a date" }: CalendarDatePickerProps) {
  const today = useMemo(() => {
    const current = new Date();
    current.setHours(0, 0, 0, 0);
    return current;
  }, []);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    function closeOnOutsideClick(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setIsOpen(false);
    }
    document.addEventListener("mousedown", closeOnOutsideClick);
    return () => document.removeEventListener("mousedown", closeOnOutsideClick);
  }, [isOpen]);
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
  const monthLabel = new Intl.DateTimeFormat("en-US", { month: "long", year: "numeric" }).format(visibleMonth);
  const earliestMonth = new Date(today.getFullYear(), today.getMonth(), 1);

  function togglePicker() {
    if (!isOpen) {
      const selected = value ? dateFromKey(value) : today;
      setVisibleMonth(new Date(selected.getFullYear(), selected.getMonth(), 1));
    }
    setIsOpen((open) => !open);
  }

  return (
    <div className="date-picker" ref={containerRef}>
      <button className={`date-picker-trigger ${value ? "has-value" : ""}`} type="button" onClick={togglePicker} aria-haspopup="dialog" aria-expanded={isOpen}>
        <span>{value ? readableDate(value) : "Pick a date"}</span><b aria-hidden="true">⌄</b>
      </button>
      {isOpen && <div className="calendar-popover" role="dialog" aria-label={ariaLabel}>
        <div className="calendar-heading">
          <button type="button" onClick={() => setVisibleMonth(new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() - 1, 1))} disabled={visibleMonth <= earliestMonth} aria-label="Previous month">‹</button>
          <strong>{monthLabel}</strong>
          <button type="button" onClick={() => setVisibleMonth(new Date(visibleMonth.getFullYear(), visibleMonth.getMonth() + 1, 1))} aria-label="Next month">›</button>
        </div>
        <div className="calendar-weekdays">{["S", "M", "T", "W", "T", "F", "S"].map((day, index) => <span key={`${day}-${index}`}>{day}</span>)}</div>
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
  // Prellenado con el perfil demo de Marta: el wizard completo se recorre
  // solo con clics (sin teclear nada) para una demo rápida y confiable.
  const [humanName, setHumanName] = useState("Marta");
  const [maxAmount, setMaxAmount] = useState("150");
  const [category, setCategory] = useState("travel.flights");
  const [merchant, setMerchant] = useState("mch_vuelaya");
  const [maxUses, setMaxUses] = useState("3");
  const [priceBelow, setPriceBelow] = useState("150");
  const [validUntil, setValidUntil] = useState(endOfMonth());
  // Estos datos viajan con el permiso para que Saturday pueda buscar la ruta real.
  // Ruta por defecto BUE→COR con fecha cercana: combinación confirmada que
  // la búsqueda web real devuelve de forma confiable para la demo.
  const [flightOrigin, setFlightOrigin] = useState("BUE");
  const [flightDestination, setFlightDestination] = useState("COR");
  const [departureDate, setDepartureDate] = useState(nearTermDate());
  const [currentStep, setCurrentStep] = useState<1 | 2 | 3 | 4>(1);

  // 🛡️ Identidad y Datos Bancarios DLP (valores demo de Marta, editables)
  const [userIdDoc, setUserIdDoc] = useState("PASSPORT-AR-948291");
  const [userPhone, setUserPhone] = useState("+52 56 1447 3083");
  const [userEmail, setUserEmail] = useState("marta@example.com");
  // Canal del código de verificación: SMS al teléfono o correo electrónico.
  const [otpChannel, setOtpChannel] = useState<"sms" | "email">("sms");
  // El backend ahora genera códigos aleatorios; en modo demo (sin Twilio/SMTP)
  // devuelve code_demo en la respuesta y el campo se autollena al enviar.
  const [smsOtp, setSmsOtp] = useState("");
  const [cardNumber, setCardNumber] = useState("4242 4242 4242 4242");

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
  const { handlePasskeyChallenge, handleTokenizeCard, sendOtp, verifyOtp, isSubmitEnabled, isStripeTokenized, isPossessionVerified, paymentMethodId, errorMessage: securityError, isLoading: securityLoading } = useZeroTrustSecurity();

  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const selectedCategory = categories.find((item) => item.value === category)?.label ?? category;
  const selectedMerchant = merchants.find((item) => item.value === merchant)?.label ?? merchant;
  // Un teléfono real: al menos 10 dígitos (ignorando espacios, guiones, etc.).
  const phoneDigits = userPhone.replace(/\D/g, "");
  const phoneComplete = phoneDigits.length >= 10;
  const emailComplete = /^\S+@\S+\.\S+$/.test(userEmail.trim());
  const otpContactReady = otpChannel === "sms" ? phoneComplete : emailComplete;
  const identityComplete = Boolean(userIdDoc.trim() && phoneComplete);
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
    () => `Saturday will be able to buy ${selectedCategory.toLowerCase()} at ${selectedMerchant}, up to $${maxAmount || "—"} per purchase, at most ${maxUses || "—"} times, only if the price drops below $${priceBelow || "—"}${validUntil ? `, valid until ${validUntil}.` : "."} (Enrolled with Passkey + SMS OTP + DLP Token).`,
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
    // Si falta algo del paso 3, regresamos ahí para que el error sea accionable.
    if (!humanName.trim() || !Number.isFinite(amount) || amount <= 0 || !Number.isInteger(uses) || uses <= 0 || !Number.isFinite(price) || price <= 0) {
      setError("Fill in your name and the limits with valid numbers greater than zero.");
      setCurrentStep(3);
      return;
    }

    if (category === "travel.flights" && (!flightOrigin.trim() || !flightDestination.trim() || !departureDate)) {
      setError("Fill in origin, destination, and departure date to search for flights.");
      setCurrentStep(3);
      return;
    }
    if (!category || !merchant) {
      setError("Choose a category and a merchant for the permission.");
      setCurrentStep(3);
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
        // El recibo de compra se envía a mandate.human.email (core/notifications).
        ...(userEmail.trim() ? { email: userEmail.trim() } : {}),
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
        allowed_merchants: category === "travel.flights"
          ? Array.from(new Set([merchant, ...FLIGHT_SEARCH_MERCHANTS]))
          : [merchant],
        max_uses: uses,
        conditions: [{ type: "price_below", value: price }],
        off_session_consent: true,
      },
      authentication: {
        passkey_biometrics: passkeyVerified ? "verified_webauthn_touch_id" : "unverified",
        sms_otp_confirmed: smsVerified,
        email_otp_confirmed: otpChannel === "email" && smsVerified,
        sms_code: smsOtp,
        otp_channel: otpChannel,
        verified_email: userEmail.trim(),
      },
      payment_token: {
        token_id: paymentMethodId || `vtok_${Math.random().toString(36).slice(2, 10)}`,
        token_type: "SCOPED_VIRTUAL_TOKEN",
        masked_card: cardNumber ? (cardNumber.startsWith("••••") ? cardNumber : `•••• ${cardNumber.replace(/\D/g, "").slice(-4) || "4242"}`) : "•••• 4242",
        bank_issuer: "Stripe Elements / Galicia AI Payments",
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
      setError(caught instanceof Error ? `We couldn't create your permission: ${caught.message}` : "We couldn't create your permission. Check the connection to the system.");
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
              <h2 style={{ margin: 0, fontFamily: "Space Grotesk", fontSize: "1.25rem", color: "#E8ECF5" }}>Face ID & Biometrics</h2>
              <button type="button" onClick={() => { stopCamera(); setShowBioModal(false); }} style={{ background: "transparent", border: 0, color: "#8A94AD", fontSize: "1.2rem", cursor: "pointer" }}>✕</button>
            </div>

            <div style={{ position: "relative", width: "230px", height: "290px", margin: "1rem auto", borderRadius: "50%", overflow: "hidden", border: "4px solid #3DDC97", boxShadow: "0 0 30px rgba(61, 220, 151, 0.5)", background: "#000" }}>
              <video ref={videoRef} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "cover", transform: "scaleX(-1)", display: "block" }} />
              <div style={{ position: "absolute", top: "10%", left: 0, right: 0, height: "3px", background: "#3DDC97", boxShadow: "0 0 15px #3DDC97" }} />
            </div>

            <p style={{ color: "#3DDC97", fontFamily: "Space Grotesk", fontSize: "0.85rem", fontWeight: 600 }}>
              {livenessState.error ? livenessState.error : livenessState.isLiveFaceVerified ? "✅ Human verified!" : "Center your face in the oval..."}
            </p>
          </div>
        </div>
      )}

      <section className="authorization-layout">
        <div className="authorization-intro">
          <p className="mission-kicker">AGENTBUYER / YOUR PERMISSION, YOUR LIMITS</p>
          <h1>Authorize <span>Saturday</span></h1>
          <p>Your agent can help you buy, but you define every limit. Nothing happens outside this permission.</p>
          <div className="creator-saturday"><Saturday state="idle" expression={saturdayExpression} /></div>
          <div className="trust-note"><b>Your control comes first.</b><span>You can revoke this permission anytime.</span></div>
        </div>

        {/* noValidate: hay inputs required en pasos ocultos (display:none); la
            validación nativa bloqueaba el submit sin poder mostrar su burbuja.
            La validación real vive en createMandate, con errores visibles. */}
        <form className="mandate-form" onSubmit={createMandate} noValidate>
          <div className="form-heading"><p className="panel-eyebrow">NEW PERMISSION</p><h2>Give Saturday clear instructions</h2></div>
          <div className="wizard-progress" aria-label={`Step ${currentStep} of 4`}>
            <span className={currentStep === 1 ? "is-current" : currentStep > 1 ? "is-complete" : ""}>1. Verify it's you</span>
            <span className={currentStep === 2 ? "is-current" : currentStep > 2 ? "is-complete" : ""}>2. Secure method</span>
            <span className={currentStep === 3 ? "is-current" : currentStep > 3 ? "is-complete" : ""}>3. Set the limits</span>
            <span className={currentStep === 4 ? "is-current" : ""}>4. Confirm</span>
          </div>

          <div className="wizard-step" style={{ display: currentStep === 3 ? "grid" : "none" }}>
            <h3>Set the limits</h3>
            <label>Who's authorizing?<input value={humanName} onChange={(event) => setHumanName(event.target.value)} placeholder="Your name" required /></label>
            <label>How much can it spend at most per purchase?<div className="money-field"><span>USD $</span><input value={maxAmount} onChange={(event) => setMaxAmount(event.target.value)} inputMode="decimal" placeholder="150" required /></div></label>
            <div className="form-pair">
              <label>What can it spend on?<select value={category} onChange={(event) => setCategory(event.target.value)}><option value="" disabled>Choose a category…</option>{categories.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>
              <label>At which merchants?<select value={merchant} onChange={(event) => setMerchant(event.target.value)}><option value="" disabled>Choose a merchant…</option>{merchants.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>{category === "travel.flights" && <small className="field-hint">For flights, Saturday compares trusted travel sites (VuelaYa, Despegar, Kayak, Expedia) — all included in your permission.</small>}</label>
            </div>
            <div className="form-pair">
              <label>How many purchases at most?<input value={maxUses} onChange={(event) => setMaxUses(event.target.value)} inputMode="numeric" placeholder="3" required /></label>
              <label>Until when is this permission valid?<CalendarDatePicker value={validUntil} onChange={setValidUntil} ariaLabel="Pick how long the permission is valid" /></label>
            </div>
            <label>Any price condition?<div className="price-condition"><span>Only if the price drops below USD $</span><input value={priceBelow} onChange={(event) => setPriceBelow(event.target.value)} inputMode="decimal" placeholder="150" required /></div></label>
          </div>

          {category === "travel.flights" && currentStep === 3 && <div className="wizard-step flight-search-step">
            <div className="form-pair">
              <label>Origin<input value={flightOrigin} onChange={(event) => setFlightOrigin(event.target.value)} placeholder="BUE or Buenos Aires" required /></label>
              <label>Destination<input value={flightDestination} onChange={(event) => setFlightDestination(event.target.value)} placeholder="COR or Mexico City" required /></label>
            </div>
            <label>Departure date<CalendarDatePicker value={departureDate} onChange={setDepartureDate} ariaLabel="Pick the departure date" /></label>
          </div>}

          {(currentStep === 1 || currentStep === 2) && <div className="wizard-step wizard-security-step" style={{ background: "rgba(30, 41, 59, 0.6)", padding: "14px", borderRadius: "10px", border: "1px solid rgba(77, 124, 255, 0.35)", marginTop: "4px" }}>
            <h3>{currentStep === 1 ? "Verify it's you" : "Secure payment method"}</h3>

            {currentStep === 1 && <>
              <p className="verify-subtitle">Three quick verifications, in order: your identity, your biometrics, and a verification code.</p>
              <div className="verify-progress" role="status">
                <span>{completedVerificationCount} of 3 verifications completed</span>
                <div className="verify-progress-bar" aria-hidden="true"><i style={{ width: `${Math.round((completedVerificationCount / 3) * 100)}%` }} /></div>
              </div>

              {/* a) Identidad: documento + teléfono */}
              <section className={`verify-item is-${identityStatus}`}>
                <header className="verify-item-heading">
                  <span className="verify-item-number" aria-hidden="true">{identityComplete ? "✓" : "1"}</span>
                  <div className="verify-item-title"><b>Identity</b><small>{identityComplete ? "Document and phone captured" : "Enter your document and your phone"}</small></div>
                  <em className={`verify-chip is-${identityStatus}`}>{verificationStatusLabel[identityStatus]}</em>
                  {identityComplete && <button className="verify-edit" type="button" onClick={() => setEditingIdentity((editing) => !editing)}>{editingIdentity ? "Done" : "Edit"}</button>}
                </header>
                {!identityCollapsed && <div className="verify-item-body">
                  <div className="form-pair">
                    <label>
                      ID document (ID / passport)
                      <input value={userIdDoc} onChange={(e) => setUserIdDoc(e.target.value)} onFocus={() => setSensitiveFieldFocused(true)} onBlur={() => setSensitiveFieldFocused(false)} placeholder="PASSPORT-AR-948291" />
                    </label>
                    <label>
                      Contact phone
                      <input value={userPhone} onChange={(e) => { setUserPhone(e.target.value); if (otpChannel === "sms") { setSmsVerified(false); setSmsCodeSent(false); setEditingSms(false); } }} inputMode="tel" placeholder="+52 56 1447 3083" />
                    </label>
                  </div>
                  {userPhone.trim() !== "" && !phoneComplete && (
                    <p className="verify-hint verify-hint-warn">Enter a complete phone number (at least 10 digits).</p>
                  )}
                </div>}
              </section>

              {/* b) Biometría: Face ID / huella */}
              <section className={`verify-item is-${biometricStatus}`}>
                <header className="verify-item-heading">
                  <span className="verify-item-number" aria-hidden="true">{passkeyVerified ? "✓" : "2"}</span>
                  <div className="verify-item-title"><b>Biometrics</b><small>{passkeyVerified ? "Identity verified" : "Confirm it's you with your face or fingerprint"}</small></div>
                  <em className={`verify-chip is-${biometricStatus}`}>{verificationStatusLabel[biometricStatus]}</em>
                </header>
                {!biometricCollapsed && <div className="verify-item-body">
                  <button className="verify-action" type="button" onClick={openBiometricsModal} disabled={passkeyVerified || showBioModal}>
                    {showBioModal ? "Verifying…" : "Verify with Face ID / Fingerprint"}
                  </button>
                </div>}
              </section>

              {/* c) Código de verificación: por SMS o por correo — enviar y luego verificar */}
              <section className={`verify-item is-${smsStatus}`}>
                <header className="verify-item-heading">
                  <span className="verify-item-number" aria-hidden="true">{smsVerified ? "✓" : "3"}</span>
                  <div className="verify-item-title"><b>Verification code</b><small>{smsVerified ? `Code verified via ${otpChannel === "email" ? "email" : "SMS"}` : "Receive a code by SMS or email and confirm it"}</small></div>
                  <em className={`verify-chip is-${smsStatus}`}>{verificationStatusLabel[smsStatus]}</em>
                  {smsVerified && <button className="verify-edit" type="button" onClick={() => setEditingSms((editing) => !editing)}>{editingSms ? "Done" : "Edit"}</button>}
                </header>
                {!smsCollapsed && <div className="verify-item-body">
                  <div className="verify-tabs" role="tablist" aria-label="Verification method">
                    <button className={`verify-tab ${otpChannel === "sms" ? "is-active" : ""}`} type="button" role="tab" aria-selected={otpChannel === "sms"} onClick={() => { if (otpChannel !== "sms") { setOtpChannel("sms"); setSmsVerified(false); setSmsCodeSent(false); setSmsOtp(""); } }}>📱 SMS</button>
                    <button className={`verify-tab ${otpChannel === "email" ? "is-active" : ""}`} type="button" role="tab" aria-selected={otpChannel === "email"} onClick={() => { if (otpChannel !== "email") { setOtpChannel("email"); setSmsVerified(false); setSmsCodeSent(false); setSmsOtp(""); } }}>📧 Email</button>
                  </div>
                  {otpChannel === "email" && <>
                    <label>
                      Email address for the code
                      <input value={userEmail} onChange={(e) => { setUserEmail(e.target.value); setSmsVerified(false); setSmsCodeSent(false); }} onFocus={() => setSensitiveFieldFocused(true)} onBlur={() => setSensitiveFieldFocused(false)} type="email" inputMode="email" placeholder="marta@example.com" />
                    </label>
                    <p className="verify-hint verify-hint-tip">Recommended: use the same email where you want to receive your purchase receipt.</p>
                    {userEmail.trim() !== "" && !emailComplete && <p className="verify-hint verify-hint-warn">Enter a valid email (name@domain.com).</p>}
                  </>}
                  <div className="sms-code-controls">
                    <button className="verify-action" type="button" disabled={securityLoading || !otpContactReady} onClick={async () => { try { const res = await sendOtp(otpChannel === "email" ? userEmail : userPhone, otpChannel); setSmsCodeSent(true); const demoCode = typeof res?.code_demo === "string" && /^\d{6}$/.test(res.code_demo) ? res.code_demo : ""; if (demoCode) setSmsOtp(demoCode); } catch (e) { console.warn(e); } }}>
                      {smsCodeSent ? "Resend code" : otpChannel === "email" ? "Send code by email" : "Send SMS code"}
                    </button>
                    <input value={smsOtp} onChange={(e) => { setSmsOtp(e.target.value); setSmsVerified(false); }} onFocus={() => setSensitiveFieldFocused(true)} onBlur={() => setSensitiveFieldFocused(false)} placeholder="6-digit code" maxLength={6} inputMode="numeric" aria-label="6-digit code received" />
                    <button className="verify-action verify-action-confirm" type="button" disabled={securityLoading || !smsOtp.trim()} onClick={async () => { try { const res = await verifyOtp(otpChannel === "email" ? userEmail : userPhone, smsOtp, otpChannel); if (res) { setSmsVerified(true); setEditingSms(false); showMicroExpression("nodding"); } } catch (e) { console.warn(e); } }}>
                      Verify code
                    </button>
                  </div>
                  <p className="verify-hint">
                    {!otpContactReady
                      ? otpChannel === "sms"
                        ? "First enter a complete phone number (at least 10 digits) in step 1."
                        : "First enter your email address above."
                      : smsCodeSent
                        ? `Code sent to ${otpChannel === "email" ? userEmail : userPhone}. Type it and press “Verify code”.`
                        : otpChannel === "email"
                          ? "Press “Send code by email” to receive it in your inbox."
                          : "Press “Send SMS code” to receive it on your phone."}
                  </p>
                </div>}
              </section>
            </>}

            {currentStep === 2 && (
              <section className={`verify-item is-${tokenVerified ? "complete" : "pending"}`}>
                <header className="verify-item-heading">
                  <span className="verify-item-number" aria-hidden="true">{tokenVerified ? "✓" : "1"}</span>
                  <div className="verify-item-title"><b>DLP Token</b><small>{tokenVerified ? "Payment method protected" : "Tokenize your card: the merchant never sees the real number"}</small></div>
                  <em className={`verify-chip is-${tokenVerified ? "complete" : "pending"}`}>{tokenVerified ? "COMPLETED" : "PENDING"}</em>
                </header>
                <div className="verify-item-body">
                  <div className="sms-code-controls">
                    <input value={cardNumber} onChange={(e) => setCardNumber(e.target.value)} placeholder="•••• •••• •••• 4242" aria-label="Card number" />
                    <button className="verify-action verify-action-confirm" type="button" disabled={tokenVerified} onClick={async () => { try { const token = await handleTokenizeCard(cardNumber); if (token) setTokenVerified(true); } catch (e) { console.warn(e); } }}>
                      {tokenVerified ? "✓ Card protected" : "Tokenize card"}
                    </button>
                  </div>
                </div>
              </section>
            )}
          </div>}

          <div className="wizard-step" style={{ display: currentStep === 4 ? "grid" : "none" }}>
            <h3>Confirm and authorize</h3>
            <div className="permission-summary"><span>THIS IS WHAT YOUR PERMISSION WILL LOOK LIKE</span><p>{summary}</p></div>
          </div>

          {(error || securityError) && <div className="form-error" role="alert">{error || securityError}</div>}

          {currentStep === 1 && !(passkeyVerified && smsVerified) && <p className="wizard-notice">To continue, complete {passkeyVerified ? "the code verification" : smsVerified ? "the biometric verification" : "the biometric and code verifications"}.</p>}
          {currentStep === 2 && !tokenVerified && <p className="wizard-notice">Tokenize your secure payment method to continue.</p>}

          <div className="wizard-navigation">
            {currentStep > 1 && <button className="wizard-back" type="button" onClick={() => setCurrentStep((currentStep - 1) as 1 | 2 | 3 | 4)}>← Back</button>}
            {currentStep === 1 && <button className="wizard-next" type="button" disabled={!stepOneReady} onClick={() => setCurrentStep(2)}>Next →</button>}
            {currentStep === 2 && <button className="wizard-next" type="button" disabled={!tokenVerified} onClick={() => setCurrentStep(3)}>Next →</button>}
            {currentStep === 3 && <button className="wizard-next" type="button" onClick={() => setCurrentStep(4)}>Next →</button>}
            {currentStep === 4 && <button className="authorize-button" disabled={creating || !(passkeyVerified && smsVerified && tokenVerified)} type="submit">{creating ? "CREATING YOUR PERMISSION…" : !passkeyVerified ? "⚠ BIOMETRICS MISSING" : !smsVerified ? "⚠ OTP CODE MISSING" : !tokenVerified ? "⚠ BANK TOKEN MISSING" : "AUTHORIZE SATURDAY"}</button>}
          </div>
        </form>
      </section>
    </main>
  );
}
