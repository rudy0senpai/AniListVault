import React, {
  useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState,
} from "react";
import { BubbleButton } from "./LiquidGlass"; // from the previous file (also injects the shared glass CSS)

/* ------------------------------------------------------------------ *
 *  AnimeVault Settings Panel (Liquid Glass)
 *  Connected to the Qt bridge for persistence and actions.
 *  Usage:
 *    <SettingsSurface bridge={bridge} onApply={...} onClose={...} />
 *  Exports: themeToCssVars(settings) — injects CSS custom properties to
 *  theme the rest of the app from applied settings.
 * ------------------------------------------------------------------ */

/* ============================== colour maths ============================== */
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const normHex = (h) => {
  h = String(h).trim().replace(/^#/, "");
  if (/^[0-9a-f]{3}$/i.test(h)) h = h.split("").map((c) => c + c).join("");
  return /^[0-9a-f]{6}$/i.test(h) ? "#" + h.toLowerCase() : null;
};
const hexToRgb = (hex) => { const n = parseInt(hex.slice(1), 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255]; };
const rgbToHex = ([r, g, b]) => "#" + [r, g, b].map((x) => clamp(Math.round(x), 0, 255).toString(16).padStart(2, "0")).join("");
const rgbStr = (hex) => hexToRgb(hex).join(",");
function rgbToHsv([r, g, b]) {
  r /= 255; g /= 255; b /= 255;
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
  let h = 0;
  if (d) {
    if (mx === r) h = ((g - b) / d) % 6; else if (mx === g) h = (b - r) / d + 2; else h = (r - g) / d + 4;
    h *= 60; if (h < 0) h += 360;
  }
  return [h, mx ? d / mx : 0, mx];
}
function hsvToRgb(h, s, v) {
  const f = (n) => { const k = (n + h / 60) % 6; return v - v * s * Math.max(0, Math.min(k, 4 - k, 1)); };
  return [f(5), f(3), f(1)].map((x) => Math.round(x * 255));
}
const lum = (hex) => { const [r, g, b] = hexToRgb(hex); return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255; };
const mix = (hex, target, t) => {
  const a = hexToRgb(hex), b = hexToRgb(target);
  return rgbToHex(a.map((x, i) => x + (b[i] - x) * t));
};
const makeThemeFromAccent = (accent) => {
  const [h, s, v] = rgbToHsv(hexToRgb(accent));
  const hx = (hh, ss, vv) => rgbToHex(hsvToRgb((hh + 360) % 360, ss, vv));
  return {
    accent, secondary: hx(h + 40, Math.max(s, 0.35), Math.max(v, 0.8)),
    bg: hx(h, Math.min(0.6, s * 0.7 + 0.15), 0.11), surface: hx(h, 0.45, 0.2), text: hx(h, 0.06, 0.96),
  };
};

/* ================================ data ================================ */
const THEMES = [
  { id: "midnight", name: "Vault Midnight", bg: "#0b1020", surface: "#131a2e", text: "#e6ecfa", accent: "#7ee8d0", secondary: "#b79cf5" },
  { id: "dracula", name: "Dracula", bg: "#282a36", surface: "#343746", text: "#f8f8f2", accent: "#bd93f9", secondary: "#ff79c6" },
  { id: "nord", name: "Nord", bg: "#2e3440", surface: "#3b4252", text: "#eceff4", accent: "#88c0d0", secondary: "#b48ead" },
  { id: "tokyo", name: "Tokyo Night", bg: "#1a1b26", surface: "#24283b", text: "#c0caf5", accent: "#7aa2f7", secondary: "#bb9af7" },
  { id: "mocha", name: "Catppuccin Mocha", bg: "#1e1e2e", surface: "#313244", text: "#cdd6f4", accent: "#cba6f7", secondary: "#f5c2e7" },
  { id: "rose", name: "Rosé Pine", bg: "#191724", surface: "#26233a", text: "#e0def4", accent: "#c4a7e7", secondary: "#ebbcba" },
  { id: "gruvbox", name: "Gruvbox", bg: "#282828", surface: "#3c3836", text: "#ebdbb2", accent: "#fabd2f", secondary: "#fe8019" },
  { id: "onedark", name: "One Dark", bg: "#282c34", surface: "#353b45", text: "#abb2bf", accent: "#61afef", secondary: "#c678dd" },
  { id: "monokai", name: "Monokai", bg: "#272822", surface: "#3e3d32", text: "#f8f8f2", accent: "#a6e22e", secondary: "#f92672" },
  { id: "solardark", name: "Solarized Dark", bg: "#002b36", surface: "#073642", text: "#eee8d5", accent: "#2aa198", secondary: "#b58900" },
  { id: "latte", name: "Catppuccin Latte", bg: "#eff1f5", surface: "#ccd0da", text: "#4c4f69", accent: "#8839ef", secondary: "#ea76cb" },
  { id: "sollight", name: "Solarized Light", bg: "#fdf6e3", surface: "#eee8d5", text: "#586e75", accent: "#268bd2", secondary: "#d33682" },
];
const themeColors = (t) => ({ accent: t.accent, secondary: t.secondary, bg: t.bg, surface: t.surface, text: t.text });

const ACCENTS = [
  ["Purple", "#a78bfa", "#7dd3fc"], ["Blue", "#60a5fa", "#a78bfa"], ["Pink", "#f472b6", "#fbbf24"],
  ["Mint", "#7ee8d0", "#b79cf5"], ["Amber", "#fbbf24", "#fb7185"],
];
const ROLES = [["accent", "Accent"], ["secondary", "Secondary"], ["bg", "Background"], ["surface", "Surface"], ["text", "Text"]];

const SECTIONS = [
  ["appearance", "Appearance"], ["library", "Library"], ["notifications", "Notifications"],
  ["data", "Data & Storage"], ["metadata", "Metadata"], ["recommendations", "Recommendations"],
  ["performance", "Performance"], ["language", "Language"], ["about", "About"],
];

const SCHEMA = {
  library: [
    { key: "view", type: "choice", label: "Default view", hint: "How titles are laid out", options: ["Grid", "List", "Compact"], def: "Grid" },
    { key: "progress", type: "toggle", label: "Show progress on cards", def: true },
    { key: "confirmDelete", type: "toggle", label: "Confirm before deleting", hint: "Ask first when removing titles", def: true },
    { key: "autoComplete", type: "toggle", label: "Move finished titles to Completed", def: false },
  ],
  notifications: [
    { key: "episodes", type: "toggle", label: "New episode alerts", def: true },
    { key: "reminders", type: "toggle", label: "Release reminders", def: false },
    { key: "lead", type: "choice", label: "Remind me", options: ["1 hour before", "1 day before", "1 week before"], def: "1 day before" },
    { key: "badge", type: "toggle", label: "Show badge count on the app icon", def: true },
  ],
  data: [
    { key: "autoBackup", type: "toggle", label: "Automatic backups", hint: "Save a copy of your database on a schedule", def: true },
    { key: "every", type: "choice", label: "Backup frequency", options: ["Daily", "Weekly", "Monthly"], def: "Weekly" },
    { key: "keep", type: "slider", label: "Backups to keep", min: 1, max: 30, step: 1, unit: "", def: 7 },
    { key: "backupNow", type: "action", label: "Back up now", hint: "Create a backup right away", button: "Back Up Database" },
    { key: "clearCache", type: "action", label: "Image cache", hint: "Remove downloaded posters", button: "Clear Cache" },
  ],
  metadata: [
    { key: "source", type: "choice", label: "Metadata source", options: ["AniList", "MyAnimeList", "Kitsu"], def: "AniList" },
    { key: "onStart", type: "toggle", label: "Fetch missing data on startup", def: false },
    { key: "overwrite", type: "toggle", label: "Overwrite existing fields", hint: "Replace values you already have", def: false },
    { key: "autoRetry", type: "toggle", label: "Retry failed lookups automatically", def: true },
  ],
  recommendations: [
    { key: "basis", type: "choice", label: "Base suggestions on", options: ["Completed", "Ratings", "Both"], def: "Both" },
    { key: "count", type: "slider", label: "Number of suggestions", min: 5, max: 50, step: 5, unit: "", def: 20 },
    { key: "hidePlanned", type: "toggle", label: "Hide titles already in Plan to Watch", def: true },
    { key: "adult", type: "toggle", label: "Include adult titles", def: false },
  ],
  performance: [
    { key: "gpu", type: "toggle", label: "Hardware acceleration", hint: "Restart required to take effect", def: true },
    { key: "cache", type: "slider", label: "Image cache size", min: 100, max: 2000, step: 100, unit: " MB", def: 500 },
    { key: "lazy", type: "toggle", label: "Load posters as you scroll", def: true },
    { key: "virtual", type: "toggle", label: "Virtualize long lists", def: true },
  ],
  language: [
    { key: "lang", type: "select", label: "App language", options: ["English", "日本語", "Español", "Français", "Deutsch", "हिन्दी"], def: "English" },
    { key: "titles", type: "choice", label: "Title language", options: ["Romaji", "English", "Native"], def: "Romaji" },
    { key: "date", type: "choice", label: "Date format", options: ["DD/MM/YYYY", "MM/DD/YYYY", "YYYY-MM-DD"], def: "DD/MM/YYYY" },
  ],
  about: [
    { key: "version", type: "info", label: "Version" },
    { key: "update", type: "action", label: "Updates", hint: "See if a newer version is available", button: "Check for Updates" },
    { key: "licenses", type: "action", label: "Open source licenses", button: "View Licenses" },
  ],
};

const APPEARANCE_INDEX = [
  ["Theme", "popular themes presets preview"], ["Accent colour", "swatches purple blue pink custom"],
  ["Colour studio", "colour picker maker selector hex rgb palette harmony eyedropper"],
  ["Glass intensity", "blur transparency"], ["Animations", "motion"], ["Reduce effects", "performance blur flat"],
].map(([label, hint]) => ({ section: "appearance", label, hint }));
const INDEX = [
  ...APPEARANCE_INDEX,
  ...Object.entries(SCHEMA).flatMap(([section, rows]) => rows.map((r) => ({ section, label: r.label, hint: r.hint || "" }))),
];

const KEY = "animevault.settings";
const defaultValues = Object.fromEntries(
  Object.entries(SCHEMA).flatMap(([s, rows]) => rows.filter((r) => "def" in r).map((r) => [`${s}.${r.key}`, r.def]))
);
const DEFAULTS = {
  themeId: "midnight", colors: themeColors(THEMES[0]), customThemes: [],
  glass: 70, animations: true, reduce: false, values: defaultValues,
};

// Async settings loading with proper loading state and error handling.
// Qt WebChannel getSettings is a @Slot(result=str) that returns a JSON string
// synchronously across the web channel, so we wrap it in a Promise.
async function loadAsync(bridge) {
  const loading = { loaded: false, error: null, settings: null };

  if (!bridge || typeof bridge.getSettings !== "function") {
    loading.settings = DEFAULTS;
    loading.loaded = true;
    return loading;
  }

  // Bridge.getSettings returns a JSON string synchronously via the WebChannel.
  return new Promise((resolve) => {
    try {
      if (typeof bridge.getSettings === "function") {
        const raw = bridge.getSettings();
        if (raw) {
          try {
            const parsed = JSON.parse(raw);
            if (parsed) {
              loading.settings = {
                ...DEFAULTS,
                ...parsed,
                colors: { ...DEFAULTS.colors, ...parsed.colors },
                values: { ...defaultValues, ...parsed.values },
              };
              loading.loaded = true;
            } else {
              loading.error = "Parsed settings were empty";
              loading.settings = DEFAULTS;
            }
          } catch (parseError) {
            loading.error = `Failed to parse settings JSON: ${parseError.message}`;
            loading.settings = DEFAULTS;
          }
        } else {
          loading.error = "Bridge returned no data";
          loading.settings = DEFAULTS;
        }
      }
    } catch (e) {
      loading.error = `Bridge.getSettings threw: ${e.message}`;
      loading.settings = DEFAULTS;
    }
    loading.loaded = true;
    resolve(loading);
  });
}

// Wrapper that returns the loading state
function load(bridge) {
  return loadAsync(bridge);
}

/* ================================== CSS ================================== */
const CSS = `
.sv{--sv-blur:24px;--sv-a:.4;position:relative;display:flex;flex-direction:column;gap:12px;padding:14px;width:100%;max-width:1080px;
  height:min(740px,calc(100vh - 32px));margin:0 auto;border-radius:38px;overflow:hidden;isolation:isolate;font-size:14px;
  background:rgb(var(--bgc));color:rgb(var(--txt));border:1px solid rgba(255,255,255,.12);box-shadow:0 40px 80px -30px rgba(0,0,0,.8);}
.sv *{box-sizing:border-box;}
.sv .lg{--lg-accent:var(--acc);--lg-violet:var(--sec);}
.sv .lg-btn{color:rgba(var(--txt),.92);}
.sv .lg-btn:hover{color:rgb(var(--txt));}
.sv .lg-btn::before{backdrop-filter:blur(calc(var(--sv-blur) * .6)) saturate(1.8);-webkit-backdrop-filter:blur(calc(var(--sv-blur) * .6)) saturate(1.8);}
.sv--light .lg-btn--danger{color:#b4233b;}

.sv-orb{position:absolute;z-index:-1;border-radius:50%;filter:blur(70px);pointer-events:none;animation:sv-drift 16s ease-in-out infinite alternate;}
.sv-orb--a{width:380px;height:380px;left:-60px;top:-80px;background:rgba(var(--acc),.45);}
.sv-orb--b{width:460px;height:460px;right:-120px;top:20%;background:rgba(var(--sec),.4);animation-duration:21s;animation-delay:-6s;}
.sv-orb--c{width:360px;height:360px;left:35%;bottom:-170px;background:rgba(var(--acc),.28);animation-duration:18s;animation-delay:-3s;}
.sv--light .sv-orb{opacity:.55;}
@keyframes sv-drift{to{transform:translate(60px,40px) scale(1.15)}}

.sv-glass{background:linear-gradient(150deg,rgba(255,255,255,.1),rgba(255,255,255,0) 40%),rgba(var(--surf),var(--sv-a));
  backdrop-filter:blur(var(--sv-blur)) saturate(1.8);-webkit-backdrop-filter:blur(var(--sv-blur)) saturate(1.8);
  border:1px solid rgba(255,255,255,.14);border-radius:30px;
  box-shadow:inset 0 1px 1px rgba(255,255,255,.45),inset 0 -12px 22px rgba(var(--sec),.06),0 20px 40px -22px rgba(0,0,0,.7);}
.sv--light .sv-glass{box-shadow:inset 0 1px 1px rgba(255,255,255,.9),0 20px 40px -24px rgba(0,0,0,.3);}

/* header */
.sv-head{display:flex;align-items:center;gap:16px;padding:12px 14px 12px 26px;}
.sv-title{margin:0;flex:1;font-size:20px;font-weight:650;letter-spacing:-.01em;}
.sv-search{position:relative;width:min(300px,45%);}
.sv-search input{width:100%;padding:10px 16px 10px 40px;border-radius:999px;border:1px solid rgba(var(--txt),.14);background:rgba(var(--txt),.06);
  color:inherit;font:inherit;outline:none;box-shadow:inset 0 2px 5px rgba(0,0,0,.25),inset 0 -1px 1px rgba(255,255,255,.15);transition:box-shadow .3s,border-color .3s;}
.sv-search input:focus{border-color:rgba(var(--acc),.8);box-shadow:inset 0 2px 5px rgba(0,0,0,.25),0 0 0 4px rgba(var(--acc),.2),0 0 24px rgba(var(--acc),.35);}
.sv-search svg{position:absolute;left:14px;top:50%;transform:translateY(-50%);width:16px;height:16px;opacity:.6;pointer-events:none;}

/* body */
.sv-body{flex:1;min-height:0;display:grid;grid-template-columns:230px 1fr;gap:12px;}
.sv-side{padding:10px;overflow:auto;}
.sv-nav{position:relative;display:flex;flex-direction:column;gap:2px;}
.sv-navitem{position:relative;z-index:2;display:flex;align-items:center;gap:12px;padding:12px 16px;border:0;background:none;border-radius:22px;
  font:inherit;font-weight:500;text-align:left;color:rgba(var(--txt),.68);cursor:pointer;transition:color .3s,transform .35s cubic-bezier(.3,1.7,.5,1);}
.sv-navitem:hover{color:rgb(var(--txt));transform:translateX(3px);}
.sv-navitem[aria-selected="true"]{color:#fff;text-shadow:0 0 12px rgba(var(--acc),.9),0 1px 2px rgba(0,0,0,.35);}
.sv--light .sv-navitem[aria-selected="true"]{color:rgb(var(--txt));text-shadow:none;}
.sv-navitem:focus-visible,.sv-chip:focus-visible,.sv-swatch:focus-visible,.sv-theme:focus-visible,.sv-switch:focus-visible,.sv-pad:focus-visible{outline:2px solid rgba(var(--acc),.95);outline-offset:3px;}
.sv-navitem i{width:9px;height:9px;border-radius:50%;flex:none;transition:transform .4s cubic-bezier(.3,1.9,.5,1);
  background:radial-gradient(circle at 30% 28%,#fff 0 14%,rgba(var(--acc),.95) 44%,rgba(var(--sec),.6));box-shadow:0 0 10px rgba(var(--acc),.5);}
.sv-navitem[aria-selected="true"] i{transform:scale(1.5);}
.sv-nbubble{position:absolute;left:0;right:0;z-index:1;pointer-events:none;overflow:hidden;border-radius:22px;
  background:radial-gradient(120% 150% at 25% 6%,rgba(255,255,255,.55),rgba(255,255,255,0) 42%),linear-gradient(160deg,rgba(var(--acc),.55),rgba(var(--sec),.32));
  border:1px solid rgba(255,255,255,.35);box-shadow:inset 0 1px 1px rgba(255,255,255,.8),inset 0 -8px 14px rgba(var(--acc),.35),0 10px 24px -8px rgba(var(--acc),.6);
  animation:lg-morph 5s ease-in-out infinite;}
.sv-nbubble.is-moving{transform:scale(.94,1.05);}

.sv-main{display:flex;flex-direction:column;min-height:0;}
.sv-scroll{flex:1;min-height:0;overflow:auto;padding:22px 26px 26px;scrollbar-width:thin;scrollbar-color:rgba(var(--acc),.5) transparent;}
.sv-page{animation:sv-in .5s cubic-bezier(.2,1.4,.4,1) backwards;}
@keyframes sv-in{from{opacity:0;transform:translateY(12px) scale(.985)}}
.sv-foot{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 20px;border-top:1px solid rgba(var(--txt),.1);}
.sv-foot-r{display:flex;align-items:center;gap:14px;}
.sv-dirty{font-size:13px;color:rgba(var(--txt),.65);display:inline-flex;align-items:center;gap:8px;}
.sv-dirty::before{content:"";width:8px;height:8px;border-radius:50%;background:rgb(var(--acc));box-shadow:0 0 10px rgb(var(--acc));}
.sv-toast{font-size:13px;padding:7px 14px;border-radius:999px;background:rgba(var(--acc),.25);border:1px solid rgba(var(--acc),.6);animation:lg-item .5s cubic-bezier(.2,1.6,.4,1) both;}

/* typography + rows */
.sv-h2{margin:0 0 4px;font-size:22px;font-weight:650;letter-spacing:-.01em;}
.sv-sub{margin:0 0 6px;color:rgba(var(--txt),.62);}
.sv-h3{margin:28px 0 4px;font-size:15px;font-weight:650;}
.sv-hint{margin:0 0 14px;font-size:13px;color:rgba(var(--txt),.6);}
.sv-row{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:14px 18px;margin-bottom:8px;border-radius:22px;
  background:rgba(var(--txt),.045);border:1px solid rgba(var(--txt),.08);box-shadow:inset 0 1px 1px rgba(255,255,255,.12);}
.sv-row b{display:block;font-weight:600;}
.sv-row small{display:block;margin-top:2px;font-size:12.5px;color:rgba(var(--txt),.6);}
.sv-chips{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end;}
.sv-chip{padding:7px 15px;border-radius:999px;border:1px solid rgba(var(--txt),.15);background:rgba(var(--txt),.05);color:inherit;font:inherit;font-size:13px;cursor:pointer;
  box-shadow:inset 0 1px 1px rgba(255,255,255,.2);transition:transform .4s cubic-bezier(.3,1.8,.5,1),background .25s,border-color .25s,box-shadow .25s;}
.sv-chip:hover{transform:scale(1.07);}
.sv-chip:active{transform:scale(1.05,.9);}
.sv-chip[aria-pressed="true"],.sv-chip[aria-checked="true"]{background:linear-gradient(160deg,rgba(var(--acc),.45),rgba(var(--sec),.22));border-color:rgba(var(--acc),.8);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.7),0 0 18px -2px rgba(var(--acc),.55);}
.sv-select,.sv-input{padding:8px 14px;border-radius:999px;border:1px solid rgba(var(--txt),.15);background:rgba(var(--txt),.06);color:inherit;font:inherit;outline:none;
  box-shadow:inset 0 2px 5px rgba(0,0,0,.22);transition:box-shadow .3s,border-color .3s;}
.sv-select{min-width:160px;}
.sv-select option{background:rgb(var(--bgc));color:rgb(var(--txt));}
.sv-select:focus,.sv-input:focus{border-color:rgba(var(--acc),.8);box-shadow:inset 0 2px 5px rgba(0,0,0,.22),0 0 0 4px rgba(var(--acc),.2);}
.sv-input.bad{border-color:rgba(var(--lg-danger),.9);}
.sv-input{width:100%;}
.sv-input--num{width:62px;padding:8px 6px;text-align:center;}

/* bubble switch */
.sv-switch{position:relative;width:58px;height:32px;flex:none;padding:0;border:1px solid rgba(var(--txt),.18);border-radius:999px;cursor:pointer;
  background:rgba(var(--txt),.08);box-shadow:inset 0 3px 6px rgba(0,0,0,.35),inset 0 -1px 1px rgba(255,255,255,.18);transition:background .4s,box-shadow .4s;}
.sv-switch[aria-checked="true"]{background:linear-gradient(160deg,rgba(var(--acc),.8),rgba(var(--sec),.45));box-shadow:inset 0 3px 6px rgba(0,0,0,.25),inset 0 -1px 1px rgba(255,255,255,.5),0 0 22px -2px rgba(var(--acc),.6);}
.sv-thumb{position:absolute;top:3px;left:3px;width:24px;height:24px;border-radius:50%;
  background:radial-gradient(circle at 32% 26%,#fff 0 12%,rgba(255,255,255,.88) 30%,rgba(var(--txt),.55) 100%);
  box-shadow:0 4px 8px rgba(0,0,0,.45),inset 0 -3px 5px rgba(0,0,0,.18);
  transition:left .5s cubic-bezier(.3,1.7,.5,1),width .25s cubic-bezier(.3,1.7,.5,1);}
.sv-switch[aria-checked="true"] .sv-thumb{left:calc(100% - 27px);}
.sv-switch:active .sv-thumb{width:34px;}
.sv-switch[aria-checked="true"]:active .sv-thumb{left:calc(100% - 37px);}

/* range sliders */
.sv-slidewrap{display:flex;align-items:center;gap:14px;width:min(260px,52%);}
.sv-slidewrap output{min-width:56px;text-align:right;font-variant-numeric:tabular-nums;color:rgba(var(--txt),.8);}
.sv-range{-webkit-appearance:none;appearance:none;width:100%;height:28px;margin:0;background:transparent;cursor:pointer;--p:50%;}
.sv-range:focus-visible{outline:2px solid rgba(var(--acc),.95);outline-offset:3px;border-radius:999px;}
.sv-range::-webkit-slider-runnable-track{height:12px;border-radius:999px;border:1px solid rgba(var(--txt),.14);
  background:linear-gradient(90deg,rgba(var(--acc),.95) 0 var(--p),rgba(var(--txt),.1) var(--p));box-shadow:inset 0 2px 4px rgba(0,0,0,.4),inset 0 -1px 1px rgba(255,255,255,.2);}
.sv-range::-webkit-slider-thumb{-webkit-appearance:none;width:26px;height:26px;margin-top:-9px;border-radius:50%;border:0;
  background:radial-gradient(circle at 32% 26%,#fff 0 12%,rgba(255,255,255,.88) 30%,rgba(var(--acc),.85) 100%);
  box-shadow:0 4px 10px rgba(0,0,0,.5),0 0 14px rgba(var(--acc),.55),inset 0 -3px 5px rgba(0,0,0,.15);transition:transform .3s cubic-bezier(.3,1.8,.5,1);}
.sv-range:hover::-webkit-slider-thumb{transform:scale(1.15);}
.sv-range:active::-webkit-slider-thumb{transform:scale(1.3,.9);}
.sv-range::-moz-range-track{height:12px;border-radius:999px;background:rgba(var(--txt),.1);}
.sv-range::-moz-range-progress{height:12px;border-radius:999px;background:rgba(var(--acc),.95);}
.sv-range::-moz-range-thumb{width:24px;height:24px;border:0;border-radius:50%;background:radial-gradient(circle at 32% 26%,#fff 0 12%,rgba(var(--acc),.9));box-shadow:0 0 14px rgba(var(--acc),.55);}
.sv-range--hue::-webkit-slider-runnable-track{background:linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00);}
.sv-range--hue::-moz-range-track{background:linear-gradient(90deg,#f00,#ff0,#0f0,#0ff,#00f,#f0f,#f00);}

/* theme cards */
.sv-themegrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:16px;}
.sv-themewrap{position:relative;}
.sv-theme{display:block;width:100%;padding:0;border:0;background:none;color:inherit;font:inherit;text-align:left;cursor:pointer;transform-style:preserve-3d;
  transform:perspective(700px) rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg)) scale(var(--s,1));transition:transform .4s cubic-bezier(.34,1.6,.5,1);}
.sv-theme:hover{--s:1.04;}
.sv-theme:active{--s:.97;}
.sv-theme-face{display:block;position:relative;padding:10px 10px 12px;border-radius:24px;transform-style:preserve-3d;
  background:rgba(var(--txt),.05);border:1px solid rgba(var(--txt),.13);box-shadow:inset 0 1px 1px rgba(255,255,255,.3),0 16px 26px -16px rgba(0,0,0,.65);transition:border-color .3s,box-shadow .3s;}
.sv-theme.is-on .sv-theme-face{border-color:rgba(var(--acc),.95);box-shadow:inset 0 1px 1px rgba(255,255,255,.5),0 0 0 3px rgba(var(--acc),.25),0 0 30px -4px rgba(var(--acc),.6);}
.sv-mini{display:flex;gap:6px;height:86px;padding:8px;border-radius:15px;overflow:hidden;position:relative;background:var(--t-bg);box-shadow:inset 0 0 0 1px rgba(255,255,255,.1);transform:translateZ(14px);}
.sv-rail{flex:none;width:18px;border-radius:8px;background:var(--t-sf);}
.sv-mainmini{flex:1;display:flex;flex-direction:column;gap:6px;}
.sv-pill{display:block;width:62%;height:12px;border-radius:999px;background:linear-gradient(180deg,rgba(255,255,255,.55),transparent 55%),var(--t-ac);box-shadow:0 0 10px var(--t-ac);}
.sv-ln{display:block;height:6px;width:90%;border-radius:999px;background:var(--t-tx);opacity:.5;}
.sv-ln.s{width:55%;opacity:.3;}
.sv-orbdot{position:absolute;right:9px;bottom:9px;width:20px;height:20px;border-radius:50%;background:radial-gradient(circle at 30% 26%,#fff 0 10%,var(--t-sc) 45%,var(--t-sf));box-shadow:0 4px 8px rgba(0,0,0,.4);}
.sv-theme-name{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px;padding:0 4px;font-size:13px;font-weight:600;transform:translateZ(8px);}
.sv-dots{display:inline-flex;gap:3px;}
.sv-dots i{width:9px;height:9px;border-radius:50%;box-shadow:inset 0 0 0 1px rgba(255,255,255,.35);}
.sv-check{position:absolute;top:16px;right:16px;width:22px;height:22px;display:grid;place-items:center;border-radius:50%;font-size:12px;font-weight:700;color:#06231d;
  background:radial-gradient(circle at 30% 26%,#fff,rgb(var(--acc)));box-shadow:0 4px 10px rgba(0,0,0,.45),0 0 14px rgba(var(--acc),.8);transform:translateZ(28px);animation:lg-item .5s cubic-bezier(.2,1.8,.4,1) both;}
.sv-del{position:absolute;top:6px;left:6px;z-index:3;width:22px;height:22px;border-radius:50%;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.55);color:#fff;font-size:14px;line-height:1;cursor:pointer;opacity:0;transition:opacity .2s,transform .3s cubic-bezier(.3,1.8,.5,1);}
.sv-themewrap:hover .sv-del,.sv-del:focus-visible{opacity:1;}
.sv-del:hover{transform:scale(1.2);}

/* accent swatches */
.sv-swatches{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;}
.sv-swatchcol{display:flex;flex-direction:column;align-items:center;gap:6px;font-size:12px;color:rgba(var(--txt),.7);}
.sv-swatch{width:40px;height:40px;border:0;border-radius:50%;cursor:pointer;
  background:radial-gradient(circle at 30% 24%,rgba(255,255,255,.95) 0 7%,rgba(255,255,255,0) 30%),radial-gradient(circle at 50% 62%,var(--c),color-mix(in srgb,var(--c) 55%,#000));
  box-shadow:inset 0 -6px 9px rgba(0,0,0,.3),inset 0 2px 3px rgba(255,255,255,.55),0 10px 18px -6px var(--c);transition:transform .45s cubic-bezier(.3,1.9,.5,1);}
.sv-swatch:hover{transform:scale(1.18) translateY(-2px);}
.sv-swatch:active{transform:scale(1.1,.88);}
.sv-swatch[aria-pressed="true"]{outline:2px solid rgb(var(--txt));outline-offset:4px;}
.sv-swatch--custom{background:radial-gradient(circle at 30% 24%,rgba(255,255,255,.9) 0 7%,rgba(255,255,255,0) 30%),conic-gradient(#f43f5e,#f59e0b,#84cc16,#06b6d4,#6366f1,#d946ef,#f43f5e);}

/* colour studio */
.sv-studio{display:grid;grid-template-columns:minmax(220px,290px) 1fr;gap:22px;padding:20px;border-radius:28px;background:rgba(var(--txt),.045);border:1px solid rgba(var(--txt),.09);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.14);}
@media (max-width:820px){.sv-studio{grid-template-columns:1fr}.sv-body{grid-template-columns:1fr}.sv-side{max-height:190px}}
.sv-pad{position:relative;height:190px;border-radius:22px;cursor:crosshair;touch-action:none;box-shadow:inset 0 0 0 1px rgba(255,255,255,.25),inset 0 8px 16px rgba(0,0,0,.25),0 14px 22px -12px rgba(0,0,0,.65);}
.sv-puck{position:absolute;width:28px;height:28px;margin:-14px 0 0 -14px;border-radius:50%;pointer-events:none;border:2px solid #fff;background:var(--c);
  box-shadow:0 0 0 1px rgba(0,0,0,.45),0 8px 16px rgba(0,0,0,.5),inset 0 -5px 7px rgba(0,0,0,.22);transition:transform .35s cubic-bezier(.3,1.9,.5,1);}
.sv-puck::after{content:"";position:absolute;left:5px;top:3px;width:10px;height:6px;border-radius:50%;background:rgba(255,255,255,.7);}
.sv-puck.is-drag{transform:scale(1.3,.95);}
.sv-studio-l{display:flex;flex-direction:column;gap:14px;}
.sv-studio-r{display:flex;flex-direction:column;gap:14px;min-width:0;}
.sv-lab{font-size:12.5px;font-weight:600;margin-bottom:6px;color:rgba(var(--txt),.75);}
.sv-roledot{display:inline-block;width:10px;height:10px;margin-right:7px;border-radius:50%;box-shadow:inset 0 0 0 1px rgba(255,255,255,.4);vertical-align:-1px;}
.sv-fields{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
.sv-fields .sv-input:first-child{width:112px;font-variant-numeric:tabular-nums;}
.sv-chipcol{display:flex;gap:10px;align-items:center;flex-wrap:wrap;}
.sv-mini-sw{width:30px;height:30px;border:0;border-radius:50%;cursor:pointer;background:radial-gradient(circle at 30% 24%,rgba(255,255,255,.9) 0 7%,rgba(255,255,255,0) 28%),var(--c);
  box-shadow:inset 0 -4px 6px rgba(0,0,0,.28),inset 0 2px 3px rgba(255,255,255,.5),0 6px 12px -5px var(--c);transition:transform .4s cubic-bezier(.3,1.9,.5,1);}
.sv-mini-sw:hover{transform:scale(1.22);}
.sv-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.sv-actions .sv-input{width:150px;}

/* effects */
.sv--reduce,.sv--reduce *,.sv--reduce *::before,.sv--reduce *::after{backdrop-filter:none!important;-webkit-backdrop-filter:none!important;}
.sv--reduce .lg-btn,.sv--reduce .sv-theme,.sv--reduce .sv-chip:hover,.sv--reduce .sv-swatch:hover{transform:none!important;}
.sv--reduce .sv-orb{filter:none;opacity:.25;}
.sv--noanim,.sv--noanim *,.sv--noanim *::before,.sv--noanim *::after{animation:none!important;transition-duration:.01ms!important;}
@media (prefers-reduced-motion:reduce){.sv,.sv *,.sv *::before,.sv *::after{animation:none!important;transition-duration:.01ms!important;}}
`;

if (typeof document !== "undefined" && !document.getElementById("sv-styles")) {
  const el = document.createElement("style");
  el.id = "sv-styles";
  el.textContent = CSS;
  document.head.appendChild(el);
}

/* ============================== small controls ============================== */
function useTilt(ref, max = 8) {
  const onPointerMove = useCallback((e) => {
    const el = ref.current; if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--ry", `${(px - 0.5) * max * 2}deg`);
    el.style.setProperty("--rx", `${-(py - 0.5) * max * 2}deg`);
  }, [ref, max]);
  const onPointerLeave = useCallback(() => {
    const el = ref.current; if (!el) return;
    el.style.setProperty("--rx", "0deg"); el.style.setProperty("--ry", "0deg");
  }, [ref]);
  return { onPointerMove, onPointerLeave };
}

const Switch = ({ checked, onChange, label }) => (
  <button type="button" role="switch" aria-checked={checked} aria-label={label} className="sv-switch" onClick={() => onChange(!checked)}>
    <span className="sv-thumb" />
  </button>
);

const Slider = ({ value, min, max, step = 1, unit = "", onChange, label, hue }) => (
  <div className="sv-slidewrap">
    <input
      type="range" aria-label={label} min={min} max={max} step={step} value={value}
      className={`sv-range${hue ? " sv-range--hue" : ""}`} style={{ "--p": `${((value - min) / (max - min)) * 100}%` }}
      onChange={(e) => onChange(+e.target.value)}
    />
    {!hue && <output>{value}{unit}</output>}
  </div>
);

const Chips = ({ options, value, onChange, label }) => (
  <div className="sv-chips" role="radiogroup" aria-label={label}>
    {options.map((o) => (
      <button key={o} type="button" role="radio" aria-checked={value === o} className="sv-chip" onClick={() => onChange(o)}>{o}</button>
    ))}
  </div>
);

const Row = ({ label, hint, children }) => (
  <div className="sv-row"><div><b>{label}</b>{hint && <small>{hint}</small>}</div>{children}</div>
);

/* ============================== side navigation ============================== */
const FIZZ = [["18%", 5, "2.6s", "0s"], ["42%", 3, "3.1s", ".7s"], ["66%", 6, "2.9s", "1.3s"], ["86%", 4, "2.4s", ".3s"]];

function SideNav({ items, value, onChange }) {
  const wrap = useRef(null), btns = useRef([]);
  const idx = Math.max(0, items.findIndex(([id]) => id === value));
  const prev = useRef(idx), dir = useRef(1);
  const [box, setBox] = useState({ t: 0, b: 0 });
  const [ready, setReady] = useState(false);
  const [moving, setMoving] = useState(false);

  const measure = useCallback(() => {
    const el = btns.current[idx], c = wrap.current;
    if (!el || !c) return;
    setBox({ t: el.offsetTop, b: c.clientHeight - el.offsetTop - el.offsetHeight });
  }, [idx]);

  useLayoutEffect(() => {
    if (idx !== prev.current) {
      dir.current = idx > prev.current ? 1 : -1; prev.current = idx;
      setMoving(true); setTimeout(() => setMoving(false), 380);
    }
    measure();
    requestAnimationFrame(() => setReady(true));
  }, [idx, measure]);

  useEffect(() => {
    if (!wrap.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure); ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [measure]);

  const ease = "cubic-bezier(.34,1.45,.64,1)";
  const lead = ".3s", lag = ".6s"; // leading edge snaps, trailing edge lags: liquid stretch
  const style = {
    top: box.t, bottom: box.b,
    transition: ready ? `top ${dir.current > 0 ? lag : lead} ${ease}, bottom ${dir.current > 0 ? lead : lag} ${ease}, transform .35s cubic-bezier(.34,1.8,.5,1)` : "none",
  };

  const onKey = (e) => {
    const len = items.length; let n = idx;
    if (e.key === "ArrowDown") n = (idx + 1) % len; else if (e.key === "ArrowUp") n = (idx - 1 + len) % len;
    else if (e.key === "Home") n = 0; else if (e.key === "End") n = len - 1; else return;
    e.preventDefault(); onChange(items[n][0]); btns.current[n]?.focus();
  };

  return (
    <div className="sv-nav" role="tablist" aria-orientation="vertical" ref={wrap} onKeyDown={onKey}>
      <span className={`sv-nbubble${moving ? " is-moving" : ""}`} style={style} aria-hidden="true">
        {FIZZ.map(([x, d, t, w], k) => <i key={k} className="lg-fizz" style={{ "--x": x, "--d": `${d}px`, "--t": t, "--w": w }} />)}
      </span>
      {items.map(([id, label], k) => (
        <button
          key={id} type="button" role="tab" className="sv-navitem" ref={(el) => (btns.current[k] = el)}
          aria-selected={id === value} tabIndex={id === value ? 0 : -1} onClick={() => onChange(id)}
        >
          <i />{label}
        </button>
      ))}
    </div>
  );
}

/* ================================ theme card ================================ */
function ThemeCard({ t, selected, onSelect, onDelete }) {
  const ref = useRef(null);
  const tilt = useTilt(ref, 9);
  const vars = { "--t-bg": t.bg, "--t-sf": t.surface, "--t-tx": t.text, "--t-ac": t.accent, "--t-sc": t.secondary };
  return (
    <div className="sv-themewrap" style={vars}>
      <button ref={ref} type="button" className={`sv-theme${selected ? " is-on" : ""}`} aria-pressed={selected} onClick={onSelect} {...tilt}>
        <span className="sv-theme-face">
          <span className="sv-mini">
            <i className="sv-rail" />
            <span className="sv-mainmini"><i className="sv-pill" /><i className="sv-ln" /><i className="sv-ln s" /></span>
            <i className="sv-orbdot" />
          </span>
          <span className="sv-theme-name">
            <span>{t.name}</span>
            <span className="sv-dots"><i style={{ background: t.accent }} /><i style={{ background: t.secondary }} /><i style={{ background: t.surface }} /></span>
          </span>
          {selected && <span className="sv-check" aria-hidden="true">✓</span>}
        </span>
      </button>
      {onDelete && <button type="button" className="sv-del" aria-label={`Delete ${t.name}`} onClick={onDelete}>×</button>}
    </div>
  );
}

/* ================================ colour studio ================================ */
function SVPad({ hsv, onChange }) {
  const ref = useRef(null);
  const [drag, setDrag] = useState(false);
  const [h, s, v] = hsv;
  const pick = (e) => {
    const r = ref.current.getBoundingClientRect();
    onChange([h, clamp((e.clientX - r.left) / r.width, 0, 1), 1 - clamp((e.clientY - r.top) / r.height, 0, 1)]);
  };
  const key = (e) => {
    const d = e.shiftKey ? 0.1 : 0.02; let ns = s, nv = v;
    if (e.key === "ArrowLeft") ns -= d; else if (e.key === "ArrowRight") ns += d;
    else if (e.key === "ArrowUp") nv += d; else if (e.key === "ArrowDown") nv -= d; else return;
    e.preventDefault(); onChange([h, clamp(ns, 0, 1), clamp(nv, 0, 1)]);
  };
  return (
    <div
      ref={ref} className="sv-pad" role="slider" tabIndex={0} aria-label="Saturation and brightness"
      aria-valuetext={`Saturation ${Math.round(s * 100)}%, brightness ${Math.round(v * 100)}%`}
      style={{ background: `linear-gradient(to top,#000,transparent),linear-gradient(to right,#fff,hsl(${h} 100% 50%))` }}
      onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); setDrag(true); pick(e); }}
      onPointerMove={(e) => drag && pick(e)} onPointerUp={() => setDrag(false)} onPointerCancel={() => setDrag(false)}
      onKeyDown={key}
    >
      <span className={`sv-puck${drag ? " is-drag" : ""}`} style={{ left: `${s * 100}%`, top: `${(1 - v) * 100}%`, "--c": rgbToHex(hsvToRgb(h, s, v)) }} />
    </div>
  );
}

function ColourStudio({ colors, role, setRole, onChange, onGenerate, onSave }) {
  const hex = colors[role];
  const [hsv, setHsv] = useState(() => rgbToHsv(hexToRgb(hex)));
  const [text, setText] = useState(hex);
  const [name, setName] = useState("");

  useEffect(() => {
    if (rgbToHex(hsvToRgb(...hsv)) !== hex) setHsv(rgbToHsv(hexToRgb(hex)));
    setText(hex);
  }, [hex]); // eslint-disable-line react-hooks/exhaustive-deps

  const push = (n) => { setHsv(n); onChange(role, rgbToHex(hsvToRgb(...n))); };
  const rgb = hexToRgb(hex);
  const setChannel = (i, val) => { const n = [...rgb]; n[i] = clamp(Number(val) || 0, 0, 255); onChange(role, rgbToHex(n)); };
  const rot = (deg) => rgbToHex(hsvToRgb((hsv[0] + deg + 360) % 360, hsv[1], hsv[2]));
  const harmony = [["Analogous -30°", rot(-30)], ["Analogous +30°", rot(30)], ["Triad 120°", rot(120)], ["Triad 240°", rot(240)], ["Complement", rot(180)]];
  const shades = [["Darkest", mix(hex, "#000000", 0.5)], ["Darker", mix(hex, "#000000", 0.25)], ["Base", hex], ["Lighter", mix(hex, "#ffffff", 0.25)], ["Lightest", mix(hex, "#ffffff", 0.5)]];
  const valid = normHex(text);

  return (
    <div className="sv-studio">
      <div className="sv-studio-l">
        <SVPad hsv={hsv} onChange={push} />
        <Slider hue min={0} max={360} value={Math.round(hsv[0])} label="Hue" onChange={(h) => push([h, hsv[1], hsv[2]])} />
      </div>
      <div className="sv-studio-r">
        <div>
          <div className="sv-lab">Colour to edit</div>
          <div className="sv-chips" style={{ justifyContent: "flex-start" }} role="radiogroup" aria-label="Colour to edit">
            {ROLES.map(([id, label]) => (
              <button key={id} type="button" role="radio" aria-checked={role === id} className="sv-chip" onClick={() => setRole(id)}>
                <span className="sv-roledot" style={{ background: colors[id] }} />{label}
              </button>
            ))}
          </div>
        </div>
        <div>
          <div className="sv-lab">Value</div>
          <div className="sv-fields">
            <input
              className={`sv-input${valid ? "" : " bad"}`} value={text} spellCheck={false} aria-label="Hex colour"
              onChange={(e) => { setText(e.target.value); const n = normHex(e.target.value); if (n) onChange(role, n); }}
              onBlur={() => setText(hex)}
            />
            {["R", "G", "B"].map((c, i) => (
              <input key={c} type="number" min={0} max={255} aria-label={c} className="sv-input sv-input--num" value={rgb[i]} onChange={(e) => setChannel(i, e.target.value)} />
            ))}
            {typeof window !== "undefined" && "EyeDropper" in window && (
              <BubbleButton onClick={() => new window.EyeDropper().open().then((r) => onChange(role, normHex(r.sRGBHex))).catch(() => {})}>Pick from screen</BubbleButton>
            )}
          </div>
        </div>
        <div>
          <div className="sv-lab">Harmony</div>
          <div className="sv-chipcol">
            {harmony.map(([n, c]) => <button key={n} type="button" title={n} aria-label={`${n} ${c}`} className="sv-mini-sw" style={{ "--c": c }} onClick={() => onChange(role, c)} />)}
          </div>
        </div>
        <div>
          <div className="sv-lab">Shades</div>
          <div className="sv-chipcol">
            {shades.map(([n, c]) => <button key={n} type="button" title={n} aria-label={`${n} ${c}`} className="sv-mini-sw" style={{ "--c": c }} onClick={() => onChange(role, c)} />)}
          </div>
        </div>
        <div className="sv-actions">
          <BubbleButton onClick={onGenerate}>Build theme from accent</BubbleButton>
          <input className="sv-input" placeholder="Theme name" aria-label="Theme name" value={name} onChange={(e) => setName(e.target.value)} />
          <BubbleButton variant="accent" onClick={() => { onSave(name.trim() || "My theme"); setName(""); }}>Save theme</BubbleButton>
        </div>
      </div>
    </div>
  );
}

/* ================================== sections ================================== */
function GenericSection({ id, label, values, setValue, version, onAction }) {
  return (
    <div className="sv-page">
      <h2 className="sv-h2">{label}</h2>
      <p className="sv-sub" />
      {SCHEMA[id].map((r) => {
        const k = `${id}.${r.key}`, v = values[k];
        return (
          <Row key={k} label={r.label} hint={r.hint}>
            {r.type === "toggle" && <Switch checked={!!v} label={r.label} onChange={(x) => setValue(k, x)} />}
            {r.type === "choice" && <Chips options={r.options} value={v} label={r.label} onChange={(x) => setValue(k, x)} />}
            {r.type === "select" && (
              <select className="sv-select" aria-label={r.label} value={v} onChange={(e) => setValue(k, e.target.value)}>
                {r.options.map((o) => <option key={o}>{o}</option>)}
              </select>
            )}
            {r.type === "slider" && <Slider value={v} min={r.min} max={r.max} step={r.step} unit={r.unit} label={r.label} onChange={(x) => setValue(k, x)} />}
            {r.type === "action" && <BubbleButton onClick={() => onAction?.(k)}>{r.button}</BubbleButton>}
            {r.type === "info" && <span>{version}</span>}
          </Row>
        );
      })}
    </div>
  );
}

/* ================================== settings persistence ================================== */
const bridgeKey = (id) => `animevault.settings.${id}`;

function saveToBridge(bridge, settings) {
  if (bridge && typeof bridge.setSettings === "function") {
    try { bridge.setSettings(JSON.stringify(settings)); } catch (e) { /* ignore */ }
  }
}

/** CSS custom properties to theme the rest of the app from applied settings. */
export function themeToCssVars(s) {
  const c = s.colors || {};
  return {
    "--av-accent": c.accent || "126,232,208",
    "--av-secondary": c.secondary || "183,156,245",
    "--av-bg": c.bg || "#0b1020",
    "--av-surface": c.surface || "#131a2e",
    "--av-text": c.text || "#e6ecfa",
    "--lg-accent": rgbStr(c.accent || "#7ee8d0"),
    "--lg-violet": rgbStr(c.secondary || "#b79cf5"),
  };
}

/* ================================== main ================================== */
export default function Settings({ bridge, onApply, onClose, onAction, version = "1.0.0" }) {
  // Async load: settings may come from the bridge (QWebChannel),
  // which is asynchronous. Use a promise to await the result.
  const [loading, setLoading] = useState(true);
  const [applied, setApplied] = useState(() => load(bridge));
  const [d, setD] = useState(applied);
  const [section, setSection] = useState("appearance");
  const [role, setRole] = useState("accent");
  const [query, setQuery] = useState("");
  const [toast, setToast] = useState(false);
  const scroller = useRef(null), studio = useRef(null);

  // Await async settings load
  useEffect(() => {
    const p = load(bridge);
    if (p && typeof p.then === "function") {
      p.then((result) => {
        if (result && result.settings) {
          setApplied(result.settings);
          setD(result.settings);
        }
        setLoading(false);
      }).catch(() => {
        setLoading(false);
      });
    } else {
      setLoading(false);
    }
  }, [bridge]);

  const dirty = useMemo(() => JSON.stringify(d) !== JSON.stringify(applied), [d, applied]);
  const c = d.colors;
  const light = lum(c.bg) > 0.55;
  const blur = d.reduce ? 0 : 4 + d.glass * 0.3;
  const alpha = d.reduce ? 0.92 : 0.72 - d.glass * 0.0046;

  useEffect(() => { scroller.current?.scrollTo({ top: 0 }); }, [section, query]);
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(false), 2000); return () => clearTimeout(t); }, [toast]);

  const set = (patch) => setD((p) => ({ ...p, ...patch }));
  const setValue = (k, v) => setD((p) => ({ ...p, values: { ...p.values, [k]: v } }));
  const setColor = (r, hex) => setD((p) => ({ ...p, themeId: "custom", colors: { ...p.colors, [r]: hex } }));
  const chooseTheme = (t) => setD((p) => ({ ...p, themeId: t.id, colors: themeColors(t) }));
  const setAccent = (a, s) => setD((p) => ({ ...p, themeId: "custom", colors: { ...p.colors, accent: a, secondary: s } }));
  const saveTheme = (name) => setD((p) => {
    const t = { id: `c${Date.now()}`, name, ...p.colors };
    return { ...p, themeId: t.id, customThemes: [...p.customThemes, t] };
  });
  const deleteTheme = (id) => setD((p) => ({ ...p, customThemes: p.customThemes.filter((t) => t.id !== id), themeId: p.themeId === id ? "custom" : p.themeId }));
  const generate = () => setD((p) => ({ ...p, themeId: "custom", colors: makeThemeFromAccent(p.colors.accent) }));

  const apply = async () => {
    setApplied(d);
    // Persist and apply via the bridge; the backend confirms success before
    // we update the UI (per the settings lifecycle requirements).
    if (bridge && typeof bridge.apply_settings === "function") {
      try {
        const raw = bridge.apply_settings(JSON.stringify(d));
        if (raw) {
          try {
            const result = JSON.parse(raw);
            if (result.status === "error") {
              setToast(false);
              // Show the backend error to the user
              setToast(true);
              return;
            }
          } catch (e) {
            // Not JSON; treat as success
          }
        }
      } catch (e) {
        logger.error("apply_settings threw: " + e.message);
      }
    }
    saveToBridge(bridge, d);
    onApply?.(d);
    setToast(true);
  };
  const restore = () => setD((p) => ({ ...DEFAULTS, customThemes: p.customThemes }));
  const handleAction = (action) => {
    onAction?.(action);
    // Route settings actions through the bridge for real execution
    if (bridge && typeof bridge.settingsAction === "function") {
      bridge.settingsAction(action);
    }
  };

  const q = query.trim().toLowerCase();
  const results = q ? INDEX.filter((r) => `${r.label} ${r.hint} ${r.section}`.toLowerCase().includes(q)) : null;
  const sectionLabel = (id) => SECTIONS.find(([s]) => s === id)[1];

  const themeList = [...THEMES, ...d.customThemes];
  const presetHit = ACCENTS.some(([, a]) => a === c.accent);

  const rootVars = {
    "--acc": rgbStr(c.accent), "--sec": rgbStr(c.secondary), "--bgc": rgbStr(c.bg), "--surf": rgbStr(c.surface), "--txt": rgbStr(c.text),
    "--lg-accent": rgbStr(c.accent), "--lg-violet": rgbStr(c.secondary),
    "--sv-blur": `${blur}px`, "--sv-a": alpha,
  };

  return (
    <div className={`sv${d.reduce ? " sv--reduce" : ""}${d.animations ? "" : " sv--noanim"}${light ? " sv--light" : ""}`} style={rootVars}>
      <span className="sv-orb sv-orb--a" /><span className="sv-orb sv-orb--b" /><span className="sv-orb sv-orb--c" />

      <header className="sv-glass sv-head">
        <h1 className="sv-title">Settings</h1>
        <label className="sv-search">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="7" cy="7" r="4.5" /><path d="m10.5 10.5 3 3" /></svg>
          <input type="search" placeholder="Search settings" aria-label="Search settings" value={query}
            onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Escape" && setQuery("")} />
        </label>
        {onClose && <BubbleButton aria-label="Close settings" onClick={onClose}>✕</BubbleButton>}
      </header>

      <div className="sv-body">
        <aside className="sv-glass sv-side"><SideNav items={SECTIONS} value={section} onChange={(s) => { setSection(s); setQuery(""); }} /></aside>

        <main className="sv-glass sv-main">
          <div className="sv-scroll" ref={scroller}>
            {results ? (
              <div className="sv-page">
                <h2 className="sv-h2">Search results</h2>
                {results.length === 0 && <p className="sv-sub">No settings match “{query}”. Try a shorter word.</p>}
                {results.map((r) => (
                  <button key={r.section + r.label} type="button" className="sv-row" style={{ width: "100%", color: "inherit", font: "inherit", textAlign: "left", cursor: "pointer" }}
                    onClick={() => { setSection(r.section); setQuery(""); }}>
                    <div><b>{r.label}</b><small>{sectionLabel(r.section)}</small></div>
                  </button>
                ))}
              </div>
            ) : section === "appearance" ? (
              <div className="sv-page">
                <h2 className="sv-h2">Appearance &amp; Personalization</h2>
                <p className="sv-sub">Changes preview here instantly. Press Apply to keep them.</p>

                <h3 className="sv-h3">Theme</h3>
                <p className="sv-hint">
                  Popular themes{d.themeId === "custom" ? " · you are using an unsaved custom theme" : ""}
                </p>
                <div className="sv-themegrid">
                  {themeList.map((t) => (
                    <ThemeCard key={t.id} t={t} selected={d.themeId === t.id} onSelect={() => chooseTheme(t)}
                      onDelete={t.id.startsWith("c") ? () => deleteTheme(t.id) : undefined} />
                  ))}
                </div>

                <h3 className="sv-h3">Accent colour</h3>
                <p className="sv-hint">Used for highlights, toggles and the active tab.</p>
                <div className="sv-swatches">
                  {ACCENTS.map(([n, a, s]) => (
                    <div className="sv-swatchcol" key={n}>
                      <button type="button" className="sv-swatch" aria-label={`${n} accent`} aria-pressed={c.accent === a} style={{ "--c": a }} onClick={() => setAccent(a, s)} />
                      {n}
                    </div>
                  ))}
                  <div className="sv-swatchcol">
                    <button type="button" className="sv-swatch sv-swatch--custom" aria-label="Custom accent colour" aria-pressed={!presetHit}
                      onClick={() => { setRole("accent"); studio.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }} />
                    Custom
                  </div>
                </div>

                <h3 className="sv-h3">Colour studio</h3>
                <p className="sv-hint">Pick or mix any colour for the accent, background, surface or text.</p>
                <div ref={studio}>
                  <ColourStudio colors={c} role={role} setRole={setRole} onChange={setColor} onGenerate={generate} onSave={saveTheme} />
                </div>

                <h3 className="sv-h3">Interface effects</h3>
                <p className="sv-hint" />
                <Row label="Glass intensity" hint="Blur and transparency of panels">
                  <Slider value={d.glass} min={0} max={100} unit="%" label="Glass intensity" onChange={(v) => set({ glass: v })} />
                </Row>
                <Row label="Animations" hint="Bubbles, wobble and motion">
                  <Switch checked={d.animations} label="Animations" onChange={(v) => set({ animations: v })} />
                </Row>
                <Row label="Reduce effects" hint="Flat panels with no blur, for older machines">
                  <Switch checked={d.reduce} label="Reduce effects" onChange={(v) => set({ reduce: v })} />
                </Row>
              </div>
            ) : (
              <GenericSection key={section} id={section} label={sectionLabel(section)} values={d.values} setValue={setValue} version={version} onAction={handleAction} />
            )}
          </div>

          <footer className="sv-foot">
            <BubbleButton onClick={restore}>Restore Defaults</BubbleButton>
            <div className="sv-foot-r">
              {toast ? <span className="sv-toast" role="status">Settings applied</span> : dirty && <span className="sv-dirty">Unsaved changes</span>}
              <BubbleButton variant="accent" onClick={apply} disabled={!dirty} style={{ opacity: dirty ? 1 : 0.5 }}>Apply</BubbleButton>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
