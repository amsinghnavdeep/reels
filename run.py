#!/usr/bin/env python3
"""
Astro Free — Talking Avatar Video Generator
Supports: EchoMimicV2 (hand+body), MuseTalk v1.5 (fast lip-sync), Hallo2 (best face)
All engines are 100% free, open-source (Apache 2.0 / MIT)
"""

import argparse
import subprocess
import sys
import os
import shutil
import yaml
import datetime
from pathlib import Path

ENGINES_DIR = Path(__file__).parent / "engines"

def run(cmd, cwd=None, env=None):
    print(f"\n\u25b6 {' '.join(str(c) for c in cmd)}\n")
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        print(f"[ERROR] Command exited with code {result.returncode}")
        sys.exit(result.returncode)

def venv_python(engine: str) -> str:
    venv = ENGINES_DIR / engine / "venv"
    if (venv / "bin" / "python").exists():
        return str(venv / "bin" / "python")
    if (venv / "Scripts" / "python.exe").exists():
        return str(venv / "Scripts" / "python.exe")
    return sys.executable

def timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def run_echomimicv2(avatar: str, audio: str, pose_dir, output: str):
    repo = ENGINES_DIR / "echomimic_v2"
    if not repo.exists():
        print("[!] EchoMimicV2 not found. Run setup_free.sh first.")
        sys.exit(1)
    cfg_path = repo / "configs" / "runtime_echomimicv2.yaml"
    cfg = {
        "reference_image_path": os.path.abspath(avatar),
        "audio_path": os.path.abspath(audio),
        "pose_dir": os.path.abspath(pose_dir) if pose_dir else None,
        "save_dir": os.path.abspath(output),
        "width": 768, "height": 768, "length": 240, "seed": 42,
        "facemusk_dilation_ratio": 0.1, "facecrop_dilation_ratio": 1.5,
        "context_frames": 12, "context_overlap": 3, "cfg_scale": 1.0,
        "steps": 6, "sample_rate": 16000, "fps": 24, "device": "cuda",
    }
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w") as f:
        import yaml as _yaml
        _yaml.dump(cfg, f, default_flow_style=False)
    py = venv_python("echomimic_v2")
    run([py, "infer_acc.py", "--config", str(cfg_path)], cwd=str(repo))
    print(f"\n\u2705 EchoMimicV2 done \u2192 {output}")

def run_musetalk(avatar: str, audio: str, output: str):
    repo = ENGINES_DIR / "MuseTalk"
    if not repo.exists():
        print("[!] MuseTalk not found. Run setup_free.sh first.")
        sys.exit(1)
    cfg_path = repo / "configs" / "runtime_inference.yaml"
    cfg = {"task_0": {"video_path": os.path.abspath(avatar), "audio_path": os.path.abspath(audio)}}
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cfg_path, "w") as f:
        import yaml as _yaml
        _yaml.dump(cfg, f, default_flow_style=False)
    os.makedirs(output, exist_ok=True)
    py = venv_python("MuseTalk")
    run([py, "scripts/inference.py", "--inference_config", str(cfg_path),
         "--version", "v15", "--batch_size", "8", "--use_float16",
         "--fps", "25", "--parsing_mode", "jaw", "--extra_margin", "10",
         "--result_dir", os.path.abspath(output)], cwd=str(repo))
    print(f"\n\u2705 MuseTalk done \u2192 {output}")

def run_hallo2(avatar: str, audio: str, output: str):
    repo = ENGINES_DIR / "hallo2"
    if not repo.exists():
        print("[!] Hallo2 not found. Run setup_free.sh first.")
        sys.exit(1)
    os.makedirs(output, exist_ok=True)
    py = venv_python("hallo2")
    run([py, "scripts/inference_long.py", "--config", "configs/inference/long.yaml",
         "--source_image", os.path.abspath(avatar), "--driving_audio", os.path.abspath(audio),
         "--pose_weight", "1.0", "--face_weight", "1.0", "--lip_weight", "1.0",
         "--face_expand_ratio", "1.2", "--save_path", os.path.abspath(output)], cwd=str(repo))
    print(f"\n\u2705 Hallo2 done \u2192 {output}")

def main():
    p = argparse.ArgumentParser(description="Astro Free — Talking Avatar Video Generator")
    p.add_argument("engine", choices=["echomimicv2", "musetalk", "hallo2"])
    p.add_argument("-a", "--avatar", required=True)
    p.add_argument("-s", "--audio", required=True)
    p.add_argument("-p", "--pose", default=None)
    p.add_argument("-o", "--output", default=None)
    args = p.parse_args()
    out = args.output or f"output/{timestamp()}"
    os.makedirs(out, exist_ok=True)
    if args.engine == "echomimicv2":
        run_echomimicv2(args.avatar, args.audio, args.pose, out)
    elif args.engine == "musetalk":
        run_musetalk(args.avatar, args.audio, out)
    elif args.engine == "hallo2":
        run_hallo2(args.avatar, args.audio, out)

if __name__ == "__main__":
    main()