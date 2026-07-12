#!/usr/bin/env python3
"""pipeline.py — end-to-end talking-avatar reel factory.

One call turns  (driving video + voice sample + script)  into a sharp 9:16 reel:

    voice sample ─┐
                  ├─► XTTS clone (isolated py3.10 'tts' env) ─► speech.wav (silence-trimmed)
    script ───────┘
    driving video ─► normalise/downscale ─► MuseTalk mouth-swap (py3.10 'muse' env) ─► raw.mp4
    raw.mp4 ─► GFPGAN face-restore + Real-ESRGAN bg upscale ─► sharp.mp4
    sharp.mp4 + captions.srt ─► ffmpeg 9:16 compose ─► reel.mp4  (+ optional Instagram post)

Runs in the Colab/Kaggle kernel and shells out to the two isolated conda envs the
notebook already builds (cells 3–4). Import it from the Gradio dashboard (app.py)
or run it standalone:

    python pipeline.py --video clip.mp4 --voice me.m4a --script examples/script.txt
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# --------------------------------------------------------------------------- paths
def base_dir():
    for p in (os.environ.get("REELS_HOME"), "/content/reels",
              "/kaggle/working/reels", os.path.dirname(os.path.abspath(__file__))):
        if p and os.path.isdir(p):
            return p
    return os.getcwd()

ROOT = base_dir()
OUT = os.path.join(ROOT, "output")
STATE = os.path.join(ROOT, "reels_state")          # gitignored: assets + config live here
MUSE = os.path.join(ROOT, "engines", "MuseTalk")
CONDA = "/opt/conda/etc/profile.d/conda.sh"
os.makedirs(OUT, exist_ok=True)
os.makedirs(STATE, exist_ok=True)


def _run(cmd, **kw):
    """Run a shell command, streaming output; raise on failure."""
    print("···", cmd if isinstance(cmd, str) else " ".join(cmd), flush=True)
    r = subprocess.run(cmd, shell=isinstance(cmd, str), **kw)
    if r.returncode != 0:
        raise RuntimeError(f"command failed ({r.returncode}): {cmd}")
    return r


def _conda(env, inner):
    """Run `inner` inside conda env `env`, forcing a headless matplotlib backend."""
    return _run(f"source {CONDA} && conda activate {env} && MPLBACKEND=Agg {inner}")


# --------------------------------------------------------------------------- 1. voice
def clone_voice(voice_src, script_path, lang="hi", log=print):
    """Clone the voice on the script with XTTS, then strip leading/trailing silence
    so the mouth tracks the words. Returns path to speech.wav."""
    ref = os.path.join(OUT, "voice_ref.wav")
    raw = os.path.join(OUT, "speech_raw.wav")
    out = os.path.join(OUT, "speech.wav")
    log("cloning voice (XTTS)…")
    _run(f'ffmpeg -y -i "{voice_src}" -ar 16000 -ac 1 "{ref}"',
         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _conda("tts",
           f'COQUI_TOS_AGREED=1 python "{ROOT}/tts.py" --script "{script_path}" '
           f'--engine xtts --clone "{ref}" --lang {lang} --output "{raw}"')
    if not os.path.exists(raw):
        raise RuntimeError("XTTS produced no audio — check the tts env / script")
    # timing fix: trim silence off both ends
    _run(f'ffmpeg -y -i "{raw}" -af '
         f'"silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB:'
         f'stop_periods=-1:stop_silence=0.2:stop_threshold=-45dB" -ar 16000 -ac 1 "{out}"',
         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


# --------------------------------------------------------------------------- 2. lip-sync
def _normalise_video(src, trim="", crop="", log=print):
    """Re-encode the upload to a safe path + cap the long side at 1280px (avoids the
    special-char ffmpeg crash and the 4K out-of-memory kill)."""
    dst = os.path.join(OUT, "drive_clip.mp4")
    dn = "scale=1280:1280:force_original_aspect_ratio=decrease:force_divisible_by=2"
    vf = f'-vf "{crop},{dn}"' if crop else f'-vf "{dn}"'
    log("normalising driving video (safe name + ≤1280px)…")
    _run(f'ffmpeg -y {trim} -i "{src}" {vf} -an -r 25 -c:v libx264 -pix_fmt yuv420p "{dst}"',
         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return dst


def lipsync(drive_video, speech_wav, trim="", crop="", log=print):
    """Run MuseTalk to swap the mouth of `drive_video` to `speech_wav`. MuseTalk loops
    the clip to cover the audio, so output length follows the SCRIPT, not the clip.
    Returns path to the raw MuseTalk mp4."""
    clip = _normalise_video(drive_video, trim, crop, log)
    import yaml
    cfg = {"task_0": {"video_path": clip, "audio_path": speech_wav}}
    cfgdir = os.path.join(MUSE, "configs", "inference")
    os.makedirs(cfgdir, exist_ok=True)
    open(os.path.join(cfgdir, "reels.yaml"), "w").write(yaml.dump(cfg))
    # guard MuseTalk's unconditional temp cleanup (crashes on image input)
    _run("sed -i 's|^            shutil.rmtree(save_dir_full)|"
         "            if get_file_type(video_path) == \"video\": shutil.rmtree(save_dir_full)|' "
         f'"{MUSE}/scripts/inference.py"')
    log("running MuseTalk lip-sync… (landmark extraction is the slow part)")
    _conda("muse",
           f'cd "{MUSE}" && FFMPEG_PATH=/usr/bin python -m scripts.inference '
           f'--inference_config configs/inference/reels.yaml '
           f'--result_dir "{OUT}/muse" '
           f'--unet_model_path models/musetalkV15/unet.pth '
           f'--unet_config models/musetalkV15/musetalk.json '
           f'--version v15 --fps 25 --batch_size 4 --use_float16 '
           f'--parsing_mode jaw --extra_margin 10')
    import glob
    clips = sorted(glob.glob(f"{OUT}/muse/**/*.mp4", recursive=True), key=os.path.getmtime)
    if not clips:
        raise RuntimeError("MuseTalk produced no output")
    return clips[-1]


# --------------------------------------------------------------------------- 3. sharpen
_RESTORE_SRC = r'''
import os, glob, cv2
from gfpgan import GFPGANer
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer

root = "%(out)s"
# Real-ESRGAN as the background/frame upscaler (fixes artifacts + noise on the whole frame)
bg = None
try:
    model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=2)
    bg = RealESRGANer(
        scale=2,
        model_path="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.1/RealESRGAN_x2plus.pth",
        model=model, tile=400, tile_pad=10, pre_pad=0, half=True)
    print("Real-ESRGAN background upscaler: ON")
except Exception as e:
    print("Real-ESRGAN unavailable (%%s) — GFPGAN face-only restore" %% e)

# GFPGAN restores the face (mouth/teeth) that MuseTalk softened
gfp = GFPGANer(
    model_path="https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth",
    upscale=2, arch="clean", channel_multiplier=2, bg_upsampler=bg)

frames = sorted(glob.glob(root + "/enh_in/*.png"))
for i, fp in enumerate(frames):
    img = cv2.imread(fp, cv2.IMREAD_COLOR)
    _, _, out = gfp.enhance(img, has_aligned=False, only_center_face=True, paste_back=True)
    cv2.imwrite(root + "/enh_out/" + os.path.basename(fp), out)
    if i %% 50 == 0:
        print("  restored", i, "/", len(frames), flush=True)
print("done", len(frames), "frames")
'''


def sharpen(raw_mp4, speech_wav, log=print):
    """GFPGAN face-restore + Real-ESRGAN frame upscale → input-quality sharpness.
    Returns path to the enhanced mp4 (or the raw clip if enhancement is unavailable)."""
    enh_in, enh_out = os.path.join(OUT, "enh_in"), os.path.join(OUT, "enh_out")
    os.makedirs(enh_in, exist_ok=True)
    os.makedirs(enh_out, exist_ok=True)
    _run(f'rm -f "{enh_in}"/* "{enh_out}"/*')
    _run(f'ffmpeg -y -i "{raw_mp4}" -qscale:v 1 "{enh_in}/f%06d.png"',
         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # one-time deps + the classic torchvision-0.16 basicsr import patch
    log("sharpening (GFPGAN + Real-ESRGAN)…")
    try:
        _conda("muse",
               'pip -q install gfpgan realesrgan basicsr facexlib >/dev/null 2>&1; '
               'BS=$(python -c "import basicsr,os;print(os.path.dirname(basicsr.__file__))"); '
               'sed -i "s/torchvision.transforms.functional_tensor/torchvision.transforms.functional/" '
               '"$BS/data/degradations.py" 2>/dev/null; true')
        script = os.path.join(OUT, "_restore.py")
        open(script, "w").write(_RESTORE_SRC % {"out": OUT})
        _conda("muse", f'python "{script}"')
        hd = os.path.join(OUT, "muse_hd.mp4")
        _run(f'ffmpeg -y -framerate 25 -i "{enh_out}/f%06d.png" -i "{speech_wav}" '
             f'-c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "{hd}"',
             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(hd):
            return hd
    except Exception as e:
        log(f"sharpen step skipped ({e}); using the raw MuseTalk clip")
    return raw_mp4


# --------------------------------------------------------------------------- 4. captions
def make_srt(script_text, speech_wav, log=print):
    """Cheap, dependency-free captions: split the script into short chunks and spread
    them evenly across the audio duration. Good enough for reels; no extra model."""
    try:
        dur = float(subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", speech_wav]).decode().strip())
    except Exception:
        return None
    # break on sentence enders / danda, then cap chunk length
    parts = re.split(r"(?<=[।!?.])\s+", script_text.strip())
    chunks = []
    for p in parts:
        p = p.strip()
        while len(p) > 42:
            cut = p.rfind(" ", 0, 42)
            cut = cut if cut > 0 else 42
            chunks.append(p[:cut].strip())
            p = p[cut:].strip()
        if p:
            chunks.append(p)
    if not chunks:
        return None
    per = dur / len(chunks)

    def ts(t):
        h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    srt = os.path.join(OUT, "captions.srt")
    with open(srt, "w", encoding="utf-8") as f:
        for i, c in enumerate(chunks):
            f.write(f"{i+1}\n{ts(i*per)} --> {ts((i+1)*per)}\n{c}\n\n")
    log(f"captions: {len(chunks)} lines")
    return srt


# --------------------------------------------------------------------------- 5. compose
def compose(clip, srt=None, log=print):
    out = os.path.join(OUT, f"reel_{int(time.time())}.mp4")
    log("composing 9:16 reel…")
    cmd = f'python "{ROOT}/reel_utils.py" --in "{clip}" --out "{out}"'
    if srt:
        cmd += f' --srt "{srt}"'
    _run(cmd)
    return out


# --------------------------------------------------------------------------- 6. script LLM (optional)
def gen_script(topic, provider="groq", api_key="", lang="Hindi", log=print):
    """Generate a fresh ~20s reel script from a topic using a FREE LLM API.
    provider: 'groq' (free tier) or 'gemini' (free tier)."""
    prompt = (
        f"Write a short, punchy {lang} script for a ~20 second vertical Instagram reel "
        f"about: {topic}. One speaker talking to camera. Start with a strong hook, give "
        f"2-3 crisp value points, end with a call to action. Plain text only, no emojis, "
        f"no stage directions, no headings."
    )
    import urllib.request
    if provider == "groq":
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps({
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.9,
            }).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        body = json.loads(urllib.request.urlopen(req, timeout=60).read())
        return body["choices"][0]["message"]["content"].strip()
    elif provider == "gemini":
        url = ("https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-1.5-flash:generateContent?key={api_key}")
        req = urllib.request.Request(
            url, data=json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode(),
            headers={"Content-Type": "application/json"})
        body = json.loads(urllib.request.urlopen(req, timeout=60).read())
        return body["candidates"][0]["content"]["parts"][0]["text"].strip()
    raise ValueError(f"unknown provider {provider}")


# --------------------------------------------------------------------------- 7. Instagram (optional)
def post_instagram(reel_path, caption, username, password, log=print):
    """Auto-post via instagrapi (unofficial). Returns (ok, message).
    NOTE: unofficial API — Instagram may flag/limit the account. Use at your own risk."""
    try:
        from instagrapi import Client
    except Exception:
        _run(f"{sys.executable} -m pip -q install instagrapi")
        from instagrapi import Client
    cl = Client()
    sess = os.path.join(STATE, "ig_session.json")
    try:
        if os.path.exists(sess):
            cl.load_settings(sess)
        cl.login(username, password)
        cl.dump_settings(sess)
        cl.clip_upload(reel_path, caption)
        return True, "posted to Instagram"
    except Exception as e:
        return False, f"Instagram post failed: {e}"


# --------------------------------------------------------------------------- orchestrator
def run_pipeline(video, voice, script_text, lang="hi", trim="", crop="",
                 captions=True, ig=None, log=print):
    """Full run. `ig` = dict(username, password, caption) to also auto-post. Returns dict."""
    os.makedirs(OUT, exist_ok=True)
    script_path = os.path.join(OUT, "script.txt")
    open(script_path, "w", encoding="utf-8").write(script_text.strip())

    speech = clone_voice(voice, script_path, lang=lang, log=log)
    raw = lipsync(video, speech, trim=trim, crop=crop, log=log)
    sharp = sharpen(raw, speech, log=log)
    srt = make_srt(script_text, speech, log=log) if captions else None
    reel = compose(sharp, srt, log=log)

    result = {"reel": reel, "posted": False, "message": "done"}
    if ig and ig.get("username") and ig.get("password"):
        ok, msg = post_instagram(reel, ig.get("caption", ""), ig["username"], ig["password"], log=log)
        result["posted"], result["message"] = ok, msg
        log(msg)
    log(f"reel ready: {reel}")
    return result


def main():
    p = argparse.ArgumentParser(description="talking-avatar reel pipeline")
    p.add_argument("--video", required=True)
    p.add_argument("--voice", required=True)
    p.add_argument("--script", required=True, help="path to a .txt script")
    p.add_argument("--lang", default="hi")
    p.add_argument("--trim", default="")
    p.add_argument("--crop", default="")
    p.add_argument("--no-captions", action="store_true")
    args = p.parse_args()
    text = open(args.script, encoding="utf-8").read()
    run_pipeline(args.video, args.voice, text, lang=args.lang,
                 trim=args.trim, crop=args.crop, captions=not args.no_captions)


if __name__ == "__main__":
    main()
