/**
 * Secure renderer → backend API bridge.
 *
 * In Electron (production) the preload script exposes `window.backend` through
 * `contextBridge` and forwards calls via `ipcRenderer.invoke('api:get')`, so the
 * renderer has NO direct fetch to arbitrary URLs, and cannot `require()`, run
 * shell commands, or access the filesystem.
 *
 * In development (no Electron) `window.backend` is undefined and the module
 * falls back to a direct fetch to the local backend on 127.0.0.1:8765. This
 * fallback is a dev-only shortcut and must never be used in production when
 * the bridge is available.
 */

const BRIDGE = window.backend;

export async function apiGet(path) {
  const req = BRIDGE?.get ? BRIDGE.get(path) : fetch(`http://127.0.0.1:8765${path}`);
  const res = await req;
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = `${res.status} ${await res.text()}`; } catch { /* ignore */ }
    throw new Error(`API ${res.status} ${path} — ${detail}`, { cause: res });
  }
  return res.body;
}

export { BRIDGE };
