import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath } from "node:url";

export default defineConfig({
  plugins: [react()],
  publicDir: fileURLToPath(new URL("../../../jarvis-main/public", import.meta.url)),
  resolve: { alias: {
    react: fileURLToPath(new URL("./node_modules/react", import.meta.url)),
    "react-dom": fileURLToPath(new URL("./node_modules/react-dom", import.meta.url)),
  } },
  optimizeDeps: { exclude: ["kokoro-js", "phonemizer", "@huggingface/transformers"] },
  preview: { host: "127.0.0.1", port: 5802, strictPort: true },
  server: { host: "127.0.0.1", port: 5802, strictPort: true,
    fs: { allow: [fileURLToPath(new URL("../../../", import.meta.url))],
      deny: [".env", ".env.*", "*.{crt,pem}", "**/.git/**", "**/keys/local-api-token", "**/*.sqlite3", "**/*.sqlite3-*", "**/runtime.lock"] } },
});
