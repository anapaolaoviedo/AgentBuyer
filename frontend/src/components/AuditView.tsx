import { useCallback, useEffect, useState } from "react";
import { auditTypeLabel, displayName, localizedText, verdictLabel } from "../lib/presentation";

const API_BASE = "http://127.0.0.1:8000";
type AuditEvent = { event_id: string; timestamp: string; type: string; mandate_id: string; verdict?: "APPROVE" | "ESCALATE" | "REJECT"; summary: string };

function formatDate(timestamp: string) {
  return new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "medium" }).format(new Date(timestamp));
}

export default function AuditView() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const loadAudit = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/audit`);
      if (!response.ok) throw new Error("No fue posible cargar el registro completo.");
      setEvents(await response.json() as AuditEvent[]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "No hay conexión con el sistema.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { void loadAudit(); }, [loadAudit]);
  const verdictCounts = events.reduce((counts, event) => {
    if (event.verdict === "APPROVE") counts.approve += 1;
    if (event.verdict === "ESCALATE") counts.escalate += 1;
    if (event.verdict === "REJECT") counts.reject += 1;
    return counts;
  }, { approve: 0, escalate: 0, reject: 0 });
  return (
    <main className="reading-shell">
      <section className="reading-page">
        <header className="reading-header"><div><p className="mission-kicker">AUDITORÍA / TRAIL APPEND-ONLY</p><h1>Registro completo del sistema</h1><p>La historia verificable de cada mandato, decisión y resultado.</p></div><button className="refresh-button" onClick={() => void loadAudit()} disabled={loading} type="button">{loading ? "ACTUALIZANDO…" : "↻ ACTUALIZAR"}</button></header>
        {error && <div className="connection-error" role="alert"><strong>No hay conexión con el sistema.</strong> {error}</div>}
        <div className="verdict-summary" aria-label="Resumen contable del trail"><span className="summary-approve">{verdictCounts.approve} aprobadas</span><span className="summary-escalate">{verdictCounts.escalate} requieren aprobación</span><span className="summary-reject">{verdictCounts.reject} rechazadas</span></div>
        <section className="audit-panel"><div className="panel-title"><span>EVENTOS · MÁS RECIENTES PRIMERO</span><small>{events.length} REGISTROS</small></div>
          {loading ? <p className="empty-copy">Consultando el trail de auditoría…</p> : events.length ? <div className="audit-table-wrap"><table className="audit-table"><thead><tr><th>Fecha y hora</th><th>Tipo</th><th>Mandato</th><th>Veredicto</th><th>Resumen</th></tr></thead><tbody>{events.map((event) => <tr className={`audit-row-${event.verdict?.toLowerCase() ?? "neutral"}`} key={event.event_id}><td>{formatDate(event.timestamp)}</td><td><span className="event-type">{auditTypeLabel(event.type)}</span></td><td><code>{displayName(event.mandate_id)}</code></td><td>{event.verdict ? <span className={`verdict-tag verdict-${event.verdict.toLowerCase()}`}>{verdictLabel(event.verdict)}</span> : <span className="neutral-tag">—</span>}</td><td>{localizedText(event.summary)}</td></tr>)}</tbody></table></div> : <p className="empty-copy">Aún no hay actividad — corre a Saturday para empezar.</p>}
        </section>
      </section>
    </main>
  );
}
