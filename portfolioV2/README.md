# MERIDIAN V2

Local research and hedge-review desk for Indian equities and MCX-oriented commodities.

**This is a different application from MERIDIAN v1.** It does not modify `meridian/`, does not open the v1 database, and must not share a window title with v1.

Advisor only. No Kite, no SmartAPI, no order routing.

## Isolation

| | v1 (`meridian`) | v2 (`meridian_v2`) |
|---|---|---|
| Package | `meridian` | `meridian_v2` |
| Default port | 8787 | **8766** |
| Database | `data/meridian.db` | **`~/MeridianV2/meridian_v2.db`** |
| CLI | `python -m meridian` | `python -m meridian_v2` |
| Window / dist | `MERIDIAN` | **`MERIDIAN-V2`** |
| Location | repo `meridian/` | this folder `portfolioV2/` |

You can run both desks at once. They do not share schema or process state.

## Run

From this directory (`portfolio/portfolioV2`):

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"
python -m meridian_v2 seed
python -m meridian_v2 serve
```

Open http://127.0.0.1:8766 — title **MERIDIAN V2**.

CLI:

```text
python -m meridian_v2 watch list
python -m meridian_v2 watch add GOLD --class commodity
python -m meridian_v2 watch archive 4
python -m meridian_v2 prices
python -m meridian_v2 alerts --once
python -m meridian_v2 alerts worker
```

Laptop poll default for the worker is **60 seconds** (`config/default.yaml` → `alerts.poll_seconds`). Each loop refreshes free-source marks (quality-flagged; international commodity prints are labelled `proxy`, never as MCX contracts), then runs `inventory_hedge`, `vol_harvest`, and `vega_defense`. Alerts still require Explicit Acknowledge. Nothing is sent to a broker.

## What is in v2

1. Watchlist — active / archived, soft cap 50
2. MCX roll-aware continuous vs contract labels
3. Signal engines + Explicit Ack (Accept / Dismiss / Snooze)
4. Journal — intended trades and actual fills (post-mortems)
5. FX context + wording-safe review prompts
6. `inventory_hedge` engine + HEDGE REVIEW
7. `vol_harvest` Δ REVIEW + gamma flags (short gamma is a warning, not an edge)
8. `vega_defense` limits + VEGA REVIEW
9. Intraday alert worker (ack only)
10. Packaging: `scripts/package-windows-v2.ps1` → `dist/MERIDIAN-V2`

Canonical locks live in the parent repo: `VERSION_2_DECISIONS.md`, `docs/v2/HEDGE_REBALANCE_SKETCH.md`, `docs/v2/VEGA_HEDGE_SKETCH.md`.

## Tests

```powershell
python -m pytest
```

## Config

Edit `config/default.yaml` or add `config/local.yaml`. Module flags can disable streams until you want them. Environment prefix: `MERIDIAN_V2_` (for example `MERIDIAN_V2_TEST_DB` for a throwaway SQLite file).
