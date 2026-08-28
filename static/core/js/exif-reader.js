(() => {
  const toDatetimeLocal = (date) => {
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
      `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    );
  };

  document.querySelectorAll("[data-photo-input]").forEach((input) => {
    const card = input.closest("[data-photo-card]");
    const capturedAtInput = card?.querySelector("[data-captured-at]");
    const sourceInput = card?.querySelector("[data-captured-at-source]");

    const setCurrentTime = () => {
      if (!capturedAtInput || !sourceInput) return;
      capturedAtInput.value = toDatetimeLocal(new Date());
      sourceInput.value = "manual";
    };

    capturedAtInput?.addEventListener("input", () => {
      sourceInput.value = capturedAtInput.value ? "manual" : "unknown";
    });

    input.addEventListener("change", async () => {
      const card = input.closest("[data-photo-card]");
      const capturedAtInput = card?.querySelector("[data-captured-at]");
      const sourceInput = card?.querySelector("[data-captured-at-source]");
      if (!capturedAtInput || !sourceInput) return;

      capturedAtInput.value = "";
      sourceInput.value = "unknown";

      const file = input.files[0];
      if (!file) return;
      if (!/^image\/jpeg$/.test(file.type)) {
        setCurrentTime();
        return;
      }

      try {
        const buffer = await file.arrayBuffer();
        const tags = window.EXIF ? window.EXIF.readFromBinaryFile(buffer) : null;
        const raw = tags ? tags.DateTimeOriginal || tags.DateTimeDigitized : null;
        if (!raw) {
          setCurrentTime();
          return;
        }
        const match = String(raw).match(/^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
        if (!match) {
          setCurrentTime();
          return;
        }
        const date = new Date(
          Number(match[1]),
          Number(match[2]) - 1,
          Number(match[3]),
          Number(match[4]),
          Number(match[5]),
          Number(match[6]),
        );
        if (Number.isNaN(date.getTime())) {
          setCurrentTime();
          return;
        }
        capturedAtInput.value = toDatetimeLocal(date);
        sourceInput.value = "exif";
      } catch (_) {
        setCurrentTime();
      }
    });
  });
})();
