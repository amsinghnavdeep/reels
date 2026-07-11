#!/usr/bin/env bash
# Astro Free — One-time setup script (LOCAL GPU machines)
# Clones all 3 engine repos + downloads pretrained weights.
#
#   bash setup_free.sh                 # defaults to CUDA 12.1 wheels
#   TORCH_CUDA=cu118 bash setup_free.sh  # older CUDA 11.8 driver
#
# Requirements: Python 3.10+, Git, ~20GB disk, NVIDIA GPU.
# On Google Colab / Kaggle you do NOT need this script — use the notebooks in
# notebooks/ instead (torch + CUDA are already provided there).

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENGINES_DIR="$SCRIPT_DIR/engines"
TORCH_CUDA="${TORCH_CUDA:-cu121}"
TORCH_INDEX="https://download.pytorch.org/whl/${TORCH_CUDA}"
mkdir -p "$ENGINES_DIR"

echo "=============================="
echo "  Astro Free — Engine Setup"
echo "=============================="

if ! nvidia-smi &>/dev/null; then
    echo "[WARNING] No NVIDIA GPU. Engines will run on CPU (very slow)."
    read -p "Continue anyway? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0
fi

make_venv() {
    local name=$1 req=$2 dir="$ENGINES_DIR/$name"
    echo "  Creating venv for $name..."
    python3 -m venv "$dir/venv"
    source "$dir/venv/bin/activate"
    pip install --upgrade pip wheel -q
    [[ -f "$req" ]] && pip install -r "$req" -q
    deactivate
}

hf_download() {
    local repo=$1 dir=$2
    echo "  Downloading from HuggingFace: $repo"
    python3 -c "from huggingface_hub import snapshot_download; snapshot_download(repo_id='$repo', local_dir='$dir', local_dir_use_symlinks=False)"
}

# 1. EchoMimicV2
echo ""
echo "[1/3] EchoMimicV2 — Hand + Body Animation"
EMV2_DIR="$ENGINES_DIR/echomimic_v2"
[[ ! -d "$EMV2_DIR" ]] && git clone --depth 1 https://github.com/antgroup/echomimic_v2.git "$EMV2_DIR"
make_venv "echomimic_v2" "$EMV2_DIR/requirements.txt"
source "$EMV2_DIR/venv/bin/activate"
pip install torch torchvision torchaudio --index-url "$TORCH_INDEX" -q
pip install xformers -q || true
pip install huggingface_hub -q
hf_download "BadToBest/EchoMimicV2" "$EMV2_DIR/pretrained_weights"
deactivate
echo "  EchoMimicV2 ready"

# 2. MuseTalk
echo ""
echo "[2/3] MuseTalk v1.5 — Fast Lip-Sync"
MT_DIR="$ENGINES_DIR/MuseTalk"
[[ ! -d "$MT_DIR" ]] && git clone --depth 1 https://github.com/TMElyralab/MuseTalk.git "$MT_DIR"
make_venv "MuseTalk" "$MT_DIR/requirements.txt"
source "$MT_DIR/venv/bin/activate"
pip install torch torchvision torchaudio --index-url "$TORCH_INDEX" -q
pip install huggingface_hub -q
hf_download "TMElyralab/MuseTalk" "$MT_DIR/models"
deactivate
echo "  MuseTalk ready"

# 3. Hallo2
echo ""
echo "[3/3] Hallo2 — Best Face Quality"
H2_DIR="$ENGINES_DIR/hallo2"
[[ ! -d "$H2_DIR" ]] && git clone --depth 1 https://github.com/fudan-generative-vision/hallo2.git "$H2_DIR"
make_venv "hallo2" "$H2_DIR/requirements.txt"
source "$H2_DIR/venv/bin/activate"
pip install torch torchvision torchaudio --index-url "$TORCH_INDEX" -q
pip install huggingface_hub -q
hf_download "fudan-generative-vision/hallo2" "$H2_DIR/pretrained_models/hallo2"
hf_download "facebook/wav2vec2-base-960h" "$H2_DIR/pretrained_models/wav2vec2"
deactivate
echo "  Hallo2 ready"

# 4. Glue deps
echo ""
echo "Installing glue dependencies..."
pip3 install --user edge-tts pydub pyyaml huggingface_hub -q

echo ""
echo "=============================="
echo "  All engines ready!"
echo ""
echo "  Quick start:"
echo "    python pipeline.py --script examples/script.txt --avatar avatars/panditji.png"
echo "    python run.py echomimicv2 -a avatars/panditji.png -s audio/speech.wav"
echo "=============================="