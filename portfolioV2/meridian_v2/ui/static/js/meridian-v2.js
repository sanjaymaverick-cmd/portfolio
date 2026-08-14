(() => {
  const THEME_KEY = "meridian-v2-theme";
  const charts = [];

  const isLight = () => document.body.classList.contains("light");

  const applyStoredTheme = () => {
    const stored = localStorage.getItem(THEME_KEY);
    if (stored === "light") document.body.classList.add("light");
    if (stored === "dark") document.body.classList.remove("light");
  };

  const setTheme = (light) => {
    document.body.classList.toggle("light", light);
    localStorage.setItem(THEME_KEY, light ? "light" : "dark");
    charts.forEach((item) => item.redraw());
  };

  const palette = () => {
    const light = isLight();
    return {
      bg: light ? "#f4efe4" : "#0c141c",
      text: light ? "#2a261f" : "#d7dde4",
      grid: light ? "#ddd6c8" : "#1a2834",
      up: "#4A9B7F",
      down: "#C46B6B",
      gold: "#C4A35A",
      tipBg: light ? "rgba(247,242,232,0.96)" : "rgba(12,20,28,0.94)",
      tipBorder: light ? "#d9d0c0" : "#1a2834",
    };
  };

  const ensureOverlay = (el) => {
    let canvas = el.querySelector("canvas.chart-overlay");
    if (!canvas) {
      el.style.position = "relative";
      canvas = document.createElement("canvas");
      canvas.className = "chart-overlay";
      canvas.style.cssText = "position:absolute;inset:0;pointer-events:none;z-index:2;";
      el.appendChild(canvas);
    }
    return canvas;
  };

  const ensureTip = (el) => {
    let tip = el.querySelector(".chart-tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "chart-tip";
      tip.hidden = true;
      el.appendChild(tip);
    }
    return tip;
  };

  const paintOverlays = (el, chart, series, data) => {
    const canvas = ensureOverlay(el);
    const dpr = window.devicePixelRatio || 1;
    const width = el.clientWidth;
    const height = el.clientHeight;
    canvas.width = Math.max(1, Math.floor(width * dpr));
    canvas.height = Math.max(1, Math.floor(height * dpr));
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const ts = chart.timeScale();
    (data.windows || []).forEach((win) => {
      const x1 = ts.timeToCoordinate(win.start);
      const x2 = ts.timeToCoordinate(win.end);
      if (x1 == null || x2 == null) return;
      ctx.fillStyle = win.color || "rgba(74,155,127,0.10)";
      ctx.fillRect(Math.min(x1, x2), 0, Math.abs(x2 - x1), height);
    });
    (data.zones || []).forEach((zone) => {
      const y1 = series.priceToCoordinate(zone.high);
      const y2 = series.priceToCoordinate(zone.low);
      if (y1 == null || y2 == null) return;
      ctx.fillStyle = zone.color || "rgba(196,163,90,0.12)";
      ctx.fillRect(0, Math.min(y1, y2), width, Math.abs(y2 - y1));
    });
  };

  const mountChart = async (el) => {
    if (!el || !window.LightweightCharts) return;
    const symbol = el.dataset.symbol;
    if (!symbol) return;
    const res = await fetch(`/api/chart/${encodeURIComponent(symbol)}`);
    if (!res.ok) return;
    const data = await res.json();
    const colors = palette();
    if (el._chart) {
      el._chart.remove();
      el._chart = null;
    }
    const chart = LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height: Number(el.dataset.height || 380),
      layout: {
        background: { color: colors.bg },
        textColor: colors.text,
        fontFamily: "IBM Plex Sans, Segoe UI, sans-serif",
        fontSize: 14,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      rightPriceScale: { borderColor: colors.grid },
      timeScale: { borderColor: colors.grid, rightOffset: 4 },
      crosshair: { mode: 0 },
      handleScroll: true,
      handleScale: true,
    });
    const candles = chart.addCandlestickSeries({
      upColor: colors.up,
      downColor: colors.down,
      borderUpColor: colors.up,
      borderDownColor: colors.down,
      wickUpColor: colors.up,
      wickDownColor: colors.down,
    });
    const rows = (data.candles || []).map((row) => ({
      time: row.time,
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
    candles.setData(rows);
    if (data.markers && data.markers.length) {
      candles.setMarkers(data.markers);
    }
    if (data.signal && data.signal.length) {
      const line = chart.addLineSeries({
        color: colors.gold,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      line.setData(data.signal);
    }
    const hasVolume = (data.candles || []).some((row) => Number(row.volume) > 0);
    if (hasVolume) {
      const volume = chart.addHistogramSeries({
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
        lastValueVisible: false,
        priceLineVisible: false,
      });
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });
      volume.setData(
        (data.candles || []).map((row) => ({
          time: row.time,
          value: Number(row.volume) || 0,
          color: row.close >= row.open ? "rgba(74,155,127,0.35)" : "rgba(196,107,107,0.35)",
        }))
      );
    }
    (data.levels || []).forEach((level) => {
      if (!level.price) return;
      candles.createPriceLine({
        price: level.price,
        color: level.color || colors.gold,
        lineWidth: 1,
        lineStyle: 2,
        title: level.title || "",
      });
    });

    const draw = () => paintOverlays(el, chart, candles, data);
    chart.timeScale().subscribeVisibleLogicalRangeChange(draw);
    requestAnimationFrame(draw);

    const tip = ensureTip(el);
    const markerAt = (time) =>
      (data.markers || []).find((item) => String(item.time) === String(time));
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time || !param.point) {
        tip.hidden = true;
        return;
      }
      const bar = param.seriesData.get(candles);
      if (!bar) {
        tip.hidden = true;
        return;
      }
      const mark = markerAt(param.time);
      const conf = mark && mark.text ? mark.text : "";
      tip.hidden = false;
      tip.style.background = colors.tipBg;
      tip.style.borderColor = colors.tipBorder;
      tip.innerHTML = `
        <strong>${param.time}</strong>
        <span>Open ${bar.open.toFixed(2)}</span>
        <span>High ${bar.high.toFixed(2)}</span>
        <span>Low ${bar.low.toFixed(2)}</span>
        <span>Close ${bar.close.toFixed(2)}</span>
        ${conf ? `<em>${conf}</em>` : ""}
      `;
      const left = Math.min(el.clientWidth - 180, Math.max(8, param.point.x + 12));
      const top = Math.max(8, param.point.y - 12);
      tip.style.left = `${left}px`;
      tip.style.top = `${top}px`;
    });

    const resize = () => {
      chart.applyOptions({ width: el.clientWidth });
      draw();
    };
    window.addEventListener("resize", resize);
    el._chart = chart;
    el._redraw = () => mountChart(el);
  };

  const bootCharts = () => {
    document.querySelectorAll("[data-chart]").forEach((el) => {
      const run = () => mountChart(el).catch(() => {});
      run();
      const seconds = Number(el.dataset.poll || 30);
      if (seconds > 0) {
        window.setInterval(run, seconds * 1000);
      }
      charts.push({ redraw: run });
    });
  };

  const bootTheme = () => {
    applyStoredTheme();
    const button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    const sync = () => {
      button.textContent = isLight() ? "Dark" : "Light";
      button.setAttribute("aria-label", isLight() ? "Use dark theme" : "Use light theme");
    };
    sync();
    button.addEventListener("click", () => {
      setTheme(!isLight());
      sync();
    });
  };

  applyStoredTheme();
  bootTheme();
  bootCharts();
})();
