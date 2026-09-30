"""CLI fixes: multi-shot TODO prompts, non-finite durations, --json failures, help text."""
import json

import pytest

from open_video.cli import open_video as cli


@pytest.mark.parametrize("value", ["nan", "inf", "-inf", "0"])
def test_non_finite_or_zero_duration_exits_2(value, capsys):
    rc = cli.main(["x", f"--duration={value}", "--dry-run"])
    assert rc == 2
    assert "--duration must be a finite number > 0" in capsys.readouterr().err


def test_multishot_todo_prompts_fail_fast_without_engine(monkeypatch, capsys):
    def boom(*a, **k):
        raise AssertionError("engine must not be touched")
    monkeypatch.setattr(cli, "load_engine", boom)
    rc = cli.main(["a cat", "--duration", "40"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "[open-video] error:" in err and "needs an LLM" in err


def test_multishot_todo_prompts_dry_run_still_ok(capsys):
    rc = cli.main(["a cat", "--duration", "40", "--dry-run"])
    assert rc == 0
    assert "template prompts" in capsys.readouterr().err


def test_json_on_unreachable_comfyui(tmp_path, capsys):
    rc = cli.main(["a cat", "--server", "http://127.0.0.1:1", "--json",
                   "--output", str(tmp_path / "f.mp4")])
    assert rc == 3
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is False and payload["exit_code"] == 3
    assert "not reachable" in payload["error"]
    assert payload["shots"] and "verdict" in payload["shots"][0]


def test_json_on_no_film(tmp_path, monkeypatch, capsys):
    class Eng:
        def health(self):
            return True

    class Pipe:
        def __init__(self, *a, **k):
            pass

        def make_film(self, shots, out_path):
            shots[0].verdict = "FAIL"
            shots[0].receipt = {"error": "boom"}
            return None, None

    monkeypatch.setattr(cli, "load_engine", lambda *a, **k: Eng())
    monkeypatch.setattr(cli, "_bind_engine", lambda *a, **k: None)
    monkeypatch.setattr("open_video.core.pipeline.LongFilmPipeline", Pipe)
    rc = cli.main(["a cat", "--json", "--output", str(tmp_path / "f.mp4")])
    assert rc == 4
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is False and payload["exit_code"] == 4
    assert payload["shots"][0]["verdict"] == "FAIL"
    assert payload["shots"][0]["error"] == "boom"


def test_top_level_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for sub in cli.SUBCOMMANDS:
        assert sub in out
    assert 'open-video run "status"' in out


def test_run_accepts_subcommand_word_as_prompt(capsys):
    rc = cli.main(["run", "status", "--dry-run"])
    assert rc == 0
    assert "[open-video] [5/5] done (dry-run)" in capsys.readouterr().out


def test_pull_models_dir_help_states_resolution_order(capsys):
    with pytest.raises(SystemExit):
        cli.main(["pull", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "OPEN_VIDEO_MODELS, $OPEN_VIDEO_LAB/h3_models, OPEN_VIDEO_HOME, ../lab/h3_models" in out
