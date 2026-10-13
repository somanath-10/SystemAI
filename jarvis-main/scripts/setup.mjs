import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { ROOT, API, MCP_CONFIG } from '../bridge/config.mjs'
import { speechStatus } from '../bridge/speech.mjs'
console.log('SystemAI workspace setup')
console.log(`Node: ${process.versions.node}`)
console.log(`Python environment: ${existsSync(resolve(ROOT, '.venv/bin/python')) ? 'present' : 'missing'}`)
console.log(`OpenAI key: ${process.env.OPENAI_API_KEY || process.env.SYSTEMAI_OPENAI_API_KEY ? 'present (kept on the server)' : 'not configured'}`)
console.log(`MCP config: ${existsSync(MCP_CONFIG) ? 'present' : 'optional; copy config/mcp.example.json to config/mcp.json'}`)
try {
  const response = await fetch(API + '/inference/status', { signal: AbortSignal.timeout(2000) })
  const status = await response.json()
  console.log(`OpenAI: ${status.openai?.configured ? 'configured' : 'disabled or missing verified rates'}`)
  const speech = speechStatus(status.speech)
  console.log(`Speech: STT=${speech.stt_provider} (${speech.stt ? 'configured' : 'unavailable'}) TTS=${speech.tts_provider} (${speech.tts ? 'configured' : 'unavailable'})`)
} catch { console.log('API is stopped; npm start launches it together with the bridge and UI.') }
console.log('Start: npm start · UI: http://127.0.0.1:5802')
