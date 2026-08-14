(() => {
  const open = (id) => document.getElementById(id)?.showModal();
  const close = (id) => document.getElementById(id)?.close();

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      const btn = form.querySelector("button[type=submit]");
      if (!btn || btn.disabled) return;
      btn.disabled = true;
      const action = form.getAttribute("action") || "";
      if (action.includes("/eod/")) {
        btn.textContent = "Reading news…";
      }
    });
  });

  document.querySelectorAll("[data-open]").forEach((el) => {
    el.addEventListener("click", () => open(el.dataset.open));
  });
  document.querySelectorAll("[data-close]").forEach((el) => {
    el.addEventListener("click", () => close(el.dataset.close));
  });

  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea, select")) return;
    if (event.key === "i" && !event.metaKey && !event.ctrlKey) {
      window.location.href = "/import";
    }
    if (event.key === "g") {
      const once = (e) => {
        const map = { d: "/", h: "/holdings", r: "/risk", a: "/alerts", s: "/settings" };
        if (map[e.key]) window.location.href = map[e.key];
        document.removeEventListener("keydown", once);
      };
      document.addEventListener("keydown", once);
    }
  });
})();
