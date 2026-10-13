import { useRef, useState } from "react";

type History = { task_id: string; objective: string; state: string; parent_task_id?: string | null };
type Rule = { rule_id: string; event_type: string; process_name: string; enabled: boolean };
type Note = { note_id: string; content: string; score: number };
type Candidate = { status: string; candidate_hash: string; [key: string]: unknown };
type Cost = { cost_task_id: string; totals: { external_calls: number; external_cost_usd: number; local_calls: number }; budget: { max_external_calls: number; max_external_cost_usd: number } };
type AuditEvent = { event_id: string; event_type: string; created_at: string; payload?: { process_name?: string; event_type?: string } };
const tabs = ["History", "Memory", "Alerts", "Review", "Routing", "Audit"] as const;

export function TaskTools({ api, taskId, onSelect }: { api: string; taskId?: string; onSelect: (id: string) => Promise<void> }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [tab, setTab] = useState<typeof tabs[number]>("History");
  const [history, setHistory] = useState<History[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [monitorReady, setMonitorReady] = useState(false);
  const [embeddingReady, setEmbeddingReady] = useState(false);
  const [notes, setNotes] = useState<Note[]>([]);
  const [content, setContent] = useState("");
  const [query, setQuery] = useState("");
  const [process, setProcess] = useState("");
  const [eventType, setEventType] = useState("PROCESS_EXITED");
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [route, setRoute] = useState<{ tier: string; reason: string } | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [alerts, setAlerts] = useState<AuditEvent[]>([]);
  const [cost, setCost] = useState<Cost | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function request<T>(path: string, body?: object, method = body ? "POST" : "GET"): Promise<T> {
    const response = await fetch(api + path, { method, signal: AbortSignal.timeout(60_000),
      ...(body ? { headers: { "content-type": "application/json" }, body: JSON.stringify(body) } : {}) });
    if (!response.ok) {
      const failure = await response.json().catch(() => null);
      throw new Error(typeof failure?.detail === "string" ? failure.detail : `Request failed (${response.status})`);
    }
    return response.json();
  }
  const taskPath = () => { if (!taskId) throw new Error("Select a task first."); return `/tasks/${encodeURIComponent(taskId)}`; };
  async function perform(job: () => Promise<void>) {
    setBusy(true); setError("");
    try { await job(); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  async function refresh() {
    const [tasks, status, ruleList, inference, recent] = await Promise.all([
      request<{ items: History[] }>("/tasks"), request<{ running: boolean }>("/monitor/status"),
      request<{ items: Rule[] }>("/monitor/rules"), request<{ models: Record<string, boolean> }>("/inference/status"),
      request<{ items: AuditEvent[] }>("/events?limit=200&latest=true"),
    ]);
    setHistory(tasks.items ?? []); setRules(ruleList.items ?? []); setMonitorReady(status.running);
    setAlerts(recent.items.filter((event) => event.event_type === "MonitorAlert"));
    setEmbeddingReady(Boolean(inference.models?.local_embedding));
    if (taskId) {
      const [usage, audit] = await Promise.all([request<Cost>(taskPath() + "/cost"), request<{ items: typeof events }>(`/events?task_id=${encodeURIComponent(taskId)}&limit=100&latest=true`)]);
      const root = usage.cost_task_id !== taskId ? await request<{ items: AuditEvent[] }>(`/events?task_id=${encodeURIComponent(usage.cost_task_id)}&limit=100&latest=true`) : { items: [] };
      setCost(usage); setEvents([...audit.items, ...root.items].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    } else { setCost(null); setEvents([]); }
  }
  return <>
    <button className="launch-button" onClick={() => { dialog.current?.showModal(); void perform(refresh); }}>Workspace tools</button>
    <dialog ref={dialog} className="composer-dialog" aria-labelledby="tools-title">
      <div className="dialog-panel workspace-tools">
        <div className="dialog-topline"><h2 id="tools-title">Workspace tools</h2><button className="dialog-close" aria-label="Close workspace tools" onClick={() => dialog.current?.close()}>×</button></div>
        <div className="mode-tabs" role="group" aria-label="Workspace tools sections">{tabs.map((name) => <button key={name} aria-pressed={tab === name} onClick={() => { setTab(name); setError(""); setCandidate(null); setRoute(null); }}>{name}</button>)}</div>
        <button className="subtle-button" disabled={busy} onClick={() => void perform(refresh)}>Refresh</button>
        {tab === "History" && <>
          {cost && <p>Shared budget: ${cost.totals.external_cost_usd.toFixed(4)} / ${cost.budget.max_external_cost_usd.toFixed(2)} · {cost.totals.external_calls} / {cost.budget.max_external_calls} external calls · {cost.totals.local_calls} local calls</p>}
          <ul className="tool-list">{history.map((task) => <li key={task.task_id}><button className="subtle-button" disabled={busy} onClick={() => void perform(async () => {
            await onSelect(task.task_id); setNotes([]); setCandidate(null); setCost(null); dialog.current?.close();
          })}>{task.objective}</button><small>{task.state.replaceAll("_", " ")} · {task.task_id.slice(-8)}{task.parent_task_id ? " · linked task" : ""}</small></li>)}</ul>
          {!history.length && <p>No saved tasks.</p>}
        </>}
        {tab === "Memory" && <div className="modal-form">
          {!embeddingReady && <p>A configured local embedding model is required. Notes stay local.</p>}
          <label htmlFor="memory-note">Note</label><textarea id="memory-note" maxLength={4000} value={content} onChange={(e) => setContent(e.target.value)} />
          <button className="accent-button" disabled={busy || !taskId || !embeddingReady || !content.trim()} onClick={() => void perform(async () => { await request(taskPath() + "/memory", { content }); setContent(""); })}>Save note</button>
          <label htmlFor="memory-query">Search notes</label><input id="memory-query" maxLength={4000} value={query} onChange={(e) => setQuery(e.target.value)} />
          <button className="subtle-button" disabled={busy || !taskId || !embeddingReady || !query.trim()} onClick={() => void perform(async () => setNotes((await request<{ items: Note[] }>(taskPath() + "/memory/search", { query })).items))}>Search notes</button>
          <ul className="tool-list">{notes.map((note) => <li key={note.note_id}><p>{note.content}</p><button className="subtle-button" disabled={busy} onClick={() => void perform(async () => { await request(taskPath() + `/memory/${encodeURIComponent(note.note_id)}`, undefined, "DELETE"); setNotes((current) => current.filter((item) => item.note_id !== note.note_id)); })}>Delete note</button></li>)}</ul>
        </div>}
        {tab === "Alerts" && <div className="modal-form">
          <p>{monitorReady ? "Process monitoring is running." : "Enable process monitoring in server settings to create alerts."} Alerts do not execute actions.</p>
          <label htmlFor="alert-process">Exact process name</label><input id="alert-process" maxLength={200} value={process} onChange={(e) => setProcess(e.target.value)} />
          <label htmlFor="alert-event">Event</label><select id="alert-event" value={eventType} onChange={(e) => setEventType(e.target.value)}><option value="PROCESS_EXITED">Process exited</option><option value="PROCESS_STARTED">Process started</option></select>
          <button className="accent-button" disabled={busy || !monitorReady || !process.trim()} onClick={() => void perform(async () => { await request("/monitor/rules", { event_type: eventType, process_name: process, cooldown_seconds: 60 }); await refresh(); })}>Create alert</button>
          <ul className="tool-list">{rules.map((rule) => <li key={rule.rule_id}><span>{rule.process_name} · {rule.event_type}</span><button className="subtle-button" disabled={busy} onClick={() => void perform(async () => { await request(`/monitor/rules/${encodeURIComponent(rule.rule_id)}/state`, { enabled: !rule.enabled }); await refresh(); })}>{rule.enabled ? "Disable" : "Enable"}</button></li>)}</ul>
          <ul className="tool-list">{alerts.map((event) => <li key={event.event_id}><span>{event.payload?.process_name || "Process alert"} · {event.payload?.event_type}</span><small>{new Date(event.created_at).toLocaleString()}</small></li>)}</ul>
        </div>}
        {tab === "Review" && <>
          <p>Review labels cannot execute, qualify, or replay skills.</p>
          <button className="subtle-button" disabled={busy || !taskId} onClick={() => void perform(async () => setCandidate(await request<Candidate>(taskPath() + "/skill-candidate")))}>Load candidate</button>
          {candidate && <><pre className="tool-output">{JSON.stringify(candidate, null, 2)}</pre><div className="button-row">{(["retain", "reject"] as const).map((decision) => <button className="subtle-button" key={decision} disabled={busy || decision === "retain" && candidate.status !== "reviewable"} onClick={() => void perform(async () => setCandidate(await request<Candidate>(taskPath() + "/skill-candidate/review", { candidate_hash: candidate.candidate_hash, decision })))}>{decision === "retain" ? "Retain review" : "Reject review"}</button>)}</div></>}
        </>}
        {tab === "Routing" && <>
          <p>Check the available model tier against this task's shared budget. This check does not run a model.</p>
          <button className="subtle-button" disabled={busy || !taskId} onClick={() => void perform(async () => setRoute(await request(taskPath() + "/inference/route", { task_id: taskId, purpose: "Workspace assistant", complexity: 0.5 })))}>Check routing</button>
          {route && <p>{route.tier} · {route.reason}</p>}
        </>}
        {tab === "Audit" && <ul className="tool-list">{events.map((event) => <li key={event.event_id}><span>{event.event_type}</span><small>{new Date(event.created_at).toLocaleString()}</small></li>)}</ul>}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    </dialog>
  </>;
}
