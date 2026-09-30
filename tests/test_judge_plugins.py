"""Judge plugin discovery: broken plugins must be visible, not silently absent.

A plugin that raises during import or instantiation is excluded from JUDGES,
but the failure lands in JUDGE_ERRORS and on stderr — otherwise a typo'd
plugin simply vanishes and quality assessment quietly runs without it.
"""
import importlib
import pkgutil

import open_video.judges as judges_pkg
from open_video.core.judge import QualityJudge


def test_judges_registry_holds_only_judge_instances():
    assert judges_pkg.JUDGES, "at least the built-in vision judge should load"
    assert all(isinstance(j, QualityJudge) for j in judges_pkg.JUDGES.values())
    assert judges_pkg.JUDGE_ERRORS == {}


def test_plugin_load_failure_is_recorded_and_warned(monkeypatch, capsys):
    real_import = importlib.import_module

    def fake_iter_modules(_path):
        yield (None, "vision", None)
        yield (None, "broken_plugin", None)

    def fake_import(name):
        if name.endswith("broken_plugin"):
            raise RuntimeError("import boom")
        return real_import(name)

    monkeypatch.setattr(pkgutil, "iter_modules", fake_iter_modules)
    monkeypatch.setattr(importlib, "import_module", fake_import)
    try:
        importlib.reload(judges_pkg)

        assert "vision" in judges_pkg.JUDGES
        assert all(isinstance(j, QualityJudge) for j in judges_pkg.JUDGES.values())
        assert judges_pkg.JUDGE_ERRORS["broken_plugin"] == {
            "status": "failed", "error": "import boom"}
        err = capsys.readouterr().err
        assert "judge plugin 'broken_plugin' failed to load" in err
        assert "import boom" in err
    finally:
        monkeypatch.undo()
        importlib.reload(judges_pkg)


def test_plugin_instantiation_failure_is_recorded(monkeypatch, capsys):
    """A Judge class whose constructor raises is reported, not swallowed."""
    real_import = importlib.import_module

    def fake_iter_modules(_path):
        yield (None, "vision", None)
        yield (None, "angry_plugin", None)

    class _AngryModule:
        class Judge:
            id = "angry"

            def __init__(self):
                raise RuntimeError("no VLM credentials")

    def fake_import(name):
        if name.endswith("angry_plugin"):
            return _AngryModule
        return real_import(name)

    monkeypatch.setattr(pkgutil, "iter_modules", fake_iter_modules)
    monkeypatch.setattr(importlib, "import_module", fake_import)
    try:
        importlib.reload(judges_pkg)

        assert "angry" not in judges_pkg.JUDGES
        assert judges_pkg.JUDGE_ERRORS["angry_plugin"]["error"] == "no VLM credentials"
        assert "angry_plugin" in capsys.readouterr().err
    finally:
        monkeypatch.undo()
        importlib.reload(judges_pkg)
