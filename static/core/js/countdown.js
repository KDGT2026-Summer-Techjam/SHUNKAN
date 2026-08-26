document.querySelectorAll("[data-countdown]").forEach((element) => {
  const endTime = new Date(element.dataset.countdown).getTime();
  if (Number.isNaN(endTime)) return;

  let timer;
  const render = () => {
    const remaining = Math.max(0, endTime - Date.now());
    const totalSeconds = Math.floor(remaining / 1000);
    const days = Math.floor(totalSeconds / 86400);
    const hours = Math.floor((totalSeconds % 86400) / 3600);
    const minutes = Math.floor((totalSeconds % 3600) / 60);
    const seconds = totalSeconds % 60;
    element.textContent = `${String(days).padStart(2, "0")}日 ${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    if (remaining === 0) window.clearInterval(timer);
  };

  render();
  timer = window.setInterval(render, 1000);
});
