import { createHash } from 'node:crypto'
import { displayServer } from './panels.mjs'
import { uiServer } from './ui.mjs'
import { visionServer } from './vision.mjs'
import { chromeServer } from './chrome.mjs'
import { systemaiServer } from './systemai.mjs'
import { connectMcp } from './mcp.mjs'
import { api } from './config.mjs'
import { tool as defineTool } from './tools.mjs'
import { z } from 'zod'

export function collectTools(servers, permitted) {
  const entries = new Map()
  for (const server of servers) for (const tool of server.tools) {
    const label = `mcp__${server.name}__${tool.name}`
    if (!permitted(label)) continue
    let name = label.replace(/[^a-zA-Z0-9_-]/g, '_')
    if (name.length > 64) name = `${name.slice(0, 43)}_${createHash('sha256').update(label).digest('hex').slice(0, 20)}`
    if (entries.has(name)) throw new Error('tool name collision')
    entries.set(name, { ...tool, label })
  }
  return entries
}

export async function* readEvents(body) {
  const decoder = new TextDecoder()
  let buffer = ''
  for await (const chunk of body) {
    buffer = (buffer + decoder.decode(chunk, { stream: true })).replace(/\r\n/g, '\n')
    if (buffer.length > 16_000_000) throw new Error('assistant event is too large')
    let end
    while ((end = buffer.indexOf('\n\n')) >= 0) {
      const frame = buffer.slice(0, end)
      buffer = buffer.slice(end + 2)
      const data = frame.split('\n').filter((line) => line.startsWith('data:')).map((line) => line.slice(5).trim()).join('\n')
      if (data && data !== '[DONE]') yield JSON.parse(data)
    }
  }
}

export function toolOutput(result) {
  const content = Array.isArray(result?.content) ? result.content : [{ type: 'text', text: JSON.stringify(result) }]
  return content.flatMap((part) => {
    if (part.type === 'text') return [{ type: 'input_text', text: String(part.text).slice(0, 64_000) }]
    if (part.type === 'image' && typeof part.data === 'string' && part.data.length < 6_000_000 &&
        ['image/png', 'image/jpeg', 'image/webp'].includes(part.mimeType)) {
      return [{ type: 'input_image', image_url: `data:${part.mimeType};base64,${part.data}` }]
    }
    return []
  })
}

export function untilInterrupted(work, signal) {
  return new Promise((resolve, reject) => {
    const abort = () => reject(new Error('turn interrupted'))
    if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true })
    Promise.resolve(work).then(resolve, reject).finally(() => signal.removeEventListener('abort', abort))
  })
}

export function attachAgent(socket, { instructions, permitted, onSession }) {
  const send = (frame) => { if (socket.readyState === socket.OPEN) socket.send(JSON.stringify(frame)) }
  const pending = new Map()
  const knownTasks = new Set()
  let sessionId = null
  let active = null
  let activeTurnId = null
  let queue = Promise.resolve()
  let history = []
  let seq = 0
  let generation = 0
  const liveServers = new Set(['SystemAI'])
  const external = connectMcp(() => sessionId).catch((error) => {
    send({ type: 'error', message: error.message })
    return { servers: [], close: async () => {} }
  })
  external.then(({ servers }) => { for (const server of servers) liveServers.add(server.name)
    send({ type: 'ready', servers: [...liveServers] }) })
    .catch(() => send({ type: 'error', message: 'The MCP configuration could not be loaded.' }))

  const session = async () => {
    const response = await api('/assistant/sessions', { method: 'POST' })
    sessionId = (await response.json()).task_id
    knownTasks.add(sessionId)
    onSession(sessionId)
    const status = await api('/inference/status', { signal: AbortSignal.timeout(3000) }).then((response) => response.json()).catch(() => ({}))
    if (status.openai?.configured) liveServers.add('OpenAI'); else liveServers.delete('OpenAI')
    if (status.models?.local_llm || status.models?.local_small) liveServers.add('Ollama')
    send({ type: 'ready', session_id: sessionId, servers: [...liveServers] })
  }
  let warming = session().catch(() => {})
  const audit = (event, turn_id, tool) => api(`/tasks/${sessionId}/assistant/events`, { method: 'POST',
    headers: { 'content-type': 'application/json' }, body: JSON.stringify({ event, turn_id, tool }) })

  const askBrowser = (kind, args, signal, timeout = 20_000) => new Promise((resolve, reject) => {
    if (signal.aborted) return reject(new Error('turn interrupted'))
    const id = `q${++seq}`
    const finish = (error, value) => {
      clearTimeout(timer)
      signal.removeEventListener('abort', abort)
      pending.delete(id)
      if (error) reject(error); else resolve(value)
    }
    const abort = () => finish(new Error('turn interrupted'))
    const timer = setTimeout(() => finish(new Error('the interface did not answer in time')), timeout)
    pending.set(id, { finish })
    signal.addEventListener('abort', abort, { once: true })
    send({ type: kind, id, ...args })
  })

  const run = async (message, requestedGeneration) => {
    if (requestedGeneration !== generation || socket.readyState !== socket.OPEN) return
    const controller = new AbortController()
    active = controller
    activeTurnId = message.id
    const signal = controller.signal
    const sendTurn = (frame) => { if (!signal.aborted) send({ ...frame, ask: message.id }) }
    let fullText = ''
    try {
      await untilInterrupted(warming, signal)
      if (requestedGeneration !== generation || signal.aborted) return
      if (!sessionId) {
        warming = session().catch(() => {})
        await untilInterrupted(warming, signal)
        if (!sessionId) throw new Error('SystemAI API is unavailable; start the local runtime and retry')
      }
      const contextId = message.context_task_id || sessionId
      if (!knownTasks.has(contextId)) {
        await untilInterrupted(api(`/tasks/${encodeURIComponent(contextId)}`), signal)
        knownTasks.add(contextId)
      }
      await untilInterrupted(audit('AssistantTurnStarted', message.id), signal)
      const status = await untilInterrupted(api('/inference/status').then((response) => response.json()), signal)
      const externalProvider = message.provider === 'openai' || (message.provider !== 'local' && status.openai?.configured)
      const route = await untilInterrupted(api(`/tasks/${sessionId}/inference/route`, { method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ task_id: sessionId, purpose: 'Assistant conversation', complexity: 0.5,
          force_tier: externalProvider ? 'standard_api' : message.provider === 'local' ? (status.models?.local_llm ? 'local_llm' : 'local_small') : undefined }) }).then((response) => response.json()), signal)
      if (signal.aborted) return
      if (!route.external) {
        if (!['local_llm', 'local_small'].includes(route.tier)) throw new Error('The selected tier cannot handle conversation')
        const context = history.flat().filter((item) => item.role).map((item) => {
          const text = typeof item.content === 'string' ? item.content : Array.isArray(item.content) ? item.content
            .filter((part) => ['input_text', 'output_text'].includes(part.type) && typeof part.text === 'string').map((part) => part.text).join('\n') : ''
          return text ? `${item.role}: ${text}` : ''
        }).filter(Boolean).join('\n')
        const response = await untilInterrupted(api(`/tasks/${sessionId}/inference/generate`, { method: 'POST', headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ prompt: `${context}\nuser: ${message.text}`.slice(-16_000), small: route.tier === 'local_small' }) }).then((response) => response.json()), signal)
        if (signal.aborted) return
        fullText = response.text
        history = [...history, [{ role: 'user', content: message.text }, { role: 'assistant', content: fullText }]].slice(-8)
        sendTurn({ type: 'text', delta: fullText })
        await untilInterrupted(audit('AssistantTurnCompleted', message.id), signal)
        sendTurn({ type: 'done', text: fullText })
        return
      }
      const mcp = await untilInterrupted(external, signal)
      const servers = [
        displayServer((panel) => sendTurn({ type: 'panel', panel }), (blade) => sendTurn({ type: 'blade', blade })),
        uiServer((op, args) => sendTurn({ type: 'ui', op, args })),
        visionServer((kind, args, timeout) => askBrowser(kind, args, signal, timeout)),
        chromeServer({ allowWrites: false, emitImage: (url) => sendTurn({ type: 'blade', blade: {
          id: `shot-${Date.now()}`, title: 'BROWSER', kind: 'image', url, size: 'wide', hold: 'turn',
        } }) }),
        systemaiServer((task_id) => send({ type: 'task', task_id, interrupted: signal.aborted }), knownTasks, () => sessionId,
          (blade) => sendTurn({ type: 'blade', blade }), () => contextId), ...mcp.servers,
      ]
      const tools = collectTools(servers, permitted)
      const visible = new Set([...tools].filter(([, tool]) => !mcp.servers.some((server) => tool.label.startsWith(`mcp__${server.name}__`))).map(([name]) => name))
      const finder = defineTool('find_tools', `Find configured MCP tools for a task. Available servers: ${mcp.servers.map((server) => server.name).join(', ') || 'none'}.`,
        { query: z.string().min(1).max(200) }, async ({ query }) => {
          const terms = query.toLowerCase().split(/\s+/)
          const matches = [...tools].filter(([name]) => name !== 'mcp__systemai__find_tools').map(([name, tool]) => ({ name, tool,
            score: terms.filter((term) => `${tool.label} ${tool.description}`.toLowerCase().includes(term)).length }))
            .filter((match) => match.score).sort((a, b) => b.score - a.score).slice(0, 8)
          for (const { name } of matches) visible.add(name)
          if (visible.size > 128) throw new Error('Too many tools selected; start a new turn')
          return { content: [{ type: 'text', text: JSON.stringify(matches.map(({ name, tool }) => ({ name, description: tool.description.slice(0, 500) }))) }] }
        })
      tools.set('mcp__systemai__find_tools', { ...finder, label: 'mcp__systemai__find_tools' })
      visible.add('mcp__systemai__find_tools')
      const turn = [{ role: 'user', content: message.text }]
      for (let round = 0; round < 12; round++) {
        if (signal.aborted) return
        const schemas = [...tools].filter(([name]) => visible.has(name)).map(([name, tool]) => ({ type: 'function', name,
          description: tool.description.slice(0, 24_000), parameters: tool.parameters, strict: false }))
        // Drain already-started paid requests in the background so their actual usage settles.
        const responseWork = api(`/tasks/${sessionId}/assistant/response`, { method: 'POST',
          headers: { 'content-type': 'application/json' }, body: JSON.stringify({ input: [...history.flat(), ...turn],
            instructions: `${instructions}\nConversation usage task: ${sessionId}. User-selected task: ${contextId}. Use that task for requested notes/status. Action approvals and resume belong in Task Center.`, tools: schemas, confirm_external: true }) }).then(async (response) => {
          let final
          for await (const event of readEvents(response.body)) {
            if (event.type === 'error') throw new Error(event.message || 'The assistant request failed.')
            if (event.type === 'response.output_text.delta' && !signal.aborted) { fullText += event.delta; sendTurn({ type: 'text', delta: event.delta }) }
            if (event.type === 'response.completed') final = event.response
          }
          return final
        })
        const final = await untilInterrupted(responseWork, signal)
        if (signal.aborted) return
        if (!final || !Array.isArray(final.output)) throw new Error('The assistant stream ended before completion.')
        const output = final.output.filter((item) => item.type !== 'reasoning' || item.encrypted_content)
        turn.push(...output)
        const calls = output.filter((item) => item.type === 'function_call')
        if (!calls.length) {
          history = [...history, turn].slice(-8)
          await untilInterrupted(audit('AssistantTurnCompleted', message.id), signal)
          sendTurn({ type: 'done', text: fullText })
          return
        }
        for (const call of calls) {
          if (signal.aborted) return
          const tool = tools.get(call.name)
          let result
          try {
            if (!tool) throw new Error('requested tool is unavailable')
            const args = JSON.parse(call.arguments)
            await untilInterrupted(audit('AssistantToolStarted', message.id, call.name), signal)
            if (signal.aborted) return
            if (!tool.label.startsWith('mcp__jarvis_ui__') && tool.label !== 'mcp__jarvis__display') sendTurn({ type: 'tool', name: tool.label })
            const work = Promise.resolve(tool.call(args, signal)).then(async (output) => {
              await audit(output?.isError ? 'AssistantToolFailed' : 'AssistantToolCompleted', message.id, call.name)
              return output
            }, async (error) => {
              await audit('AssistantToolFailed', message.id, call.name)
              throw error
            })
            result = await untilInterrupted(work, signal)
          } catch (error) { result = { isError: true, content: [{ type: 'text', text: `Tool failed: ${error.message}` }] } }
          if (signal.aborted) return
          turn.push({ type: 'function_call_output', call_id: call.call_id, output: toolOutput(result) })
        }
      }
      throw new Error('The assistant reached the tool-loop limit.')
    } catch (error) {
      if (!signal.aborted) sendTurn({ type: 'error', message: error.message || 'The assistant failed.' })
    } finally { if (active === controller) { active = null; activeTurnId = null } }
  }

  const interrupt = () => {
    if (!active || active.signal.aborted) return
    active.abort()
    void audit('AssistantTurnInterrupted', activeTurnId).catch(() => send({ type: 'error', message: 'The interruption could not be recorded.' }))
  }

  socket.on('message', (raw) => {
    let message
    try { message = JSON.parse(raw.toString()) } catch { return }
    if (!message || typeof message !== 'object' || Array.isArray(message)) return
    if (message.type === 'reply' && typeof message.id === 'string') pending.get(message.id)?.finish(null, message)
    if (message.type === 'interrupt') { generation++; interrupt() }
    if (message.type === 'ask' && typeof message.text === 'string' && message.text.trim() && message.text.length <= 16_000 && typeof message.id === 'string' && message.id.length > 0 && message.id.length <= 128 &&
        (message.provider === undefined || ['auto', 'local', 'openai'].includes(message.provider)) &&
        (message.context_task_id === undefined || typeof message.context_task_id === 'string' && /^task_[a-zA-Z0-9_-]{1,100}$/.test(message.context_task_id))) {
      interrupt()
      const currentGeneration = ++generation
      queue = queue.catch(() => {}).then(() => run(message, currentGeneration))
    }
  })
  socket.on('close', () => { interrupt(); for (const item of pending.values()) item.finish(new Error('interface closed'));
    external.then((mcp) => mcp.close()).catch(() => {}) })
}
