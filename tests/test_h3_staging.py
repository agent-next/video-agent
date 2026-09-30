"""H3 reference-frame staging + engine-success-without-output handling.

The i2v/flf2v path copies continuity frames into ComfyUI's input/ dir. That dir
must resolve absolutely (OPEN_VIDEO_COMFYUI_INPUT → lab/runtime layout → repo
ComfyUI/input, never the caller's CWD), staged filenames must be unique per run,
and the workflow must reference the file actually written. Missing/unreadable
refs and unusable staging dirs fail loudly before any workflow is submitted.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from open_video.backends.h3.backend import H3Backend, resolve_comfy_input
from open_video.core.backend import ShotRequest

ENV_VARS = ("OPEN_VIDEO_COMFYUI_INPUT", "OPEN_VIDEO_COMFYUI_DIR",
            "OPEN_VIDEO_LAB", "H3_LAB")
FF_BYTES = b"\x89PNG\r\n\x1a\n fake-first"
LF_BYTES = b"\x89PNG\r\n\x1a\n fake-last"


class _CaptureEngine:
    """Engine stub: records the submitted workflow, replies with a canned result."""

    id = "capture"

    def __init__(self, outputs=("/tmp/clip.mp4",)):
        self.workflow = None
        self.outputs = list(outputs)

    def submit_and_wait(self, workflow, timeout=1800, save_node="save_video"):
        self.workflow = workflow
        return {"prompt_id": "p1", "status": {"status_str": "success"},
                "outputs": self.outputs}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _req(tmp_path, mode="i2v", seed=42, first=True, last=False):
    ff = tmp_path / "ff.png"
    lf = tmp_path / "lf.png"
    if first:
        ff.write_bytes(FF_BYTES)
    if last:
        lf.write_bytes(LF_BYTES)
    return ShotRequest(prompt="p", mode=mode, width=64, height=36, duration_s=2.0,
                       seed=seed,
                       first_frame=str(ff) if first else None,
                       last_frame=str(lf) if last else None)


def test_staging_dir_is_absolute_not_cwd_relative(tmp_path, monkeypatch):
    """Frames land in the configured ComfyUI input dir, not under the CWD."""
    staging = tmp_path / "lab" / "ComfyUI" / "input"
    staging.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(staging))
    monkeypatch.chdir(elsewhere)

    assert resolve_comfy_input() == staging.resolve()

    engine = _CaptureEngine()
    res = H3Backend().generate(_req(tmp_path), engine=engine)

    assert res.ok, res.error
    assert not (elsewhere / "ComfyUI").exists(), "must not stage relative to the CWD"
    staged = list(staging.iterdir())
    assert len(staged) == 1 and staged[0].name.startswith("ov_ff_42_")
    assert staged[0].read_bytes() == FF_BYTES
    assert engine.workflow["load_firstframe"]["inputs"]["image"] == staged[0].name


def test_lab_layout_resolution_and_mkdir(tmp_path, monkeypatch):
    """$OPEN_VIDEO_LAB/ComfyUI exists but input/ doesn't → input/ created there."""
    comfy = tmp_path / "lab" / "ComfyUI"
    comfy.mkdir(parents=True)
    monkeypatch.setenv("OPEN_VIDEO_LAB", str(tmp_path / "lab"))

    assert resolve_comfy_input() == (comfy / "input").resolve()

    engine = _CaptureEngine()
    res = H3Backend().generate(_req(tmp_path), engine=engine)
    assert res.ok, res.error
    staged = list((comfy / "input").iterdir())
    assert len(staged) == 1 and staged[0].read_bytes() == FF_BYTES


@pytest.mark.parametrize("var", ["OPEN_VIDEO_COMFYUI_DIR", "OPEN_VIDEO_LAB", "H3_LAB"])
def test_invalid_explicit_runtime_does_not_fall_back(tmp_path, monkeypatch, var):
    from open_video.backends.h3 import backend as module
    fallback = tmp_path / "product" / "ComfyUI"
    fallback.mkdir(parents=True)
    monkeypatch.setattr(module, "REPO_ROOT", fallback.parent)
    monkeypatch.setenv(var, str(tmp_path / "missing-runtime"))
    engine = _CaptureEngine()
    result = H3Backend().generate(_req(tmp_path), engine=engine)
    assert not result.ok
    assert var in result.error
    assert engine.workflow is None
    assert not (fallback / "input").exists()


def test_staged_filename_is_unique_per_run(tmp_path, monkeypatch):
    """Two runs never collide on a hardcoded firstframe.png-style name."""
    staging = tmp_path / "input"
    staging.mkdir()
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(staging))
    backend = H3Backend()
    names = set()
    for _ in range(2):
        engine = _CaptureEngine()
        assert backend.generate(_req(tmp_path), engine=engine).ok
        names.add(engine.workflow["load_firstframe"]["inputs"]["image"])
    assert len(names) == 2 and len(list(staging.iterdir())) == 2


def test_flf2v_stages_both_refs(tmp_path, monkeypatch):
    """flf2v stages first+last frames and the workflow references both."""
    staging = tmp_path / "input"
    staging.mkdir()
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(staging))

    engine = _CaptureEngine()
    res = H3Backend().generate(_req(tmp_path, mode="flf2v", last=True), engine=engine)

    assert res.ok, res.error
    wf = engine.workflow
    ff_ref = wf["load_firstframe"]["inputs"]["image"]
    lf_ref = wf["load_lastframe"]["inputs"]["image"]
    assert ff_ref != lf_ref
    assert (staging / ff_ref).read_bytes() == FF_BYTES
    assert (staging / lf_ref).read_bytes() == LF_BYTES
    assert wf["h3_i2v"]["inputs"]["last_frame"] == ["load_lastframe", 0]


def test_i2v_without_first_frame_fails_loudly(tmp_path, monkeypatch):
    """i2v with no frame must fail before staging/submitting."""
    staging = tmp_path / "input"
    staging.mkdir()
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(staging))
    engine = _CaptureEngine()

    res = H3Backend().generate(_req(tmp_path, mode="i2v", first=False), engine=engine)

    assert not res.ok and "first_frame" in res.error
    assert engine.workflow is None and not list(staging.iterdir())


def test_flf2v_without_last_frame_fails_loudly(tmp_path, monkeypatch):
    """flf2v missing last_frame must fail — never silently degrade to i2v."""
    staging = tmp_path / "input"
    staging.mkdir()
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(staging))
    engine = _CaptureEngine()

    res = H3Backend().generate(_req(tmp_path, mode="flf2v", last=False), engine=engine)

    assert not res.ok and "last_frame" in res.error
    assert engine.workflow is None and not list(staging.iterdir())


def test_unreadable_ref_fails_loudly(tmp_path, monkeypatch):
    """A first_frame path that isn't a readable file fails before submit."""
    staging = tmp_path / "input"
    staging.mkdir()
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(staging))
    req = ShotRequest(prompt="p", mode="i2v", width=64, height=36, duration_s=2.0,
                      seed=1, first_frame=str(tmp_path / "ghost.png"))
    engine = _CaptureEngine()

    res = H3Backend().generate(req, engine=engine)

    assert not res.ok and "not readable" in res.error
    assert engine.workflow is None and not list(staging.iterdir())


def test_unresolvable_staging_dir_fails_loudly(tmp_path, monkeypatch):
    """Explicit env pointing at a non-dir → failed ShotResult, no mkdir, no submit."""
    missing = tmp_path / "nope" / "input"
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(missing))
    monkeypatch.chdir(tmp_path)
    engine = _CaptureEngine()

    res = H3Backend().generate(_req(tmp_path), engine=engine)

    assert not res.ok
    assert "OPEN_VIDEO_COMFYUI_INPUT" in res.error
    assert engine.workflow is None, "must not submit a workflow with an unstaged frame"
    assert not missing.exists() and not (tmp_path / "ComfyUI").exists()


def test_no_runtime_anywhere_fails_loudly(tmp_path, monkeypatch):
    """No env + no lab + no repo ComfyUI → error, never a silent wrong-dir mkdir."""
    from open_video.backends.h3 import backend as module
    monkeypatch.setattr(module, "REPO_ROOT", tmp_path / "repo" / "pkg")
    for var in ("OPEN_VIDEO_COMFYUI_INPUT", "OPEN_VIDEO_COMFYUI_DIR", "OPEN_VIDEO_LAB", "H3_LAB"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.chdir(tmp_path)
    engine = _CaptureEngine()

    res = H3Backend().generate(_req(tmp_path), engine=engine)

    assert not res.ok and "OPEN_VIDEO_COMFYUI_INPUT" in res.error
    assert engine.workflow is None
    assert not (tmp_path / "ComfyUI").exists()


def test_input_path_blocked_by_file_fails(tmp_path, monkeypatch):
    """lab/ComfyUI exists but input is a file → mkdir fails with actionable error."""
    comfy = tmp_path / "lab" / "ComfyUI"
    comfy.mkdir(parents=True)
    (comfy / "input").write_text("not a dir")
    monkeypatch.setenv("OPEN_VIDEO_LAB", str(tmp_path / "lab"))
    engine = _CaptureEngine()

    res = H3Backend().generate(_req(tmp_path), engine=engine)

    assert not res.ok and "staging" in res.error
    assert engine.workflow is None


def test_t2v_does_not_touch_the_staging_dir(tmp_path, monkeypatch):
    """t2v needs no reference frame — an absent staging dir must not break it."""
    monkeypatch.setenv("OPEN_VIDEO_COMFYUI_INPUT", str(tmp_path / "absent"))
    monkeypatch.chdir(tmp_path)
    req = ShotRequest(prompt="p", mode="t2v", width=64, height=36, duration_s=2.0, seed=1)

    res = H3Backend().generate(req, engine=_CaptureEngine())

    assert res.ok, res.error
    assert not (tmp_path / "ComfyUI").exists()
    assert res.receipt["model"] == "minimax-h3"
    assert res.receipt["seed"] == req.seed
    assert (res.receipt["width"], res.receipt["height"]) == (64, 36)
    assert res.receipt["duration_s"] == H3Backend().duration_to_length(2.0) / 24


def test_success_with_no_outputs_is_a_failure(tmp_path):
    """Engine says success but returned no file → failed ShotResult, never ok+None."""
    req = ShotRequest(prompt="p", mode="t2v", width=64, height=36, duration_s=2.0, seed=1)

    res = H3Backend().generate(req, engine=_CaptureEngine(outputs=()))

    assert not res.ok and res.video_path is None
    assert "no video" in res.error
    assert res.receipt["prompt_id"] == "p1"


def test_r2v_not_advertised_and_rejected():
    """r2v has no workflow — capabilities must not claim it, generate must refuse."""
    assert H3Backend().capabilities.r2v is False
    req = ShotRequest(prompt="p", mode="r2v", width=64, height=36, duration_s=2.0, seed=1)
    res = H3Backend().generate(req, engine=_CaptureEngine())
    assert not res.ok and "unsupported" in res.error
