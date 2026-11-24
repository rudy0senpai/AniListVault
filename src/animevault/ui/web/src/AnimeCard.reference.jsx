import { useEffect, useRef, useState } from "react";
import "./liquid-glass.css";

/* Specular highlight under the cursor. With { tilt: true } it also tilts the
   element in 3D and sets --px/--py (-0.5..0.5) for the parallax layers. */
function useSpecular({ tilt = false } = {}) {
  const ref = useRef(null);
  const onPointerMove = (e) => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const x = e.clientX - r.left;
    const y = e.clientY - r.top;
    el.style.setProperty("--mx", `${x}px`);
    el.style.setProperty("--my", `${y}px`);
    if (tilt) {
      const px = x / r.width - 0.5;
      const py = y / r.height - 0.5;
      el.style.setProperty("--px", px.toFixed(3));
      el.style.setProperty("--py", py.toFixed(3));
      el.style.setProperty("--rx", `${(-py * 10).toFixed(2)}deg`);
      el.style.setProperty("--ry", `${(px * 12).toFixed(2)}deg`);
    }
  };
  const onPointerLeave = () => {
    const el = ref.current;
    if (!el || !tilt) return;
    ["--px", "--py", "--rx", "--ry"].forEach((v) => el.style.removeProperty(v));
  };
  return { ref, onPointerMove, onPointerLeave };
}

const statusClass = (s = "") => {
  const k = s.toLowerCase();
  if (k.includes("complete")) return "pill--completed";
  if (k.includes("watching")) return "pill--watching";
  if (k.includes("plan")) return "pill--planning";
  if (k.includes("hold") || k.includes("pause")) return "pill--paused";
  if (k.includes("drop")) return "pill--dropped";
  return "pill--paused";
};

const tierClass = (t = "") => {
  const first = t.trim().charAt(0).toUpperCase();
  return ["S", "A", "B", "C"].includes(first) && t !== "SS" ? `pill--tier-${first}` : "";
};

function Pills({ anime }) {
  return (
    <div className="av-pills">
      <span className={`pill ${statusClass(anime.status)}`}>{anime.status}</span>
      {anime.tier && <span className={`pill pill--tier ${tierClass(anime.tier)}`}>{anime.tier}</span>}
      {anime.favorite && <span className="pill pill--fav">★ Favorite</span>}
    </div>
  );
}

/* ───────── Card ───────── */
export function AnimeCard({ anime, onOpen, onMenu }) {
  const spec = useSpecular({ tilt: true });
  const pct = anime.episodes ? Math.min(100, (anime.progress / anime.episodes) * 100) : 0;

  return (
    <article>
      <button
        type="button"
        className="glass av-card"
        onClick={() => onOpen?.(anime)}
        aria-label={`${anime.title}, ${anime.status}, ${anime.progress} of ${anime.episodes} episodes`}
        {...spec}
      >
        <img className="av-poster" src={anime.cover} alt="" loading="lazy" />

        <div className="av-body">
          <div className="av-title-row">
            <h3 className="av-title">{anime.title}</h3>
            <span
              role="button"
              tabIndex={0}
              className="av-menu"
              aria-label="More options"
              onClick={(e) => { e.stopPropagation(); onMenu?.(anime, e); }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") { e.stopPropagation(); e.preventDefault(); onMenu?.(anime, e); }
              }}
            >
              ⋮
            </span>
          </div>

          <div className="av-meta">{anime.type} · {anime.episodes} ep</div>

          <div className="av-progress">
            <span>{anime.progress} / {anime.episodes}</span>
            <span className="av-bar" role="progressbar" aria-valuemin={0} aria-valuemax={anime.episodes} aria-valuenow={anime.progress}>
              <i style={{ width: `${pct}%` }} />
            </span>
          </div>

          <Pills anime={anime} />
        </div>
      </button>
    </article>
  );
}

/* ───────── Detail modal ───────── */
const Section = ({ title, rows }) => (
  <section className="av-section">
    <h3>{title}</h3>
    <dl>
      {rows.filter(([, v]) => v !== undefined && v !== null && v !== "").map(([k, v]) => (
        <div className="av-row" key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  </section>
);

export function AnimeModal({ anime, onClose }) {
  const spec = useSpecular();
  const closeRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeRef.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  if (!anime) return null;
  const a = anime;

  return (
    <div className="av-scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="glass av-modal" role="dialog" aria-modal="true" aria-label={a.title} {...spec}>
        <header className="av-modal-bar">
          <span>{a.title}</span>
          <button ref={closeRef} className="av-close" onClick={onClose} aria-label="Close">✕</button>
        </header>

        <div className="av-hero">
          <img className="av-poster" src={a.cover} alt="" />
          <div>
            <h2>{a.title}</h2>
            {a.nativeTitle && <p className="av-native">{a.nativeTitle}</p>}
            <Pills anime={a} />
            {a.synopsis && <p className="av-synopsis">{a.synopsis}</p>}
          </div>
        </div>

        <Section
          title="Personal"
          rows={[
            ["Tier", a.tier],
            ["Status", a.status],
            ["Progress", `${a.progress} / ${a.episodes}`],
            ["Rewatches", a.rewatches],
            ["Favorite", a.favorite ? "Yes" : "No"],
          ]}
        />
        <Section
          title="Metadata"
          rows={[
            ["Type", a.type],
            ["Episodes", a.episodes],
            ["Duration", a.duration && `${a.duration} min`],
            ["Season", a.season],
            ["Year", a.year],
            ["Aired", a.aired],
            ["Genres", a.genres?.join(", ")],
            ["Studios", a.studios?.join(", ")],
          ]}
        />
        <Section
          title="Provider IDs"
          rows={[
            ["AniList", a.anilistId],
            ["MAL / Jikan", a.malId],
            ["Source", a.source],
            ["Fetched", a.fetchedAt],
          ]}
        />
      </div>
    </div>
  );
}

/* ───────── Demo (replace with your real data) ───────── */
const SAMPLE = [
  {
    id: 934,
    title: "Higurashi: When they cry",
    nativeTitle: "ひぐらしのなく頃に",
    cover: "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/bx934-0e4a1a4cX8mE.jpg",
    type: "TV",
    episodes: 65,
    progress: 65,
    status: "Completed",
    tier: "SS",
    favorite: true,
    rewatches: 1,
    duration: 24,
    season: "SPRING",
    year: 2006,
    aired: "2006-04-05 → 2006-09-27",
    genres: ["Horror", "Mystery", "Psychological", "Supernatural", "Thriller"],
    studios: ["Studio DEEN"],
    synopsis:
      "After moving into the quiet town of Hinamizawa, Maebara Keiichi spends his days blissfully in school often playing games with his local friends. However, appearances can be deceiving.",
    anilistId: 934,
    malId: 934,
    source: "anilist",
    fetchedAt: "2026-10-08T07:52:28+00:00",
  },
];

export default function AnimeGrid({ items = SAMPLE }) {
  const [open, setOpen] = useState(null);

  return (
    <div
      style={{
        minHeight: "100vh",
        /* glass needs something colorful behind it to refract */
        background:
          "radial-gradient(900px 500px at 10% 0%, #3a52a0 0%, transparent 60%)," +
          "radial-gradient(800px 600px at 95% 20%, #5b2d7a 0%, transparent 55%)," +
          "radial-gradient(700px 500px at 40% 100%, #0f6b64 0%, transparent 60%), #0d1120",
      }}
    >
      <div className="av-grid">
        {items.map((a) => (
          <AnimeCard key={a.id} anime={a} onOpen={setOpen} />
        ))}
      </div>
      {open && <AnimeModal anime={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
