import * as bridge from './bridge'
import type { AskHandlers, Msg } from './conversation'

export type { AskHandlers, Msg }
export type { ConnectionState } from './bridge'
export const usingBridge = true
export const ask = (prompt: string, _history: Msg[], handlers: AskHandlers) => bridge.ask(prompt, handlers)
export { warmBridge as warm, watchServers, watchPanels, watchBlades, watchUi, watchCapture,
  watchConnection, cancel, interrupt, isConnected, bridgeServers as connectedLabels } from './bridge'
