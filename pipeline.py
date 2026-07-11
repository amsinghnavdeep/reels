#!/usr/bin/env python3
"""
Astro Free — Full End-to-End Pipeline
Script text \u2192 Free TTS \u2192 Resample \u2192 Video Engine \u2192 MP4

Usage:
    python pipeline.py --script examples/script.txt --avatar avatars/panditji.png
    python pipeline.py --script examples/script.txt --avatar avatars/panditji.png --engine hallo2
"""

import argparse
import asyncio
import os
import subprocess
import sys
import datetime
from pathlib import Path

try:
    import edge_tts
except ImportError:
    edge_tts = None

try:
    from pydub import AudioSegment
    from pydub.effects import normalize
except ImportError:
    AudioSegment = None

SUPPORTED_VOICES = {
    "hi-male":   "hi-IN-MadhurNeural",
    "hi-female": "hi-IN-SwaraNeural",
    "en-male":   "en-IN-PrabhatNeural",
    "en-female": "en-IN-NeerjaNeural",
}

async def _synthesize(text, voice, out_mp3):
    communicate = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
    await communicate.save(out_mp3)

def text_to_speech(text, voice, out_wav):
    if edge_tts is None:
        print("[!] edge-tts not installed. Run: pip install edge-tts")
        sys.exit(1)
    voice = SUPPORTED_VOICES.get(voice, voice)
    mp3_path = out_wav.replace(".wav", "_raw.mp3")
    print(f"TTS: {voice} -> {mp3_path}")
    asyncio.run(_synthesize(text, voice, mp3_path))
    if AudioSegment is not None:
        audio = AudioSegment.from_mp3(mp3_path)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio = normalize(audio)
        audio.export(out_wav, format="wav")
        os.remove(mp3_path)
    else:
        subprocess.run(["ffmpeg", "-y", "-i", mp3_path, "-ar", "16000", "-ac", "1", out_wav], check=True)
        os.remove(mp3_path)
    print(f"Audio ready -> {out_wav}")
    return out_wav

def generate_video(engine, avatar, audio, pose, out_dir):
    script_dir = Path(__file__).parent
    cmd = [sys.executable, str(script_dir / "run.py"), engine, "-a", avatar, "-s", audio, "-o", out_dir]
    if pose and engine == "echomimicv2":
        cmd += ["--pose", pose]
    print(f"\nRunning engine: {engine}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)

def timestamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def main():
    p = argparse.ArgumentParser(description="Astro Free Full Pipeline")
    p.add_argument("--script", required=True)
    p.add_argument("--avatar", required=True)
    p.add_argument("--engine", default="echomimicv2", choices=["echomimicv2", "musetalk", "hallo2"])
    p.add_argument("--voice", default="hi-IN-MadhurNeural")
    p.add_argument("--pose", default=None)
    p.add_argument("--output", default=None)
    args = p.parse_args()
    ts = timestamp()
    out_dir = args.output or f"output/{ts}"
    os.makedirs(out_dir, exist_ok=True)
    with open(args.script, "r", encoding="utf-8") as f:
        script_text = f.read().strip()
    print(f"Script loaded ({len(script_text)} chars)")
    audio_path = os.path.join(out_dir, "speech.wav")
    text_to_speech(script_text, args.voice, audio_path)
    generate_video(args.engine, args.avatar, audio_path, args.pose, out_dir)
    print(f"\nPipeline complete! Output -> {out_dir}/")

if __name__ == "__main__":
    main()