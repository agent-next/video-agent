# Agents — OpenVideo product repo

You are inside the **product** git repo: [`agent-next/video-agent`](https://github.com/agent-next/video-agent).

## Read first

| Doc | Why |
|---|---|
| [`README.md`](README.md) | What v0.1.0 ships vs design-only |
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | Install / pull / run |
| [`skill/h3-video/SKILL.md`](skill/h3-video/SKILL.md) | Agent generate path |
| [`docs/LAB.md`](docs/LAB.md) | ComfyUI + weights outside git |

## Rules (public-safe)

1. **Brand:** OpenVideo. Do not rename the product to “H3 app” or “ComfyUI wrapper.”
2. **Honesty:** Do not claim free cloud GPU, desktop installers, marketplace, or a verified multi-shot demo as shipped in v0.1.0. The VLM judge is opt-in (`OPEN_VIDEO_VLM_*`); without it verdicts are `SKIPPED`, not PASS.
3. **Secrets:** Never commit `.env`, tokens, private keys, or host credential paths.
4. **Weights:** Never commit `*.safetensors` / ComfyUI / `lab/`.
5. **Strategy:** No GTM, star-count north stars, or competitive war docs in this repo.
6. **Visibility:** Do **not** flip the repo public unless the owner explicitly says go.

## Env (before GPU work)

```bash
export OPEN_VIDEO_ROOT="$(pwd)"
export OPEN_VIDEO_LAB="${OPEN_VIDEO_LAB:-$OPEN_VIDEO_ROOT/../lab}"
export OPEN_VIDEO_MODELS="${OPEN_VIDEO_MODELS:-$OPEN_VIDEO_LAB/h3_models}"
export OPEN_VIDEO_COMFYUI="${OPEN_VIDEO_COMFYUI:-http://127.0.0.1:8188}"
```
