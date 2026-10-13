import { readFile } from 'node:fs/promises'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js'
import { MCP_CONFIG, ROOT } from './config.mjs'
import { meteredExternal } from './usage.mjs'
import { LOCAL_SERVERS } from './policy.mjs'

const expand = (value) => String(value).replace(/\$\{([A-Z0-9_]+)\}/g, (_, key) => {
  if (!process.env[key]) throw new Error(`missing environment setting ${key}`)
  return process.env[key]
})

export async function connectMcp(getSession) {
  let configured = {}
  try { configured = JSON.parse(await readFile(MCP_CONFIG, 'utf8')).mcpServers || {} }
  catch (error) { if (error.code !== 'ENOENT') throw new Error('MCP configuration is invalid') }
  const clients = []
  const servers = []
  for (const [name, config] of Object.entries(configured)) {
    if (config.enabled === false) continue
    if (!/^[a-zA-Z0-9_-]{1,32}$/.test(name)) throw new Error('MCP server name is invalid')
    let client
    try {
      if (LOCAL_SERVERS.has(name)) throw new Error('MCP connector cannot use a reserved local server name')
      if (!Array.isArray(config.allowedTools) || !config.allowedTools.every((value) => typeof value === 'string') ||
          !Number.isFinite(config.usdPerCall) || config.usdPerCall <= 0 || config.usdPerCall > 10) {
        throw new Error('Configure allowedTools and a positive usdPerCall ceiling before enabling this connector')
      }
      const makeClient = () => new Client({ name: 'systemai-jarvis', version: '1.0.0' })
      client = makeClient()
      const headers = Object.fromEntries(Object.entries(config.headers || {}).map(([key, value]) => [key, expand(value)]))
      let transport
      if (config.url) {
        const url = new URL(expand(config.url))
        if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname))) {
          throw new Error('MCP HTTP connections require HTTPS or loopback')
        }
        transport = config.type === 'sse' ? new SSEClientTransport(url, { requestInit: { headers } }) :
          new StreamableHTTPClientTransport(url, { requestInit: { headers } })
      } else {
        if (typeof config.command !== 'string' || !Array.isArray(config.args || [])) throw new Error('MCP command is invalid')
        const env = Object.fromEntries(Object.entries(config.env || {}).map(([key, value]) => [key, expand(value)]))
        transport = new StdioClientTransport({ command: config.command, args: (config.args || []).map(expand),
          cwd: config.cwd || ROOT, env: { PATH: process.env.PATH || '', HOME: process.env.HOME || '', ...env } })
      }
      let timer
      try {
        await Promise.race([client.connect(transport), new Promise((_, reject) => {
          timer = setTimeout(() => reject(new Error('MCP connection timed out')), 10_000)
        })])
      } finally { clearTimeout(timer) }
      const tools = []
      let cursor
      const cursors = new Set()
      do {
        if (cursors.has(cursor) || cursors.size >= 16) throw new Error('MCP tool pagination did not finish')
        cursors.add(cursor)
        const page = await client.listTools(cursor ? { cursor } : {})
        tools.push(...page.tools)
        cursor = page.nextCursor
        if (tools.length > 256) throw new Error('MCP server exposes too many tools')
      } while (cursor)
      clients.push(client)
      servers.push({ name, tools: tools.filter((tool) => config.allowedTools.includes(tool.name)).map((tool) => ({
        name: tool.name, description: tool.description || '', parameters: tool.inputSchema,
        call: (args) => meteredExternal(getSession(), `mcp-${name}`, tool.name, config.usdPerCall,
          () => client.callTool({ name: tool.name, arguments: args }, undefined, { timeout: 60_000 })),
      })) })
    } catch (error) {
      await client?.close().catch(() => {})
      console.warn(`[systemai] MCP ${name} unavailable: ${error.message}`)
    }
  }
  return { servers, close: () => Promise.allSettled(clients.map((client) => client.close())) }
}
