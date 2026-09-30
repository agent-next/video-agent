<p align="center">
  <img src="https://open-video.ai/logo.svg" width="110" height="110" alt="OpenVideo" />
</p>

<h1 align="center">OpenVideo</h1>

<p align="center">
  <strong>Ollama for video models.</strong><br/>
  <sub>Run MiniMax H3 on your own GPU — <code>install · pull · run</code> — plus a drop-in skill
  so any coding agent can generate high-quality video.</sub>
</p>

<p align="center">
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/badge/license-Apache--2.0-blue.svg"/></a>
  <img alt="Version" src="https://img.shields.io/badge/version-0.1.0-informational.svg"/>
  <a href="https://open-video.ai"><img alt="Website" src="https://img.shields.io/website?url=https%3A%2F%2Fopen-video.ai&label=open-video.ai"/></a>
  <a href="https://huggingface.co/open-video-ai"><img alt="Hugging Face" src="https://img.shields.io/badge/HuggingFace-open--video--ai-yellow.svg"/></a>
</p>

<p align="center">
  <sub><b>Ollama → local LLMs.&nbsp;&nbsp;OpenVideo → local video.</b></sub><br/>
  <sub>v0.1.0 is exactly that loop for MiniMax H3 — not a multi-model platform yet. <a href="https://open-video.ai/demo.mp4">▶ Watch the demo</a></sub>
</p>

---

## 60-second start

```bash
# v0.1.0 ships from the GitHub tag (Linux / macOS / WSL2)
git clone --depth 1 --branch v0.1.0 https://github.com/agent-next/video-agent
cd open-video
bash scripts/install.sh             # ComfyUI engine + H3 weights (resumable, ~54 GB)

# Same mental model as Ollama: pull → status → run
open-video pull h3                  # verify / resume H3 weights
open-video status                   # engine health + weight inventory (alias: ps)
open-video run "A lone astronaut planting a flag on a red dune at dusk" --duration 8

open-video "sunset waves" --dry-run # plan + validate, no GPU spent
```

Use the versioned clone above to install this release. The website installer
is updated separately and may serve an older version.

| OS | Install | Generate |
|---|---|---|
| **Linux** | tag clone + `scripts/install.sh` | NVIDIA GPU · full H3 |
| **macOS** | same clone (setup + dry-run) | H3 generation via community/MLX paths; not default |
| **Windows** | same clone inside **WSL2** | WSL2 for H3 GPU; native execution is unverified |

**Hardware.** Local-first; bring your own NVIDIA GPU. `open-video recommend-quant` picks the
right weight tier for your card:

| VRAM | Quant tier |
|---|---|
| ≥ 22 GiB | INT8 ConvRot (default, checksum verified — the only tier `pull` installs) |
| 12–22 GiB | INT8 + automatic ComfyUI low-VRAM offload |
| 9–12 GB | W4 ConvRot (~10 GB) — manual, experimental |
| < 9 GB | NF4 (~8 GB entry) — manual, experimental |

`recommend-quant` may *suggest* W4/NF4 for small cards, but the installer never
fetches them — those tiers are manual experiments, not a shipped path.

<details>
<summary><b>Prefer manual clone / pip?</b></summary>

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/agent-next/video-agent && cd open-video
pip install -e .
open-video pull h3
open-video run "waves at sunset, golden hour" --duration 10 --model h3 --output out.mp4
# ComfyUI at http://127.0.0.1:8188 (env OPEN_VIDEO_COMFYUI)
```

Python API: `from open_video import H3Backend, ComfyUIAdapter` — see
[`ARCHITECTURE.md`](ARCHITECTURE.md).

</details>

## The agent path (what makes this different)

Point any agent host at the skill — it installs/pulls if needed, crafts the **official H3
3-field prompt**, validates against hard constraints, generates, and reviews:

| Skill | Use when |
|---|---|
| **[`skill/h3-video/SKILL.md`](skill/h3-video/SKILL.md)** | **v0.1.0 default** — high-quality single/short H3 clips (T2V / I2V / FL2VA) |
| [`skill/open-video/SKILL.md`](skill/open-video/SKILL.md) | Longer director path (plan → judge → stitch) — **experimental** |

Works with Claude Code, Cursor, Codex, OpenCode, and any host that loads `SKILL.md`.
Quality is encoded, not left to chance: prompt grammar ([`backends/h3/PROMPT_GRAMMAR.md`](backends/h3/PROMPT_GRAMMAR.md)),
a hard validator, and curated presets (`open-video list-presets`).

## Three ways to use it

| Interface | For | Experience |
|---|---|---|
| 🤖 **Skill harness** | Any agent | Load `skill/h3-video` → agent generates H3 video end-to-end |
| ⌨️ **CLI** | Developers / scripts | `open-video pull · status · run` (Ollama-shaped) |
| 🖥️ **Site** | Discovery | [open-video.ai](https://open-video.ai) — install + docs |

## What works today vs what is designed next

| | v0.1.0 (shipped) | Designed (not wired yet) |
|---|---|---|
| **Generate** | Local MiniMax H3 via ComfyUI — `pull` / `status` / `run` | Multi-model backends (Wan, LTX, …) |
| **Agent path** | `skill/h3-video` crafts official prompts + drives the CLI | Full multi-shot director agent |
| **Judge loop** | Opt-in real VLM judge via env `OPEN_VIDEO_VLM_URL/MODEL/KEY` + bounded REFINE retries (`OPEN_VIDEO_JUDGE_RETRIES`, best take kept); honest `SKIPPED` (score 0) when unset | Best-of-N tournament judging |
| **Long film** | Single clips (H3 shot length) | Planner → stitch multi-minute film |
| **Hosted try** | Site `/try` is a **browser mockup** | Real hosted generate |

The generate → judge → **refine** loop runs today: point `OPEN_VIDEO_VLM_URL` at any
OpenAI-compatible vision model and low-scoring shots regenerate automatically with a bumped
seed (`OPEN_VIDEO_JUDGE_RETRIES` extra takes, best score kept — full take history plus the
winning take's seed in the `--json` receipt). With no VLM configured the verdict is
honestly `SKIPPED` — never a fake PASS.

## Why local

Closed tools charge per second and keep your prompts and footage in their pipeline. Open video
models are now good enough to matter — what was missing is the simple local loop: install →
pull → run, with best-practice prompting built in. v0.1.0 is that loop.

| | OpenVideo (local) | Typical closed SaaS |
|---|---|---|
| **Model** | MiniMax H3, open weights on your GPU | Vendor-hosted only |
| **Cost** | Your GPU + electricity | Per-second API / subscription |
| **Data** | Stays on your machine | Vendor pipeline |
| **Software license** | Apache-2.0 | Proprietary ToS |

## Licenses — read this before commercial use

- Detailed weights terms: [docs/WEIGHTS_LICENSE.md](docs/WEIGHTS_LICENSE.md).
- **Code (this repo): [Apache-2.0](LICENSE).** Use it freely.
- **Model weights are NOT covered by this repo's license.** MiniMax H3 weights are distributed
  under the **MiniMax H3 Community License** (see the
  [model card](https://huggingface.co/Comfy-Org/MiniMax-H3) and upstream
  [MiniMaxAI](https://huggingface.co/MiniMaxAI)), which includes **territorial and
  commercial-use restrictions**. The installer downloads weights from the upstream mirrors;
  you are responsible for confirming the license permits your use case and region.
- License-cleaner second backends (e.g. Wan) are on the roadmap.

## How it compares (honest)

| | What | Open software? | Local open model? | Notes |
|---|---|:--:|:--:|---|
| **OpenVideo** | CLI + skill + H3 on ComfyUI | ✅ Apache-2.0 | ✅ H3 | this project — director/judge loop is scaffolding |
| **Runway** | Closed SaaS | ❌ | ❌ | Hosted product |
| **Seedance** | Closed agentic long video | ❌ | ❌ | Hosted product |
| **ComfyUI** | Node-graph engine | ✅ GPL | via custom nodes | **The runtime we drive** — a dependency, not a competitor |

> OpenVideo is not a foundation model and not a replacement for ComfyUI. v0.1.0 is the
> **install → pull → run** layer plus an agent skill on top of H3.

## Contributing

**OpenVideo is a plugin surface — contribute what you're good at:**

| You have | Contribute → | Effort |
|---|---|---|
| A great prompt | `library/prompts/` — a verified recipe | 5 min |
| A new model (Wan 2.2, Hunyuan, LTX) | `backends/<model>/` — a backend plugin | an afternoon |
| A scoring method / vision judge | `judges/` — a judge plugin | an afternoon |
| A new engine (diffusers, SGLang) | `engines/<engine>/` — an adapter | an afternoon |
| A style LoRA | `library/` — share it | 10 min |

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for templates and [`GOVERNANCE.md`](GOVERNANCE.md) for
how decisions get made. **We integrate, we don't reinvent** — if a working project already does
it, we wrap it as a plugin. Chat lands later; for now use GitHub Issues.

## Architecture

**Shipped path:**

```
prompt / skill ──→ open-video CLI ──→ backends/h3 ──→ engines/comfyui ──→ mp4
```

**Design target** (modules exist as scaffolds; not all wired end-to-end):

```
concept ──→ planner → crafter → validator → backend → judge → stitcher → film
```

- **`backends/h3/`** — MiniMax H3 plugin: prompt grammar, workflows, constraints.
- **`engines/comfyui/`** — ComfyUI HTTP adapter (submit / wait / fetch).
- **`skill/h3-video/`** — the agent harness.
- **`core/`** — shared contracts + judge/planner scaffolding for later phases.

Full design notes: [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Status & roadmap

**v0.1.0 — shipped:** local H3 pull/run with integrity-verified weights, agent skill
harness, recipe-in-render metadata, opt-in VLM judge with honest `SKIPPED` fallback, and
unique I2V/FL2V input staging (`OPEN_VIDEO_COMFYUI_INPUT`).

- **Next:** a multi-shot demo with an independent visual review and receipts,
  multi-shot continuity, a license-clean second backend.
- **Later, only when real:** hosted generate, desktop packaging, community gallery.

## Acknowledgments

Standing on the shoulders of open giants: **[ComfyUI](https://github.com/comfyanonymous/ComfyUI)**
(the engine), **[MiniMax H3](https://huggingface.co/MiniMaxAI)** (the model),
the **[woodfantasy](https://github.com/woodfantasy)** prompt methodology (MIT-0), and
**[VideoScore](https://github.com/TIGER-AI-Lab/VideoScore)** (judge direction). We integrate,
not reinvent.

## Security

Private vulnerability reporting: [SECURITY.md](SECURITY.md).

## License

[Apache-2.0](LICENSE) © OpenVideo contributors · [open-video.ai](https://open-video.ai)

<p align="center"><sub>OpenVideo · open-video.ai · Apache-2.0</sub></p>
