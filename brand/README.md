# LitPilot — Brand Kit

> Literature review, on autopilot.

The mark is a paper plane framed by academic citation brackets `[ ]` — combining the **Pilot** (navigation, flight) and **Literature** (citations, references) sides of the product.

---

## Quick start for AI dev tools

Most coding agents (Cursor, Claude Code, v0, Bolt, etc.) can ingest this folder directly. Point them at:

| You want | Use file |
|---|---|
| Drop-in React component | [`react/LitPilotMark.tsx`](./react/LitPilotMark.tsx) |
| Raw SVG to paste anywhere | [`svg/mark.svg`](./svg/mark.svg) |
| CSS variables | [`tokens.css`](./tokens.css) |
| Tailwind config | [`tailwind.tokens.js`](./tailwind.tokens.js) |
| Typed token export | [`tokens.ts`](./tokens.ts) |
| Plain JSON tokens | [`tokens.json`](./tokens.json) |
| Favicon `<head>` snippet | [`snippets/head.html`](./snippets/head.html) |
| PWA manifest | [`site.webmanifest`](./site.webmanifest) |
| Social card | [`png/og-image-1200x630.png`](./png/og-image-1200x630.png) |

Suggested prompt to your AI tool:

> Use `brand/tokens.css` for colors and `brand/react/LitPilotMark.tsx` for the logo. Wire up favicons from `brand/snippets/head.html`.

---

## Files

```
brand/
├── README.md
├── tokens.json            ← canonical token source
├── tokens.css             ← CSS custom properties
├── tokens.ts              ← TypeScript export
├── tailwind.tokens.js     ← Tailwind theme.extend snippet
├── site.webmanifest       ← PWA manifest
├── svg/
│   ├── mark.svg                       ← primary mark, 64×64
│   ├── mark-reversed.svg              ← for dark backgrounds
│   ├── mark-mono-ink.svg              ← single-colour, ink
│   ├── mark-mono-paper.svg            ← single-colour, paper
│   ├── lockup-horizontal.svg          ← mark + wordmark
│   ├── lockup-horizontal-reversed.svg
│   ├── lockup-stacked.svg
│   ├── lockup-stacked-reversed.svg
│   ├── app-icon-dark.svg              ← rounded square, ink bg
│   ├── app-icon-light.svg             ← paper bg
│   ├── app-icon-accent.svg            ← accent bg
│   ├── favicon.svg
│   ├── favicon-dark.svg
│   └── og-image.svg                   ← 1200×630 social card
├── png/                               ← rasterised at standard sizes
│   ├── mark-{32,64,128,256,512,1024}.png
│   ├── favicon-{16,32,48}.png
│   ├── apple-touch-icon-180.png
│   ├── icon-{192,512,1024}.png
│   ├── lockup-horizontal-{960,1920}.png
│   ├── lockup-stacked-640.png
│   └── og-image-1200x630.png
├── react/
│   └── LitPilotMark.tsx               ← React component, zero deps
└── snippets/
    └── head.html                      ← <head> tags for favicons + OG
```

---

## Colour

| Token | Hex | Usage |
|---|---|---|
| `--lp-ink` | `#0E1633` | Primary mark, headings, body text on light |
| `--lp-ink-soft` | `#1B2547` | Secondary text |
| `--lp-accent` | `#F26A1F` | "Pilot" letters, plane underside, CTAs |
| `--lp-accent-soft` | `#FDE3D2` | Backgrounds, badges |
| `--lp-paper` | `#F6F4EE` | Light backgrounds, "on ink" text |
| `--lp-line` | `#E4E1D8` | Hairlines, dividers |
| `--lp-muted` | `#8C92A8` | Disabled, metadata |

The accent is used **sparingly** — the "Pilot" word and the plane's underside fold. Never recolour the brackets in accent; they stay ink.

---

## Type

| Role | Family | Weights |
|---|---|---|
| UI / wordmark | **Geist** | 400, 500, 600 |
| Code / labels | **Geist Mono** | 400, 500 |

Both are free on Google Fonts. The wordmark uses `font-weight: 600` with `letter-spacing: -0.04em`.

```html
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
```

---

## Usage

**Clear space**: at least 1× the height of the brackets on all sides.
**Minimum size**: mark 16px (favicon), lockup 80px wide.
**Don't**: recolour the plane to non-brand colours, rotate the mark, swap the order of "Lit" and "Pilot", or use the wordmark without the mark in dense UI.

---

## Regenerating

PNGs are rasterised from the SVG sources. To regenerate at custom sizes, open any SVG and resize — they're written by hand and stay sharp.
