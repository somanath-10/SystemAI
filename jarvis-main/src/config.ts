import { mediaKey } from '../../apps/desktop/ui/src/api'

const setting = (value: unknown) => typeof value === 'string' ? value.trim() : ''
export const BRIDGE_WS_URL = setting(import.meta.env.VITE_BRIDGE_URL) || 'ws://127.0.0.1:8787'
const bridge = new URL(BRIDGE_WS_URL)
if (bridge.protocol !== 'ws:' || !['127.0.0.1', 'localhost', '[::1]'].includes(bridge.hostname) || bridge.username || bridge.password || bridge.pathname !== '/' || bridge.search || bridge.hash) throw new Error('Bridge must be a plain loopback WebSocket origin')
export const BRIDGE_HTTP_URL = BRIDGE_WS_URL.replace(/^ws/, 'http')
export function bridgeMediaURL(value: string) {
  const url = new URL(value, BRIDGE_HTTP_URL)
  if (url.origin !== new URL(BRIDGE_HTTP_URL).origin || !['/img', '/file', '/media', '/page'].includes(url.pathname)) return 'data:,'
  url.searchParams.set('media_token', mediaKey())
  return url.href
}
export const TTS_ENGINE: 'system' | 'kokoro' = setting(import.meta.env.VITE_TTS_ENGINE) === 'kokoro' ? 'kokoro' : 'system'
export const KOKORO_VOICE = setting(import.meta.env.VITE_KOKORO_VOICE) || 'bm_george'
export const USE_CLOUD_TTS = ['1', 'true'].includes(setting(import.meta.env.VITE_USE_CLOUD_TTS))
