"""Backend discovery failure reporting: causes must reach the user.

A backend that fails to import or instantiate is omitted from discovery; the
cause must be returned structurally so CLI commands and the bench harness can
explain why a model is missing instead of silently dropping it.
"""
import types

import pytest

from cli import open_video as cli


def _broken_backend_dir(tmp_path):
    backends = tmp_path / "backends"
    broken = backends / "broken"
    broken.mkdir(parents=True)
    (broken / "backend.py").write_text("raise RuntimeError('missing dependency')\n")
    return backends


def test_discover_backends_no_backends_dir_returns_empty_pair(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)

    found, errors = cli.discover_backends()

    assert found == []
    assert errors == []


def test_discover_backends_reports_import_failure(monkeypatch, tmp_path):
    _broken_backend_dir(tmp_path)

    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda _: (_ for _ in ()).throw(RuntimeError("missing dependency")),
    )

    found, errors = cli.discover_backends()

    assert found == []
    assert errors == [{
        "backend": "broken",
        "stage": "import",
        "cause": "missing dependency",
    }]


def test_discover_backends_reports_instantiate_failure(monkeypatch, tmp_path):
    """A backend class whose constructor raises is reported, not swallowed."""
    from open_video.core.backend import ModelBackend

    class ExplodingBackend(ModelBackend):
        id = "broken"
        display_name = "Broken"

        def __init__(self):
            raise RuntimeError("no weights manifest")

    mod = types.ModuleType("open_video.backends.broken.backend")
    mod.Broken = ExplodingBackend
    ExplodingBackend.__module__ = mod.__name__  # pass the defined-here guard

    _broken_backend_dir(tmp_path)
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(cli.importlib, "import_module", lambda _: mod)

    found, errors = cli.discover_backends()

    assert found == []
    assert errors == [{
        "backend": "broken",
        "stage": "instantiate",
        "cause": "no weights manifest",
    }]


def test_load_backend_unknown_model_reports_discovery_failures(monkeypatch, tmp_path):
    """KeyError for an unknown model must name the backends that failed to load."""
    _broken_backend_dir(tmp_path)

    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        cli.importlib,
        "import_module",
        lambda _: (_ for _ in ()).throw(RuntimeError("missing dependency")),
    )

    with pytest.raises(KeyError) as excinfo:
        cli.load_backend("nope")

    msg = str(excinfo.value)
    assert "nope" in msg
    assert "discovery failures" in msg
    assert "broken" in msg and "missing dependency" in msg
