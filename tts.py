#!/usr/bin/env python3
"""
Astro Free — Text-to-Speech Module
Supports: edge-tts (free, no API key), MMS-TTS (Meta MIT), XTTS-v2 (voice cloning)

Usage:
    python tts.py --text "Hello world" --voice hi-IN-MadhurNeural
    python tts.py --script examples/script.txt --engine mms --lang hin
    python tts.py --script examples/script.txt --engine xtts --clone voices/my_voice.wav
"""

import argparse
import asyncio
import os
import sys
import subprocess

EDGE_VOICES = {
    "hi-male": "hi-IN-MadhurNeural",
    "hi-female": "hi-IN-SwaraNeural",
    "hi-IN-MadhurNeural": "hi-IN-MadhurNeural",
    "hi-IN-SwaraNeural": "hi-IN-SwaraNeural",
    "en-male": "en-IN-PrabhatNeural",
    "en-female": "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural": "en-IN-PrabhatNeural",
    "en-IN-NeerjaNeural": "en-IN-NeerjaNeural",
    "en-us-male": "en-US-GuyNeural",
    "en-us-female": "en-US-AriaNeural",
}

async def _edge_synthesize(text, voice, output_mp3):
    try:
        import edge_tts
    except ImportError:
        print("[!] edge-tts not installed. Run: pip install edge-tts")
        sys.exit(1)
    communicate = edge_tts.Communicate(text, voice, rate="+0%", pitch="+0Hz")
    await communicate.save(output_mp3)

def tts_edge(text, voice, output_wav):
    voice = EDGE_VOICES.get(voice, voice)
    mp3 = output_wav.replace(".wav", "_tmp.mp3")
    asyncio.run(_edge_synthesize(text, voice, mp3))
    _to_wav_16k(mp3, output_wav)
    os.remove(mp3)
    print(f"edge-tts -> {output_wav}")

def tts_mms(text, lang, output_wav):
    try:
        from transformers import VitsModel, AutoTokenizer
        import torch, scipy.io.wavfile, numpy as np
    except ImportError:
        print("[!] Run: pip install transformers scipy torch")
        sys.exit(1)
    model_id = f"facebook/mms-tts-{lang}"
    print(f"Loading MMS-TTS: {model_id}")
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = VitsModel.from_pretrained(model_id)
    inputs = tokenizer(text, return_tensors="pt")
    with torch.no_grad():
        output = model(**inputs).waveform
    waveform = output.squeeze().numpy()
    sr = model.config.sampling_rate
    scipy.io.wavfile.write(output_wav, rate=sr, data=(waveform * 32767).astype(np.int16))
    subprocess.run(["ffmpeg", "-y", "-i", output_wav, "-ar", "16000", "-ac", "1", output_wav], check=True)
    print(f"MMS-TTS ({lang}) -> {output_wav}")

def tts_xtts(text, clone_wav, lang, output_wav):
    try:
        from TTS.api import TTS
    except Exception as e:
        print(f"[!] Could not import TTS ({type(e).__name__}: {e}). Install with: pip install coqui-tts")
        sys.exit(1)
    import torch
    tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=torch.cuda.is_available())
    tts_model.tts_to_file(text=text, speaker_wav=clone_wav, language=lang, file_path=output_wav)
    print(f"XTTS-v2 -> {output_wav}")

def _to_wav_16k(src, dst):
    try:
        from pydub import AudioSegment
        from pydub.effects import normalize
        audio = AudioSegment.from_file(src)
        audio = audio.set_frame_rate(16000).set_channels(1)
        audio = normalize(audio)
        audio.export(dst, format="wav")
    except ImportError:
        subprocess.run(["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", dst], check=True)

def main():
    p = argparse.ArgumentParser(description="Astro Free TTS")
    p.add_argument("--text")
    p.add_argument("--script")
    p.add_argument("--engine", default="edge", choices=["edge", "mms", "xtts"])
    p.add_argument("--voice", default="hi-IN-MadhurNeural")
    p.add_argument("--lang", default="hin")
    p.add_argument("--clone")
    p.add_argument("--output", default="output/speech.wav")
    args = p.parse_args()
    if not args.text and not args.script:
        print("[!] Provide --text or --script")
        sys.exit(1)
    text = args.text
    if args.script:
        with open(args.script, "r", encoding="utf-8") as f:
            text = f.read().strip()
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    if args.engine == "edge":
        tts_edge(text, args.voice, args.output)
    elif args.engine == "mms":
        tts_mms(text, args.lang, args.output)
    elif args.engine == "xtts":
        if not args.clone:
            print("[!] --clone required for xtts")
            sys.exit(1)
        tts_xtts(text, args.clone, args.lang, args.output)

if __name__ == "__main__":
    main()