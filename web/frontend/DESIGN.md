# Stellar — Design Specification

> The design language for the **Multi-Source Candidate Data Transformer** frontend.
> Every token below is implemented in [`src/styles.css`](src/styles.css) and consumed by
> [`src/App.jsx`](src/App.jsx). The palette is **adapted from the live Resonate CRM dashboard**
> (`resonate-crm-crm.vercel.app/dashboard`) — the same product whose landing hero the cinematic
> **"Stellar Genesis"** intro ([`src/landing/intro/constants.ts`](src/landing/intro/constants.ts))
> was lifted from. Result: near-black neutral-warm surfaces, a single **soft muted amber** accent,
> **serif** display headings, and white metric numbers. `styles.css` is the source of truth for exact values.

---

## 1. Overall Design Philosophy

**Style.** Cinematic dark-mode "warm cosmos." A premium, filmic dashboard that feels like the
still-glowing aftermath of the intro's stellar genesis — copper light on a warm void.

**Design principles**
- **One universe.** The intro opens on a warm-only cosmos (copper, champagne, ember, cream over
  a near-black warm void). The app inherits that palette exactly, so the reveal is seamless.
- **Warm-only discipline.** *No blues, no purples, anywhere.* Every neutral is tinted warm; every
  accent lives on the amber→copper→ember arc. (This replaces the old cool blue/purple UI.)
- **Deterministic, legible data.** The product's core value is deterministic provenance +
  confidence. Type and color make the *source of truth* obvious: monospace for machine facts
  (IDs, keys, provenance, dates), gold for the LLM lane, copper for deterministic merges.
- **Quiet luxury.** Restraint over decoration — generous negative space, one accent family,
  hairline borders, soft glow instead of hard chrome.
- **Depth through light, not lines.** Elevation reads through warm glow + layered surface tints,
  echoing the intro's bloom and vignette.

**Brand personality / emotional feel.** Confident, precise, cinematic, expensive. Calm but alive
(subtle glow, grain, motion). "Aerospace instrument panel meets luxury editorial."

**Premium / luxury / minimal / enterprise characteristics.** Minimal surface count, luxury color
restraint, enterprise information density in the data cards. Premium cues: gradient wordmark,
monospace micro-labels with wide tracking, copper focus glow, film grain, staggered entrance.

**Inspiration sources.** The in-repo "Stellar Genesis" R3F film (proto-sun → impact → genesis
flash); anamorphic bloom / lens-flare cinematography; premium dark dashboards (Linear, Vercel)
re-tuned to a warm rather than neutral/cool key.

---

## 2. Color System

All colors are CSS custom properties on `:root`. Palette core mirrors `PALETTE` in the intro.

### Brand / cosmic core
| Token | HEX | RGB | HSL | Role |
|---|---|---|---|---|
| `--void` | `#050403` | 5, 4, 3 | 30° 25% 2% | Deepest warm black — intro's opening frame |
| `--brand-copper` | `#e09a52` | 224, 154, 82 | 30° 70% 60% | **Primary brand** — the hero star's gold |
| `--champagne` | `#e8a05c` | 232, 160, 92 | 29° 75% 64% | Bright warm gold — secondary accent |
| `--ember` | `#ff7a2f` | 255, 122, 47 | 22° 100% 59% | Orange plasma — hot emphasis |
| `--hot-core` | `#fff3d6` | 255, 243, 214 | 42° 100% 92% | Incandescent highlight / glow |
| `--deep-amber` | `#8c4a16` | 140, 74, 22 | 26° 72% 32% | Bronze shadow — deep gradient stop |
| `--cream` | `#f5efe6` | 245, 239, 230 | 36° 42% 93% | Warm off-white — primary text |

### Semantic accent aliases (soft muted amber — the CRM "New campaign" button)
| Token | Value | Role |
|---|---|---|
| `--amber-soft` | `#e8a56a` | **Primary UI accent** — soft peach-amber |
| `--accent` (primary) | `var(--amber-soft)` `#e8a56a` | Buttons, logo, focus, interactive |
| `--accent-bright` (secondary) | `#f2bd8a` | Lighter peach — hover highlights |
| `--accent-hot` (tertiary) | `var(--ember)` `#ff7a2f` | Reserved for hot moments |

> The brand-core tokens (`--brand-copper #e09a52`, `--champagne #e8a05c`, `--ember`, etc.) remain
> defined as the intro's cosmic reference, but the **product UI accent is the softer `--amber-soft`**
> to match the calmer CRM dashboard.

### Status / functional
| Token | HEX | Role |
|---|---|---|
| `--success` | `#6cc38a` | Warm-leaning green (enrichment OK) |
| `--warning` | `#e0a230` | Amber (fits palette natively) |
| `--error` | `#ff6b4a` | Ember-red |
| `--info` | `#e8a05c` | Champagne (no blue "info") |

### Pipeline semantics
| Token | HEX | Role |
|---|---|---|
| `--llm` | `#e0a94a` | LLM gap-fill lane (gold) |
| `--win` | `#e07a4a` | Deterministic merge winner (copper-orange) |

### Backgrounds & surfaces (neutral-warm dark ramp)
| Token | HEX | Role |
|---|---|---|
| `--bg-0` | `#0d0c0b` | Page base — near-black, barely warm |
| `--bg-1` | `#121110` | App frame |
| `--panel` | `#171614` | Card / control surface |
| `--panel-2` | `#1e1d1a` | Inset fields, chips, nested surfaces |
| `--panel-3` | `#262420` | Hover / raised nested surfaces |

There is a single card surface (`--panel`) — the "sidebar color" concept from a classic dashboard
does not apply (this is a single-column tool with no sidebar). If a sidebar is added, use `--bg-1`.

### Borders
| Token | Value | Role |
|---|---|---|
| `--line` | `#2c2925` | Default border |
| `--line-soft` | `#201e1b` | Quiet dividers inside cards |
| `--line-strong` | `#3a352f` | Emphasized / hover border |
| `--hairline` | `rgba(232,165,106,0.09)` | Amber hairline over dark |

### Text
| Token | HEX | Role |
|---|---|---|
| `--text` | `#f4efe7` | Primary — warm white (KPI numbers, wordmark) |
| `--text-dim` | `#cdc6ba` | Secondary — table values |
| `--muted` | `#8f887c` | Tertiary / labels / captions |
| `--faint` | `#645d52` | Placeholder / disabled label |
| `--on-accent` | `#2a1c0d` | Text on the amber button |

### Interaction states
| State | Treatment |
|---|---|
| Hover (surface) | border → `--line-strong`, background → `--panel-3`, optional 1–2px lift |
| Hover (primary btn) | `translateY(-1px)` + `--glow-copper` |
| Active | `translateY(0)` + `brightness(0.96)` |
| Focus | `--glow-focus` = `0 0 0 3px rgba(224,154,82,0.28)` |
| Disabled | `opacity: 0.45`, no shadow/transform, `cursor: not-allowed` |
| Overlay / scrim | intro flash `#fff`; modal scrim (if added) `rgba(5,4,3,0.66)` |

### Gradients (softened to the CRM's flat, muted amber)
| Token | Definition |
|---|---|
| `--grad-brand` | `linear-gradient(180deg, #eeb079 0%, #e49b58 100%)` — the amber button |
| `--grad-heat` | `linear-gradient(90deg, #e8955a, #f2bd8a)` — confidence bars, switch |
| `--grad-surface` | `linear-gradient(155deg, #1b1a17, #141311)` — panels / cards |
| `--grad-text` | `linear-gradient(100deg, #f6f1e8, #e8c9a3)` — optional (headings are solid serif) |
| `--grad-ambient` | 3 **faint** warm radial glows so the page reads as flat near-black, on `body::before` |

### Dark mode
The app is **dark-only by design** (it emerges from a black-void film). The palette above *is* the
dark theme. A light theme is intentionally out of scope; `prefers-color-scheme` is not branched.

---

## 3. Typography

**Font families**
- Serif (display / headings): `--font-serif` = `"Newsreader", "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, Cambria, ui-serif, serif` — the CRM's editorial headings ("Dashboard", "Campaigns").
- Sans (UI / data): `--font-sans` = `"Inter", "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif`
- Mono (micro-labels / IDs): `--font-mono` = `ui-monospace, "SF Mono", SFMono-Regular, "Cascadia Code", Menlo, Consolas, monospace`

> System-stack based (zero web-font payload). Preferred faces ("Newsreader", "Inter") render if present,
> else the native fallback. To match the reference exactly, add a web font — e.g. link **Newsreader** in
> `index.html` and it drops into `--font-serif` automatically. Base `font-feature-settings: "kern","liga"`, antialiased.

**Type scale**
| Role | Size | Weight | Tracking | Line-height |
|---|---|---|---|---|
| Display / H1 | `clamp(30px, 4.6vw, 46px)` **serif** | 500 | −0.01em | 1.05 |
| Card title / H2 | 23px **serif** | 500 | 0 | 1.2 |
| Section label / H4 | 11px **mono** | 500 | 0.14em, UPPERCASE | 1.4 |
| Eyebrow | 11px **mono** | 500 | 0.28em, UPPERCASE | 1 |
| KPI label | 14px sans | 400 | 0 | 1.4 |
| KPI value | 34px sans | 600 | −0.02em | 1.1 |
| Body / paragraph | 15px | 400 | 0 | 1.55 |
| Sub / lead | 14px | 400 | 0 | 1.5 |
| Caption / meta | 12–13px | 400–500 | 0–0.02em | 1.4 |
| Micro-label (KPI/ctl) | 10–10.5px **mono** | 500 | 0.16–0.18em, UPPERCASE | 1.3 |
| Button | 14px | 650 | 0.01em | 1 |
| Badge | 9.5px **mono** | 600 | 0.1em, UPPERCASE | 1 |

**Heading hierarchy.** Eyebrow (mono, amber) → H1 (**serif**, warm-white) → sub (muted). Inside cards:
H2 name (**serif**) → mono H4 field labels (amber) → body values.

**Paragraph.** `--text-dim` at 14–15px / 1.5, max width ~62ch for the lead.

**Caption.** `--muted`, 12–13px; machine captions (IDs, dates) switch to mono.

**Button / navigation typography.** Sans 650 weight, near-zero tracking; there is no persistent nav
bar — the topbar is the only chrome, using the eyebrow + gradient title pattern.

---

## 4. Spacing System

**Base unit:** 4px. Scale tokens `--s-1 … --s-16`:

| Token | px | Token | px |
|---|---|---|---|
| `--s-1` | 4 | `--s-6` | 24 |
| `--s-2` | 8 | `--s-8` | 32 |
| `--s-3` | 12 | `--s-10` | 40 |
| `--s-4` | 16 | `--s-12` | 48 |
| `--s-5` | 20 | `--s-16` | 64 |

**Margins / padding.** Cards pad `24px` head / `24px` body sides; fields `16px` vertical. Controls
panel pads `24px`. App gutter `24px` desktop → `16px` mobile.

**Container width.** `--container: 1040px`, centered, with `24px` side gutters.

**Grid system.** CSS Grid throughout — controls: 2-col (`1fr 1fr`); KPIs: `repeat(auto-fit, minmax(150px,1fr))`;
skills: `repeat(auto-fill, minmax(230px,1fr))`.

**Breakpoints.** `720px` (single-column collapse); `640px` legacy inputs. Mobile-first fluid below.

**Section spacing.** Topbar → controls `32px`; controls → results `32px`; card → card `20px`; KPI row
bottom `24px`.

---

## 5. Border Radius

| Token | px | Applied to |
|---|---|---|
| `--r-xs` | 6 | source tags, small inline chips |
| `--r-sm` | 8 | file-button, dropdown menu items |
| `--r-md` | 10 | buttons, inputs, selects, skill cards, notices, provenance table, KV |
| `--r-lg` | 14 | KPI cards |
| `--r-xl` | 18 | candidate cards, controls panel |
| `--r-2xl` | 24 | dialogs / modals (if added) |
| `--r-pill` | 999 | chips, badges, confidence bar, switch |

| Component | Radius |
|---|---|
| Buttons | `--r-md` (10) |
| Cards | `--r-xl` (18) |
| Inputs / selects | `--r-md` (10) |
| Dialogs | `--r-2xl` (24) |
| Badges | `--r-pill` |
| Chips | `--r-pill` |
| Dropdowns | menu `--r-md`, items `--r-sm` |
| Tables | wrapper `--r-md`, clipped corners |
| Navigation/topbar | n/a (borderless hero) |

---

## 6. Shadows & Elevation

| Token | Value | Use |
|---|---|---|
| `--sh-1` | `0 1px 2px rgba(0,0,0,.4)` | Buttons at rest, level 1 |
| `--sh-2` | `0 8px 24px -12px rgba(0,0,0,.6)` | Cards / KPIs / controls, level 2 |
| `--sh-3` | `0 18px 48px -18px rgba(0,0,0,.72)` | Card hover, level 3 |
| `--sh-modal` | `0 40px 120px -24px rgba(0,0,0,.85)` | Modals / drawers, level 4 |
| `--glow-copper` | `0 0 0 1px rgba(224,154,82,.22), 0 12px 40px -14px rgba(224,154,82,.35)` | Primary hover glow |
| `--glow-focus` | `0 0 0 3px rgba(224,154,82,.28)` | Focus ring |
| `--inset-top` | `inset 0 1px 0 rgba(255,243,214,.05)` | Top highlight on panels |

**Elevation ladder.** 0 flat → 1 rest (`sh-1`) → 2 surface (`sh-2` + `inset-top`) → 3 hover (`sh-3`)
→ 4 overlay (`sh-modal`). Shadows are dark drops; *emphasis* (hover/focus) is warm glow, echoing the
intro's bloom.

**Blur.** Backdrop blur `6px` (intro skip pill / any glass surface). Ambient grain sits at 4% opacity;
glow radii up to `120px`.

---

## 7. Component Library

Every component below is styled in `styles.css`. States: **rest / hover / active / focus / disabled /
loading**. Motion uses `--dur` (200ms) + `--ease-out` unless noted.

### Buttons
- **Primary** (`button`): `--grad-brand` fill, `--on-accent` text, weight 650, radius 10, `sh-1`.
  Hover: `translateY(-1px)` + `--glow-copper`. Active: settle + `brightness(.96)`. Focus: `--glow-focus`.
  Disabled: `opacity .45`, flat.
- **Secondary** (`button.secondary`): `--panel-2` fill, `--line-strong` border, `--text`. Hover:
  `--panel-3` + copper border.
- Size: single size (11×20px). For a small variant use 8×14px + 13px text.

### Inputs / Selects
- Fill `--panel-2`, border `--line`, radius 10, 10–12px padding. Focus → copper border + `--glow-focus`.
  Select has a custom copper caret (inline SVG). File input has a custom `::file-selector-button`
  (panel-3 pill, champagne text, copper hover).
- **Textarea** (pattern): identical to input, `min-height: 96px`, `resize: vertical`.

### Switch (checkbox)
- 40×22 pill; track `--panel-3`→`--grad-heat` when checked; 16px knob slides 18px; focus glow.

### Cards
- `--panel` surface, `--line` border, radius 18, `sh-2`, entrance `rise` animation. Hover: `--line-strong`
  border + `sh-3`. Header uses a `panel-2→transparent` gradient with a `--line-soft` underline.

### KPI / Metric cards
- `--grad-surface`, radius 14, left 3px `--grad-heat` accent bar. `kpi-label` (mono, 10px, tracked) +
  `kpi-value` (26px, `--hot-core`; `.gold` variant → `--llm`) with a small `kpi-unit`.

### Tables (KV + Provenance)
- Header row: mono 10px uppercase, `--panel-2` bg, tracked. Rows 7px pad, `--line-soft` dividers,
  hover `rgba(224,154,82,.05)`. Wrapper radius 10, clipped. Provenance method colored: `--win` / `--llm`.

### Chips / Badges / Source tags
- **Chip**: pill, `--panel-2`, `--line` border; hover → copper border + text brighten.
- **Source tag** (`.src`): mono, small, `rgba(224,154,82,.12)` bg + champagne text.
- **Badge (LLM)**: gold pill, mono 9.5px uppercase.

### Confidence bar
- 16px pill track (`--panel-2`), fill width = %, color from a warm HSL scale (ember-red→gold→green),
  `currentColor` glow, mono % label. Width tweens over `--dur-slow`.

### Status / Notices / Toasts
- **Status** row with optional spinner (`.loading`). **Notice** `.ok` (green tint) / `.warn` (amber tint).
  A toast (pattern) = notice styling, fixed bottom-right, `sh-modal`, slide-in.

### Skeleton loader (pattern)
- `--panel-2` block, radius `--r-md`, animated shimmer sweep (`--grad-surface` at 1.4s linear).

### Empty state (pattern)
- Centered mono eyebrow + muted line + secondary button, inside a dashed `--line` card.

### Modal / Drawer / Command palette / AI chat / Avatars / Progress / Pagination / Search / Tooltip / Accordion / Tabs
These are **patterns extending the tokens** (not yet all instantiated in this single-view tool):
- **Modal**: `--panel` card, radius 24, `--sh-modal`, scrim `rgba(5,4,3,.66)`, scale-in 0.98→1.
- **Drawer**: same surface, slides from right, `--sh-modal`.
- **Command palette**: modal + top search input + `--r-sm` result rows, copper active row.
- **AI chat**: see §14.
- **Avatar**: circle, `--grad-brand` fallback, mono initials in `--on-accent`.
- **Progress bar**: confidence-bar track + `--grad-heat` fill.
- **Pagination**: pill buttons, active = `--grad-brand`.
- **Search bar**: input + leading copper icon.
- **Tooltip**: `--panel-3`, `--line-strong`, radius `--r-sm`, 12px, `sh-2`.
- **Accordion**: `.prov-toggle` pattern (mono header, ▸/▾ affordance).
- **Tabs**: mono labels, active underline `--grad-heat`.

---

## 8. Icons

- **Library:** none bundled — glyphs are Unicode (`⚠ ✓ ▸ ▾ ⏎ ·`) plus inline SVG for the select caret
  and file button. Recommended addition: **Lucide** (outline, 1.5–2px stroke) to match the airy line feel.
- **Stroke width:** 1.5px (small) / 2px (default) if Lucide is added.
- **Default sizes:** 14 / 16 / 20 / 24.
- **Filled vs outline:** outline default; filled reserved for status glyphs (✓ success, ⚠ warn/error).
- **Color rules:** inherit `currentColor`; copper for interactive/section markers, `--muted` for inert,
  status colors for state.

---

## 9. Layout System

- **Sidebar:** none (single-column tool). Reserved width if added: 260px, surface `--bg-1`.
- **Header/topbar:** borderless hero — eyebrow + gradient H1 + sub; ~`32px` bottom margin. No fixed height.
- **Content width:** `--container` 1040px, centered, `24px` gutters.
- **Dashboard grid:** KPI row `auto-fit minmax(150px,1fr)`; results are a vertical stack of full-width cards.
- **Card layout:** header (name + overall confidence) over body (field sections divided by hairlines).
- **Responsive behavior:**
  - **Desktop (>720px):** 2-col controls, multi-col KPI/skills grids, right-aligned overall confidence.
  - **Tablet (≤720px):** controls collapse to 1 col; card header stacks; overall confidence left-aligns.
  - **Mobile (≤640px):** full-width everything, reduced gutters (`16px`), single-column grids.

---

## 10. Motion & Animation

| Token | Value |
|---|---|
| `--dur-fast` | 120ms |
| `--dur` | 200ms |
| `--dur-slow` | 320ms |
| `--ease` | `cubic-bezier(0.4, 0, 0.2, 1)` (standard) |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` (premium expo-out entrance) |

- **Hover animations:** cards/skills lift 1–2px; buttons lift + glow; chips brighten. All `--dur` / `--ease-out`.
- **Page / reveal transition:** the intro fades over `900ms ease` then unmounts (`StellarIntro.jsx`);
  cards then stagger in via `@keyframes rise` (opacity + 12px translate, `--dur-slow` `--ease-out`).
- **Loading:** `@keyframes spin` 0.7s linear ring on `.status.loading`.
- **Skeleton:** shimmer sweep 1.4s linear (pattern).
- **Micro-interactions:** switch knob slide (`--ease-out`), focus-ring fade, confidence-bar width tween
  (`--dur-slow`), select-caret rotate on open (pattern).
- **Modal / drawer:** scale-in 0.98→1 / slide-in, `--dur-slow` `--ease-out`; scrim fade `--dur`.
- **Chart animations:** bar width / line draw-on over `--dur-slow`.
- **Reduced motion:** `@media (prefers-reduced-motion: reduce)` collapses all animation/transition to ~0
  and disables the intro film entirely.

---

## 11. Charts & Data Visualization

There is no chart *library* — visualization is CSS/SVG primitives keyed to the palette.

- **Palette (categorical):** `#e09a52` → `#ff7a2f` → `#e0a94a` → `#8c4a16` → `#f5efe6` (copper, ember,
  gold, bronze, cream). Sequential: `--deep-amber` → `--ember` → `--hot-core`.
- **Confidence scale (diverging):** warm HSL ramp `hsl(12,78%,52%)` (low) → gold → `hsl(130,78%,52%)` (high).
- **Grid / axis:** `--line-soft` gridlines, `--muted` mono axis labels (10px, tracked).
- **Tooltip:** `--panel-3` surface, `--line-strong` border, `sh-2`, mono values.
- **Legend:** mono uppercase micro-labels + color dots.
- **KPI presentation:** big `--hot-core` number + mono tracked label + left heat accent bar (see §7).
- **Dashboard metrics style:** KPI cards row above the data stack; provenance/confidence tables for detail.

---

## 12. Forms

- **Labels:** mono, 10.5px, `0.16em` tracked, uppercase, `--muted` (the `.ctl > span`).
- **Required indicator:** copper asterisk `*` after the label (pattern).
- **Helper text:** `--muted`, 12px, below field.
- **Validation / error state:** border → `--error`, `box-shadow: 0 0 0 3px rgba(255,107,74,.25)`,
  error message `--error` 12px.
- **Success state:** border → `--success`, matching soft ring.
- **Focus ring:** `--glow-focus` (copper) + copper border.
- **Input spacing:** `8px` label→field, `16px` between fields, `12px` field→helper.

---

## 13. Tables

- **Header style:** mono 10px uppercase tracked, `--panel-2` background, `--muted` text.
- **Row height:** ~30px (7px vertical padding), comfortable-compact.
- **Hover:** row background `rgba(224,154,82,.05)`.
- **Dividers:** `--line-soft`, last row borderless; wrapper radius 10 clipped.
- **Sorting indicators (pattern):** ▲/▼ copper glyph after active header.
- **Filters (pattern):** inline chips / select above table.
- **Pagination (pattern):** pill controls, active = `--grad-brand`.
- **Empty state:** muted italic (`null` shown as `<em class="muted">null</em>`).
- **Selection (pattern):** checkbox column, selected row `rgba(224,154,82,.08)` + copper left border.
- Provenance method cells are semantically colored (`--win` copper-orange, `--llm` gold).

---

## 14. AI Elements

The product has an optional **LLM gap-fill** lane; its visual language is the **gold** family so AI
contribution is always distinguishable from deterministic data.

- **AI badge:** `.badge-llm` — gold pill, mono 9.5px uppercase, appears on any field the LLM filled.
- **AI accent color:** `--llm` `#e0a94a` (distinct from `--win` copper-orange for deterministic merges).
- **Enrichment notice:** `.notice.ok` (green, succeeded) / `.notice.warn` (amber, skipped/failed).
- **KPI:** "LLM Gap-fills" KPI uses `.kpi-value.gold`.
- **Prompt box (pattern):** textarea styling + gold focus ring + send button (`--grad-brand`).
- **Message bubbles (pattern):** user = `--panel-2`; assistant = `--panel` with a gold left border.
- **Thinking / streaming (pattern):** three-dot pulse in `--llm`; streamed text with a copper caret;
  shimmer skeleton while awaiting first token.

---

## 15. Design Tokens

All tokens live on `:root` in [`src/styles.css`](src/styles.css). Summary:

```css
:root {
  /* brand / cosmic reference (from the intro) */
  --void:#050403; --brand-copper:#e09a52; --champagne:#e8a05c; --ember:#ff7a2f;
  --hot-core:#fff3d6; --deep-amber:#8c4a16; --cream:#f5efe6;
  /* accents — soft amber (CRM) */
  --amber-soft:#e8a56a; --accent:var(--amber-soft); --accent-bright:#f2bd8a; --accent-hot:var(--ember);
  /* status */
  --success:#6cc38a; --warning:#e0a230; --error:#ff6b4a; --info:var(--champagne);
  --llm:#e0a94a; --win:#e07a4a;
  /* surfaces — neutral-warm dark */
  --bg-0:#0d0c0b; --bg-1:#121110; --panel:#171614; --panel-2:#1e1d1a; --panel-3:#262420;
  --line:#2c2925; --line-soft:#201e1b; --line-strong:#3a352f; --hairline:rgba(232,165,106,.09);
  /* text — warm white → warm grays */
  --text:#f4efe7; --text-dim:#cdc6ba; --muted:#8f887c; --faint:#645d52; --on-accent:#2a1c0d;
  /* radii */  --r-xs:6; --r-sm:8; --r-md:10; --r-lg:14; --r-xl:18; --r-2xl:24; --r-pill:999px;
  /* spacing */ --s-1:4 … --s-16:64 (4px base);
  /* shadow */  --sh-1 --sh-2 --sh-3 --sh-modal --glow-copper --glow-focus --inset-top;
  /* type */    --font-serif --font-sans --font-mono;
  /* motion */  --dur-fast:120ms --dur:200ms --dur-slow:320ms --ease --ease-out;
  /* layout */  --container:1040px;
}
```

- **Spacing scale:** `4·8·12·16·20·24·32·40·48·64`.
- **Radius scale:** `6·8·10·14·18·24·999`.
- **Shadow scale:** `sh-1 → sh-2 → sh-3 → sh-modal` (+ two glows + inset).
- **Typography tokens:** `--font-sans`, `--font-mono` (see §3 for the scale).
- **Color tokens:** see §2.

**Tailwind mapping (if you migrate to Tailwind):**
```js
// tailwind.config.js — theme.extend
colors: {
  void:'#050403', copper:'#e09a52', champagne:'#e8a05c', ember:'#ff7a2f',
  hotcore:'#fff3d6', bronze:'#8c4a16', cream:'#f5efe6',
  panel:{DEFAULT:'#16110b',2:'#1e1810',3:'#271f15'},
  line:{DEFAULT:'#342a1d',soft:'#241d14',strong:'#463829'},
},
borderRadius:{ xs:'6px',sm:'8px',md:'10px',lg:'14px',xl:'18px','2xl':'24px' },
boxShadow:{ e1:'0 1px 2px rgba(0,0,0,.4)', e2:'0 8px 24px -12px rgba(0,0,0,.6)',
            e3:'0 18px 48px -18px rgba(0,0,0,.72)' },
fontFamily:{ sans:['Inter','Segoe UI','sans-serif'], mono:['ui-monospace','SF Mono','monospace'] },
transitionTimingFunction:{ out:'cubic-bezier(.16,1,.3,1)' },
```

---

## 16. Frontend Stack

| Layer | Choice |
|---|---|
| Framework | **React 19** |
| Build tool | **Vite 5** (`base:"./"`, `/api` proxy → FastAPI :8000) |
| CSS | **Hand-authored CSS + custom properties** (no CSS framework) |
| Component library | None — bespoke components in `App.jsx` + `styles.css` |
| Icon library | None bundled (Unicode + inline SVG); Lucide recommended |
| Animation library | CSS keyframes/transitions for the app; **GSAP** drives the R3F intro |
| 3D / intro | **three.js + @react-three/fiber + @react-three/postprocessing** (Stellar Genesis film) |
| Chart library | None — CSS/SVG primitives |
| State management | React hooks (`useState`/`useEffect`/`useMemo`) — no external store |
| Font source | System stacks (zero web-font payload) |

---

## 17. UI Patterns

- **Card composition:** header (identity + one headline metric) → hairline-divided body sections →
  optional collapsible detail (provenance). One surface, one accent, generous padding.
- **Dashboard composition:** hero (eyebrow → gradient title → sub) → controls panel → KPI row →
  data card stack. Scannable top-to-bottom, densest at the bottom.
- **Section hierarchy:** mono uppercase micro-labels mark every section; the eye reads label → value.
- **Information density:** airy chrome, dense data. Controls and KPIs breathe; cards pack structured
  detail (skills grid, KV tables, provenance) enterprise-tight.
- **Visual rhythm:** consistent 4px-based spacing; repeated pill/hairline/gradient-accent motifs;
  copper as the single recurring highlight.
- **Alignment:** left-aligned content; right-aligned single metric (overall confidence) on desktop;
  baseline alignment within experience rows.
- **White-space usage:** 24–32px between major sections, 16px within; whitespace (not borders) carries
  most separation — hairlines only where grouping needs reinforcing.
- **Component consistency:** every surface uses the same radius/border/shadow ladder; every accent is a
  palette token; every machine fact is mono; every LLM contribution is gold. No off-palette one-offs.

---

### Provenance of this spec
Palette core = `PALETTE` in [`src/landing/intro/constants.ts`](src/landing/intro/constants.ts).
Tokens & components = [`src/styles.css`](src/styles.css). Consumption = [`src/App.jsx`](src/App.jsx).
No backend files were changed.
