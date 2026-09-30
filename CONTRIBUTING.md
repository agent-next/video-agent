# Contributing to open-video

**We build together.** open-video is a plugin platform — you contribute what you're good at,
we provide the framework. Here's how.

## Easiest contributions (anyone, 1–5 min)

### 📝 Prompt recipe → `library/prompts/`
Copy `templates/prompt_recipe.md` → fill in → PR. That's it. A good prompt that works well on H3
is a real contribution. (See `library/prompts/*.txt` for examples.)

### 📊 Benchmark profile → `bench/`
Ran open-video on your GPU? Share your settings + timings → `templates/bench_profile.md`.

### 🎬 Reference pack → `library/reference_packs/`
A turnaround sheet or lighting board that helps consistency? Share it.

## Code contributions (developers)

### 🔌 Model backend → `backends/<your_model>/`
1. Copy `templates/model_backend.py` → `backends/<model>/backend.py`
2. Implement `ModelBackend` (capabilities, prompt_guide, constraints, generate, settings)
3. Add your workflows to `backends/<model>/workflows/`
4. PR — done. The core never changes; your model just plugs in.
**Wanted now:** Wan2.2, HunyuanVideo-1.5, LTX-2.3 backends.

### 🧪 Judge plugin → `judges/`
Implement `QualityJudge` with your vision model / scoring method. Copy `templates/judge_plugin.py`.
**Wanted:** VideoScore integration, human-in-the-loop judge.

### ⚙️ Engine adapter → `engines/<engine>/`
Implement `EngineAdapter` for your generation backend (diffusers, SGLang, standalone). Copy
`templates/engine_adapter.py`.

### 🎨 Pipeline step → `core/steps/`
Custom planner / stitcher / upscaler / audio processor. Copy `templates/pipeline_step.py`.

## Build on existing work (preferred — don't reinvent)
Before writing from scratch, check if an existing project already does it:
- **Multi-shot orchestration** → refer to `ComfyUI-H3-Multishot` (jlucasmcrell) — wrap as a plugin.
- **Director/storyboard UI** → refer to `ComfyUI-MiniMaxH3-Director` (seesee75-commits).
- **Prompt design + validator** → port from `woodfantasy/Seedance-ShotDesign-Skills` (MIT-0).
- **Video scoring** → integrate `TIGER-AI-Lab/VideoScore`.
- **Speed** → `Turbo LoRA + Dual-Clock Sampler` as a fast-path preset.
- **H3 quants** → use existing Comfy-Org / DmitryDB / DiffSynth quants (don't re-quantize).

**Rule: if it exists and works, integrate it as a plugin — don't rewrite.**

## Quick start for contributors
```bash
git clone https://github.com/agent-next/video-agent.git
cd video-agent
python -m pip install -e ".[dev]"
python -m pytest tests/ -q

# Easiest contribution — a prompt recipe
cp templates/prompt_recipe.md library/prompts/my_recipe.md
# …fill it in…
# open a PR from a fork/branch
```

### Local CLI smoke (no GPU required)
```bash
python cli/open_video.py list-models
python cli/open_video.py recommend-quant --vram 8192
python cli/open_video.py "sunset waves" --dry-run
```

### Agent skill
- Short clip / H3 harness: `skill/h3-video/SKILL.md`
- Long film director: `skill/open-video/SKILL.md`

## PR expectations
- One logical change per PR
- Tests green (`pytest tests/`)
- No secrets (`.env`, tokens, keys); no GTM/strategy essays in product PRs
- Conventional Commits preferred: `feat:`, `fix:`, `docs:`, `test:`, `ci:`

## Governance
- **Early stage:** BDFL (founder sets vision, fast decisions). See `GOVERNANCE.md`.
- **Growing:** community council + RFC for architecture.
- **License:** **Apache-2.0** (see `LICENSE`).

## Code of conduct
See `CODE_OF_CONDUCT.md`. Be kind. Be constructive. Welcome newcomers.
