import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Saturday, { type SaturdayState } from "./components/Saturday";
import MandateCreator from "./components/MandateCreator";

const API_BASE = "http://127.0.0.1:8000";

type LiveState = {
  status: "active" | "revoked" | "expired";
  uses_count: number;
  amount_spent: number;
  revoked_at: string | null;
};

type Condition = { type: string; value: number };
type Constraints = {
  max_amount_per_purchase?: number;
  currency?: string;
  allowed_categories?: string[];
  allowed_merchants?: string[];
  max_uses?: number;
  conditions?: Condition[];
};

type MandateRecord = {
  mandate: {
    mandate_id: string;
    human?: { name?: string };
    constraints?: Constraints;
    payment_token?: { token_id?: string; masked_card?: string };
  };
  live_state: LiveState;
};

type Flight = { id: string; route: string; price: number; category: string; merchant_id: string };
type Check = { rule: string; pass: boolean; detail: string };
type Verification = { verdict: "APPROVE" | "ESCALATE" | "REJECT"; checks: Check[]; human_readable?: string };
type AgentRun = {
  verification?: Verification;
  verdict?: Verification["verdict"];
  checks?: Check[];
  human_readable?: string;
  selected_flight?: Flight;
  flights_seen?: Flight[];
  purchase_completed?: boolean;
};

type DecisionPhase = "idle" | "discovering" | "evaluating" | "choosing" | "verifying";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) throw new Error(`El sistema respondió ${response.status}.`);
  return response.json() as Promise<T>;
}

function verdictState(verdict: Verification["verdict"]): SaturdayState {
  return verdict === "APPROVE" ? "approve" : verdict === "ESCALATE" ? "escalate" : "reject";
}

function amount(value?: number, currency = "USD") {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency, maximumFractionDigits: 0 }).format(value ?? 0);
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
}

type MissionControlProps = {
  mandateId: string;
  onCreateNew: () => void;
};

function MissionControl({ mandateId, onCreateNew }: MissionControlProps) {
  const [mandate, setMandate] = useState<MandateRecord | null>(null);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [pendingVerification, setPendingVerification] = useState<Verification | null>(null);
  const [activity, setActivity] = useState<AgentRun | null>(null);
  const [saturdayState, setSaturdayState] = useState<SaturdayState>("idle");
  const [busy, setBusy] = useState<"loading" | "running" | "revoking" | null>("loading");
  const [error, setError] = useState<string | null>(null);
  const [phase, setPhase] = useState<DecisionPhase>("idle");
  const [scannedFlight, setScannedFlight] = useState<number | null>(null);
  const [chosenFlightId, setChosenFlightId] = useState<string | null>(null);
  const [revealedChecks, setRevealedChecks] = useState(0);

  const constraints = mandate?.mandate.constraints ?? {};
  const priceLimit = useMemo(
    () => constraints.conditions?.find((condition) => condition.type === "price_below")?.value,
    [constraints.conditions],
  );
  const evaluationLimit = Math.min(
    constraints.max_amount_per_purchase ?? Number.POSITIVE_INFINITY,
    priceLimit ?? Number.POSITIVE_INFINITY,
  );
  const phaseCopy: Record<DecisionPhase, string> = {
    idle: "",
    discovering: "Descubriendo vuelos…",
    evaluating: "Evaluando límites…",
    choosing: "Eligiendo la mejor opción…",
    verifying: "Verificando con el guardián…",
  };

  const loadMission = useCallback(async (preserveSaturday = false) => {
    setBusy("loading");
    setError(null);
    try {
      const [mandateData, flightData] = await Promise.all([
        request<MandateRecord>(`/mandates/${mandateId}`),
        request<Flight[]>("/merchant/flights"),
      ]);
      setMandate(mandateData);
      setFlights(flightData);
      if (!preserveSaturday) setSaturdayState(mandateData.live_state.status === "revoked" ? "reject" : "idle");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No hay conexión con el sistema.");
    } finally {
      setBusy(null);
    }
  }, [mandateId]);

  useEffect(() => { void loadMission(); }, [loadMission]);

  async function runAgent() {
    setBusy("running");
    setError(null);
    // Un nuevo intento no debe mostrar el veredicto ni relato del intento anterior.
    setVerification(null);
    setPendingVerification(null);
    setActivity(null);
    setChosenFlightId(null);
    setRevealedChecks(0);
    setSaturdayState("thinking");

    try {
      // Se inicia la operación real al comienzo; la UI solo demora su presentación.
      const agentRequest = request<AgentRun>("/agent/run", {
        method: "POST",
        body: JSON.stringify({ mandate_id: mandateId }),
      });
      setPhase("discovering");
      for (let index = 0; index < flights.length; index += 1) {
        setScannedFlight(index);
        await wait(150);
      }
      setScannedFlight(null);
      await wait(250);
      setPhase("evaluating");
      await wait(850);

      // La elección nunca se inventa: esperamos el vuelo devuelto por /agent/run.
      const run = await agentRequest;
      const result: Verification = run.verification ?? {
        verdict: run.verdict ?? "REJECT",
        checks: run.checks ?? [],
        human_readable: run.human_readable,
      };
      setPhase("choosing");
      setChosenFlightId(run.selected_flight?.id ?? null);
      await wait(700);

      setPhase("verifying");
      setPendingVerification(result);
      for (let index = 1; index <= result.checks.length; index += 1) {
        setRevealedChecks(index);
        await wait(160);
      }
      setActivity(run);
      setVerification(result);
      setPendingVerification(null);
      setSaturdayState(verdictState(result.verdict));
      const mandateData = await request<MandateRecord>(`/mandates/${mandateId}`);
      setMandate(mandateData);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No hay conexión con el sistema.");
      setSaturdayState(mandate?.live_state.status === "revoked" ? "reject" : "idle");
    } finally {
      setPhase("idle");
      setScannedFlight(null);
      setBusy(null);
    }
  }

  async function revokeMandate() {
    setBusy("revoking");
    setError(null);
    try {
      await request<MandateRecord>(`/mandates/${mandateId}/revoke`, { method: "POST" });
      const mandateData = await request<MandateRecord>(`/mandates/${mandateId}`);
      setMandate(mandateData);
      // La aprobación anterior ya no representa el estado real del mandato.
      setVerification(null);
      setPendingVerification(null);
      setActivity(null);
      setChosenFlightId(null);
      setRevealedChecks(0);
      setPhase("idle");
      setSaturdayState("reject");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No hay conexión con el sistema.");
    } finally {
      setBusy(null);
    }
  }

  const status = mandate?.live_state.status ?? "loading";
  const statusLabel = status === "active" ? "ACTIVO" : status === "revoked" ? "REVOCADO" : status === "expired" ? "EXPIRADO" : "CARGANDO";
  const displayedVerification = verification ?? pendingVerification;
  const displayedChecks = verification
    ? verification.checks
    : pendingVerification?.checks.slice(0, revealedChecks) ?? [];

  return (
    <main className="mission-shell">
      <div className="starfield" aria-hidden="true" />
      <div className="mission-control">
        <header className="mission-header">
          <div>
            <p className="mission-kicker">AGENTBUYER / MISSION CONTROL</p>
            <h1>Centro de confianza para compras de agentes</h1>
          </div>
          <div className="mission-header-actions">
            <button className="new-mandate-button" onClick={onCreateNew} disabled={busy !== null} type="button">+ CREAR NUEVO MANDATO</button>
            <button className="refresh-button" onClick={() => void loadMission(true)} disabled={busy !== null} type="button">
              {busy === "loading" ? "RECARGANDO…" : "↻ REINICIAR VISTA"}
            </button>
          </div>
        </header>

        {error && <div className="connection-error" role="alert"><strong>No hay conexión con el sistema.</strong> {error} Comprueba que FastAPI esté activo en el puerto 8000.</div>}

        <section className="mandate-panel">
          <div className="mandate-heading">
            <div>
              <p className="panel-eyebrow">MANDATO ACTIVO · {mandate?.mandate.human?.name ?? "MARTA"}</p>
              <h2>{mandate?.mandate.mandate_id ?? mandateId}</h2>
              <div style={{ display: "flex", gap: "8px", marginTop: "4px", flexWrap: "wrap" }}>
                <span style={{ background: "rgba(59, 130, 246, 0.15)", color: "#93c5fd", padding: "2px 8px", borderRadius: "10px", fontSize: "0.7rem", border: "1px solid rgba(59, 130, 246, 0.3)" }}>
                  🛡️ DLP: {mandate?.mandate.payment_token?.masked_card ?? "•••• 4242"} ({mandate?.mandate.payment_token?.token_id ?? "vtok_scoped"})
                </span>
                <span style={{ background: "rgba(16, 185, 129, 0.15)", color: "#6ee7b7", padding: "2px 8px", borderRadius: "10px", fontSize: "0.7rem", border: "1px solid rgba(16, 185, 129, 0.3)" }}>
                  🔐 Passkey &amp; SMS OTP Confirmados
                </span>
              </div>
            </div>
            <span className={`status-pill status-${status}`}>{statusLabel}</span>
          </div>
          <div className="limit-grid">
            <div><span>MÁX. POR COMPRA</span><strong>{amount(constraints.max_amount_per_purchase, constraints.currency)}</strong></div>
            <div><span>CATEGORÍA</span><strong>{constraints.allowed_categories?.[0] ?? "—"}</strong></div>
            <div><span>COMERCIO</span><strong>{constraints.allowed_merchants?.[0] ?? "—"}</strong></div>
            <div><span>USOS</span><strong>{mandate ? `${mandate.live_state.uses_count}/${constraints.max_uses ?? "—"}` : "—"}</strong></div>
            <div><span>CONDICIÓN</span><strong>precio &lt; {amount(priceLimit, constraints.currency)}</strong></div>
          </div>
        </section>

        <section className="control-grid">
          <aside className="side-panel flights-panel">
            <div className="panel-title"><span>VUELOS DESCUBIERTOS</span><small>{flights.length} EN CATÁLOGO</small></div>
            <div className="flight-list">
              {flights.map((flight, index) => {
                const isEvaluating = phase === "evaluating" || phase === "choosing" || phase === "verifying";
                const passesLimit = flight.price <= (constraints.max_amount_per_purchase ?? Number.POSITIVE_INFINITY)
                  && flight.price < (priceLimit ?? Number.POSITIVE_INFINITY);
                const isChosen = chosenFlightId === flight.id;
                return (
                  <motion.article
                    className={`flight-card ${scannedFlight === index ? "flight-scanning" : ""} ${isEvaluating ? (passesLimit ? "flight-eligible" : "flight-ineligible") : ""} ${isChosen ? "flight-chosen" : ""}`}
                    key={flight.id}
                    animate={scannedFlight === index ? { scale: [1, 1.035, 1] } : { scale: 1 }}
                    transition={{ duration: 0.2 }}
                  >
                    <div><p>{flight.route}</p><span>{flight.id}</span>{isEvaluating && <em>{passesLimit ? "dentro del límite" : `excede ${amount(evaluationLimit, constraints.currency)}`}</em>}{isChosen && <em className="chosen-label">elegido por Saturday</em>}</div>
                    <strong>{amount(flight.price)}</strong>
                  </motion.article>
                );
              })}
              {!flights.length && <p className="empty-copy">Esperando el catálogo de VuelaYa…</p>}
            </div>
          </aside>

          <section className="saturday-command">
            <p className="agent-label">SATURDAY / AGENTE AUTORIZADO</p>
            <Saturday state={saturdayState} />
            <p className={`saturday-state state-${saturdayState}`}>{phase !== "idle" ? phaseCopy[phase] : saturdayState.toUpperCase()}</p>
            <div className="action-stack">
              <button className="run-button" onClick={() => void runAgent()} disabled={busy !== null} type="button">
                {busy === "running" ? "SATURDAY ESTÁ DECIDIENDO…" : "CORRER AGENTE"}
              </button>
              <button className="revoke-button" onClick={() => void revokeMandate()} disabled={busy !== null || status === "revoked"} type="button">
                {busy === "revoking" ? "REVOCANDO…" : status === "revoked" ? "MANDATO REVOCADO" : "REVOCAR MANDATO"}
              </button>
            </div>
          </section>

          <aside className="side-panel verification-panel">
            <div className="panel-title"><span>PANEL DE VERIFICACIÓN</span><small>{displayedVerification ? (phase === "verifying" ? "ESCANEANDO" : "ÚLTIMO INTENTO") : "EN ESPERA"}</small></div>
            {displayedVerification ? (
              <>
                {phase === "verifying" ? <div className="verdict verdict-scanning">VERIFICANDO</div> : <div className={`verdict verdict-${displayedVerification.verdict.toLowerCase()}`}>{displayedVerification.verdict}</div>}
                <div className="checks-list">
                  <AnimatePresence initial={false}>
                  {displayedChecks.map((check, index) => (
                    <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className={`check-row ${check.pass ? "check-pass" : "check-fail"}`} key={`${check.rule}-${index}`}>
                      <b>{check.pass ? "✓" : "✕"}</b><div><strong>{check.rule}</strong><span>{check.detail}</span></div>
                    </motion.div>
                  ))}
                  </AnimatePresence>
                </div>
              </>
            ) : <p className="empty-copy">{status === "revoked" ? "Mandato revocado — corre el agente para ver el resultado real del siguiente intento." : "Corre a Saturday para ver los checks reales del backend."}</p>}
          </aside>
        </section>

        <section className="activity-panel">
          <div className="panel-title"><span>ACTIVIDAD DEL AGENTE</span><small>{activity ? "REGISTRO REAL" : "SIN EJECUCIONES"}</small></div>
          {activity ? (
            <div className="activity-content">
              <p>{activity.human_readable ?? activity.verification?.human_readable ?? "Saturday terminó su evaluación."}</p>
              {activity.selected_flight && <span>Intento: <b>{activity.selected_flight.route}</b> · {amount(activity.selected_flight.price)} · {activity.purchase_completed ? "compra completada" : "compra no procedió"}</span>}
            </div>
          ) : <p className="empty-copy">{status === "revoked" ? "El mandato fue revocado. El próximo intento del agente quedará registrado aquí." : "La narración de descubrimiento y decisión aparecerá aquí."}</p>}
        </section>
      </div>
    </main>
  );
}

function App() {
  const [activeMandateId, setActiveMandateId] = useState<string | null>(null);

  if (!activeMandateId) {
    return <MandateCreator onCreated={setActiveMandateId} />;
  }

  return <MissionControl mandateId={activeMandateId} onCreateNew={() => setActiveMandateId(null)} />;
}

export default App;
