import test from 'node:test'
import assert from 'node:assert/strict'
import { reuseLocalApi } from '../scripts/api-ready.mjs'
import { meteredExternal } from '../bridge/usage.mjs'

process.env.SYSTEMAI_API_TOKEN = 'fixture-access-' + 'a'.repeat(64)

test('startup only starts a new API after a refused connection', async () => {
  const transport = globalThis.fetch
  try {
    globalThis.fetch = async () => { throw new TypeError('fetch failed', { cause: Object.assign(new Error(), { code: 'ECONNREFUSED' }) }) }
    assert.equal(await reuseLocalApi(), false)
    const refused = Object.assign(new Error(), { code: 'ECONNREFUSED' })
    globalThis.fetch = async () => { throw new TypeError('fetch failed', { cause: new AggregateError([refused, refused]) }) }
    assert.equal(await reuseLocalApi(), false)
    for (const error of [new DOMException('timeout', 'TimeoutError'), new TypeError('fetch failed'),
      new TypeError('fetch failed', { cause: new AggregateError([refused, Object.assign(new Error(), { code: 'ENETUNREACH' })]) })]) {
      globalThis.fetch = async () => { throw error }
      await assert.rejects(reuseLocalApi(), /no services started/)
    }
    for (const response of [() => new Response('not json'), () => Response.json({ status: 'ok', authentication_required: 'yes' }),
      () => Response.json({ status: 'ok', authentication_required: true }, { status: 503 })]) {
      globalThis.fetch = async () => response()
      await assert.rejects(reuseLocalApi(), /incompatible or unhealthy/)
    }
    for (const schema of [() => Response.json({ detail: 'Unauthorized' }, { status: 401 }), () => new Response('bad schema'),
      () => Response.json({ paths: {} })]) {
      globalThis.fetch = async (url) => String(url).endsWith('/health')
        ? Response.json({ status: 'ok', authentication_required: true }) : schema()
      await assert.rejects(reuseLocalApi(), /incompatible or unhealthy/)
    }
    globalThis.fetch = async (url) => String(url).endsWith('/health')
      ? Response.json({ status: 'ok', authentication_required: true })
      : Response.json({ paths: { '/assistant/sessions': {} } })
    assert.equal(await reuseLocalApi(), true)
  } finally { globalThis.fetch = transport }
})

test('a missed billing heartbeat still settles a confirmed result; unknown outcomes remain reserved', async () => {
  const transport = globalThis.fetch, interval = globalThis.setInterval, clear = globalThis.clearInterval
  let heartbeat, cleared, phases = []
  globalThis.setInterval = (callback) => { heartbeat = callback; return { unref() {} } }
  globalThis.clearInterval = () => { cleared = true }
  globalThis.fetch = async (_url, options) => {
    const { phase } = JSON.parse(options.body)
    phases.push(phase)
    if (phase === 'renew') throw new Error('temporary connection loss')
    return Response.json({ call_id: 'model_fixture' })
  }
  try {
    assert.equal(await meteredExternal('task_fixture', 'cartesia', 'tts', 0.01, async () => {
      await heartbeat()
      return 'confirmed audio'
    }), 'confirmed audio')
    assert.deepEqual(phases, ['reserve', 'renew', 'settle'])
    assert.equal(cleared, true)
    phases = []; cleared = false
    await assert.rejects(meteredExternal('task_fixture', 'deepgram', 'stt', 0.01, async () => { throw new Error('unknown outcome') }), /unknown outcome/)
    assert.deepEqual(phases, ['reserve', 'abandon'])
    assert.equal(cleared, true)
    phases = []
    globalThis.fetch = async (_url, options) => {
      const { phase } = JSON.parse(options.body); phases.push(phase)
      if (phase === 'settle') throw new Error('settlement unavailable')
      return Response.json({ call_id: 'model_fixture' })
    }
    await assert.rejects(meteredExternal('task_fixture', 'cartesia', 'tts', 0.01, async () => 'audio'), /settlement unavailable/)
    assert.deepEqual(phases, ['reserve', 'settle', 'abandon'])
  } finally { globalThis.fetch = transport; globalThis.setInterval = interval; globalThis.clearInterval = clear }
})
