# Getting Started

> **Status:** open-video is **v0.1.0**. You install it from the GitHub tag with
> `scripts/install.sh` (there is no PyPI package). The heavy lifting (model inference) happens
> inside a local [ComfyUI](https://github.com/comfyanonymous/ComfyUI) server that open-video
> drives over HTTP.

This guide takes you from an empty machine to your first open-video-generated clip. For the
short version, see [`QUICKSTART.md`](./QUICKSTART.md).

## Fast path (v0.1.0)

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/agent-next/video-agent
cd video-agent
bash scripts/install.sh      # ComfyUI engine + H3 INT8 weights (resumable, ~54 GB)
open-video pull h3           # verify / resume the H3 weights
open-video status            # ComfyUI health + weight inventory
open-video run "a cinematic lighthouse on a cliff at dusk, golden light, stormy sea"
```

If you skip the installer, `pip install -e .` from the repo root installs the `open-video` entry
point. Sections 3-4 below are the **manual alternative** (your own ComfyUI checkout and
hand-downloaded weights).

---

## 1. What you need

| Requirement | Why | Notes |
|---|---|---|
| **Python 3.10+** | Run the open-video orchestrator | 3.11/3.12 recommended. The orchestrator itself has no third-party dependencies. |
| **Git** | Clone the repo | |
| **An NVIDIA GPU** | Run the H3 model | See the VRAM table below. |
| **NVIDIA drivers + CUDA** | ComfyUI inference | CUDA 12.x, current driver. |
| **ffmpeg** | Stitching shots + audio | `ffmpeg -version` should print a version. |
| **~60 GB free disk** | ComfyUI + model weights + outputs | `install.sh` downloads ~54 GB of INT8 H3 weights. |

### GPU / VRAM cheat sheet (H3)

`install.sh` / `open-video pull h3` install the INT8 ConvRot tier only (checksum verified, ~54 GB).
W4 and NF4 are manual, experimental downloads (see [`docs/h3_ecosystem.md`](./h3_ecosystem.md) for
the full list and known issues):

| VRAM | H3 quant | Notes |
|---|---|---|
| **≥ 22 GiB** | INT8 ConvRot (default) | Comfy-Org; the tier `pull` installs |
| **12–22 GiB** | INT8 + ComfyUI low-VRAM offload | enabled automatically by the installer |
| **9–12 GB** | W4 ConvRot (~10 GB) | manual, experimental (`DmitryDB/MiniMax-H3-ComfyUI-Quants`) |
| **< 9 GB** | NF4 (~8 GB) | manual, experimental (`DiffSynth-Studio/MiniMax-H3-NF4`) |

> Avoid **NVFP4** on RTX 5090 — it hits a known ComfyUI bug (#14157).

No NVIDIA GPU? open-video still plans and validates prompts, but generation needs a model
backend. A Mac port (`minimax-h3-mlx`) exists in the community but is not wired into the CLI yet.

---

## 2. Clone open-video (skip if you ran `install.sh`)

```bash
git clone https://github.com/agent-next/video-agent.git
cd video-agent
```

The orchestrator is pure Python with **no third-party pip dependencies** (`dependencies = []` in
`pyproject.toml`). Optionally run `pip install -e .` to get the `open-video` command; otherwise use
`python cli/open_video.py` as below. You can sanity-check it right now:

```bash
python cli/open_video.py list-models
# Expected output: a table with the "h3" backend (MiniMax H3), modes t2v/i2v/flf2v, max 15.0s
```

If `list-models` prints the table, the orchestrator is healthy. The remaining steps set up the
**engine** (ComfyUI) and the **model weights** (H3) that actually render the frames.

---

## 3. Set up ComfyUI (the engine) — manual alternative

open-video is the **director**; ComfyUI is the **hands**. open-video talks to ComfyUI's HTTP API,
so install ComfyUI separately following its [official install guide](https://github.com/comfyanonymous/ComfyUI).

In short:

```bash
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI
pip install -r requirements.txt
```

ComfyUI brings in `torch`, `safetensors`, the scheduler, etc. — everything needed to actually run
the model. Keep note of the path to your `ComfyUI/` checkout; you will drop the H3 weights into
its `models/` folders next.

---

## 4. Download the H3 model weights — manual alternative

`open-video pull h3` does this for you. To do it by hand, the default H3 settings in open-video use Comfy-Org's **INT8 ConvRot** quants (proven on the
RTX 5090). Download these four files from the [MiniMax H3 model card](https://huggingface.co/MiniMaxAI/MiniMax-H3)
and the linked Comfy-Org quant repos, and place them under `ComfyUI/models/`:

| File | Destination |
|---|---|
| `minimax_h3_fl2va_pruned_int8_convrot.safetensors` (diffusion model) | `ComfyUI/models/diffusion_models/` |
| `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` (text encoder) | `ComfyUI/models/text_encoders/` |
| `minimax_h3_video_vae_fp16.safetensors` (video VAE) | `ComfyUI/models/vae/` |
| `minimax_h3_audio_vae_fp32.safetensors` (audio VAE) | `ComfyUI/models/vae/` |

> Low on VRAM? NF4 (`DiffSynth-Studio/MiniMax-H3-NF4`) is a manual, experimental alternative to the
> two INT8 files; pass `--lowvram` when you start ComfyUI. The fastest path (4-step Turbo LoRA + Dual-Clock
> sampler, ~5× faster) is documented in [`docs/h3_ecosystem.md`](./h3_ecosystem.md).

---

## 5. Start ComfyUI

From your ComfyUI checkout:

```bash
python main.py --listen --lowvram --use-sage-attention
```

ComfyUI prints a server URL, by default **`http://127.0.0.1:8188`**. Leave it running in its own
terminal — open-video will connect to it.

Verify open-video can reach it:

```bash
# from the open-video repo root
open-video status            # or: python cli/open_video.py status
```

`status` prints the ComfyUI health line (`up` / `down`) and the weight inventory.

`--dry-run` (`python cli/open_video.py "anything" --dry-run`) validates the prompt and builds the
plan, then exits **without generating**. It does **not** contact ComfyUI, so it cannot tell you
whether the engine is reachable.

A real run (without `--dry-run`) fails with `ComfyUI not reachable at http://127.0.0.1:8188` if
ComfyUI isn't running or the URL differs — point open-video at it with `--server` or the
`OPEN_VIDEO_COMFYUI` env var.

---

## 6. Generate your first video

All commands run from the **open-video repo root**. The default model is `h3` and the default
ComfyUI server is `http://127.0.0.1:8188` (override with `OPEN_VIDEO_MODEL` and
`OPEN_VIDEO_COMFYUI`).

### a) Single-shot, text-to-video (simplest)

```bash
python cli/open_video.py "a neon koi swimming through rain, slow dolly" \
  --duration 8 --output output/koi.mp4
```

H3's per-shot ceiling is **15 s**. At `--duration 15` or below, open-video generates a single
shot using your prompt verbatim.

### b) Image-to-video (animate a still)

```bash
python cli/open_video.py "the diver turns to face the light" \
  --mode i2v --first-frame start.png --duration 6 --output output/diver.mp4
```

`--mode i2v` requires `--first-frame`. Supplying `--first-frame` to a plain `t2v` prompt
auto-upgrades shot 1 to i2v.

### c) First-and-last-frame interpolation

```bash
python cli/open_video.py "the cyclist opens her umbrella in the rain" \
  --mode flf2v --first-frame frame_a.png --last-frame frame_b.png --duration 8
```

`--mode flf2v` requires **both** `--first-frame` and `--last-frame`.

### d) Multi-shot film (longer than 15 s)

```bash
python cli/open_video.py "a 90-second chase across a stormy harbour at dusk" \
  --duration 90 --output output/chase.mp4
```

Durations above 15 s trigger a **multi-shot plan**: open-video splits the film into ≤15 s shots
and chains them so each shot's first frame is the previous shot's last frame (FL2VA continuity).

> **Honest v0 caveat:** multi-shot plans currently use template prompts and need an LLM planner
> (`Planner(llm_fn=...)`) to author per-shot prompts. The CLI will print a note telling you this.
> For authored single takes, stay at `--duration <= 15`.

---

## 7. Useful CLI subcommands

```bash
python cli/open_video.py list-models          # show discovered backends under backends/
python cli/open_video.py list-presets         # browse the prompt recipes in library/prompts/
python cli/open_video.py "..." --dry-run      # plan + validate, no GPU spent, no ComfyUI contact
python cli/open_video.py status               # ComfyUI health + weight inventory
python cli/open_video.py pull h3              # download / verify H3 weights
python cli/open_video.py "..." --seed 42      # reproducible; applied as seed+i across shots
```

The full flag list:

```bash
python cli/open_video.py --help
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ComfyUI not reachable at …` | Start ComfyUI first; or pass `--server <url>` / set `OPEN_VIDEO_COMFYUI`. |
| `unknown model 'h3'` | Run from the repo root so `backends/h3/` is importable. `list-models` must show `h3`. |
| OOM during generation | Try a smaller manual H3 quant (W4/NF4, experimental), start ComfyUI with `--lowvram`, reduce `--duration`. |
| Audio popping / artifact | Try the Dual-Clock Euler sampler (see [`h3_ecosystem.md`](./h3_ecosystem.md)). |
| Wide shots corrupt faces | Known H3 issue (Comfy-Org #30). Tighten framing in the prompt or use i2v with a clean reference. |

---

## Next steps

- **Browse the architecture** (plain-language): [`architecture-overview.md`](./architecture-overview.md)
- **Compare open models** (H3 / Wan 2.2 / HunyuanVideo / LTX): [`model-comparison.md`](./model-comparison.md)
- **Contribute a prompt, preset, or backend**: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- **H3 community ecosystem** (quants, samplers, speedups, UIs): [`h3_ecosystem.md`](./h3_ecosystem.md)
