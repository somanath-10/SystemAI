import { BRIDGE_HTTP_URL } from '../config'

export type SpeechProvider = 'openai' | 'elevenlabs' | 'deepgram' | 'cartesia' | 'sarvam'
export type Capabilities = { stt: boolean; tts: boolean; provider: SpeechProvider; stt_provider: SpeechProvider; voice?: string }
const defaults: Capabilities = { stt: false, tts: false, provider: 'openai', stt_provider: 'openai' }
let current: Capabilities = { ...defaults }
const provider = (name: unknown): SpeechProvider => ['openai', 'elevenlabs', 'deepgram', 'cartesia', 'sarvam'].includes(String(name)) ? name as SpeechProvider : 'openai'
export const speechProviderLabel = (name: SpeechProvider) => ({ openai: 'OpenAI', elevenlabs: 'ElevenLabs', deepgram: 'Deepgram', cartesia: 'Cartesia', sarvam: 'Sarvam' })[name]
let probed = false
export const caps = () => current
export const capabilitiesProbed = () => probed

export async function probeCapabilities(): Promise<Capabilities> {
  current = { ...defaults }
  try {
    const response = await fetch(`${BRIDGE_HTTP_URL}/health`, { signal: AbortSignal.timeout(3000) })
    if (response.ok) {
      const health = await response.json()
      current = { stt: Boolean(health.stt), tts: Boolean(health.tts),
        provider: provider(health.tts_provider || health.provider), stt_provider: provider(health.stt_provider || health.provider), voice: health.voice }
    }
  } catch { current = { ...defaults } }
  probed = true
  return current
}
export function engineLabel() {
  if (!current.stt && !current.tts) return 'browser speech'
  return `${current.stt ? speechProviderLabel(current.stt_provider) : 'browser'} → ${current.tts ? speechProviderLabel(current.provider) : 'browser'}`
}
