export type Msg = { role: 'user' | 'assistant'; content: string }
export type AskHandlers = { onText: (delta: string) => void; onTool: (name: string) => void }
