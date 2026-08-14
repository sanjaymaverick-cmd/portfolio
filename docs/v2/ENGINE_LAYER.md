# Meridian engine + chart layer

v1 keeps its scoring, tape, SHAP, and risk **math**. Only the words got simpler.  
v2 is the full desk: those review habits plus Greeks, gamma scalping, vega actions, and the same chart contract.

This note is the production contract: architecture, templates, PnL logic, scalp / vega approach, chart plan, JSON shapes, and how the math stays private.

---

## 1. How the two desks relate

```
v1  meridian/          equity book, tape, factors, SHAP, EOD
                       language simplified · candles via Lightweight Charts
                       math stays in Python

v2  meridian_v2/       watch, MCX, journal, three hedge streams
                       + full Greeks snapshot
                       + Daily PnL and Gamma Scalping PnL
                       + six vega actions (each shows Δ Γ ν Θ)
                       + gamma-scalp walkthrough (helping vs hurting)
                       + the same chart contract
```

They do not share a database. v2 can read a v1 snapshot (`import-v1`) but never writes back.

v2 is the complete unified risk and signal desk. It includes every review habit of v1 (plain words, “(not an order)”, finished chart JSON only) plus the Greeks, scalp, and vega modules. v1 algorithms are not copied into v2 and are not changed.

---

## 2. Data flow

1. Legs and marks sit in SQLite.
2. Pure functions build a `GreekSnapshot` (delta lots, gamma, vega, theta, two PnL lines).
3. `explain_scalp` turns that snapshot into a helping / hurting walkthrough.
4. `compose_review` turns the snapshot into a `PlainReview` (title always contains “not an order”).
5. `plan_vega_actions` sizes six reviews and the side-effect on the other Greeks.
6. `ChartPayload` is candles + diamonds + lines + zones + windows. No model coefficients.
7. The browser only fetches `/api/review/{symbol}` and `/api/chart/{symbol}` (v2) or `/api/holdings/{id}/chart` (v1).

```
SQLite legs / bars
        │
        ▼
 Python engine (private)
   greeks_book · gamma_scalp · vega_strategies · signals
        │
        ├── PlainReview + GammaScalpReport + VegaAction[]
        └── ChartPayload (candles, markers, levels, zones, windows)
                │
                ▼
         FastAPI JSON
                │
                ▼
   Jinja + Lightweight Charts
   (words + picture only)
```

---

## 3. Combining Delta, Gamma, Vega, Theta with the two PnL lines

| Greek | What the person is told | Number on the card |
|---|---|---|
| **Delta** | Leftover direction, in lots | `delta_lots` |
| **Gamma** | Long = a move can help if you stay hedged. Short = a move can hurt. Flat = no scalp story. | `gamma` + `gamma_sign` |
| **Vega** | Rupees for each 1 point of vol, and how full the line is | `vega`, `utilization` |
| **Theta** | What one quiet day does | `theta` |

**Daily PnL** = net theta for one day. If the market sits still, this is the expected rupee effect of time.

**Gamma Scalping PnL** = `½ × Γ × (ΔS)² × multiplier` for a chosen move (default 1%). Sign follows gamma: long can add extra profit, short can add extra loss.

**Net after a move-day** = Daily PnL + Gamma Scalping PnL. If long gamma and `|scalp| ≥ |theta|`, the move more than pays for time.

Scenario pick (first match wins):

1. `|vega|` over the line → over-limit vega  
2. Short gamma and paying time → high-risk corner  
3. Short gamma and collecting time → not a harvest  
4. Long gamma and paying time → the usual long-gamma trade-off  
5. Leftover delta with flat gamma → residual delta  
6. Quiet tape (`|scalp| + 1 < |theta|`) → time is the main story  
7. Else → balanced full Greeks review  

---

## 4. Gamma scalping mechanics

The engine starts the picture **delta-flattened**, then moves the underlier up and down by the chosen amount.

- New leftover delta ≈ old delta + Γ × ΔS  
- Futures to review = − that leftover delta, snapped to the lot step  
- Locked extra = the ½ Γ (ΔS)² term  

**Long gamma (helping):** price up → extra long delta → review *selling* futures high. Price down → extra short delta → review *buying* futures low. That is the helpful loop.

**Short gamma (hurting):** the same loop runs backward. You review buying high and selling low. This is never called an edge or a harvest.

If current `|delta|` is already outside the rehedge band (default 1 lot), the desk adds a flatten suggestion. Nothing is sent to a broker.

---

## 5. Vega risk actions

Six sized reviews. Each one also reports Δ, Γ, ν, Θ after the step.

| Key | What it does |
|---|---|
| `limit_cap` | Stay under the hard vega line (shows utilization %) |
| `cut_options` | Shrink this option toward flat vega |
| `hedge_options` | Pair with an opposite / different option |
| `book_balance` | Even long and short vega across names |
| `regime_limit` | Calm 120% / Elevated 100% / Stress 70% of the usual line |
| `time_reduce` | Inside 21 days, keep `dte/21` of today’s vega |

None of these is an order. The human accepts, dismisses, snoozes, or does nothing.

---

## 6. Simple-language message templates

Every review uses this shape:

1. Clear title + “(not an order)”  
2. Delta / Gamma / Vega / Theta in simple words + numbers  
3. Daily PnL line  
4. Gamma Scalping PnL line  
5. Model suggestion (exact size and direction, review only)  
6. Choices: Accept and write an intended-trade note / Dismiss / Snooze / Do nothing  

| Scenario | Title |
|---|---|
| Balanced | Full Greeks review (not an order) |
| Long gamma + time cost | Long gamma, paying time (not an order) |
| Short gamma + time benefit | Short gamma, collecting time (not an order) |
| Short gamma + paying time | Short gamma and paying time (not an order) |
| Over-limit vega | Vega is over the line (not an order) |
| Quiet market | Quiet tape — time is the main story (not an order) |
| Residual delta | Leftover delta drift (not an order) |
| Combined four Greeks | Delta, gamma, vega and theta together (not an order) |
| Gamma scalping | Gamma scalping status (not an order) |
| Vega action | Vega action to review (not an order) |

Canonical text lives in `meridian_v2/domain/templates.py`. Live fill-in is `compose_review`.

v1 uses the same language rule on equity notes: “What is helping / What is holding it back”, always “(not an order)”. Scoring, SHAP, and risk formulas are unchanged.

---

## 7. Lightweight Charts plan

TradingView Lightweight Charts is a picture box. It receives finished OHLCV and overlay JSON.

| Overlay | Meaning |
|---|---|
| Candles | Last marks, refreshed about every 30 seconds |
| Green diamond | Look at a long / entry |
| Red diamond | Look at a short / exit |
| Gold / grey lines | Key levels already computed (averages) |
| Soft filled band | Recent range, not a target |
| Shaded days | Higher-attention window |
| Gold line | Optional smoothed close |
| Tooltip | Date, OHLC, and a simple confidence score |

The chart never imports a pricing model. Changing a formula means changing a Python module and a test, not a template.

v1 price detail uses the same contract at `GET /api/holdings/{id}/chart`. SHAP bars and ρ/β charts stay as they are (they are not the signal overlay).

---

## 8. Example JSON

### Review (`GET /api/review/GOLD`)

```json
{
  "symbol": "GOLD",
  "as_of": "2026-08-14",
  "stale": false,
  "greeks": {
    "delta_lots": 2.0,
    "gamma": 0.32,
    "gamma_sign": "long",
    "vega": 240000,
    "theta": -4800,
    "utilization": 1.2,
    "vega_limit": 200000,
    "daily_pnl": -4800,
    "gamma_scalp_pnl": 159,
    "move_pct": 0.01,
    "scalp_helps": true
  },
  "review": {
    "title": "Vega is over the line (not an order)",
    "scenario": "over_limit_vega",
    "status": [
      "Delta: +2.00 lots of leftover direction (+2.00 lots).",
      "Gamma: Long gamma — a move can help if you stay hedged (+0.3200).",
      "Vega: 240,000 ₹ for each 1 point of vol.",
      "Theta: you pay about ₹4,800 each day as time passes (-4,800 ₹/day)."
    ],
    "daily_pnl": "Daily PnL: about -₹4,800 today if the market sits still (this is mostly time decay).",
    "gamma_scalp_pnl": "Gamma Scalping PnL: a 1.0% move could add about +₹159 if you keep delta small (gamma scalping is helping).",
    "suggestion": "Model suggestion: sell 4.0 lots (review only). Vol-sensitivity is larger than the line you set.",
    "choices": [
      "Accept and write an intended-trade note",
      "Dismiss this review",
      "Snooze and look again later",
      "Do nothing and keep watching"
    ]
  },
  "gamma_scalp": {
    "posture": "long",
    "helps": true,
    "hurts": false,
    "needs_rehedge": true,
    "suggested_futures_lots": -2.0,
    "steps": [
      { "label": "Start (delta flattened)", "delta_lots": 0.0, "hedge_lots": 0.0, "locked_pnl": 0 },
      { "label": "If price rises 1.0%", "delta_lots": 1.01, "hedge_lots": -1.0, "locked_pnl": 159 },
      { "label": "If price falls 1.0%", "delta_lots": -1.01, "hedge_lots": 1.0, "locked_pnl": 159 }
    ]
  },
  "actions": [
    {
      "key": "limit_cap",
      "title": "Stay under the vega line",
      "enabled": true,
      "opt_lots": -4.0,
      "effects": { "delta": -1.92, "gamma": -0.08, "vega": -220000, "theta": 3200 },
      "after_vega": 20000,
      "after_util": 0.1,
      "note": "Used 120% of the 200,000 ₹/vol-pt line."
    }
  ]
}
```

### Chart (`GET /api/chart/GOLD` or `/api/holdings/12/chart`)

```json
{
  "symbol": "GOLD",
  "label": "GOLD · CONTINUOUS",
  "quality": "proxy",
  "candles": [
    { "time": "2026-08-07", "open": 109, "high": 111, "low": 108, "close": 110, "volume": 11 }
  ],
  "markers": [
    {
      "time": "2026-08-07",
      "position": "belowBar",
      "shape": "diamond",
      "color": "#4A9B7F",
      "text": "Look at a long / entry · 72"
    }
  ],
  "levels": [{ "price": 108.2, "title": "Slow average", "color": "#C4A35A" }],
  "zones": [{ "low": 99, "high": 111, "title": "Recent range", "color": "rgba(196,163,90,0.12)" }],
  "windows": [{ "start": "2026-08-04", "end": "2026-08-07", "title": "Higher-attention window" }],
  "signal": [{ "time": "2026-08-07", "value": 108.4 }],
  "legend": {
    "long": "Green diamond = look at a long / entry",
    "short": "Red diamond = look at a short / exit"
  },
  "poll_seconds": 30
}
```

Missing on purpose: weights, SHAP φ, IV surface, per-leg construction, hedge ratios, regime sensors.

---

## 9. Keeping the math private

- The frontend never imports a pricing model.
- It never sees per-leg construction beyond the net numbers the desk already stores.
- Changing a formula means changing a Python module and a test, not a template.
- User-facing words stay simple enough for a 10-year-old and a 60-year-old. The numbers stay exact.
- Every review says “(not an order)”. The desk never buys or sells.

---

## Where the code lives

| Concern | v2 | v1 |
|---|---|---|
| Snapshot + two PnL lines | `risk/greeks_book.py` | — (equity book only) |
| Gamma scalping walkthrough | `risk/gamma_scalp.py` | — |
| Six vega actions | `risk/vega_strategies.py` | — |
| Plain reviews | `domain/reviews.py` | `recommendations/copy.py` |
| Template catalog | `domain/templates.py` | — |
| Chart DTO | `signals/chart_payload.py` | `ui/chart_payload.py` |
| Chart fetch | `signals/chart_service.py` | `ui/chart_service.py` |
| Picture box | `ui/static/js/meridian-v2.js` | `ui/static/js/meridian.js` |
