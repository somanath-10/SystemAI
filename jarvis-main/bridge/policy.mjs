export const LOCAL_SERVERS = new Set(['jarvis', 'jarvis_ui', 'jarvis_eyes', 'jarvis_chrome', 'systemai'])
const CHROME_READS = new Set(['chrome_status', 'chrome_tabs', 'chrome_read_page', 'chrome_page_text', 'chrome_find', 'chrome_screenshot', 'chrome_scroll', 'chrome_console', 'chrome_network'])
const READ = /^(get|list|read|search|find|query|fetch|check|describe|inspect|show|view|explain|screenshot)(?:[_-]|$)/i
const EFFECT = /(?:^|[_-])(send|call|post|create|delete|remove|update|edit|write|install|launch|tap|swipe|press|type|buy|pay|charge|publish|deploy|outbound|download|generate)(?:[_-]|$)/i

export function permittedTool(name) {
  const [, server, ...parts] = name.split('__')
  if (!name.startsWith('mcp__') || !server) return false
  const tool = parts.join('__')
  if (server === 'jarvis_chrome') return CHROME_READS.has(tool)
  if (LOCAL_SERVERS.has(server)) return true
  return READ.test(tool) && !EFFECT.test(tool)
}
