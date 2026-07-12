// Reels dashboard — talks to the Cloudflare Worker API. All state lives server-side
// (KV) except the API URL + dashboard key, which we keep in localStorage for convenience.
const $ = (id) => document.getElementById(id);
// UI is served from the same Worker that hosts the API, so default to this origin.
let API = localStorage.getItem("reels_api") || window.location.origin;
let KEY = localStorage.getItem("reels_key") || "";
$("api").value = API;
$("key").value = KEY;

async function api(path, opts = {}) {
  if (!API) throw new Error("Set the Worker API URL first");
  const headers = Object.assign({ "x-dash-key": KEY }, opts.headers || {});
  const res = await fetch(API.replace(/\/$/, "") + path, Object.assign({}, opts, { headers }));
  if (!res.ok) throw new Error(`${path} → ${res.status} ${await res.text()}`);
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function toast(el, msg, ok = true) {
  const n = $(el);
  n.textContent = msg;
  n.style.color = ok ? "var(--mut)" : "#ff7b72";
}

// ---- connect + poll runner status --------------------------------------------
$("save-conn").onclick = async () => {
  API = $("api").value.trim();
  KEY = $("key").value.trim();
  localStorage.setItem("reels_api", API);
  localStorage.setItem("reels_key", KEY);
  await loadConfig();
  refreshStatus();
  refreshGallery();
};

async function refreshStatus() {
  try {
    const s = await api("/status");
    const alive = s.runner_seen && Date.now() / 1000 - s.runner_seen < 120;
    const b = $("runner");
    b.textContent = "runner: " + (alive ? "online" : "offline") + (s.state ? " · " + s.state : "");
    b.className = "badge " + (alive ? "on" : "off");
    if (s.state) {
      const line = "status: " + s.state + (s.message ? " — " + s.message : "");
      toast("run-state", line);
      toast("last-run", line);
    }
  } catch (e) { /* not connected yet */ }
}
setInterval(refreshStatus, 10000);

// ---- config load/save --------------------------------------------------------
async function loadConfig() {
  try {
    const c = await api("/config");
    $("script").value = c.script || "";
    $("topic").value = c.topic || "";
    $("provider").value = c.provider || "groq";
    $("video-url").value = c.video_url || "";
    $("voice-url").value = c.voice_url || "";
    $("trim").value = c.trim || "";
    $("crop").value = c.crop || "";
    $("lang").value = c.lang || "hi";
    $("captions").checked = c.captions !== false;
    $("sched").value = c.schedule || "03:00";
    $("sched-on").checked = !!c.schedule_on;
    $("ig-user").value = c.ig_user || "";
    $("ig-caption").value = c.ig_caption || "";
    $("ig-post").checked = !!c.ig_post;
  } catch (e) { toast("run-state", e.message, false); }
}

function cfgFromForm() {
  return {
    script: $("script").value, topic: $("topic").value, provider: $("provider").value,
    llmkey: $("llmkey").value || undefined,
    video_url: $("video-url").value, voice_url: $("voice-url").value,
    trim: $("trim").value, crop: $("crop").value,
    lang: $("lang").value, captions: $("captions").checked,
    schedule: $("sched").value, schedule_on: $("sched-on").checked,
    ig_caption: $("ig-caption").value, ig_post: $("ig-post").checked,
  };
}

$("save-cfg").onclick = async () => {
  try { await api("/config", { method: "POST", body: JSON.stringify(cfgFromForm()) }); toast("run-state", "config saved ✓"); }
  catch (e) { toast("run-state", e.message, false); }
};

// ---- Instagram creds (stored server-side; write-only from UI) -----------------
$("save-ig").onclick = async () => {
  try {
    await api("/ig", { method: "POST", body: JSON.stringify({
      ig_user: $("ig-user").value, ig_pass: $("ig-pass").value }) });
    $("ig-pass").value = "";
    toast("run-state", "Instagram login saved ✓");
  } catch (e) { toast("run-state", e.message, false); }
};

// ---- auto-generate script ----------------------------------------------------
$("gen-script").onclick = async () => {
  try {
    toast("run-state", "generating script…");
    const r = await api("/gen-script", { method: "POST", body: JSON.stringify({
      topic: $("topic").value, provider: $("provider").value, llmkey: $("llmkey").value, lang: $("lang").value }) });
    $("script").value = r.script || "";
    toast("run-state", "script generated ✓");
  } catch (e) { toast("run-state", e.message, false); }
};

// ---- manual trigger ----------------------------------------------------------
$("run-now").onclick = async () => {
  try {
    await api("/config", { method: "POST", body: JSON.stringify(cfgFromForm()) });
    await api("/run", { method: "POST", body: "{}" });
    toast("run-state", "job queued — the GPU runner will pick it up shortly");
  } catch (e) { toast("run-state", e.message, false); }
};

// ---- last-run status ---------------------------------------------------------
$("refresh").onclick = refreshStatus;

if (API) { loadConfig(); refreshStatus(); }
