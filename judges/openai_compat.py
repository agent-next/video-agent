"""OpenAI-compatible VLM client — the default real ``vision_fn`` for QualityJudge.

Stdlib only (urllib), same policy as the rest of the runtime. Activated by env:

    OPEN_VIDEO_VLM_URL     chat-completions endpoint, e.g.
                           https://integrate.api.nvidia.com/v1/chat/completions
                           http://127.0.0.1:8000/v1/chat/completions
    OPEN_VIDEO_VLM_MODEL   a vision-capable chat model id
    OPEN_VIDEO_VLM_KEY     bearer token (optional for local servers)

With URL+MODEL set, ``QualityJudge.from_env()`` judges for real; without them the
judge reports an honest SKIPPED verdict (score 0.0), never a fake PASS.
"""
from __future__ import annotations

import base64
import json
import os

from open_video.core.http import post_json

_SYSTEM = (
    "You are a strict video-quality judge. You are shown evenly spaced frames "
    "from one generated video shot plus the prompt that requested it. Reply "
    "with ONLY a JSON object, no prose, using exactly these keys: "
    '{"score": <float 0.0-1.0 overall quality/adherence>, '
    '"missing_elements": [<prompt elements not visible>], '
    '"artifacts": <"" or short description of visual artifacts>, '
    '"motion_quality": <"good"|"acceptable"|"poor" judged from frame-to-frame change>, '
    '"incoherence": <false or short description if frames do not flow>}'
)

_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _frame_part(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    mime = _MIME.get(ext, "image/png")
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _parse_verdict(content: str) -> dict:
    """Extract the JSON verdict object from a model reply (tolerates code fences)."""
    text = content.strip()
    # find/rfind is the fence tolerance: it skips ``` markers and any prose
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"vision model returned no JSON object: {content[:200]!r}")
    out = json.loads(text[start : end + 1])
    if not isinstance(out, dict) or "score" not in out:
        raise ValueError(f"vision verdict missing 'score': {content[:200]!r}")
    out["score"] = float(out["score"])
    return out


def make_vision_fn(url: str, model: str, api_key: str | None = None, timeout: float = 120.0):
    """Build a ``vision_fn(frames, prompt) -> dict`` against an OpenAI-compatible endpoint.

    Failures (HTTP error, non-JSON reply) raise — a judge that cannot judge must
    not silently PASS.
    """

    def vision_fn(frames: list, prompt: str) -> dict:
        content = [
            {
                "type": "text",
                "text": (
                    f"Prompt for this shot:\n{prompt}\n\n"
                    f"The {len(frames)} frames follow in temporal order. Judge the shot."
                ),
            }
        ] + [_frame_part(p) for p in frames]
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": content},
            ],
            "temperature": 0,
            "max_tokens": 512,
        }
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        body = post_json(url, payload, headers=headers, timeout=timeout)
        return _parse_verdict(body["choices"][0]["message"]["content"])

    return vision_fn


def vision_fn_from_env():
    """Return a real vision_fn if OPEN_VIDEO_VLM_URL + OPEN_VIDEO_VLM_MODEL are set, else None."""
    url = os.environ.get("OPEN_VIDEO_VLM_URL", "").strip()
    model = os.environ.get("OPEN_VIDEO_VLM_MODEL", "").strip()
    if not url or not model:
        return None
    raw = os.environ.get("OPEN_VIDEO_VLM_TIMEOUT", "120")
    try:
        timeout = float(raw)
    except ValueError:
        raise RuntimeError(
            f"OPEN_VIDEO_VLM_TIMEOUT must be numeric, got {raw!r}") from None
    return make_vision_fn(url, model, api_key=os.environ.get("OPEN_VIDEO_VLM_KEY") or None,
                          timeout=timeout)
