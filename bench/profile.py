#!/usr/bin/env python3
"""open-video benchmark / profiling harness.

Profiles ANY ModelBackend (H3, Wan3, FLUX3-Dev, ...) at multiple resolutions x
durations and captures:
  - per-step time        (parsed from the ComfyUI server log tqdm progress)
  - total generation time(wall clock around backend.generate())
  - peak VRAM            (nvidia-smi sampler thread)
  - peak RAM             (/proc/meminfo sampler thread)
  - output file size     (from the returned ShotResult.video_path)

Writes incremental + resumable JSON to bench/results/<model>-<gpu>-<date>.json
(after every config, so a kill never loses data) and prints a summary table.

The profiling primitives — nvidia-smi VRAM sampler thread, /proc/meminfo RAM read,
ComfyUI server-log per-step parsing, incremental result writes, resumable skip —
are ported from the early lab/scripts/h3_full_benchmark.py and
lifted behind the model-agnostic ModelBackend interface, so any backend plugin
can be profiled without editing this file.

Usage:
    python bench/profile.py --model h3 --gpu rtx5090
    python bench/profile.py --model h3 --gpu 0 --resolutions 480p,768p --durations 5,10
    python bench/profile.py --model h3 --gpu a100 --server-log logs/comfy_server.log

Requirements:
  * The ComfyUI server must already be running on the target GPU (--server).
  * nvidia-smi must be on PATH (used by the VRAM sampler).
  * Optional: --server-log enables per-step / prompt-executed timing (engine-level).
"""
from __future__ import annotations
import argparse
import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

# --- repo-root bootstrap: core/, backends/, engines/ import as top-level ------
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BENCH_DIR = REPO_ROOT / "bench"
RESULTS_DIR = BENCH_DIR / "results"
DEFAULT_OUTPUT_DIR = BENCH_DIR / "output"

# ComfyUI server-log regexes (engine-level; model-agnostic). tqdm KSampler lines
# look like: ` 45%|████▍     | 9/20 [00:42<00:51,  4.69s/it]`
PROMPT_EXEC_RE = re.compile(r"Prompt executed in ([0-9.]+) seconds")
STEP_RE = re.compile(r"(\d+)/(\d+)\s*\[[0-9:]+<[0-9:]+,\s*([0-9.]+)s/it")

# Short-edge pixel targets for the named resolution presets.
RESOLUTION_PRESETS = {"480p": 480, "540p": 540, "720p": 720, "768p": 768}
ASPECTS = {"21:9": (21, 9), "16:9": (16, 9), "4:3": (4, 3), "1:1": (1, 1),
           "3:4": (3, 4), "9:16": (9, 16)}

DEFAULT_PROMPT = ("A cinematic shot of waves crashing on a rocky shore at sunset, "
                  "slow motion, detailed, natural light.")


# =============================================================================#
# CLI loader reuse (single source of truth for backend discovery)
# =============================================================================#
def _load_cli():
    """Dynamically load cli/open_video.py so bench uses the SAME backend + engine
    loader as the CLI (no duplicated discovery logic)."""
    spec = importlib.util.spec_from_file_location(
        "open_video_cli", REPO_ROOT / "cli" / "open_video.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# =============================================================================#
# Proven profiling primitives (ported from early lab h3_full_benchmark.py)
# =============================================================================#
def ram_used_mb() -> int:
    """Current system RAM used (MB), from /proc/meminfo."""
    with open("/proc/meminfo") as f:
        mi = {ln.split(":")[0]: int(ln.split()[1]) for ln in f}
    return round((mi["MemTotal"] - mi["MemAvailable"]) / 1024)


class ResourceSampler:
    """Background thread sampling peak VRAM (nvidia-smi) and peak RAM (/proc/meminfo).

    Ports the reference VRAM class and adds an analogous RAM peak (the reference
    took a single RAM sample; profiling wants the peak across the whole run).
    """

    def __init__(self, gpu_index: int = 0, interval: float = 1.5):
        self.gpu_index = gpu_index
        self.interval = interval
        self.peak_vram_mb = 0
        self.peak_ram_mb = 0
        self.samples = 0
        self.environment_failures = []
        self._stop = False
        self._thread = None

    def start(self):
        self._stop = False
        self.peak_vram_mb = 0
        self.peak_ram_mb = ram_used_mb()  # baseline so peak >= pre-run usage
        self.samples = 0
        self.environment_failures = []
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _record_failure(self, msg: str):
        """Record a sampler/environment failure once per distinct message, so a
        repeating sample loop cannot spam unbounded duplicate entries."""
        if msg not in self.environment_failures:
            self.environment_failures.append(msg)

    def stop(self):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=max(5.0, self.interval * 2))

    def _run(self):
        cmd = ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"]
        while not self._stop:
            # VRAM (one line per GPU; pick the requested index)
            try:
                out = subprocess.check_output(cmd, text=True, timeout=5).strip().splitlines()
                if len(out) > self.gpu_index:
                    v = int(out[self.gpu_index])
                    if v > self.peak_vram_mb:
                        self.peak_vram_mb = v
            except FileNotFoundError:
                self._record_failure(
                    "nvidia-smi not found on PATH; VRAM sampling unavailable")
            except Exception as e:
                self._record_failure(f"nvidia-smi sampler failed: {e}")
            # RAM
            try:
                r = ram_used_mb()
                if r > self.peak_ram_mb:
                    self.peak_ram_mb = r
            except Exception as e:
                self._record_failure(f"RAM sampler failed: {e}")
            self.samples += 1
            time.sleep(self.interval)


def last_log_match(path: str, pattern: re.Pattern):
    """Last regex match in the ComfyUI server log (reads only the last ~1MB so
    multi-GB logs stay cheap). Returns the re.Match or None."""
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        with open(p, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            chunk = min(size, 1 << 20)
            f.seek(size - chunk)
            tail = f.read().decode("utf-8", errors="ignore")
    except OSError:
        return None
    for line in reversed(tail.splitlines()):
        m = pattern.search(line)
        if m:
            return m
    return None


# =============================================================================#
# Model-agnostic resolution / config helpers
# =============================================================================#
def compute_resolution(short_edge: int, aspect: str, multiple: int) -> tuple:
    """Map short-edge target + aspect -> (w, h) snapped to the model's grid."""
    aw, ah = ASPECTS.get(aspect, (16, 9))
    # snap the short edge to the grid too
    se = max(multiple, int(round(short_edge / multiple)) * multiple)
    if aw >= ah:  # landscape / square: short edge is height
        h = se
        w = int(round(se * aw / ah / multiple)) * multiple
    else:         # portrait: short edge is width
        w = se
        h = int(round(se * ah / aw / multiple)) * multiple
    return w, h


def build_configs(backend, resolutions, durations, aspect, seed_base):
    """Build the (name, w, h, dur, seed) matrix from model capabilities + grid."""
    multiple = backend.constraints().get("resolution_multiple", 32) or 32
    cap_short = getattr(backend.capabilities, "max_short_edge_px", None)
    cfgs = []
    for res in resolutions:
        short = RESOLUTION_PRESETS.get(res)
        if short is None:  # allow raw short-edge ints like "720"
            try:
                short = int(res)
            except ValueError:
                raise ValueError(f"unknown resolution '{res}' (use {sorted(RESOLUTION_PRESETS)} or an int)")
        if cap_short and short > cap_short:
            print(f"[bench] warning: {res} short edge {short} > model max "
                  f"{cap_short}; capping to {cap_short}.", file=sys.stderr)
            short = cap_short
        w, h = compute_resolution(short, aspect, multiple)
        for dur in durations:
            durlbl = str(int(dur)) if float(dur).is_integer() else str(dur)
            name = f"{res}_{durlbl}s"
            cfgs.append((name, w, h, dur, seed_base + len(cfgs)))
    return cfgs


# =============================================================================#
# Backend.generate() call (handles optional engine kwarg, model-agnostic)
# =============================================================================#
def call_generate(backend, req, engine):
    """Invoke backend.generate() with engine only if the signature accepts it.

    The base contract declares generate(req); H3 declares generate(req, engine=None).
    Inspect so we work with any backend without special-casing."""
    try:
        params = inspect.signature(backend.generate).parameters
    except (TypeError, ValueError):
        params = {}
    accepts_engine = "engine" in params or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if accepts_engine:
        return backend.generate(req, engine=engine)
    return backend.generate(req)


# =============================================================================#
# Single config run
# =============================================================================#
def run_config(backend, engine, name, w, h, dur, seed, prompt, mode,
               server_log, steps_hint, gpu_index, results, receipt_path,
               profile="default"):
    """Run one generation config, capture metrics, write incremental JSON."""
    from open_video.core.backend import ShotRequest
    req = ShotRequest(prompt=prompt, mode=mode, width=w, height=h,
                      duration_s=dur, seed=seed, extra={"settings_profile": profile})

    sampler = ResourceSampler(gpu_index=gpu_index)
    sampler.start()
    t0 = time.time()
    result = None
    err = None
    try:
        result = call_generate(backend, req, engine)
        if not result.ok:
            err = result.error or "backend returned ok=False"
    except Exception as e:  # noqa: BLE001 - profile must not die on one config
        err = f"exception: {e}"
    wall = time.time() - t0
    sampler.stop()

    entry = {"width": w, "height": h, "duration_s": dur, "seed": seed,
             "length_frames": backend.duration_to_length(dur)}

    if result is not None and result.ok:
        size_mb = None
        if result.video_path and os.path.exists(result.video_path):
            try:
                size_mb = round(os.path.getsize(result.video_path) / 1e6, 2)
            except OSError:
                pass
        # engine-level timings from the ComfyUI server log (optional)
        pe = last_log_match(server_log, PROMPT_EXEC_RE)
        prompt_exec_s = float(pe.group(1)) if pe else None
        per_step_s = None
        log_steps = None
        sm = last_log_match(server_log, STEP_RE)
        if sm:
            per_step_s = float(sm.group(3))
            log_steps = int(sm.group(2))
        if per_step_s is None and prompt_exec_s and (steps_hint or log_steps):
            per_step_s = round(prompt_exec_s / (steps_hint or log_steps), 3)
        entry.update({
            "status": "ok",
            "wall_s": round(wall, 1),
            "prompt_executed_s": prompt_exec_s,
            "per_step_s": per_step_s,
            "steps": steps_hint or log_steps,
            "peak_vram_mb": sampler.peak_vram_mb,
            "peak_ram_mb": sampler.peak_ram_mb,
            "output_size_mb": size_mb,
            "video_path": result.video_path,
            "vram_samples": sampler.samples,
            "environment_failures": sampler.environment_failures,
        })
    else:
        entry.update({
            "status": "error",
            "error": str(err)[:400] if err else "unknown",
            "wall_s": round(wall, 1),
            "peak_vram_mb": sampler.peak_vram_mb,
            "peak_ram_mb": sampler.peak_ram_mb,
            "vram_samples": sampler.samples,
            "environment_failures": sampler.environment_failures,
        })

    results[name] = entry
    receipt_path.write_text(json.dumps(results, indent=2))
    print(json.dumps({name: {k: v for k, v in entry.items()
                             if k in ("status", "wall_s", "per_step_s", "steps",
                                      "peak_vram_mb", "peak_ram_mb", "output_size_mb",
                                      "width", "height", "duration_s")}}),
          flush=True)


def is_complete(entry: dict) -> bool:
    """Resumable-skip test.

    A completed receipt is only reusable while its generated artifact still
    exists.  Receipts intentionally remain useful for failed runs and metrics,
    but successful runs must be rerunnable if the output disappears.
    """
    if not entry or entry.get("status") in (None, "error", "timeout"):
        return False
    if entry.get("wall_s", 0) <= 0:
        return False

    video_path = entry.get("video_path")
    if video_path:
        return Path(video_path).is_file()

    return False


# =============================================================================#
# Summary table
# =============================================================================#
def print_summary(meta, results, warmup_key=None):
    cols = ("config", "res", "dur", "wall_s", "per_step_s", "steps",
            "vram_mb", "ram_mb", "size_mb", "status")
    widths = {"config": 16, "res": 10, "dur": 5, "wall_s": 8, "per_step_s": 10,
              "steps": 6, "vram_mb": 9, "ram_mb": 9, "size_mb": 9, "status": 8}

    def fmt(v, w):
        return str(v if v is not None else "-")[:w]

    print("=" * 96)
    print(f"BENCH  model={meta['model_id']}  gpu={meta['gpu']}  "
          f"engine={meta['engine']}  {meta['timestamp']}")
    print(f"       prompt: {meta['prompt'][:80]}")
    print("-" * 96)
    print("  " + "  ".join(c.upper().ljust(widths[c]) for c in cols))
    print("-" * 96)
    for name, e in results.items():
        if name == warmup_key or name.startswith("_"):
            continue  # skip _meta header and warmup entries
        row = {
            "config": name,
            "res": f"{e.get('width')}x{e.get('height')}",
            "dur": f"{e.get('duration_s')}s",
            "wall_s": e.get("wall_s"),
            "per_step_s": e.get("per_step_s"),
            "steps": e.get("steps"),
            "vram_mb": e.get("peak_vram_mb"),
            "ram_mb": e.get("peak_ram_mb"),
            "size_mb": e.get("output_size_mb"),
            "status": e.get("status"),
        }
        print("  " + "  ".join(fmt(row[c], widths[c]).ljust(widths[c]) for c in cols))
    print("=" * 96)


# =============================================================================#
# main
# =============================================================================#
def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="open-video-bench",
        description="Profile a ModelBackend at multiple resolutions x durations. "
                    "Measures per-step time, total time, peak VRAM/RAM, output size.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  python bench/profile.py --model h3 --gpu rtx5090\n"
               "  python bench/profile.py --model h3 --gpu 0 --resolutions 480p,768p --durations 5,10\n"
               "  python bench/profile.py --model h3 --gpu a100 --server-log logs/comfy_server.log\n"
               "  python bench/profile.py --list-models\n",
    )
    p.add_argument("--model", default="h3",
                   help="Backend alias/id to profile (default 'h3'). Use --list-models to see all.")
    p.add_argument("--gpu", default=None,
                   help="GPU label for the results filename (e.g. 'rtx5090', 'a100', '0'). "
                        "Required for profiling (not for --list-models).")
    p.add_argument("--gpu-index", type=int, default=None,
                   help="nvidia-smi GPU index to sample (default: parse int from --gpu, else 0).")
    p.add_argument("--resolutions", default="480p,768p",
                   help="Comma-separated resolution presets (480p/540p/720p/768p) or raw short-edge ints.")
    p.add_argument("--durations", default="5,10",
                   help="Comma-separated durations in seconds.")
    p.add_argument("--aspect", default="16:9", help="Aspect ratio (default 16:9).")
    p.add_argument("--mode", default="t2v", help="Generation mode (default t2v).")
    p.add_argument("--profile", default="default",
                   help="Backend settings profile (default 'default'; e.g. 'vdn_dmd8' for "
                        "the OpenVDN 8-NFE distilled route when the backend provides it).")
    p.add_argument("--prompt", default=DEFAULT_PROMPT, help="Prompt text (default: cinematic waves).")
    p.add_argument("--seed", type=int, default=101, help="Base seed (seed+i per config).")
    p.add_argument("--warmup", type=int, default=1,
                   help="Number of priming runs before the matrix (default 1; 0 to disable).")
    p.add_argument("--server", default=os.environ.get("OPEN_VIDEO_COMFYUI", "http://127.0.0.1:8188"),
                   help="ComfyUI server URL (default http://127.0.0.1:8188).")
    p.add_argument("--server-log", default=str(REPO_ROOT / "logs" / "comfy_server.log"),
                   help="ComfyUI server log path (enables per-step timing). "
                        "Default: <repo>/logs/comfy_server.log if present.")
    p.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR),
                   help="Where the engine saves generated videos (default bench/output).")
    p.add_argument("--results-dir", default=str(RESULTS_DIR),
                   help="Where to write results JSON (default bench/results).")
    p.add_argument("--no-skip", action="store_true",
                   help="Re-run configs even if already complete in the results file.")
    p.add_argument("--list-models", action="store_true", help="List available backends and exit.")
    return p.parse_args(argv)


def _split_csv(s):
    return [x.strip() for x in s.split(",") if x.strip()]


def main(argv=None) -> int:
    args = parse_args(argv)
    cli = _load_cli()

    if args.list_models:
        discovered, errors = cli.discover_backends()
        for alias, inst in discovered:
            print(f"{alias:<14} {getattr(inst,'id',alias):<22} {inst.display_name}")
        for err in errors:
            print(f"[bench] warning: {err['backend']} ({err['stage']}): {err['cause']}",
                  file=sys.stderr)
        return 0

    if not args.gpu:
        print("[bench] error: --gpu is required for profiling "
              "(e.g. --gpu rtx5090). Use --list-models to enumerate backends.",
              file=sys.stderr)
        return 2

    # --- load backend (same loader as the CLI) -------------------------------
    try:
        backend = cli.load_backend(args.model)
    except Exception as e:
        print(f"[bench] error: could not load model '{args.model}': {e}", file=sys.stderr)
        discovered, _ = cli.discover_backends()
        known = [a for a, _ in discovered]
        print(f"[bench] available: {', '.join(known) or '(none)'}", file=sys.stderr)
        return 2

    # mode vs capabilities
    mode_on = {"t2v": backend.capabilities.t2v, "i2v": backend.capabilities.i2v,
               "flf2v": backend.capabilities.flf2v, "r2v": backend.capabilities.r2v
               }.get(args.mode, False)
    if not mode_on:
        print(f"[bench] error: model '{backend.id}' does not support mode '{args.mode}'",
              file=sys.stderr)
        return 2

    # --- engine + health ------------------------------------------------------
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    engine = cli.load_engine(args.server, output_dir=str(output_dir))
    if not engine.health():
        print(f"[bench] error: engine not reachable at {args.server}. "
              f"Start ComfyUI on the target GPU first.", file=sys.stderr)
        return 3

    # --- gpu index for sampling ----------------------------------------------
    gpu_index = args.gpu_index
    if gpu_index is None:
        gpu_index = int(args.gpu) if re.fullmatch(r"\d+", args.gpu) else 0

    # --- results file (incremental + resumable) ------------------------------
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    safe = lambda s: re.sub(r"[^A-Za-z0-9._-]", "-", s)
    date = time.strftime("%Y%m%d")
    profile_tag = f"-{safe(args.profile)}" if args.profile != "default" else ""
    receipt_path = results_dir / f"{safe(args.model)}{profile_tag}-{safe(args.gpu)}-{date}.json"
    results = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}

    profiles = backend.settings_profiles() if hasattr(backend, "settings_profiles") else {}
    if args.profile != "default" and args.profile not in profiles:
        print(f"[bench] error: backend '{backend.id}' has no settings profile "
              f"'{args.profile}' (have: {', '.join(profiles) or 'none'})", file=sys.stderr)
        return 2
    steps_hint = profiles.get(args.profile, backend.default_settings()).get("steps")

    # --- build config matrix --------------------------------------------------
    try:
        cfgs = build_configs(backend, _split_csv(args.resolutions),
                             [float(d) for d in _split_csv(args.durations)],
                             args.aspect, args.seed)
    except ValueError as e:
        print(f"[bench] error: {e}", file=sys.stderr)
        return 2

    meta = {
        "model_alias": args.model,
        "model_id": backend.id,
        "model_display": backend.display_name,
        "gpu": args.gpu,
        "gpu_index": gpu_index,
        "engine": engine.id,
        "engine_server": args.server,
        "server_log": args.server_log if Path(args.server_log).is_file() else None,
        "aspect": args.aspect,
        "mode": args.mode,
        "prompt": args.prompt,
        "settings_profile": args.profile,
        "steps_hint": steps_hint,
        "capabilities": {
            "t2v": backend.capabilities.t2v, "i2v": backend.capabilities.i2v,
            "flf2v": backend.capabilities.flf2v, "r2v": backend.capabilities.r2v,
            "native_audio": backend.capabilities.native_audio,
            "max_duration_s": backend.capabilities.max_duration_s,
            "max_short_edge_px": backend.capabilities.max_short_edge_px,
        },
        "constraints": backend.constraints(),
        "settings": profiles.get(args.profile, backend.default_settings()),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "configs": [c[0] for c in cfgs],
    }
    # persist meta into the results file header (merge with any prior run)
    results.setdefault("_meta", {}).update(meta)
    receipt_path.write_text(json.dumps(results, indent=2))

    print(f"[bench] model={backend.id}  gpu={args.gpu} (index {gpu_index})  "
          f"engine={engine.id}  configs={len(cfgs)}  -> {receipt_path}", flush=True)
    print(f"[bench] matrix: {', '.join(c[0] for c in cfgs)}", flush=True)

    # --- warmup (prime model load; not part of the measured matrix) ----------
    warmup_key = None
    if args.warmup > 0 and cfgs:
        warmup_key = f"_warmup_{args.warmup}"
        # run warmups at the smallest config
        wname, ww, wh, wdur, wseed = cfgs[0]
        print(f"[bench] warmup x{args.warmup} @ {wname} (priming model load; not in summary)",
              flush=True)
        for _ in range(args.warmup):
            run_config(backend, engine, warmup_key, ww, wh, wdur, wseed,
                       args.prompt, args.mode, args.server_log, steps_hint,
                       gpu_index, results, receipt_path, profile=args.profile)

    # --- measured matrix (resumable) -----------------------------------------
    for name, w, h, dur, seed in cfgs:
        if not args.no_skip and is_complete(results.get(name)):
            print(f"[bench] skip {name} (already complete)", flush=True)
            continue
        print(f"[bench] run {name}  {w}x{h}  {dur}s  seed={seed}", flush=True)
        run_config(backend, engine, name, w, h, dur, seed, args.prompt, args.mode,
                   args.server_log, steps_hint, gpu_index, results, receipt_path,
                   profile=args.profile)

    # --- summary --------------------------------------------------------------
    print_summary(meta, results, warmup_key=warmup_key)
    print(f"[bench] DONE -> {receipt_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
