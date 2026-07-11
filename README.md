# Reels — Free Talking-Avatar Generator

Turn a **script + one photo** into a vertical (9:16) talking-avatar reel. 100% free,
open-source engines. Designed to run on a **free GPU** (Google Colab / Kaggle) for
testing and personal reels.

```
script.txt  ──▶  edge-tts voice  ──▶  MuseTalk lip-sync  ──▶  9:16 reel.mp4
```

## Fastest path — free GPU notebook (recommended)

Open [`notebooks/AstroFree_Colab.ipynb`](notebooks/AstroFree_Colab.ipynb) in Google
Colab → set **Runtime → GPU (T4)** → run the cells top to bottom. It clones this
repo, installs MuseTalk, generates the voice, lip-syncs the avatar, and gives you a
downloadable 9:16 `reel.mp4`.

Kaggle users: [`notebooks/AstroFree_Kaggle.ipynb`](notebooks/AstroFree_Kaggle.ipynb)
(enable GPU in the notebook settings; 30 GPU-hrs/week free).

## Engines (all free / open-source)

| Engine | Strength | License | Speed on T4 |
|---|---|---|---|
| **MuseTalk v1.5** | Fast face lip-sync (default) | Apache-2.0 | fast |
| **EchoMimicV2** | Hand + body motion (half-body) | Apache-2.0 | medium |
| **Hallo2** | Best face quality | MIT | slow |

The notebook uses **MuseTalk** because it is the most reliable on a free T4. To use
EchoMimicV2 / Hallo2, run `setup_free.sh` on a local GPU box (below) and pick the
engine via `run.py`.

## Local GPU machine

```bash
# CUDA 12.1 wheels by default; TORCH_CUDA=cu118 for older drivers
bash setup_free.sh

# one-shot: script -> voice -> video
python pipeline.py --script examples/script.txt --avatar avatars/panditji.png --engine musetalk

# or drive an engine directly with your own audio
python run.py musetalk    -a avatars/panditji.png -s output/speech.wav
python run.py echomimicv2 -a avatars/panditji.png -s output/speech.wav
python run.py hallo2      -a avatars/panditji.png -s output/speech.wav

# make it a 9:16 reel (blurred fill + optional burned captions)
python reel_utils.py --in output/<clip>.mp4 --out output/reel.mp4 --srt captions.srt
```

## Voice options (`tts.py`)

- `--engine edge` — free neural voices, no key (default). E.g. `hi-IN-MadhurNeural`
  (male), `hi-IN-SwaraNeural` (female), `en-IN-PrabhatNeural`.
- `--engine mms` — Meta MMS-TTS (offline, many Indian languages).
- `--engine xtts --clone voice.wav` — clone your own voice (XTTS-v2; auto-uses GPU
  when available). XTTS weights are non-commercial — fine for personal/testing.

## Avatar

`avatars/panditji.png` is bundled as the default character. Drop any clear,
front-facing photo into `avatars/` and pass it with `--avatar`.

## Notes / honesty

- **GPU required for realistic results.** On CPU these engines are impractically
  slow — use Colab/Kaggle or a local NVIDIA GPU.
- Model weights (several GB per engine) are **not** in this repo; the notebook and
  `setup_free.sh` download them on first run. `engines/` and `output/` are gitignored.
- Never commit tokens/secrets. `push_to_github.sh` reads `GITHUB_PAT` from the
  environment — do not hardcode a token in it.
