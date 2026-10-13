import test from 'node:test'
import assert from 'node:assert/strict'
import { proxySpeech, speechStatus } from '../bridge/speech.mjs'

const wav = Buffer.from('RIFF1234WAVEaudio')
async function invoke(kind, body = kind === 'tts' ? '{"text":"hello"}' : 'audio', type = kind === 'tts' ? 'application/json' : 'audio/webm;codecs=opus', connected = true) {
  const req = { url: `/${kind}`, headers: { 'x-systemai-session': 'task_voice', 'content-type': type },
    async *[Symbol.asyncIterator]() { yield Buffer.from(body) } }
  const res = { writeHead(status, headers) { this.status = status; this.headers = headers }, end(data) { this.data = data } }
  await proxySpeech(req, res, {}, new Set(connected ? ['task_voice'] : []))
  return res
}

test('mixed speech providers use server keys, bounded audio and shared reservations', async (t) => {
  const values = { SYSTEMAI_STT_PROVIDER: 'deepgram', SYSTEMAI_TTS_PROVIDER: 'cartesia', DEEPGRAM_API_KEY: 'test-deepgram',
    CARTESIA_API_KEY: 'test-cartesia', SARVAM_API_KEY: 'test-sarvam', DEEPGRAM_DIARIZE: 'true', DEEPGRAM_MODEL: 'nova-3',
    DEEPGRAM_LANGUAGE: 'en', CARTESIA_MODEL: 'sonic-3.6', CARTESIA_LANGUAGE: 'en',
    CARTESIA_VOICE_ID: 'db6b0ed5-d5d3-463d-ae85-518a07d3c2b4', SARVAM_STT_LANGUAGE: 'unknown', SARVAM_TTS_LANGUAGE: 'en-IN', SARVAM_SPEAKER: '',
    SYSTEMAI_DEEPGRAM_STT_MAX_CALL_COST_USD: '0.01', SYSTEMAI_CARTESIA_TTS_MAX_CALL_COST_USD: '0.30',
    SYSTEMAI_SARVAM_STT_MAX_CALL_COST_USD: '0.01', SYSTEMAI_SARVAM_TTS_MAX_CALL_COST_USD: '0.15' }
  const saved = Object.fromEntries(Object.keys(values).map((key) => [key, process.env[key]])), transport = globalThis.fetch
  Object.assign(process.env, values)
  let calls = [], failure = '', malformed = false
  globalThis.fetch = async (url, options) => {
    const parsed = new URL(url)
    if (parsed.pathname.endsWith('/external-usage')) {
      const details = JSON.parse(options.body)
      calls.push(details)
      if (failure === 'budget') return Response.json({ detail: 'budget exceeded' }, { status: 409 })
      return Response.json({ call_id: 'model_fixture' })
    }
    calls.push({ url: parsed, options })
    assert.equal(options.redirect, 'error')
    assert.ok(options.signal)
    if (failure === 'provider') return new Response('private provider error', { status: 401 })
    if (failure === 'transport') throw new Error('test-deepgram must not leak')
    if (malformed) return new Response('private malformed response')
    if (parsed.hostname === 'api.deepgram.com') return Response.json({ results: { channels: [{ alternatives: [{ transcript: ' hello ', words: [{ word: 'hello', speaker: 0, start: 0, end: 1 }] }] }] } })
    if (parsed.hostname === 'api.cartesia.ai') return new Response(wav)
    if (parsed.pathname === '/speech-to-text') return Response.json({ transcript: ' नमस्ते ' })
    return Response.json({ audios: [wav.toString('base64')] })
  }
  try {
    await t.test('Deepgram diarization preserves speaker words without polluting command text', async () => {
      assert.deepEqual(speechStatus(), { stt: true, tts: true, provider: 'cartesia', stt_provider: 'deepgram', tts_provider: 'cartesia' })
      const response = await invoke('stt')
      assert.equal(response.status, 200)
      assert.deepEqual(JSON.parse(response.data), { text: 'hello', words: [{ word: 'hello', speaker: 0, start: 0, end: 1 }] })
      assert.deepEqual(calls.map((call) => call.phase || 'provider'), ['reserve', 'provider', 'settle'])
      assert.equal(calls[0].provider, 'deepgram')
      assert.equal(calls[1].options.headers.authorization, 'Token test-deepgram')
      assert.equal(calls[1].url.searchParams.get('diarize_model'), 'latest')
      assert.equal(calls[1].options.body.toString(), 'audio')
      calls = []; process.env.DEEPGRAM_DIARIZE = 'false'
      await invoke('stt')
      assert.equal(calls[1].url.searchParams.has('diarize_model'), false)
    })
    await t.test('Cartesia produces WAV with proportional conservative reservation', async () => {
      calls = []
      const response = await invoke('tts')
      assert.equal(response.status, 200)
      assert.equal(response.headers['content-type'], 'audio/wav')
      assert.deepEqual(response.data, wav)
      assert.equal(calls[0].provider, 'cartesia')
      assert.equal(calls[0].estimated_cost_usd, 0.30 * 5 / 4096)
      assert.equal(calls[1].options.headers.authorization, 'Bearer test-cartesia')
      assert.equal(calls[1].options.headers['Cartesia-Version'], '2026-08-14')
      const body = JSON.parse(calls[1].options.body)
      assert.equal(body.transcript, 'hello'); assert.equal(body.model_id, 'sonic-3.6')
      assert.equal(body.output_format.container, 'wav')
    })
    await t.test('Sarvam transcribes multipart audio and decodes its WAV response', async () => {
      process.env.SYSTEMAI_STT_PROVIDER = 'sarvam'; process.env.SYSTEMAI_TTS_PROVIDER = 'sarvam'
      calls = []
      assert.equal(JSON.parse((await invoke('stt')).data).text, 'नमस्ते')
      assert.equal(calls[1].options.headers['api-subscription-key'], 'test-sarvam')
      assert.equal(calls[1].options.body.get('model'), 'saaras:v4')
      assert.equal(calls[1].options.body.get('file').name, 'speech.webm')
      assert.deepEqual((await invoke('tts')).data, wav)
      assert.equal(JSON.parse(calls[4].options.body).model, 'bulbul:v4-flash')
      calls = []
      assert.equal((await invoke('tts', JSON.stringify({ text: 'x'.repeat(2501) }))).status, 503)
      assert.equal(calls.length, 0)
    })
    await t.test('invalid sessions, inputs, providers and missing ceilings never make paid requests', async () => {
      calls = []
      assert.equal((await invoke('stt', 'audio', 'audio/webm', false)).status, 403)
      assert.equal((await invoke('stt', '')).status, 503)
      assert.equal((await invoke('stt', 'audio', 'text/html')).status, 503)
      assert.equal((await invoke('stt', 'x'.repeat(2_000_001))).status, 413)
      process.env.SYSTEMAI_TTS_PROVIDER = 'deepgram'
      assert.equal(speechStatus().tts, false)
      assert.equal((await invoke('tts')).status, 503)
      process.env.SYSTEMAI_TTS_PROVIDER = 'cartesia'; process.env.SYSTEMAI_CARTESIA_TTS_MAX_CALL_COST_USD = '0'
      assert.equal((await invoke('tts')).status, 503)
      assert.equal(calls.length, 0)
      process.env.SYSTEMAI_CARTESIA_TTS_MAX_CALL_COST_USD = '0.30'
    })
    await t.test('budget rejection prevents dispatch; provider failure retains reservation and hides raw errors', async () => {
      process.env.SYSTEMAI_STT_PROVIDER = 'deepgram'
      for (const scenario of ['budget', 'provider', 'transport']) {
        calls = []; failure = scenario
        const response = await invoke('stt')
        assert.equal(response.status, 503)
        assert.equal(calls.length, scenario === 'budget' ? 1 : 2)
        assert.ok(!String(response.data).includes('private') && !String(response.data).includes('test-deepgram'))
      }
      failure = ''
    })
    await t.test('malformed audio/transcripts are rejected and cannot settle billing', async () => {
      malformed = true
      for (const provider of ['cartesia', 'sarvam']) {
        process.env.SYSTEMAI_TTS_PROVIDER = provider; calls = []
        assert.equal((await invoke('tts')).status, 503)
        assert.equal(calls.length, 2)
      }
      calls = []
      const response = await invoke('stt')
      assert.equal(response.status, 503)
      assert.ok(!String(response.data).includes('private'))
      assert.equal(calls.length, 2)
    })
  } finally {
    globalThis.fetch = transport
    for (const [key, value] of Object.entries(saved)) { if (value === undefined) delete process.env[key]; else process.env[key] = value }
  }
})
