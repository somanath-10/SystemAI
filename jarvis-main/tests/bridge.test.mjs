import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer, request as httpRequest } from 'node:http'
import { createServer as netServer } from 'node:net'
import { spawn } from 'node:child_process'
import { once } from 'node:events'
import { existsSync } from 'node:fs'
import { mkdtemp, rm, mkdir, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import WebSocket from 'ws'
import { readEvents, collectTools, toolOutput, untilInterrupted } from '../bridge/agent.mjs'
import { permittedTool } from '../bridge/policy.mjs'
import { uiServer } from '../bridge/ui.mjs'
import { displayServer } from '../bridge/panels.mjs'
import { chromeServer } from '../bridge/chrome.mjs'
import { proxySpeech, speechStatus } from '../bridge/speech.mjs'
import { systemaiServer } from '../bridge/systemai.mjs'
import { api as apiRequest, OPERATION_TIMEOUT_MS, ROOT } from '../bridge/config.mjs'

const accessToken = 'fixture-access-' + 'a'.repeat(64)
process.env.SYSTEMAI_API_TOKEN = accessToken

test('development server cannot serve runtime keys or private SQLite files', async () => {
  const directory = await mkdtemp(join(ROOT, '.access-test-'))
  const ui = join(ROOT, 'apps/desktop/ui')
  let vite
  try {
    await mkdir(join(directory, 'keys'))
    await writeFile(join(directory, 'keys/local-api-token'), 'b'.repeat(64), { mode: 0o600 })
    await writeFile(join(directory, 'systemai.sqlite3'), 'private fixture', { mode: 0o600 })
    const { createServer } = await import('../../apps/desktop/ui/node_modules/vite/dist/node/index.js')
    vite = await createServer({ root: ui, configFile: join(ui, 'vite.config.ts'), logLevel: 'silent',
      server: { host: '127.0.0.1', port: await freePort(), strictPort: true, preTransformRequests: false } })
    await vite.listen()
    const port = vite.httpServer.address().port
    for (const path of ['keys/local-api-token', 'systemai.sqlite3']) {
      const response = await fetch(`http://127.0.0.1:${port}/@fs${directory}/${path}`)
      assert.equal(response.status, 403)
      assert.ok(!(await response.text()).includes('private fixture'))
    }
    const frontend = await vite.ssrLoadModule('/src/api.ts')
    frontend.saveAccessKey(accessToken)
    frontend.saveMediaKey('b'.repeat(64))
    const config = await vite.ssrLoadModule('/@fs' + join(ROOT, 'jarvis-main/src/config.ts'))
    const media = config.bridgeMediaURL('/img?url=https%3A%2F%2Fexample.com%2Fimage.png')
    assert.equal(new URL(media).searchParams.get('media_token'), 'b'.repeat(64))
    assert.ok(!media.includes(accessToken))
    assert.equal(config.bridgeMediaURL('/authenticate'), 'data:,')
    await assert.rejects(async () => frontend.apiFetch('https://untrusted.example/'), /another origin/)
    const previousWindow = globalThis.window
    const transport = globalThis.fetch
    globalThis.window = new EventTarget()
    try {
      let updates = 0
      const unwatch = frontend.watchMediaKey(() => updates++)
      frontend.saveMediaKey('c'.repeat(64))
      frontend.saveMediaKey('c'.repeat(64))
      assert.equal(updates, 1)
      assert.equal(new URL(config.bridgeMediaURL('/file?path=fixture.png')).searchParams.get('media_token'), 'c'.repeat(64))
      unwatch()
      frontend.saveMediaKey('d'.repeat(64))
      assert.equal(updates, 1)
      let reloads = 0
      globalThis.window.top = { location: { reload: () => reloads++ } }
      globalThis.fetch = async () => {
        frontend.saveAccessKey(accessToken + '-new')
        return Response.json({ detail: 'Unauthorized' }, { status: 401 })
      }
      await frontend.apiFetch(frontend.API + '/tasks')
      assert.equal(reloads, 0, 'a late rejection must not revoke a newer access key')
      globalThis.fetch = async () => Response.json({ detail: 'Unauthorized' }, { status: 401 })
      await frontend.apiFetch(frontend.API + '/tasks')
      assert.equal(reloads, 1, 'a rejected current key relocks the top-level workspace')
      assert.equal(frontend.accessKey(), '')
      assert.equal(frontend.mediaKey(), '')
    } finally {
      globalThis.fetch = transport
      if (previousWindow === undefined) delete globalThis.window
      else globalThis.window = previousWindow
    }
  } finally { await vite?.close(); await rm(directory, { recursive: true, force: true }) }
})

test('API calls carry access keys and long operations outlast backend deadlines', async () => {
  const transport = globalThis.fetch, timeout = AbortSignal.timeout, deadlines = []
  AbortSignal.timeout = (milliseconds) => { deadlines.push(milliseconds); return timeout(50) }
  globalThis.fetch = async (url, options) => {
    assert.equal(options.headers.get('authorization'), `Bearer ${accessToken}`)
    if (String(url).endsWith('/assistant/tools/image')) await delay(25)
    if (options.signal.aborted) throw new Error('request aborted')
    return Response.json({ ok: true })
  }
  try {
    await apiRequest('/tasks/fixture/assistant/tools/image')
    await apiRequest('/tasks/fixture/inference/generate')
    await apiRequest('/assistant/sessions', { method: 'POST' })
    assert.deepEqual(deadlines, [OPERATION_TIMEOUT_MS, OPERATION_TIMEOUT_MS, 60_000])
    assert.ok(OPERATION_TIMEOUT_MS > 120_000)
    const signal = new AbortController().signal
    await apiRequest('/health', { signal })
    assert.equal(deadlines.length, 3)
  } finally { globalThis.fetch = transport; AbortSignal.timeout = timeout }
})

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
async function until(check) {
  for (let i = 0; i < 200; i++) { if (await check()) return; await delay(25) }
  throw new Error('fixture did not become ready')
}
async function freePort() {
  const server = netServer(); server.listen(0, '127.0.0.1'); await once(server, 'listening')
  const port = server.address().port; await new Promise((resolve) => server.close(resolve)); return port
}

test('SSE chunk boundaries and image tool results preserve the protocol', async () => {
  async function* chunks() { for (const chunk of ['data: {"type":"text","delta":"a"}\r', '\n\r\ndata: {"type":"done"}', '\n\n']) yield Buffer.from(chunk) }
  const seen = []
  for await (const event of readEvents(chunks())) seen.push(event)
  assert.deepEqual(seen, [{ type: 'text', delta: 'a' }, { type: 'done' }])
  assert.equal(toolOutput({ content: [{ type: 'image', mimeType: 'image/png', data: 'YWJj' }] })[0].type, 'input_image')
  assert.equal(toolOutput({ content: [{ type: 'image', mimeType: 'image/svg+xml', data: 'YWJj' }] }).length, 0)
})

test('ported UI tools retain validation and namespace isolation', async () => {
  const emitted = []
  const ui = uiServer((op, args) => emitted.push({ op, args }))
  await ui.tools.find((tool) => tool.name === 'ui_reactor').call({ scale: 999, spin: -1 })
  assert.deepEqual(emitted[0], { op: 'patch', args: { reactor: { scale: 3, spin: 0 } } })
  const displays = []
  const server = displayServer(() => {}, (blade) => displays.push(blade))
  assert.equal((await server.tools.find((tool) => tool.name === 'blade').call({ title: 'EMPTY', kind: 'image' })).isError, true)
  assert.equal(displays.length, 0)
  assert.equal(collectTools([{ name: 'x', tools: ui.tools }], () => false).size, 0)
})

test('external mutations cannot override the trusted action boundary', () => {
  for (const name of ['mcp__github__send_message', 'mcp__exa__create_index', 'mcp__openrouter__send-message', 'mcp__jarvis_chrome__chrome_click', 'mcp__jarvis_chrome__chrome_navigate', 'Bash']) assert.equal(permittedTool(name), false)
  for (const name of ['mcp__github__read_status', 'mcp__jarvis_chrome__chrome_screenshot', 'mcp__systemai__browser', 'mcp__jarvis_ui__ui_theme']) assert.equal(permittedTool(name), true)
})

test('interruption releases the turn while already-started work is tracked to completion', async () => {
  const controller = new AbortController()
  let finish, settled = false
  const work = new Promise((resolve) => { finish = resolve }).then(() => { settled = true; return 'finished' })
  const turn = untilInterrupted(work, controller.signal)
  controller.abort()
  await assert.rejects(turn, /interrupted/)
  assert.equal(settled, false)
  finish()
  assert.equal(await work, 'finished')
})

test('bridge streams a function loop and proxies STT/TTS only for connected sessions', async (t) => {
  let round = 0
  let connectorCalls = 0
  const modelInputs = []
  const usage = [], audit = []
  let sessions = 0, finishTask, finishAudit, browserInput, localPrompt, browserCalls = 0
  let holdSession = false, finishSession, statusReads = 0
  const api = createServer(async (req, res) => {
    const chunks = []; for await (const chunk of req) chunks.push(chunk)
    const body = Buffer.concat(chunks)
    res.setHeader('content-type', 'application/json')
    if (req.url === '/mcp') {
      if (req.method === 'GET' || req.method === 'DELETE') { res.writeHead(405); return res.end() }
      const rpc = JSON.parse(body)
      if (rpc.id === undefined) { res.writeHead(202); return res.end() }
      const results = {
        initialize: { protocolVersion: '2025-03-26', capabilities: { tools: {} }, serverInfo: { name: 'fixture', version: '1' } },
        'tools/list': { tools: [{ name: 'read_status', description: 'Read fixture status', inputSchema: { type: 'object', properties: {} } }] },
        'tools/call': { content: [{ type: 'text', text: 'Connector ready' }] },
      }
      if (rpc.method === 'tools/call') connectorCalls++
      return res.end(JSON.stringify({ jsonrpc: '2.0', id: rpc.id, result: results[rpc.method] }))
    }
    if (req.url === '/assistant/sessions') {
      sessions++
      if (holdSession) { finishSession = () => res.end('{"task_id":"task_closed"}'); return }
      return res.end(JSON.stringify({ task_id: 'task-fixture' }))
    }
    if (req.url.endsWith('/assistant/events')) {
      const event = JSON.parse(body); audit.push(event)
      if (event.turn_id === 'guarded' && event.event === 'AssistantToolStarted') { finishAudit = () => res.end('{"event_id":"event-fixture"}'); return }
      return res.end('{"event_id":"event-fixture"}')
    }
    if (req.url.endsWith('/assistant/external-usage')) { usage.push(JSON.parse(body)); return res.end('{"call_id":"model_0123456789abcdef"}') }
    if (req.url.endsWith('/inference/route')) return res.end(JSON.stringify(JSON.parse(body).force_tier === 'local_small' ? { tier: 'local_small', external: false } : { tier: 'standard_api', external: true }))
    if (req.url.endsWith('/inference/generate')) { localPrompt = JSON.parse(body).prompt; return res.end('{"text":"Local answer."}') }
    if (req.url.startsWith('/tasks/browser?')) {
      browserCalls++
      browserInput = { path: req.url, body: JSON.parse(body) }
      finishTask = () => res.end('{"task_id":"task_browser","state":"WAITING_FOR_APPROVAL"}')
      return
    }
    if (req.url === '/inference/status') { statusReads++; return res.end(JSON.stringify({ openai: { configured: true }, speech: { stt: true, tts: true, voice: 'cedar' } })) }
    if (req.url.endsWith('/assistant/tts')) { res.setHeader('content-type', 'audio/mpeg'); return res.end('ID3fixture') }
    if (req.url.endsWith('/assistant/stt')) return res.end(JSON.stringify({ text: 'hello' }))
    if (req.url.endsWith('/assistant/response')) {
      modelInputs.push(JSON.parse(body))
      res.setHeader('content-type', 'text/event-stream')
      if (['start browser', 'guarded start'].includes(modelInputs.at(-1).input.at(-1).content)) return res.end(`data: ${JSON.stringify({ type: 'response.completed', response: { output: [
        { type: 'function_call', call_id: 'browser', name: 'mcp__systemai__browser', arguments: JSON.stringify({ capability: 'browser.click', url: 'http://127.0.0.1:5802/', selector: 'button', expected_text: 'Done' }) },
      ] } })}\n\n`)
      if (modelInputs.at(-1).input.at(-1).content === 'slow') {
        res.write(': pending\n\n')
        const timer = setTimeout(() => res.end('data: {"type":"response.output_text.delta","delta":"STALE"}\n\n'), 500)
        res.on('close', () => clearTimeout(timer))
        return
      }
      const output = ++round === 1 ? [{ type: 'function_call', call_id: 'find', name: 'mcp__systemai__find_tools', arguments: '{"query":"fixture status"}' }] : round === 2 ? [
        { type: 'function_call', call_id: 'mcp', name: 'mcp__fixture__read_status', arguments: '{}' },
        { type: 'function_call', call_id: 'c1', name: 'mcp__jarvis_ui__ui_theme', arguments: '{"accent":"red"}' }] :
        [{ type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Ready.' }] }]
      if (round > 2) res.write('data: {"type":"response.output_text.delta","delta":"Ready."}\n\n')
      return res.end(`data: ${JSON.stringify({ type: 'response.completed', response: { output } })}\n\n`)
    }
    res.writeHead(404); res.end()
  })
  api.listen(0, '127.0.0.1'); await once(api, 'listening')
  const port = await freePort()
  const child = spawn(process.execPath, ['bridge/server.mjs'], { cwd: new URL('../', import.meta.url),
    env: { ...process.env, SYSTEMAI_API_URL: `http://127.0.0.1:${api.address().port}`, SYSTEMAI_BRIDGE_PORT: String(port),
      SYSTEMAI_MCP_CONFIG: 'jarvis-main/tests/fixtures/mcp.json', SYSTEMAI_TEST_MCP_URL: `http://127.0.0.1:${api.address().port}/mcp`,
      SYSTEMAI_SPEECH_PROVIDER: 'openai', SYSTEMAI_STT_PROVIDER: 'openai', SYSTEMAI_TTS_PROVIDER: 'openai' }, stdio: ['ignore', 'pipe', 'pipe'] })
  let logs = ''; child.stdout.on('data', (chunk) => { logs += chunk }); child.stderr.on('data', (chunk) => { logs += chunk })
  let socket
  t.after(async () => { socket?.close(); child.kill('SIGTERM'); if (child.exitCode === null) await once(child, 'exit'); await new Promise((resolve) => api.close(resolve)) })
  await until(() => logs.includes('bridge listening'))
  const base = `http://127.0.0.1:${port}`
  await t.test('bridge requires authentication before initializing sessions', async () => {
    assert.equal((await fetch(base + '/tts', { method: 'POST', headers: { origin: 'http://127.0.0.1:5802' }, body: '{}' })).status, 401)
    assert.equal((await fetch(base + '/file?path=/fixture.png')).status, 401)
    const before = sessions
    const bad = new WebSocket(`ws://127.0.0.1:${port}`, { origin: 'http://127.0.0.1:5802' })
    await once(bad, 'open'); bad.send(JSON.stringify({ type: 'authenticate', token: 'wrong' }))
    assert.equal((await once(bad, 'close'))[0], 1008)
    assert.equal(sessions, before)
    const authenticated = await fetch(base + '/authenticate', { method: 'POST', headers: { origin: 'http://127.0.0.1:5802', authorization: `Bearer ${accessToken}` } })
    assert.equal(authenticated.status, 200)
    const media = (await authenticated.json()).media_token
    const cookie = authenticated.headers.get('set-cookie').split(';')[0]
    assert.ok(!cookie.includes(accessToken))
    assert.equal((await fetch(base + '/file?path=/fixture.png', { headers: { cookie } })).status, 400)
    assert.equal((await fetch(base + `/file?path=/fixture.png&media_token=${media}`)).status, 400)
    assert.equal((await fetch(base + `/tts?media_token=${media}`, { method: 'POST', headers: { origin: 'http://127.0.0.1:5802' }, body: '{}' })).status, 401)
    const mediaSocket = new WebSocket(`ws://127.0.0.1:${port}`, { origin: 'http://127.0.0.1:5802' })
    await once(mediaSocket, 'open'); mediaSocket.send(JSON.stringify({ type: 'authenticate', token: media }))
    assert.equal((await once(mediaSocket, 'close'))[0], 1008)
    assert.equal((await fetch(base + '/tts', { method: 'POST', headers: { origin: 'http://127.0.0.1:5802', cookie }, body: '{}' })).status, 401)
  })
  await t.test('bridge refuses non-loopback Host headers', async () => {
    for (const host of ['attacker.example', `127.0.0.1:${port}/..`, `attacker.example@127.0.0.1:${port}`, `127.0.0.1:${port}?`, 'localhost']) {
      const status = await new Promise((resolve, reject) => {
        const req = httpRequest(base + '/health', { headers: { host } }, (res) => { res.resume(); resolve(res.statusCode) })
        req.on('error', reject); req.end()
      })
      assert.equal(status, 403, `invalid Host accepted: ${host}`)
    }
    assert.equal((await fetch(base + '/health')).status, 200)
    const badSocket = new WebSocket(`ws://127.0.0.1:${port}`, { origin: 'http://127.0.0.1:5802', headers: { host: 'attacker.example' } })
    const [error] = await once(badSocket, 'error'); assert.match(error.message, /403/)
  })
  const rejected = new WebSocket(`ws://127.0.0.1:${port}`, { origin: 'https://untrusted.example' })
  const [error] = await once(rejected, 'error'); assert.match(error.message, /403/)
  socket = new WebSocket(`ws://127.0.0.1:${port}`, { origin: 'http://127.0.0.1:5802' })
  const frames = []; socket.on('message', (raw) => frames.push(JSON.parse(raw)))
  await once(socket, 'open'); socket.send(JSON.stringify({ type: 'authenticate', token: accessToken })); await until(() => frames.some((frame) => frame.session_id))
  assert.match(frames.find((frame) => frame.type === 'authenticated').media_token, /^[0-9a-f]{64}$/)
  for (const value of ['null', '[]', '0', '"text"', '{}']) socket.send(value)
  socket.send(JSON.stringify({ type: 'ask', id: 'a1', text: 'make it red' }))
  await until(() => frames.some((frame) => frame.type === 'done'))
  assert.equal(frames.find((frame) => frame.type === 'ui').args.accent, 'red')
  assert.equal(frames.find((frame) => frame.type === 'text').ask, 'a1')
  assert.equal(modelInputs[1].input.at(-1).type, 'function_call_output')
  assert.equal(connectorCalls, 1)
  assert.deepEqual(usage.map((call) => call.phase), ['reserve', 'settle'])
  assert.ok(audit.some((event) => event.event === 'AssistantToolCompleted'))
  assert.ok(modelInputs[1].tools.some((tool) => tool.name === 'mcp__fixture__read_status'))
  assert.equal(modelInputs[0].confirm_external, true)
  assert.equal((await fetch(base + '/tts', { method: 'POST', body: '{}' })).status, 403)
  const headers = { authorization: `Bearer ${accessToken}`, origin: 'http://127.0.0.1:5802', 'content-type': 'application/json', 'x-systemai-session': 'task-fixture' }
  const audio = await fetch(base + '/tts', { method: 'POST', headers, body: '{"text":"hello"}' })
  assert.equal(await audio.text(), 'ID3fixture')
  headers['x-systemai-session'] = 'unknown'
  assert.equal((await fetch(base + '/tts', { method: 'POST', headers, body: '{"text":"hello"}' })).status, 403)
  socket.send(JSON.stringify({ type: 'ask', id: 'slow', text: 'slow' }))
  await until(() => modelInputs.at(-1).input.at(-1).content === 'slow')
  socket.send(JSON.stringify({ type: 'interrupt' }))
  socket.send(JSON.stringify({ type: 'ask', id: 'fresh', text: 'fresh answer' }))
  await until(() => frames.some((frame) => frame.type === 'done' && frame.ask === 'fresh'))
  await delay(550)
  assert.equal(frames.some((frame) => frame.delta === 'STALE'), false)
  assert.equal(child.exitCode, null)
  socket.send(JSON.stringify({ type: 'ask', id: 'local', text: 'offline answer', provider: 'local' }))
  await until(() => frames.some((frame) => frame.type === 'done' && frame.ask === 'local'))
  assert.match(localPrompt, /offline answer/)
  assert.match(localPrompt, /assistant: Ready\./)
  assert.equal(frames.find((frame) => frame.ask === 'local' && frame.type === 'text').delta, 'Local answer.')
  socket.send(JSON.stringify({ type: 'ask', id: 'browser', text: 'start browser' }))
  await until(() => Boolean(finishTask))
  socket.send(JSON.stringify({ type: 'interrupt' }))
  socket.send(JSON.stringify({ type: 'ask', id: 'after-task', text: 'another answer' }))
  await until(() => frames.some((frame) => frame.type === 'done' && frame.ask === 'after-task'))
  assert.equal(frames.some((frame) => frame.task_id === 'task_browser'), false)
  finishTask()
  await until(() => frames.some((frame) => frame.task_id === 'task_browser'))
  assert.equal(frames.find((frame) => frame.task_id === 'task_browser').interrupted, true)
  assert.match(browserInput.path, /parent_task_id=task-fixture/)
  assert.equal(browserInput.body.expected_text, 'Done')
  assert.equal(sessions, 1)
  socket.send(JSON.stringify({ type: 'ask', id: 'guarded', text: 'guarded start' }))
  await until(() => Boolean(finishAudit))
  socket.send(JSON.stringify({ type: 'interrupt' }))
  socket.send(JSON.stringify({ type: 'ask', id: 'after-guard', text: 'fresh guarded answer' }))
  let unblocked = true
  try { await until(() => frames.some((frame) => frame.type === 'done' && frame.ask === 'after-guard')) } catch { unblocked = false }
  finishAudit()
  await until(() => browserCalls > 1 || frames.some((frame) => frame.type === 'done' && frame.ask === 'after-guard'))
  if (browserCalls > 1) finishTask()
  await until(() => frames.some((frame) => frame.type === 'done' && frame.ask === 'after-guard'))
  assert.equal(unblocked, true, 'an interrupted audit preflight must release the next turn')
  assert.equal(browserCalls, 1, 'a tool whose preflight was interrupted must not start')
  await t.test('a closed connection cannot acquire speech access through late startup', async () => {
    holdSession = true
    const lateSocket = new WebSocket(`ws://127.0.0.1:${port}`, { origin: 'http://127.0.0.1:5802' })
    await once(lateSocket, 'open')
    lateSocket.send(JSON.stringify({ type: 'authenticate', token: accessToken }))
    await until(() => Boolean(finishSession))
    lateSocket.close(); await once(lateSocket, 'close')
    const before = statusReads
    finishSession()
    await until(() => statusReads > before)
    const speech = await fetch(base + '/tts', { method: 'POST', headers: { authorization: `Bearer ${accessToken}`, origin: 'http://127.0.0.1:5802', 'content-type': 'application/json', 'x-systemai-session': 'task_closed' }, body: '{"text":"hello"}' })
    assert.equal(speech.status, 403)
  })
})

test('speech validates text and meters optional ElevenLabs before sending audio', async () => {
  const names = ['SYSTEMAI_SPEECH_PROVIDER', 'SYSTEMAI_STT_PROVIDER', 'SYSTEMAI_TTS_PROVIDER', 'ELEVENLABS_API_KEY', 'SYSTEMAI_ELEVENLABS_TTS_MAX_CALL_COST_USD', 'SYSTEMAI_ELEVENLABS_STT_MAX_CALL_COST_USD']
  const saved = Object.fromEntries(names.map((name) => [name, process.env[name]])), transport = globalThis.fetch
  const calls = []
  async function invoke(url, body, type = 'application/json') {
    const req = { url, headers: { 'x-systemai-session': 'task_voice', 'content-type': type }, async *[Symbol.asyncIterator]() { yield Buffer.from(body) } }
    const res = { writeHead(status) { this.status = status }, end(data) { this.data = data } }
    await proxySpeech(req, res, {}, new Set(['task_voice']))
    return res
  }
  try {
    process.env.SYSTEMAI_SPEECH_PROVIDER = 'elevenlabs'; process.env.ELEVENLABS_API_KEY = 'fixture'
    delete process.env.SYSTEMAI_STT_PROVIDER; delete process.env.SYSTEMAI_TTS_PROVIDER
    process.env.SYSTEMAI_ELEVENLABS_TTS_MAX_CALL_COST_USD = '0'
    globalThis.fetch = async (url, options) => {
      const path = new URL(url).pathname
      calls.push(path.endsWith('/external-usage') ? JSON.parse(options.body).phase : 'provider')
      if (path.endsWith('/external-usage')) return Response.json({ call_id: 'model_fixture' })
      return path.endsWith('/speech-to-text') ? Response.json({ text: ' hello ' }) : new Response('ID3fixture')
    }
    assert.equal(speechStatus().tts, false)
    assert.equal((await invoke('/tts', '{"text":"hello"}')).status, 503)
    assert.equal(calls.length, 0)
    process.env.SYSTEMAI_ELEVENLABS_TTS_MAX_CALL_COST_USD = '0.01'; process.env.SYSTEMAI_ELEVENLABS_STT_MAX_CALL_COST_USD = '0.01'
    for (const body of ['null', '[]', '{}', '{"text":3}', '{"text":""}']) assert.equal((await invoke('/tts', body)).status, 400)
    assert.equal((await invoke('/tts', '{"text":"hello"}')).data.toString(), 'ID3fixture')
    assert.equal((await invoke('/stt', 'fixture audio', 'audio/webm')).data, '{"text":"hello"}')
    assert.deepEqual(calls, ['reserve', 'provider', 'settle', 'reserve', 'provider', 'settle'])
    assert.equal((await invoke('/stt', 'audio', 'text/html')).status, 503)
  } finally {
    globalThis.fetch = transport
    for (const name of names) { if (saved[name] === undefined) delete process.env[name]; else process.env[name] = saved[name] }
  }
})

test('task controls reject unknown model-selected tasks', async () => {
  const server = systemaiServer(() => {}, new Set(['task_owned']), () => 'task_owned', () => {})
  await assert.rejects(server.tools.find((tool) => tool.name === 'task_control').call({ task_id: 'task_other', control: 'cancel' }), /does not belong/)
  assert.throws(() => server.tools.find((tool) => tool.name === 'task_control').call({ task_id: 'task_owned', control: 'approve' }))
})

test('Chrome tools work against an isolated real Chrome debug profile', async (t) => {
  const binary = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
  if (!existsSync(binary)) return t.skip('Chrome is not installed')
  const port = await freePort()
  const directory = await mkdtemp(join(tmpdir(), 'systemai-cdp-'))
  const child = spawn(binary, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${directory}`, '--no-first-run', 'about:blank'], { stdio: 'ignore' })
  const page = createServer((req, res) => { if (req.url === '/redirect') { res.writeHead(302, { location: '/' }); return res.end() }
    res.setHeader('content-type', 'text/html'); res.end('<h1>Fixture page</h1><input aria-label="Name"><button onclick="document.querySelector(\'h1\').textContent=\'Clicked\'">Apply</button>') })
  page.listen(0, '127.0.0.1'); await once(page, 'listening')
  process.env.SYSTEMAI_CHROME_CDP_URL = `http://127.0.0.1:${port}`
  t.after(async () => { delete process.env.SYSTEMAI_CHROME_CDP_URL; child.kill('SIGTERM'); if (child.exitCode === null) await once(child, 'exit'); await new Promise((resolve) => page.close(resolve)); await rm(directory, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 }) })
  await until(async () => { try { return (await fetch(`http://127.0.0.1:${port}/json/list`)).ok } catch { return false } })
  assert.equal(chromeServer({ allowWrites: false }).tools.some((tool) => tool.name === 'chrome_click'), false)
  const shots = []
  const tools = chromeServer({ allowWrites: true, emitImage: (url) => shots.push(url) }).tools
  const call = (name, args = {}) => tools.find((tool) => tool.name === name).call(args)
  await call('chrome_navigate', { url: `http://127.0.0.1:${page.address().port}/redirect` })
  const snapshot = (await call('chrome_read_page', { filter: 'interactive' })).content[0].text
  const input = snapshot.split('\n').find((line) => line.includes('Name')).match(/\[([^\]]+)\]/)[1]
  const button = snapshot.split('\n').find((line) => line.includes('Apply')).match(/\[([^\]]+)\]/)[1]
  await call('chrome_form_input', { ref: input, value: 'Ada' })
  await call('chrome_click', { ref: input })
  await call('chrome_key', { text: 'ctrl+a' })
  await call('chrome_key', { text: 'Backspace' })
  await call('chrome_type', { text: 'Grace' })
  await call('chrome_click', { ref: button })
  assert.match((await call('chrome_page_text')).content[0].text, /Clicked/)
  assert.equal((await call('chrome_screenshot')).content[0].type, 'image')
  assert.ok(shots[0].startsWith('data:image/png;base64,'))
})
