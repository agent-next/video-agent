#!/usr/bin/env python3
"""open-video CLI — concept -> planned film -> generated film.

Two ways to run (from the repo root):

    python cli/open_video.py "A cinematic shot of waves at sunset" \\
        --duration 10 --model h3 --output output.mp4

    # also works if the repo root is on PYTHONPATH and an open_video package
    # shim points here:
    python -m open_video "A cinematic shot of waves at sunset" [options]

Subcommands (Ollama-shaped where it helps):
    pull [h3]      Fetch / verify MiniMax H3 weights (resumable via install.sh)
    run "…"        Alias for generate (ollama run → open-video run)
    status | ps    ComfyUI health + H3 weight inventory + quant recommendation
    list-models    List available backends discovered under backends/.
    list-presets   List prompt presets in library/prompts/.
    recommend-quant  Resource-aware H3 quant (pull-by-hardware)
    serve          Start the open-video HTTP server (if installed).

The default action (no subcommand) is `generate`: validate the prompt -> build a
Planner plan -> run LongFilmPipeline (plan -> per-shot generate via the backend ->
FL2VA continuity chain -> judge -> stitch) -> write the film to --output.

Ollama mental model::

    curl -fsSL https://open-video.ai/install | bash   # install + pull
    open-video pull h3                                # (re)fetch weights
    open-video run "sunset waves" --duration 5        # generate
    open-video status                                 # engine + weights
"""
from __future__ import annotations
import argparse
import importlib
import inspect
import json
import math
import os
import sys
from pathlib import Path

# --- repo-root bootstrap ------------------------------------------------------
# REPO_ROOT is the parent of this cli/ dir: the repo root when run from source,
# the installed open_video/ package dir when packaged (backends/ etc. live
# directly under it either way). Only script-style invocation
# (python cli/open_video.py) needs the sys.path insert so `open_video.*`
# resolves; as an imported module the package machinery already handles it.
REPO_ROOT = Path(__file__).resolve().parent.parent
if not __package__ and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# --- defaults / constants -----------------------------------------------------
DEFAULT_MODEL = os.environ.get("OPEN_VIDEO_MODEL", "h3")
DEFAULT_DURATION = 10.0
DEFAULT_ASPECT = "16:9"
DEFAULT_OUTPUT = "output/film.mp4"
DEFAULT_SERVER = os.environ.get("OPEN_VIDEO_COMFYUI", "http://127.0.0.1:8188")
VALID_MODES = ("t2v", "i2v", "flf2v")
# Ollama-style aliases included (run/pull/status/ps/list).
SUBCOMMANDS = (
    "list-models",
    "list-presets",
    "list",  # alias → list-models
    "serve",
    "recommend-quant",
    "pull",
    "run",
    "status",
    "ps",  # alias → status
)

# Explicit registry (alias -> module path, class name). Discovery below is the
# fallback for new models dropped into backends/<name>/backend.py.
BACKEND_REGISTRY = {
    "h3": ("open_video.backends.h3.backend", "H3Backend"),
}


# =============================================================================#
# Backend discovery + loading
# =============================================================================#
def discover_backends():
    """Walk backends/<name>/backend.py and instantiate every ModelBackend subclass.

    Returns (found, errors): ``found`` is a list of (alias, instance) where alias
    is the directory name; ``errors`` lists discovery failures as
    ``{"backend", "stage", "cause"}`` dicts so callers can report why a backend
    is missing instead of silently omitting it.
    """
    from open_video.core.backend import ModelBackend
    backends_dir = REPO_ROOT / "backends"
    found = []
    errors = []
    if not backends_dir.is_dir():
        return found, errors
    for sub in sorted(backends_dir.iterdir()):
        if not (sub.is_dir() and (sub / "backend.py").exists()):
            continue
        mod_path = f"open_video.backends.{sub.name}.backend"
        try:
            mod = importlib.import_module(mod_path)
        except Exception as e:  # pragma: no cover - depends on backend deps
            errors.append({"backend": sub.name, "stage": "import", "cause": str(e)})
            continue
        for _name, obj in inspect.getmembers(mod, inspect.isclass):
            if obj is ModelBackend or not issubclass(obj, ModelBackend):
                continue
            if obj.__module__ != mod.__name__:
                continue  # imported base class, not the one defined here
            try:
                inst = obj()
            except Exception as e:  # pragma: no cover
                errors.append({"backend": sub.name, "stage": "instantiate",
                               "cause": str(e)})
                continue
            found.append((sub.name, inst))
    return found, errors


def _format_discovery_errors(errors: list) -> str:
    """One line per discovery failure, for stderr output."""
    return "\n".join(
        f"[open-video]   - {e['backend']} ({e['stage']}): {e['cause']}" for e in errors)


def load_backend(model_id: str):
    """Resolve a model alias/id to a ModelBackend instance.

    Order: explicit BACKEND_REGISTRY -> discovery (match dir name or backend.id).
    Raises KeyError if not found.
    """
    if model_id in BACKEND_REGISTRY:
        mod_path, cls_name = BACKEND_REGISTRY[model_id]
        try:
            mod = importlib.import_module(mod_path)
        except Exception as e:
            raise KeyError(f"model '{model_id}' ({mod_path}) could not be imported: {e}") from e
        if not hasattr(mod, cls_name):
            raise KeyError(f"model '{model_id}': {mod_path} has no '{cls_name}'")
        return getattr(mod, cls_name)()

    discovered, errors = discover_backends()
    for alias, inst in discovered:
        if alias == model_id or getattr(inst, "id", None) == model_id:
            return inst
    if errors:
        detail = "; ".join(f"{e['backend']}/{e['stage']}: {e['cause']}" for e in errors)
        raise KeyError(f"model '{model_id}' not found; backend discovery failures: {detail}")
    raise KeyError(model_id)


def _bind_engine(backend, engine):
    """Inject `engine` into every backend.generate() call made by LongFilmPipeline.

    The base contract declares generate(req); H3 declares generate(req, engine=None)
    and creates its own default adapter when engine is None. The pipeline calls
    generate(req) (one arg), so without this binding the --server flag would be
    silently ignored. We wrap generate so our configured engine is always passed,
    but only if the backend's signature actually accepts it.
    """
    orig = backend.generate
    try:
        params = inspect.signature(orig).parameters
    except (TypeError, ValueError):
        params = {}
    accepts_engine = "engine" in params or any(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    if not accepts_engine:
        return  # backend takes no engine kwarg; let it use its own default adapter

    def _generate(req, *args, **kwargs):
        # bound engine is authoritative; a caller-supplied engine kwarg is
        # dropped so it cannot collide with the injected one.
        kwargs.pop("engine", None)
        return orig(req, *args, engine=engine, **kwargs)

    # call as bound method on the instance so `self` is preserved
    backend.generate = _generate


# =============================================================================#
# Engine loading
# =============================================================================#
def load_engine(server: str, output_dir: str):
    from open_video.engines.comfyui.adapter import ComfyUIAdapter
    return ComfyUIAdapter(server=server, output_dir=output_dir)


# =============================================================================#
# Plan rendering
# =============================================================================#
def _truncate(s: str, n: int = 240) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def print_plan(plan, backend):
    caps = backend.capabilities
    print("=" * 78)
    print(f"CONCEPT: {plan.concept}")
    print(f"target: {plan.target_duration_s:g}s | aspect: {plan.metadata.get('aspect','?')} "
          f"| model: {backend.id} ({backend.display_name})")
    print(f"max shot: {caps.max_duration_s:g}s | native audio: {caps.native_audio} "
          f"| modes: "
          + "/".join(m for m, on in (("t2v", caps.t2v), ("i2v", caps.i2v),
                                     ("flf2v", caps.flf2v), ("r2v", caps.r2v)) if on))
    print(f"plan: {len(plan.shots)} shot(s), {len(plan.transitions)} transition(s)")
    if plan.metadata.get("v0_note"):
        print(f"note: {plan.metadata['v0_note']}")
    print("-" * 78)
    for s in plan.shots:
        ff = f" ff={s.first_frame}" if s.first_frame else ""
        lf = f" lf={s.last_frame}" if s.last_frame else ""
        print(f"  Shot {s.scene_id} [{s.mode}] {s.duration_s:g}s seed={s.seed}{ff}{lf}")
        print(f"    {_truncate(s.prompt)}")
    print("=" * 78)


# =============================================================================#
# generate (default command)
# =============================================================================#
def _emit_generate_json(shots, film, dry_run: bool):
    """One schema for the --json self-verification line (dry-run + real)."""
    out = []
    for s_ in shots:
        d = {"scene_id": s_.scene_id, "mode": s_.mode,
             "duration_s": s_.duration_s, "seed": s_.seed}
        if not dry_run:
            d.update({"video_path": s_.video_path, "verdict": s_.verdict,
                      "judge_score": s_.receipt.get("judge_score"),
                      "judge_issues": s_.receipt.get("judge_issues", []),
                      "judge_frames": s_.receipt.get("judge_frames", []),
                      "receipt": s_.receipt})
        out.append(d)
    print(json.dumps({"dry_run": dry_run, "validated": True, "film": film, "shots": out}))


def _emit_failure_json(args, shots, exit_code: int, error: str) -> None:
    """--json failure line (exit 3/4): same shot keys as _emit_generate_json."""
    out = []
    for s_ in shots:
        receipt = s_.receipt or {}
        out.append({"scene_id": s_.scene_id, "mode": s_.mode,
                    "duration_s": s_.duration_s, "seed": s_.seed,
                    "video_path": s_.video_path, "verdict": s_.verdict,
                    "receipt": receipt, "error": receipt.get("error")})
    print(json.dumps({"ok": False, "exit_code": exit_code, "error": error,
                      "dry_run": False, "film": None, "shots": out}))


def cmd_generate(args) -> int:
    print("[open-video] [1/5] loading backend + validating prompt…", flush=True)
    # 1. prompt validation
    if not args.prompt or not args.prompt.strip():
        print("[open-video] error: prompt is empty", file=sys.stderr)
        return 2

    # 2. load backend
    try:
        backend = load_backend(args.model)
    except KeyError as e:
        print(f"[open-video] error: unknown model '{args.model}' ({e})", file=sys.stderr)
        discovered, _ = discover_backends()
        known = sorted({*BACKEND_REGISTRY.keys(), *[a for a, _ in discovered]})
        print(f"[open-video] available: {', '.join(known) or '(none)'}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[open-video] error loading model '{args.model}': {e}", file=sys.stderr)
        return 2

    caps = backend.capabilities

    # 3. mode vs capabilities
    mode_supported = {"t2v": caps.t2v, "i2v": caps.i2v, "flf2v": caps.flf2v}.get(args.mode, False)
    if not mode_supported:
        print(f"[open-video] error: model '{backend.id}' does not support mode '{args.mode}'",
              file=sys.stderr)
        return 2

    # 4. Reject unsupported aspects before planning or spending GPU time.
    if caps.aspects and args.aspect not in caps.aspects:
        print(f"[open-video] error: model '{backend.id}' does not support aspect "
              f"'{args.aspect}'; choose from {', '.join(caps.aspects)}.",
              file=sys.stderr)
        return 2

    # 5. duration sanity
    if not math.isfinite(args.duration) or args.duration <= 0:
        print(f"[open-video] error: --duration must be a finite number > 0 (got {args.duration})",
              file=sys.stderr)
        return 2
    if args.duration < 1.0:
        print(f"[open-video] warning: --duration {args.duration}s is very short.",
              file=sys.stderr)

    # 6. frame-input validation per mode
    ff, lf = args.first_frame, args.last_frame
    if args.mode == "i2v" and not ff:
        print("[open-video] error: --mode i2v requires --first-frame", file=sys.stderr)
        return 2
    if args.mode == "flf2v" and not (ff and lf):
        print("[open-video] error: --mode flf2v requires both --first-frame and --last-frame",
              file=sys.stderr)
        return 2
    for label, path in (("first-frame", ff), ("last-frame", lf)):
        if path and not Path(path).is_file():
            print(f"[open-video] error: {label} not found: {path}", file=sys.stderr)
            return 2

    # 7. decide shot-0 mode (upgrade t2v -> i2v when a first frame is supplied)
    shot0_mode = args.mode
    if ff and args.mode == "t2v":
        if not caps.i2v:
            print(f"[open-video] error: --first-frame needs i2v but '{backend.id}' "
                  f"has no i2v capability", file=sys.stderr)
            return 2
        print("[open-video] note: --first-frame supplied; upgrading shot 1 t2v -> i2v",
              file=sys.stderr)
        shot0_mode = "i2v"

    # 8. build the plan
    print("[open-video] [2/5] planning shots…", flush=True)
    from open_video.core.planner import Planner
    planner = Planner(backend=backend)
    plan = planner.plan_from_concept(args.prompt, target_duration_s=args.duration,
                                     aspect=args.aspect)
    shots = plan.shots
    if not shots:
        print("[open-video] error: planner produced no shots", file=sys.stderr)
        return 1

    # 9. inject CLI overrides into the planned shots
    shots[0].mode = shot0_mode
    if ff:
        shots[0].first_frame = str(Path(ff).resolve())
    if lf and shot0_mode == "flf2v":
        shots[0].last_frame = str(Path(lf).resolve())
    if args.seed is not None:
        for i, s in enumerate(shots):
            s.seed = args.seed + i

    # 10. single-shot films use the user's prompt verbatim; multi-shot v0 plans
    #     carry template prompts and need an LLM planner — be honest about it.
    if len(shots) == 1:
        shots[0].prompt = args.prompt
    elif any("TODO: LLM generates" in (s.prompt or "") for s in shots):
        if not args.dry_run:
            print(f"[open-video] error: multi-shot prompt generation needs an LLM and is "
                  f"not wired; use --duration <= {caps.max_duration_s:g} for a single-shot "
                  f"film using your prompt verbatim, or pass shots explicitly.",
                  file=sys.stderr)
            return 2
        print(f"[open-video] note: multi-shot plan uses v0 template prompts. Wire an "
              f"LLM planner (Planner(llm_fn=...)) for authored per-shot prompts, or set "
              f"--duration <= {caps.max_duration_s:g}s for a single-shot film using "
              f"your prompt verbatim.", file=sys.stderr)

    # 11. show the plan
    print("[open-video] [3/5] plan ready", flush=True)
    print_plan(plan, backend)

    # Optional: show resource-aware quant hint (never blocks)
    try:
        from open_video.core.resources import format_recommendation, recommend_for_host
        print(format_recommendation(recommend_for_host()), flush=True)
    except Exception:
        pass

    if args.dry_run:
        print("[open-video] [4/5] --dry-run: prompt + plan validated. No generation performed.",
              flush=True)
        print("[open-video] [5/5] done (dry-run).", flush=True)
        if args.json:
            _emit_generate_json(shots, film=None, dry_run=True)
        return 0

    # 12. engine + pipeline
    print("[open-video] [4/5] connecting ComfyUI + generating…", flush=True)
    out_path = Path(args.output)
    out_dir = str(out_path.parent) if str(out_path.parent) not in ("", ".") else "output"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    engine = load_engine(args.server, output_dir=out_dir)
    if not engine.health():
        msg = (f"ComfyUI not reachable at {args.server}. "
               f"Start it (or use --dry-run to validate without generating).")
        print(f"[open-video] error: {msg}", file=sys.stderr)
        if args.json:
            _emit_failure_json(args, shots, 3, msg)
        return 3
    _bind_engine(backend, engine)

    from open_video.core.pipeline import LongFilmPipeline
    pipeline = LongFilmPipeline(backend=backend, engine=engine, output_dir=out_dir,
                                aspect=args.aspect)
    film, _final_plan = pipeline.make_film(shots, out_path=str(out_path))
    if not film:
        print("[open-video] error: pipeline did not produce a film.", file=sys.stderr)
        if args.json:
            _emit_failure_json(args, shots, 4, "pipeline did not produce a film.")
        return 4
    print(f"[open-video] [5/5] DONE -> {film}", flush=True)
    if args.json:
        _emit_generate_json(shots, film=film, dry_run=False)
    return 0


# =============================================================================#
# list-models
# =============================================================================#
def cmd_list_models(args) -> int:
    rows = []
    # registry-first so aliases like "h3" always appear even if discovery trips
    seen = set()
    for alias in BACKEND_REGISTRY:
        try:
            inst = load_backend(alias)
        except Exception as e:
            rows.append((alias, "?", "ERROR", "", f"load failed: {e}"))
            seen.add(alias)
            continue
        rows.append(_backend_row(alias, inst))
        seen.add(alias)
    discovered, discovery_errors = discover_backends()
    for alias, inst in discovered:
        if alias in seen:
            continue
        rows.append(_backend_row(alias, inst))
        seen.add(alias)
    if discovery_errors:
        print("[open-video] backend discovery failures:", file=sys.stderr)
        print(_format_discovery_errors(discovery_errors), file=sys.stderr)

    if args.json:
        print(json.dumps([{"alias": a, "id": i, "display": d, "modes": m, "max_s": mx}
                          for (a, i, d, m, mx) in rows], indent=2))
        return 0

    if not rows:
        print("(no backends found under backends/)")
        return 0
    print(f"{'ALIAS':<14} {'MODEL ID':<22} {'MODES':<18} {'MAX_S':<7} DISPLAY")
    print("-" * 78)
    for alias, bid, display, modes, max_s in rows:
        print(f"{alias:<14} {bid:<22} {modes:<18} {str(max_s):<7} {display}")
    return 0


def _backend_row(alias, inst):
    caps = inst.capabilities
    modes = "/".join(m for m, on in (("t2v", caps.t2v), ("i2v", caps.i2v),
                                     ("flf2v", caps.flf2v), ("r2v", caps.r2v)) if on) or "-"
    return (alias, getattr(inst, "id", alias), getattr(inst, "display_name", alias),
            modes, caps.max_duration_s)


# =============================================================================#
# list-presets
# =============================================================================#
def cmd_list_presets(args) -> int:
    presets_dir = REPO_ROOT / "library" / "prompts"
    if not presets_dir.is_dir():
        print(f"[open-video] no presets dir at {presets_dir}", file=sys.stderr)
        return 1
    files = sorted(p for p in presets_dir.iterdir()
                   if p.is_file() and p.suffix in (".txt", ".md"))
    if not files:
        print("(no presets found)")
        return 0
    if args.json:
        out = []
        for f in files:
            out.append({"file": f.name, "path": str(f), "title": _first_line(f)})
        print(json.dumps(out, indent=2))
        return 0
    print(f"{'FILE':<38} TITLE")
    print("-" * 78)
    for f in files:
        print(f"{f.name:<38} {_truncate(_first_line(f), 36)}")
    return 0


def _first_line(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    return line
    except OSError:
        return ""
    return ""


# =============================================================================#
# serve
# =============================================================================#
def cmd_serve(args) -> int:
    candidates = [("server.app", "app"), ("server", "app"),
                  ("api.app", "app"), ("open_video.server", "app")]
    app_obj, loaded_from = None, None
    for mod, attr in candidates:
        try:
            m = importlib.import_module(mod)
        except ImportError:
            continue
        if hasattr(m, attr):
            app_obj = getattr(m, attr)
            loaded_from = f"{mod}:{attr}"
            break
    if app_obj is None:
        print("[open-video] no server module found. Looked for: "
              + ", ".join(f"{m}:{a}" for m, a in candidates), file=sys.stderr)
        print("[open-video] the HTTP server is not installed in this repo yet.",
              file=sys.stderr)
        return 5
    try:
        import uvicorn
    except ImportError:
        print("[open-video] uvicorn not installed; install with: pip install uvicorn",
              file=sys.stderr)
        return 5
    print(f"[open-video] serving {loaded_from} on http://{args.host}:{args.port}",
          flush=True)
    uvicorn.run(app_obj, host=args.host, port=args.port)
    return 0


# =============================================================================#
# argparse builders
# =============================================================================#
def build_generate_parser():
    p = argparse.ArgumentParser(
        prog="open_video",
        description="Generate a film from a concept (default action). "
                    "Validates the prompt, builds a Planner plan, runs LongFilmPipeline "
                    "(generate -> judge -> FL2VA chain -> stitch).",
        epilog="examples:\n"
               "  open_video \"waves at sunset\" --duration 10 --model h3\n"
               "  open_video \"...\" --mode i2v --first-frame start.png --output out.mp4\n"
               "  open_video \"...\" --dry-run        # plan only, no generation\n"
               "  open_video list-models\n"
               "\n"
               f"subcommands: {', '.join(SUBCOMMANDS)}\n"
               "  (a prompt equal to a subcommand word is dispatched as that subcommand;\n"
               "   use `open-video run \"status\"` to generate from such a prompt)\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("prompt", help="Concept / prompt for the film.")
    p.add_argument("--duration", type=float, default=DEFAULT_DURATION,
                   help=f"Target duration in seconds (default {DEFAULT_DURATION:g}). "
                        f"Values above the model's max shot length produce a multi-shot film.")
    p.add_argument("--model", default=DEFAULT_MODEL,
                   help=f"Backend alias or id (default '{DEFAULT_MODEL}'). "
                        f"See `list-models`.")
    p.add_argument("--output", default=DEFAULT_OUTPUT,
                   help=f"Output film path (default '{DEFAULT_OUTPUT}').")
    p.add_argument("--aspect", default=DEFAULT_ASPECT,
                   help=f"Aspect ratio (default '{DEFAULT_ASPECT}').")
    p.add_argument("--seed", type=int, default=None,
                   help="Base seed; applied as seed+i across shots (default: planner's).")
    p.add_argument("--mode", choices=VALID_MODES, default="t2v",
                   help="Generation mode for shot 1 (default t2v). i2v/flf2v require "
                        "frame inputs; supplying --first-frame auto-upgrades t2v -> i2v.")
    p.add_argument("--first-frame", metavar="PATH",
                   help="First-frame image (i2v/flf2v, or to upgrade shot 1 from t2v).")
    p.add_argument("--last-frame", metavar="PATH",
                   help="Last-frame image (flf2v only).")
    p.add_argument("--server", default=DEFAULT_SERVER,
                   help=f"ComfyUI server URL (default '{DEFAULT_SERVER}'; "
                        f"env OPEN_VIDEO_COMFYUI).")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate prompt + show the plan, then exit without generating.")
    p.add_argument("--json", action="store_true",
                   help="Emit a machine-readable JSON result (film path + per-shot judge "
                        "verdicts + full take receipts) as the final stdout line — the "
                        "agent self-verification channel.")
    return p


def build_list_models_parser():
    p = argparse.ArgumentParser(prog="open_video list-models",
                                description="List available backends under backends/.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    return p


def build_list_presets_parser():
    p = argparse.ArgumentParser(prog="open_video list-presets",
                                description="List prompt presets in library/prompts/.")
    p.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    return p


def build_serve_parser():
    p = argparse.ArgumentParser(prog="open_video serve",
                                description="Start the open-video HTTP server (uvicorn).")
    p.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
    p.add_argument("--port", type=int, default=8000, help="Bind port (default 8000).")
    return p


def build_recommend_quant_parser():
    p = argparse.ArgumentParser(
        prog="open_video recommend-quant",
        description="Resource-aware H3 quant recommendation (Ollama-style pull-by-hardware).",
    )
    p.add_argument("--vram", type=int, default=None, help="Override VRAM MiB (fixture mode).")
    p.add_argument("--no-nvidia", action="store_true", help="Simulate no NVIDIA GPU.")
    p.add_argument("--quant", default="auto", help="Force quant or auto (default).")
    p.add_argument("--json", action="store_true", help="Emit JSON.")
    return p


def cmd_recommend_quant(args) -> int:
    print("[open-video] [1/1] probing host resources for H3 quant…", flush=True)
    from open_video.core.resources import (
        format_recommendation,
        recommend_for_host,
        recommend_quant,
    )
    import json as _json
    if args.vram is not None or args.no_nvidia:
        has = not args.no_nvidia
        vram = 0 if args.no_nvidia else int(args.vram or 0)
        rec = recommend_quant(vram, has_nvidia=has, force_quant=args.quant)
    else:
        rec = recommend_for_host(force_quant=args.quant)
    if args.json:
        print(_json.dumps(rec.to_dict(), indent=2, sort_keys=True))
    else:
        print(format_recommendation(rec))
    return 0


def build_pull_parser():
    p = argparse.ArgumentParser(
        prog="open_video pull",
        description="Fetch MiniMax H3 weights (Ollama-style pull). "
                    "Downloads and verifies INT8 weights; resumes via the packaged manifest tool.",
        epilog="examples:\n"
               "  open-video pull h3\n"
               "  open-video pull h3 --check-only\n"
               "  open-video pull h3 --models-dir /data/ComfyUI/models\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "model",
        nargs="?",
        default="h3",
        help="Model id to pull (default: h3). Only h3 is shipped today.",
    )
    p.add_argument(
        "--models-dir",
        default=None,
        help="Weights root (default: OPEN_VIDEO_MODELS, $OPEN_VIDEO_LAB/h3_models, "
             "OPEN_VIDEO_HOME, ../lab/h3_models, or <repo>/ComfyUI/models; "
             "see core/h3_weights.default_models_dir).",
    )
    p.add_argument(
        "--check-only",
        action="store_true",
        help="Only inventory presence and sizes; no checksum verification or download.",
    )
    p.add_argument("--quant", default="auto", help="Quant profile hint (auto|nf4|w4|int8).")
    p.add_argument("--json", action="store_true", help="Emit inventory JSON.")
    return p


def cmd_pull(args) -> int:
    """Ollama ``pull`` analogue — verify / download H3 weights."""
    from open_video.core.h3_weights import (
        default_models_dir,
        format_inventory,
        inventory_h3_int8,
        known_models,
    )
    from open_video.core.resources import format_recommendation, recommend_for_host

    model = (args.model or "h3").strip().lower()
    if model not in known_models():
        print(
            f"[open-video] error: unknown model {model!r}. "
            f"Known: {', '.join(known_models())}",
            file=sys.stderr,
        )
        return 2

    models_dir = (
        Path(args.models_dir).expanduser().resolve()
        if args.models_dir
        else default_models_dir(REPO_ROOT)
    )
    print(f"[open-video] [1/3] pull {model} → {models_dir}", flush=True)
    rec = recommend_for_host(force_quant=args.quant)
    print(format_recommendation(rec), flush=True)

    inv = inventory_h3_int8(models_dir)
    if args.json:
        payload = inv.to_dict()
        payload["quant"] = rec.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(format_inventory(inv), flush=True)

    if args.check_only:
        print("[open-video] [3/3] --check-only: size inventory only; no checksum verification or download.",
              flush=True)
        return 0 if inv.ready else 1

    # Weight pulls must also work from a read-only wheel installation. Runtime
    # setup belongs to install.sh; fetch/check only touch the selected model store.
    from open_video.scripts import verify_h3_manifest as manifest_tool
    verify_args = argparse.Namespace(manifest=str(REPO_ROOT / "models" / "h3_manifest.json"),
                                     models_dir=str(models_dir), size_only=False)
    try:
        manifest = manifest_tool.load_manifest(verify_args.manifest)
        if manifest_tool.missing_metadata(manifest):
            print("[open-video] error: weight manifest lacks SHA-256/commit metadata; refusing download.",
                  file=sys.stderr)
            return 2
        if not inv.ready:
            print("[open-video] [2/3] fetching INT8 weights (curl, resumable, ~54 GB)…", flush=True)
            code = manifest_tool.cmd_fetch(verify_args)
            if code:
                print("[open-video] pull incomplete: download failed; rerun to resume.", file=sys.stderr)
                return code
        print("[open-video] [3/3] verifying SHA-256 for every weight file…", flush=True)
        code = manifest_tool.cmd_check(verify_args)
    except (OSError, ValueError, KeyError, SystemExit) as exc:
        print(f"[open-video] error: weight pull failed: {exc}", file=sys.stderr)
        return 2
    if code:
        print("[open-video] pull failed integrity verification; existing files were preserved.",
              file=sys.stderr)
        return code
    print("[open-video] H3 weights verified (SHA-256).", flush=True)
    return 0


def build_status_parser():
    p = argparse.ArgumentParser(
        prog="open_video status",
        description="Engine + weights status (Ollama-style ps/status).",
    )
    p.add_argument(
        "--server",
        default=DEFAULT_SERVER,
        help=f"ComfyUI URL (default {DEFAULT_SERVER}).",
    )
    p.add_argument("--models-dir", default=None, help="Override models directory.")
    p.add_argument("--json", action="store_true", help="Emit JSON.")
    return p


def cmd_status(args) -> int:
    """Ollama ``ps`` / status — ComfyUI health + H3 inventory + quant."""
    from open_video.core.h3_weights import default_models_dir, format_inventory, inventory_h3_int8
    from open_video.core.resources import format_recommendation, recommend_for_host
    from open_video.engines.comfyui.adapter import ComfyUIAdapter

    models_dir = (
        Path(args.models_dir).expanduser().resolve()
        if args.models_dir
        else default_models_dir(REPO_ROOT)
    )
    rec = recommend_for_host()
    inv = inventory_h3_int8(models_dir)
    engine = ComfyUIAdapter(server=args.server)
    healthy = engine.health()

    payload = {
        "server": args.server,
        "comfyui_ok": healthy,
        "quant": rec.to_dict(),
        "weights": inv.to_dict(),
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"[open-video] ComfyUI {args.server}: "
            f"{'up' if healthy else 'down (start engine or use --dry-run)'}",
            flush=True,
        )
        print(format_recommendation(rec), flush=True)
        print(format_inventory(inv), flush=True)
        if healthy and inv.ready:
            print(
                '[open-video] ready — try: open-video run "a red panda in mist" --duration 5',
                flush=True,
            )
        elif not inv.ready:
            print("[open-video] next: open-video pull h3", flush=True)
        elif not healthy:
            print(
                "[open-video] next: start ComfyUI "
                "(install.sh starts it, or python ComfyUI/main.py --lowvram)",
                flush=True,
            )
    # exit 0 if engine up and weights ready; 1 if usable dry-run only; 2 hard fail
    if healthy and inv.ready:
        return 0
    if inv.ready or healthy:
        return 1
    return 1


# =============================================================================#
# dispatch
# =============================================================================#
def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in SUBCOMMANDS:
        sub, rest = argv[0], argv[1:]
        if sub in ("list-models", "list"):
            return cmd_list_models(build_list_models_parser().parse_args(rest))
        if sub == "list-presets":
            return cmd_list_presets(build_list_presets_parser().parse_args(rest))
        if sub == "serve":
            return cmd_serve(build_serve_parser().parse_args(rest))
        if sub == "recommend-quant":
            return cmd_recommend_quant(build_recommend_quant_parser().parse_args(rest))
        if sub == "pull":
            return cmd_pull(build_pull_parser().parse_args(rest))
        if sub in ("status", "ps"):
            return cmd_status(build_status_parser().parse_args(rest))
        if sub == "run":
            # ollama run → generate
            return cmd_generate(build_generate_parser().parse_args(rest))
    return cmd_generate(build_generate_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
