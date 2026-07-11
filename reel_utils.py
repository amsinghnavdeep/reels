#!/usr/bin/env python3
"""reel_utils — turn an engine's talking-head clip into a 9:16 reel.

Pads/crops any video to a vertical 1080x1920 frame over a blurred fill of
itself, and (optionally) burns captions from an .srt file. Pure ffmpeg, no GPU.

    python reel_utils.py --in talking.mp4 --out reel.mp4
    python reel_utils.py --in talking.mp4 --out reel.mp4 --srt captions.srt
"""
import argparse
import subprocess
import sys


def to_vertical(src, out, srt=None, w=1080, h=1920, font="Noto Sans Devanagari"):
    # Blurred, zoom-filled background + the sharp clip centered on top.
    vf = (
        f"[0:v]scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},boxblur=luma_radius=40:luma_power=1[bg];"
        f"[0:v]scale={w}:-2:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
    )
    if srt:
        # Escape path for the subtitles filter.
        srt_esc = srt.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf += (
            f",subtitles='{srt_esc}':force_style="
            f"'FontName={font},FontSize=16,PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H80000000,BorderStyle=3,Outline=2,Alignment=2,MarginV=90'"
        )
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-filter_complex", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", "-pix_fmt", "yuv420p", out,
    ]
    print("▶ ffmpeg vertical compose…")
    r = subprocess.run(cmd)
    if r.returncode != 0:
        sys.exit(r.returncode)
    print(f"✅ reel -> {out}")
    return out


def main():
    p = argparse.ArgumentParser(description="Compose a 9:16 reel from a clip.")
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--srt", default=None, help="Optional captions (.srt).")
    p.add_argument("--font", default="Noto Sans Devanagari")
    args = p.parse_args()
    to_vertical(args.inp, args.out, args.srt, font=args.font)


if __name__ == "__main__":
    main()
