"""H3 settings profiles — the OpenVDN DMD8 (8-NFE) variant.

vdn_dmd8 selects the h3_t2v_vdn workflow: same pruned INT8/ConvRot base, but the
T8 VDN composer applies the OpenVDN stage_dmd_8nfe branch+adapters and the plan
node owns sampler/sigmas (8 NFE, shifts 12/3). These tests pin that contract:
profile selection, workflow shape, injection points, LoRA refusal and the
default path staying untouched.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from open_video.backends.h3.backend import H3Backend
from open_video.core.backend import ShotRequest


class _RecordingEngine:
    """Engine double: captures the workflow the backend submits."""

    def __init__(self):
        self.id = "fake"
        self.wf = None

    def submit_and_wait(self, wf, timeout=1800, save_node=None):
        self.wf = wf
        return {"status": {"status_str": "success"}, "prompt_id": "spy-1",
                "outputs": ["/tmp/ov_spy.mp4"]}


def _req(**kw):
    base = dict(prompt="a test pattern", mode="t2v", width=960,
                height=544, duration_s=5.0, seed=42)
    base.update(kw)
    return ShotRequest(**base)


def test_profiles_advertised():
    profiles = H3Backend().settings_profiles()
    assert set(profiles) >= {"default", "vdn_dmd8"}
    assert profiles["default"]["steps"] == 20
    assert profiles["vdn_dmd8"]["steps"] == 8
    assert profiles["vdn_dmd8"]["modes"] == ("t2v",)
    assert profiles["vdn_dmd8"]["no_lora_stacking"] is True
    assert "territory excludes" in profiles["vdn_dmd8"]["license_note"]


def test_vdn_profile_builds_vdn_workflow():
    engine = _RecordingEngine()
    res = H3Backend().generate(_req(extra={"settings_profile": "vdn_dmd8"}), engine=engine)
    assert res.ok, res.error
    wf = engine.wf
    assert wf["vdn_composer"]["class_type"] == "MiniMaxH3VDNModelComposerT8Advanced"
    comp = wf["vdn_composer"]["inputs"]
    assert comp["stage"] == "stage_dmd_8nfe"
    assert comp["allow_structural_base"] is True  # required for the INT8/ConvRot base
    assert comp["verify_hashes"] is True
    # plan node owns sampler/sigmas — no classic sigmashift/scheduler nodes to touch
    assert "sigmashift" not in wf and "scheduler" not in wf
    assert wf["plan"]["inputs"]["model"] == ["vdn_composer", 0]
    # shared injection points still work
    assert wf["h3_i2v"]["inputs"]["prompt"] == "a test pattern"
    assert wf["h3_i2v"]["inputs"]["task_type"] == "T2VA"
    assert wf["noise"]["inputs"]["noise_seed"] == 42
    assert res.receipt["steps"] == 8


def test_default_profile_unchanged():
    engine = _RecordingEngine()
    res = H3Backend().generate(_req(), engine=engine)
    assert res.ok, res.error
    wf = engine.wf
    assert "vdn_composer" not in wf
    assert wf["sigmashift"]["inputs"]["shift_video"] == 12.0
    assert wf["scheduler"]["inputs"]["steps"] == 20
    assert res.receipt["steps"] == 20


def test_vdn_rejects_lora():
    res = H3Backend().generate(
        _req(extra={"settings_profile": "vdn_dmd8"}, lora="style.safetensors"), engine=_RecordingEngine())
    assert not res.ok
    assert "LoRA" in res.error


def test_vdn_rejects_unsupported_mode():
    res = H3Backend().generate(
        _req(mode="flf2v", extra={"settings_profile": "vdn_dmd8"}), engine=_RecordingEngine())
    assert not res.ok
    assert "does not support mode" in res.error


def test_unknown_profile_named_in_error():
    res = H3Backend().generate(_req(extra={"settings_profile": "nope"}), engine=_RecordingEngine())
    assert not res.ok
    assert "nope" in res.error and "vdn_dmd8" in res.error


def test_vdn_workflow_file_only_known_assets():
    wf = json.loads((Path(__file__).parent.parent /
                     "backends/h3/workflows/h3_t2v_vdn_api.json").read_text())
    # base/text-encoder/VAEs identical to the proven default profile's assets
    assert wf["load_unet"]["inputs"]["unet_name"] == "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    assert wf["load_clip"]["inputs"]["clip_name"] == "qwen3vl_32b_minimax_h3_int8_convrot.safetensors"
    assert wf["load_clip"]["inputs"]["type"] == "minimax"
    # every model link resolves to a node that exists in the graph
    for node in wf.values():
        for v in node.get("inputs", {}).values():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                assert v[0] in wf, f"dangling link {v} in {node['class_type']}"
