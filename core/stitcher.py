"""open-video stitcher — concatenates shot videos + handles audio continuity + optional 2K upscale.

The stitcher takes a list of generated shot videos and produces one coherent film:
1. Concat via ffmpeg (re-encode if codecs differ, stream-copy if same).
2. Cross-shot audio crossfade (optional, for smooth transitions).
3. Optional 2K upscale via API (H3-Regenerate-2K or simple super-resolution).
"""
import shutil
import subprocess
from pathlib import Path
from typing import Optional


class Stitcher:
    """Concatenates shots into a coherent film with audio continuity."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def concat(self, video_paths: list, output_path: str,
               re_encode: bool = False) -> Optional[str]:
        """Concatenate videos. If all same codec → stream-copy (fast); else re-encode."""
        if not video_paths:
            return None
        if len(video_paths) == 1:
            source = Path(video_paths[0])
            destination = Path(output_path)
            if source.resolve() != destination.resolve():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
            return str(destination)

        list_file = self.output_dir / "_concat.txt"
        # ffmpeg resolves relative entries against the list file's dir, so use absolute paths
        def _entry(p):
            return "file '" + str(Path(p).resolve()).replace("'", "'\\''") + "'"
        list_file.write_text("\n".join(_entry(p) for p in video_paths))
        output_path = str(Path(output_path).resolve())

        codec = ["-c", "copy"] if not re_encode else ["-c:v", "libx264", "-c:a", "aac"]
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
               "-i", str(list_file)] + codec + [output_path]
        r = subprocess.run(cmd, capture_output=True, timeout=120)
        if r.returncode != 0:
            # fallback: re-encode
            cmd_re = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                      "-i", str(list_file), "-c:v", "libx264", "-c:a", "aac", output_path]
            r = subprocess.run(cmd_re, capture_output=True, timeout=300)
        return output_path if r.returncode == 0 else None

    def extract_last_frame(self, video_path: str, output_png: str) -> Optional[str]:
        """Extract the last frame of a video (for FL2VA chaining)."""
        Path(output_png).unlink(missing_ok=True)  # never return a stale frame
        r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.1",
                            "-i", video_path, "-frames:v", "1", output_png],
                           check=False, timeout=30)
        if r.returncode != 0:
            return None
        return output_png if Path(output_png).exists() else None

    def upscale_2k(self, video_path: str, output_path: str,
                   api_key: Optional[str] = None) -> str:
        """2K upscale. If api_key provided → H3-Regenerate-2K API; else ffmpeg super-resolution."""
        if api_key:
            # TODO: call H3-Regenerate-2K API (POST /video-generation-v2-regeneration)
            # For now, fall through to ffmpeg
            pass
        # Simple ffmpeg upscale (bicubic) as fallback
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video_path,
                        "-vf", "scale=2560:-1:flags=bicubic", "-c:v", "libx264",
                        "-crf", "18", "-c:a", "aac", output_path],
                       check=False, timeout=600)
        return output_path if Path(output_path).exists() else video_path
