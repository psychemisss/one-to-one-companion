(() => {
  const el = document.getElementById("timer");
  const started = Date.parse(el.dataset.started.replace(/\.\d+/, ""));
  // Per-block start survives reloads/back-navigation within the tab.
  const key = `block-start-${el.dataset.session}-${el.dataset.block}`;
  let blockStart = Number(sessionStorage.getItem(key));
  if (!blockStart) sessionStorage.setItem(key, (blockStart = Date.now()));
  const budget = Number(el.dataset.minutes) * 60;
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const elapsed = document.getElementById("elapsed");
  const left = document.getElementById("block-left");

  function tick() {
    elapsed.textContent = fmt(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    const remaining = budget - Math.floor((Date.now() - blockStart) / 1000);
    left.textContent = remaining >= 0 ? fmt(remaining) : `-${fmt(-remaining)} ${el.dataset.over}`;
    left.classList.toggle("over", remaining < 0);
  }
  tick();
  setInterval(tick, 1000);

  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea, select") || e.altKey || e.ctrlKey || e.metaKey) return;
    const link = document.getElementById(e.key === "ArrowRight" ? "next" : e.key === "ArrowLeft" ? "prev" : "");
    if (link) link.click();
  });
})();
