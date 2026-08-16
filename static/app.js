const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const selectedFileEl = document.getElementById("selected-file");
const submitBtn = document.getElementById("submit-btn");

const uploadCard = document.getElementById("upload-card");
const progressCard = document.getElementById("progress-card");
const resultCard = document.getElementById("result-card");

const stageLabel = document.getElementById("stage-label");
const progressBar = document.getElementById("progress-bar");
const progressPct = document.getElementById("progress-pct");
const notesList = document.getElementById("notes-list");
const errorMsg = document.getElementById("error-msg");

const resultVideo = document.getElementById("result-video");
const downloadLink = document.getElementById("download-link");
const restartBtn = document.getElementById("restart-btn");

let selectedFile = null;
let pollTimer = null;

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropzone.classList.add("drag-over");
});
dropzone.addEventListener("dragleave", () => dropzone.classList.remove("drag-over"));
dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropzone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) selectFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", () => {
  if (fileInput.files.length) selectFile(fileInput.files[0]);
});

function selectFile(file) {
  selectedFile = file;
  selectedFileEl.textContent = `Selected: ${file.name} (${(file.size / 1024 / 1024).toFixed(1)} MB)`;
  submitBtn.disabled = false;
}

submitBtn.addEventListener("click", async () => {
  if (!selectedFile) return;
  submitBtn.disabled = true;

  const form = new FormData();
  form.append("file", selectedFile);
  form.append("target_lang", "bn");

  uploadCard.classList.add("hidden");
  progressCard.classList.remove("hidden");
  errorMsg.classList.add("hidden");
  notesList.innerHTML = "";

  try {
    const resp = await fetch("/api/jobs", { method: "POST", body: form });
    if (!resp.ok) throw new Error(await resp.text());
    const job = await resp.json();
    pollJob(job.id);
  } catch (err) {
    showError(err.message || String(err));
  }
});

function pollJob(jobId) {
  pollTimer = setInterval(async () => {
    try {
      const resp = await fetch(`/api/jobs/${jobId}`);
      const job = await resp.json();
      renderProgress(job);

      if (job.status === "done") {
        clearInterval(pollTimer);
        showResult(jobId, job);
      } else if (job.status === "error") {
        clearInterval(pollTimer);
        showError(job.error || "Something went wrong.");
      }
    } catch (err) {
      clearInterval(pollTimer);
      showError(err.message || String(err));
    }
  }, 2000);
}

function renderProgress(job) {
  stageLabel.textContent = job.stage || "Processing…";
  progressBar.style.width = `${job.progress}%`;
  progressPct.textContent = `${job.progress}%`;
  notesList.innerHTML = "";
  (job.notes || []).forEach((note) => {
    const li = document.createElement("li");
    li.textContent = note;
    notesList.appendChild(li);
  });
}

function showResult(jobId, job) {
  progressCard.classList.add("hidden");
  resultCard.classList.remove("hidden");
  const src = `/api/jobs/${jobId}/download`;
  resultVideo.src = src;
  downloadLink.href = src;
}

function showError(message) {
  errorMsg.textContent = message;
  errorMsg.classList.remove("hidden");
}

restartBtn.addEventListener("click", () => {
  selectedFile = null;
  fileInput.value = "";
  selectedFileEl.textContent = "";
  submitBtn.disabled = true;
  resultCard.classList.add("hidden");
  uploadCard.classList.remove("hidden");
});
