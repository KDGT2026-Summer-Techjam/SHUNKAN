(() => {
  const dialog = document.querySelector("[data-room-dialog]");
  if (!dialog) return;

  const actionLabel = dialog.querySelector("[data-room-action]");
  document.querySelectorAll("[data-room-required]").forEach((button) => {
    button.addEventListener("click", () => {
      actionLabel.textContent = button.dataset.roomRequired;
      dialog.showModal();
    });
  });

  dialog.querySelector("[data-room-dialog-close]").addEventListener("click", () => {
    dialog.close();
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
})();
