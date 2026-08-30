import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import Saturday, { type SaturdayState } from "./components/Saturday";
import MandateCreator from "./components/MandateCreator";
import AccountView from "./components/AccountView";
import AuditView from "./components/AuditView";
import { checkDetailLabel, checkRuleLabel, displayName, localizedText, saturdayStateLabel, translateBackendText, verdictLabel } from "./lib/presentation";

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

type SearchFields = {
  origin?: string;
  destination?: string;
  departure_date?: string;
};

type MandateRecord = {
  mandate: { mandate_id: string; human?: { name?: string }; constraints?: Constraints; search_fields?: SearchFields };
  live_state: LiveState;
};

type Flight = { id: string; route: string; price: number; category: string; merchant_id: string; merchant?: string; details?: string; url?: string; source?: "web" };
type Check = { rule: string; pass: boolean; detail: string };
type Verification = { verdict: "APPROVE" | "ESCALATE" | "REJECT"; checks: Check[]; human_readable?: string };
type AgentRun = {
  attempt_id?: string | null;
  discovery_source?: string;
  verification?: Verification;
  verdict?: Verification["verdict"];
  checks?: Check[];
  human_readable?: string;
  selected_flight?: Flight | null;
  flights_seen?: Flight[];
  selection_reason?: string;
  no_offers?: boolean;
  purchase_completed?: boolean;
};

type Toast = { id: number; tone: "approve" | "escalate" | "reject"; message: string };

type DecisionPhase = "idle" | "discovering" | "evaluating" | "choosing" | "verifying";
type AppView = "mission" | "account" | "audit";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    // El backend explica sus 404/409/422 en `detail`; se traduce en la capa
    // de presentación (clave para los errores de la revisión humana).
    let message = `The system responded ${response.status}.`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (typeof body.detail === "string" && body.detail) message = translateBackendText(body.detail);
    } catch { /* cuerpo no-JSON: se conserva el mensaje genérico */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function verdictState(verdict: Verification["verdict"]): SaturdayState {
  return verdict === "APPROVE" ? "approve" : verdict === "ESCALATE" ? "escalate" : "reject";
}

function amount(value?: number, currency = "USD") {
  return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: 0 }).format(value ?? 0);
}

function wait(milliseconds: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, milliseconds));
}

function merchantName(flight?: Flight | null) {
  if (!flight) return "el comercio";
  return flight.merchant ?? (flight.merchant_id ? displayName(flight.merchant_id) : "el comercio");
}

function toastFor(run: AgentRun, result: Verification): Omit<Toast, "id"> {
  const flight = run.selected_flight;
  const purchaseAmount = flight?.price;
  const merchant = merchantName(flight);
  if (result.verdict === "APPROVE") return { tone: "approve", message: `💳 Payment approved — ${amount(purchaseAmount)} at ${merchant}` };
  if (result.verdict === "ESCALATE") return { tone: "escalate", message: `⏸ Needs your approval — ${amount(purchaseAmount)} at ${merchant}` };
  const revoked = result.checks.some((check) => check.rule === "status" && !check.pass && check.detail.toLowerCase().includes("revocado"));
  return revoked
    ? { tone: "reject", message: "🔒 Payment blocked — mandate revoked" }
    : { tone: "reject", message: "⚠ Attempt blocked — verification failed" };
}

type MissionControlProps = {
  mandateId: string;
  onCreateNew: () => void;
  onNavigate: (view: AppView) => void;
};

function MissionControl({ mandateId, onCreateNew, onNavigate }: MissionControlProps) {
  const [mandate, setMandate] = useState<MandateRecord | null>(null);
  const [flights, setFlights] = useState<Flight[]>([]);
  const [verification, setVerification] = useState<Verification | null>(null);
  const [pendingVerification, setPendingVerification] = useState<Verification | null>(null);
  const [activity, setActivity] = useState<AgentRun | null>(null);
  const [saturdayState, setSaturdayState] = useState<SaturdayState>("idle");
  const [busy, setBusy] = useState<"loading" | "running" | "revoking" | "resetting" | "reviewing" | null>("loading");
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [phase, setPhase] = useState<DecisionPhase>("idle");
  const [revealedChecks, setRevealedChecks] = useState(0);
  // Intento escalado pendiente de la decisión humana (approve/decline).
  const [escalatedAttemptId, setEscalatedAttemptId] = useState<string | null>(null);
  // La búsqueda web real no devolvió vuelos (ya no existe catálogo demo de respaldo).
  const [noOffers, setNoOffers] = useState(false);

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
    discovering: "Searching for real flights on the web…",
    evaluating: "Checking your limits…",
    choosing: "Picking the best option…",
    verifying: "Verifying with the gatekeeper…",
  };

  const loadMission = useCallback(async (preserveSaturday = false) => {
    setBusy("loading");
    setError(null);
    try {
      // Solo el mandato: los vuelos llegan de la búsqueda web real al correr el agente.
      const mandateData = await request<MandateRecord>(`/mandates/${mandateId}`);
      setMandate(mandateData);
      if (!preserveSaturday) setSaturdayState(mandateData.live_state.status === "revoked" ? "reject" : "idle");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No connection to the system.");
    } finally {
      setBusy(null);
    }
  }, [mandateId]);

  useEffect(() => { void loadMission(); }, [loadMission]);
  useEffect(() => {
    if (!toast) return undefined;
    const timeout = window.setTimeout(() => setToast(null), 3000);
    return () => window.clearTimeout(timeout);
  }, [toast]);

  async function runAgent() {
    setBusy("running");
    setError(null);
    // Un nuevo intento no debe mostrar el veredicto ni relato del intento anterior.
    setVerification(null);
    setPendingVerification(null);
    setActivity(null);
    setFlights([]);
    setRevealedChecks(0);
    setEscalatedAttemptId(null);
    setNoOffers(false);
    setSaturdayState("thinking");

    try {
      // La búsqueda web real puede tardar hasta un minuto; la fase "discovering"
      // dura lo que dure la petición, sin animaciones inventadas.
      setPhase("discovering");
      const run = await request<AgentRun>("/agent/run", {
        method: "POST",
        body: JSON.stringify({
          mandate_id: mandateId,
          ...(mandate?.mandate.search_fields ? { search_fields: mandate.mandate.search_fields } : {}),
        }),
      });

      // Sin catálogo demo: si la web no devolvió vuelos, se dice tal cual.
      if (run.no_offers || !run.selected_flight) {
        setNoOffers(true);
        setActivity(run);
        setSaturdayState(mandate?.live_state.status === "revoked" ? "reject" : "idle");
        return;
      }

      const result: Verification = run.verification ?? {
        verdict: run.verdict ?? "REJECT",
        checks: run.checks ?? [],
        human_readable: run.human_readable,
      };
      setFlights(run.flights_seen ?? []);
      setPhase("evaluating");
      await wait(850);
      setPhase("choosing");
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
      // Una escalación queda pendiente de la decisión humana (approve/decline).
      setEscalatedAttemptId(result.verdict === "ESCALATE" ? run.attempt_id ?? null : null);
      setSaturdayState(verdictState(result.verdict));
      setToast({ id: Date.now(), ...toastFor(run, result) });
      const mandateData = await request<MandateRecord>(`/mandates/${mandateId}`);
      setMandate(mandateData);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No connection to the system.");
      setSaturdayState(mandate?.live_state.status === "revoked" ? "reject" : "idle");
    } finally {
      setPhase("idle");
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
      setFlights([]);
      setNoOffers(false);
      setRevealedChecks(0);
      setEscalatedAttemptId(null);
      setPhase("idle");
      setSaturdayState("reject");
      setToast({ id: Date.now(), tone: "reject", message: "🔒 Mandato revocado — Saturday ya no puede comprar" });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No connection to the system.");
    } finally {
      setBusy(null);
    }
  }

  async function reviewEscalation(decision: "approve" | "decline") {
    if (!escalatedAttemptId) return;
    setBusy("reviewing");
    setError(null);
    try {
      const result = await request<Verification>(`/mandates/${mandateId}/approve_escalation`, {
        method: "POST",
        body: JSON.stringify({ purchase_attempt_id: escalatedAttemptId, decision }),
      });
      // La respuesta tiene la misma forma que /verify: se renderiza como cualquier veredicto.
      setVerification(result);
      setSaturdayState(verdictState(result.verdict));
      setEscalatedAttemptId(null);
      setToast({
        id: Date.now(),
        tone: decision === "approve" ? "approve" : "reject",
        message: decision === "approve" ? "✅ Aprobaste la compra — registrada" : "🚫 Rechazaste la compra",
      });
      const mandateData = await request<MandateRecord>(`/mandates/${mandateId}`);
      setMandate(mandateData);
    } catch (caught) {
      // El mandato pudo revocarse entre la escalación y la decisión: el backend lo explica.
      setError(caught instanceof Error ? caught.message : "No connection to the system.");
    } finally {
      setBusy(null);
    }
  }

  async function resetMission() {
    setBusy("resetting");
    setError(null);
    try {
      const record = await request<MandateRecord>(`/mandates/${mandateId}/reset`, { method: "POST" });
      setMandate(record);
      setVerification(null);
      setPendingVerification(null);
      setActivity(null);
      setFlights([]);
      setNoOffers(false);
      setRevealedChecks(0);
      setEscalatedAttemptId(null);
      setPhase("idle");
      setSaturdayState("idle");
      setToast(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No connection to the system.");
    } finally {
      setBusy(null);
    }
  }

  const status = mandate?.live_state.status ?? "loading";
  const statusLabel = status === "active" ? "ACTIVE" : status === "revoked" ? "REVOKED" : status === "expired" ? "EXPIRED" : "LOADING";
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
            <h1>Centro de confianza para agentes</h1>
          </div>
          <div className="mission-header-actions">
            <button className="new-mandate-button" onClick={() => { if (window.confirm("Leave and create a new permission? The current view will be cleared.")) onCreateNew(); }} disabled={busy !== null} type="button">+ START OVER</button>
            <button className="refresh-button" onClick={() => void resetMission()} disabled={busy !== null} type="button">
              {busy === "resetting" ? "RESETTING…" : "↻ RESET VIEW"}
            </button>
          </div>
        </header>

        {error && <div className="connection-error" role="alert"><strong>Something went wrong.</strong> {error} Check that FastAPI is running on port 8000.</div>}
        <AnimatePresence>
          {toast && <motion.div className={`push-toast toast-${toast.tone}`} key={toast.id} initial={{ opacity: 0, x: 72, y: -10 }} animate={{ opacity: 1, x: 0, y: 0 }} exit={{ opacity: 0, x: 72, y: -10 }} transition={{ type: "spring", stiffness: 330, damping: 28 }} role="status">{toast.message}</motion.div>}
        </AnimatePresence>

        <section className="mandate-panel">
          <div className="mandate-heading">
            <div>
              <p className="panel-eyebrow">ACTIVE MANDATE · {mandate?.mandate.human?.name ?? "MARTA"}</p>
              <h2>{mandate?.mandate.mandate_id ?? mandateId}</h2>
            </div>
            <span className={`status-pill status-${status}`}>{statusLabel}</span>
          </div>
          <div className="limit-grid">
            <div><span>MAX PER PURCHASE</span><strong>{amount(constraints.max_amount_per_purchase, constraints.currency)}</strong></div>
            <div><span>CATEGORY</span><strong>{constraints.allowed_categories?.[0] ? displayName(constraints.allowed_categories[0]) : "—"}</strong></div>
            <div><span>MERCHANT</span><strong>{constraints.allowed_merchants?.[0] ? displayName(constraints.allowed_merchants[0]) : "—"}</strong></div>
            <div><span>USES</span><strong>{mandate ? `${mandate.live_state.uses_count}/${constraints.max_uses ?? "—"}` : "—"}</strong></div>
            <div><span>CONDITION</span><strong>price &lt; {amount(priceLimit, constraints.currency)}</strong></div>
          </div>
        </section>

        <section className="control-grid">
          <aside className="side-panel flights-panel">
            <div className="panel-title"><span>SATURDAY'S SEARCH</span><small>{phase === "discovering" ? "SEARCHING" : activity?.selected_flight ? "CHOICE MADE" : noOffers ? "NO RESULTS" : flights.length ? "EVALUATING" : "STANDING BY"}</small></div>

            {phase === "discovering" && (
              <div className="search-live" role="status">
                <span className="search-pulse" aria-hidden="true" />
                <p>Saturday is searching for real flights on the web…<br /><small>This can take up to a minute.</small></p>
              </div>
            )}

            {phase !== "discovering" && noOffers && (
              <p className="no-offers-note" role="status">
                Saturday couldn't find flights right now — try again.
              </p>
            )}

            {/* Momento héroe: la elección de Saturday, una sola tarjeta protagonista. */}
            {phase === "idle" && activity?.selected_flight && (() => {
              const chosen = activity.selected_flight;
              if (!chosen) return null;
              const others = flights.filter((flight) => flight.id !== chosen.id);
              const verdict = verification?.verdict ?? activity.verification?.verdict;
              const heroBadge = activity.purchase_completed
                ? { tone: "approve", text: "✓ Purchased" }
                : verdict === "ESCALATE"
                  ? { tone: "escalate", text: "⏸ Waiting for your approval" }
                  : verdict === "APPROVE"
                    ? { tone: "approve", text: "✓ Approved" }
                    : { tone: "reject", text: "✕ Blocked" };
              const withinLimit = chosen.price < (priceLimit ?? Number.POSITIVE_INFINITY)
                && chosen.price <= (constraints.max_amount_per_purchase ?? Number.POSITIVE_INFINITY);
              return (
                <>
                  <motion.article className="flight-hero" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.35 }}>
                    <p className="hero-kicker">SATURDAY PICKED THIS FLIGHT FOR YOU</p>
                    <div className="hero-main">
                      <strong className="hero-route">{chosen.route.replace("->", " → ")}</strong>
                      <strong className="hero-price">{amount(chosen.price)}</strong>
                    </div>
                    <p className="hero-merchant">{merchantName(chosen)}{chosen.details ? ` · ${chosen.details}` : ""}</p>
                    <p className="hero-reason">{withinLimit ? "The cheapest option that meets your price condition." : "No option met your limit; it attempted the cheapest one available."}</p>
                    <span className={`hero-badge badge-${heroBadge.tone}`}>{heroBadge.text}</span>
                  </motion.article>
                  {others.length > 0 && (
                    <div className="other-options">
                      <p className="other-options-title">Other options Saturday found</p>
                      {others.map((flight) => (
                        <div className="other-option" key={flight.id}>
                          <span>{merchantName(flight)}{flight.details ? ` · ${flight.details}` : ""}</span>
                          <b>{amount(flight.price)}</b>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              );
            })()}

            {/* Mientras evalúa/elige/verifica: las opciones reales, sin protagonismo aún. */}
            {(phase === "evaluating" || phase === "choosing" || phase === "verifying") && (
              <div className="flight-list">
                {flights.map((flight) => {
                  const passesLimit = flight.price <= (constraints.max_amount_per_purchase ?? Number.POSITIVE_INFINITY)
                    && flight.price < (priceLimit ?? Number.POSITIVE_INFINITY);
                  return (
                    <motion.article className={`flight-card ${passesLimit ? "flight-eligible" : "flight-ineligible"}`} key={flight.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }}>
                      <div><p>{flight.route.replace("->", " → ")}</p><span>{merchantName(flight)}</span><em>{passesLimit ? "within your limit" : `exceeds ${amount(evaluationLimit, constraints.currency)}`}</em></div>
                      <div className="flight-price"><strong>{amount(flight.price)}</strong></div>
                    </motion.article>
                  );
                })}
              </div>
            )}

            {phase === "idle" && !activity && !noOffers && (
              <p className="empty-copy">{status === "revoked" ? "Mandate revoked — you can still run the agent to watch the attempt get blocked." : "Run Saturday: it will search for real flights on the web within your permission."}</p>
            )}
          </aside>

          <section className="saturday-command">
            <p className="agent-label">SATURDAY / AUTHORIZED AGENT</p>
            <Saturday state={saturdayState} />
            <p className={`saturday-state state-${saturdayState}`}>{phase !== "idle" ? phaseCopy[phase] : saturdayStateLabel(saturdayState)}</p>
            <div className="action-stack">
              <button className="run-button" onClick={() => void runAgent()} disabled={busy !== null} type="button">
                {busy === "running" ? "SATURDAY IS DECIDING…" : "RUN AGENT"}
              </button>
              <button className="revoke-button" onClick={() => void revokeMandate()} disabled={busy !== null || status === "revoked"} type="button">
                {busy === "revoking" ? "REVOKING…" : status === "revoked" ? "MANDATE REVOKED" : "REVOKE MANDATE"}
              </button>
            </div>
            {status === "revoked" && <p className="revoked-run-hint">The mandate is revoked — run the agent to watch the system block the attempt.</p>}
          </section>

          <aside className="side-panel verification-panel">
            <div className="panel-title"><span>VERIFICATION PANEL</span><small>{displayedVerification ? (phase === "verifying" ? "SCANNING" : "LAST ATTEMPT") : "STANDING BY"}</small></div>
            {displayedVerification ? (
              <>
                {phase === "verifying" ? <div className="verdict verdict-scanning">VERIFYING</div> : <div className={`verdict verdict-${displayedVerification.verdict.toLowerCase()}`}>{verdictLabel(displayedVerification.verdict)}</div>}
                <div className="checks-list">
                  <AnimatePresence initial={false}>
                  {displayedChecks.map((check, index) => (
                    <motion.div initial={{ opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className={`check-row ${check.pass ? "check-pass" : "check-fail"}`} key={`${check.rule}-${index}`}>
                      <b>{check.pass ? "✓" : "✕"}</b><div><strong>{checkRuleLabel(check.rule)}</strong><span>{checkDetailLabel(check.rule, check.detail)}</span></div>
                    </motion.div>
                  ))}
                  </AnimatePresence>
                </div>
                {verification?.verdict === "ESCALATE" && escalatedAttemptId && phase === "idle" && (
                  <div className="human-review">
                    <p>⚠ Escalated — nothing is approved silently. You decide:</p>
                    <div className="human-review-actions">
                      <button className="human-approve" disabled={busy !== null} onClick={() => void reviewEscalation("approve")} type="button">
                        {busy === "reviewing" ? "RECORDING…" : "✓ APPROVE"}
                      </button>
                      <button className="human-decline" disabled={busy !== null} onClick={() => void reviewEscalation("decline")} type="button">
                        ✕ DECLINE
                      </button>
                    </div>
                  </div>
                )}
                {verification && phase === "idle" && <div className="result-links">
                  {verification.verdict === "APPROVE" && <button onClick={() => onNavigate("account")} type="button">✓ Purchase recorded — see it in My purchases</button>}
                  <button onClick={() => onNavigate("audit")} type="button">This attempt is on the record — view in Audit →</button>
                </div>}
              </>
            ) : <p className="empty-copy">{status === "revoked" ? "Mandate revoked — run the agent to see the real outcome of the next attempt." : "Run Saturday to see the backend's real checks."}</p>}
          </aside>
        </section>

        <section className="activity-panel">
          <div className="panel-title"><span>AGENT ACTIVITY</span><small>{activity ? "REAL RECORD" : "NO RUNS YET"}</small></div>
          {activity ? (
            <div className="activity-content">
              <p>{localizedText(activity.human_readable ?? activity.verification?.human_readable ?? "Saturday finished its evaluation.")}</p>
              {activity.selected_flight && <span>Attempt: <b>{activity.selected_flight.route}</b> · {amount(activity.selected_flight.price)} · {activity.purchase_completed ? "purchase completed" : "purchase did not proceed"}</span>}
            </div>
          ) : <p className="empty-copy">{status === "revoked" ? "The mandate was revoked. The agent's next attempt will be recorded here." : "The discovery-and-decision story will appear here."}</p>}
        </section>
      </div>
    </main>
  );
}

function App() {
  const [activeMandateId, setActiveMandateId] = useState<string | null>(null);
  const [view, setView] = useState<AppView>("mission");

  if (!activeMandateId) {
    return <MandateCreator onCreated={(mandateId) => { setActiveMandateId(mandateId); setView("mission"); }} />;
  }

  return (
    <>
      <nav className="app-nav" aria-label="Main navigation">
        <button className="nav-brand" onClick={() => setView("mission")} type="button"><span>Saturday</span><small>by AgentBuyer</small></button>
        <div className="nav-links">
          <button className={view === "mission" ? "is-active" : ""} onClick={() => setView("mission")} type="button">Mission Control</button>
          <button className={view === "account" ? "is-active" : ""} onClick={() => setView("account")} type="button">My purchases</button>
          <button className={view === "audit" ? "is-active" : ""} onClick={() => setView("audit")} type="button">Audit</button>
        </div>
      </nav>
      {view === "mission" && <MissionControl mandateId={activeMandateId} onCreateNew={() => setActiveMandateId(null)} onNavigate={setView} />}
      {view === "account" && <AccountView mandateId={activeMandateId} />}
      {view === "audit" && <AuditView />}
    </>
  );
}

export default App;
