import { useCallback, useEffect, useState } from "react";
import { auditTypeLabel, localizedText, verdictLabel } from "../lib/presentation";

const API_BASE = "http://127.0.0.1:8000";

type AuditEvent = {
  event_id: string; timestamp: string; type: string; mandate_id: string;
  attempt_id?: string; verdict?: "APPROVE" | "ESCALATE" | "REJECT"; summary: string;
};
type MandateRecord = {
  live_state: { status: string; uses_count: number; amount_spent: number };
  mandate: { human?: { id?: string; display_name?: string }; constraints?: { max_uses?: number; currency?: string } };
};
type DisputeClaim = {
  dispute_id: string; attempt_id: string; verdict?: string;
  liable_party?: "HUMAN" | "MERCHANT" | "FRAUDSTER" | "AGENT";
  refund_issued: boolean; explanation?: string;
};

function formatDate(timestamp: string) {
  return new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" }).format(new Date(timestamp));
}

function amount(value: number, currency = "USD") {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

// Traduce el veredicto forense del árbitro a lenguaje para el titular.
function liableCopy(party?: string): { label: string; tone: "human" | "protected" } {
  switch (party) {
    case "MERCHANT": return { label: "Comercio responsable", tone: "protected" };
    case "FRAUDSTER": return { label: "Fraude — titular protegido", tone: "protected" };
    case "AGENT": return { label: "Agente responsable", tone: "protected" };
    default: return { label: "Cargo válido — titular responsable", tone: "human" };
  }
}

// Un cargo disputable es una compra que efectivamente ocurrió.
function isDisputable(event: AuditEvent): boolean {
  return Boolean(
    event.attempt_id &&
    (event.verdict === "APPROVE" || event.type === "purchase_completed" || event.type === "human_override_approved"),
  );
}

export default function AccountView({ mandateId }: { mandateId: string }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [mandate, setMandate] = useState<MandateRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [disputingId, setDisputingId] = useState<string | null>(null);
  const [dispute, setDispute] = useState<DisputeClaim | null>(null);
  const [disputeError, setDisputeError] = useState<string | null>(null);

  const loadAccount = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [trailResponse, mandateResponse] = await Promise.all([
        fetch(`${API_BASE}/audit/${mandateId}`),
        fetch(`${API_BASE}/mandates/${mandateId}`),
      ]);
      if (!trailResponse.ok || !mandateResponse.ok) throw new Error("No fue posible actualizar tu información.");
      setEvents(await trailResponse.json() as AuditEvent[]);
      setMandate(await mandateResponse.json() as MandateRecord);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No hay conexión con el sistema.");
    } finally {
      setLoading(false);
    }
  }, [mandateId]);

  useEffect(() => { void loadAccount(); }, [loadAccount]);

  async function fileDispute(attemptId: string) {
    setDisputingId(attemptId);
    setDisputeError(null);
    setDispute(null);
    try {
      const claimantId = mandate?.mandate.human?.id ?? "hum_cardholder";
      const response = await fetch(`${API_BASE}/disputes/file`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          attempt_id: attemptId,
          mandate_id: mandateId,
          claimant_id: claimantId,
          reason: "No reconozco este cargo — el titular niega haberlo autorizado.",
        }),
      });
      if (!response.ok) {
        let message = `El sistema respondió ${response.status}.`;
        try { const body = await response.json() as { detail?: string }; if (body.detail) message = body.detail; } catch { /* no-json */ }
        throw new Error(message);
      }
      setDispute(await response.json() as DisputeClaim);
      // El árbitro deja un evento en el trail; refrescamos para que se vea.
      void loadAccount();
    } catch (caught) {
      setDisputeError(caught instanceof Error ? caught.message : "No se pudo abrir la disputa.");
    } finally {
      setDisputingId(null);
    }
  }

  const status = mandate?.live_state.status === "active" ? "ACTIVO" : mandate?.live_state.status === "revoked" ? "REVOCADO" : "CARGANDO";
  const verdictCounts = events.reduce((counts, event) => {
    if (event.verdict === "APPROVE") counts.approve += 1;
    if (event.verdict === "ESCALATE") counts.escalate += 1;
    if (event.verdict === "REJECT") counts.reject += 1;
    return counts;
  }, { approve: 0, escalate: 0, reject: 0 });

  const liable = liableCopy(dispute?.liable_party);

  return (
    <main className="reading-shell">
      <section className="reading-page">
        <header className="reading-header"><div><p className="mission-kicker">MI CUENTA / TU HISTORIAL</p><h1>Lo que Saturday compró por ti</h1><p>Revisa con calma cada decisión tomada dentro de tu permiso.</p></div><button className="refresh-button" onClick={() => void loadAccount()} disabled={loading} type="button">{loading ? "ACTUALIZANDO…" : "↻ ACTUALIZAR"}</button></header>
        {error && <div className="connection-error" role="alert"><strong>No hay conexión con el sistema.</strong> {error}</div>}

        {/* Veredicto de la disputa: el trail auditable resuelve quién tiene razón. */}
        {dispute && (
          <div className={`dispute-card dispute-${liable.tone}`} role="status">
            <div className="dispute-card-head">
              <span className="dispute-eyebrow">RESOLUCIÓN DE DISPUTA · {dispute.dispute_id}</span>
              <button className="dispute-close" onClick={() => setDispute(null)} type="button" aria-label="Cerrar">✕</button>
            </div>
            <h2>{liable.label}</h2>
            <div className="dispute-badges">
              <span className={`dispute-badge ${dispute.refund_issued ? "refund-yes" : "refund-no"}`}>
                {dispute.refund_issued ? "💸 Reembolso emitido" : "🚫 Sin reembolso"}
              </span>
              {dispute.verdict && <span className="dispute-badge verdict-code">{dispute.verdict}</span>}
            </div>
            {dispute.explanation && <p className="dispute-explanation">{dispute.explanation}</p>}
            <p className="dispute-foot">Resuelto por el árbitro sobre la evidencia criptográfica del registro append-only.</p>
          </div>
        )}
        {disputeError && <div className="connection-error" role="alert">{disputeError}</div>}

        <div className="verdict-summary" aria-label="Resumen de decisiones"><span className="summary-approve">{verdictCounts.approve} aprobadas</span><span className="summary-escalate">{verdictCounts.escalate} requieren aprobación</span><span className="summary-reject">{verdictCounts.reject} rechazadas</span></div>
        <section className="account-summary">
          <div><span>ESTADO DEL PERMISO</span><b className={`account-status account-${status.toLowerCase()}`}>{status}</b></div>
          <div><span>GASTADO HASTA AHORA</span><strong>{amount(mandate?.live_state.amount_spent ?? 0, mandate?.mandate.constraints?.currency)}</strong></div>
          <div><span>COMPRAS USADAS</span><strong>{mandate ? `${mandate.live_state.uses_count}/${mandate.mandate.constraints?.max_uses ?? "—"}` : "—"}</strong></div>
        </section>
        <section className="timeline-panel"><div className="panel-title"><span>DECISIONES DE SATURDAY</span><small>{events.length} EVENTOS</small></div>
          {loading ? <p className="empty-copy">Cargando tu actividad…</p> : events.length ? <div className="timeline">{events.map((event) => (
            <article className="timeline-event" key={event.event_id}>
              <div className={`timeline-dot verdict-dot-${event.verdict?.toLowerCase() ?? "neutral"}`} />
              <div>
                <div className="event-meta"><span>{formatDate(event.timestamp)}</span><b>{auditTypeLabel(event.type)}</b>{event.verdict && <i className={`verdict-tag verdict-${event.verdict.toLowerCase()}`}>{verdictLabel(event.verdict)}</i>}</div>
                <p>{localizedText(event.summary)}</p>
                {isDisputable(event) && (
                  <button className="dispute-button" disabled={disputingId !== null} onClick={() => void fileDispute(event.attempt_id!)} type="button">
                    {disputingId === event.attempt_id ? "RESOLVIENDO DISPUTA…" : "⚖ No reconozco este cargo — disputar"}
                  </button>
                )}
              </div>
            </article>
          ))}</div> : <p className="empty-copy">Aún no hay actividad — corre a Saturday para empezar.</p>}
        </section>
      </section>
    </main>
  );
}
