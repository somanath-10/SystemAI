import { useEffect, useRef, useState } from 'react'
import { warmBridge } from '../lib/bridge'
import { assistantProvider, selectTask, selectedTaskId, setAssistantProvider } from '../../../apps/desktop/ui/src/taskContext'

export function CommandDock({ onMessage }: { onMessage: (text: string) => Promise<void> }) {
  const chat = useRef<HTMLDialogElement>(null)
  const tasks = useRef<HTMLDialogElement>(null)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [taskId, setTaskId] = useState(selectedTaskId)
  const [tasksOpen, setTasksOpen] = useState(false)
  const frame = useRef<HTMLIFrameElement>(null)
  const [provider, setProvider] = useState(assistantProvider)
  useEffect(() => {
    const handler = (event: Event) => setTaskId(String((event as CustomEvent).detail))
    const message = (event: MessageEvent) => {
      if (event.origin === location.origin && event.source === frame.current?.contentWindow && event.data?.type === 'systemai-task-selected') selectTask(event.data.task_id)
    }
    void warmBridge().catch(() => {})
    window.addEventListener('systemai-task', handler)
    window.addEventListener('message', message)
    return () => { window.removeEventListener('systemai-task', handler); window.removeEventListener('message', message) }
  }, [])
  return <>
    <nav className="command-dock" aria-label="Workspace controls">
      <button onClick={() => chat.current?.showModal()}>Message</button>
      <button aria-label="Task Center" onClick={() => { setTasksOpen(true); tasks.current?.showModal() }}>Task Center{taskId && <span aria-hidden="true"> ·</span>}</button>
    </nav>
    <dialog ref={chat} className="command-dialog" aria-labelledby="message-title">
      <form onSubmit={(event) => { event.preventDefault(); if (!text.trim() || busy) return;
        const message = text.trim(); setText(''); setBusy(true); chat.current?.close();
        void onMessage(message).finally(() => setBusy(false)) }}>
        <header><h2 id="message-title">Message</h2><button type="button" onClick={() => chat.current?.close()} aria-label="Close message">×</button></header>
        <label>AI engine <select value={provider} onChange={(event) => { setProvider(event.target.value); setAssistantProvider(event.target.value) }}>
          <option value="auto">Auto</option><option value="local">Local text</option><option value="openai">OpenAI tools</option>
        </select></label>
        <textarea aria-label="Message" value={text} onChange={(event) => setText(event.target.value)} maxLength={16_000} autoFocus required />
        <button type="submit" disabled={busy || !text.trim()}>{busy ? 'Working…' : 'Send'}</button>
        <small><a href="/audio/CREDITS.md" target="_blank" rel="noopener noreferrer">Music credits</a> · <a href="/LICENSE.txt" target="_blank" rel="noopener noreferrer">UI license</a></small>
      </form>
    </dialog>
    <dialog ref={tasks} className="task-dialog" aria-label="Task Center">
      <button className="task-close" onClick={() => tasks.current?.close()} aria-label="Close Task Center">×</button>
      {tasksOpen && <iframe ref={frame} key={taskId} title="Task Center" src={`/?view=tasks${taskId ? `&task_id=${encodeURIComponent(taskId)}` : ''}`} />}
    </dialog>
  </>
}
