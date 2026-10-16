import { API, api } from '../bridge/config.mjs'

export async function reuseLocalApi() {
  let response
  try {
    response = await fetch(API + '/health', { signal: AbortSignal.timeout(1500) })
  } catch (error) {
    const cause = error.cause
    if (cause?.code === 'ECONNREFUSED' || (cause instanceof AggregateError && cause.errors.length && cause.errors.every((item) => item.code === 'ECONNREFUSED'))) return false
    throw new Error(`Could not verify the API at ${API}; no services started`, { cause: error })
  }
  try {
    const health = await response.json()
    if (!response.ok || health.authentication_required !== true || health.status !== 'ok') throw new Error('incompatible health response')
    const schema = await (await api('/openapi.json', { signal: AbortSignal.timeout(1500) })).json()
    if (!schema.paths?.['/assistant/sessions']) throw new Error('assistant API is missing')
    return true
  } catch (error) {
    throw new Error(`An incompatible or unhealthy API is running at ${API}; check its local access key or stop it before launching this workspace`, { cause: error })
  }
}
