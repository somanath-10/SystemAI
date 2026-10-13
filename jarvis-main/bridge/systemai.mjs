import { z } from 'zod'
import { tool, createToolServer } from './tools.mjs'
import { api } from './config.mjs'

const json = (body) => ({ method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
const result = (value) => ({ content: [{ type: 'text', text: JSON.stringify(value) }] })

const escape = (value) => String(value).replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]))

export function systemaiServer(emitTask, knownTasks, sessionId, emitBlade, contextId = sessionId) {
  const creationPath = (path) => `${path}?parent_task_id=${encodeURIComponent(sessionId())}`
  const ownedTask = (id = contextId()) => {
    if (!knownTasks.has(id)) throw new Error('task does not belong to this conversation or selected context')
    return encodeURIComponent(id)
  }
  const taskId = z.string().optional()
  const inspect = async (task) => {
    knownTasks.add(task.task_id)
    emitTask(task.task_id)
    return result(task)
  }
  return createToolServer({ name: 'systemai', tools: [
    tool('web_search', 'Search the live web with OpenAI and show the result with clickable sources.', { query: z.string().min(1).max(16_000) }, async ({ query }) => {
      const found = await (await api(`/tasks/${sessionId()}/assistant/tools/search`, json({ prompt: query, confirm_external: true }))).json()
      emitBlade({ id: `search-${Date.now()}`, title: 'WEB SEARCH', kind: 'markup', size: 'wide', hold: 'turn',
        html: `<p class="hud-note">${escape(found.text)}</p><div class="hud-rows">${found.sources.map((source) =>
          `<div class="hud-row"><a class="hud-label" href="${escape(source.url)}">${escape(source.title)}</a></div>`).join('')}</div>` })
      return result(found)
    }),
    tool('generate_image', 'Generate one PNG with the configured OpenAI image model and show it on a blade. Returns a disk path usable with ui_orbit.',
      { prompt: z.string().min(1).max(16_000) }, async ({ prompt }) => {
        const image = await (await api(`/tasks/${sessionId()}/assistant/tools/image`, json({ prompt, confirm_external: true }))).json()
        emitBlade({ id: image.artifact_id, title: 'GENERATED IMAGE', kind: 'image', url: image.path, size: 'wide', hold: 'sticky' })
        return result(image)
      }),
    tool('diagnose_project', 'Inspect a user-specified project and propose verified repairs. Approval is handled in Task Center.',
      { project_root: z.string(), goal: z.string().default('Find why this project is not running and fix it.') }, async (args) =>
        inspect(await (await api(creationPath('/tasks/developer-diagnosis'), json({ ...args, autonomy_mode: 'assist' }))).json())),
    tool('task_status', 'Read a task created in this conversation.', { task_id: z.string() }, async ({ task_id }) => {
      return result(await (await api(`/tasks/${ownedTask(task_id)}`)).json())
    }),
    tool('browser', 'Navigate, observe, click or fill within SystemAI allowed browser origins. The action must be requested by the user; approvals are handled in Task Center.',
      { capability: z.enum(['browser.navigate', 'browser.observe', 'browser.click', 'browser.fill', 'browser.download', 'browser.upload']), url: z.string(),
        selector: z.string().optional(), role: z.string().optional(), name: z.string().optional(), value: z.string().optional(), path: z.string().optional(),
        expected_url: z.string().optional(), expected_title: z.string().optional(), expected_text: z.string().optional() },
      async (args) => inspect(await (await api(creationPath('/tasks/browser'), json(args))).json())),
    tool('inspect_apps', 'Inspect running desktop applications through the configured SystemAI desktop driver.', {}, async () =>
      inspect(await (await api(creationPath('/tasks/desktop-observation'), { method: 'POST' })).json())),
    tool('desktop', 'Launch an allowed application or perform a requested desktop observation/click/input with verification. Approvals remain in Task Center.',
      { capability: z.enum(['application.launch', 'window.observe', 'ui.click', 'ui.set_value']), bundle_id: z.string(),
        window_title: z.string().optional(), element_name: z.string().optional(), element_role: z.string().optional(),
        value: z.string().optional(), verify_element_name: z.string().optional(), verify_window_title: z.string().optional() }, async (args) =>
        inspect(await (await api(creationPath('/tasks/desktop'), json(args))).json())),
    tool('cost_status', 'Read the shared conversation budget and model/connector usage.', { task_id: taskId }, async ({ task_id }) =>
      result(await (await api(`/tasks/${ownedTask(task_id)}/cost`)).json())),
    tool('task_control', 'Pause, stop, or take control of a task when the user asks. Resume and action approvals require Task Center.',
      { task_id: z.string(), control: z.enum(['pause', 'cancel', 'take-control']) }, async ({ task_id, control }) =>
        inspect(await (await api(`/tasks/${ownedTask(task_id)}/${control}`, { method: 'POST' })).json())),
    tool('memory_add', 'Save a local task note only when the user explicitly asks; never automatically capture secrets.',
      { task_id: taskId, content: z.string().min(1).max(4000) }, async ({ task_id, content }) =>
        result(await (await api(`/tasks/${ownedTask(task_id)}/memory`, json({ content }))).json())),
    tool('memory_search', 'Retrieve user-saved local notes for this task, using the configured local embedding model.',
      { task_id: taskId, query: z.string().min(1).max(4000) }, async ({ task_id, query }) =>
        result(await (await api(`/tasks/${ownedTask(task_id)}/memory/search`, json({ query }))).json())),
    tool('skill_preview', 'Read the non-executable skill candidate and current review. This cannot replay actions.', { task_id: z.string() }, async ({ task_id }) =>
      result(await (await api(`/tasks/${ownedTask(task_id)}/skill-candidate`)).json())),
    tool('monitor_status', 'Read process monitoring readiness and configured alert rules. Alerts never execute host actions.', {}, async () =>
      result({ status: await (await api('/monitor/status')).json(), rules: await (await api('/monitor/rules')).json() })),
    tool('monitor_rule', 'Create an exact-name process start/exit alert when requested. Requires process monitoring enabled in server settings.',
      { event_type: z.enum(['PROCESS_STARTED', 'PROCESS_EXITED']), process_name: z.string().min(1).max(200), cooldown_seconds: z.number().int().min(0).max(86400).default(60) },
      async (args) => result(await (await api('/monitor/rules', json(args))).json())),
  ] })
}
