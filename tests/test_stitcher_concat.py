"""Stitcher.concat with cwd-relative paths; extract_last_frame stale/failed handling."""
import shutil
import subprocess

import pytest

from open_video.core.stitcher import Stitcher

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg/ffprobe required")


def _clip(path, seconds=1):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                    f"testsrc=size=64x64:rate=10:duration={seconds}",
                    "-pix_fmt", "yuv420p", "-c:v", "libx264", str(path)], check=True)


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def test_concat_relative_paths_from_relative_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    st = Stitcher("output")
    _clip("output/a.mp4")
    _clip("output/b.mp4")
    film = st.concat(["output/a.mp4", "output/b.mp4"], "output/film.mp4")
    assert film is not None and (tmp_path / "output" / "film.mp4").exists()
    assert _duration(tmp_path / "output" / "film.mp4") == pytest.approx(2.0, abs=0.3)


def test_concat_path_with_single_quote(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    st = Stitcher("output")
    _clip("output/it's a.mp4")
    _clip("output/b.mp4")
    film = st.concat(["output/it's a.mp4", "output/b.mp4"], "output/film.mp4")
    assert film is not None and (tmp_path / "output" / "film.mp4").exists()
    assert _duration(tmp_path / "output" / "film.mp4") == pytest.approx(2.0, abs=0.3)


def test_extract_last_frame_ok(tmp_path):
    _clip(tmp_path / "v.mp4")
    png = tmp_path / "lf.png"
    assert Stitcher(str(tmp_path)).extract_last_frame(str(tmp_path / "v.mp4"), str(png)) == str(png)
    assert png.stat().st_size > 0


def test_extract_last_frame_failure_ignores_stale_png(tmp_path):
    bad = tmp_path / "notvideo.mp4"
    bad.write_text("not a video")
    png = tmp_path / "lf.png"
    png.write_bytes(b"stale")
    assert Stitcher(str(tmp_path)).extract_last_frame(str(bad), str(png)) is None
    assert not png.exists()
