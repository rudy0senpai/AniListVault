/** Lightweight placeholder nav (Library / Overview / Recommendations / Settings). */
export default function NavPlaceholder() {
  const items = [
    { href: '#library', label: 'Library' },
    { href: '#overview', label: 'Overview' },
    { href: '#recommend', label: 'Recommendations' },
    { href: '#settings', label: 'Settings' },
  ];

  return (
    <nav className="nav-placeholder" aria-label="Sections">
      {items.map((item) => (
        <a key={item.href} className="nav-placeholder__item" href={item.href}>
          <span className="nav-placeholder__icon" aria-hidden="true">{itemLabelIcon(item.label)}</span>
          <span className="nav-placeholder__label">{item.label}</span>
        </a>
      ))}
    </nav>
  );
}

function itemLabelIcon(label) {
  const icons = {
    Library: '◈',
    Overview: '◎',
    Recommendations: '●',
    Settings: '⚙',
  };
  return icons[label] || '•';
}
