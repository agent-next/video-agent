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


def test_release_installs_ffmpeg_before_tests():
    text = WORKFLOW.read_text()
    assert "apt-get install -y -qq --no-install-recommends ffmpeg" in text
    assert text.index("apt-get install") < text.index("python -m pytest")


def test_release_checks_tag_against_pyproject_version():
    text = WORKFLOW.read_text()
    assert '"$GITHUB_REF_NAME"' in text
    assert 'tomllib.load(open("pyproject.toml","rb"))["project"]["version"]' in text
    assert text.index("GITHUB_REF_NAME\"") < text.index("python -m pytest")


def test_release_body_is_only_the_matching_changelog_section():
    text = WORKFLOW.read_text()
    assert "body_path: CHANGELOG.md" not in text
    assert "body_path: release-body.md" in text
    assert text.index("> release-body.md") < text.index("Create GitHub Release")
    assert "has no section for" in text


def test_ci_cancels_only_pull_request_runs():
    ci = WORKFLOW.with_name("ci.yml").read_text()
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in ci
