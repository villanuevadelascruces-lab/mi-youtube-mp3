/* ==========================================================================
   YT2MP3 — lógica de la interfaz web
   ========================================================================== */
"use strict";

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const ICON = {
  music: '<svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>',
  download: '<svg viewBox="0 0 24 24"><path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>',
  clock: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  alert: '<svg viewBox="0 0 24 24"><path d="M12 3 2.5 20h19z"/><path d="M12 9v5m0 3h.01"/></svg>',
  retry: '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 3v6h-6"/></svg>',
  x: '<svg viewBox="0 0 24 24"><path d="M18 6 6 18M6 6l12 12"/></svg>',
  list: '<svg viewBox="0 0 24 24"><path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path d="M8 5.14v13.72c0 .8.87 1.3 1.56.9l10.5-6.86a1.06 1.06 0 0 0 0-1.8L9.56 4.24A1.06 1.06 0 0 0 8 5.14z"/></svg>',
  spinner: '<svg viewBox="0 0 24 24"><path d="M21 12a9 9 0 1 1-3-6.7"/></svg>'
};

const STATUS_LABEL = {
  waiting: "En espera",
  downloading: "Descargando",
  converting: "Convirtiendo",
  done: "Completado",
  error: "Error",
  cancelled: "Cancelado"
};

const state = {
  jobs: [],
  settings: { output_dir: "", quality: "192", embed: true },
  previews: [],
  analyzing: false,
  maxParallel: 4,
  online: true,
  shutdown: false
};

/* ================= TEMA ================= */
const root = document.documentElement;
const storedTheme = localStorage.getItem("yt2mp3-theme");
if (storedTheme === "light" || storedTheme === "dark") root.dataset.theme = storedTheme;

$("#themeToggle").addEventListener("click", () => {
  const next = root.dataset.theme === "dark" ? "light" : "dark";
  root.dataset.theme = next;
  localStorage.setItem("yt2mp3-theme", next);
});

/* ================= UTILIDADES ================= */
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => (
  { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]
));

function toast(message, kind = "ok") {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = "toast" + (kind === "err" ? " err" : "");
  el.innerHTML = (kind === "err" ? ICON.alert : ICON.check) + "<span>" + esc(message) + "</span>";
  box.appendChild(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 260);
  }, kind === "err" ? 6000 : 3400);
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  if (!total) return "";
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return h
    ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`
    : `${m}:${String(s).padStart(2, "0")}`;
}

function formatSpeed(bytesPerSecond) {
  const value = Number(bytesPerSecond) || 0;
  if (value <= 0) return "";
  if (value >= 1024 * 1024) return (value / 1024 / 1024).toFixed(1).replace(".", ",") + " MB/s";
  return Math.round(value / 1024) + " KB/s";
}

function formatEta(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  if (!value) return "";
  const m = Math.floor(value / 60);
  const s = value % 60;
  return String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
}

function safeThumb(url) {
  return typeof url === "string" && /^https?:\/\//i.test(url) ? url : "";
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  if (!response.ok) {
    let detail = "";
    try { detail = (await response.json()).error || ""; } catch (_) { /* sin detalle */ }
    throw new Error(detail || "El servidor respondió con un error (" + response.status + ")");
  }
  return response.json();
}

function setConnection(online) {
  state.online = online;
  const dot = $("#statusDot");
  const text = $("#statusText");
  dot.classList.toggle("offline", !online);
  text.textContent = online ? "Servidor local" : "Sin conexión";
}

/* ================= VISTA PREVIA ================= */
function previewCard(preview) {
  if (!preview.ok) {
    return `
      <div class="preview-card" data-url="${esc(preview.url)}">
        <button class="pv-remove" data-remove-preview="${esc(preview.url)}" title="Quitar">${ICON.x}</button>
        <div class="thumb" style="background:linear-gradient(135deg,#6b2131,#3a1622)">${ICON.alert}</div>
        <div class="pv-info">
          <div class="pv-title">No se pudo analizar el enlace</div>
          <div class="pv-sub" style="color:var(--danger)">${esc(preview.error || "Error desconocido")}</div>
        </div>
        <div class="pv-actions">
          <button class="btn btn-ghost btn-sm" data-remove-preview="${esc(preview.url)}">Quitar</button>
        </div>
      </div>`;
  }

  const thumb = safeThumb(preview.thumbnail);
  const hasPlaylist = preview.has_playlist && preview.playlist_count > 0;
  const isPlaylist = preview.kind === "playlist";
  const count = Number(preview.playlist_count) || 0;
  const duration = isPlaylist
    ? (count ? count + (count === 1 ? " canción" : " canciones") : "Playlist")
    : formatDuration(preview.duration);

  const choices = hasPlaylist
    ? `<div class="pl-choice">
         <button class="chip ${preview.choice === "single" ? "sel" : ""}" data-choice="${esc(preview.url)}" data-value="single">Solo esta canción</button>
         <button class="chip ${preview.choice === "playlist" ? "sel" : ""}" data-choice="${esc(preview.url)}" data-value="playlist">Playlist completa (${count})</button>
       </div>`
    : "";

  const badge = (isPlaylist || hasPlaylist)
    ? `<span class="pl-badge">${ICON.list} ${count ? count + " canciones" : "Playlist"}</span>`
    : "";

  return `
    <div class="preview-card" data-url="${esc(preview.url)}">
      <button class="pv-remove" data-remove-preview="${esc(preview.url)}" title="Quitar">${ICON.x}</button>
      <div class="thumb">
        ${thumb ? `<img src="${esc(thumb)}" alt="" loading="lazy" referrerpolicy="no-referrer">` : ICON.music}
        ${badge}
        ${duration ? `<span class="dur">${esc(duration)}</span>` : ""}
      </div>
      <div class="pv-info">
        <div class="pv-title">${esc(preview.title || preview.url)}</div>
        <div class="pv-sub">${esc(preview.channel || "")}</div>
      </div>
      ${choices}
      <div class="pv-actions">
        <button class="btn btn-primary btn-sm" data-add="${esc(preview.url)}">
          ${ICON.download} ${isPlaylist || preview.choice === "playlist" ? "Añadir playlist" : "Añadir a la cola"}
        </button>
      </div>
    </div>`;
}

function renderPreviews() {
  const section = $("#previewSection");
  const grid = $("#previewGrid");
  const previews = state.previews;

  if (!previews.length && !state.analyzing) {
    section.classList.add("hidden");
    grid.innerHTML = "";
    return;
  }

  section.classList.remove("hidden");
  $("#previewCount").textContent = previews.length + (previews.length === 1 ? " enlace" : " enlaces");
  grid.innerHTML = previews.map(previewCard).join("");

  // Si una miniatura falla, se oculta y queda el icono de música de fondo
  $$("img", grid).forEach((img) => {
    img.addEventListener("error", () => img.remove());
  });
}

function showSkeletons(count) {
  const section = $("#previewSection");
  const grid = $("#previewGrid");
  section.classList.remove("hidden");
  grid.innerHTML = Array.from({ length: Math.max(1, Math.min(count, 6)) }, () => `
    <div class="skeleton">
      <div class="sk-thumb"></div>
      <div class="sk-line"></div>
      <div class="sk-line short"></div>
    </div>`).join("");
}

function extractUrls(text) {
  const found = [];
  for (const token of String(text || "").split(/\s+/)) {
    const value = token.trim();
    if (!value) continue;
    try {
      const url = new URL(value);
      if (url.protocol === "http:" || url.protocol === "https:") found.push(url.href);
    } catch (_) { /* no es una URL */ }
  }
  return Array.from(new Set(found));
}

async function analyzeInput() {
  if (state.analyzing) return;
  const urls = extractUrls($("#urls").value);
  if (!urls.length) {
    toast("Pega al menos un enlace de YouTube (debe empezar por https://).", "err");
    $("#urls").focus();
    return;
  }

  const known = new Set(state.previews.map((preview) => preview.url));
  const fresh = urls.filter((url) => !known.has(url));
  if (!fresh.length) {
    toast("Esos enlaces ya están en la vista previa.");
    return;
  }

  state.analyzing = true;
  $("#btnAnalyze").disabled = true;
  $("#analyzeStatus").innerHTML = '<span class="spinner"></span> Analizando ' + fresh.length + (fresh.length === 1 ? " enlace…" : " enlaces…");
  showSkeletons(fresh.length);

  try {
    const data = await api("/api/analyze", { urls: fresh });
    const items = (data.items || []).map((item) => ({ ...item, choice: "single" }));
    state.previews = state.previews.concat(items);
    const failed = items.filter((item) => !item.ok);
    if (failed.length) {
      toast(failed.length === 1 ? "Un enlace no se pudo analizar." : failed.length + " enlaces no se pudieron analizar.", "err");
    }
    if (items.length > failed.length) {
      $("#previewSection").scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    $("#urls").value = "";
  } catch (error) {
    toast(error.message, "err");
  } finally {
    state.analyzing = false;
    $("#btnAnalyze").disabled = false;
    $("#analyzeStatus").textContent = "";
    renderPreviews();
  }
}

async function addPreview(url) {
  const preview = state.previews.find((item) => item.url === url);
  if (!preview) return;
  const isPlaylist = preview.kind === "playlist" || preview.choice === "playlist";
  const button = $$("[data-add]").find((element) => element.dataset.add === url);
  if (button) button.disabled = true;

  try {
    await api("/api/queue", {
      items: [{
        url: preview.url,
        title: preview.title || preview.url,
        channel: preview.channel || "",
        duration: preview.duration || 0,
        thumbnail: preview.thumbnail || "",
        kind: isPlaylist ? "playlist" : "video",
        playlist_count: preview.playlist_count || 0,
        no_playlist: !isPlaylist
      }]
    });
    state.previews = state.previews.filter((item) => item.url !== url);
    renderPreviews();
    toast("Añadido a la cola: " + (preview.title || preview.url));
    await refreshState();
  } catch (error) {
    if (button) button.disabled = false;
    toast(error.message, "err");
  }
}

/* ================= COLA ================= */
function jobActions(job) {
  const id = job.id;
  if (job.status === "downloading" || job.status === "converting") {
    return `<button class="icon-btn" data-action="cancel" data-id="${id}" title="Cancelar">${ICON.x}</button>`;
  }
  if (job.status === "waiting") {
    return `<button class="icon-btn" data-action="cancel" data-id="${id}" title="Quitar de la cola">${ICON.x}</button>`;
  }
  if (job.status === "error") {
    return `<button class="btn btn-ghost btn-sm" data-action="retry" data-id="${id}">${ICON.retry} Reintentar</button>
            <button class="icon-btn" data-action="remove" data-id="${id}" title="Quitar de la lista">${ICON.x}</button>`;
  }
  if (job.status === "cancelled") {
    return `<button class="btn btn-ghost btn-sm" data-action="retry" data-id="${id}">${ICON.retry} Reintentar</button>
            <button class="icon-btn" data-action="remove" data-id="${id}" title="Quitar de la lista">${ICON.x}</button>`;
  }
  return `<button class="icon-btn" data-action="open" data-id="${id}" title="Abrir carpeta">${ICON.folder}</button>
          <button class="icon-btn" data-action="remove" data-id="${id}" title="Quitar de la lista">${ICON.x}</button>`;
}

function jobMeta(job) {
  if (job.status === "error") {
    return `<span style="color:var(--danger)">${esc(job.error || "Error desconocido")}</span>`;
  }
  if (job.status === "cancelled") {
    return "Descarga cancelada";
  }

  const quality = "MP3 " + esc(job.quality) + " kbps";
  if (job.status === "downloading" || job.status === "converting") {
    const parts = [];
    if (job.playlist_total > 1) {
      const index = Math.min(job.playlist_index || 1, job.playlist_total);
      parts.push("Canción " + index + " de " + job.playlist_total);
    }
    if (job.status === "converting") {
      parts.push("Convirtiendo a MP3…");
    } else {
      parts.push(Math.round(job.progress || 0) + "%");
      const speed = formatSpeed(job.speed);
      if (speed) parts.push(speed);
      const eta = formatEta(job.eta);
      if (eta) parts.push("faltan " + eta);
    }
    return parts.map((part) => esc(part)).join(' <span class="sep">·</span> ');
  }

  const parts = [];
  if (job.channel) parts.push(esc(job.channel));
  parts.push(quality);
  const duration = formatDuration(job.duration);
  if (duration) parts.push(esc(duration));
  if (job.playlist_total > 1) parts.push(esc(job.playlist_total + " canciones"));
  return parts.join(' <span class="sep">·</span> ');
}

function createQueueItem(job) {
  const el = document.createElement("div");
  el.className = "q-item";
  el.dataset.id = job.id;
  el.innerHTML = `
    <div class="q-icon"></div>
    <div class="q-main">
      <div class="q-title"><span class="name"></span><span class="badge"></span></div>
      <div class="q-meta"></div>
      <div class="progress-track hidden"><div class="progress-fill"></div></div>
    </div>
    <div class="q-actions"></div>`;
  return el;
}

function updateQueueItem(el, job) {
  const status = job.status;
  const previous = el.dataset.status || "";
  el.dataset.status = status;
  el.className = "q-item " + {
    done: "done", error: "err", cancelled: "cancelled", waiting: "", downloading: "", converting: ""
  }[status];

  const icon = $(".q-icon", el);
  icon.className = "q-icon " + status;
  if (icon.dataset.status !== status) {
    icon.dataset.status = status;
    icon.innerHTML = status === "done" ? ICON.check
      : status === "error" ? ICON.alert
      : status === "cancelled" ? ICON.x
      : status === "waiting" ? ICON.clock
      : status === "converting" ? ICON.spinner
      : ICON.download;
  }

  $(".name", el).textContent = job.title || job.url;
  const badge = $(".badge", el);
  badge.className = "badge " + status;
  badge.textContent = STATUS_LABEL[status] || status;

  $(".q-meta", el).innerHTML = jobMeta(job);

  const isActive = status === "downloading" || status === "converting";
  const track = $(".progress-track", el);
  track.classList.toggle("hidden", !isActive);
  if (isActive) {
    $(".progress-fill", el).style.width = Math.max(0, Math.min(100, job.progress || 0)) + "%";
  }

  if (previous !== status) {
    $(".q-actions", el).innerHTML = jobActions(job);
  }
}

function renderQueue() {
  const box = $("#queue");
  const jobs = state.jobs;
  const seen = new Set();

  for (const job of jobs) {
    seen.add(String(job.id));
    let el = box.querySelector(`.q-item[data-id="${job.id}"]`);
    if (!el) {
      el = createQueueItem(job);
      box.appendChild(el);
    }
    updateQueueItem(el, job);
    // Mantener el orden de la cola
    box.appendChild(el);
  }

  $$(".q-item", box).forEach((el) => {
    if (!seen.has(el.dataset.id)) el.remove();
  });

  $("#queueEmpty").classList.toggle("hidden", jobs.length > 0);
  $("#queueCount").textContent = jobs.length;
  $("#btnClearEnded").disabled = !jobs.some((job) => ["done", "error", "cancelled"].includes(job.status));
  renderSummary();
}

function renderSummary() {
  const jobs = state.jobs;
  const card = $("#summaryCard");
  if (!jobs.length) {
    card.classList.add("hidden");
    return;
  }
  card.classList.remove("hidden");

  const count = (statuses) => jobs.filter((job) => statuses.includes(job.status)).length;
  const done = count(["done"]);
  const downloading = count(["downloading", "converting"]);
  const waiting = count(["waiting"]);
  const error = count(["error"]);
  const cancelled = count(["cancelled"]);

  $("#summaryTitle").textContent = done + " de " + jobs.length + (jobs.length === 1 ? " completada" : " completadas");

  const parts = [];
  if (downloading) parts.push(downloading + " descargando");
  if (waiting) parts.push(waiting + " en espera");
  if (error) parts.push(error + " con error");
  if (cancelled) parts.push(cancelled + " cancelada" + (cancelled === 1 ? "" : "s"));

  let subtitle = parts.join(" · ");
  if (!parts.length && done === jobs.length) {
    subtitle = "Todo listo. Los MP3 están en la carpeta de salida.";
  }
  $("#summarySub").textContent = subtitle;
}

/* ================= ACCIONES DE LA COLA ================= */
async function jobAction(action, id) {
  const job = state.jobs.find((item) => item.id === id);
  if (!job) return;
  try {
    if (action === "cancel") {
      await api("/api/cancel", { id });
      toast("Cancelando: " + job.title);
    } else if (action === "retry") {
      await api("/api/retry", { id });
      toast("Reintentando: " + job.title);
    } else if (action === "remove") {
      await api("/api/remove", { id });
    } else if (action === "open") {
      await api("/api/open-folder", { path: job.output_dir });
    }
    await refreshState();
  } catch (error) {
    toast(error.message, "err");
  }
}

$("#queue").addEventListener("click", (event) => {
  const button = event.target.closest("[data-action]");
  if (button) jobAction(button.dataset.action, Number(button.dataset.id));
});

/* ================= AJUSTES ================= */
function applySettings(settings) {
  state.settings = { ...state.settings, ...settings };
  $("#folderPath").value = state.settings.output_dir || "";
  $("#folderPath").title = state.settings.output_dir || "";
  $$("#quality button").forEach((button) => {
    button.classList.toggle("active", button.dataset.q === String(state.settings.quality));
  });
  $("#metaSwitch").classList.toggle("on", !!state.settings.embed);
  $("#metaRow").setAttribute("aria-checked", state.settings.embed ? "true" : "false");
}

async function updateSettings(patch) {
  try {
    const data = await api("/api/settings", patch);
    applySettings(data.settings || patch);
  } catch (error) {
    toast(error.message, "err");
  }
}

$("#quality").addEventListener("click", (event) => {
  const button = event.target.closest("button[data-q]");
  if (!button) return;
  updateSettings({ quality: button.dataset.q });
});

function toggleMeta() {
  updateSettings({ embed: !state.settings.embed });
}
$("#metaRow").addEventListener("click", toggleMeta);
$("#metaRow").addEventListener("keydown", (event) => {
  if (event.key === " " || event.key === "Enter") {
    event.preventDefault();
    toggleMeta();
  }
});

$("#btnFolder").addEventListener("click", async () => {
  const button = $("#btnFolder");
  button.disabled = true;
  try {
    const data = await api("/api/pick-folder", { initial: state.settings.output_dir });
    if (data.path) {
      applySettings(data.settings || { output_dir: data.path });
      toast("Carpeta de salida cambiada.");
    }
  } catch (error) {
    toast(error.message, "err");
  } finally {
    button.disabled = false;
  }
});

async function openOutputFolder() {
  try {
    await api("/api/open-folder", { path: state.settings.output_dir });
  } catch (error) {
    toast(error.message, "err");
  }
}
$("#btnOpenFolder").addEventListener("click", openOutputFolder);
$("#btnOpenFolder2").addEventListener("click", openOutputFolder);

$("#btnClearEnded").addEventListener("click", async () => {
  try {
    await api("/api/clear", {});
    await refreshState();
  } catch (error) {
    toast(error.message, "err");
  }
});

$("#btnQuit").addEventListener("click", async () => {
  const active = state.jobs.filter((job) => job.status === "downloading" || job.status === "converting").length;
  const message = active
    ? "Hay " + active + " descarga(s) en curso. Si apagas YT2MP3 se interrumpirán.\n\n¿Apagar de todas formas?"
    : "¿Apagar YT2MP3?\n\nPodrás volver a abrirlo desde el icono del escritorio.";
  if (!window.confirm(message)) return;

  try {
    state.shutdown = true;
    await api("/api/shutdown", {});
  } catch (_) { /* el servidor puede cerrar antes de responder */ }

  document.body.innerHTML = `
    <div style="min-height:100vh;display:grid;place-items:center;padding:24px;text-align:center;font-family:'Segoe UI',system-ui,sans-serif;background:#08090d;color:#eef0f4">
      <div>
        <div style="width:56px;height:56px;border-radius:16px;background:linear-gradient(135deg,#ff2d55,#ff6b3d);display:grid;place-items:center;margin:0 auto 18px">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="#fff"><path d="M8 5.14v13.72c0 .8.87 1.3 1.56.9l10.5-6.86a1.06 1.06 0 0 0 0-1.8L9.56 4.24A1.06 1.06 0 0 0 8 5.14z"/></svg>
        </div>
        <h1 style="font-size:22px;margin-bottom:8px">YT2MP3 se ha apagado</h1>
        <p style="color:#99a1ad;font-size:14px">Ya puedes cerrar esta pestaña.<br>Para volver a usarlo, abre el icono <strong style="color:#eef0f4">YT2MP3</strong> de tu escritorio.</p>
      </div>
    </div>`;
});

/* ================= VISTA PREVIA: EVENTOS ================= */
$("#previewGrid").addEventListener("click", (event) => {
  const remove = event.target.closest("[data-remove-preview]");
  if (remove) {
    state.previews = state.previews.filter((item) => item.url !== remove.dataset.removePreview);
    renderPreviews();
    return;
  }

  const choice = event.target.closest("[data-choice]");
  if (choice) {
    const preview = state.previews.find((item) => item.url === choice.dataset.choice);
    if (preview) {
      preview.choice = choice.dataset.value;
      renderPreviews();
    }
    return;
  }

  const add = event.target.closest("[data-add]");
  if (add) addPreview(add.dataset.add);
});

$("#btnClearPreviews").addEventListener("click", () => {
  state.previews = [];
  renderPreviews();
});

$("#btnAnalyze").addEventListener("click", analyzeInput);

$("#urls").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
    event.preventDefault();
    analyzeInput();
  }
});

$("#btnPaste").addEventListener("click", async () => {
  try {
    const text = await navigator.clipboard.readText();
    if (!text) {
      toast("El portapapeles está vacío.", "err");
      return;
    }
    const area = $("#urls");
    area.value = area.value.trim() ? area.value.trim() + "\n" + text.trim() : text.trim();
    area.focus();
  } catch (_) {
    toast("El navegador no permite leer el portapapeles. Pega con Ctrl+V.", "err");
    $("#urls").focus();
  }
});

/* ================= ESTADO DEL SERVIDOR ================= */
async function refreshState() {
  try {
    const data = await api("/api/state");
    setConnection(true);
    state.jobs = data.jobs || [];
    state.maxParallel = data.max_parallel || 4;
    applySettings(data.settings || {});
    $("#appVersion").textContent = data.version || "1.1";
    $("#parallelText").textContent = state.maxParallel + " descargas en paralelo";
    $("#ffmpegBanner").classList.toggle("hidden", data.ffmpeg !== false);
    renderQueue();
  } catch (_) {
    setConnection(false);
  }
}

async function poll() {
  if (state.shutdown) return;
  if (document.hidden) return;
  await refreshState();
}

setInterval(poll, 900);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refreshState();
});

/* ================= ARRANQUE ================= */
(async function start() {
  await refreshState();
  renderPreviews();
})();
