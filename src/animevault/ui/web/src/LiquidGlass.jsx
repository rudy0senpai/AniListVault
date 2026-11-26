import React, {
  forwardRef, useCallback, useEffect, useId, useLayoutEffect, useRef, useState,
} from "react";

/* ------------------------------------------------------------------ *
 *  Bubble Liquid Glass UI for AnimeVault
 *  Exports: BubbleTabs, BubbleMenu, BubbleButton  (default: <Demo />)
 *  Styles inject themselves once; no CSS file needed.
 *  Re-theme by overriding --lg-accent / --lg-violet / --lg-danger
 *  (comma-separated RGB) on any ancestor.
 * ------------------------------------------------------------------ */

const CSS = `
.lg{--lg-accent:126,232,208;--lg-violet:183,156,245;--lg-danger:255,125,145;}

/* ---------- shared glass layer (pseudo so children can float in 3D) ---------- */
.lg-btn,.lg-tabs{position:relative;transform-style:preserve-3d;}
.lg-btn::before,.lg-tabs::before{
  content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:
    radial-gradient(150px circle at var(--mx,50%) var(--my,0%),rgba(255,255,255,.30),transparent 62%),
    linear-gradient(145deg,rgba(var(--tint,255,255,255),calc(var(--ta,.08) + .10)),rgba(var(--tint,255,255,255),.02) 48%,rgba(var(--tint,255,255,255),var(--ta,.08)));
  backdrop-filter:blur(14px) saturate(1.8) brightness(1.1);
  -webkit-backdrop-filter:blur(14px) saturate(1.8) brightness(1.1);
  border:1px solid rgba(255,255,255,.16);
  box-shadow:
    inset 0 1px 1px rgba(255,255,255,.6),
    inset 0 -9px 16px rgba(var(--tint,255,255,255),.07),
    inset 0 -1px 1px rgba(var(--lg-violet),.45),
    0 12px 24px -10px rgba(0,0,0,.7),
    0 0 var(--glow,0px) -4px rgba(var(--tint,255,255,255),.6);
}

/* ---------- bubble button ---------- */
.lg-btn{
  display:inline-flex;align-items:center;gap:8px;padding:10px 18px;border:0;background:none;
  border-radius:999px;font:inherit;font-weight:500;color:rgba(226,234,250,.92);cursor:pointer;
  transform:perspective(700px) rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg)) scale3d(var(--sx,1),var(--sy,1),1);
  transition:transform .4s cubic-bezier(.34,1.7,.5,1),color .25s;
}
.lg-btn:hover{--sx:1.05;--sy:1.05;color:#fff;}
.lg-btn:active{--sx:1.08;--sy:.88;transition-duration:.12s;}
.lg-btn:focus-visible,.lg-tab:focus-visible,.lg-item:focus-visible{outline:2px solid rgba(var(--lg-accent),.9);outline-offset:3px;}
.lg-btn::after{
  content:"";position:absolute;left:12%;right:12%;top:3px;height:42%;border-radius:999px;pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.55),rgba(255,255,255,0));opacity:.5;transform:translateZ(8px);
}
.lg-label{position:relative;display:inline-flex;align-items:center;gap:8px;transform:translateZ(16px);}
.lg-btn--accent{--tint:var(--lg-accent);--ta:.26;--glow:26px;color:#eafff9;}
.lg-btn--danger{--tint:var(--lg-danger);--ta:.30;--glow:22px;color:#ffe3e8;}
.lg-chev{width:12px;height:12px;transition:transform .35s cubic-bezier(.3,1.8,.5,1);}
.lg-btn[aria-expanded="true"] .lg-chev{transform:rotate(180deg);}

/* ---------- tabs with liquid bubble ---------- */
.lg-tabs{
  display:inline-flex;gap:2px;padding:6px;border-radius:999px;
  transform:perspective(900px) rotateX(var(--rx,0deg)) rotateY(var(--ry,0deg));
  transition:transform .45s cubic-bezier(.2,1.2,.4,1);
}
.lg-tab{
  position:relative;z-index:2;padding:10px 22px;border:0;background:none;border-radius:999px;
  font:inherit;font-weight:500;color:rgba(204,214,236,.7);cursor:pointer;
  transform:translateZ(18px);transition:color .3s,text-shadow .3s;
}
.lg-tab:hover{color:#fff;}
.lg-tab[aria-selected="true"]{color:#fff;text-shadow:0 0 14px rgba(var(--lg-accent),.9);}
.lg-bubble{
  position:absolute;top:6px;bottom:6px;z-index:1;pointer-events:none;overflow:hidden;border-radius:999px;
  background:
    radial-gradient(120% 150% at 28% 8%,rgba(255,255,255,.6),rgba(255,255,255,0) 40%),
    linear-gradient(160deg,rgba(var(--lg-accent),.58),rgba(var(--lg-violet),.34));
  backdrop-filter:blur(8px) saturate(1.9);-webkit-backdrop-filter:blur(8px) saturate(1.9);
  border:1px solid rgba(255,255,255,.35);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.85),inset 0 -8px 14px rgba(var(--lg-accent),.4),0 10px 26px -6px rgba(var(--lg-accent),.6);
  transform:translateZ(8px);
  animation:lg-morph 5s ease-in-out infinite;
}
.lg-bubble.is-moving{transform:translateZ(8px) scale(1.04,.86);}
.lg-fizz{
  position:absolute;bottom:-8px;left:var(--x);width:var(--d);height:var(--d);border-radius:50%;opacity:0;
  background:radial-gradient(circle at 30% 30%,rgba(255,255,255,.95),rgba(255,255,255,.18) 60%,transparent 72%);
  animation:lg-rise var(--t) linear var(--w) infinite;
}
@keyframes lg-rise{0%{transform:translateY(0) scale(.6);opacity:0}18%{opacity:.9}100%{transform:translateY(-46px) scale(1.15);opacity:0}}
@keyframes lg-morph{
  0%,100%{border-radius:50% 50% 50% 50%/50% 50% 50% 50%}
  33%{border-radius:46% 54% 52% 48%/56% 52% 48% 44%}
  66%{border-radius:54% 46% 48% 52%/46% 56% 44% 54%}
}

/* ---------- dropdown menu ---------- */
.lg-menuwrap{position:relative;display:inline-block;}
.lg-menu{
  position:absolute;z-index:50;top:calc(100% + 12px);left:0;min-width:248px;padding:8px;border-radius:28px;
  background:linear-gradient(150deg,rgba(255,255,255,.16),rgba(255,255,255,.03) 40%),rgba(12,18,34,.62);
  backdrop-filter:blur(26px) saturate(1.9);-webkit-backdrop-filter:blur(26px) saturate(1.9);
  border:1px solid rgba(255,255,255,.18);
  box-shadow:inset 0 1px 1px rgba(255,255,255,.5),inset 0 -14px 26px rgba(var(--lg-violet),.09),0 34px 60px -16px rgba(0,0,0,.8);
  transform-origin:30px -12px;animation:lg-pop .55s cubic-bezier(.2,1.5,.35,1) both;
}
.lg-menu.is-closing{animation:lg-unpop .14s ease-in both;}
.lg-menu::before{
  content:"";position:absolute;left:18px;right:18px;top:4px;height:26px;border-radius:999px;pointer-events:none;
  background:linear-gradient(180deg,rgba(255,255,255,.22),rgba(255,255,255,0));
}
@keyframes lg-pop{
  from{opacity:0;transform:perspective(900px) translateY(-10px) rotateX(-38deg) scale(.35)}
  55%{opacity:1}
  to{opacity:1;transform:perspective(900px) translateY(0) rotateX(0deg) scale(1)}
}
@keyframes lg-unpop{to{opacity:0;transform:perspective(900px) translateY(-6px) rotateX(-20deg) scale(.7)}}
.lg-item{
  position:relative;display:flex;align-items:center;gap:12px;width:100%;padding:11px 16px;border:0;background:none;
  border-radius:999px;font:inherit;text-align:left;color:rgba(232,238,250,.92);cursor:pointer;
  animation:lg-item .5s cubic-bezier(.2,1.6,.4,1) calc(var(--i) * 26ms + 70ms) backwards;
  transition:transform .3s cubic-bezier(.3,1.7,.5,1);
}
.lg-item > *{position:relative;}
.lg-item::before{
  content:"";position:absolute;inset:0;border-radius:inherit;opacity:0;transition:opacity .2s;
  background:
    radial-gradient(130px circle at var(--mx,50%) var(--my,50%),rgba(var(--lg-accent),.4),rgba(var(--lg-accent),.08) 70%),
    linear-gradient(rgba(255,255,255,.07),rgba(255,255,255,0));
  box-shadow:inset 0 1px 1px rgba(255,255,255,.5),inset 0 -5px 10px rgba(var(--lg-accent),.2);
}
.lg-item:hover,.lg-item:focus-visible{transform:translateX(4px) scale(1.02);color:#fff;}
.lg-item:hover::before,.lg-item:focus-visible::before{opacity:1;}
.lg-bead{
  width:9px;height:9px;flex:none;border-radius:50%;
  background:radial-gradient(circle at 30% 28%,#fff 0 12%,rgba(var(--lg-accent),.95) 42%,rgba(var(--lg-violet),.6));
  box-shadow:0 0 10px rgba(var(--lg-accent),.55);transition:transform .35s cubic-bezier(.3,1.9,.5,1);
}
.lg-item:hover .lg-bead{transform:scale(1.55);}
.lg-item--danger{color:#ffc2cc;}
.lg-item--danger .lg-bead{background:radial-gradient(circle at 30% 28%,#fff 0 12%,rgba(var(--lg-danger),.95) 45%,rgba(var(--lg-danger),.5));box-shadow:0 0 10px rgba(var(--lg-danger),.55);}
.lg-div{height:1px;margin:6px 18px;background:linear-gradient(90deg,transparent,rgba(255,255,255,.28),transparent);}
@keyframes lg-item{from{opacity:0;transform:translateY(-8px) scale(.7)}to{opacity:1;transform:none}}

@media (prefers-reduced-motion:reduce){
  .lg,.lg *,.lg::before,.lg *::before,.lg *::after{animation:none!important;transition-duration:.01ms!important;}
}
`;

if (typeof document !== "undefined" && !document.getElementById("lg-styles")) {
  const el = document.createElement("style");
  el.id = "lg-styles";
  el.textContent = CSS;
  document.head.appendChild(el);
}

/* ---------- pointer tilt + specular tracking ---------- */
function useTilt(ref, max = 8) {
  const onPointerMove = useCallback((e) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    el.style.setProperty("--mx", `${px * 100}%`);
    el.style.setProperty("--my", `${py * 100}%`);
    el.style.setProperty("--ry", `${(px - 0.5) * max * 2}deg`);
    el.style.setProperty("--rx", `${-(py - 0.5) * max * 2}deg`);
  }, [ref, max]);
  const onPointerLeave = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    el.style.setProperty("--rx", "0deg");
    el.style.setProperty("--ry", "0deg");
    el.style.setProperty("--my", "0%");
  }, [ref]);
  return { onPointerMove, onPointerLeave };
}

/* ---------- BubbleButton ---------- */
export const BubbleButton = forwardRef(function BubbleButton(
  { variant = "glass", icon, children, className = "", ...rest }, fwd
) {
  const local = useRef(null);
  const setRef = useCallback((n) => {
    local.current = n;
    if (typeof fwd === "function") fwd(n); else if (fwd) fwd.current = n;
  }, [fwd]);
  const tilt = useTilt(local, 10);
  const v = variant === "glass" ? "" : ` lg-btn--${variant}`;
  return (
    <button type="button" {...rest} {...tilt} ref={setRef} className={`lg lg-btn${v} ${className}`}>
      <span className="lg-label">{icon}{children}</span>
    </button>
  );
});

const Chevron = () => (
  <svg className="lg-chev" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.5 4.5 6 8l3.5-3.5" />
  </svg>
);

/* ── shared dropdown controller ───────────────────────────────
   Single-open controller: only one BubbleMenu is open at a time.
   Notifies the native overlay (via onOpenChange callback) when a
   menu opens or closes. Stale-timer protection via closing flag. */
let managedMenu = null;
let disposing = false;

export function registerMenu(id, closeMenu, onOpen, itemCount) {
  if (disposing) return;
  if (managedMenu && managedMenu.id !== id) {
    managedMenu.closeMenu(false);
  }
  managedMenu = { id, closeMenu, onOpen, itemCount };
  onOpen?.(true, itemCount);
}

export function unregisterMenu(id) {
  if (managedMenu?.id === id) {
    managedMenu.onOpen?.(false, 0);
    managedMenu = null;
  }
}

export function closeAllMenus() {
  managedMenu?.closeMenu(false);
  managedMenu = null;
}

export function disposeMenus() {
  disposing = true;
  managedMenu = null;
}
export function BubbleMenu({ label, items, variant = "glass", icon, onOpenChange }) {
  const [open, setOpen] = useState(false);
  const [closing, setClosing] = useState(false);
  const wrap = useRef(null);
  const trigger = useRef(null);
  const list = useRef(null);
  const id = useId();

  const close = useCallback((refocus) => {
    setClosing(true);
    onOpenChange?.(false, 0);
    setTimeout(() => {
      setOpen(false);
      setClosing(false);
      if (refocus) trigger.current?.focus();
    }, 140);
  }, [onOpenChange]);

  // Register only from the effect so component state is the sole trigger.
  // The global controller keeps the active menu's close callback and closes
  // it before another menu registers.
  const itemCount = items.filter((item) => !item.divider).length;
  useEffect(() => {
    if (open) registerMenu(id, close, onOpenChange, itemCount);
    else unregisterMenu(id);
    return () => unregisterMenu(id);
  }, [id, open, close, onOpenChange, itemCount]);

  // Outside-click dismissal
  useEffect(() => {
    if (!open) return;
    const down = (e) => {
      if (!wrap.current?.contains(e.target)) {
        close(false);
      }
    };
    document.addEventListener("pointerdown", down);
    return () => document.removeEventListener("pointerdown", down);
  }, [open, close]);

  // Focus the first menu item when opened
  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => list.current?.querySelector('[role="menuitem"]')?.focus());
    }
  }, [open]);

  const onTriggerKey = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
    }
  };

  const onListKey = (e) => {
    const els = [...list.current.querySelectorAll('[role="menuitem"]')];
    const i = els.indexOf(document.activeElement);
    const go = (n) => {
      e.preventDefault();
      els[(n + els.length) % els.length]?.focus();
    };
    if (e.key === "ArrowDown") go(i + 1);
    else if (e.key === "ArrowUp") go(i - 1);
    else if (e.key === "Home") go(0);
    else if (e.key === "End") go(els.length - 1);
    else if (e.key === "Escape") { e.preventDefault(); close(true); }
    else if (e.key === "Tab") close(false);
  };

  const track = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
    e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
  };

  const onTriggerClick = (e) => {
    if (closing) return;
    if (!open) {
      // Opening state is authoritative; the effect registers with the shared controller.
      setOpen(true);
    } else {
      // Toggle this menu closed.
      setOpen(false);
      close(true);
    }
  };

  let n = 0;
  return (
    <div className="lg lg-menuwrap" ref={wrap}>
      <BubbleButton
        ref={trigger} variant={variant} icon={icon}
        aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
        onClick={onTriggerClick}
        onKeyDown={onTriggerKey}
      >
        {label}<Chevron />
      </BubbleButton>
      {open && (
        <div className={`lg-menu${closing ? " is-closing" : ""}`} role="menu" id={id} ref={list} onKeyDown={onListKey}>
          {items.map((it, k) => it.divider ? (
            <div className="lg-div" role="separator" key={`d${k}`} />
          ) : (
            <button
              key={it.label} type="button" role="menuitem"
              className={`lg-item${it.danger ? " lg-item--danger" : ""}`}
              style={{ "--i": n++ }}
              onPointerMove={track}
              onClick={() => { it.onSelect?.(); close(true); }}
            >
              <span className="lg-bead" /><span>{it.label}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- BubbleTabs ----------
   tabs: [{ id, label }]   value: active id   onChange(id)               */
const FIZZ = [
  ["14%", 5, "2.6s", "0s"], ["30%", 3, "3.1s", ".7s"], ["48%", 6, "2.9s", "1.3s"],
  ["64%", 4, "2.4s", ".3s"], ["80%", 5, "3.3s", "1.8s"], ["92%", 3, "2.7s", "1s"],
];

export function BubbleTabs({ tabs, value, onChange }) {
  const wrap = useRef(null);
  const btns = useRef([]);
  const idx = Math.max(0, tabs.findIndex((t) => t.id === value));
  const prev = useRef(idx);
  const dir = useRef(1);
  const [box, setBox] = useState({ l: 0, r: 0 });
  const [ready, setReady] = useState(false);
  const [moving, setMoving] = useState(false);
  const tilt = useTilt(wrap, 3);

  const measure = useCallback(() => {
    const el = btns.current[idx], c = wrap.current;
    if (!el || !c) return;
    setBox({ l: el.offsetLeft, r: c.clientWidth - el.offsetLeft - el.offsetWidth });
  }, [idx]);

  useLayoutEffect(() => {
    if (idx !== prev.current) {
      dir.current = idx > prev.current ? 1 : -1;
      prev.current = idx;
      setMoving(true);
      setTimeout(() => setMoving(false), 380);
    }
    measure();
    requestAnimationFrame(() => setReady(true));
  }, [idx, measure]);

  useEffect(() => {
    if (!wrap.current || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(measure);
    ro.observe(wrap.current);
    return () => ro.disconnect();
  }, [measure]);

  // Leading edge snaps fast, trailing edge lags: the bubble stretches like liquid.
  const ease = "cubic-bezier(.34,1.45,.64,1)";
  const fast = ".32s", slow = ".6s";
  const style = {
    left: box.l, right: box.r,
    transition: ready
      ? `left ${dir.current > 0 ? slow : fast} ${ease}, right ${dir.current > 0 ? fast : slow} ${ease}, transform .35s cubic-bezier(.34,1.8,.5,1)`
      : "none",
  };

  const onKey = (e) => {
    const len = tabs.length;
    let n = idx;
    if (e.key === "ArrowRight") n = (idx + 1) % len;
    else if (e.key === "ArrowLeft") n = (idx - 1 + len) % len;
    else if (e.key === "Home") n = 0;
    else if (e.key === "End") n = len - 1;
    else return;
    e.preventDefault();
    onChange(tabs[n].id);
    btns.current[n]?.focus();
  };

  return (
    <div className="lg lg-tabs" role="tablist" ref={wrap} onKeyDown={onKey} {...tilt}>
      <span className={`lg-bubble${moving ? " is-moving" : ""}`} style={style} aria-hidden="true">
        {FIZZ.map(([x, d, t, w], k) => (
          <i key={k} className="lg-fizz" style={{ "--x": x, "--d": `${d}px`, "--t": t, "--w": w }} />
        ))}
      </span>
      {tabs.map((t, k) => (
        <button
          key={t.id} type="button" role="tab" className="lg-tab"
          ref={(el) => (btns.current[k] = el)}
          aria-selected={t.id === value} tabIndex={t.id === value ? 0 : -1}
          onClick={() => onChange(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/* ---------- Demo: mirrors the AnimeVault toolbar ---------- */
const TABS = [
  { id: "anime", label: "Anime" }, { id: "manga", label: "Manga" },
  { id: "manhwa", label: "Manhwa" }, { id: "manhua", label: "Manhua" },
];

export default function Demo() {
  const [tab, setTab] = useState("anime");
  const say = (m) => () => console.log(m);
  const file = [
    { label: "Import Excel (.xlsx)…", onSelect: say("import xlsx") },
    { label: "Import CSV (.csv)…", onSelect: say("import csv") },
    { label: "Import SQL Dump (.sql)…", onSelect: say("import sql") },
    { divider: true },
    { label: "Export to CSV…", onSelect: say("export csv") },
    { label: "Export to Excel (.xlsx)…", onSelect: say("export xlsx") },
    { label: "Export to OpenDocument (.ods)…", onSelect: say("export ods") },
    { label: "Export to SQL Dump…", onSelect: say("export sql") },
    { divider: true },
    { label: "Back Up Database", onSelect: say("backup") },
    { label: "Quit", danger: true, onSelect: say("quit") },
  ];
  const sample = (...names) => names.map((label) => ({ label, onSelect: say(label) }));

  return (
    <div style={{
      minHeight: "100vh", padding: 32, color: "#e6ecfa", position: "relative", overflow: "hidden",
      background: "#0b1020", fontFamily: "system-ui, sans-serif",
    }}>
      {/* colour behind the glass gives the blur something to refract */}
      <div aria-hidden style={{
        position: "absolute", inset: 0, pointerEvents: "none",
        background: `radial-gradient(420px 300px at 12% 20%,rgba(126,232,208,.28),transparent 70%),
                     radial-gradient(520px 360px at 78% 8%,rgba(183,156,245,.30),transparent 70%),
                     radial-gradient(460px 320px at 60% 90%,rgba(80,120,255,.22),transparent 70%)`,
      }} />
      <div style={{ position: "relative", display: "flex", flexDirection: "column", gap: 28 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 28, flexWrap: "wrap" }}>
          <h1 style={{ margin: 0, fontSize: 32, color: "#b79cf5" }}>AnimeVault</h1>
          <BubbleTabs tabs={TABS} value={tab} onChange={setTab} />
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
          <BubbleMenu label="File" items={file} />
          <BubbleMenu label="Tools" items={sample("Find Duplicates", "Clean Titles", "Refresh Posters")} />
          <BubbleButton variant="accent">Recommendations</BubbleButton>
          <BubbleMenu label="Help" items={sample("Documentation", "Keyboard Shortcuts", "About")} />
          <BubbleMenu label="Upload" items={sample("Upload Excel", "Upload CSV", "Upload SQL Dump")} />
          <BubbleMenu label="Export" items={sample("Export to CSV", "Export to Excel", "Export to SQL Dump")} />
          <BubbleButton variant="danger">Delete</BubbleButton>
          <BubbleButton>Fetch Missing Data</BubbleButton>
          <BubbleButton disabled style={{ opacity: 0.45, pointerEvents: "none" }}>Retry Failed</BubbleButton>
        </div>
      </div>
    </div>
  );
}
