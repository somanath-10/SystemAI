import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { timingSafeEqual } from 'node:crypto'

export const ROOT = fileURLToPath(new URL('../../', import.meta.url))
try { process.loadEnvFile(resolve(ROOT, '.env')) } catch (error) {
  if (error.code !== 'ENOENT') throw error
}
export const API = process.env.SYSTEMAI_API_URL || 'http://127.0.0.1:8765'
const parsed = new URL(API)
if (parsed.protocol !== 'http:' || !['localhost', '127.0.0.1', '[::1]'].includes(parsed.hostname) ||
    parsed.username || parsed.password || parsed.pathname !== '/' || parsed.search || parsed.hash) {
  throw new Error('SYSTEMAI_API_URL must be a plain loopback HTTP origin')
}
export const MCP_CONFIG = resolve(ROOT, process.env.SYSTEMAI_MCP_CONFIG || 'config/mcp.json')
export function apiToken() {
  const directory = process.env.SYSTEMAI_DATA_DIR || resolve(homedir(), '.systemai/runtime')
  const token = process.env.SYSTEMAI_API_TOKEN || readFileSync(resolve(directory.startsWith('~/') ? resolve(homedir(), directory.slice(2)) : resolve(ROOT, directory), 'keys/local-api-token'), 'utf8').trim()
  if (token.length < 32 || !/^[!-~]+$/.test(token)) throw new Error('Invalid local API access key')
  return token
}
export function validAccessKey(value) {
  try {
    const token = Buffer.from(apiToken()), supplied = Buffer.from(value || '')
    return token.length === supplied.length && timingSafeEqual(token, supplied)
  } catch { return false }
}

const providerTimeout = Math.max(120, Math.min(600, Number(process.env.SYSTEMAI_OPENAI_TIMEOUT_SECONDS) || 60), Math.min(600, Number(process.env.SYSTEMAI_OLLAMA_TIMEOUT_SECONDS) || 60))
export const OPERATION_TIMEOUT_MS = providerTimeout * 2000 + 10_000

export async function api(path, options = {}) {
  const longOperation = /\/(?:inference\/(?:generate|openai)|assistant\/(?:response|stt|tts|tools\/(?:image|search))|approval|resume)$/.test(path.split('?')[0]) || /^\/tasks\/(?:developer-diagnosis|browser|desktop|desktop-observation)(?:\?|$)/.test(path)
  const headers = new Headers(options.headers)
  headers.set('authorization', `Bearer ${apiToken()}`)
  const response = await fetch(`${API}${path}`, { ...options, headers, signal: options.signal || AbortSignal.timeout(longOperation ? OPERATION_TIMEOUT_MS : 60_000) })
  if (!response.ok) {
    let message = `SystemAI request failed (${response.status})`
    try { message = (await response.json()).detail || message } catch { /* bounded status message */ }
    throw new Error(message)
  }
  return response
}
