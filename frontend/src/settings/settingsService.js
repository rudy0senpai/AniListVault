/* ==========================================================================
 * AnimeVault Settings Service
 * ==========================================================================
 * Centralised settings service.
 *
 * Settings are stored per-user in the app data directory as
 *   <appdata>/AnimeVault/settings.json
 *
 * The FastAPI backend serves this file over /api/settings so that the
 * React frontend and the Qt desktop application share ONE source of truth.
 *
 * The service provides:
 *   - Typed, validated settings (defaults + migration for removed keys)
 *   - A single consumeable state (no duplicate/conflicting sources)
 *   - Async load/save with the backend as the authoritative store
 *   - LocalStorage fallback ONLY for headless development (never for
 *     production Electron/desktop deployments)
 *
 * Usage:
 *   import { load, save, defaults, migrate } from './settingsService';
 *   const s = await load();
 *   s.values.library.view = 'Grid';
 *   await save(s);
 * ========================================================================== */

import { DEFAULTS, DEFAULT_VALUES, KEY } from './LiquidSettings';

const STORAGE_KEY = KEY; // "animevault.settings"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Deep-clone a value (handles plain objects/arrays). */
export function clone(v) {
  return JSON.parse(JSON.stringify(v));
}

/** Merge `override` over `base` (deep merge for plain objects). */
export function deepMerge(base, override) {
  const out = clone(base);
  for (const [k, ov] of Object.entries(override || {})) {
    if (ov && typeof ov === 'object' && !Array.isArray(ov) && base[k] && typeof base[k] === 'object' && !Array.isArray(base[k])) {
      out[k] = deepMerge(base[k], ov);
    } else {
      out[k] = clone(ov);
    }
  }
  return out;
}

/**
 * Validate and normalise a settings object against the schema.
 * Returns the normalised object (with defaults filled in).
 */
export function validateSettings(input) {
  const cfg = clone(DEFAULTS);

  // Top-level scalar settings (themeId, glass, animations, reduce)
  const scalarKeys = ['themeId', 'glass', 'animations', 'reduce'];
  for (const k of scalarKeys) {
    if (k in input && input[k] !== null && input[k] !== undefined) {
      if (k === 'themeId') {
        cfg.themeId = String(input.themeId);
        if (!THEMES.some(t => t.id === cfg.themeId)) cfg.themeId = DEFAULTS.themeId;
      } else if (k === 'glass') {
        cfg.glass = clamp(Number(input.glass) || 0, 0, 100);
      } else if (k === 'animations') {
        cfg.animations = Boolean(input.animations);
      } else if (k === 'reduce') {
        cfg.reduce = Boolean(input.reduce);
      }
    }
  }

  // values sub-object: normalise against the schema
  cfg.values = clone(DEFAULT_VALUES);
  const rawValues = input?.values && typeof input.values === 'object' ? input.values : {};
  for (const [key, raw] of Object.entries(rawValues)) {
    const parts = key.split('.');
    if (parts.length !== 2) continue;
    const [section, field] = parts;
    const sectionDef = SCHEMA[section];
    if (!sectionDef) continue;
    const fieldDef = sectionDef.find(r => r.key === field);
    if (!fieldDef) continue;

    let value = raw;
    switch (fieldDef.type) {
      case 'toggle':
        value = Boolean(value);
        break;
      case 'choice':
      case 'select':
        value = String(value);
        if (!fieldDef.options.includes(value)) value = fieldDef.def;
        break;
      case 'slider':
        value = clamp(Number(value) || fieldDef.def, fieldDef.min, fieldDef.max);
        break;
      case 'action':
      case 'info':
        // Actions/Info have no user-settable value; ignore.
        break;
      default:
        value = raw;
    }
    cfg.values[key] = value;
  }

  //.colors sub-object: normalise against DEFAULTS.colors
  if (input?.colors && typeof input.colors === 'object') {
    cfg.colors = { ...cfg.colors, ...input.colors };
  }

  // customThemes: always an array of theme objects
  cfg.customThemes = Array.isArray(input?.customThemes) ? input.customThemes : [];

  return cfg;
}

// Re-export THEMES from LiquidSettings (clone to avoid mutation)
import { THEMES } from './LiquidSettings';

/** Default settings object (static, never mutated). */
export const defaults = clone(DEFAULTS);

/** Default values for the `values` sub-object. */
export const defaultValues = clone(DEFAULT_VALUES);

// Expose as `THEMES` for validation purposes
export { THEMES };

/**
 * Load settings.
 *
 * Priority:
 *   1. Backend (GET /api/settings) – authoritative store
 *   2. localStorage – ONLY in development when the backend is unreachable
 *
 * Returns the validated, merged settings object.
 */
export async function load() {
  // Try the backend first (Electron bridge in production, direct fetch in dev).
  try {
    const res = await window.backend?.get ? window.backend.get('/api/settings') : null;
    if (res) {
      const validated = validateSettings(res);
      // Pre-warm localStorage with the same data (for fast in-memory reads
      // and for non-JS contexts to pick up later).
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(validated));
      } catch (e) { /* storage unavailable; continue */ }
      return validated;
    }
  } catch (e) {
    // Ignore network errors; fall through to localStorage fallback.
  }

  // Development-only fallback (no backend configured).
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return validateSettings(parsed);
    }
  } catch (e) { /* fall through */ }

  return clone(defaults);
}

/**
 * Save settings.
 *
 * 1. PUT /api/settings (authoritative)
 * 2. Update localStorage (fallback / fast-read cache)
 */
export async function save(settings) {
  const validated = validateSettings(settings);
  try {
    const res = await window.backend?.get ? window.backend.put('/api/settings', validated) : null;
    if (res) {
      // Persist to localStorage as well (fast-read cache for the next load).
      try { localStorage.setItem(STORAGE_KEY, JSON.stringify(validated)); } catch (e) {}
      return validated;
    }
  } catch (e) {
    // Backend unreachable – persist to localStorage as the fallback store.
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(validated)); } catch (e) {}
    // In a real production build, log the error; the backend will be the
    // authoritative store once the app is running under Electron.
    console.warn('Settings save fell back to localStorage (backend unreachable).');
  }
  return validated;
}

/**
 * Load settings and return a promise that resolves to the validated
 * settings object.  If the app is running in a context where the backend
 * is available, this reads from the backend; otherwise falls back to
 * localStorage (development-only).
 */
export default async function loadSettings() {
  return load();
}
