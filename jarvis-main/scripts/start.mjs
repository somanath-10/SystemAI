import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { ROOT, API } from '../bridge/config.mjs'
import './vendor.mjs'

if (process.argv.includes('--writes')) throw new Error('Direct-write bypass was removed; use signed SystemAI tasks and Task Center approvals')

const children = []
let stopping = false
function stop(code = 0) {
  if (stopping) return
  stopping = true
  for (const child of children) child.kill('SIGTERM')
  setTimeout(() => process.exit(code), 500)
}
function run(name, command, args, cwd, env = {}) {
  const child = spawn(command, args, { cwd, env: { ...process.env, ...env }, shell: false, stdio: ['ignore', 'pipe', 'pipe'] })
  children.push(child)
  child.stdout.on('data', (chunk) => process.stdout.write(`[${name}] ${chunk}`))
  child.stderr.on('data', (chunk) => process.stderr.write(`[${name}] ${chunk}`))
  child.on('error', (error) => { console.error(`[${name}] ${error.message}`); stop(1) })
  child.on('exit', (code) => { if (!stopping) stop(code || 1) })
}
process.on('SIGINT', () => stop())
process.on('SIGTERM', () => stop())
let runningApi = false
try {
  const response = await fetch(API + '/openapi.json', { signal: AbortSignal.timeout(1500) })
  const schema = await response.json()
  runningApi = Boolean(schema.paths?.['/assistant/sessions'])
  if (!runningApi) throw new Error('An older API is running on 8765; restart it before launching the workspace')
} catch (error) {
  if (error.message.includes('older API')) throw error
}
if (!runningApi) {
  const python = resolve(ROOT, '.venv/bin/python')
  if (!existsSync(python)) throw new Error('Install the Python project into .venv before starting: python3 -m venv .venv && .venv/bin/pip install -e .[dev,browser]')
  run('api', python, ['-m', 'systemai.api.run'], ROOT)
}
run('bridge', process.execPath, [resolve(ROOT, 'jarvis-main/bridge/server.mjs')], ROOT)
const ui = resolve(ROOT, 'apps/desktop/ui')
run('ui', process.execPath, [resolve(ui, 'node_modules/vite/bin/vite.js')], ui)
console.log('SystemAI workspace: http://127.0.0.1:5802 · Message, Task Center, or “Hey Jarvis”.')
