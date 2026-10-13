import { defineConfig, mergeConfig } from 'vite'
import workspace from '../apps/desktop/ui/vite.config'
import { fileURLToPath } from 'node:url'

export default mergeConfig(workspace, defineConfig({
  root: fileURLToPath(new URL('../apps/desktop/ui', import.meta.url)),
}))
