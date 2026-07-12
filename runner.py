#!/usr/bin/env python3
"""runner.py — GPU-side worker that drives the Cloudflare dashboard.

Runs on free Colab/Kaggle (where the GPU + isolated envs live). It polls the
Cloudflare Worker for jobs, downloads the current assets, renders the reel with
pipeline.py, and uploads the finished MP4 back to Cloudflare (R2). The dashboard
UI (on Cloudflare Pages) is how you change video / voice / script / IG login /
schedule — this process just executes what the dashboard queues.

    API=https://reels-api.<you>.workers.dev RUNNER_KEY=xxxx python runner.py
"""
import os
import time
import urllib.request

import pipeline

API = os.environ["API"].rstrip("/")
RUNNER_KEY = os.environ["RUNNER_KEY"]
POLL = int(os.environ.get("POLL_SECONDS", "15"))


def _req(path, method="GET", data=None, headers=None):
    h = {"x-runner-key": RUNNER_KEY}
    h.update(headers or {})
    req = urllib.request.Request(API + path, data=data, method=method, headers=h)
    return urllib.request.urlopen(req, timeout=300)


def _get_json(path):
    import json
    return json.loads(_req(path).read())


def download(key, dst):
    with _req("/file/" + key) as r, open(dst, "wb") as f:
        f.write(r.read())
    return dst


def report(status, message, reel=None):
    headers = {"x-job-status": status, "x-job-message": message[:300]}
    body = None
    if reel and os.path.exists(reel):
        headers["x-reel-name"] = os.path.basename(reel)
        headers["content-type"] = "video/mp4"
        body = open(reel, "rb").read()
    _req("/result", method="POST", data=body or b"", headers=headers)


def run_job(cfg):
    import json
    os.makedirs(pipeline.STATE, exist_ok=True)
    ext = os.path.splitext(cfg.get("voice", "voice.m4a"))[1] or ".m4a"
    video = download("assets/video.mp4", os.path.join(pipeline.STATE, "video.mp4"))
    voice = download(cfg["voice"], os.path.join(pipeline.STATE, "voice" + ext))
    script = (cfg.get("script") or "").strip()
    if not script:
        raise RuntimeError("no script set in the dashboard")
    ig = None
    if cfg.get("ig_post") and cfg.get("ig_user") and cfg.get("ig_pass"):
        ig = {"username": cfg["ig_user"], "password": cfg["ig_pass"], "caption": cfg.get("ig_caption", "")}
    res = pipeline.run_pipeline(
        video, voice, script,
        lang=cfg.get("lang", "hi"), trim=cfg.get("trim", ""), crop=cfg.get("crop", ""),
        captions=cfg.get("captions", True), ig=ig, log=print,
    )
    return res["reel"], res["message"]


def poll_once():
    data = _get_json("/job")                    # also registers a heartbeat
    job = data.get("job")
    if not job:
        _req("/heartbeat", method="POST", data=b"")
        return False
    print("picked up job", job["id"])
    try:
        reel, msg = run_job(data["config"])
        report("done", msg, reel)
        print("uploaded reel:", reel)
    except Exception as e:
        print("job failed:", e)
        report("error", str(e))
    return True


def main():
    # ONESHOT=1 → poll once, render a pending job if any, then exit (for Kaggle
    # scheduled notebooks). Default: loop forever (interactive Colab/Kaggle).
    if os.environ.get("ONESHOT"):
        print(f"runner one-shot → {API}")
        poll_once()
        return
    print(f"runner online → {API}")
    while True:
        try:
            poll_once()
        except Exception as e:
            print("poll error:", e)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
