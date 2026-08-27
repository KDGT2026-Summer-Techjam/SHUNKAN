(() => {
  const selectByKind = {
    task: document.querySelector("#id_task"),
    category: document.querySelector("#id_category"),
  };

  document.querySelectorAll("[data-quick-create]").forEach((details) => {
    const kind = details.dataset.quickCreate;
    const select = selectByKind[kind];
    const form = details.querySelector("[data-quick-create-form]");
    if (!select || !form) return;

    const errorBox = details.querySelector("[data-quick-create-error]");
    const showError = (message) => {
      errorBox.textContent = message;
      errorBox.hidden = false;
    };

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      errorBox.hidden = true;

      const csrfInput = form.querySelector('input[name="csrfmiddlewaretoken"]');
      const body = new FormData(form);
      if (csrfInput) body.delete("csrfmiddlewaretoken");

      let response;
      try {
        response = await fetch(form.action, {
          method: "POST",
          headers: { "X-CSRFToken": csrfInput ? csrfInput.value : "" },
          body,
        });
      } catch (_) {
        showError("通信に失敗しました。もう一度お試しください。");
        return;
      }

      if (!response.ok) {
        let message = "作成できませんでした。入力内容を確認してください。";
        try {
          const data = await response.json();
          const errors = data.errors ? JSON.parse(data.errors) : {};
          const first = Object.values(errors).flat()[0];
          if (first && first.message) message = first.message;
        } catch (_) {
          // JSONでないエラーは既定文言のまま
        }
        showError(message);
        return;
      }

      const data = await response.json();
      const option = new Option(data.label, data.id, false, true);
      select.append(option);
      select.value = data.id;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      form.reset();
      details.removeAttribute("open");
    });
  });
})();
