const video = document.getElementById('video');
const captureBtn = document.getElementById('capture');
const result = document.getElementById('result');

// Load audio
const audioSuccess = new Audio('/static/sukses.mp3');
const audioUnknown = new Audio('/static/gagal.mp3');

// Aktifkan kamera
navigator.mediaDevices.getUserMedia({ video: true })
  .then(stream => {
    video.srcObject = stream;
  })
  .catch(err => {
    console.error("Gagal akses kamera:", err);
    alert("Tidak bisa mengakses kamera: " + err.message);
  });

// Tombol presensi
captureBtn.addEventListener('click', () => {
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  const imageData = canvas.toDataURL('image/jpeg');

  fetch('/detect', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: imageData })
  })
    .then(response => response.json())
    .then(data => {
      const name = data.identity;
      result.textContent = "Terdeteksi: " + name;

      if (name === "Tidak Dikenal") {
        audioUnknown.play();
      } else {
        audioSuccess.play();
      }

      setTimeout(() => {
        window.location.reload();
      }, 5000);
    });
});
