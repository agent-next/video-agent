"""ComfyUIAdapter.wait/fetch_outputs survive transient network errors (no real server)."""
import json
import urllib.error

from open_video.engines.comfyui.adapter import ComfyUIAdapter

DONE = {"pid": {"status": {"status_str": "success"}}}


def _adapter(tmp_path, monkeypatch, errors):
    a = ComfyUIAdapter(output_dir=str(tmp_path))
    calls = {"n": 0}

    def fake_json(url, data=None, timeout=30):
        calls["n"] += 1
        if calls["n"] <= len(errors):
            raise errors[calls["n"] - 1]
        return DONE

    monkeypatch.setattr(a, "_json", fake_json)
    monkeypatch.setattr("time.sleep", lambda s: None)
    return a, calls


def test_wait_survives_urlerror_then_succeeds(tmp_path, monkeypatch):
    a, calls = _adapter(tmp_path, monkeypatch,
                        [urllib.error.URLError("refused"), urllib.error.URLError("reset")])
    assert a.wait("pid", timeout=60, poll=0.0) == {"status_str": "success"}
    assert calls["n"] == 3


def test_wait_survives_oserror_and_bad_json(tmp_path, monkeypatch):
    a, _ = _adapter(tmp_path, monkeypatch,
                    [ConnectionResetError(), TimeoutError(), json.JSONDecodeError("m", "d", 0)])
    assert a.wait("pid", timeout=60, poll=0.0)["status_str"] == "success"


def test_wait_times_out_when_always_failing(tmp_path, monkeypatch):
    a = ComfyUIAdapter(output_dir=str(tmp_path))

    def always(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(a, "_json", always)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr("time.time", lambda: next(clock))
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert a.wait("pid", timeout=50, poll=0.0) == {"status_str": "timeout"}


def test_fetch_outputs_returns_empty_on_urlerror(tmp_path, monkeypatch):
    a = ComfyUIAdapter(output_dir=str(tmp_path))

    def boom(*args, **kwargs):
        raise urllib.error.URLError("down")

    monkeypatch.setattr(a, "_json", boom)
    assert a.fetch_outputs("pid") == []
