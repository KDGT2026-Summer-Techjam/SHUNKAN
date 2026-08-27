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
  let stream = null;
  let activeInput = null;

  const occupiedCount = () => inputs.filter((input) => input.files.length).length;
  const nextEmptyInput = () => inputs.find((input) => !input.files.length);

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
      cards[index].querySelector('[name="captions"]').value = "";
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

  const stopCamera = () => {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
  };
  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  form.querySelector("[data-camera-open]").addEventListener("click", async () => {
    activeInput = nextEmptyInput();
    if (!activeInput) return;
    error.hidden = true;
    dialog.showModal();
    if (!navigator.mediaDevices?.getUserMedia) {
      showError("このブラウザではカメラ撮影を利用できません。端末から写真を選んでください。");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      video.srcObject = stream;
    } catch (_) {
      showError("カメラを開始できませんでした。ブラウザのカメラ権限を確認してください。");
    }
  });

  dialog.querySelector("[data-camera-shutter]").addEventListener("click", () => {
    if (!stream || !video.videoWidth || !activeInput) {
      showError("カメラの準備ができていません。");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) return showError("写真を作成できませんでした。もう一度お試しください。");
      const transfer = new DataTransfer();
      transfer.items.add(new File([blob], `shunkan-${Date.now()}.jpg`, { type: "image/jpeg" }));
      activeInput.files = transfer.files;
      setPreview(activeInput);
      stopCamera();
      dialog.close();
    }, "image/jpeg", 0.9);
  });

  dialog.querySelector("[data-camera-close]").addEventListener("click", () => dialog.close());
  dialog.addEventListener("close", stopCamera);
  updateUi();
})();
