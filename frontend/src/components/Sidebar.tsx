import { NavLink, useLocation, useNavigate } from "react-router-dom";

import {
  IconActivity,
  IconInbox,
  IconPackage,
  IconSettings,
} from "@/components/icons";

interface SidebarProps {
  online: boolean;
  devMode: boolean;
  onToggleDev: (next: boolean) => void;
}

interface NavItem {
  to: string;
  label: string;
  Icon: () => JSX.Element;
}

const BASE_ITEMS: NavItem[] = [
  { to: "/parcels", label: "Parcels", Icon: IconPackage },
  { to: "/sources", label: "Sources", Icon: IconInbox },
  { to: "/preferences", label: "Preferences", Icon: IconSettings },
];

export function Sidebar({ online, devMode, onToggleDev }: SidebarProps) {
  const items: NavItem[] = devMode
    ? [
        ...BASE_ITEMS,
        { to: "/diagnostics", label: "Diagnostics", Icon: IconActivity },
      ]
    : BASE_ITEMS;

  const location = useLocation();
  const navigate = useNavigate();

  const toggleDev = () => {
    const next = !devMode;
    onToggleDev(next);
    if (!next && location.pathname === "/diagnostics") {
      navigate("/parcels", { replace: true });
    }
  };

  return (
    <aside className="sidebar">
      <div className="logo-area">
        <div className="logo">
          pars<em>li</em>
        </div>
        <div className="tagline">Local Parcel Intelligence</div>
      </div>

      <nav className="nav">
        {items.map((it) => (
          <NavLink
            key={it.to}
            to={it.to}
            className={({ isActive }) =>
              `nav-item${isActive ? " active" : ""}`
            }
          >
            <span className="nav-icon">
              <it.Icon />
            </span>
            <span>{it.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <label
          className="dev-toggle-row"
          title="Show diagnostics for the local pipeline"
        >
          <span className="dev-toggle-label">Dev mode</span>
          <button
            type="button"
            className={`toggle-switch${devMode ? " on" : ""}`}
            aria-pressed={devMode}
            aria-label="Toggle dev mode"
            onClick={toggleDev}
          >
            <span className="toggle-track" />
            <span className="toggle-thumb" />
          </button>
        </label>
        <div className="station-status">
          <div className={`status-dot${online ? " online" : ""}`} />
          <span>{online ? "Online" : "Connecting…"}</span>
        </div>
      </div>
    </aside>
  );
}
