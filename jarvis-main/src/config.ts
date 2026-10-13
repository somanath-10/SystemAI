const setting = (value: unknown) => typeof value === 'string' ? value.trim() : ''
export const BRIDGE_WS_URL = setting(import.meta.env.VITE_BRIDGE_URL) || 'ws://127.0.0.1:8787'
export const BRIDGE_HTTP_URL = BRIDGE_WS_URL.replace(/^ws/, 'http')
export const TTS_ENGINE: 'system' | 'kokoro' = setting(import.meta.env.VITE_TTS_ENGINE) === 'kokoro' ? 'kokoro' : 'system'
export const KOKORO_VOICE = setting(import.meta.env.VITE_KOKORO_VOICE) || 'bm_george'
export const USE_CLOUD_TTS = ['1', 'true'].includes(setting(import.meta.env.VITE_USE_CLOUD_TTS))
