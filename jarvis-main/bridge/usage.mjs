import { api } from './config.mjs'

export async function meteredExternal(taskId, provider, feature, estimate, run, audioSeconds = 0) {
  if (!Number.isFinite(estimate) || estimate <= 0 || estimate > 10) throw new Error('Connector needs a positive configured call-cost ceiling')
  const details = { provider, feature, estimated_cost_usd: estimate, audio_seconds: audioSeconds }
  const post = (phase, call_id) => api(`/tasks/${taskId}/assistant/external-usage`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...details, phase, call_id }),
  })
  const { call_id } = await (await post('reserve')).json()
  const result = await run()
  await post('settle', call_id)
  return result
}
