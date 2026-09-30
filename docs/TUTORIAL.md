# OpenVideo — Beginner's Tutorial (v0.0.1)

> **From zero to your first local H3 clip on an NVIDIA GPU.**
>
> OpenVideo v0.0.1 is **local MiniMax H3** (install · pull · status · run) plus an **agent skill
> harness** for high-quality prompts. Longer “director” features (live vision judge, multi-minute
> film) are designed and partially scaffolded — not finished product claims.

---

## Table of contents

1. [What is OpenVideo today?](#1-what-is-openvideo-today)
2. [Install (primary paths)](#2-install-primary-paths)
3. [Make your first video](#3-make-your-first-video)
4. [Use presets (recipe files)](#4-use-presets-recipe-files)
5. [Multi-shot / long film (honest status)](#5-multi-shot--long-film-honest-status)
6. [Community LoRAs (planned UX)](#6-community-loras-planned-ux)
7. [The quality loop (design target)](#7-the-quality-loop-design-target)
8. [Share your work](#8-share-your-work)
9. [Troubleshooting & glossary](#9-troubleshooting--glossary)

---

## 1. What is OpenVideo today?

**OpenVideo** is open-source video generation. In **v0.0.1** that means:

1. **Local MiniMax H3** on your machine via ComfyUI — `install` · `pull` · `status` · `run`
2. **Agent skill harness** (`skill/h3-video`) so coding agents can craft official 3-field H3
   prompts and generate high-quality short clips on **your** GPU

It is **not** (yet): a free cloud render service, a polished desktop app store install, a live
vision quality loop that always re-renders bad takes, or a finished multi-minute film director.

> **In one line:** *Open video models on your GPU — with an agent-friendly harness.*

<details>
<summary><b>What does "open-source" mean for me?</b></summary>

Apache 2.0: free to use, modify, and share. You run generation on hardware you control. There is
**no** hosted free GPU product today. Optional cloud convenience may come later; the core stays
open and local-first.
</details>

> **Screenshots:** TBD — UI and gallery still land; this tutorial uses commands you can run now.

---

## 2. Install (primary paths)

Pick **one**. Real generation uses an **NVIDIA GPU** with the INT8 weights;
the installer enables ComfyUI offloading below 22 GiB VRAM. Other quantization
tiers are manual experiments.

| Path | Best for | Needs |
|---|---|---|
| **A. Versioned install** | Installing v0.1.0 | Linux/WSL2 + NVIDIA GPU + disk (~60 GB) |
| **B. Clone + scripts** | Developers already in the repo | Same GPU + Python 3.10+ |
| **C. Browser `/try`** | Seeing the *idea* of the product | Browser only — **mockup, not cloud generate** |

Full detail: [`getting-started.md`](./getting-started.md) · [`QUICKSTART.md`](./QUICKSTART.md).

### Option A — Versioned install (recommended)

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/agent-next/video-agent
cd video-agent
bash scripts/install.sh
```

On Windows, run these commands inside WSL2. The website installer is updated
separately and may serve an older version.

The installer sets up ComfyUI, downloads H3 weights (resumable), and prints next commands. Prefer
flags from the script’s `--help` / `--self-test` when debugging.

There are **no** shipping primary installers named `OpenVideo-Setup.exe`, `OpenVideo.dmg`, or
`OpenVideo.AppImage` today. Use curl/clone, not a fake desktop package.

### Option B — Clone + CLI

```bash
git clone https://github.com/agent-next/video-agent.git
cd video-agent
# optional: bash scripts/install.sh
python -m open_video list-models
python -m open_video pull h3 --check-only
python -m open_video status
```

You still need a running ComfyUI with H3 weights (installer or manual layout under your lab /
ComfyUI `models/` paths). See `getting-started.md`.

### Option C — Website `/try` (mockup only)

[open-video.ai/try](https://open-video.ai/try) is a **static browser mockup** of the director
flow. It does **not** render free cloud video on OpenVideo GPUs. For real clips, use A or B on a
local NVIDIA GPU.

---

## 3. Make your first video

### Step 1 — Health checks

```bash
open-video status
# or: python -m open_video status
# dry-run validates without a full render:
open-video "a neon-lit koi fish swimming slowly through rain" --dry-run
```

Confirm ComfyUI is up (default `http://127.0.0.1:8188`) and weights are present.

### Step 2 — Write a visual prompt

Be specific: subject + setting + lighting + camera.

> *a neon-lit koi fish swimming slowly through falling rain, soft reflections on wet asphalt,
> gentle camera dolly forward, cinematic, moody*

For best H3 quality, agents should use the official **3-field** grammar
(`backends/h3/PROMPT_GRAMMAR.md` / `skill/h3-video`).

### Step 3 — Generate

```bash
open-video run "a neon-lit koi fish swimming slowly through falling rain, soft reflections on wet asphalt, gentle camera dolly forward, cinematic, moody" \
  --duration 8
# battle-tested agent path:
# python scripts/h3_agent.py --prompt "$(cat my_prompt.txt)" --duration 8
```

Single shots are typically **4–15 seconds** (model ceiling). Longer targets need multi-shot
orchestration (section 5) — still partial in v0.0.1.

### Step 4 — Find the mp4

Outputs land under the paths the CLI / ComfyUI print (often `output/`). Re-run with a new seed or
tighter prompt if the take is off.

---

## 4. Use presets (recipe files)

**Presets** in the repo are YAML **coherence recipes** under
[`library/coherence_recipes/`](../library/coherence_recipes/) — templates for film *types*
(cinematic short, product ad, social clip, …). They are starting points for planners and humans,
not a finished “pick a preset in a GUI and get a commercial” product.

```bash
# when wired in your checkout:
python -m open_video list-presets
# or open the YAML files directly
ls library/coherence_recipes/
```

Copy a recipe, edit shot structure / duration, and feed prompts into `run` / `h3_agent.py`. A
polished preset picker UI is future work.

---

## 5. Multi-shot / long film (honest status)

Models cap a **single shot** around **15s**. Longer pieces need: plan shots → generate each →
chain last-frame → first-frame (FL2VA) → stitch with ffmpeg.

**v0.0.1 status:**

| Piece | Status |
|---|---|
| Single-shot H3 generate | **Shipped** |
| Multi-shot scripts / pipeline scaffold | **Partial** (`scripts/h3_multishot.py`, `core/pipeline.py`) |
| Full autonomous multi-minute director | **Not shipped** — design target |

Preview planning without GPU when supported:

```bash
open-video "a 90-second chase across a stormy harbour at dusk" --duration 90 --dry-run
```

Do not treat dry-run or scaffold code as proof of a finished long-film product.

---

## 6. Community LoRAs (planned UX)

A **LoRA** is a small style/identity adapter (`.safetensors`) that can sit on H3.

**Today:** drop standard H3 LoRAs into ComfyUI’s `models/loras/` and use them in workflows.

**Planned:** gallery, `open-video lora pull`, and one-click `--lora name@strength` UX — documented
as a target in [`library-and-loras.md`](./library-and-loras.md). Do not expect a full community
marketplace in v0.0.1.

Contribution shape when you train one: recipe markdown + off-repo weights + consent rules
(`templates/lora_recipe.md`).

---

## 7. The quality loop (design target)

**Idea:** generate → extract frames → vision-judge vs prompt → refine / best-of-N → keep the take.

This is **core product IP we are building toward**, inspired by research patterns (e.g. VISTA-style
judge + refine). In v0.0.1:

- `core/judge.py` exists as a **scaffold**
- Without a wired `vision_fn`, assessment may **PASS by default** (hook ready; not a live critic)
- Agents should still **validate prompts** and re-run manually when quality is poor

Do **not** market OpenVideo as “the first open project that already ships a live quality loop.”
It is a design target with early scaffolding.

---

## 8. Share your work

Easiest contributions (no coding required for some):

1. **Prompt recipes** — good 3-field H3 prompts under `library/prompts/`
2. **Coherence recipes** — YAML film templates under `library/coherence_recipes/`
3. **Issues / PRs** on GitHub when the tree is available to you

There is **no** public Discord as a required community path. Prefer:

- Site: [https://open-video.ai](https://open-video.ai)
- GitHub Issues on `agent-next/video-agent`

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) and [`docs/COMMUNITY.md`](./COMMUNITY.md).

---

## 9. Troubleshooting & glossary

| Problem | What to do |
|---|---|
| **Clip ignores the prompt** | Use the official 3-field grammar; name subject + camera + visible detail. |
| **Glitchy / broken frames** | New seed; shorter duration; lower resolution; re-validate prompt. |
| **OOM / CUDA errors** | Smaller quant (NF4/W4), `--lowvram`, shorter clip. |
| **No NVIDIA GPU** | You can use the `/try` mockup only; real gen is local GPU-first. |
| **`/try` didn’t “generate”** | Expected — browser mockup, not free cloud GPU. |
| **Slow** | Warm runs still minutes per short clip on consumer cards; see `docs/h3/BENCHMARK.md`. |

### Glossary

- **Prompt** — text describing the video (prefer H3 3-field for quality).
- **Shot / clip** — one continuous render, typically ≤15s on H3.
- **Film (multi-shot)** — several shots planned and stitched (partial support).
- **LoRA** — small adapter for style/identity.
- **Judge / quality loop** — design: auto score and refine takes (scaffold today).
- **ComfyUI** — open render engine OpenVideo drives over HTTP.
- **H3 (MiniMax H3)** — default open video model; strong open Arena placement.

### Where to go next

- Quickstart: [`QUICKSTART.md`](./QUICKSTART.md)
- Local setup: [`getting-started.md`](./getting-started.md)
- H3 quality: [`docs/h3/`](./h3/) · skill `h3-video`
- Architecture intent: [`architecture-overview.md`](./architecture-overview.md)
- Contribute: [`CONTRIBUTING.md`](../CONTRIBUTING.md)

Welcome to OpenVideo. Generate something local.
