import { cpSync, existsSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const from = fileURLToPath(new URL('../node_modules/@mediapipe/tasks-vision/wasm', import.meta.url))
const to = fileURLToPath(new URL('../public/mediapipe', import.meta.url))
export function vendorWasm() {
  if (!existsSync(from)) throw new Error('Install Jarvis dependencies before building the workspace')
  mkdirSync(to, { recursive: true })
  cpSync(from, to, { recursive: true })
  cpSync(new URL('../LICENSE', import.meta.url), new URL('../public/LICENSE.txt', import.meta.url))
}
vendorWasm()
