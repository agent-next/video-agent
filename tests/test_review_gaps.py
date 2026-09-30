"""Reviewer-gap regressions: pin CURRENT behavior of reviewed seams.

Covers: the ModelBackend contract, _bind_engine (both signature paths),
H3 LoRA workflow insertion, list-models --json output, plugin import
failure diagnostics, and the ComfyUI output download path.
"""
import importlib
import inspect
import json
import urllib.request
from pathlib import Path

import pytest

from cli import open_video as cli
from open_video.backends.h3.backend import H3Backend
from open_video.core.backend import ModelBackend, ShotRequest, ShotResult
from open_video.engines.comfyui.adapter import ComfyUIAdapter


def _req(**kw):
    base = {"prompt": "waves at dusk", "mode": "t2v", "width": 1344,
            "height": 768, "duration_s": 5.0, "seed": 42}
    base.update(kw)
    return ShotRequest(**base)


class _FakeEngine:
    id = "fake"

    def __init__(self):
        self.workflows = []

    def submit_and_wait(self, workflow, timeout=1800, save_node="save_video"):
        self.workflows.append(workflow)
        return {"prompt_id": "p1", "status": {"status_str": "success"},
                "outputs": ["/tmp/ov_fake.mp4"]}


def test_backend_contract_unimplemented_methods_raise():
    b = ModelBackend()
    with pytest.raises(NotImplementedError):
        b.prompt_guide()
    with pytest.raises(NotImplementedError):
        b.craft_prompt({}, "t2v")
    with pytest.raises(NotImplementedError):
        b.generate(_req())
    with pytest.raises(NotImplementedError):
        b.duration_to_length(5.0)
    with pytest.raises(NotImplementedError):
        b.resolution_for("16:9")
    assert b.constraints() == {}
    assert b.default_settings() == {}


def test_bind_engine_injects_engine_only_when_backend_accepts_it():
    class _WithEngine(ModelBackend):
        id = "with-engine"

        def __init__(self):
            self.seen = None

        def generate(self, req, engine=None):
            self.seen = engine
            return ShotResult(ok=True, video_path="y")

    class _WithoutEngine(ModelBackend):
        id = "without-engine"

        def generate(self, req):
            return ShotResult(ok=True, video_path="z")

    sentinel = object()
    a = _WithEngine()
    cli._bind_engine(a, sentinel)
    assert a.generate(_req()).video_path == "y"
    assert a.seen is sentinel

    b = _WithoutEngine()
    cli._bind_engine(b, sentinel)
    assert list(inspect.signature(b.generate).parameters) == ["req"]
    assert b.generate(_req()).video_path == "z"


def test_h3_generate_inserts_lora_into_workflow():
    b = H3Backend()
    eng = _FakeEngine()
    res = b.generate(_req(lora="cinematic-v2.safetensors", lora_weight=0.8),
                     engine=eng)
    assert res.ok is True
    assert res.video_path == "/tmp/ov_fake.mp4"
    assert res.receipt["prompt_id"] == "p1"
    assert res.receipt["engine"] == "fake"
    wf = eng.workflows[0]
    assert wf["lora_loader"]["class_type"] == "LoraLoader"
    assert wf["lora_loader"]["inputs"]["lora_name"] == "cinematic-v2.safetensors"
    assert wf["lora_loader"]["inputs"]["strength_model"] == 0.8
    assert wf["lora_loader"]["inputs"]["model"] == ["load_unet", 0]
    assert wf["lora_loader"]["inputs"]["clip"] == ["load_clip", 0]
    assert wf["sigmashift"]["inputs"]["model"] == ["lora_loader", 0]
    assert wf["h3_i2v"]["inputs"]["prompt"] == "waves at dusk"
    assert wf["h3_i2v"]["inputs"]["length"] == b.duration_to_length(5.0)

    res2 = b.generate(_req(), engine=eng)
    assert res2.ok is True
    wf2 = eng.workflows[1]
    assert "lora_loader" not in wf2
    assert wf2["sigmashift"]["inputs"]["model"] == ["load_unet", 0]


def test_list_models_json_serializable(capsys):
    rc = cli.main(["list-models", "--json"])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert isinstance(rows, list) and rows
    assert all(set(r) == {"alias", "id", "display", "modes", "max_s"}
               for r in rows)
    h3 = next(r for r in rows if r["alias"] == "h3")
    assert h3["id"] == "minimax-h3"
    assert set(h3["modes"].split("/")) == {"t2v", "i2v", "flf2v"}
    assert h3["max_s"] == 15.0


def test_plugin_import_failure_is_diagnostic(tmp_path, capsys, monkeypatch):
    (tmp_path / "backends" / "broken").mkdir(parents=True)
    (tmp_path / "backends" / "broken" / "backend.py").write_text("# broken\n")
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    real_import_module = importlib.import_module

    def fake_import_module(name, *args, **kwargs):
        if name == "open_video.backends.broken.backend":
            raise ImportError("missing dependency 'fake-dep'")
        return real_import_module(name, *args, **kwargs)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)
    found, errors = cli.discover_backends()
    assert found == []
    assert errors == [{"backend": "broken", "stage": "import",
                       "cause": "missing dependency 'fake-dep'"}]

    # the failure stays user-visible through the CLI surface
    rc = cli.main(["list-models"])
    err = capsys.readouterr().err
    assert rc == 0
    assert "backend discovery failures" in err
    assert "broken" in err and "missing dependency 'fake-dep'" in err


def test_comfy_fetch_outputs_downloads_saved_files(tmp_path, monkeypatch):
    adapter = ComfyUIAdapter(server="http://127.0.0.1:9",
                             output_dir=str(tmp_path / "out"))
    history = {"p1": {"outputs": {"save_video": {
        "videos": [{"filename": "ov_t2v_1.mp4", "subfolder": ""}]}}}}
    monkeypatch.setattr(adapter, "_json",
                        lambda url, data=None, timeout=30: history)
    urls = []

    def fake_retrieve(url, dest):
        urls.append(url)
        Path(dest).write_bytes(b"FAKEVIDEO")

    monkeypatch.setattr(urllib.request, "urlretrieve", fake_retrieve)

    saved = adapter.fetch_outputs("p1")

    assert urls == ["http://127.0.0.1:9/view?filename=ov_t2v_1.mp4"
                    "&subfolder=&type=output"]
    assert len(saved) == 1
    p = Path(saved[0])
    assert p.parent == adapter.output_dir
    prefix, rest = p.name.split("_", 1)
    assert prefix.isdigit()
    assert rest == "ov_t2v_1.mp4"
    assert p.read_bytes() == b"FAKEVIDEO"
