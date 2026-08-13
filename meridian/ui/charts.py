from __future__ import annotations

from decimal import Decimal

from meridian.storage.schema import PriceBar

UP = "#4A9B7F"
DOWN = "#C46B6B"
GOLD = "#C4A35A"
INK = "#0E131B"
LINE = "#1C2433"
MIST = "#9AA3B2"
IVORY = "#E7E2D6"
ASH = "#6B7380"


def sparkline(values: list[float], *, width: int = 56, height: int = 16) -> str:
    if len(values) < 2:
        return ""
    lo = min(values)
    hi = max(values)
    span = (hi - lo) or 1.0
    points: list[str] = []
    for index, value in enumerate(values):
        x = index / (len(values) - 1) * width
        y = height - ((value - lo) / span) * (height - 2) - 1
        points.append(f"{x:.1f},{y:.1f}")
    color = UP if values[-1] >= values[0] else DOWN
    joined = " ".join(points)
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
        f'aria-hidden="true"><polyline fill="none" stroke="{color}" stroke-width="1.2" '
        f'points="{joined}"/></svg>'
    )


def price_chart_html(symbol: str, bars: list[PriceBar]) -> str:
    if len(bars) < 2:
        return ""
    try:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
    except ImportError:
        return _svg_line(symbol, bars)

    dates = [bar.bar_date for bar in bars]
    closes = [float(bar.close) for bar in bars]
    figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.78, 0.22],
    )
    figure.add_trace(
        go.Candlestick(
            x=dates,
            open=[float(bar.open) for bar in bars],
            high=[float(bar.high) for bar in bars],
            low=[float(bar.low) for bar in bars],
            close=closes,
            increasing_line_color=UP,
            decreasing_line_color=DOWN,
            increasing_fillcolor=UP,
            decreasing_fillcolor=DOWN,
            whiskerwidth=0.4,
            name=symbol,
        ),
        row=1,
        col=1,
    )
    for window, color in ((20, GOLD), (50, MIST), (200, ASH)):
        if len(closes) >= window:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=_sma(closes, window),
                    mode="lines",
                    line=dict(width=1, color=color),
                    name=f"SMA{window}",
                    hoverinfo="skip",
                ),
                row=1,
                col=1,
            )
    colors = [UP if float(bar.close) >= float(bar.open) else DOWN for bar in bars]
    figure.add_trace(
        go.Bar(
            x=dates,
            y=[float(bar.volume) for bar in bars],
            marker_color=colors,
            opacity=0.45,
            name="Volume",
            showlegend=False,
        ),
        row=2,
        col=1,
    )
    figure.update_layout(
        paper_bgcolor=INK,
        plot_bgcolor=INK,
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", color=MIST, size=11),
        margin=dict(l=48, r=12, t=8, b=24),
        height=360,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=10)),
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        bargap=0.15,
    )
    figure.update_xaxes(gridcolor=LINE, zeroline=False, showline=False, tickfont=dict(size=10))
    figure.update_yaxes(
        gridcolor=LINE,
        zeroline=False,
        tickfont=dict(family="IBM Plex Mono, Consolas, monospace", size=10, color=IVORY),
        tickprefix="₹",
        row=1,
        col=1,
    )
    figure.update_yaxes(gridcolor=LINE, showticklabels=False, row=2, col=1)
    return figure.to_html(
        full_html=False,
        include_plotlyjs=False,
        config={"displaylogo": False, "modeBarButtonsToRemove": ["lasso2d", "select2d"]},
        div_id=f"px-{symbol.lower()}",
    )


def _sma(values: list[float], window: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for index, value in enumerate(values):
        total += value
        if index >= window:
            total -= values[index - window]
        if index >= window - 1:
            out[index] = total / window
    return out


def _svg_line(symbol: str, bars: list[PriceBar]) -> str:
    closes = [float(bar.close) for bar in bars]
    path = sparkline(closes, width=640, height=180)
    last = bars[-1].close
    return (
        f'<div class="chart-fallback"><p class="muted">{symbol} · last {last}</p>{path}</div>'
    )


def as_decimal(value: Decimal | float | int | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
