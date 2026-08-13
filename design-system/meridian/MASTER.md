# MERIDIAN — Design System

Private-banking research desk. Not a retail fintech app.
Dark theme is canonical. Light theme is a refined inverse, never the default.

**Dials:** Variance 3 · Motion 3 · Density 9

---

## Colour

| Token | Hex | Use |
|---|---|---|
| `--void` | `#06080C` | App ground |
| `--ink` | `#0A0D13` | Frame, sidebar |
| `--panel` | `#0E131B` | Surfaces |
| `--panel-2` | `#131922` | Raised / hover |
| `--line` | `#1C2433` | Hairlines |
| `--line-gold` | `rgba(196,163,90,0.18)` | Active / focus |
| `--ivory` | `#E7E2D6` | Primary text |
| `--mist` | `#9AA3B2` | Secondary text |
| `--ash` | `#6B7380` | Labels, meta |
| `--gold` | `#C4A35A` | Brand, regime calm, focus |
| `--gold-dim` | `#8A7340` | Idle gold |
| `--up` | `#4A9B7F` | Gains — muted institutional green |
| `--down` | `#C46B6B` | Losses — muted institutional red |
| `--elevated` | `#C4A35A` | Regime elevated |
| `--stress` | `#B85C4A` | Regime stress |
| `--hold` | `#8B95A8` | Neutral action |

No neon. No gradients as decoration. P&L colour is never the brand colour.

## Typography

- **UI / headings:** IBM Plex Sans (300 / 400 / 500 / 600)
- **Figures:** IBM Plex Mono, `font-variant-numeric: tabular-nums`
- **Wordmark:** IBM Plex Sans 500, 11px, 0.22em tracking
- **Field labels:** 10px, 0.14em tracking, uppercase, `--ash`
- **Hero figures:** 28–34px mono, weight 400
- **Table figures:** 12.5px mono
- **Body / reasoning:** 13px / 1.55 sans

Never use display / oversized fashion type on a working desk.

## Spacing

Dense dashboard scale: 2 / 4 / 8 / 12 / 16 / 24 / 32.
Hairline separators instead of card chrome. Panels share a common grid, not floating cards.

## Motion

150–220ms opacity / colour only. No layout-shifting hover. `prefers-reduced-motion: reduce` disables all of it.

## Charts (later phases)

- Price: candlestick, bull `#4A9B7F` / bear `#C46B6B`, hollow bear optional
- Factors: 5-axis radar + grouped bar fallback
- SHAP: waterfall, 4–12 bars
- Risk: dual-axis line (correlation left, EWMA beta right)

## Anti-patterns

No emoji icons. No generic fintech gradients. No pill soup. No drop shadows on panels. No green as brand. No light-mode default.
