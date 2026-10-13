const read = (key: string) => { try { return sessionStorage.getItem(key) ?? ""; } catch { return ""; } };
const save = (key: string, value: string) => { try { sessionStorage.setItem(key, value); } catch { /* Storage is optional; live context still works. */ } };

export const selectedTaskId = () => read("systemai.selectedTask");
export const assistantSessionId = () => read("systemai.assistantSession");
export const assistantProvider = () => read("systemai.assistantProvider") || "auto";
export const setAssistantProvider = (provider: string) => save("systemai.assistantProvider", provider);

export function selectTask(task_id: string) {
  if (typeof task_id !== "string" || !/^task_[a-zA-Z0-9_-]{1,100}$/.test(task_id)) return;
  save("systemai.selectedTask", task_id);
  window.dispatchEvent(new CustomEvent("systemai-task", { detail: task_id }));
  if (window.parent !== window) window.parent.postMessage({ type: "systemai-task-selected", task_id }, location.origin);
}

export function setAssistantSession(task_id: string) {
  const previous = assistantSessionId();
  save("systemai.assistantSession", task_id);
  if (!selectedTaskId() || selectedTaskId() === previous) selectTask(task_id);
  window.dispatchEvent(new CustomEvent("systemai-session", { detail: task_id }));
}
