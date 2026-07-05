---
version: alpha
name: Mossforge
description: An industrial-warm design system that pairs cream paper surfaces with deep evergreen panels and a single charged lime accent for confident, data-led product pages.
colors:
  primary: "#C5F26E"
  primary-pressed: "#B6E254"
  secondary: "#1B342B"
  secondary-hover: "#244235"
  tertiary: "#2C4A3E"
  neutral: "#F2EFE6"
  surface: "#FFFFFF"
  surface-inverse: "#1B342B"
  surface-inverse-2: "#2C4A3E"
  on-surface: "#1A2A22"
  on-surface-muted: "#5A6A60"
  on-inverse: "#F2EFE6"
  on-inverse-muted: "#A9B6AE"
  border: "#DDD7C6"
  border-inverse: "rgba(255, 255, 255, 0.08)"
  focus: "#C5F26E"
  success: "#3B7A4A"
  warning: "#C58A2E"
  error: "#B23A3A"
typography:
  font-sans: "'Manrope', system-ui, sans-serif"
  font-mono: "'JetBrains Mono', ui-monospace, monospace"
  display-xl:
    fontFamily: "{typography.font-sans}"
    fontSize: "64px"
    lineHeight: 1.04
    letterSpacing: "-0.025em"
    fontWeight: 800
  display-lg:
    fontFamily: "{typography.font-sans}"
    fontSize: "56px"
    lineHeight: 1.05
    letterSpacing: "-0.022em"
    fontWeight: 800
  headline-lg:
    fontFamily: "{typography.font-sans}"
    fontSize: "40px"
    lineHeight: 1.12
    letterSpacing: "-0.018em"
    fontWeight: 700
  headline-md:
    fontFamily: "{typography.font-sans}"
    fontSize: "32px"
    lineHeight: 1.18
    letterSpacing: "-0.014em"
    fontWeight: 700
  headline-sm:
    fontFamily: "{typography.font-sans}"
    fontSize: "24px"
    lineHeight: 1.25
    letterSpacing: "-0.01em"
    fontWeight: 700
  title-md:
    fontFamily: "{typography.font-sans}"
    fontSize: "20px"
    lineHeight: 1.3
    letterSpacing: "-0.005em"
    fontWeight: 700
  title-sm:
    fontFamily: "{typography.font-sans}"
    fontSize: "18px"
    lineHeight: 1.35
    fontWeight: 600
  body-lg:
    fontFamily: "{typography.font-sans}"
    fontSize: "16px"
    lineHeight: 1.55
    fontWeight: 500
  body-md:
    fontFamily: "{typography.font-sans}"
    fontSize: "15px"
    lineHeight: 1.55
    fontWeight: 500
  body-sm:
    fontFamily: "{typography.font-sans}"
    fontSize: "14px"
    lineHeight: 1.5
    fontWeight: 500
  label-sm:
    fontFamily: "{typography.font-sans}"
    fontSize: "13px"
    lineHeight: 1.3
    fontWeight: 600
    letterSpacing: "0.01em"
  eyebrow:
    fontFamily: "{typography.font-mono}"
    fontSize: "12px"
    lineHeight: 1.2
    letterSpacing: "0.14em"
    fontWeight: 500
  metric-xl:
    fontFamily: "{typography.font-mono}"
    fontSize: "44px"
    lineHeight: 1.0
    letterSpacing: "-0.02em"
    fontWeight: 700
  metric-md:
    fontFamily: "{typography.font-mono}"
    fontSize: "20px"
    lineHeight: 1.1
    letterSpacing: "-0.01em"
    fontWeight: 500
  caption-mono:
    fontFamily: "{typography.font-mono}"
    fontSize: "11px"
    lineHeight: 1.25
    letterSpacing: "0.08em"
    fontWeight: 400
rounded:
  none: "0px"
  sm: "8px"
  md: "14px"
  lg: "20px"
  xl: "28px"
  full: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "40px"
  "2xl": "64px"
  "3xl": "96px"
  gutter: "24px"
  container-max: "1200px"
elevation:
  none: "none"
  ambient: "0 1px 0 rgba(27, 52, 43, 0.04), 0 10px 30px -18px rgba(27, 52, 43, 0.25)"
  lift: "0 2px 0 rgba(27, 52, 43, 0.05), 0 24px 48px -24px rgba(27, 52, 43, 0.35)"
  focus-ring: "0 0 0 2px {colors.neutral}, 0 0 0 4px {colors.focus}"
borders:
  hairline: "1px solid {colors.border}"
  hairline-inverse: "1px solid {colors.border-inverse}"
  strong: "1.5px solid {colors.secondary}"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.secondary}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    padding: "14px 22px"
    height: "48px"
  button-primary-hover:
    backgroundColor: "{colors.primary-pressed}"
    textColor: "{colors.secondary}"
  button-secondary:
    backgroundColor: "{colors.secondary}"
    textColor: "{colors.neutral}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    padding: "14px 22px"
    height: "48px"
  button-secondary-hover:
    backgroundColor: "{colors.secondary-hover}"
    textColor: "{colors.neutral}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.on-surface}"
    border: "{borders.hairline}"
    rounded: "{rounded.full}"
    padding: "14px 22px"
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "{borders.hairline}"
    rounded: "{rounded.md}"
    padding: "12px 14px"
    height: "48px"
  input-field-focus:
    border: "1px solid {colors.focus}"
    elevation: "{elevation.focus-ring}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "{borders.hairline}"
    rounded: "{rounded.lg}"
    padding: "24px"
  card-inverse:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-inverse}"
    border: "{borders.hairline-inverse}"
    rounded: "{rounded.lg}"
    padding: "24px"
  checkbox:
    backgroundColor: "{colors.surface}"
    border: "{borders.hairline}"
    rounded: "6px"
    size: "20px"
  checkbox-checked:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.secondary}"
    border: "1px solid {colors.primary}"
  tabs-track:
    backgroundColor: "{colors.neutral}"
    border: "{borders.hairline}"
    rounded: "{rounded.full}"
    padding: "4px"
  tabs-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.secondary}"
    rounded: "{rounded.full}"
    padding: "10px 18px"
  tabs-inactive:
    backgroundColor: "transparent"
    textColor: "{colors.on-surface-muted}"
    rounded: "{rounded.full}"
    padding: "10px 18px"
  metric-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "{borders.hairline}"
    rounded: "{rounded.lg}"
    padding: "20px"
  metric-card-inverse:
    backgroundColor: "{colors.tertiary}"
    textColor: "{colors.on-inverse}"
    border: "{borders.hairline-inverse}"
    rounded: "{rounded.lg}"
    padding: "20px"
  delta-pill:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.secondary}"
    typography: "{typography.eyebrow}"
    rounded: "{rounded.full}"
    padding: "4px 10px"
  icon-badge:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.secondary}"
    border: "{borders.hairline}"
    rounded: "{rounded.md}"
    size: "40px"
---

## Overview

Mossforge is an industrial-warm product language built around three tonal events: warm cream paper, deep evergreen panels, and a single charged lime accent. It is designed to read like a modern manufacturing brand — precise, grounded, optimistic, and quietly technical — so light and dark sections can sit on the same page without losing rhythm.

The system is framework-agnostic CSS. Pages compose from a small set of primitives: pill buttons, hairline-bordered cards, mono numerals, and square icon badges. Lime is rationed: it lands on primary actions, focus rings, signature delta pills, and one chart accent per card. Everything else stays in the cream-to-forest tonal corridor.

Three rules carry the whole system:

1. Tone, not chrome — depth comes from cream-vs-forest contrast and 1px hairlines, not shadows.
2. Pills over rectangles for actions and tabs; hairlined rounded squares for cards and inputs.
3. Mono numerals signal data; geometric sans carries headlines and copy.

## Colors

The palette is a three-tier neutral scaffold (paper, surface, ink) crossed by a two-tier forest tier (Forest, Moss) and a single chromatic accent (Lime Charge). Cream and forest are siblings; lime is the only chromatic event.

| Token            | Hex       | Role                                                              |
| ---------------- | --------- | ----------------------------------------------------------------- |
| `neutral`        | `#F2EFE6` | Paper — page background and base section tone                     |
| `surface`        | `#FFFFFF` | Crisp card and input surface on light sections                    |
| `secondary`      | `#1B342B` | Forest — inverted panels, footer, primary ink, pill CTA on light  |
| `tertiary`       | `#2C4A3E` | Moss — secondary tier inside dark sections and inverted cards     |
| `primary`        | `#C5F26E` | Lime Charge — primary action fill, focus ring, signature accent   |
| `on-surface`     | `#1A2A22` | Pine ink — body and headlines on cream/white                      |
| `on-surface-muted` | `#5A6A60` | Lichen — labels, captions, secondary copy on light                |
| `on-inverse`     | `#F2EFE6` | Paper text on forest panels                                       |
| `on-inverse-muted` | `#A9B6AE` | Muted lichen-on-forest for secondary copy in dark sections        |
| `border`         | `#DDD7C6` | Paper-tinted 1px hairline on light                                |
| `border-inverse` | `rgba(255,255,255,0.08)` | Translucent hairline on forest panels              |
| `focus`          | `#C5F26E` | Focus-visible ring on inputs and controls                         |

Contrast targets:

- Pine ink on Paper: ~13:1 (AAA).
- Pine ink on Lime Charge: ~12:1 (AAA) — used for primary button label.
- Paper on Forest: ~12:1 (AAA) — used for inverted body copy.
- Lichen on Paper: ~5.2:1 (AA) — reserved for labels at 13px+ only.

## Typography

Mossforge uses two free Google fonts and treats them as roles:

- **Manrope** carries display, headlines, body, and UI labels. Weights 400, 500, 600, 700, 800.
- **JetBrains Mono** is reserved for numerals, eyebrows, micro tags, and chart axis labels. Weights 400, 500, 700.

Headlines run weight 700–800 with tight negative tracking to feel architectural. Body sits at weight 500 for a touch of warmth at small sizes. Eyebrow labels use mono uppercase with wide tracking to mark sections without competing with headlines.

Scale (CSS variable → role):

- `--type-display-xl` 64/1.04 → page hero on landing.
- `--type-display-lg` 56/1.05 → secondary hero or section opener.
- `--type-headline-lg` 40/1.12 → section titles.
- `--type-headline-md` 32/1.18 → card group titles.
- `--type-headline-sm` 24/1.25 → component titles.
- `--type-title-md` 20/1.3 → card titles.
- `--type-title-sm` 18/1.35 → list titles.
- `--type-body-lg` 16/1.55 → primary paragraph.
- `--type-body-md` 15/1.55 → dense paragraph.
- `--type-body-sm` 14/1.5 → meta and helper text.
- `--type-label-sm` 13/1.3 → UI labels, buttons.
- `--type-eyebrow` 12 mono uppercase tracked → section eyebrows.
- `--type-metric-xl` 44 mono → signature numerals.
- `--type-metric-md` 20 mono → inline stats.
- `--type-caption-mono` 11 mono tracked → micro tags and axis labels.

## Layout

Pages target a `1200px` content max with a `24px` gutter at desktop, collapsing to single column under `720px`. Vertical rhythm uses a `2xl` (`64px`) section gap and a `3xl` (`96px`) gap between major narratives.

Grid behavior:

- Card grids prefer 3 columns at desktop, 2 at tablet, 1 at mobile.
- Hero sections use a 12-column conceptual grid but a 7/5 split is the canonical layout: 7 columns of copy, 5 columns of visual or stats.
- Dark sections (`section--forest`) span full width with the same internal `--container` width inside, so the cream and forest panels share alignment.

Spacing scale: `xs 4`, `sm 8`, `md 16`, `lg 24`, `xl 40`, `2xl 64`, `3xl 96`.

## Elevation & Depth

The system is mostly flat. Depth is built three ways, in this order of preference:

1. **Tonal contrast** — paper next to forest creates the strongest read of depth.
2. **Hairlines** — 1px borders separate cards, inputs, and dividers. Inverted panels use `rgba(255,255,255,0.08)` borders.
3. **Soft ambient shadow** — only for floating CTAs (`--shadow-ambient`) and on hover/lift states (`--shadow-lift`). Forest panels never carry shadow.

Focus ring: 2px lime offset by 2px of background, expressed as a double box-shadow so it works on both paper and forest backgrounds.

## Shapes

Two shape families coexist:

- **Pills (`--radius-full`)** for primary CTAs, secondary CTAs, tabs, and delta badges. Pills signal action and motion.
- **Rounded rectangles** for cards (`--radius-lg`), inputs (`--radius-md`), icon badges (`--radius-md`), and chart panels (`--radius-lg`). These read as structure and data.

Ornament is restrained: 40px square icon badges with a hairline border sit at the top-left of feature cards; small mono pills carry deltas and tags. There are no decorative gradients, no glow, no glassmorphism.

## Components

### Button

- **Primary (`.btn--primary`)** — pill, lime fill, pine ink label, weight 700. Default 48px height; supports optional leading or trailing Lucide icon.
- **Secondary (`.btn--secondary`)** — pill, forest fill, paper text. Used inside cream sections when the action is structural rather than the headline CTA.
- **Ghost (`.btn--ghost`)** — transparent fill, hairline border, pine ink text. Used for tertiary actions on cards.

Disabled buttons drop to 50% opacity and lose hover lift.

### Input

- White surface, hairline border, `md` radius, 14px horizontal padding, 48px height.
- Labels render in mono uppercase eyebrow above the field.
- Focus-visible adds a lime border + 2px ring via `--shadow-focus`.
- Supports leading Lucide icon at 18px in `--color-on-surface-muted`.

### Card

- `.card` is white, hairline-bordered, `lg` radius, `24px` padding.
- `.card--inverse` flips to moss surface with translucent borders for use inside forest sections.
- Optional `.card__badge` square icon container sits at top-left.
- Optional `.card__footer` row carries actions or metric pills.

### Checkbox

- 20px square, 6px corner radius, hairline border on white.
- Checked fills with lime and shows a forest check glyph from Lucide.
- Focus-visible adds the lime double ring.

### Tabs

- Segmented pill control on a paper or moss track.
- Active tab is lime fill with pine text; inactive tabs are transparent with lichen text and a hover lift.
- Tracks default to `--radius-full` and `4px` inset padding.

### Signature element — Metric Forge Card

The `.metric-card` is the system's data signature. It pairs a square Lucide icon badge, a mono eyebrow, a display mono numeral, a lime delta pill, a four-bar mini chart in lime + forest, and a mono caption row. The same tokens drive both `.metric-card` (paper variant) and `.metric-card--inverse` (forest variant), so it reads identically across light and dark sections.

### Navigation

A slim horizontal nav uses mono uppercase labels in `--color-on-surface-muted`, a wordmark left, and a single primary pill CTA right.

### Icons

Iconography uses **Lucide** (ISC) exclusively. The preview hydrates icons via the official CDN script and styles strokes with `currentColor`. Examples used: `arrow-up-right`, `factory`, `cpu`, `bar-chart-2`, `truck`, `shield-check`, `check`, `search`, `chevron-down`.

## Do's and Don'ts

**Do**

- Use pill shapes for actions and tabs; rounded rectangles for cards and inputs.
- Pair forest panels with cream panels to create the system's signature alternating rhythm.
- Use mono numerals on every metric block; let Manrope carry prose.
- Use lime sparingly: one chromatic event per card or section is the ceiling.
- Use 1px hairlines as the default separator before reaching for shadow.

**Don't**

- Don't apply shadows to forest panels or to inverted cards.
- Don't lower body type under 14px — labels at that size must be mono uppercase eyebrow style.
- Don't use lime as a background fill across large areas; it is reserved for accents and primary actions.
- Don't introduce a second icon library, decorative gradients, or glass effects.
- Don't replace the metric card's mono numeral with sans — the data signature depends on the tabular monospace read.
