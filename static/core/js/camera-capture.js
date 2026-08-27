(() => {
  const dialog = document.querySelector("[data-camera-dialog]");
  const fileInput = document.querySelector("#primary-photo-input");
  if (!dialog || !fileInput) return;

  const video = dialog.querySelector("[data-camera-video]");
  const canvas = dialog.querySelector("[data-camera-canvas]");
  const error = dialog.querySelector("[data-camera-error]");
  const preview = document.querySelector("[data-camera-preview]");
  let stream = null;

  const stopCamera = () => {
    if (stream) stream.getTracks().forEach((track) => track.stop());
    stream = null;
    video.srcObject = null;
  };

  const showError = (message) => {
    error.textContent = message;
    error.hidden = false;
  };

  document.querySelector("[data-camera-open]").addEventListener("click", async () => {
    error.hidden = true;
    dialog.showModal();
    if (!navigator.mediaDevices?.getUserMedia) {
      showError("このブラウザではカメラ撮影を利用できません。写真1の選択ボタンから撮影してください。");
      return;
    }
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      video.srcObject = stream;
    } catch (cameraError) {
      showError("カメラを開始できませんでした。ブラウザのカメラ権限を確認してください。");
    }
  });

  dialog.querySelector("[data-camera-shutter]").addEventListener("click", () => {
    if (!stream || !video.videoWidth) {
      showError("カメラの準備ができていません。");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((blob) => {
      if (!blob) {
        showError("写真を作成できませんでした。もう一度お試しください。");
        return;
      }
      const file = new File([blob], `shunkan-${Date.now()}.jpg`, { type: "image/jpeg" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      fileInput.files = transfer.files;
      preview.src = URL.createObjectURL(blob);
      preview.hidden = false;
      stopCamera();
      dialog.close();
    }, "image/jpeg", 0.9);
  });

  dialog.querySelector("[data-camera-close]").addEventListener("click", () => {
    stopCamera();
    dialog.close();
  });

  dialog.addEventListener("close", stopCamera);
})();
