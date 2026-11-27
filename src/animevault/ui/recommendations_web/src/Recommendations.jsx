import { useCallback, useEffect, useMemo, useRef, useState } from "react";
//import "./liquid-glass.css"; // shared glass tokens + .glass surface
import "./recommendations.css";
import { SAMPLE_RECS } from "./sampleRecs";

const MODES = [
  { key: "balanced", label: "Balanced", tip: "A mix of your taste, fan picks and quality" },
  { key: "safe", label: "Safe", tip: "Popular, well-reviewed picks" },
  { key: "discover", label: "Discover", tip: "Hidden gems and less obvious picks" },
];
const topCounts = (arr, n) => {
  const m = new Map();
  arr.forEach((x) => m.set(x, (m.get(x) || 0) + 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n).map((e) => e[0]);
};

/* ───────── Python bridge (sample data in a plain browser) ───────── */
function useRecs() {
  const [api, setApi] = useState(null);
  const [data, setData] = useState(window.qt ? null : SAMPLE_RECS);
  const [mode, setMode] = useState("balanced");
  const [busy, setBusy] = useState(!!window.qt);
  const [msg, setMsg] = useState("Starting…");
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!window.qt) return;
    const s = document.createElement("script");
    s.src = "qrc:///qtwebchannel/qwebchannel.js";
    s.onload = () =>
      new window.QWebChannel(window.qt.webChannelTransport, (ch) => {
        const r = ch.objects.recs;
        r.progress.connect(setMsg);
        r.result.connect((j) => { const d = JSON.parse(j); setData(d); setMode(d.mode); setBusy(false); setError(null); });
        r.error.connect((m) => { setError(m); setBusy(false); });
        window.recs = r;
        setApi(r);
        r.load("balanced", false);
      });
    document.head.appendChild(s);
    return () => s.remove();
  }, []);

  const load = useCallback((m, force = false) => {
    setMode(m); setBusy(true); setError(null); setMsg("Working…");
    if (api) api.load(m, force); else setTimeout(() => setBusy(false), 500);
  }, [api]);

  const act = useCallback((action, id) => {
    setData((d) => d && { ...d, items: d.items.filter((i) => i.id !== id) }); // optimistic
    if (action === "add") api?.addToLibrary(id);
    else { api?.feedback(action, id); if (api && action !== "hide") setBusy(true); }
  }, [api]);

  const open = (url) => (api ? api.openExternal(url) : window.open(url, "_blank"));
  return { data, mode, busy, msg, error, load, act, open, api };
}

/* ───────── Pieces ───────── */
function useTilt() {
  const ref = useRef(null);
  return {
    ref,
    onPointerMove: (e) => {
      const el = ref.current, r = el.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      el.style.setProperty("--mx", `${x}px`); el.style.setProperty("--my", `${y}px`);
      el.style.setProperty("--rx", `${(-(y / r.height - 0.5) * 7).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${((x / r.width - 0.5) * 9).toFixed(2)}deg`);
    },
    onPointerLeave: () => ["--rx", "--ry"].forEach((v) => ref.current?.style.removeProperty(v)),
  };
}

const Ico = ({ title, onClick, children, tone }) => (
  <button className={`rc-ico ${tone || ""}`} title={title} aria-label={title} onClick={onClick}>{children}</button>
);

function RecCard({ it, onAct, onOpen }) {
  const tilt = useTilt();
  const meta = [it.type, it.episodes ? `${it.episodes} ep` : null, it.year, it.score ? `★ ${it.score.toFixed(1)}` : null].filter(Boolean).join(" · ");
  return (
    <article className="glass rc-card" {...tilt}>
      <div className="rc-poster">
        <span className="rc-ph">{it.title.charAt(0)}</span>
        {it.img && <img src={it.img} alt="" loading="lazy" referrerPolicy="no-referrer" onError={(e) => (e.currentTarget.style.display = "none")} />}
        <b className="rc-match" style={{ "--k": (it.match - 60) / 40 }}>{it.match}%</b>
        {it.airing && <span className="rc-air">Airing</span>}
      </div>
      <h3 className="rc-title" title={it.title}>{it.title}</h3>
      <div className="rc-meta">{meta}</div>
      {!!it.reasons?.length && <ul className="rc-why">{it.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      <div className="rc-tags">{(it.tags || []).slice(0, 3).map((t) => <span key={t}>{t}</span>)}</div>
      <div className="rc-acts">
        <button className="rc-btn rc-btn--go" onClick={() => onAct("add", it.id)}>＋ Plan to watch</button>
        <Ico title="More like this" tone="up" onClick={() => onAct("like", it.id)}>♥</Ico>
        <Ico title="Not for me" onClick={() => onAct("dislike", it.id)}>⊘</Ico>
        <Ico title="Hide" onClick={() => onAct("hide", it.id)}>✕</Ico>
        <Ico title="Open on AniList" onClick={() => onOpen(it.url)}>↗</Ico>
      </div>
    </article>
  );
}

const Skeletons = () => (
  <div className="rc-grid">{Array.from({ length: 8 }, (_, i) => <div key={i} className="glass rc-card rc-skel" style={{ animationDelay: `${i * 0.08}s` }} />)}</div>
);

/* ───────── Window ───────── */
export default function Recommendations() {
  const { data, mode, busy, msg, error, load, act, open, api } = useRecs();
  const [genre, setGenre] = useState("all");
  const [format, setFormat] = useState("all");
  const [minMatch, setMin] = useState(0);

  const items = data?.items || [];
  const genres = useMemo(() => topCounts(items.flatMap((i) => i.tags || []), 30), [items]);
  const formats = useMemo(() => [...new Set(items.map((i) => i.type).filter(Boolean))].sort(), [items]);
  const shown = items.filter((i) => (genre === "all" || i.tags?.includes(genre)) && (format === "all" || i.type === format) && i.match >= minMatch);
  const p = data?.profile;
  const idx = MODES.findIndex((m) => m.key === mode);
  const close = () => (api ? api.closeWindow() : window.close());

  return (
    <div className="rc-page">
      {busy && items.length > 0 && <div className="rc-busy" role="progressbar" aria-label="Updating" />}

      <header className="rc-head">
        <div>
          <h1>Discover Your Next Favorite</h1>
          <p className="rc-sub">
            {p ? `Personalized from ${p.size} titles in your library (${p.rated} rated) · data from AniList` : "Personalized recommendations based on your library."}
          </p>
        </div>
        <div className="rc-actions">
          <button className="rc-btn" onClick={() => load(mode, true)} disabled={busy}>
            {busy && <i className="rc-spin" />}Refresh
          </button>
          <button className="rc-btn" onClick={close}>Close</button>
        </div>
      </header>

      <div className="glass rc-bar">
        <div className="rc-seg" style={{ "--i": idx }} role="tablist" aria-label="Recommendation style">
          {MODES.map((m) => (
            <button key={m.key} role="tab" aria-selected={m.key === mode} title={m.tip} onClick={() => m.key !== mode && load(m.key)}>{m.label}</button>
          ))}
        </div>
        <label className="rc-select"><span className="sr">Genre</span>
          <select value={genre} onChange={(e) => setGenre(e.target.value)}>
            <option value="all">Any genre</option>{genres.map((g) => <option key={g}>{g}</option>)}
          </select>
        </label>
        <label className="rc-select"><span className="sr">Format</span>
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="all">All formats</option>{formats.map((f) => <option key={f}>{f}</option>)}
          </select>
        </label>
        <label className="rc-range">
          <span>Minimum match: <b>{minMatch}%</b></span>
          <input type="range" min="0" max="100" value={minMatch} onChange={(e) => setMin(+e.target.value)} />
        </label>
      </div>

      {p && (p.topTags.length > 0 || p.avoidTags.length > 0) && (
        <div className="rc-taste" aria-label="Your taste profile">
          {p.topTags.map((t) => (
            <button key={t} className={`rc-chip ${genre === t ? "on" : ""}`} onClick={() => setGenre(genre === t ? "all" : t)}>{t}</button>
          ))}
          {p.avoidTags.map((t) => <span key={t} className="rc-chip neg">Not into {t}</span>)}
        </div>
      )}

      {error && (
        <div className="glass rc-state">
          <p>{error}</p>
          <button className="rc-btn rc-btn--go" onClick={() => load(mode, false)}>Try again</button>
        </div>
      )}

      {!error && busy && !data && (
        <>
          <div className="glass rc-state"><i className="rc-spin rc-spin--big" /><p>Loading recommendations…</p><small>{msg}</small></div>
          <Skeletons />
        </>
      )}

      {!error && data && (shown.length ? (
        <div className="rc-grid">{shown.map((it) => <RecCard key={it.id} it={it} onAct={act} onOpen={open} />)}</div>
      ) : (
        <div className="glass rc-state">
          <p>{items.length ? "No picks match these filters." : "No recommendations yet. Add and rate more anime, then refresh."}</p>
          {items.length > 0 && <button className="rc-btn" onClick={() => { setGenre("all"); setFormat("all"); setMin(0); }}>Reset filters</button>}
        </div>
      ))}
    </div>
  );
}
