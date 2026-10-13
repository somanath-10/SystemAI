import { fileURLToPath } from 'node:url'
import { resolve } from 'node:path'

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

export async function api(path, options = {}) {
  const response = await fetch(`${API}${path}`, { ...options, signal: options.signal || AbortSignal.timeout(60_000) })
  if (!response.ok) {
    let message = `SystemAI request failed (${response.status})`
    try { message = (await response.json()).detail || message } catch { /* bounded status message */ }
    throw new Error(message)
  }
  return response
}
