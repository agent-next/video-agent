"""The tag-triggered release workflow must build, smoke test, and ship wheels.

The v0.1.0 wheel/sdist were attached by hand; these tests pin the workflow so
future tags produce and attach verified artifacts automatically.
"""
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release.yml"


def test_release_workflow_builds_are_required():
    text = WORKFLOW.read_text()
    assert "python -m build" in text
    assert "continue-on-error: true" not in text


def test_release_wheel_smoke_runs_outside_checkout():
    # `python -m` prepends cwd to sys.path; running from the repo root would
    # import the source tree instead of the installed wheel.
    text = WORKFLOW.read_text()
    assert "pip install dist/*.whl" in text
    assert "python -m open_video --help" in text
    # --help exits before any packaged data is read; these need library/ and backends.
    assert "python -m open_video list-models" in text
    assert "python -m open_video list-presets" in text
    assert "cd /tmp" in text
    assert "assert 'site-packages' in open_video.__file__" in text


def test_release_workflow_smoke_precedes_release_step():
    text = WORKFLOW.read_text()
    smoke = text.index("Install wheel smoke test")
    release = text.index("Create GitHub Release")
    assert smoke < release, "wheel must be smoke tested before publishing"


def test_release_uploads_built_artifacts():
    assert "files: dist/*" in WORKFLOW.read_text()
