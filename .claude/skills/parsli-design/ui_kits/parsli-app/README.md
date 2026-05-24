# Parsli App — UI Kit

A pixel-faithful, click-through React recreation of the live parsli web app. Use it as the starting point for new screens, mocks, and prototypes that need to feel like they belong inside parsli.

## What's here

- **Sidebar** — dark olive shell with logo, nav, status dot.
- **Parcels screen** — stat cards, search + filter pills, parcel list with expandable timelines.
- **Sources screen** — connected accounts, privacy banner, sensor toggles (Email / SMS / Voice / Screenshots).
- **Preferences screen** — theme picker, sync schedule, privacy switches.

Interactions wired into the prototype:
- Click a parcel card to expand its event timeline.
- "Mark received" / "Delete" actions per parcel (Delete confirms then removes).
- Search + filter pills filter the parcel list live.
- "+ Add account" simulates an OAuth flow that finishes in ~1.5s and toasts the result.
- Sync button on an account row shows a syncing badge then toasts completion.
- Sensor cards toggle on/off (mocked — they don't actually wire up new data).

## File layout

```
ui_kits/parsli-app/
├── index.html          ← entry point, wires up React + Babel + scripts
├── styles.css          ← full visual scaffolding, ports the live frontend
├── data.js             ← mock fixtures (shipments, accounts, sensors)
├── atoms.jsx           ← Badge, Button, Spinner, MiniTracker, ActionBanner, Toast
├── StatCard.jsx        ← 4-up dashboard meter
├── Sensor.jsx          ← retro toggle for a data source
├── Banners.jsx         ← PrivacyBanner, PendingRow
├── Sidebar.jsx         ← dark-olive nav shell
├── AccountRow.jsx      ← one connected Gmail account
├── ParcelCard.jsx      ← collapsible parcel card + Timeline
├── screens.jsx         ← ParcelsScreen, SourcesScreen, PreferencesScreen
└── app.jsx             ← App with all top-level state + routing
```

## Design tokens

Every color, type rule, radius, and spacing value resolves to a CSS custom property from `../../colors_and_type.css`. To re-skin (e.g. ship the "Grand Hotel" theme), override those tokens on `:root`.

## Notes on fidelity

- All copy here is the **default voice** — plain, calm, no jargon. The themed "Retro Station" copy (Comms Array, Cargo hold is clear, etc.) is not in the React components; it would be layered on as theme overrides via a string map.
- The original frontend is a single 2,500-line vanilla-JS file; this kit splits it into ~10 small React components without changing the look. The visual recreation is faithful to within a pixel or two.
- The Diagnostics dev-only screen from the live app is omitted — surface it later if needed.
- No real backend. Sync, OAuth, delete — all simulated with `setTimeout` + state.
