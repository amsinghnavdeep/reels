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


def fetch_url(url, dst):
    """Download a public direct-download URL to dst (used when the dashboard supplies
    a video/voice URL instead of relying on the local files on this box)."""
    urllib.request.urlretrieve(url, dst)
    return dst


def report(status, message):
    _req("/result", method="POST", data=b"",
         headers={"x-job-status": status, "x-job-message": (message or "")[:300]})


def _local(prefix):
    """Find a local asset uploaded on this box (reels_state/<prefix>.*)."""
    import glob
    hits = sorted(glob.glob(os.path.join(pipeline.STATE, prefix + ".*")))
    return hits[0] if hits else None


def run_job(cfg):
    os.makedirs(pipeline.STATE, exist_ok=True)
    # video/voice: prefer a URL from the dashboard, else the file uploaded on this box.
    if cfg.get("video_url"):
        video = fetch_url(cfg["video_url"], os.path.join(pipeline.STATE, "video.mp4"))
    else:
        video = _local("video")
    if cfg.get("voice_url"):
        ext = os.path.splitext(cfg["voice_url"])[1] or ".m4a"
        voice = fetch_url(cfg["voice_url"], os.path.join(pipeline.STATE, "voice" + ext))
    else:
        voice = _local("voice")
    if not video or not voice:
        raise RuntimeError("no driving video/voice — upload them on this box or paste URLs in the dashboard")
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
        report("done", (msg or "rendered") + f" · {os.path.basename(reel)}")
        print("reel ready (local):", reel)
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
