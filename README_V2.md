# MERIDIAN V2

Separate application from Meridian v1 (`meridian/`). **Do not** point this package at the v1 database or overwrite v1 code.

## Isolation

| Item | V1 | V2 |
|------|----|----|
| Package | `meridian` | `meridian_v2` |
| CLI | `python -m meridian` | `python -m meridian_v2` |
| Default port | (v1 setting) | `8766` |
| DB | v1 path only | `MERIDIAN_V2_DB` or `~/.meridian_v2/meridian_v2.db` |
| Dist | `MERIDIAN` | `MERIDIAN-V2` |

## Charter

Advisor-only desk: equities + MCX-oriented commodities, signals with Explicit Acknowledge, dual hedge policies (`inventory_hedge`, `vol_harvest`), vega defense reviews, journal intents + fills. **No** broker order routing.

## Current status

- Package skeleton
- Pure engine templates: `meridian_v2/hedge/`, `meridian_v2/vega/`
- Unit tests for engines under `tests/v2/`

UI, SQLite schema, MCX providers, and alert worker are **not** fully wired yet — see `docs/v2/GROK_BUILD_PROMPTS.md`.

## Run tests

```bash
pytest tests/v2 -q
```

## Docs

- `VERSION_2_DECISIONS.md`
- `docs/v2/HEDGE_REBALANCE_SKETCH.md`
- `docs/v2/VEGA_HEDGE_SKETCH.md`
- `docs/v2/ADVANCED_HEDGE_STRATEGIES.md`
- `docs/v2/GROK_BUILD_PROMPTS.md`
