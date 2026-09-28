import { useEffect, useMemo, useState } from "react";

type Step = {
  node_id: string;
  title: string;
  state: string;
  attempts: number;
  resources: string[];
  action: {
    action_id: string;
    capability: string;
    expected_result: string;
    risk_hint?: string | null;
  };
  verification?: { status: string; summary: string } | null;
};

type Goal = { objective: string };

type Task = {
  task_id: string;
  goal: Goal;
  project_root: string;
  state: string;
  error?: string | null;
  pending_approvals: Record<string, string>;
  diagnosis: { summary?: string; hypotheses?: Array<{ code: string; cause: string; confidence: number }> };
  steps: Step[];
};

type Approval = {
  approval_id: string;
  action_id: string;
  canonical_summary: string;
  reason: string;
};

const API = import.meta.env.VITE_SYSTEMAI_API ?? "http://127.0.0.1:8765";

export default function App() {
  const [projectRoot, setProjectRoot] = useState("");
  const [goal, setGoal] = useState("Find why this project is not running and fix it.");
  const [task, setTask] = useState<Task | null>(null);
  const [approval, setApproval] = useState<Approval | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const terminal = useMemo(() => !!task && ["completed", "failed", "cancelled"].includes(task.state), [task]);

  async function createTask() {
    setBusy(true);
    setError(null);
    setApproval(null);
    try {
      const response = await fetch(`${API}/tasks/developer-diagnosis`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project_root: projectRoot, goal, autonomy_mode: "standard_auto" }),
      });
      if (!response.ok) throw new Error(await response.text());
      setTask(await response.json());
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
    }
  }

  async function control(action: "pause" | "resume" | "take-control" | "cancel") {
    if (!task) return;
    try {
      const response = await fetch(`${API}/tasks/${task.task_id}/${action}`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      setTask(await response.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    if (!task) return;
    loadApproval(task).catch(() => setApproval(null));
  }, [task?.task_id, JSON.stringify(task?.pending_approvals ?? {})]);

  useEffect(() => {
    if (!task || terminal || task.state === "waiting_for_approval") return;
    const timer = window.setInterval(async () => {
      try {
        const response = await fetch(`${API}/tasks/${task.task_id}`);
        if (response.ok) setTask(await response.json());
      } catch {
        // Backend restarts are shown as stale state rather than breaking the UI.
      }
    }, 800);
    return () => window.clearInterval(timer);
  }, [task?.task_id, task?.state, terminal]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">Trusted local-first operating intelligence</div>
          <h1>SystemAI V1</h1>
        </div>
        <div className="status-stack">
          <span className="status"><i /> Local control plane</span>
          <span className="desktop-status ready">Developer diagnosis vertical</span>
        </div>
      </header>

      <section className="command panel">
        <label htmlFor="project">Project directory</label>
        <input id="project" className="project-input" value={projectRoot} onChange={(e) => setProjectRoot(e.target.value)} placeholder="/Users/me/Projects/my-app" />
        <label htmlFor="goal">Goal</label>
        <div className="composer">
          <textarea id="goal" value={goal} onChange={(e) => setGoal(e.target.value)} />
          <button onClick={createTask} disabled={busy || !goal.trim() || !projectRoot.trim()}>{busy ? "Inspecting…" : "Diagnose"}</button>
        </div>
        <p className="hint">V1 reads project/Git/process/port/config/package/log state locally, generates bounded typed actions, and pauses on canonical approval boundaries.</p>
      </section>

      {error && <div className="error">{error}</div>}

      <div className="grid">
        <section className="panel task-panel">
          <div className="section-head">
            <div>
              <span className="eyebrow">Current task</span>
              <h2>{task?.goal.objective ?? "No task running"}</h2>
              {task && <small>{task.project_root}</small>}
            </div>
            {task && <span className={`pill ${task.state}`}>{task.state}</span>}
          </div>

          {approval && (
            <div className="approval">
              <strong>Canonical approval required</strong>
              <pre>{approval.canonical_summary}</pre>
              <p>{approval.reason}</p>
              <div className="approval-actions">
                <button className="secondary" onClick={() => decide(false)}>Deny</button>
                <button onClick={() => decide(true)}>Approve exact action</button>
              </div>
            </div>
          )}

          {task && (
            <div className="task-controls">
              <button className="secondary" onClick={() => control("pause")}>Pause</button>
              {task.state === "paused" && <button className="secondary" onClick={() => control("resume")}>Resume</button>}
              <button className="secondary" onClick={() => control("take-control")}>Take control</button>
              <button className="secondary" onClick={() => control("cancel")}>Stop</button>
            </div>
          )}

          {task?.diagnosis?.summary && <div className="diagnosis"><b>Diagnosis:</b> {task.diagnosis.summary}</div>}

          <div className="steps">
            {(task?.steps ?? []).map((step, index) => (
              <article className="step" key={step.node_id}>
                <div className={`step-dot ${step.state}`}>{index + 1}</div>
                <div>
                  <strong>{step.title}</strong>
                  <span>{step.action.capability} · {step.action.risk_hint ?? "kernel decides risk"}</span>
                  <small>{step.verification?.summary ?? step.action.expected_result}</small>
                  {step.resources?.length > 0 && <small>Lease: {step.resources.join(", ")}</small>}
                </div>
              </article>
            ))}
            {!task && <div className="empty">Choose a project to see the diagnosis, validated DAG, approvals, execution, and verification trail.</div>}
          </div>
        </section>

        <aside className="panel architecture">
          <span className="eyebrow">V1 authority path</span>
          <h2>Execution chain</h2>
          {[
            "GoalContract",
            "Validated Task DAG",
            "Resource lease",
            "Typed ActionIntent",
            "Security Kernel",
            "Signed capability",
            "Trusted executor",
            "Fresh observation",
            "Independent verifier",
            "Event log / recovery",
          ].map((item, i) => <div className="arch-row" key={item}><b>{String(i + 1).padStart(2, "0")}</b>{item}</div>)}
          <div className="guard">The planner cannot lower canonical risk, self-approve, mint authority, or receive a general root/admin shell.</div>
        </aside>
      </div>
    </main>
  );
}
