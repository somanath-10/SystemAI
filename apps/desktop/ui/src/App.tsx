import { useEffect, useRef, useState } from "react";
import { assistantSessionId, selectedTaskId, selectTask } from "./taskContext";
import { TaskTools } from "./TaskTools";
import { API, apiFetch as fetch } from './api';

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
  parent_task_id?: string | null;
  state: string;
  error?: string | null;
  pending_approvals: Record<string, string>;
  diagnosis: { summary?: string; hypotheses?: Array<{ cause: string }> };
  steps: Step[];
};

type Approval = { action_id: string; canonical_summary: string };
type DesktopStatus = { available: boolean; allowed_applications: string[] };
type BrowserStatus = { available: boolean; configured: boolean; allowed_origins: string[] };
type Mode = "project" | "browser" | "desktop" | "ai";
type CostSummary = { budget: { max_external_cost_usd: number; max_external_calls: number; max_external_vision_calls: number }; totals: { local_calls: number; external_calls: number; external_cost_usd: number } };
type InferenceStatus = { connected: boolean; models: Record<string, boolean>; installed_models?: string[]; openai?: { configured: boolean; model: string | null } };

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
  const [inferenceStatus, setInferenceStatus] = useState<InferenceStatus | null>(null);
  const [cost, setCost] = useState<CostSummary | null>(null);
  const [prompt, setPrompt] = useState("");
  const [inferenceProvider, setInferenceProvider] = useState<"local" | "openai">("local");
  const [selectedLocalModel, setSelectedLocalModel] = useState("");
  const [inferenceImage, setInferenceImage] = useState<File | null>(null);
  const [answer, setAnswer] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [showActivity, setShowActivity] = useState(false);
  const [busy, setBusy] = useState(false);
  const [actionBusy, setActionBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const terminal = !!task && ["completed", "failed", "cancelled"].includes(task.state);
  const cloudReady = !!inferenceStatus?.openai?.configured && !!cost && cost.budget.max_external_calls > cost.totals.external_calls &&
    cost.budget.max_external_cost_usd > cost.totals.external_cost_usd && (!inferenceImage || cost.budget.max_external_vision_calls > 0);
  const completedSteps = task?.steps.filter((step) => ["succeeded", "completed"].includes(step.state)).length ?? 0;
  const progress = task?.steps.length ? Math.round((completedSteps / task.steps.length) * 100) : 0;
  const stateLabel: Record<string, string> = {
    waiting_for_approval: "Needs approval",
    waiting_for_resource: "Waiting for resource",
    user_takeover: "In your control",
  };
  const taskLabel = task?.goal.objective === "Voice assistant conversation" ? "Assistant" : task?.goal.objective.startsWith("browser.") ? "Browser" :
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
    fetch(`${API}/inference/status`)
      .then((response) => response.ok ? response.json() : null)
      .then(setInferenceStatus)
      .catch(() => setInferenceStatus(null));
  }

  async function refreshCost(taskId: string) {
    try {
      const response = await fetch(`${API}/tasks/${taskId}/cost`);
      if (response.ok) setCost(await response.json());
    } catch { setCost(null); }
  }

  async function generate() {
    if (!task) return;
    setBusy(true);
    setError(null);
    setAnswer("");
    try {
      if (inferenceImage && inferenceImage.size > 4_000_000) throw new Error("Image must be at most 4 MB.");
      const image_base64 = inferenceImage ? await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
        reader.onerror = () => reject(new Error("Image could not be read."));
        reader.readAsDataURL(inferenceImage);
      }) : undefined;
      const external = inferenceProvider === "openai";
      const response = await fetch(`${API}/tasks/${task.task_id}/inference/${external ? "openai" : "generate"}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt, image_base64, ...(external ? { confirm_external: true } : { model: selectedLocalModel || undefined }) }),
      });
      if (!response.ok) throw new Error(await response.text());
      setAnswer((await response.json()).text);
      await refreshCost(task.task_id);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }

  async function submitTask(path: string, body?: object) {
    setBusy(true);
    setError(null);
    setApproval(null);
    try {
      const parent = assistantSessionId();
      const response = await fetch(`${API}/tasks/${path}${parent ? `?parent_task_id=${encodeURIComponent(parent)}` : ""}`, {
        method: "POST",
        ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      });
      if (!response.ok) throw new Error(await response.text());
      const next: Task = await response.json();
      setTask(next);
      selectTask(next.task_id);
      setCost(null);
      setAnswer("");
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

  async function control(action: "pause" | "resume" | "cancel" | "take-control") {
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
    const taskId = new URLSearchParams(location.search).get("task_id") || selectedTaskId();
    if (taskId) {
      void fetch(`${API}/tasks/${encodeURIComponent(taskId)}`).then(async (response) => {
        if (!response.ok) throw new Error("Task could not be loaded.");
        setTask(await response.json());
        setShowActivity(true);
      }).catch((error: Error) => setError(error.message));
    }
  }, []);

  useEffect(() => {
    if (!task) return;
    loadApproval(task).catch(() => setApproval(null));
    void refreshCost(task.task_id);
    const timer = window.setInterval(() => void refreshCost(task.task_id), 3000);
    return () => window.clearInterval(timer);
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
          <button className="launch-button" onClick={() => openComposer()}>New task <span aria-hidden="true">↗</span></button>
          <TaskTools api={API} taskId={task?.task_id} onSelect={async (id) => {
            try {
              const response = await fetch(`${API}/tasks/${encodeURIComponent(id)}`);
              if (!response.ok) throw new Error("Task could not be loaded.");
              setTask(await response.json()); selectTask(id); setShowActivity(true);
            } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
          }} />
        </div>
      </section>

      {error && !task && !composer.current?.open && <p className="error" role="alert">{error}</p>}
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
            {cost && <p className="usage-line">Local calls {cost.totals.local_calls} · Cloud calls {cost.totals.external_calls} · Cloud spend ${cost.totals.external_cost_usd.toFixed(4)}</p>}

            <ol className="steps">
              {task.steps.map((step) => <li className={`step ${step.state}`} key={step.node_id}>
                <span className="step-mark" aria-hidden="true">{["succeeded", "completed"].includes(step.state) ? "✓" : "·"}</span>
                <span><strong>{step.title}</strong>{step.verification?.status === "failed" && <small>{step.verification.summary}</small>}</span>
                <em>{step.state.replaceAll("_", " ")}</em>
              </li>)}
            </ol>

            {!terminal && <div className="button-row run-controls">
              {task.state === "paused" || task.state === "waiting_for_resource" ?
                <button className="subtle-button" onClick={() => control("resume")} disabled={actionBusy}>Resume</button> :
                !["waiting_for_approval", "user_takeover"].includes(task.state) && <button className="subtle-button" onClick={() => control("pause")} disabled={actionBusy}>Pause</button>}
              <button className="subtle-button danger-button" onClick={() => control("cancel")} disabled={actionBusy}>Stop</button>
              {task.state !== "user_takeover" && <button className="subtle-button" onClick={() => control("take-control")} disabled={actionBusy}>Take control</button>}
            </div>}
          </div>}
        </section>
      )}

      <dialog ref={composer} className="composer-dialog" aria-labelledby="composer-title" onClick={(event) => { if (event.target === event.currentTarget) composer.current?.close(); }}>
        <div className="dialog-panel">
          <div className="dialog-topline"><span className="dialog-kicker">SYSTEMAI</span><button className="dialog-close" onClick={() => composer.current?.close()} aria-label="Close dialog">×</button></div>
          <h1 id="composer-title">New task</h1>
          <div className="mode-tabs" role="group" aria-label="Task type">
            {(["project", "browser", "desktop", "ai"] as const).map((item) => <button key={item} aria-pressed={mode === item} className={mode === item ? "selected" : ""} onClick={() => { setMode(item); setError(null); }}>{item === "ai" ? "AI" : item[0].toUpperCase() + item.slice(1)}</button>)}
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

          {mode === "ai" && <form className="modal-form" onSubmit={(event) => { event.preventDefault(); void generate(); }}>
            <div className="mode-tabs provider-tabs" role="group" aria-label="AI provider">
              <button type="button" aria-pressed={inferenceProvider === "local"} className={inferenceProvider === "local" ? "selected" : ""} onClick={() => setInferenceProvider("local")}>Local</button>
              <button type="button" aria-pressed={inferenceProvider === "openai"} className={inferenceProvider === "openai" ? "selected" : ""} onClick={() => setInferenceProvider("openai")}>OpenAI</button>
            </div>
            <label htmlFor="ai-prompt">Prompt</label>
            <textarea id="ai-prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} maxLength={16000} required />
            {inferenceProvider === "local" && <><label htmlFor="local-model">Model</label><select id="local-model" value={selectedLocalModel} onChange={(event) => setSelectedLocalModel(event.target.value)}>
              <option value="">Configured default</option>
              {inferenceStatus?.installed_models?.map((name) => <option key={name} value={name}>{name}</option>)}
            </select></>}
            <label htmlFor="ai-image">Image (optional)</label>
            <input id="ai-image" type="file" accept="image/png,image/jpeg,image/webp" onChange={(event) => setInferenceImage(event.target.files?.[0] ?? null)} />
            {!task && <p className="helper-text">Start a task first.</p>}
            {task && inferenceProvider === "local" && !selectedLocalModel && !inferenceStatus?.models?.[inferenceImage ? "local_vlm" : "local_llm"] && <p className="helper-text">Choose an installed model or configure a default.</p>}
            {task && inferenceProvider === "openai" && <p className="helper-text">{!inferenceStatus?.openai?.configured ? "OpenAI is not configured." : !cloudReady ? "No cloud budget remains for this task." : `Sends this prompt to OpenAI · task limit $${cost.budget.max_external_cost_usd.toFixed(2)}`}</p>}
            <button className="accent-button form-submit" disabled={busy || !task || !prompt.trim() || (inferenceProvider === "openai" ? !cloudReady : !selectedLocalModel && !inferenceStatus?.models?.[inferenceImage ? "local_vlm" : "local_llm"])}>{busy ? "Thinking…" : inferenceProvider === "openai" ? "Send to OpenAI" : "Generate"}<span aria-hidden="true">↗</span></button>
            {answer && <output className="ai-answer">{answer}</output>}
          </form>}

          {error && <p className="error" role="alert">{error}</p>}
        </div>
      </dialog>
    </main>
  );
}
