#!/usr/bin/env python3
"""Download MuseTalk weights via the huggingface_hub Python API.

MuseTalk's own download_weights.sh calls `huggingface-cli download`, which the
current huggingface_hub has REMOVED -> it prints a deprecation notice and
downloads nothing. Run this from the MuseTalk engine dir instead.
"""
import os, glob
from huggingface_hub import hf_hub_download

os.makedirs("models/face-parse-bisent", exist_ok=True)


def dl(repo, filename, local_dir):
    os.makedirs(local_dir, exist_ok=True)
    p = hf_hub_download(repo_id=repo, filename=filename, local_dir=local_dir)
    print("  ok:", p)


for f in ["musetalk/musetalk.json", "musetalk/pytorch_model.bin",
          "musetalkV15/musetalk.json", "musetalkV15/unet.pth"]:
    dl("TMElyralab/MuseTalk", f, "models")
for f in ["config.json", "diffusion_pytorch_model.bin"]:
    dl("stabilityai/sd-vae-ft-mse", f, "models/sd-vae")
for f in ["config.json", "pytorch_model.bin", "preprocessor_config.json"]:
    dl("openai/whisper-tiny", f, "models/whisper")
dl("yzd-v/DWPose", "dw-ll_ucoco_384.pth", "models/dwpose")

os.system("gdown 154JgKpzCPW82qINcVieuPH3fZ2e0P812 "
          "-O models/face-parse-bisent/79999_iter.pth")
os.system("curl -sL https://download.pytorch.org/models/resnet18-5c106cde.pth "
          "-o models/face-parse-bisent/resnet18-5c106cde.pth")

print("\nweights present:")
for p in sorted(glob.glob("models/**/*", recursive=True)):
    if os.path.isfile(p):
        print(" ", p, round(os.path.getsize(p) / 1e6, 1), "MB")
