(() => {
  "use strict";

  const overlay = document.querySelector("[data-achievement-overlay]");
  const messageEl = document.querySelector("[data-achievement-message]");
  const skipHint = document.querySelector("[data-achievement-skip-hint]");
  const fallbackCanvas = document.querySelector("[data-achievement-fallback-canvas]");
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
  const fallbackColors = ["#FFFFFF", "#FFF3D0", "#FFD9A8", "#FFC46B", "#E27F3E", "#CFE0F5"];

  let playing = false;
  let runToken = 0;
  let libraryCanvas = null;
  let instance = null;
  let container = null;
  let timeouts = [];
  let skipArmedAt = 0;
  let focusTarget = null;
  let fallbackContext = null;
  let fallbackRaf = null;
  let fallbackLastFrame = 0;
  let fallbackRockets = [];
  let fallbackParticles = [];
  const motionQuery = window.matchMedia?.("(prefers-reduced-motion: reduce)");
  const reducedMotion = () => Boolean(motionQuery?.matches);
  const libraryReady = () => typeof window.fireworks === "function";
  const later = (fn, ms) => { const id = setTimeout(fn, ms); timeouts.push(id); return id; };
  const clearTimers = () => { timeouts.forEach(clearTimeout); timeouts = []; };

  const resetTransitions = () => [overlay, messageEl, skipHint].forEach((element) => { element.style.transitionDuration = ""; });
  const clearFallback = () => {
    if (fallbackRaf !== null) cancelAnimationFrame(fallbackRaf);
    fallbackRaf = null;
    fallbackLastFrame = 0;
    fallbackRockets = [];
    fallbackParticles = [];
    if (fallbackContext && fallbackCanvas) fallbackContext.clearRect(0, 0, fallbackCanvas.width, fallbackCanvas.height);
    fallbackContext = null;
    if (fallbackCanvas) fallbackCanvas.hidden = true;
  };
  const teardown = () => {
    try { container?.pauseEmitter(0); } catch (_) { /* already stopped */ }
    try { if (instance && !instance.destroyed) instance.destroy(); } catch (_) { /* already destroyed */ }
    libraryCanvas?.remove();
    libraryCanvas = null; instance = null; container = null;
    clearFallback();
  };
  const createLibraryCanvas = () => {
    libraryCanvas = document.createElement("canvas");
    libraryCanvas.id = "shunkan-fireworks";
    libraryCanvas.className = "achievement-canvas";
    libraryCanvas.setAttribute("aria-hidden", "true");
    document.body.append(libraryCanvas);
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
    try {
      createLibraryCanvas();
      const created = await window.fireworks.create(libraryCanvas, fireworksOptions);
      if (token !== runToken) { try { created?.destroy(); } catch (_) { /* no-op */ } teardown(); return false; }
      instance = created;
      container = window.tsParticles?.items?.find((item) => item.id?.description === "shunkan-fireworks") || null;
      if (!container) { teardown(); return false; }
      configureContainer();
      container.removeEmitter(0);
      await container.addEmitter(emitterOptions);
      if (token !== runToken) { teardown(); return false; }
      container.pauseEmitter(0);
      return true;
    } catch (_) {
      teardown();
      return false;
    }
  };
  const launchLibrary = (token) => {
    if (token !== runToken || !container) return;
    try {
      container.playEmitter(0);
      later(() => { if (token === runToken) container?.pauseEmitter(0); }, timings.gate);
    } catch (_) { /* fallback cannot be swapped safely after a partial library launch */ }
  };

  const resizeFallbackCanvas = () => {
    if (!fallbackCanvas || !fallbackContext) return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    const dpr = Math.max(1, window.devicePixelRatio || 1);
    fallbackCanvas.width = Math.round(width * dpr);
    fallbackCanvas.height = Math.round(height * dpr);
    fallbackCanvas.style.width = `${width}px`;
    fallbackCanvas.style.height = `${height}px`;
    fallbackContext.setTransform(dpr, 0, 0, dpr, 0, 0);
  };
  const drawFallback = () => {
    if (!fallbackContext) return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    fallbackContext.clearRect(0, 0, width, height);
    fallbackRockets.forEach((rocket) => {
      const trail = fallbackContext.createLinearGradient(rocket.x, rocket.y + 26, rocket.x, rocket.y);
      trail.addColorStop(0, "rgba(255,196,107,0)");
      trail.addColorStop(1, "rgba(255,243,208,.95)");
      fallbackContext.strokeStyle = trail;
      fallbackContext.lineWidth = 2;
      fallbackContext.beginPath();
      fallbackContext.moveTo(rocket.x, rocket.y + 26);
      fallbackContext.lineTo(rocket.x, rocket.y);
      fallbackContext.stroke();
    });
    fallbackParticles.forEach((particle) => {
      const alpha = Math.max(0, 1 - particle.age / particle.life);
      fallbackContext.globalAlpha = alpha * alpha;
      fallbackContext.fillStyle = particle.color;
      fallbackContext.beginPath();
      fallbackContext.arc(particle.x, particle.y, particle.size * (0.5 + alpha), 0, Math.PI * 2);
      fallbackContext.fill();
    });
    fallbackContext.globalAlpha = 1;
  };
  const explodeFallbackRocket = (rocket) => {
    for (let index = 0; index < 44; index += 1) {
      const angle = (Math.PI * 2 * index) / 44 + (Math.random() - .5) * .18;
      const speed = 90 + Math.random() * 120;
      fallbackParticles.push({
        x: rocket.x, y: rocket.targetY, vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        age: 0, life: 850 + Math.random() * 400, size: 1.5 + Math.random() * 1.5,
        color: fallbackColors[index % fallbackColors.length],
      });
    }
  };
  const animateFallback = (now) => {
    const elapsed = fallbackLastFrame ? Math.min(50, now - fallbackLastFrame) : 16;
    fallbackLastFrame = now;
    const seconds = elapsed / 1000;
    fallbackRockets.forEach((rocket) => {
      rocket.age += elapsed;
      rocket.y = rocket.startY + (rocket.targetY - rocket.startY) * Math.min(1, rocket.age / timings.flight);
    });
    const exploding = fallbackRockets.filter((rocket) => rocket.age >= timings.flight);
    fallbackRockets = fallbackRockets.filter((rocket) => rocket.age < timings.flight);
    exploding.forEach(explodeFallbackRocket);
    fallbackParticles.forEach((particle) => {
      particle.age += elapsed;
      particle.x += particle.vx * seconds;
      particle.y += particle.vy * seconds;
      particle.vy += 130 * seconds;
      particle.vx *= .985;
    });
    fallbackParticles = fallbackParticles.filter((particle) => particle.age < particle.life);
    drawFallback();
    if (fallbackRockets.length || fallbackParticles.length) fallbackRaf = requestAnimationFrame(animateFallback);
    else fallbackRaf = null;
  };
  const launchFallback = (token, launchIndex) => {
    if (token !== runToken || !fallbackContext) return;
    const width = window.innerWidth;
    const height = window.innerHeight;
    fallbackRockets.push({
      x: width * [.28, .5, .72][launchIndex % 3], startY: height + 20,
      y: height + 20, targetY: height * [.34, .24, .4][launchIndex % 3], age: 0,
    });
    if (fallbackRaf === null) fallbackRaf = requestAnimationFrame(animateFallback);
  };
  const startFallback = () => {
    if (!fallbackCanvas) return false;
    fallbackContext = fallbackCanvas.getContext("2d");
    if (!fallbackContext) return false;
    fallbackCanvas.hidden = false;
    resizeFallbackCanvas();
    return true;
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
    const schedule = (effect) => {
      if (token !== runToken) return;
      const useEffect = Boolean(effect);
      const wait = useEffect ? Math.max(0, timings.firstLaunch - (performance.now() - startedAt)) : fadeIn;
      if (useEffect) launchOffsets.forEach((offset, index) => later(() => {
        if (effect === "library") launchLibrary(token);
        else launchFallback(token, index);
      }, wait + offset));
      const messageAt = useEffect ? wait + timings.flight : fadeIn;
      const lastLaunch = useEffect ? wait + launchOffsets.at(-1) : fadeIn;
      later(() => {
        if (token !== runToken) return;
        messageEl.setAttribute("aria-hidden", "false"); messageEl.classList.add("is-active");
      }, messageAt);
      later(() => { if (token === runToken) finish(reduced ? reducedTimings.fadeOut : timings.fadeOut); }, lastLaunch + (useEffect ? timings.flight : 0) + afterglow);
    };
    if (reduced) schedule(null);
    else schedule(startFallback() ? "fallback" : null);
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

  window.addEventListener("resize", resizeFallbackCanvas);
  overlay.addEventListener("click", skip);
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") abandon(); });
  window.addEventListener("pagehide", abandon);
  document.addEventListener("keydown", (event) => {
    if (playing && ["Escape", "Enter", " "].includes(event.key)) { event.preventDefault(); skip(); }
  });
  window.ShunkanAchievement = { play, skip, stop, get isPlaying() { return playing; } };

  const autoplay = document.querySelector("[data-achievement-autoplay]");
  if (autoplay) {
    requestAnimationFrame(() => play({ message: autoplay.dataset.achievementMessage }));
  }

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
