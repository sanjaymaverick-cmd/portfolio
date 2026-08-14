(() => {
  const mount = async (el) => {
    if (!el || !window.LightweightCharts) return;
    const url = el.dataset.chartUrl;
    if (!url) return;
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    const dark = !document.body.classList.contains("light");
    const chart = LightweightCharts.createChart(el, {
      width: el.clientWidth,
      height: Number(el.dataset.height || 360),
      layout: {
        background: { color: dark ? "#0E131B" : "#F4EFE4" },
        textColor: dark ? "#9AA3B2" : "#4A453C",
        fontFamily: "IBM Plex Sans, Segoe UI, sans-serif",
        fontSize: 13,
      },
      grid: {
        vertLines: { color: dark ? "#1C2433" : "#DDD6C8" },
        horzLines: { color: dark ? "#1C2433" : "#DDD6C8" },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
    });
    const series = chart.addCandlestickSeries({
      upColor: "#4A9B7F",
      downColor: "#C46B6B",
      wickUpColor: "#4A9B7F",
      wickDownColor: "#C46B6B",
      borderUpColor: "#4A9B7F",
      borderDownColor: "#C46B6B",
    });
    series.setData(
      (data.candles || []).map((row) => ({
        time: row.time,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
      }))
    );
    if (data.markers && data.markers.length) series.setMarkers(data.markers);
    if (data.signal && data.signal.length) {
      chart.addLineSeries({ color: "#C4A35A", lineWidth: 1, priceLineVisible: false }).setData(data.signal);
    }
    (data.levels || []).forEach((level) => {
      if (level.price) {
        series.createPriceLine({
          price: level.price,
          color: level.color || "#C4A35A",
          lineWidth: 1,
          lineStyle: 2,
          title: level.title || "",
        });
      }
    });
    window.addEventListener("resize", () => chart.applyOptions({ width: el.clientWidth }));
  };

  document.querySelectorAll("[data-chart-url]").forEach((el) => {
    mount(el).catch(() => {});
  });
})();
