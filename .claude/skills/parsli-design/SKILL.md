---
name: parsli-design
description: Use this skill to generate well-branded interfaces and assets for Parsli (a local-first parcel tracker), either for production or throwaway prototypes/mocks. Contains essential design guidelines, colors, type, fonts, assets, and UI kit components for prototyping.
user-invocable: true
---

Read the `README.md` file inside this skill first — it covers the brand's voice, content fundamentals, visual foundations, iconography rules, and tells you what's where.

Other files worth knowing about:
- `colors_and_type.css` — drop into any HTML artifact for the full token system (colors, type, spacing, radius, motion).
- `assets/` — logo SVGs and the parcel mark.
- `preview/` — small specimen cards covering every color, type rule, component, and brand atom; useful for inspiration and copy-paste.
- `ui_kits/parsli-app/` — a faithful React recreation of the full Parsli app (sidebar + Parcels / Sources / Preferences screens) split into small reusable components. Lift components from here when building new screens.
- `reference/` — the original `olgazju/parsli` source material this system was built from. Read these when the design system doesn't capture detail you need.

If creating visual artifacts (slides, mocks, throwaway prototypes), copy assets out of this skill and create static HTML files for the user to view. If working on production code, copy assets and follow the rules in `README.md` to design as a Parsli expert.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask 4–10 focused questions, and act as an expert designer who outputs HTML artifacts *or* production code depending on the need.

**Two things that often trip people up:**
1. **Default copy is plain English**, not the cargo-station vocabulary. "Sources", "No active parcels", "Online". The cute "Comms Array / Cargo hold is clear" copy belongs to the *Retro Station theme* skin, not the brand baseline. See the Content Fundamentals section of the README for the full default lexicon and themed overrides.
2. **Emoji are first-class iconography**, not placeholder. 📦 📥 ⚙️ 🔬 🔒 📭 are the canonical nav and decorative glyphs. Don't replace them with hand-rolled SVG unless you're styling for a theme that calls for something different.
