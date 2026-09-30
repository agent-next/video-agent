"""open-video judge plugins — community-contributed quality assessors.

Each judge implements the QualityJudge interface from core/judge.py. Plugins:
- vision.py: VLM-based judge (calls a vision model on extracted frames)
- (future) videoscore.py: TIGER-AI-Lab VideoScore integration
- (future) human.py: human-in-the-loop judge
- (future) tournament.py: best-of-N tournament judge

Auto-discovery: drop a .py file in judges/ implementing QualityJudge → it's available.
"""
import importlib, pkgutil, sys
from open_video.core.judge import QualityJudge

JUDGES = {}
JUDGE_ERRORS = {}
for _, name, _ in pkgutil.iter_modules(__path__):
    try:
        mod = importlib.import_module(f"{__name__}.{name}")
        if hasattr(mod, "Judge"):
            JUDGES[mod.Judge.id] = mod.Judge()
    except Exception as exc:
        # graceful: broken plugins don't crash the system — but the cause is
        # recorded (JUDGE_ERRORS) and warned so a missing judge is debuggable
        # instead of silently absent from JUDGES.
        JUDGE_ERRORS[name] = {"status": "failed", "error": str(exc)}
        print(f"[open-video] warning: judge plugin '{name}' failed to load: {exc}",
              file=sys.stderr)
