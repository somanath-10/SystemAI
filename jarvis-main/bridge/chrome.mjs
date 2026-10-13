import WebSocket from 'ws'
import { randomUUID } from 'node:crypto'
import { z } from 'zod'
import { createToolServer, tool } from './tools.mjs'
import './config.mjs'

const connections = new Map()
const text = (value) => ({ content: [{ type: 'text', text: typeof value === 'string' ? value : JSON.stringify(value) }] })
function origin() {
  const endpoint = process.env.SYSTEMAI_CHROME_CDP_URL || ''
  if (!endpoint) throw new Error('Chrome CDP is not configured; use SystemAI browser tools or set SYSTEMAI_CHROME_CDP_URL')
  const url = new URL(endpoint)
  if (url.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
      url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('Chrome CDP must use a loopback HTTP origin')
  return url.origin
}
async function http(path, method = 'GET') {
  const response = await fetch(origin() + path, { method, signal: AbortSignal.timeout(5000) })
  if (!response.ok) throw new Error('Chrome CDP request failed')
  return response
}
const tabs = async () => (await (await http('/json/list')).json()).filter((tab) => tab.type === 'page')
function safeTab(tab) {
  let origin = ''
  try { origin = new URL(tab.url).origin } catch {}
  return { tabId: tab.id, origin }
}
async function connect(tab) {
  if (connections.has(tab.id)) return connections.get(tab.id)
  const wsUrl = new URL(tab.webSocketDebuggerUrl)
  if (wsUrl.protocol !== 'ws:' || !['localhost', '127.0.0.1', '[::1]'].includes(wsUrl.hostname)) throw new Error('Chrome returned a non-local socket')
  const socket = new WebSocket(wsUrl, { maxPayload: 16_000_000 })
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => { socket.close(); reject(new Error('Chrome socket timed out')) }, 5000)
    socket.once('open', () => { clearTimeout(timer); resolve() })
    socket.once('error', (error) => { clearTimeout(timer); reject(error) })
  })
  const waiting = new Map()
  const logs = [], network = new Map()
  let sequence = 0
  const call = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++sequence
    const timer = setTimeout(() => { waiting.delete(id); reject(new Error('Chrome command timed out')) }, 10_000)
    waiting.set(id, { resolve, reject, timer })
    socket.send(JSON.stringify({ id, method, params }), (error) => {
      if (error) { clearTimeout(timer); waiting.delete(id); reject(error) }
    })
  })
  socket.on('message', (raw) => {
    let frame
    try { frame = JSON.parse(raw.toString()) } catch { return }
    if (frame.id && waiting.has(frame.id)) {
      const pending = waiting.get(frame.id); waiting.delete(frame.id); clearTimeout(pending.timer)
      if (frame.error) pending.reject(new Error(frame.error.message)); else pending.resolve(frame.result || {})
    } else if (frame.method === 'Runtime.consoleAPICalled') {
      logs.push({ level: frame.params.type, text: frame.params.args.map((arg) => String(arg.value ?? arg.description ?? '')).join(' ').slice(0, 4000) })
      if (logs.length > 200) logs.shift()
    } else if (frame.method === 'Network.responseReceived') {
      const { requestId, response } = frame.params
      network.set(requestId, { requestId, url: response.url, status: response.status, mimeType: response.mimeType })
      if (network.size > 200) network.delete(network.keys().next().value)
    }
  })
  socket.on('close', () => {
    connections.delete(tab.id)
    for (const pending of waiting.values()) { clearTimeout(pending.timer); pending.reject(new Error('Chrome tab closed')) }
    waiting.clear()
  })
  const session = { call, logs, network }
  connections.set(tab.id, session)
  await Promise.all([call('Runtime.enable'), call('Page.enable'), call('Network.enable')])
  return session
}
async function evaluate(session, expression) {
  const result = await session.call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error('Browser operation failed; refresh the page observation')
  return result.result?.value
}

export function chromeServer({ allowWrites, emitImage = () => {} }) {
  let activeTab
  const target = async (id) => {
    const list = await tabs()
    const found = id ? list.find((tab) => tab.id === String(id)) : list.find((tab) => tab.id === activeTab) || list[0]
    if (!found) throw new Error('No Chrome tab is available')
    activeTab = found.id
    return { tab: found, session: await connect(found) }
  }
  const tabId = z.union([z.string(), z.number()]).optional()
  const read = async (args) => {
    const { session } = await target(args.tabId)
    const generation = randomUUID().slice(0, 8)
    const limit = Math.min(64_000, Math.max(1000, Number(args.max_chars) || 24_000))
    return evaluate(session, `(() => {
      const refs = new Map(); window.__systemai_refs = refs;
      const rows = []; let i = 0;
      for (const element of document.querySelectorAll('a,button,input,textarea,select,[role],h1,h2,h3,p,li')) {
        const rect = element.getBoundingClientRect(); if (!rect.width || !rect.height) continue;
        if (${JSON.stringify(args.filter === 'interactive')} && !element.matches('a,button,input,textarea,select,[role="button"],[role="textbox"]')) continue;
        const ref = ${JSON.stringify(generation)} + '_ref_' + (++i); refs.set(ref, element);
        const label = element.getAttribute('aria-label') || element.getAttribute('placeholder') || element.innerText || '';
        rows.push('['+ref+'] '+(element.getAttribute('role') || element.tagName.toLowerCase())+' '+label.trim().slice(0,300));
        if (i >= 400) break;
      }
      return rows.join('\\n').slice(0,${limit});
    })()`)
  }
  const tools = [
    tool('chrome_status', 'Check the explicitly configured Chrome debug connection.', {}, async () => text((await tabs()).map(safeTab))),
    tool('chrome_tabs', 'List reachable Chrome tabs and their origins.', { createIfEmpty: z.boolean().optional() }, async () => text((await tabs()).map(safeTab))),
    tool('chrome_navigate', 'Navigate an existing Chrome debug tab to a requested HTTP(S) page, back, or forward.', { url: z.string(), tabId }, async (args) => {
      const { session } = await target(args.tabId)
      const previous = await evaluate(session, 'location.href')
      let expected
      if (['back', 'forward'].includes(args.url)) {
        const history = await session.call('Page.getNavigationHistory')
        const index = history.currentIndex + (args.url === 'back' ? -1 : 1)
        if (!history.entries[index]) throw new Error('No history entry in that direction')
        expected = history.entries[index].url
        await session.call('Page.navigateToHistoryEntry', { entryId: history.entries[index].id })
      } else {
        const url = new URL(args.url)
        if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Browser navigation requires HTTP(S)')
        expected = url.href
        const result = await session.call('Page.navigate', { url: url.href })
        if (result.errorText) throw new Error(result.errorText)
      }
      for (let attempt = 0; attempt < 30; attempt++) {
        if (await evaluate(session, `document.readyState !== 'loading' && (location.href === ${JSON.stringify(expected)} || location.href !== ${JSON.stringify(previous)})`)) return text('Page ready.')
        await new Promise((resolve) => setTimeout(resolve, 100))
      }
      throw new Error('Page did not finish loading')
    }),
    tool('chrome_read_page', 'Read visible page text and interactive references before acting. Ref ids expire on the next observation.', { tabId, filter: z.enum(['all', 'interactive']).optional(), max_chars: z.number().optional() }, async (args) => text(await read(args))),
    tool('chrome_page_text', 'Read the visible page prose.', { tabId, max_chars: z.number().optional() }, async (args) => {
      const { session } = await target(args.tabId)
      return text(await evaluate(session, `document.body.innerText.slice(0,${Math.min(64_000, Math.max(1000, args.max_chars || 24_000))})`))
    }),
    tool('chrome_find', 'Find visible element references by words in their labels. Uses the page DOM, without a second model.', { query: z.string(), tabId }, async (args) => {
      const page = await read({ ...args, filter: 'interactive' })
      const terms = args.query.toLowerCase().split(/\s+/).filter(Boolean)
      return text(page.split('\n').filter((line) => terms.some((term) => line.toLowerCase().includes(term))).join('\n') || 'No matching visible element.')
    }),
    tool('chrome_screenshot', 'Capture the current tab and show it on a blade.', { tabId }, async (args) => {
      const { session } = await target(args.tabId)
      const shot = await session.call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
      emitImage('data:image/png;base64,' + shot.data)
      return { content: [{ type: 'image', data: shot.data, mimeType: 'image/png' }] }
    }),
    tool('chrome_scroll', 'Scroll the page in one direction.', { direction: z.enum(['up', 'down', 'left', 'right']), amount: z.number().optional(), tabId }, async (args) => {
      const { session } = await target(args.tabId)
      const amount = Math.min(3000, Math.max(1, args.amount || 3)) * 100
      await evaluate(session, `window.scrollBy(${args.direction === 'left' ? -amount : args.direction === 'right' ? amount : 0},${args.direction === 'up' ? -amount : args.direction === 'down' ? amount : 0})`)
      return text('Scrolled.')
    }),
    tool('chrome_console', 'Read console messages observed since connecting to the tab.', { tabId, onlyErrors: z.boolean().optional(), limit: z.number().optional() }, async (args) => {
      const { session } = await target(args.tabId)
      return text(session.logs.filter((line) => !args.onlyErrors || line.level === 'error').slice(-Math.min(200, Math.max(1, args.limit || 30))))
    }),
    tool('chrome_network', 'Read observed network response metadata, or a bounded response body by id.', { tabId, requestId: z.string().optional(), urlPattern: z.string().optional(), limit: z.number().optional() }, async (args) => {
      const { session } = await target(args.tabId)
      if (args.requestId) {
        if (!session.network.has(args.requestId)) throw new Error('Request id was not observed')
        const body = await session.call('Network.getResponseBody', { requestId: args.requestId })
        return text({ ...body, body: body.body.slice(0, 64_000) })
      }
      return text([...session.network.values()].filter((row) => !args.urlPattern || row.url.includes(args.urlPattern)).slice(-Math.min(200, Math.max(1, args.limit || 30))))
    }),
  ]
  if (allowWrites) tools.push(
    tool('chrome_click', 'Click a currently observed ref or an explicit coordinate.', { tabId, ref: z.string().optional(), coordinate: z.tuple([z.number(), z.number()]).optional() }, async (args) => {
      const { session } = await target(args.tabId)
      if (args.ref) await evaluate(session, `(() => { const e = window.__systemai_refs?.get(${JSON.stringify(args.ref)}); if (!e?.isConnected) throw Error('stale ref'); e.click(); return true })()`)
      else if (args.coordinate) for (const type of ['mousePressed', 'mouseReleased']) await session.call('Input.dispatchMouseEvent', { type, x: args.coordinate[0], y: args.coordinate[1], button: 'left', clickCount: 1 })
      else throw new Error('Click needs a ref or coordinate')
      return text('Clicked.')
    }),
    tool('chrome_type', 'Type into the focused field.', { text: z.string().max(16_000), tabId }, async (args) => {
      const { session } = await target(args.tabId); await session.call('Input.insertText', { text: args.text }); return text('Typed.')
    }),
    tool('chrome_key', 'Press a key or chord such as Return, Escape, Tab, cmd+a, ctrl+a.', { text: z.string().max(100), tabId }, async (args) => {
      const { session } = await target(args.tabId)
      const parts = args.text.toLowerCase().split('+'), name = parts.pop()
      const keys = { return: 'Enter', enter: 'Enter', escape: 'Escape', tab: 'Tab', backspace: 'Backspace', delete: 'Delete', arrowup: 'ArrowUp', arrowdown: 'ArrowDown', arrowleft: 'ArrowLeft', arrowright: 'ArrowRight' }
      const key = keys[name] || (name.length === 1 ? name : null)
      if (!key || parts.some((part) => !['cmd', 'meta', 'ctrl', 'control', 'alt', 'shift'].includes(part))) throw new Error('Unsupported key')
      const modifiers = parts.reduce((sum, part) => sum | ({ cmd: 4, meta: 4, ctrl: 2, control: 2, alt: 1, shift: 8 }[part]), 0)
      const codes = { Enter: 13, Escape: 27, Tab: 9, Backspace: 8, Delete: 46, ArrowUp: 38, ArrowDown: 40, ArrowLeft: 37, ArrowRight: 39 }
      const code = key.length === 1 ? `Key${key.toUpperCase()}` : key
      const virtualKey = codes[key] || key.toUpperCase().charCodeAt(0)
      for (const type of ['keyDown', 'keyUp']) await session.call('Input.dispatchKeyEvent', { type, key, code, modifiers,
        windowsVirtualKeyCode: virtualKey, nativeVirtualKeyCode: virtualKey })
      return text('Key pressed.')
    }),
    tool('chrome_form_input', 'Set an observed input/select/checkbox value, then dispatch input and change.', { ref: z.string(), value: z.union([z.string(), z.number(), z.boolean()]), tabId }, async (args) => {
      const { session } = await target(args.tabId)
      await evaluate(session, `(() => { const e=window.__systemai_refs?.get(${JSON.stringify(args.ref)}); if(!e?.isConnected || !e.matches('input,textarea,select')) throw Error('stale input');
        const value=${JSON.stringify(args.value)}; const property=e.type==='checkbox'?'checked':'value';
        const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(e),property)?.set;
        if(setter) setter.call(e,value); else e[property]=value;
        e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true})); return true })()`)
      return text('Input set.')
    }),
    tool('chrome_new_tab', 'Create a fresh tab for this browser workflow.', {}, async () => {
      const tab = await (await http('/json/new?about:blank', 'PUT')).json(); activeTab = tab.id; return text(safeTab(tab))
    }),
    tool('chrome_close_tab', 'Close an explicitly named tab.', { tabId: z.union([z.string(), z.number()]) }, async (args) => {
      await target(args.tabId); await http('/json/close/' + encodeURIComponent(args.tabId)); return text('Tab closed.')
    }),
  )
  return createToolServer({ name: 'jarvis_chrome', tools })
}
export async function chromeAvailable() {
  try { await tabs(); return true } catch { return false }
}
