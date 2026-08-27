(() => {
  const toDatetimeLocal = (date) => {
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
      `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    );
  };

  document.querySelectorAll("[data-photo-input]").forEach((input) => {
    input.addEventListener("change", async () => {
      const card = input.closest("[data-photo-card]");
      const capturedAtInput = card?.querySelector("[data-captured-at]");
      const exifHidden = card?.querySelector("[data-exif-captured-at]");
      if (!capturedAtInput || !exifHidden) return;

      exifHidden.value = "";
      if (capturedAtInput.value) capturedAtInput.value = "";

      const file = input.files[0];
      if (!file) return;
      if (!/^image\/jpeg$/.test(file.type)) return;

      try {
        const buffer = await file.arrayBuffer();
        const tags = window.EXIF ? window.EXIF.readFromBinaryFile(buffer) : null;
        const raw = tags ? tags.DateTimeOriginal || tags.DateTimeDigitized : null;
        if (!raw) return;
        const match = String(raw).match(/^(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})/);
        if (!match) return;
        const date = new Date(
          Number(match[1]),
          Number(match[2]) - 1,
          Number(match[3]),
          Number(match[4]),
          Number(match[5]),
          Number(match[6]),
        );
        if (Number.isNaN(date.getTime())) return;
        const value = toDatetimeLocal(date);
        exifHidden.value = value;
        if (!capturedAtInput.value) {
          capturedAtInput.value = value;
          capturedAtInput.dataset.exifPrefilled = "1";
        }
      } catch (_) {
        // EXIFが読めなくても写真のアップロード自体は続行する。
      }
    });
  });
})();
