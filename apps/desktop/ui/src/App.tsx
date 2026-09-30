import { useEffect, useRef, useState } from "react";

type Step = {
  node_id: string;
  title: string;
  state: string;
  verification?: { status: string; summary: string } | null;
  result?: { output?: { apps?: Array<{ name: string; pid: number }> } } | null;
};

type Task = {
  task_id: string;
  goal: { objective: string };
  project_root: string;
  state: string;
  error?: string | null;
  pending_approvals: Record<string, string>;
  diagnosis: { summary?: string; hypotheses?: Array<{ cause: string }> };
  steps: Step[];
};

type Approval = { action_id: string; canonical_summary: string };
type DesktopStatus = { available: boolean; allowed_applications: string[] };
type BrowserStatus = { available: boolean; configured: boolean; allowed_origins: string[] };
type Mode = "project" | "browser" | "desktop";

const API = import.meta.env.VITE_SYSTEMAI_API ?? "http://127.0.0.1:8765";
const SATELLITES = Array.from({ length: 14 }, (_, index) => index);

export default function App() {
  const composer = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<Mode>("project");
  const [projectRoot, setProjectRoot] = useState("");
  const [goal, setGoal] = useState("Find why this project is not running and fix it.");
  const [browserUrl, setBrowserUrl] = useState("http://127.0.0.1:5802/");
  const [desktopApp, setDesktopApp] = useState("");
  const [desktopStatus, setDesktopStatus] = useState<DesktopStatus | null>(null);
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus | null>(null);
  const [task, setTask] = useState<Task | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [showActivity, setShowActivity] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const terminal = !!task && ["completed", "failed", "cancelled"].includes(task.state);
  const completedSteps = task?.steps.filter((step) => ["succeeded", "completed"].includes(step.state)).length ?? 0;
  const progress = task?.steps.length ? Math.round((completedSteps / task.steps.length) * 100) : 0;
  const stateLabel: Record<string, string> = {
    waiting_for_approval: "Needs approval",
    waiting_for_resource: "Waiting for resource",
    user_takeover: "In your control",
  };
  const taskLabel = task?.goal.objective.startsWith("browser.") ? "Browser" :
    task?.goal.objective.startsWith("Inspect running desktop") || task?.goal.objective.includes(" in com.") ? "Desktop" : "Project";
  const activitySummary = taskLabel === "Browser" ? "Browser session" : taskLabel === "Desktop" ? "Desktop action" : task?.goal.objective;

  function openComposer(nextMode: Mode = "project") {
    setMode(nextMode);
    setError(null);
    refreshStatus();
    composer.current?.showModal();
  }

  function refreshStatus() {
    fetch(`${API}/desktop/status`)
      .then((response) => response.ok ? response.json() : null)
      .then((status) => { setDesktopStatus(status); setDesktopApp(status?.allowed_applications?.[0] ?? ""); })
      .catch(() => setDesktopStatus(null));
    fetch(`${API}/browser/status`)
      .then((response) => response.ok ? response.json() : null)
      .then((status) => setBrowserStatus(status))
      .catch(() => setBrowserStatus(null));
  }

  async function submitTask(path: string, body?: object) {
    setBusy(true);
    setError(null);
    setApproval(null);
    try {
      const response = await fetch(`${API}/tasks/${path}`, {
        method: "POST",
        ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) throw new Error(await response.text());
      const next: Task = await response.json();
      setTask(next);
      setShowActivity(["waiting_for_approval", "failed"].includes(next.state));
      composer.current?.close();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function loadApproval(current: Task) {
    const ids = Object.values(current.pending_approvals || {});
    if (!ids.length) {
      setApproval(null);
      return;
    }
    const response = await fetch(`${API}/approvals/${ids[0]}`);
    if (response.ok) setApproval(await response.json());
  }

  async function decide(approved: boolean) {
    if (!task || !approval) return;
    setActionBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API}/tasks/${task.task_id}/approval`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action_id: approval.action_id, approved, reason: "Command Center decision" }),
      });
      if (!response.ok) throw new Error(await response.text());
      const next = await response.json();
      setTask(next);
      await loadApproval(next);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  }

  async function control(action: "pause" | "resume" | "cancel") {
    if (!task) return;
    setActionBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API}/tasks/${task.task_id}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      setTask(await response.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActionBusy(false);
    }
  }

  useEffect(() => {
    refreshStatus();
  }, []);

  useEffect(() => {
    if (!task) return;
    loadApproval(task).catch(() => setApproval(null));
  }, [task?.task_id, JSON.stringify(task?.pending_approvals ?? {})]);

  useEffect(() => {
    if (!task || terminal) return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/tasks/${task.task_id}`);
        if (response.ok) setTask(await response.json());
      } catch {
        // Keep the latest state visible while the local API restarts.
      }
    }, task.state === "waiting_for_approval" ? 2500 : 800);
    return () => window.clearInterval(timer);
  }, [task?.task_id, task?.state, terminal]);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="brand"><span className="brand-symbol" aria-hidden="true">✦</span><span>SystemAI</span></div>
        <span className="local-status"><span className="status-dot" />LOCAL</span>
      </header>

      <section className="scene" aria-label="SystemAI workspace">
        <div className="orbit-field">
          <div className="orb-aura" aria-hidden="true" />
          <div className="orbit-ring orbit-ring-one" aria-hidden="true" />
          <div className="orbit-ring orbit-ring-two" aria-hidden="true" />
          <div className="satellites" aria-hidden="true">
            {SATELLITES.map((index) => <span className="satellite-track" key={index}><span className="satellite" /></span>)}
          </div>
          <button className={`orb-core ${task && !terminal ? "is-active" : ""}`} onClick={() => openComposer()} aria-label="Start a new task">
            <span className="orb-surface" aria-hidden="true" />
            <span className="orb-glint" aria-hidden="true" />
            <span className="orb-heart" aria-hidden="true" />
          </button>
        </div>
        <div className="scene-actions">
          <span className="scene-state"><span className="status-dot" />{task ? stateLabel[task.state] ?? task.state.replaceAll("_", " ") : "Ready"}</span>
          <button className="launch-button" onClick={() => openComposer()}>New task <span aria-hidden="true">↗</span></button>
        </div>
      </section>

      {task && (
        <section className={`activity ${showActivity ? "expanded" : ""}`} aria-label="Current run">
          <button className="activity-toggle" onClick={() => setShowActivity(!showActivity)} aria-expanded={showActivity} aria-controls="activity-details">
            <span className={`activity-indicator ${task.state}`} />
            <span className="activity-summary"><strong>{taskLabel}</strong><small>{activitySummary}</small></span>
            <span className="activity-state">{stateLabel[task.state] ?? task.state.replaceAll("_", " ")}</span>
            <span className="activity-chevron" aria-hidden="true">⌃</span>
          </button>
          {showActivity && <div className="activity-body" id="activity-details">
            {task.steps.length > 0 && <div className="progress-track" role="progressbar" aria-label="Run progress" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${progress}%` }} /></div>}

            {approval && task.state === "waiting_for_approval" && <div className="approval">
              <strong>Review action</strong>
              <pre>{approval.canonical_summary}</pre>
              <div className="button-row">
                <button className="subtle-button" onClick={() => decide(false)} disabled={actionBusy}>Deny</button>
                <button className="accent-button" onClick={() => decide(true)} disabled={actionBusy}>{actionBusy ? "Working…" : "Approve"}</button>
              </div>
            </div>}

            {task.diagnosis?.hypotheses?.[0]?.cause && <p className="diagnosis">{task.diagnosis.hypotheses[0].cause}</p>}
            {task.goal.objective === "Inspect running desktop applications" && task.steps[0]?.result?.output?.apps && <div className="desktop-apps" aria-label="Running applications">
              {task.steps[0].result.output.apps.slice(0, 12).map((item) => <span key={item.pid}>{item.name}</span>)}
            </div>}
            {task.error && <p className="error" role="alert">{task.error}</p>}
            {error && <p className="error" role="alert">{error}</p>}

            <ol className="steps">
              {task.steps.map((step) => <li className={`step ${step.state}`} key={step.node_id}>
                <span className="step-mark" aria-hidden="true">{["succeeded", "completed"].includes(step.state) ? "✓" : "·"}</span>
                <span><strong>{step.title}</strong>{step.verification?.status === "failed" && <small>{step.verification.summary}</small>}</span>
                <em>{step.state.replaceAll("_", " ")}</em>
              </li>)}
            </ol>

            {!terminal && task.state !== "user_takeover" && <div className="button-row run-controls">
              {task.state === "paused" || task.state === "waiting_for_resource" ?
                <button className="subtle-button" onClick={() => control("resume")} disabled={actionBusy}>Resume</button> :
                task.state !== "waiting_for_approval" && <button className="subtle-button" onClick={() => control("pause")} disabled={actionBusy}>Pause</button>}
              <button className="subtle-button danger-button" onClick={() => control("cancel")} disabled={actionBusy}>Stop</button>
            </div>}
          </div>}
        </section>
      )}

      <dialog ref={composer} className="composer-dialog" aria-labelledby="composer-title" onClick={(event) => { if (event.target === event.currentTarget) composer.current?.close(); }}>
        <div className="dialog-panel">
          <div className="dialog-topline"><span className="dialog-kicker">SYSTEMAI</span><button className="dialog-close" onClick={() => composer.current?.close()} aria-label="Close dialog">×</button></div>
          <h1 id="composer-title">New task</h1>
          <div className="mode-tabs" role="group" aria-label="Task type">
            {(["project", "browser", "desktop"] as const).map((item) => <button key={item} aria-pressed={mode === item} className={mode === item ? "selected" : ""} onClick={() => { setMode(item); setError(null); }}>{item[0].toUpperCase() + item.slice(1)}</button>)}
          </div>

          {mode === "project" && <form className="modal-form" onSubmit={(event) => { event.preventDefault(); void submitTask("developer-diagnosis", { project_root: projectRoot, goal, autonomy_mode: "standard_auto" }); }}>
            <label htmlFor="project-root">Project directory</label>
            <input id="project-root" value={projectRoot} onChange={(event) => setProjectRoot(event.target.value)} placeholder="/path/to/project" autoComplete="off" required />
            <label htmlFor="goal">What should I do?</label>
            <textarea id="goal" value={goal} onChange={(event) => setGoal(event.target.value)} rows={3} required />
            <button className="accent-button form-submit" disabled={busy || !goal.trim() || !projectRoot.trim()}>{busy ? "Starting…" : "Diagnose project"}<span aria-hidden="true">↗</span></button>
          </form>}

          {mode === "browser" && <form className="modal-form" onSubmit={(event) => { event.preventDefault(); void submitTask("browser", { capability: "browser.navigate", url: browserUrl }); }}>
            <label htmlFor="browser-url">Page URL</label>
            <input id="browser-url" type="url" value={browserUrl} onChange={(event) => setBrowserUrl(event.target.value)} list="allowed-origins" required />
            <datalist id="allowed-origins">{browserStatus?.allowed_origins?.map((origin) => <option key={origin} value={`${origin}/`} />)}</datalist>
            {!browserStatus?.available && <p className="helper-text">Browser control is unavailable.</p>}
            <button className="accent-button form-submit" disabled={busy || !browserStatus?.available || !browserStatus?.configured}>{busy ? "Opening…" : "Open page"}<span aria-hidden="true">↗</span></button>
          </form>}

          {mode === "desktop" && <div className="modal-form">
            <label htmlFor="desktop-app">Allowed application</label>
            <select id="desktop-app" value={desktopApp} onChange={(event) => setDesktopApp(event.target.value)} disabled={!desktopStatus?.allowed_applications?.length}>
              {!desktopApp && <option value="">No applications configured</option>}
              {desktopStatus?.allowed_applications?.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
            {!desktopStatus?.available && <p className="helper-text">Desktop driver is not connected.</p>}
            <div className="button-row desktop-actions">
              <button className="subtle-button" onClick={() => submitTask("desktop-observation")} disabled={busy || !desktopStatus?.available}>Inspect apps</button>
              <button className="accent-button" onClick={() => submitTask("desktop", { capability: "application.launch", bundle_id: desktopApp })} disabled={busy || !desktopStatus?.available || !desktopApp}>{busy ? "Starting…" : "Launch app"}<span aria-hidden="true">↗</span></button>
            </div>
          </div>}

          {error && <p className="error" role="alert">{error}</p>}
        </div>
      </dialog>
    </main>
  );
}
