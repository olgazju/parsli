# Parsli Design System

> **Parsli** — *Local Parcel Intelligence*. A privacy-first parcel tracker that runs entirely on your laptop. It scans Gmail (later: SMS, voice, screenshots), parses shipment events with a local AI model, and shows a "cargo manifest" of everything currently in flight — without anything leaving the device.

The product positions itself as a **retro space-station "comms array"** that quietly picks up signals about parcels in your life and decodes them. The visual brand carries that idea: warm-cream surfaces, dusty greens, a single dark-olive sidebar that reads like a control panel, lever-style sensor toggles, and emoji used as friendly iconography.

This design system is the toolkit a designer needs to build new screens, mocks, slides, and prototypes that feel like they belong inside Parsli.

---

## Sources used to build this system

| Source | Notes |
|---|---|
| **GitHub — [olgazju/parsli](https://github.com/olgazju/parsli)** | Primary source. The full frontend lives in `frontend/index.html` (single-file React-free SPA) and is the canonical visual reference. The repo README explains the backend pipeline and product surface. |
| **GitHub — [olgazju/parsli `dashboard.py`](https://github.com/olgazju/parsli/blob/main/dashboard.py)** | A standalone Python diagnostic dashboard. Confirms status taxonomy and copy. |
| **Brand brief** (in-conversation) | Color palette, type choices, mascot direction, micro-interaction list, texture rules. Treated as authoritative where it disagrees with the frontend. |

**Open these directly** when you need detail this system doesn't capture — the frontend is single-file and very readable.

The original repo materials this system was built from are kept in `reference/` for fast lookup.

---

## How to use this system

Drop one CSS file into any artifact and you have Parsli's colors, type, spacing, radius, and motion tokens:

```html
<link rel="stylesheet" href="colors_and_type.css">
<body class="parsli-typography">…</body>
```

The `parsli-typography` class on a wrapper gives sensible defaults for `h1`, `h2`, `p`, `.meta`, `.small-caps`, `.mono`, etc. Or skip it and use the raw `--c-*`, `--t-*`, `--sp-*`, `--r-*` tokens directly.

For full product mocks, see the **UI kit** in [`ui_kits/parsli-app/`](ui_kits/parsli-app/) — pixel-faithful recreations of Parsli's screens as React components.

---

## Content fundamentals

Parsli's default voice is **plain, calm, and human** — the product gets out of the way and tells you what's happening. The cute "retro space-station" vocabulary that lives in the codebase is a **theme overlay** (the "Retro Station" skin), not the brand baseline. New surfaces should default to plain language; themed phrasing only swaps in when a theme is active.

### Voice & tone — the default

- **Plain English, not jargon.** "Sources", not "Comms Array". "Email", not "Comms array sensor". "No active parcels", not "Cargo hold is clear". If a label is opaque to a first-time user, rewrite it.
- **Conversational, but quiet.** Short sentences. No exclamation points. The app narrates *what's happening* — it rarely addresses the user directly.
- **You-form, but rarely.** Reserve "you/your" for moments that need to feel personal — privacy banners, onboarding hero, errors that depend on user action.
- **No marketing speak.** No "powerful", "seamless", "supercharge", "AI-powered". Describe what the product does, not how impressive it is.
- **Confidence from calm.** Concrete numbers and verbs do the work — *"Sync complete — 12 new, 184 processed"*, not *"Done!"*

### Casing & rhythm

- **Sentence case** for everything — headings, buttons, nav, banners. *"Add a source"*, *"Sources"*, *"Connected accounts"*.
- **UPPERCASE small-caps with wide tracking** for section labels and stat labels — *`ACTIVE`*, *`CONNECTED ACCOUNTS`*, *`LOCAL PARCEL INTELLIGENCE`*. This is the brand's signature texture, applied to metadata and meters — *never* to actual content.
- **lowercase** for the logo: `parsli` (the "li" tinted sage).
- **Status labels stay lowercase**: `delivered`, `in transit`, `customs pending`. Looks like a manifest readout.
- **Mono font** (Courier New) for tracking numbers, order IDs, batch IDs, latency — machine-generated character strings.

### Default lexicon

| Concept                    | Default copy           |
|----------------------------|------------------------|
| Nav item for accounts      | **Sources**            |
| Connect a Gmail account    | **Add a source**       |
| Status: app reachable      | **Online**             |
| Status: app unreachable    | **Connecting…**        |
| Empty state                | **No active parcels**  |
| Loading state              | **Loading…**           |
| Privacy line               | *"Your data never leaves this device."* |
| Dev-only screen            | **Diagnostics**        |

### Tone examples (default voice)

- **Empty state:** *"No active parcels. Connect a source to start scanning, or sit back and enjoy the quiet."*
- **Privacy banner:** *"Your data never leaves this device. All processing happens locally — no cloud, no servers. Powered by a local AI model."*
- **Onboarding hero:** *"Connect a Gmail account to start tracking parcels. Everything runs locally on your machine."*
- **Toast after sync:** *"Sync complete — 12 new, 184 processed."*
- **Action banner inside a card:** *"Action required — expand to see details."* (em-dash; never "Click here")
- **Sign-in pending:** *"Waiting for Google sign-in — check the window that just opened."*

### Themes — when language gets cute

Parsli ships a **theme picker** with whimsical skins. The active skin can re-color *and re-name* surfaces. Themed copy belongs to the skin, not the product. Today there's one shipped theme ("Retro Station") with three slots planned (Grand Hotel, Shire Post, Magical Post). When you ship a new theme, give it a complete copy pass — empty state, nav items, source names, status messages — so the language stays internally consistent.

**Retro Station overlay** — the cargo / mail-station vocabulary the code already uses:

| Default term         | Retro Station theme                  |
|----------------------|--------------------------------------|
| Sources              | **Comms Array**                      |
| Email source         | **Comms array** sensor               |
| SMS source           | **Short-range scanner**              |
| Voice source         | **Audio decoder**                    |
| Screenshot source    | **Visual scanner**                   |
| Online               | **Station online**                   |
| Offline              | **Station unresponsive**             |
| Add a source         | **Calibrate Comms Array**            |
| No active parcels    | "Cargo hold is clear"                |
| Loading…             | "Scanning cargo manifest…"           |
| Your data never leaves this device | *"…never leaves this station."* |

The themed copy follows the same craft rules — no exclamation points, sentence-case, em-dashes, mono for IDs — it just trades concrete nouns for whimsical ones. Future themes should do the same: pick a coherent metaphor, swap nouns and verbs, leave the structure alone.

### Emoji usage — yes, deliberately

Emoji **are** part of the brand. The live product uses them as nav icons and decorative glyphs because they match the cozy, handmade tone better than line icons would. Specifically:

- 📦 Parcels  · 📥 Sources  · ⚙️ Preferences  · 🔬 Diagnostics
- 🔒 Privacy banner  · 📭 Empty state  · ✓ Marked received

Treat them as **first-class iconography**, not decoration. They should be readable at 16–22px and align centred in a `width: 20px` slot. See the **Iconography** section below for the substitution rules when a richer icon is needed.

---

## Visual foundations

The look is **warm, muted, slightly dusty**. Think: a well-loved enamel control panel from the 1970s, gently lit. Not chrome, not neon, not glossy. Greens and tans dominate. Pops of red, yellow, blue and a single pink are reserved for status.

### Palette philosophy

- The **whole page** sits on `#e5dfd4` (slightly darker cream) so cards in `#f5f0e8` cream lift off it without needing a shadow.
- The **sidebar** is the only dark surface in the default theme — deep olive `#3d4a3a`. It anchors the screen and acts as the "control panel."
- **Status colors are semantic, not decorative.** Don't use the jacket-red for a "primary" button just because it pops; it means *something is wrong*. The "primary" button uses dark olive.
- **No gradients** for backgrounds or buttons. Color is flat. The only gradient-ish moment is the soft glow on the "current step" tracker dot.

### Backgrounds

- Solid color, full-bleed cream-on-cream. **No imagery, no full-bleed photos** in the live product.
- **A subtle dot-grid texture** runs across the whole page background: `radial-gradient(circle, rgba(61,74,58,.12) 1px, transparent 0)` at `22px × 22px`. It's barely visible but adds the "graph paper / manifest" feel.
- Cards never have an inner gradient. The only thing that breaks a card's flat-color rule is the **3px bottom border** on stat cards and the **4px left border** on parcel cards — both used to encode status.

### Borders & strokes

- All borders are **thin and low-contrast**. `1px solid #ddd8cf` is the default, `1px solid #c8bfb2` for slightly more prominence.
- Status-bearing strips are **3–4px**: bottom on stat cards, left on parcel cards.
- Focus state on inputs swaps the border to `--c-sage`. No focus ring, no glow.

### Shadows

- **No drop shadows in resting state.** Depth comes from layering surfaces (`bg → surface → surface-hi`) and from the dark sidebar.
- **One soft shadow** is allowed: on parcel-card hover, `0 2px 12px rgba(61,74,58,.08)` — barely there.
- The toast notification uses a slightly stronger shadow `0 4px 20px rgba(0,0,0,.18)` because it floats above content.

### Corner radii

- Cards: **12px**
- Buttons: **10px**
- Inputs: **10px**
- Pills, badges, large CTAs: **20px** (full-pill on small heights)
- Chips, tags, observability pills: **4–6px**
- Avatars: **10px** rounded square, not circle
- Status dots, tracker dots, indicator dots: full circle

### Typography in use

- The primary font is **Nunito** (rounded, friendly, slightly bubbly). Quicksand and Fredoka are alternates that hit the same retro-modern tone — load via the @import in `colors_and_type.css`.
- **Type scale is compact** — body is 14px, card titles 15px, page headings only 24px. The brand doesn't shout; it labels. Density is moderate.
- **Letter-spacing is the trick.** Wide tracking on labels (2.5px on small-caps, 1px on stat labels) gives the manifest/control-panel rhythm without needing a different font.
- The **mono font** (Courier New) is reserved for IDs, codes, latency, batch numbers — anything that's machine-generated and might need to be read character-by-character.

### Layout rules

- **Fixed sidebar, 208px wide**, dark olive, sticky to the left edge.
- **Main content area** has `max-width: 800px` and 32px / 36px padding. The app is not a wide dashboard — it's a focused list.
- **Grids are usually 4-up** for stat cards / sensors / diagnostics. They never reflow below 4 columns inside the 800px content area.
- Generous **vertical rhythm**: 16–24px between sections, 8–10px between cards in a list.

### Animation & motion

- **Short, friendly, no bounce.** Most transitions are 120–180ms with a standard `cubic-bezier(.4, 0, .2, 1)`. The expand-timeline animation is 350ms.
- **Spinners** are a thin border-top ring, sage-tinted.
- **The "current step" tracker dot pulses** with a soft outer halo (`box-shadow: 0 0 0 3px rgba(135,206,235,.25)`) — the only resting motion in the UI.
- **Action banners pulse** the red dot at 2s `ease-in-out` infinite — the only attention-getting motion.
- The brand brief calls for a **cargo-shuttle sliding along a dotted route** for progress bars, a **conveyor-belt loop** for loading, a **"thunk" bounce** on delivery complete, a **mascot shrug** on errors, and a **mascot napping** in empty states. These are aspirational — the live product currently uses emoji + spinners instead.

### Hover & press states

- **Buttons** get `opacity: 0.88` on hover (primary) or a background swap to `--c-bg` (secondary). `:active` shrinks to `scale(0.97)` — quick `transform .1s`. No color change on press.
- **Nav items** swap to a soft inset `rgba(255,255,255,.08)` background; the active item gets a left border in sage `--c-sage` (3px).
- **Filter pills** flip to filled dark-olive when active (`background: --fg-1`, `color: --c-cream`).
- **Cards** lift on hover with the single allowed shadow. No transform.
- **Tag remove buttons** turn their square red on hover (`badge-red-bg` background) — feedback that this destroys something.

### Transparency & blur

- **No backdrop blur** anywhere. The aesthetic is solid, opaque, papery.
- Transparency is used only for: sidebar dividers (`rgba(255,255,255,.07)`), the received-card overlay (`rgba(245,240,232,.8)`), the page-background dot grid (`rgba(61,74,58,.12)`).

### Imagery & illustration

- The brand brief allows **hand-drawn parcel mascot** illustrations (a shrugging box for errors, a napping box for empty states). These don't exist in the live product yet — placeholder emoji or text are used instead.
- **No photography** in product UI. The brand can use stock photography in marketing, but it should skew **warm, slightly desaturated, soft daylight**, never cool/cold/blue.
- **No isometric 3D**, **no gradient meshes**, **no abstract blobs**, **no AI-rendered hero images**. Keep it flat, warm, slightly imperfect.

---

## Iconography

Parsli's icon system is unusual and worth getting right.

### Default: emoji as iconography

The live frontend uses emoji as nav icons and decorative glyphs. **This is intentional**, not a placeholder. Emoji match the cozy, hand-made tone of the brand better than a clean line-icon set would. Use them at 16–22px in a centred 20px slot.

Canonical usage:

| Surface                | Emoji   | Notes |
|------------------------|---------|---|
| Parcels nav            | 📦      | also used in empty-state context |
| Comms Array nav        | 📡      | the dish, used for connectivity / accounts |
| Preferences nav        | ⚙️       | gear |
| Diagnostics nav        | 🔬      | microscope, dev-only |
| Privacy banner         | 🔒      | always with a green tinted bg |
| Empty cargo            | 📭      | empty mailbox |
| Onboarding hero        | 📡      | repeated — "calibrate the array" |
| Marked received        | ✓        | the only ascii glyph; never a checkmark emoji |

### When you need a richer icon

The current frontend has **one** inline SVG icon — the search-bar magnifying glass, drawn as a 2.5-stroke circle + line in `currentColor`. **Use that pattern** when emoji is too informal for the context (form inputs, table headers, dropdown carets). Specifically:

- 24×24 viewBox, `fill: none`, `stroke: currentColor`, `stroke-width: 2.5`, `stroke-linecap: round`, `stroke-linejoin: round`.
- Color via `currentColor` only — never hardcode a hex.

This matches the **Lucide** icon set almost exactly. **If you need a new line icon, pull it from [Lucide](https://lucide.dev/) via CDN** — `https://unpkg.com/lucide-static@latest/icons/<name>.svg`. The default stroke weight (2) is slightly lighter than the in-product magnifier, so set `stroke-width: 2.5` for visual parity.

**Flagged substitution:** The repo has no icon font, no SVG sprite, and no asset directory — only the inline magnifier. We've documented Lucide as the standard for new line icons. If the user provides a hand-drawn icon set later, switch to that.

### Logos & marks

The wordmark is the only "logo" — there is no separate icon mark in the live product. See `assets/parsli-logo.svg` for an SVG version we built from the live HTML/CSS.

Hand-rolled SVG icons in mocks **are allowed** when they encode product-specific concepts that no icon set will carry (the cargo-shuttle progress indicator, the lever-style sensor toggles). Keep them in the line-icon style above.

---

## Index — what's in this project

```
.
├── README.md                ← you are here
├── SKILL.md                 ← skill manifest, for Claude Code / agent use
├── colors_and_type.css      ← all design tokens (colors, type, spacing, radius, motion)
├── assets/                  ← logo, brand SVGs, mascot placeholders
├── preview/                 ← cards for the Design System review tab (16+ specimens)
├── reference/               ← original source material from olgazju/parsli
│   ├── parsli-frontend.html ← full live frontend, single file
│   ├── dashboard.py         ← standalone Python diagnostic dashboard
│   └── parsli-repo-README.md
└── ui_kits/
    └── parsli-app/          ← interactive React UI kit, faithful to the live product
        ├── index.html       ← click-through prototype of the app
        ├── README.md
        └── *.jsx            ← Sidebar, ParcelCard, StatCard, SensorPanel, …
```

---

## Caveats & known gaps

- **No real icon font / SVG sprite exists** in the upstream repo. We've documented Lucide as the substitution for new line icons; the rest stays emoji.
- **No mascot illustrations exist** in the upstream repo. The brand brief describes a parcel-box mascot (shrugging, napping); we've left placeholders where those would live.
- **No marketing site, no slide deck** in scope — the UI kit covers the product itself only.
- The brand brief lists "Quicksand" and "Fredoka" as alternates to Nunito. The live product uses **Nunito**; we've loaded all three so designers can A/B alternate fonts, but Nunito is the default.
