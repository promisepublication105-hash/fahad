const $ = (id) => document.getElementById(id);

const adCard = $("ad-card");
const uploadCard = $("upload-card");
const progressCard = $("progress-card");
const resultCard = $("result-card");

let activeTab = "ad";
let pollTimer = null;

// ---------------------------------------------------------------- tabs
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => showTab(btn.dataset.tab))
);

function showTab(tab) {
  activeTab = tab;
  document.querySelectorAll(".tab").forEach((b) =>
    b.classList.toggle("active", b.dataset.tab === tab)
  );
  progressCard.classList.add("hidden");
  resultCard.classList.add("hidden");
  adCard.classList.toggle("hidden", tab !== "ad");
  uploadCard.classList.toggle("hidden", tab !== "dub");
}

// ---------------------------------------------------------------- dropzone helper
function wireDropzone(zone, input, onFiles) {
  zone.addEventListener("click", () => input.click());
  zone.addEventListener("dragover", (e) => {
    e.preventDefault();
    zone.classList.add("drag-over");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    if (e.dataTransfer.files.length) onFiles([...e.dataTransfer.files]);
  });
  input.addEventListener("change", () => {
    if (input.files.length) onFiles([...input.files]);
  });
}

// ---------------------------------------------------------------- product ad
let adImages = [];
const adThumbs = $("ad-thumbs");
const adSubmit = $("ad-submit");

wireDropzone($("ad-drop"), $("ad-images"), (files) => {
  const imgs = files.filter((f) => f.type.startsWith("image/"));
  adImages = adImages.concat(imgs).slice(0, 8);
  renderThumbs();
});

function renderThumbs() {
  adThumbs.innerHTML = "";
  adImages.forEach((file, i) => {
    const wrap = document.createElement("div");
    wrap.className = "thumb";
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = file.name;
    const rm = document.createElement("button");
    rm.type = "button";
    rm.textContent = "×";
    rm.title = "Remove";
    rm.addEventListener("click", () => {
      adImages.splice(i, 1);
      renderThumbs();
    });
    const n = document.createElement("span");
    n.textContent = i + 1;
    wrap.append(img, rm, n);
    adThumbs.appendChild(wrap);
  });
  updateAdSubmit();
}

function updateAdSubmit() {
  adSubmit.disabled = !(
    adImages.length &&
    $("ad-name").value.trim() &&
    $("ad-scenes").value.trim()
  );
}
["ad-name", "ad-scenes"].forEach((id) => $(id).addEventListener("input", updateAdSubmit));

$("ad-write").addEventListener("click", async () => {
  const name = $("ad-name").value.trim();
  const msg = $("ad-write-msg");
  if (!name) {
    msg.textContent = "Enter the product name first.";
    return;
  }
  const btn = $("ad-write");
  btn.disabled = true;
  msg.textContent = "Writing…";
  const form = new FormData();
  form.append("product_name", name);
  form.append("description", $("ad-desc").value);
  form.append("num_scenes", $("ad-num").value);
  try {
    const resp = await fetch("/api/ads/script", { method: "POST", body: form });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Script writing failed.");
    $("ad-scenes").value = data.scenes.join("\n");
    if (data.tagline) $("ad-tagline").value = data.tagline;
    if (data.cta) $("ad-cta").value = data.cta;
    msg.textContent = "Done. Edit the lines however you like.";
    updateAdSubmit();
  } catch (err) {
    msg.textContent = err.message || String(err);
  } finally {
    btn.disabled = false;
  }
});

$("ad-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (adSubmit.disabled) return;
  const form = new FormData($("ad-form"));
  adImages.forEach((f) => form.append("images", f));
  form.set("voiceover", $("ad-voice").checked);
  form.set("builtin_music", $("ad-builtin").checked);
  const music = $("ad-music").files[0];
  if (music) form.append("music", music);
  adCard.classList.add("hidden");
  startJob("/api/ads", form);
});

// ---------------------------------------------------------------- dub a video
let selectedFile = null;
const submitBtn = $("submit-btn");

wireDropzone($("dropzone"), $("file-input"), (files) => {
  selectedFile = files[0];
  $("selected-file").textContent =
    `Selected: ${selectedFile.name} (${(selectedFile.size / 1024 / 1024).toFixed(1)} MB)`;
  submitBtn.disabled = false;
});

submitBtn.addEventListener("click", () => {
  if (!selectedFile) return;
  const form = new FormData();
  form.append("file", selectedFile);
  form.append("target_lang", "bn");
  uploadCard.classList.add("hidden");
  startJob("/api/jobs", form);
});

// ---------------------------------------------------------------- shared job flow
async function startJob(url, form) {
  progressCard.classList.remove("hidden");
  $("error-msg").classList.add("hidden");
  $("back-btn").classList.add("hidden");
  $("notes-list").innerHTML = "";
  renderProgress({ stage: "Uploading…", progress: 0, notes: [] });
  try {
    const resp = await fetch(url, { method: "POST", body: form });
    if (!resp.ok) {
      let detail = await resp.text();
      try { detail = JSON.parse(detail).detail || detail; } catch (_) {}
      throw new Error(detail);
    }
    const job = await resp.json();
    pollJob(job.id);
  } catch (err) {
    showError(err.message || String(err));
  }
}

function pollJob(jobId) {
  clearInterval(pollTimer);
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
  }, 1500);
}

function fillNotes(list, notes) {
  list.innerHTML = "";
  (notes || []).forEach((note) => {
    const li = document.createElement("li");
    li.textContent = note;
    list.appendChild(li);
  });
}

function renderProgress(job) {
  $("stage-label").textContent = job.stage || "Processing…";
  $("progress-bar").style.width = `${job.progress}%`;
  $("progress-pct").textContent = `${job.progress}%`;
  fillNotes($("notes-list"), job.notes);
}

function showResult(jobId, job) {
  progressCard.classList.add("hidden");
  resultCard.classList.remove("hidden");
  const src = `/api/jobs/${jobId}/download?t=${Date.now()}`;
  $("result-video").src = src;
  $("download-link").href = src;
  fillNotes($("result-notes"), job.notes);
}

function showError(message) {
  $("error-msg").textContent = message;
  $("error-msg").classList.remove("hidden");
  $("back-btn").classList.remove("hidden");
}

$("back-btn").addEventListener("click", () => showTab(activeTab));

$("restart-btn").addEventListener("click", () => {
  $("result-video").pause();
  selectedFile = null;
  $("file-input").value = "";
  $("selected-file").textContent = "";
  submitBtn.disabled = true;
  showTab(activeTab);
});
