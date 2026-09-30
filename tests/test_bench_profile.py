"""Tests for benchmark resume behavior + backend discovery error reporting."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from bench.profile import is_complete  # noqa: E402


def test_is_complete_requires_existing_video_artifact(tmp_path):
    video = tmp_path / "result.mp4"
    entry = {
        "status": "ok",
        "wall_s": 12.5,
        "video_path": str(video),
    }

    assert is_complete(entry) is False

    video.write_bytes(b"fake-video")
    assert is_complete(entry) is True


# --- backend discovery error reporting (discover_backends returns pairs) ------

def _load_profile():
    spec = importlib.util.spec_from_file_location(
        "bench_profile_under_test", REPO / "bench" / "profile.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeBackend:
    id = "fake"
    display_name = "Fake Backend"


def test_bench_list_models_reports_discovery_errors(monkeypatch, capsys):
    profile = _load_profile()
    errors = [{"backend": "broken", "stage": "import",
               "cause": "missing dependency"}]
    fake_cli = types.SimpleNamespace(
        discover_backends=lambda: ([("fake", _FakeBackend())], errors))
    monkeypatch.setattr(profile, "_load_cli", lambda: fake_cli)

    rc = profile.main(["--list-models"])

    assert rc == 0
    captured = capsys.readouterr()
    assert "fake" in captured.out
    assert "broken" in captured.err
    assert "missing dependency" in captured.err


def test_bench_unknown_model_reports_discovery_errors(monkeypatch, capsys):
    profile = _load_profile()
    errors = [{"backend": "broken", "stage": "import",
               "cause": "missing dependency"}]

    def fake_load_backend(model_id):
        # mirrors cli.load_backend: discovery failures ride in the KeyError
        detail = "; ".join(f"{e['backend']}/{e['stage']}: {e['cause']}" for e in errors)
        raise KeyError(f"model '{model_id}' not found; backend discovery failures: {detail}")

    fake_cli = types.SimpleNamespace(
        load_backend=fake_load_backend,
        discover_backends=lambda: ([], errors))
    monkeypatch.setattr(profile, "_load_cli", lambda: fake_cli)

    rc = profile.main(["--model", "nope", "--gpu", "0"])

    assert rc == 2
    captured = capsys.readouterr()
    assert "broken" in captured.err
    assert "missing dependency" in captured.err
