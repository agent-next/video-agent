# Agents — OpenVideo (video-agent)

Repo guide for the **OpenVideo** product repo. House rules live in the
[agent-next agent standard](https://github.com/agent-next/.github/blob/main/AGENT-STANDARD.md);
if this file conflicts with it, the standard wins.

## Purpose

OpenVideo = "Ollama for video models": run MiniMax H3 on your own GPU with an
install → pull → run loop, plus a drop-in skill so any coding agent can generate
video. v0.1.0 ships local H3 pull/run with integrity-verified weights, the
`skill/h3-video` agent harness, recipe-in-render metadata, and an opt-in VLM
judge — honest `SKIPPED` (never a fake PASS) when `OPEN_VIDEO_VLM_*` is unset.

## Orient

- `open_video/` is the import root; sibling dirs are packaged as `open_video.*`
  subpackages via `[tool.setuptools.package-dir]` in `pyproject.toml`.
- `cli/` CLI entry (`python cli/open_video.py`) · `core/` shared contracts,
  judge/planner scaffolding · `backends/h3/` H3 plugin (prompt grammar,
  workflows) · `engines/comfyui/` ComfyUI HTTP adapter · `judges/` judge
  plugins · `library/` prompt presets · `models/` weight manifest · `scripts/`
  install / download / bench tooling.
- `skill/h3-video/SKILL.md` — the v0.1.0 agent generate path.
- `tests/` pytest suite (unit + e2e against a fake local ComfyUI server).
- Docs: `README.md` (what v0.1.0 ships vs design-only), `ARCHITECTURE.md`,
  `docs/QUICKSTART.md` (install / pull / run), `docs/LAB.md` (ComfyUI + weights
  outside git).

## Setup

```bash
make setup    # = python3 -m pip install -e ".[dev]"  (pytest, ruff)
```

Runtime Python deps: none — the core path is stdlib-only (pyproject
`dependencies = []`). System deps: `ffmpeg`/`ffprobe` on PATH; the e2e test
hard-requires them (CI apt-installs ffmpeg).

GPU work additionally needs ComfyUI + H3 weights outside the repo
(`bash scripts/install.sh`, ~54 GB download) and:

```bash
export OPEN_VIDEO_ROOT="$(pwd)"
export OPEN_VIDEO_LAB="${OPEN_VIDEO_LAB:-$OPEN_VIDEO_ROOT/../lab}"
export OPEN_VIDEO_MODELS="${OPEN_VIDEO_MODELS:-$OPEN_VIDEO_LAB/h3_models}"
export OPEN_VIDEO_COMFYUI="${OPEN_VIDEO_COMFYUI:-http://127.0.0.1:8188}"
```

## Check

```bash
make check    # = python3 -m pytest tests/ -q --tb=short  (the CI test gate)
```

No GPU, secrets, or internet needed — the e2e test drives a fake ComfyUI on
localhost; `ffmpeg`/`ffprobe` must be on PATH. CI
(`.github/workflows/ci.yml`) additionally runs import + CLI smoke
(`python cli/open_video.py list-models`, `… "sunset waves" --dry-run`) on
Python 3.10–3.12 and a wheel-build smoke job.

## Boundaries

1. **Brand:** OpenVideo. Do not rename the product to "H3 app" or "ComfyUI wrapper."
2. **Honesty:** Do not claim free cloud GPU, desktop installers, marketplace, or
   a verified multi-shot demo as shipped in v0.1.0. The VLM judge is opt-in
   (`OPEN_VIDEO_VLM_*`); without it verdicts are `SKIPPED`, not PASS.
3. **Secrets:** Never commit `.env`, tokens, private keys, or host credential paths.
4. **Weights:** Never commit `*.safetensors` / ComfyUI / `lab/`.
5. **Strategy:** No GTM, star-count north stars, or competitive war docs in this repo.
6. **Visibility:** Do **not** flip the repo public unless the owner explicitly says go.
7. The standard's hard limits apply (never force-push master; owner-gated
   actions need written owner confirmation).

## Done

A change is done when `make check` is green on your branch; new production code
ships with at least one test with a real oracle; the PR body carries receipts
(pasted real command output, not claims); no secrets or weights are committed;
commit messages are conventional (`feat:`, `fix:`, `chore:`, …) with no
tool-attribution trailers.
