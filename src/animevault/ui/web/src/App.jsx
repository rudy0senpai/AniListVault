import { useLibrary as useBridgeLibrary } from "./bridge.js";
import { useCallback, useEffect, useState } from "react";
import Dashboard from "./Dashboard.jsx";

const statusClass = (status = "") => {
  const s = status.toLowerCase();
  if (s.includes("complete")) return "pill--completed";
  if (s.includes("reread")) return "pill--rereading";
  if (s.includes("plan")) return "pill--planning";
  if (s.includes("watch") || s.includes("read")) return "pill--watching";
  if (s.includes("hold") || s.includes("pause")) return "pill--paused";
  if (s.includes("drop")) return "pill--dropped";
  return "pill--paused";
};
const tierClass = (tier = "") => {
  const t = tier.trim().toUpperCase();
  return ["SSS", "SS", "S", "A", "B", "C", "D", "E", "F"].includes(t) ? `pill--tier-${t}` : "";
};
const safeText = (value) => value === undefined || value === null ? "" : String(value);

function Pills({ item }) {
  return <div className="av-pills">
    {item.status && <span className={`pill ${statusClass(item.status)}`}>{item.status}</span>}
    {item.tier && <span className={`pill pill--tier ${tierClass(item.tier)}`}>{item.tier}</span>}
    {item.favorite && <span className="pill pill--fav">★ Favorite</span>}
  </div>;
}

function useSpecular(tilt = false) {
  return {
    onPointerMove(e) {
      const el = e.currentTarget; const r = el.getBoundingClientRect();
      const x = e.clientX - r.left; const y = e.clientY - r.top;
      el.style.setProperty("--mx", `${x}px`); el.style.setProperty("--my", `${y}px`);
      if (tilt && r.width && r.height) {
        const px = x / r.width - 0.5; const py = y / r.height - 0.5;
        el.style.setProperty("--px", px.toFixed(3)); el.style.setProperty("--py", py.toFixed(3));
        el.style.setProperty("--rx", `${(-py * 10).toFixed(2)}deg`); el.style.setProperty("--ry", `${(px * 12).toFixed(2)}deg`);
      }
    },
    onPointerLeave(e) {
      const el = e.currentTarget;
      if (tilt) ["--px", "--py", "--rx", "--ry"].forEach((key) => el.style.removeProperty(key));
    },
  };
}

function Card({ item, bridge, onOpen, selectionMode, selected, onSelected }) {
  const pointer = useSpecular(true);
  const total = Number.isFinite(Number(item.total)) && Number(item.total) > 0 ? Number(item.total) : null;
  const progress = Math.max(0, Number(item.progress) || 0);
  const percent = total ? Math.min(100, progress * 100 / total) : 0;
  const unit = item.unit === "chapters" ? "ch" : "ep";
  const summary = `${safeText(item.type)}${item.type ? " · " : ""}${total ? `${total} ${unit}` : `? ${unit}`}`;
  return <article className="card-shell" style={{ contentVisibility: "auto", containIntrinsicSize: "200px" }}>
    <div className={`glass av-card${selected ? " is-selected" : ""}`} role="button" tabIndex={0}
      aria-label={`${item.title}, ${item.status || ""}, ${progress} of ${total ?? "unknown"} ${item.unit || "episodes"}`}
      onClick={() => selectionMode ? onSelected(item.id, !selected) : onOpen(item)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); selectionMode ? onSelected(item.id, !selected) : onOpen(item); } }}
      {...pointer}>
      {selectionMode && <span className={`selection-mark${selected ? " checked" : ""}`}>{selected ? "✓" : ""}</span>}
      {item.cover ? <img className="av-poster" src={item.cover} alt="" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} /> : <div className="av-poster av-placeholder" aria-hidden="true">✧</div>}
      <div className="av-body">
        <div className="av-title-row"><h3 className="av-title" title={item.title}>{item.title}</h3>
          {bridge && <button type="button" className="av-menu" aria-label="More options" onClick={(e) => { e.stopPropagation(); bridge.showMenu(item.id); }}>⋮</button>}
        </div>
        <div className="av-meta">{summary}</div>
        <div className="av-progress"><span>{progress} / {total ?? "?"}</span>
          <span className={`av-bar${total ? "" : " indeterminate"}`} role="progressbar" aria-valuemin={0} aria-valuemax={total || undefined} aria-valuenow={total ? Math.min(progress, total) : undefined} aria-label="Progress">
            <i style={{ width: total ? `${percent}%` : `${progress ? 34 : 0}%` }} />
          </span>
        </div>
        <Pills item={item} />
      </div>
    </div>
  </article>;
}

function Section({ title, rows }) {
  const visible = rows.filter(([, v]) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && !v.length));
  if (!visible.length) return null;
  return <section className="av-section"><h3>{title}</h3><dl>{visible.map(([key, value]) => <div className="av-row" key={key}><dt>{key}</dt><dd>{Array.isArray(value) ? value.join(", ") : String(value)}</dd></div>)}</dl></section>;
}
function Detail({ item, onClose }) {
  useEffect(() => {
    const key = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key); const old = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = old; };
  }, [onClose]);
  const lit = item.mediaType !== "anime";
  const unit = item.unit === "chapters" ? "chapters" : "episodes";
  return <div className="av-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
    <div className="glass av-modal" role="dialog" aria-modal="true" aria-label={item.title}>
      <header className="av-modal-bar"><span>{item.title}</span><button className="av-close" onClick={onClose} aria-label="Close">✕</button></header>
      <div className="av-hero">{item.cover ? <img className="av-poster" src={item.cover} alt="" /> : <div className="av-poster av-placeholder">✧</div>}
        <div><h2>{item.title}</h2>{item.nativeTitle && item.nativeTitle !== item.title && <p className="av-native">{item.nativeTitle}</p>}
          <Pills item={item} />{item.synopsis && <p className="av-synopsis">{item.synopsis}</p>}</div></div>
      <Section title="Personal" rows={[["Tier", item.tier], ["Status", item.status], ["Progress", `${item.progress || 0} / ${item.total ?? "?"} ${unit}`], [lit ? "Rereads" : "Rewatches", item.rewatches], ["Favorite", item.favorite ? "Yes" : "No"]]} />
      <Section title="Metadata" rows={[["Type", item.type], [lit ? "Chapters" : "Episodes", item.total], ["Volumes", item.volumes], ["Duration", item.duration ? `${item.duration} min` : null], ["Season", item.season], ["Year", item.year], ["Aired / Published", item.aired], ["Genres", item.genres], [lit ? "Authors" : "Studios", lit ? item.authors : item.studios], ["Serialization", item.serialization]]} />
      <Section title="Provider IDs" rows={[["AniList", item.anilistId], ["MAL / Jikan", item.malId], ["Source", item.source], ["Fetched", item.fetchedAt]]} />
    </div>
  </div>;
}

export default function App() {
  const { items, bridge, ready } = useBridgeLibrary();
  const [page, setPage] = useState("library");
  const [open, setOpen] = useState(null);
  const [selectionMode, setSelectionMode] = useState(false);
  const [selected, setSelected] = useState(() => new Set());
  const onClose = useCallback(() => setOpen(null), []);
  useEffect(() => {
    const showDashboard = () => setPage("dashboard");
    const showLibrary = () => setPage("library");
    window.addEventListener("animevault:dashboard", showDashboard);
    window.addEventListener("animevault:library", showLibrary);
    return () => {
      window.removeEventListener("animevault:dashboard", showDashboard);
      window.removeEventListener("animevault:library", showLibrary);
    };
  }, []);
  const select = useCallback((id, value) => {
    setSelected((before) => { const next = new Set(before); value ? next.add(id) : next.delete(id); return next; });
    bridge?.setSelected(id, value);
  }, [bridge]);
  const toggleSelectionMode = () => {
    const next = !selectionMode; setSelectionMode(next); setSelected(new Set()); bridge?.setSelectionMode(next);
  };
  if (page === "dashboard") return <Dashboard api={bridge}
    onBack={() => setPage("library")}
    onRecommendations={() => bridge?.openRecommendations()}
    onOpenRecord={(id) => bridge?.openRecord(String(id))} />;
  return <main className="av-app">
    <div className="av-toolbar"><div><div className="eyebrow">YOUR COLLECTION</div><h1>Library</h1><p>{items.length} titles · ordered and filtered by AnimeVault</p></div>
      <div>{bridge && <><button className="select-button" onClick={() => setPage("dashboard")}>Dashboard</button> <button className={`select-button${selectionMode ? " active" : ""}`} onClick={toggleSelectionMode}>{selectionMode ? "✓ Selecting" : "Select"}</button></>}</div></div>
    {!ready ? <div className="empty-state">Loading library…</div> : items.length ? <div className="av-grid">
      {items.map((item) => <Card key={item.id} item={item} bridge={bridge} onOpen={setOpen} selectionMode={selectionMode} selected={selected.has(item.id)} onSelected={select} />)}
    </div> : <div className="empty-state">No titles match the current library filters.</div>}
    {open && <Detail item={open} onClose={onClose} />}
  </main>;
}
