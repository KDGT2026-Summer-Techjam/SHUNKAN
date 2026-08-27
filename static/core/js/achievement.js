(() => {
  "use strict";

  const overlay = document.querySelector("[data-achievement-overlay]");
  const messageEl = document.querySelector("[data-achievement-message]");
  const skipHint = document.querySelector("[data-achievement-skip-hint]");
  if (!overlay || !messageEl || !skipHint) return;

  const timings = { fadeIn: 500, fadeOut: 600, firstLaunch: 400, flight: 600, afterglow: 1500, gate: 130 };
  const launchOffsets = [0, 700, 1400];
  const reducedTimings = { fadeIn: 200, fadeOut: 200, afterglow: 1200 };
  const fireworksOptions = {
    sounds: false, rate: 10, splitCount: 240,
    colors: ["#FFFFFF", "#FFF3D0", "#FFD9A8", "#FFC46B", "#E27F3E", "#CFE0F5"],
    minHeight: { min: 32, max: 52 }, speed: { min: 26, max: 42 }, gravity: 20,
    brightness: { min: 5, max: 30 }, saturation: { min: -15, max: 15 },
  };
  const emitterOptions = {
    direction: "top", life: { count: 0, duration: .1, delay: .1 },
    rate: { delay: .1, quantity: 1 }, size: { width: 52, height: 0 }, position: { x: 50, y: 100 },
  };

  let playing = false;
  let runToken = 0;
  let canvas = null;
  let instance = null;
  let container = null;
  let timeouts = [];
  let skipArmedAt = 0;
  let focusTarget = null;
  const motionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  const reducedMotion = () => Boolean(motionQuery?.matches);
  const libraryReady = () => typeof window.fireworks === "function";
  const later = (fn, ms) => { const id = setTimeout(fn, ms); timeouts.push(id); return id; };
  const clearTimers = () => { timeouts.forEach(clearTimeout); timeouts = []; };

  const resetTransitions = () => [overlay, messageEl, skipHint].forEach((element) => { element.style.transitionDuration = ""; });
  const teardown = () => {
    try { container?.pauseEmitter(0); } catch (_) { /* already stopped */ }
    try { if (instance && !instance.destroyed) instance.destroy(); } catch (_) { /* already destroyed */ }
    canvas?.remove();
    canvas = null; instance = null; container = null;
  };
  const createCanvas = () => {
    canvas = document.createElement("canvas");
    canvas.id = "shunkan-fireworks";
    canvas.className = "achievement-canvas";
    canvas.setAttribute("aria-hidden", "true");
    document.body.append(canvas);
  };
  const configureContainer = () => {
    try {
      const split = container.actualOptions.particles.destroy.split.particles;
      split.move.speed.min = 22; split.move.speed.max = 48;
    } catch (_) { /* optional preset tuning */ }
    try {
      const move = container.actualOptions.particles.move;
      move.angle.value = 0; move.angle.offset = 0; move.straight = true;
    } catch (_) { /* optional preset tuning */ }
  };
  const startFireworks = async (token) => {
    if (!libraryReady()) return false;
    createCanvas();
    const created = await window.fireworks.create(canvas, fireworksOptions);
    if (token !== runToken) { try { created?.destroy(); } catch (_) { /* no-op */ } teardown(); return false; }
    instance = created;
    container = window.tsParticles?.items?.find((item) => item.id?.description === "shunkan-fireworks") || null;
    if (!container) return false;
    configureContainer();
    container.removeEmitter(0);
    await container.addEmitter(emitterOptions);
    if (token !== runToken) { teardown(); return false; }
    container.pauseEmitter(0);
    return true;
  };
  const launchOnce = (token) => {
    if (token !== runToken || !container) return;
    try {
      container.playEmitter(0);
      later(() => { if (token === runToken) container?.pauseEmitter(0); }, timings.gate);
    } catch (_) { /* message-only fallback remains available */ }
  };
  const finish = (duration) => {
    [overlay, messageEl, skipHint].forEach((element) => { element.style.transitionDuration = `${duration}ms`; });
    overlay.classList.remove("is-active"); messageEl.classList.remove("is-active"); skipHint.classList.remove("is-active");
    messageEl.setAttribute("aria-hidden", "true"); teardown();
    later(() => {
      overlay.style.pointerEvents = "none"; overlay.setAttribute("aria-hidden", "true"); playing = false; resetTransitions();
      focusTarget?.focus({ preventScroll: true }); focusTarget = null;
    }, duration + 80);
  };
  const stop = (immediate = false) => {
    if (!playing) return;
    runToken += 1; clearTimers();
    finish(immediate ? 0 : (reducedMotion() ? reducedTimings.fadeOut : timings.fadeOut));
  };
  const skip = () => { if (playing && performance.now() >= skipArmedAt) stop(); };

  const play = ({ message, returnFocus } = {}) => {
    if (playing) return false;
    playing = true; clearTimers();
    const token = ++runToken;
    const reduced = reducedMotion();
    const fadeIn = reduced ? reducedTimings.fadeIn : timings.fadeIn;
    const afterglow = reduced ? reducedTimings.afterglow : timings.afterglow;
    focusTarget = returnFocus || null;
    messageEl.textContent = message || "達成！";
    messageEl.setAttribute("aria-hidden", "true");
    overlay.setAttribute("aria-hidden", "false");
    overlay.style.transitionDuration = `${fadeIn}ms`;
    overlay.classList.add("is-active"); skipHint.classList.add("is-active");
    skipArmedAt = performance.now() + 300;
    const startedAt = performance.now();
    const schedule = (useFireworks) => {
      if (token !== runToken) return;
      const wait = useFireworks ? Math.max(0, timings.firstLaunch - (performance.now() - startedAt)) : fadeIn;
      if (useFireworks) launchOffsets.forEach((offset) => later(() => launchOnce(token), wait + offset));
      const messageAt = useFireworks ? wait + timings.flight : fadeIn;
      const lastLaunch = useFireworks ? wait + launchOffsets.at(-1) : fadeIn;
      later(() => {
        if (token !== runToken) return;
        messageEl.setAttribute("aria-hidden", "false"); messageEl.classList.add("is-active");
      }, messageAt);
      later(() => { if (token === runToken) finish(reduced ? reducedTimings.fadeOut : timings.fadeOut); }, lastLaunch + (useFireworks ? timings.flight : 0) + afterglow);
    };
    if (reduced || !libraryReady()) schedule(false);
    else startFireworks(token).then((ready) => { if (token === runToken) schedule(ready); }).catch(() => { teardown(); if (token === runToken) schedule(false); });
    return true;
  };
  const abandon = () => {
    if (!playing) return;
    runToken += 1; clearTimers(); teardown(); playing = false;
    [overlay, messageEl, skipHint].forEach((element) => { element.style.transitionDuration = "0ms"; element.classList.remove("is-active"); });
    messageEl.setAttribute("aria-hidden", "true"); overlay.style.pointerEvents = "none";
    overlay.setAttribute("aria-hidden", "true");
    requestAnimationFrame(resetTransitions);
  };

  overlay.addEventListener("click", skip);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") abandon(); });
  window.addEventListener("pagehide", abandon);
  document.addEventListener("keydown", (event) => {
    if (playing && ["Escape", "Enter", " "].includes(event.key)) { event.preventDefault(); skip(); }
  });
  window.ShunkanAchievement = { play, skip, stop, get isPlaying() { return playing; } };

  document.querySelectorAll("[data-task-completion-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector("[data-task-completion-button]");
      const error = form.querySelector("[data-task-completion-error]");
      if (!button || button.disabled || playing) return;
      button.disabled = true; error.hidden = true;
      const csrfToken = form.querySelector("[name=csrfmiddlewaretoken]")?.value;
      try {
        const response = await fetch(form.action, {
          method: "POST", credentials: "same-origin",
          headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest", "X-CSRFToken": csrfToken },
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.task) throw new Error(result.error || "完了を保存できませんでした。もう一度お試しください。");
        const card = form.closest("[data-task-card]");
        card?.classList.add("task-card--completed");
        const status = card?.querySelector("[data-task-status]");
        if (status) { status.textContent = "✓"; status.setAttribute("aria-label", "完了"); }
        button.textContent = "完了しました";
        play({ message: `${result.task.title} を達成！`, returnFocus: button });
      } catch (requestError) {
        button.disabled = false; error.textContent = requestError.message; error.hidden = false;
      }
    });
  });
})();
