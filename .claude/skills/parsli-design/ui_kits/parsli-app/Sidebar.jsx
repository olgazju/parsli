/* Sidebar — dark olive shell with logo, nav, dev toggle, status.
   Uses line SVG icons (Lucide-style) instead of emoji. */

/* ── Icons ───────────────────────────────────────────────────────
   All icons share the same shape: 18×18 viewBox, currentColor stroke,
   stroke-width 2, line-cap round. Inherit nav-item color. */

function IconPackage() {
  return (
    <svg className="nav-icon-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16.5 9.4 7.55 4.24" />
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.29 7 12 12 20.71 7" />
      <line x1="12" y1="22" x2="12" y2="12" />
    </svg>
  );
}

function IconInbox() {
  return (
    <svg className="nav-icon-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 16 12 14 15 10 15 8 12 2 12" />
      <path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" />
    </svg>
  );
}

function IconSettings() {
  return (
    <svg className="nav-icon-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

function IconActivity() {
  return (
    <svg className="nav-icon-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}

function Sidebar({ screen, onNavigate, online = true, devMode, onToggleDev }) {
  const baseItems = [
    { id: 'parcels',     label: 'Parcels',     Icon: IconPackage },
    { id: 'accounts',    label: 'Sources',     Icon: IconInbox },
    { id: 'preferences', label: 'Preferences', Icon: IconSettings },
  ];
  const items = devMode
    ? [...baseItems, { id: 'diagnostics', label: 'Diagnostics', Icon: IconActivity }]
    : baseItems;

  return (
    <aside className="sidebar">
      <div className="logo-area">
        <div className="logo">pars<em>li</em></div>
        <div className="tagline">Local Parcel Intelligence</div>
      </div>

      <nav className="nav">
        {items.map(it => (
          <button
            key={it.id}
            className={`nav-item${screen === it.id ? ' active' : ''}`}
            onClick={() => onNavigate(it.id)}
          >
            <span className="nav-icon"><it.Icon /></span>
            <span>{it.label}</span>
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <label className="dev-toggle-row" title="Show diagnostics for the local pipeline">
          <span className="dev-toggle-label">Dev mode</span>
          <span className={`toggle-switch${devMode ? ' on' : ''}`} onClick={(e) => { e.preventDefault(); onToggleDev(!devMode); }}>
            <span className="toggle-track"></span>
            <span className="toggle-thumb"></span>
          </span>
        </label>
        <div className="station-status">
          <div className={`status-dot${online ? ' online' : ''}`}></div>
          <span>{online ? 'Online' : 'Connecting…'}</span>
        </div>
      </div>
    </aside>
  );
}

Object.assign(window, { Sidebar });
