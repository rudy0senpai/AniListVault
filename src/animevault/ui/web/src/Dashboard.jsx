import { useCallback, useEffect, useMemo, useState } from "react";
import "./liquid-glass.css"; // shared glass tokens + .glass surface (from the card UI)
import "./dashboard.css";


const PAL = ["#c4b5fd", "#7fe3cf", "#ffe1a0", "#f5b6d8", "#a9d6ff", "#9be3b0", "#ff8f9f", "#a58bf0"];
const STATUS_C = { planned: "#c4b5fd", active: "#7fe3cf", done: "#ffe1a0", hold: "#f5b6d8", dropped: "#a9d6ff" };
const MEDIA_C = { anime: "#c4b5fd", manga: "#7fe3cf", manhwa: "#ffe1a0", manhua: "#f5b6d8" };
const DATES = [{ value: "all", label: "All dates" }, { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" }, { value: "365d", label: "Last year" }];
const ALL = { media: "all", status: "all", format: "all", genre: "all", dates: "all" };
const fmt = (n) => (n ?? 0).toLocaleString();

/* ───────── Python dashboard bridge (no browser/sample fallback) ───────── */
function useDashboard(filters, api) {
  const [tick, setTick] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!api) { setLoading(false); setError("The AnimeVault Python bridge is unavailable."); return; }
    let current = true;
    setLoading(true); setError("");
    api.getDashboard(JSON.stringify(filters), (raw) => {
      if (!current) return;
      try {
        const parsed = JSON.parse(raw);
        if (parsed?.error) throw new Error(parsed.error);
        if (!parsed?.kpis || !Array.isArray(parsed.media)) throw new Error("Dashboard response is incomplete.");
        setData(parsed);
      } catch (e) { setData(null); setError(e.message || "Could not read dashboard data."); }
      finally { setLoading(false); }
    });
    return () => { current = false; };
  }, [api, filters, tick]);

  useEffect(() => {
    if (!api?.dashboardChanged?.connect) return;
    const changed = () => setTick((t) => t + 1);
    api.dashboardChanged.connect(changed);
  }, [api]);
  const refresh = useCallback(() => api ? api.refreshDashboard() : setTick((t) => t + 1), [api]);
  return { data, error, loading, refresh };
}

/* ───────── Building blocks ───────── */
function Glass({ className = "", children, as: Tag = "section", ...rest }) {
  const move = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
    e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
  };
  return <Tag className={`glass ${className}`} onPointerMove={move} {...rest}>{children}</Tag>;
}

const Panel = ({ title, sub, span = 6, children }) => (
  <Glass className={`dv-panel dv-${span}`}>
    <h2>{title}</h2>
    {sub && <p className="dv-sub">{sub}</p>}
    {children}
  </Glass>
);
const Empty = () => <p className="dv-empty">Nothing recorded for these filters.</p>;

const Select = ({ label, value, onChange, options }) => (
  <label className="dv-select">
    <span className="sr">{label}</span>
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  </label>
);

const Kpi = ({ label, value }) => (
  <Glass as="div" className="dv-kpi"><span>{label}</span><b>{value}</b></Glass>
);

/* glossy donut: round-capped bubble segments */
function Donut({ items, center }) {
  const total = items.reduce((s, i) => s + i.count, 0);
  if (!total) return <Empty />;
  const R = 70, C = 2 * Math.PI * R, PAD = 12;
  let acc = 0;
  return (
    <div className="dv-donut">
      <svg viewBox="0 0 200 200" role="img" aria-label="Distribution chart">
        <circle cx="100" cy="100" r={R} className="dv-track" />
        {items.map((it, i) => {
          const len = (C * it.count) / total;
          const el = (
            <circle key={it.label} cx="100" cy="100" r={R} fill="none" stroke={it.color || PAL[i % PAL.length]}
              strokeWidth="24" strokeLinecap="round" transform="rotate(-90 100 100)"
              strokeDasharray={`${Math.max(len - 2 * PAD - 2, 0.01)} ${C}`} strokeDashoffset={-(acc + PAD)}>
              <title>{it.label}: {fmt(it.count)}</title>
            </circle>
          );
          acc += len;
          return el;
        })}
        <circle cx="100" cy="100" r={R} fill="none" stroke="url(#dv-ring)" strokeWidth="24" pointerEvents="none" />
        <text x="100" y="108" textAnchor="middle" className="dv-donut-n">{center}</text>
      </svg>
      <ul className="dv-legend">
        {items.map((it, i) => (
          <li key={it.label}>
            <i style={{ background: it.color || PAL[i % PAL.length] }} />
            {it.label} <b>{fmt(it.count)}</b> <small>({Math.round((it.count / total) * 100)}%)</small>
          </li>
        ))}
      </ul>
    </div>
  );
}

function HBars({ items, label = (i) => i.label }) {
  if (!items.length) return <Empty />;
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <ul className="dv-hbars">
      {items.map((it, i) => (
        <li key={label(it)}>
          <span>{label(it)}</span>
          <span className="dv-tube" style={{ "--c": PAL[i % PAL.length] }}><i style={{ width: `${(it.count / max) * 100}%` }} /></span>
          <b>{fmt(it.count)}</b>
        </li>
      ))}
    </ul>
  );
}

function Funnel({ items }) {
  const max = Math.max(...items.map((i) => i.count), 1);
  return (
    <ul className="dv-funnel">
      {items.map((it) => (
        <li key={it.key}>
          <span>{it.label}</span>
          <div><i style={{ width: `${Math.max((it.count / max) * 100, 4)}%`, "--c": STATUS_C[it.key] }} /></div>
          <b>{fmt(it.count)}</b>
        </li>
      ))}
    </ul>
  );
}

function StatusByMedia({ data, statuses }) {
  const rows = Object.entries(data).map(([m, s]) => [m, s, Object.values(s).reduce((a, b) => a + b, 0)]).filter((r) => r[2]);
  if (!rows.length) return <Empty />;
  return (
    <>
      <ul className="dv-hbars">
        {rows.map(([m, s, n]) => (
          <li key={m}>
            <span>{m[0].toUpperCase() + m.slice(1)}</span>
            <span className="dv-tube dv-stack">
              {statuses.map((k) => s[k.key] > 0 && (
                <i key={k.key} title={`${k.label}: ${s[k.key]}`} style={{ flexGrow: s[k.key], "--c": STATUS_C[k.key] }} />
              ))}
            </span>
            <b>{fmt(n)}</b>
          </li>
        ))}
      </ul>
      <ul className="dv-legend dv-legend--row">
        {statuses.map((k) => <li key={k.key}><i style={{ background: STATUS_C[k.key] }} />{k.label}</li>)}
      </ul>
    </>
  );
}

function Line({ points }) {
  if (!points.length) return <Empty />;
  const W = 600, H = 170, P = 18, max = Math.max(...points.map((p) => p.count), 1);
  const x = (i) => (points.length === 1 ? W / 2 : P + (i * (W - 2 * P)) / (points.length - 1));
  const y = (v) => H - P - (v / max) * (H - 2 * P);
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i)} ${y(p.count)}`).join(" ");
  const step = Math.ceil(points.length / 6);
  return (
    <svg viewBox={`0 0 ${W} ${H + 20}`} className="dv-line-svg" role="img" aria-label="Recorded dates by month">
      <path d={`${d} L${x(points.length - 1)} ${H - P} L${x(0)} ${H - P} Z`} fill="url(#dv-area)" />
      <path d={d} className="dv-line" />
      {points.map((p, i) => (
        <g key={p.ym}>
          <circle cx={x(i)} cy={y(p.count)} r="6" fill="#7fe3cf" className="dv-dot" />
          <circle cx={x(i)} cy={y(p.count)} r="6" fill="url(#dv-gloss)" />
          <title>{p.ym}: {p.count}</title>
          {(i % step === 0 || i === points.length - 1) && <text x={x(i)} y={H + 14} textAnchor="middle">{p.ym}</text>}
        </g>
      ))}
    </svg>
  );
}

function Heat({ heat }) {
  const years = Object.keys(heat).sort();
  if (!years.length) return <Empty />;
  const max = Math.max(1, ...years.flatMap((y) => Object.values(heat[y])));
  return (
    <div className="dv-heat">
      {years.map((y) => (
        <div key={y}>
          <span>{y}</span>
          {Array.from({ length: 12 }, (_, m) => {
            const c = heat[y][m + 1] || 0;
            return <i key={m} title={`${y}-${String(m + 1).padStart(2, "0")}: ${c}`} style={{ "--k": c / max }}>{m + 1}</i>;
          })}
        </div>
      ))}
    </div>
  );
}

function Columns({ items }) {
  if (!items.length) return <Empty />;
  const max = Math.max(...items.map((i) => i.count), 1);
  const step = Math.ceil(items.length / 10);
  return (
    <div className="dv-cols">
      {items.map((it, i) => (
        <div key={it.year} title={`${it.year}: ${it.count}`}>
          <i style={{ height: `${Math.max((it.count / max) * 100, 3)}%` }} />
          <span>{i % step === 0 ? it.year : ""}</span>
        </div>
      ))}
    </div>
  );
}

/* the memorable bit: genres as floating glass bubbles, packed on a spiral */
function Bubbles({ items }) {
  const { nodes, box } = useMemo(() => {
    const max = Math.max(...items.map((i) => i.count), 1);
    const placed = [];
    items.forEach((it) => {
      const r = 18 + 46 * Math.sqrt(it.count / max);
      for (let t = 0; t < 6000; t++) {
        const a = t * 2.39996, d = 2.4 * Math.sqrt(t);
        const x = Math.cos(a) * d * 1.5, y = Math.sin(a) * d;
        if (placed.every((p) => Math.hypot(p.x - x, p.y - y) >= p.r + r + 4)) { placed.push({ ...it, x, y, r }); return; }
      }
    });
    if (!placed.length) return { nodes: [], box: [0, 0, 10, 10] };
    const x0 = Math.min(...placed.map((p) => p.x - p.r)) - 8, x1 = Math.max(...placed.map((p) => p.x + p.r)) + 8;
    const y0 = Math.min(...placed.map((p) => p.y - p.r)) - 8, y1 = Math.max(...placed.map((p) => p.y + p.r)) + 8;
    return { nodes: placed, box: [x0, y0, x1 - x0, y1 - y0] };
  }, [items]);
  if (!nodes.length) return <Empty />;
  return (
    <>
      <svg viewBox={box.join(" ")} className="dv-bubbles" role="img" aria-label="Genre bubble map">
        {nodes.map((p, i) => {
          const c = MEDIA_C[p.media] || PAL[i % PAL.length], fs = Math.min(14, p.r / 2.4);
          const n = Math.max(3, Math.floor(p.r / 4));
          return (
            <g key={p.label} className="dv-bubble" style={{ animationDelay: `${(i % 7) * -0.9}s` }}>
              <circle cx={p.x} cy={p.y} r={p.r} fill={c} fillOpacity=".34" stroke="rgba(255,255,255,.55)" strokeWidth="1.2" />
              <circle cx={p.x} cy={p.y} r={p.r} fill="url(#dv-sphere)" />
              <ellipse cx={p.x - p.r * 0.34} cy={p.y - p.r * 0.5} rx={p.r * 0.36} ry={p.r * 0.16} fill="#fff" opacity=".6"
                transform={`rotate(-28 ${p.x - p.r * 0.34} ${p.y - p.r * 0.5})`} />
              <text x={p.x} y={p.y + fs * 0.1} textAnchor="middle" fontSize={fs}>{p.label.length > n ? p.label.slice(0, n - 1) + "…" : p.label}</text>
              <text x={p.x} y={p.y + fs * 1.25} textAnchor="middle" fontSize={fs * 0.82} className="dv-bn">{fmt(p.count)}</text>
              <title>{p.label}: {fmt(p.count)}</title>
            </g>
          );
        })}
      </svg>
      <ul className="dv-legend dv-legend--row">
        {Object.entries(MEDIA_C).map(([m, c]) => <li key={m}><i style={{ background: c }} />{m[0].toUpperCase() + m.slice(1)}</li>)}
      </ul>
    </>
  );
}

/* ───────── Page ───────── */
export default function Dashboard({ api, onBack, onRecommendations, onOpenRecord }) {
  const [f, setF] = useState(ALL);
  const { data, error, loading, refresh } = useDashboard(f, api);
  if (loading && !data) return <div className="dv-page" role="status">Loading dashboard from the AnimeVault database…</div>;
  if (error && !data) return <div className="dv-page" role="alert"><h1>Dashboard unavailable</h1><p>{error}</p><button className="dv-btn" onClick={refresh}>Retry</button></div>;
  if (!data) return <div className="dv-page" role="alert"><h1>Dashboard unavailable</h1><button className="dv-btn" onClick={refresh}>Retry</button></div>;
  const k = data.kpis, o = data.options || {};
  const set = (key) => (v) => setF((p) => ({ ...p, [key]: v }));
  const withAll = (label, list = []) => [{ value: "all", label }, ...list];
  const call = (fn, name, ...a) => (fn ? fn(...a) : window.dashboard?.[name]?.(...a));

  return (
    <div className="dv-page">
      <svg width="0" height="0" style={{ position: "absolute" }} aria-hidden="true">
        <defs>
          <linearGradient id="dv-ring" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#fff" stopOpacity=".7" /><stop offset=".5" stopColor="#fff" stopOpacity="0" />
            <stop offset="1" stopColor="#fff" stopOpacity=".18" />
          </linearGradient>
          <radialGradient id="dv-gloss" cx=".32" cy=".28" r=".6">
            <stop offset="0" stopColor="#fff" stopOpacity=".9" /><stop offset=".6" stopColor="#fff" stopOpacity="0" />
          </radialGradient>
          <radialGradient id="dv-sphere" cx=".5" cy=".5" r=".5">
            <stop offset=".6" stopColor="#fff" stopOpacity="0" /><stop offset="1" stopColor="#fff" stopOpacity=".3" />
          </radialGradient>
          <linearGradient id="dv-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#7fe3cf" stopOpacity=".35" /><stop offset="1" stopColor="#7fe3cf" stopOpacity="0" />
          </linearGradient>
        </defs>
      </svg>

      <header className="dv-head">
        <div>
          <h1>Library Dashboard</h1>
          <p className="dv-sub">Collection metrics and recorded progress activity</p>
        </div>
        <div className="dv-actions">
          <span className="dv-sub">Updated {new Date(data.updatedAt).toLocaleTimeString()}</span>
          <button className="dv-btn" onClick={() => call(onBack, "goBack")}>← Back to Library</button>
          <button className="dv-btn dv-btn--go" onClick={refresh}>Refresh</button>
        </div>
      </header>

      {data.error && <p role="alert">{data.error} <button className="dv-btn" onClick={refresh}>Retry</button></p>}
      {k.total === 0 && <p className="dv-empty" role="status">Your library is empty for the selected filters.</p>}

      <div className="dv-kpis">
        <Kpi label="Total items" value={fmt(k.total)} />
        <Kpi label="Completed items" value={fmt(k.completed)} />
        <Kpi label="In progress" value={fmt(k.inProgress)} />
        <Kpi label="Favorites" value={fmt(k.favorites)} />
        {k.avgScore != null && <Kpi label="Avg Anime score" value={`${k.avgScore} / 10`} />}
        {k.avgScore != null && <Kpi label="Rated Anime" value={fmt(k.ratedCount)} />}
        <Kpi label="Episodes" value={`${fmt(k.episodes[0])} / ${fmt(k.episodes[1])}`} />
        <Kpi label="Chapters" value={`${fmt(k.chapters[0])} / ${fmt(k.chapters[1])}`} />
        <Kpi label="Tiered items" value={fmt(k.tiered)} />
        <Kpi label="Unique genres" value={fmt(k.uniqueGenres)} />
      </div>

      <Glass className="dv-filters">
        <Select label="Media" value={f.media} onChange={set("media")} options={withAll("All media", o.media)} />
        <Select label="Status" value={f.status} onChange={set("status")} options={withAll("All statuses", o.status)} />
        <Select label="Format" value={f.format} onChange={set("format")} options={withAll("All formats", o.format)} />
        <Select label="Genre" value={f.genre} onChange={set("genre")} options={withAll("All genres", o.genre)} />
        <Select label="Dates" value={f.dates} onChange={set("dates")} options={DATES} />
      </Glass>

      <div className="dv-grid">
        <Panel title="Media distribution" sub="Share of the selected collection by media category." span={6}>
          <Donut center={fmt(k.total)} items={data.media.map((m) => ({ ...m, color: MEDIA_C[m.key] }))} />
        </Panel>
        <Panel title="Format proportions" sub="Format mix from saved anime media types and literature formats." span={6}>
          <Donut center={data.formats.length} items={data.formats} />
        </Panel>

        <Panel title="Genre bubble map" sub="Bubble size is the number of matching records; colour is the media type most often tagged." span={7}>
          <Bubbles items={data.genres} />
        </Panel>
        <Panel title="Status breakdown" sub="Statuses are independent states, not sequential stages." span={5}>
          <Funnel items={data.status} />
        </Panel>

        <Panel title="Most common genres" sub="Distinct genre tags on matching library records." span={6}>
          <HBars items={data.genres.slice(0, 8)} />
        </Panel>
        <Panel title="Status by media type" sub="Each bar splits one media category by status." span={6}>
          <StatusByMedia data={data.statusByMedia} statuses={data.status} />
        </Panel>

        <Panel title="Tier distribution" sub="Saved personal tiers; unranked items are not counted." span={6}>
          <HBars items={data.tiers} label={(i) => i.tier} />
        </Panel>
        <Panel title="Release years" sub="Anime season year, aired date and literature start dates when available." span={6}>
          <Columns items={data.years} />
        </Panel>

        <Panel title="Recorded personal dates by month" sub="Uses saved first/last progress and completion dates; no history is inferred." span={6}>
          <Line points={data.months} />
        </Panel>
        <Panel title="Recorded-date heat map" sub="Saved personal progress dates grouped by year and month." span={6}>
          <Heat heat={data.heat} />
        </Panel>

        <Panel title="In progress" span={6}>
          {data.inProgress.length ? (
            <ul className="dv-rows">
              {data.inProgress.map((r) => (
                <li key={r.id}>
                  <button onClick={() => call(onOpenRecord, "openRecord", r.id)}>
                    <span className="dv-rt">{r.title}</span>
                    <small>{r.media}</small>
                    <span className="dv-tube dv-mini" style={{ "--c": MEDIA_C[r.media] }}>
                      <i style={{ width: `${r.total ? Math.min(100, (r.progress / r.total) * 100) : 0}%` }} />
                    </span>
                    <b>{r.progress}/{r.total || "?"}</b>
                  </button>
                </li>
              ))}
            </ul>
          ) : <Empty />}
        </Panel>
        <Panel title="Recent recorded activity" span={6}>
          {data.activity.length ? (
            <ul className="dv-rows dv-act">
              {data.activity.map((a, i) => (
                <li key={i}><small>{a.date}</small><span>{a.label}</span><span className="dv-rt">{a.title}</span></li>
              ))}
            </ul>
          ) : <Empty />}
        </Panel>

        <Panel title="Recommendations" sub="Generated by the existing recommendation workflow." span={12}>
          <button className="dv-btn dv-btn--wide" onClick={() => call(onRecommendations, "openRecommendations")}>Open Recommendations</button>
        </Panel>
      </div>
    </div>
  );
}
