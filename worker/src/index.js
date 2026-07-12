// Reels coordination API (Cloudflare Worker) — TEXT-ONLY, no file storage.
//   - Dashboard (served by this Worker) calls UI endpoints with header `x-dash-key`.
//   - The GPU runner (Colab/Kaggle) calls runner endpoints with header `x-runner-key`.
//   - Everything lives in KV (binding: STATE): config, job, Instagram creds, heartbeat.
//   - No videos/reels are stored here. The driving video + voice live on the GPU box
//     (or a URL you paste); the finished reel is posted to Instagram / downloaded there.
//
// Secrets (wrangler secret put): DASH_KEY, RUNNER_KEY.

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "content-type,x-dash-key,x-runner-key,x-job-status,x-job-message",
};

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json", ...CORS } });
const text = (s, status = 200) => new Response(s, { status, headers: CORS });

const dashKey = (req, url) => req.headers.get("x-dash-key") || url.searchParams.get("k") || "";

async function getConfig(env) {
  return JSON.parse((await env.STATE.get("config")) || "{}");
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url);
    const p = url.pathname.replace(/\/+$/, "") || "/";
    if (req.method === "OPTIONS") return text("", 204);

    // Non-API paths fall through to the static assets (the dashboard UI in web/).
    const API = new Set(["/config", "/ig", "/gen-script", "/run", "/status", "/job", "/heartbeat", "/result"]);
    if (!API.has(p)) return env.ASSETS ? env.ASSETS.fetch(req) : text("not found", 404);

    const dashOK = () => dashKey(req, url) && dashKey(req, url) === env.DASH_KEY;
    const runnerOK = () => req.headers.get("x-runner-key") === env.RUNNER_KEY;

    try {
      // =================================================================== UI API
      if (p === "/config" && req.method === "GET") {
        if (!dashOK()) return text("unauthorized", 401);
        const c = await getConfig(env);
        delete c.ig_pass; delete c.llmkey;               // never echo secrets back
        return json(c);
      }
      if (p === "/config" && req.method === "POST") {
        if (!dashOK()) return text("unauthorized", 401);
        const body = await req.json();
        const cur = await getConfig(env);
        for (const [k, v] of Object.entries(body)) if (v !== undefined) cur[k] = v;
        await env.STATE.put("config", JSON.stringify(cur));
        return json({ ok: true });
      }
      if (p === "/ig" && req.method === "POST") {
        if (!dashOK()) return text("unauthorized", 401);
        const b = await req.json();
        const cur = await getConfig(env);
        if (b.ig_user !== undefined) cur.ig_user = b.ig_user;
        if (b.ig_pass) cur.ig_pass = b.ig_pass;           // write-only from UI
        await env.STATE.put("config", JSON.stringify(cur));
        return json({ ok: true });
      }
      if (p === "/gen-script" && req.method === "POST") {
        if (!dashOK()) return text("unauthorized", 401);
        const b = await req.json();
        const script = await genScript(b.topic, b.provider, b.llmkey, b.lang);
        const cur = await getConfig(env);
        cur.script = script;
        if (b.llmkey) cur.llmkey = b.llmkey;
        await env.STATE.put("config", JSON.stringify(cur));
        return json({ script });
      }
      if (p === "/run" && req.method === "POST") {
        if (!dashOK()) return text("unauthorized", 401);
        const job = { id: Date.now().toString(36), status: "pending", message: "", created: Date.now() / 1000 };
        await env.STATE.put("job", JSON.stringify(job));
        return json(job);
      }
      if (p === "/status" && req.method === "GET") {
        if (!dashOK()) return text("unauthorized", 401);
        const job = JSON.parse((await env.STATE.get("job")) || "{}");
        const seen = Number((await env.STATE.get("runner_seen")) || 0);
        return json({ state: job.status, message: job.message, runner_seen: seen });
      }

      // =============================================================== RUNNER API
      if (p === "/job" && req.method === "GET") {
        if (!runnerOK()) return text("unauthorized", 401);
        await env.STATE.put("runner_seen", String(Date.now() / 1000));
        const job = JSON.parse((await env.STATE.get("job")) || "{}");
        if (job.status !== "pending") return json({ job: null });
        job.status = "running";
        await env.STATE.put("job", JSON.stringify(job));
        return json({ job, config: await getConfig(env) });
      }
      if (p === "/heartbeat" && req.method === "POST") {
        if (!runnerOK()) return text("unauthorized", 401);
        await env.STATE.put("runner_seen", String(Date.now() / 1000));
        return json({ ok: true });
      }
      if (p === "/result" && req.method === "POST") {
        if (!runnerOK()) return text("unauthorized", 401);
        const job = JSON.parse((await env.STATE.get("job")) || "{}");
        job.status = req.headers.get("x-job-status") || "done";
        job.message = req.headers.get("x-job-message") || "";
        await env.STATE.put("job", JSON.stringify(job));
        return json({ ok: true });
      }

      return text("not found", 404);
    } catch (e) {
      return text("error: " + (e && e.message ? e.message : e), 500);
    }
  },

  // daily schedule: cron in wrangler.toml. If enabled + time matches, queue a job.
  async scheduled(event, env, ctx) {
    const c = await getConfig(env);
    if (!c.schedule_on) return;
    const now = new Date();
    const [h] = (c.schedule || "03:00").split(":").map(Number);
    if (now.getUTCHours() === h && now.getUTCMinutes() < 15) {
      const job = { id: Date.now().toString(36), status: "pending", message: "scheduled", created: Date.now() / 1000 };
      await env.STATE.put("job", JSON.stringify(job));
    }
  },
};

async function genScript(topic, provider, key, lang) {
  const prompt =
    `Write a short, punchy ${lang || "Hindi"} script for a ~20 second vertical Instagram reel about: ` +
    `${topic}. One speaker talking to camera. Strong hook, 2-3 crisp value points, end with a call to action. ` +
    `Plain text only, no emojis, no stage directions, no headings.`;
  if (provider === "gemini") {
    const r = await fetch(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key=${key}`,
      { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }) });
    const b = await r.json();
    return b.candidates?.[0]?.content?.parts?.[0]?.text?.trim() || "";
  }
  const r = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: { authorization: `Bearer ${key}`, "content-type": "application/json" },
    body: JSON.stringify({ model: "llama-3.3-70b-versatile", temperature: 0.9,
      messages: [{ role: "user", content: prompt }] }),
  });
  const b = await r.json();
  return b.choices?.[0]?.message?.content?.trim() || "";
}
