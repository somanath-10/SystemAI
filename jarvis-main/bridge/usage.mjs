import { api } from './config.mjs'
import { randomUUID } from 'node:crypto'

const worker_id = randomUUID()

export async function meteredExternal(taskId, provider, feature, estimate, run, audioSeconds = 0) {
  if (!Number.isFinite(estimate) || estimate <= 0 || estimate > 10) throw new Error('Connector needs a positive configured call-cost ceiling')
  const details = { provider, feature, estimated_cost_usd: estimate, audio_seconds: audioSeconds, worker_id }
  const post = (phase, call_id) => api(`/tasks/${taskId}/assistant/external-usage`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...details, phase, call_id }),
  })
  const { call_id } = await (await post('reserve')).json()
  let renewing = false
  const heartbeat = setInterval(async () => {
    if (renewing) return
    renewing = true
    // Expiry blocks new charges; a confirmed result can still settle after a missed heartbeat.
    try { await post('renew', call_id) } catch { /* Keep the reservation until settlement. */ }
    finally { renewing = false }
  }, 20_000)
  heartbeat.unref()
  try {
    const result = await run()
    await post('settle', call_id)
    return result
  } catch (error) {
    await post('abandon', call_id).catch(() => {})
    throw error
  } finally { clearInterval(heartbeat) }
}
