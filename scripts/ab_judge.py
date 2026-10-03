#!/usr/bin/env python3
"""A/B quality judge: score two generated videos with the same VLM judge.

Used by the bench flow to compare settings profiles (e.g. default 20-step vs
vdn_dmd8 8-NFE) on identical prompts. Reads video paths directly or the newest
output videos referenced in two bench receipt JSONs; judges each with
QualityJudge.from_env() (same prompt, same frame count) and writes a
side-by-side receipt. VLM wiring is the standard judge env (see
judges/openai_compat.py); without it both verdicts are honest SKIPPED and the
script exits 2 so callers never mistake "not judged" for "judged equal".
"""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from open_video.core.judge import QualityJudge


def _video_from_receipt(receipt_path: Path) -> tuple[str, str]:
    d = json.loads(receipt_path.read_text())
    videos = [(k, v.get("video_path")) for k, v in d.items()
              if isinstance(v, dict) and v.get("video_path")]
    if not videos:
        raise SystemExit(f"no completed config with video_path in {receipt_path}")
    name, path = videos[-1]
    prompt = (d.get("_meta") or {}).get("prompt")
    return path, prompt or ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--a-receipt", type=Path, help="bench receipt JSON of side A")
    p.add_argument("--b-receipt", type=Path, help="bench receipt JSON of side B")
    p.add_argument("--a-video", help="video of side A (overrides --a-receipt)")
    p.add_argument("--b-video", help="video of side B (overrides --b-receipt)")
    p.add_argument("--prompt", help="shared prompt (required with --a/--b-video "
                                    "unless a receipt supplies it)")
    p.add_argument("--out", type=Path, required=True, help="output receipt JSON")
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

    judge = QualityJudge.from_env()
    out = {"timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"), "prompt": prompt,
           "a": {"video": va}, "b": {"video": vb}}
    def _judged(side: dict) -> bool:  # SKIPPED and judge_error FAILs are not judgments
        return not (side["verdict"] == "SKIPPED"
                    or any(i["type"] == "judge_error" for i in side["issues"]))
    for side, video in (("a", va), ("b", vb)):
        v = judge.assess(video, prompt, shot_id=1)
        out[side].update({"verdict": v.verdict, "score": v.score,
                          "issues": [{"type": i.type, "detail": i.detail} for i in v.issues],
                          "frames": v.frames})
    out["summary"] = {
        "a_score": out["a"]["score"], "b_score": out["b"]["score"],
        "delta_b_minus_a": round(out["b"]["score"] - out["a"]["score"], 3),
        "judged": _judged(out["a"]) and _judged(out["b"]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2))
    print(json.dumps(out["summary"]))
    return 0 if out["summary"]["judged"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
