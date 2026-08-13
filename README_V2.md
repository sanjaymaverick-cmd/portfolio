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

- Package skeleton (`config`, `cli`, `app` health)
- **Pure engines implemented:**
  - `meridian_v2/hedge/engine.py` — inventory + vol_harvest-capable Δ reviews
  - `meridian_v2/vega/engine.py` — vega_defense limits and sizing
- Unit tests: `tests/v2/`
- **Implementation details:** [`docs/v2/ENGINE_IMPLEMENTATION.md`](docs/v2/ENGINE_IMPLEMENTATION.md)

UI, SQLite schema, MCX providers, journal, and alert worker are **not** fully wired yet — see `docs/v2/GROK_BUILD_PROMPTS.md`.

## Quick engine import

```python
from meridian_v2.hedge import aggregate_exposure, evaluate_symbol
from meridian_v2.vega import aggregate_vega, evaluate_vega
from meridian_v2.domain.enums import PolicyKind, RegimeLabel
```

## Run tests

```bash
pytest tests/v2 -q
```

## CLI

```bash
python -m meridian_v2 info
```

## Docs

- `docs/v2/ENGINE_IMPLEMENTATION.md` — **code-level engine details**
- `VERSION_2_DECISIONS.md`
- `docs/v2/HEDGE_REBALANCE_SKETCH.md`
- `docs/v2/VEGA_HEDGE_SKETCH.md`
- `docs/v2/ADVANCED_HEDGE_STRATEGIES.md`
- `docs/v2/GROK_BUILD_PROMPTS.md`
