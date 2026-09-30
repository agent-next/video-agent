# OpenVideo v0.1.0 — Release Notes

Reliability improvements for local MiniMax H3 generation: verified weight
downloads, isolated reference inputs, accurate generation receipts, and explicit
failure and judge status.

## Get it

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/agent-next/video-agent
cd video-agent && bash scripts/install.sh
```

Use the versioned clone above to install this release. The website installer
is updated separately and may serve an older version.

## What changed

- **Recipe-in-render round-trip** — `embed_recipe`/`read_recipe` round-trip
  with atomic replacement for in-place updates; stale OpenVideo metadata tags
  are cleared on re-embed.
- **Integrity-verified weights** — `open-video pull h3` verifies a packaged
  manifest (sizes + SHA-256), including existing files with matching sizes.
  Downloads only write to the selected model store and work from wheel
  installations. `--check-only` is a size inventory without checksum verification.
- **Engine adapter hardening** — correct URL encoding; ComfyUI errors propagate
  as errors instead of silent timeouts.
- **I2V / FLF2V unique staging** — first/last frames are staged under unique
  names via `OPEN_VIDEO_COMFYUI_INPUT`, which must point at a directory that
  belongs to the target ComfyUI server.
- **Honest judge** — with no VLM configured (`OPEN_VIDEO_VLM_URL` +
  `OPEN_VIDEO_VLM_MODEL`, or an explicit `vision_fn`), shot verdicts are
  `SKIPPED` (score 0) instead of a silent PASS. Real VLM callbacks remain
  strictly opt-in.
- **Judge retries and receipts** — `OPEN_VIDEO_JUDGE_RETRIES` sets the number
  of extra takes (default 1). The best take's seed and full take history are
  recorded in the JSON receipt. A failed requested shot stops the run without
  reporting a partial film as complete.
- **Portrait generation** — `--aspect 9:16` reaches the backend's generation
  settings; JSON output includes the actual dimensions and take receipts.

## Scope and limitations

- No `open-video inspect` / `remix` / `--lora` CLI flags exist. Recipe read-back:
  `python -c "from open_video.core.recipe import read_recipe; print(read_recipe('out.mp4'))"`.
- Default weights are **INT8 only**. W4 / NF4 are manual, experimental tiers —
  `recommend-quant` may suggest them but nothing auto-installs them.
- The long-film director (`skill/open-video`) stays **experimental**; generation
  requires an NVIDIA GPU runtime.
- Native Windows execution and independent visual-quality acceptance remain
  unverified. The GPU check below covers a small functional sequence.
- With the pinned ComfyUI and legacy low-VRAM offloading, audio VAE decoding
  can fail with a CPU/CUDA device mismatch. `--cpu-vae` worked for the small
  check but moves both VAEs to CPU and can substantially slow decoding. A
  full-size retry was cancelled during CPU video decoding; full-size acceptance
  remains unverified. See [the runtime notes](LAB.md#audio-vae-with-constrained-gpu-memory).

## Verification status

| Check | Status |
|---|---|
| Unit/integration tests (`pytest`) | **163 passed**, including from an extracted source distribution |
| Installed wheel in a clean Python 3.12 environment | **10 checks passed**: packaged data, entry point, model listing, dry-run, portrait CLI wiring, take receipts and recipe read-back |
| Real GPU functional sequence | **Passed at 256×256**: T2V followed by I2V using the first shot's last frame; 214 video frames at 24 fps (8.9167 s), with audio and embedded recipe |
| Independent visual-quality / VLM acceptance | **Unverified**; both shots report `SKIPPED` |
| Full-size GPU / native Windows execution | **Unverified** |

The wheel CLI check used a loopback ComfyUI fixture and real ffmpeg; it checks
integration, not model generation. The separate real GPU check used an RTX 5090,
the four checksum-verified INT8 files, ComfyUI
`14b05228cef127ce529bc0c08660770d4af3e9a8`, 20 steps per shot, seeds 220901 and
220902, and `--lowvram --disable-dynamic-vram --cpu-vae`. It completed in about
446 seconds on a shared host. This is a functional result, not a speed or
visual-quality benchmark.

## Upgrade notes

- From source: `git fetch --tags && git checkout v0.1.0`, then `pip install -e .`.
- I2V/FL2V users: set `OPEN_VIDEO_COMFYUI_INPUT` to the ComfyUI server's own
  `input/` directory before running.
- If you relied on the judge auto-PASSing with no VLM: verdicts now read
  `SKIPPED`. Set `OPEN_VIDEO_VLM_*` to get real scoring.
