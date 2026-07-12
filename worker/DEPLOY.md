# Deploy the Reels dashboard (Cloudflare)

The **UI + API** run free on a single Cloudflare Worker (the Worker serves the
`web/` files as static assets *and* the API). The **GPU rendering** runs free on
Colab/Kaggle (`runner.py`) and talks to the API. You control everything from the UI.

```
 Cloudflare Worker (UI + API) + KV + R2  ◄──  Colab/Kaggle GPU (runner.py)
   web/ + worker/                              runner.py + pipeline.py
```

Token needs: **Workers Scripts: Edit**, **Workers KV Storage: Edit**,
**Workers R2 Storage: Edit**. R2 must be enabled on the account once (free tier).

## 0. Prereqs
```bash
npm i -g wrangler
wrangler login          # opens the browser to authorise your Cloudflare account
```

## 1. Create the storage (once)
```bash
cd worker
wrangler kv namespace create STATE     # copy the printed id into wrangler.toml (id = "...")
wrangler r2 bucket create reels-media
```

## 2. Set the two secrets (once)
```bash
wrangler secret put DASH_KEY     # the password you'll type into the dashboard
wrangler secret put RUNNER_KEY   # a long random token for the GPU runner (e.g. `openssl rand -hex 24`)
```

## 3. Deploy (UI + API together)
```bash
wrangler deploy          # prints https://reels-api.<your-subdomain>.workers.dev
```
Open that URL — it serves the dashboard. Paste your **DASH_KEY**, click **Connect**
(the API URL is pre-filled to the same origin).

## 5. Start the GPU runner
In the Colab/Kaggle notebook, run cells 1–4 (env + weights) once, then the last
**DASHBOARD RUNNER** cell after setting `API` + `RUNNER_KEY` (same value as the secret).
Leave it running — the dashboard badge flips to **runner: online**.

## Use it
- **Assets**: upload a talking-head video + a voice sample once.
- **Script**: type one, or set a topic + free LLM key (Groq/Gemini) and Auto-generate.
- **Instagram** (optional): save login; tick Auto-post to publish after each render.
- **Generate now**: queues a job; the runner renders and the reel appears under Outputs.
- **Daily**: set a time + tick Enable daily. The Worker cron queues one job/day; the
  runner must be online at that time (keep a Kaggle scheduled notebook running, or
  trigger manually). Free GPUs can't stay up 24/7 — see below.

## True unattended daily (free)
Colab/Kaggle won't keep a server alive 24/7 for free. Two options:
1. **Kaggle scheduled notebook**: schedule a daily "Save & Run All" that runs cells
   1–4 then a *single-shot* runner (poll once, render the pending job, exit).
2. **Trigger manually** from the dashboard whenever you want a new reel.
