# MERIDIAN V2

Local research and hedge-review desk for NSE/BSE equities and MCX-oriented commodities.

**V2 is a different application from v1.** Do not edit `meridian/` to add v2 features. Do not open or migrate `meridian.db`.

Advisor only. No Kite, no SmartAPI, no order routing.

App root: [`portfolioV2/`](portfolioV2/)  
Package: `meridian_v2`  
Build prompts: [`docs/v2/GROK_BUILD_PROMPTS.md`](docs/v2/GROK_BUILD_PROMPTS.md)

## Isolation

| | v1 (`meridian`) | v2 (`meridian_v2`) |
|---|---|---|
| Location | `meridian/` | `portfolioV2/meridian_v2/` |
| Package | `meridian` | `meridian_v2` |
| CLI | `python -m meridian` | `python -m meridian_v2` |
| Port | 8787 | **8766** |
| Database | `data/meridian.db` | **`~/MeridianV2/meridian_v2.db`** (Windows: `%USERPROFILE%\MeridianV2\meridian_v2.db`) |
| Window / dist | `MERIDIAN` | **`MERIDIAN-V2`** |
| Env prefix | `MERIDIAN_` | `MERIDIAN_V2_` |

Both desks can run at once. They do not share schema or process state.

## How to run

From `portfolioV2/`:

```powershell
cd C:\Users\BHAGWAN\portfolio\portfolioV2
python -m pip install -e .
python -m meridian_v2 seed
python -m meridian_v2 serve
```

Open http://127.0.0.1:8766 — browser / window title is **MERIDIAN V2**.

```text
python -m meridian_v2 watch list
python -m meridian_v2 watch add GOLD --class commodity
python -m meridian_v2 watch archive 4
python -m meridian_v2 prices
python -m meridian_v2 regime
python -m meridian_v2 score
python -m meridian_v2 backtest GOLD
python -m meridian_v2 export --out desk-brief.md
python -m meridian_v2 import-csv --file names.csv --kind watch
python -m meridian_v2 import-v1
python -m meridian_v2 alerts --once
python -m meridian_v2 alerts worker
```

Alert worker poll default: **60 seconds**. Each loop refreshes free-source marks, then runs `inventory_hedge`, `vol_harvest`, and `vega_defense`. Reviews still need Explicit Acknowledge (Accept / Dismiss / Snooze). Nothing is sent to a broker.

Package for Windows (does not touch v1 scripts):

```powershell
.\scripts\package-windows-v2.ps1
```

Output: `dist\MERIDIAN-V2\`.

## What v2 contains

1. Watchlist — active / archived, soft cap 50  
2. MCX roll-aware CONTINUOUS vs CONTRACT labels  
3. Signals + Explicit Ack  
4. Journal — intended trades + actual fills (post-mortems)  
5. FX context + wording-safe REVIEW prompts  
6. `inventory_hedge` → HEDGE REVIEW  
7. `vol_harvest` → Δ REVIEW (short gamma is a warning, not an edge)  
8. `vega_defense` → VEGA REVIEW  
9. Intraday alert worker (ack only)  
10. Isolated packaging → `MERIDIAN-V2`

Canonical locks: `VERSION_2_DECISIONS.md`, `docs/v2/HEDGE_REBALANCE_SKETCH.md`, `docs/v2/VEGA_HEDGE_SKETCH.md`.

## Config

`portfolioV2/config/default.yaml` (override with `local.yaml`). Module flags can mute a stream. Tests: `python -m pytest portfolioV2/tests`.
