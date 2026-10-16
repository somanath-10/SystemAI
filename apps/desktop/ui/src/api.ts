const configured = import.meta.env.VITE_SYSTEMAI_API ?? 'http://127.0.0.1:8765';
const origin = new URL(configured);
if (origin.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(origin.hostname) || origin.username || origin.password || origin.pathname !== '/' || origin.search || origin.hash) throw new Error('SystemAI API must be a plain loopback HTTP origin');
export const API = origin.origin;
let currentKey = '';
let currentMediaKey = '';
export function mediaKey() { try { return sessionStorage.getItem('systemai.mediaKey') || currentMediaKey; } catch { return currentMediaKey; } }
export function saveMediaKey(key: string) {
  const previous = mediaKey();
  currentMediaKey = key;
  try { sessionStorage.setItem('systemai.mediaKey', key); } catch { /* Memory-only access. */ }
  if (previous !== key && typeof window !== 'undefined') window.dispatchEvent(new Event('systemai-media-key'));
}
export function watchMediaKey(changed: () => void) {
  window.addEventListener('systemai-media-key', changed);
  window.addEventListener('storage', changed);
  return () => { window.removeEventListener('systemai-media-key', changed); window.removeEventListener('storage', changed); };
}
let operationTimeout = 250_000;
export const operationTimeoutMs = () => operationTimeout;
export function configureOperationTimeout(value: unknown) { if (typeof value === 'number' && Number.isInteger(value) && value >= 250_000 && value <= 1_210_000) operationTimeout = value; }
export function accessKey() { try { return sessionStorage.getItem('systemai.accessKey') || currentKey; } catch { return currentKey; } }
export function saveAccessKey(key: string) { currentKey = key; try { sessionStorage.setItem('systemai.accessKey', key); } catch { /* Memory-only access when storage is disabled. */ } }
export const accessHeaders = () => ({ authorization: `Bearer ${accessKey()}` });
export function expireAccessKey(rejected: string) {
  if (!rejected || rejected !== accessKey()) return;
  saveAccessKey('');
  saveMediaKey('');
  // Reload also stops microphones, audio and sockets; Task Center must relock its parent.
  try { (window.top || window).location.reload(); } catch { window.location.reload(); }
}
export async function apiFetch(url: string, options: RequestInit = {}) {
  if (new URL(url).origin !== API) throw new Error('Refusing to send local access key to another origin');
  const key = accessKey();
  const headers = new Headers(options.headers);
  headers.set('authorization', `Bearer ${key}`);
  const response = await fetch(url, { ...options, headers, signal: options.signal || AbortSignal.timeout(options.method && options.method !== 'GET' ? operationTimeout : 60_000) });
  if (response.status === 401) expireAccessKey(key);
  return response;
}
