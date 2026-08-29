import { useCallback, useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8000";

type AuditEvent = { event_id: string; timestamp: string; type: string; mandate_id: string; verdict?: "APPROVE" | "ESCALATE" | "REJECT"; summary: string };
type MandateRecord = { live_state: { status: string; uses_count: number; amount_spent: number }; mandate: { constraints?: { max_uses?: number; currency?: string } } };

function formatDate(timestamp: string) {
  return new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" }).format(new Date(timestamp));
}

function amount(value: number, currency = "USD") {
  return new Intl.NumberFormat("es-MX", { style: "currency", currency, maximumFractionDigits: 0 }).format(value);
}

export default function AccountView({ mandateId }: { mandateId: string }) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [mandate, setMandate] = useState<MandateRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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
  const status = mandate?.live_state.status === "active" ? "ACTIVO" : mandate?.live_state.status === "revoked" ? "REVOCADO" : "CARGANDO";
  const verdictCounts = events.reduce((counts, event) => {
    if (event.verdict === "APPROVE") counts.approve += 1;
    if (event.verdict === "ESCALATE") counts.escalate += 1;
    if (event.verdict === "REJECT") counts.reject += 1;
    return counts;
  }, { approve: 0, escalate: 0, reject: 0 });

  return (
    <main className="reading-shell">
      <section className="reading-page">
        <header className="reading-header"><div><p className="mission-kicker">MI CUENTA / TU HISTORIAL</p><h1>Lo que Saturday compró por ti</h1><p>Revisa con calma cada decisión tomada dentro de tu permiso.</p></div><button className="refresh-button" onClick={() => void loadAccount()} disabled={loading} type="button">{loading ? "ACTUALIZANDO…" : "↻ ACTUALIZAR"}</button></header>
        {error && <div className="connection-error" role="alert"><strong>No hay conexión con el sistema.</strong> {error}</div>}
        <div className="verdict-summary" aria-label="Resumen de decisiones"><span className="summary-approve">{verdictCounts.approve} aprobadas</span><span className="summary-escalate">{verdictCounts.escalate} escaladas</span><span className="summary-reject">{verdictCounts.reject} bloqueadas</span></div>
        <section className="account-summary">
          <div><span>ESTADO DEL PERMISO</span><b className={`account-status account-${status.toLowerCase()}`}>{status}</b></div>
          <div><span>GASTADO HASTA AHORA</span><strong>{amount(mandate?.live_state.amount_spent ?? 0, mandate?.mandate.constraints?.currency)}</strong></div>
          <div><span>COMPRAS USADAS</span><strong>{mandate ? `${mandate.live_state.uses_count}/${mandate.mandate.constraints?.max_uses ?? "—"}` : "—"}</strong></div>
        </section>
        <section className="timeline-panel"><div className="panel-title"><span>DECISIONES DE SATURDAY</span><small>{events.length} EVENTOS</small></div>
          {loading ? <p className="empty-copy">Cargando tu actividad…</p> : events.length ? <div className="timeline">{events.map((event) => <article className="timeline-event" key={event.event_id}><div className={`timeline-dot verdict-dot-${event.verdict?.toLowerCase() ?? "neutral"}`} /><div><div className="event-meta"><span>{formatDate(event.timestamp)}</span><b>{event.type.replace(/_/g, " ")}</b>{event.verdict && <i className={`verdict-tag verdict-${event.verdict.toLowerCase()}`}>{event.verdict}</i>}</div><p>{event.summary}</p></div></article>)}</div> : <p className="empty-copy">Aún no hay actividad — corre a Saturday para empezar.</p>}
        </section>
      </section>
    </main>
  );
}
