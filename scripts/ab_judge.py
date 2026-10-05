#!/usr/bin/env python3
"""A/B quality judge: score two generated videos with the same VLM judge.

Used by the bench flow to compare settings profiles (e.g. default 20-step vs
vdn_dmd8 8-NFE) on identical prompts. Reads video paths directly or the newest
output videos referenced in two bench receipt JSONs. For each side it extracts
evenly spaced frames (downscaled JPEG, payload-safe for constrained links) and
calls the OpenAI-compatible VLM directly (judges/openai_compat.py env wiring);
per-side frames live in separate directories so the two receipts never alias.

Writes a side-by-side receipt and prints the summary. Anything that is not a
real judgment — no VLM env, frame-extraction failure, VLM error — makes
``judged:false`` and exits 2, so callers never mistake "not judged" for
"judged equal".
"""
from __future__ import annotations
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from judges.openai_compat import vision_fn_from_env

FRAMES_PER_SIDE = 5
FRAME_WIDTH_PX = 640


def _video_from_receipt(receipt_path: Path) -> tuple[str, str]:
    d = json.loads(receipt_path.read_text())
    videos = [(k, v.get("video_path")) for k, v in d.items()
              if isinstance(v, dict) and v.get("video_path")]
    if not videos:
        raise SystemExit(f"no completed config with video_path in {receipt_path}")
    name, path = videos[-1]
    prompt = (d.get("_meta") or {}).get("prompt")
    return path, prompt or ""


def _rel(path: str) -> str:
    """Repo-relative form when the file lives under the cwd, else as given."""
    try:
        return str(Path(path).resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return path


def _extract_frames(video: str, out_dir: Path) -> list[str]:
    """Evenly spaced frames as downscaled JPEGs; raises on any failure."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f*.jpg"):
        old.unlink()
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], capture_output=True, text=True)
    if probe.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {probe.stderr.strip()[:200]}")
    dur = float(probe.stdout.strip())
    paths = []
    for i in range(FRAMES_PER_SIDE):
        t = dur * i / FRAMES_PER_SIDE
        p = out_dir / f"f{i}.jpg"
        r = subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", video,
             "-frames:v", "1", "-vf", f"scale={FRAME_WIDTH_PX}:-2", "-q:v", "3",
             str(p)], capture_output=True, text=True)
        if r.returncode != 0 or not p.is_file() or p.stat().st_size == 0:
            raise RuntimeError(f"frame {i} extraction failed: {r.stderr.strip()[:200]}")
        paths.append(str(p))
    return paths


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a-receipt", type=Path, help="bench receipt JSON of side A")
    p.add_argument("--b-receipt", type=Path, help="bench receipt JSON of side B")
    p.add_argument("--a-video", help="video of side A (overrides --a-receipt)")
    p.add_argument("--b-video", help="video of side B (overrides --b-receipt)")
    p.add_argument("--prompt", help="shared prompt (required with --a/--b-video "
                                    "unless a receipt supplies it)")
    p.add_argument("--out", type=Path, required=True, help="output receipt JSON")
    p.add_argument("--frames-root", type=Path, default=Path("bench/output/ab_judge_frames"),
                   help="where per-side frames are written (default: gitignored bench/output)")
    args = p.parse_args(argv)

    va, vb, prompt = args.a_video, args.b_video, args.prompt
    if not va and args.a_receipt:
        va, pr = _video_from_receipt(args.a_receipt)
        prompt = prompt or pr
    if not vb and args.b_receipt:
        vb, pr = _video_from_receipt(args.b_receipt)
        prompt = prompt or pr
    if not (va and vb and prompt):
        p.error("need both videos and the shared prompt (receipts or explicit flags)")
    for v in (va, vb):
        if not Path(v).is_file():
            raise SystemExit(f"video not found: {v}")

    vision_fn = vision_fn_from_env()
    out = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "prompt": prompt}
    if vision_fn is None:
        out["summary"] = {"judged": False,
                          "reason": "no judge env: set OPEN_VIDEO_VLM_URL + OPEN_VIDEO_VLM_MODEL"}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=2))
        print(json.dumps(out["summary"]))
        return 2
    import os
    out["judge"] = {"model": os.environ.get("OPEN_VIDEO_VLM_MODEL", ""),
                    "transport": "OpenAI-compatible chat completions (env)",
                    "frames_per_side": FRAMES_PER_SIDE, "frame_width_px": FRAME_WIDTH_PX}

    frames_dir = args.frames_root / args.out.stem
    for side, video in (("a", va), ("b", vb)):
        entry = {"video": _rel(video)}
        try:
            fps = _extract_frames(video, frames_dir / side)
            verdict = vision_fn(fps, prompt)
            entry.update({"verdict": "JUDGED", "score": float(verdict["score"]),
                          "detail": verdict, "frames": [_rel(f) for f in fps]})
        except Exception as e:  # noqa: BLE001 - recorded, never a fake judgment
            kind = "extraction_error" if "extraction failed" in str(e) or "ffprobe" in str(e) \
                else "judge_error"
            entry.update({"verdict": kind, "score": 0.0, "error": str(e)[:300]})
        out[side] = entry

    def _judged(side: str) -> bool:
        return out[side]["verdict"] == "JUDGED"
    out["summary"] = {
        "a_score": out["a"]["score"], "b_score": out["b"]["score"],
        "delta_b_minus_a": round(out["b"]["score"] - out["a"]["score"], 3),
        "judged": _judged("a") and _judged("b"),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"]))
    return 0 if out["summary"]["judged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
