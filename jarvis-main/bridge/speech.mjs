import { api } from './config.mjs'
import { meteredExternal } from './usage.mjs'

export function speechProvider(kind) {
  return process.env[`SYSTEMAI_${kind.toUpperCase()}_PROVIDER`] || process.env.SYSTEMAI_SPEECH_PROVIDER || 'openai'
}

const ceiling = (provider, kind) => Number(process.env[`SYSTEMAI_${provider.toUpperCase()}_${kind.toUpperCase()}_MAX_CALL_COST_USD`] || 0)
const cartesiaVoice = () => process.env.CARTESIA_VOICE_ID || 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4'
const audioExtension = (type) => ({ 'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'mp4', 'audio/mpeg': 'mp3', 'audio/wav': 'wav', 'audio/x-wav': 'wav' })[type.split(';')[0].trim().toLowerCase()]

export function speechStatus(openai = {}) {
  const result = { stt_provider: speechProvider('stt'), tts_provider: speechProvider('tts'), provider: speechProvider('tts') }
  for (const kind of ['stt', 'tts']) {
    const provider = speechProvider(kind), fee = ceiling(provider, kind)
    const supported = ['elevenlabs', 'sarvam', kind === 'stt' ? 'deepgram' : 'cartesia'].includes(provider)
    result[kind] = provider === 'openai' ? Boolean(openai[kind]) : supported && Boolean(process.env[`${provider.toUpperCase()}_API_KEY`]) && fee > 0 && fee <= 10
    if (provider === 'cartesia' && !/^[0-9a-f-]{36}$/i.test(cartesiaVoice())) result[kind] = false
  }
  return result
}

async function externalSpeech(id, kind, body, type) {
  const provider = speechProvider(kind)
  if (!speechStatus()[kind]) throw new Error(`${provider} requires a server-side key and positive call-cost ceiling`)
  const ext = kind === 'stt' && audioExtension(type)
  if (kind === 'stt' && (!ext || !body.length)) throw new Error('Unsupported or empty speech audio')
  let url, payload, headers = { 'xi-api-key': process.env.ELEVENLABS_API_KEY }
  if (provider === 'deepgram') {
    url = new URL('https://api.deepgram.com/v1/listen')
    url.searchParams.set('model', process.env.DEEPGRAM_MODEL || 'nova-3')
    url.searchParams.set('smart_format', 'true')
    url.searchParams.set('language', process.env.DEEPGRAM_LANGUAGE || 'en')
    if (process.env.DEEPGRAM_DIARIZE === 'true') url.searchParams.set('diarize_model', 'latest')
    payload = body
    headers = { authorization: `Token ${process.env.DEEPGRAM_API_KEY}`, 'content-type': type }
  } else if (provider === 'cartesia') {
    url = 'https://api.cartesia.ai/tts/bytes'
    headers = { authorization: `Bearer ${process.env.CARTESIA_API_KEY}`, 'Cartesia-Version': '2026-08-14', 'content-type': 'application/json' }
    payload = JSON.stringify({ model_id: process.env.CARTESIA_MODEL || 'sonic-3.6', transcript: body, voice: cartesiaVoice(),
      language: process.env.CARTESIA_LANGUAGE || 'en', output_format: { container: 'wav', encoding: 'pcm_s16le', sample_rate: 24000 } })
  } else if (provider === 'sarvam') {
    headers = { 'api-subscription-key': process.env.SARVAM_API_KEY }
    url = `https://api.sarvam.ai/${kind === 'stt' ? 'speech-to-text' : 'text-to-speech'}`
    if (kind === 'stt') {
      payload = new FormData()
      payload.append('file', new Blob([body], { type }), `speech.${ext}`)
      payload.append('model', 'saaras:v4')
      payload.append('language_code', process.env.SARVAM_STT_LANGUAGE || 'unknown')
    } else {
      if (body.length > 2500) throw new Error('Sarvam speech text exceeds 2500 characters')
      headers['content-type'] = 'application/json'
      payload = JSON.stringify({ text: body, model: 'bulbul:v4-flash', language_code: process.env.SARVAM_TTS_LANGUAGE || 'en-IN',
        ...(process.env.SARVAM_SPEAKER ? { speaker: process.env.SARVAM_SPEAKER } : {}), output_audio_codec: 'wav', speech_sample_rate: 24000 })
    }
  } else if (kind === 'tts') {
    const voice = process.env.JARVIS_VOICE_ID || 'JBFqnCBsd6RMkjVDRZzb'
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(voice)) throw new Error('Invalid ElevenLabs voice ID')
    url = `https://api.elevenlabs.io/v1/text-to-speech/${voice}/stream?output_format=mp3_22050_32`
    payload = JSON.stringify({ text: body, model_id: 'eleven_flash_v2_5', voice_settings: { stability: 0.4, similarity_boost: 0.75, speed: 1.05 } })
    headers['content-type'] = 'application/json'
  } else {
    url = 'https://api.elevenlabs.io/v1/speech-to-text'
    payload = new FormData()
    payload.append('model_id', 'scribe_v1')
    payload.append('file', new Blob([body], { type }), `speech.${ext}`)
  }
  const estimate = ceiling(provider, kind) * (kind === 'tts' && provider !== 'elevenlabs' ? body.length / (provider === 'sarvam' ? 2500 : 4096) : 1)
  return meteredExternal(id, provider, kind, estimate, async () => {
    let upstream
    try { upstream = await fetch(url, { method: 'POST', headers, body: payload, signal: AbortSignal.timeout(60_000), redirect: 'error' }) }
    catch { throw new Error(`${provider} ${kind} connection failed; reserved cost retained`) }
    if (!upstream.ok) throw new Error(`${provider} ${kind} failed (${upstream.status}); reserved cost retained`)
    const chunks = []; let size = 0
    for await (const chunk of upstream.body) {
      size += chunk.length
      if (size > 10_000_000) throw new Error('Speech response is too large')
      chunks.push(chunk)
    }
    const data = Buffer.concat(chunks)
    if (kind === 'tts') {
      let audio = data
      if (provider === 'sarvam') {
        let audios
        try { audios = JSON.parse(data)?.audios } catch { throw new Error('Invalid Sarvam audio response') }
        if (!Array.isArray(audios) || audios.length !== 1 || typeof audios[0] !== 'string' || !/^[A-Za-z0-9+/]+={0,2}$/.test(audios[0])) throw new Error('Invalid Sarvam audio response')
        audio = Buffer.from(audios[0], 'base64')
      }
      if (!audio.length || (provider !== 'elevenlabs' && (audio.subarray(0, 4).toString() !== 'RIFF' || audio.subarray(8, 12).toString() !== 'WAVE'))) throw new Error('Invalid speech audio response')
      return audio
    }
    let result
    try { result = JSON.parse(data) } catch { throw new Error('Invalid speech transcript response') }
    const alternative = result?.results?.channels?.[0]?.alternatives?.[0]
    const text = provider === 'deepgram' ? alternative?.transcript : provider === 'sarvam' ? result?.transcript : result?.text
    if (typeof text !== 'string') throw new Error('Speech response has no transcript')
    return JSON.stringify({ text: text.trim(), ...(provider === 'deepgram' && Array.isArray(alternative.words) ? { words: alternative.words } : {}) })
  }, kind === 'tts' ? Math.min(600, body.length / 10) : 30)
}

export async function proxySpeech(req, res, cors, sessions) {
  const id = req.headers['x-systemai-session']
  if (typeof id !== 'string' || !sessions.has(id)) {
    res.writeHead(403, cors); res.end('voice session is not connected'); return
  }
  const chunks = []
  let size = 0
  const limit = req.url === '/stt' ? 2_000_000 : 16_000
  for await (const chunk of req) {
    size += chunk.length
    if (size > limit) { res.writeHead(413, cors); res.end('speech request is too large'); return }
    chunks.push(chunk)
  }
  let body = Buffer.concat(chunks)
  const headers = { 'content-type': req.headers['content-type'] || 'audio/webm' }
  if (req.url === '/tts') {
    let payload
    try { payload = JSON.parse(body) } catch { res.writeHead(400, cors); res.end('invalid speech text'); return }
    if (typeof payload?.text !== 'string' || !payload.text.trim() || payload.text.length > 4096) {
      res.writeHead(400, cors); res.end('speech text must contain 1–4096 characters'); return
    }
    body = JSON.stringify({ text: payload.text, confirm_external: true })
    headers['content-type'] = 'application/json'
  }
  try {
    const kind = req.url.slice(1), provider = speechProvider(kind)
    if (provider !== 'openai') {
      const result = await externalSpeech(id, kind, kind === 'tts' ? JSON.parse(body).text : body, headers['content-type'])
      res.writeHead(200, { ...cors, 'content-type': kind === 'tts' ? (provider === 'elevenlabs' ? 'audio/mpeg' : 'audio/wav') : 'application/json', 'cache-control': 'no-store' })
      res.end(result); return
    }
    const upstream = await api(`/tasks/${id}/assistant${req.url}`, { method: 'POST', headers, body })
    res.writeHead(200, { ...cors, 'content-type': upstream.headers.get('content-type'), 'cache-control': 'no-store' })
    for await (const chunk of upstream.body) {
      if (res.destroyed) break
      if (!res.write(chunk)) await new Promise((resolve) => res.once('drain', resolve))
    }
    res.end()
  } catch (error) {
    if (!res.headersSent) res.writeHead(503, cors)
    res.end(error.message)
  }
}
