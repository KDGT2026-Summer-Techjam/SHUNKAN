(() => {
  const form = document.querySelector("[data-capture-form]");
  const dialog = document.querySelector("[data-camera-dialog]");
  if (!form || !dialog) return;

  const inputs = [...form.querySelectorAll("[data-photo-input]")];
  const cards = [...form.querySelectorAll("[data-photo-card]")];
  const count = form.querySelector("[data-photo-count]");
  const stage = form.querySelector("[data-photo-stage]");
  const addButton = form.querySelector(".photo-add-button");
  const photoList = form.querySelector(".photo-upload-list");
  const taskSelect = form.querySelector("#id_task");
  const taskCompletion = form.querySelector("[data-task-completion]");
  const video = dialog.querySelector("[data-camera-video]");
  const canvas = dialog.querySelector("[data-camera-canvas]");
  const error = dialog.querySelector("[data-camera-error]");
  const shutter = dialog.querySelector("[data-camera-shutter]");
  let stream = null;
  let activeInput = null;
  let cameraRequest = 0;
  let isCapturing = false;

  const occupiedCount = () => inputs.filter((input) => input.files.length).length;
  const nextEmptyInput = () => inputs.find((input) => !input.files.length);
  const toLocalDateTimeValue = (date) => {
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
      `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    );
  };
  const recordCapturedAt = (input) => {
    const card = cards[inputs.indexOf(input)];
    const capturedAt = card?.querySelector("[data-captured-at]");
    const source = card?.querySelector("[data-captured-at-source]");
    if (!capturedAt || !source) return;
    capturedAt.value = toLocalDateTimeValue(new Date());
    source.value = "manual";
  };

  const updateUi = () => {
    const selected = occupiedCount();
    count.textContent = `${selected} / 3枚`;
    stage.hidden = selected > 0;
    addButton.hidden = selected === 0 || selected === inputs.length;
    cards.forEach((card, index) => { card.hidden = !inputs[index].files.length; });
    // multipart送信時も写真とひとことの順序が一致するよう、選択済みカードを先に並べる。
    [...cards]
      .sort((a, b) => Number(b.querySelector("[data-photo-input]").files.length) - Number(a.querySelector("[data-photo-input]").files.length))
      .forEach((card) => photoList.append(card));
  };

  const setPreview = (input) => {
    const index = inputs.indexOf(input);
    const preview = cards[index].querySelector("[data-photo-preview]");
    if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
    if (!input.files.length) {
      preview.removeAttribute("src");
      delete preview.dataset.objectUrl;
      updateUi();
      return;
    }
    const objectUrl = URL.createObjectURL(input.files[0]);
    preview.src = objectUrl;
    preview.dataset.objectUrl = objectUrl;
    updateUi();
  };

  const openFilePicker = () => {
    const input = nextEmptyInput();
    if (input) input.click();
  };

  form.querySelectorAll("[data-file-picker]").forEach((button) => button.addEventListener("click", openFilePicker));
  inputs.forEach((input, index) => {
    input.addEventListener("change", () => setPreview(input));
    cards[index].querySelector("[data-photo-remove]").addEventListener("click", () => {
      input.value = "";
      cards[index].querySelector('[name="captured_at"]').value = "";
      cards[index].querySelector('[name="captured_at_source"]').value = "unknown";
      setPreview(input);
    });
  });

  const syncTaskCompletion = () => {
    if (!taskSelect || !taskCompletion) return;
    taskCompletion.hidden = !taskSelect.value;
    if (!taskSelect.value) taskCompletion.querySelector("input").checked = false;
  };
  taskSelect?.addEventListener("change", syncTaskCompletion);
  syncTaskCompletion();

  const setShutterReady = (ready) => {
    shutter.disabled = !ready;
    shutter.textContent = ready ? "この瞬間を撮影" : "カメラを準備中…";
  };
  const stopCamera = () => {
    cameraRequest += 1;
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
    activeInput = null;
    isCapturing = false;
    setShutterReady(false);
  };
  const clearError = () => {
    error.textContent = "";
    error.hidden = true;
  };
  const showError = (message) => {
    error.textContent = "";
    error.hidden = false;
    requestAnimationFrame(() => { error.textContent = message; });
  };

  form.querySelector("[data-camera-open]").addEventListener("click", async () => {
    activeInput = nextEmptyInput();
    if (!activeInput) return;
    const requestId = ++cameraRequest;
    clearError();
    setShutterReady(false);
    dialog.showModal();
    if (!navigator.mediaDevices?.getUserMedia) {
      showError("このブラウザではカメラ撮影を利用できません。端末から写真を選んでください。");
      return;
    }
    try {
      const requestedStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      if (requestId !== cameraRequest || !dialog.open) {
        requestedStream.getTracks().forEach((track) => track.stop());
        return;
      }
      stream = requestedStream;
      video.srcObject = stream;
      await video.play();
      if (requestId === cameraRequest && dialog.open && video.videoWidth) setShutterReady(true);
    } catch (_) {
      if (requestId === cameraRequest && dialog.open) {
        showError("カメラを開始できませんでした。ブラウザのカメラ権限を確認してください。");
      }
    }
  });

  video.addEventListener("loadedmetadata", () => {
    if (stream && dialog.open && video.videoWidth) setShutterReady(true);
  });

  shutter.addEventListener("click", () => {
    if (isCapturing) return;
    if (!stream || !video.videoWidth || !activeInput) {
      setShutterReady(false);
      showError("カメラの準備ができていません。");
      return;
    }
    isCapturing = true;
    shutter.disabled = true;
    shutter.textContent = "撮影中…";
    const destinationInput = activeInput;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        isCapturing = false;
        setShutterReady(true);
        showError("写真を作成できませんでした。もう一度お試しください。");
        return;
      }
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], `shunkan-${Date.now()}.jpg`, { type: "image/jpeg" }));
      destinationInput.files = transfer.files;
      recordCapturedAt(destinationInput);
      setPreview(destinationInput);
      dialog.close();
    }, "image/jpeg", 0.9);
  });

  dialog.querySelector("[data-camera-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", stopCamera);
  updateUi();
})();
