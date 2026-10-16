import { useEffect, useState, type ReactNode } from 'react';
import { API, accessKey, saveAccessKey, saveMediaKey, configureOperationTimeout } from './api';
import { BRIDGE_HTTP_URL } from '../../../../jarvis-main/src/config';
import './access.css';

export function AccessGate({ children }: { children: ReactNode }) {
  const [key, setKey] = useState(accessKey);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function unlock(candidate: string) {
    setBusy(true); setError('');
    try {
      const headers = { authorization: `Bearer ${candidate}` };
      const response = await fetch(`${API}/auth/check`, { headers, signal: AbortSignal.timeout(5000) });
      if (!response.ok) throw new Error(response.status === 401 ? 'Access key was not accepted.' : 'Local runtime is unavailable.');
      const status = await response.json();
      if (status.authenticated !== true) throw new Error('Local runtime authentication is unavailable.');
      configureOperationTimeout(status.operation_timeout_ms);
      const bridge = await fetch(`${BRIDGE_HTTP_URL}/authenticate`, { method: 'POST', headers, credentials: 'include', signal: AbortSignal.timeout(5000) });
      if (!bridge.ok) throw new Error('The bridge could not authenticate. Restart both services and retry.');
      const media = await bridge.json();
      if (typeof media.media_token !== 'string' || !/^[0-9a-f]{64}$/.test(media.media_token)) throw new Error('Bridge media access is unavailable.');
      saveMediaKey(media.media_token);
      saveAccessKey(candidate);
      setReady(true); setKey('');
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Could not unlock workspace.'); }
    finally { setBusy(false); }
  }
  useEffect(() => { const saved = accessKey(); if (saved) void unlock(saved); }, []);
  if (ready) return children;
  return <main className="access-screen"><form className="access-card" onSubmit={(event) => { event.preventDefault(); void unlock(key.trim()); }}>
    <div className="access-orb" aria-hidden="true" />
    <h1>Unlock workspace</h1>
    <label htmlFor="workspace-access-key">Local access key</label>
    <input id="workspace-access-key" type="password" autoComplete="off" value={key} onChange={(event) => setKey(event.target.value)} required autoFocus />
    <p>Use SYSTEMAI_API_TOKEN, or the key in your runtime’s <code>keys/local-api-token</code> file. This is not a provider API key.</p>
    <button disabled={busy || !key.trim()}>{busy ? 'Connecting…' : 'Unlock'}</button>
    {error && <p role="alert">{error}</p>}
  </form></main>;
}
