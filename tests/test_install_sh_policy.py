"""Structural tests on scripts/install.sh policy (skeptic-flagged paths)."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INSTALL = (REPO / "scripts" / "install.sh").read_text(encoding="utf-8")


def test_no_nvidia_sets_skip_server_and_generate():
    assert 'if [[ "${HAVE_NVIDIA:-0}" -ne 1 ]]; then' in INSTALL
    assert "SKIP_SERVER=1" in INSTALL
    assert "SKIP_GENERATE=1" in INSTALL
    # must return before start_server on no-GPU path
    idx = INSTALL.index("No NVIDIA: SKIP_SERVER=1 SKIP_GENERATE=1")
    # after that flag block, main must branch HAVE_NVIDIA -ne 1 with return 0
    assert 'if [[ "$HAVE_NVIDIA" -ne 1 ]]; then' in INSTALL
    assert "print_success" in INSTALL
    # start_server must not die-only on no GPU
    assert "die \"ComfyUI generation needs an NVIDIA GPU" not in INSTALL
    assert "not starting ComfyUI (generation deferred)" in INSTALL or "No NVIDIA GPU — not starting" in INSTALL


def test_lowvram_flag_is_conditional():
    assert "lowvram_args" in INSTALL
    assert 'if [[ "${USE_LOWVRAM:-0}" -eq 1 ]]; then' in INSTALL
    assert "lowvram_args=\"--lowvram\"" in INSTALL
    # launch line uses variable, not hardcoded alone
    assert "$lowvram_args" in INSTALL
    # must not have unconditional --lowvram on the nohup main.py line without variable
    for line in INSTALL.splitlines():
        if "nohup" in line and "main.py" in line and "--listen" in line:
            assert "--lowvram $sage_args" not in line or "$lowvram_args" in line
            assert "$lowvram_args" in line


def test_windows_installer_exists():
    ps1 = REPO / "scripts" / "install.ps1"
    assert ps1.is_file()
    text = ps1.read_text(encoding="utf-8")
    assert "irm https://open-video.ai/install.ps1" in text or "install.ps1" in text
    assert "WSL" in text


def test_windows_installer_wsl_guard_accepts_gitfile():
    """WSL embedded-bash reuse guard must accept linked checkouts where .git is
    a file (worktrees/submodules), matching install.sh's -e test."""
    text = (REPO / "scripts" / "install.ps1").read_text(encoding="utf-8")
    assert "[ ! -e `$HOME/open-video/.git ]" in text
    assert "[ ! -d `$HOME/open-video/.git ]" not in text


def test_comfyui_pin_single_source():
    """Both installer scripts must source scripts/comfyui.pin (no drifting SHAs)."""
    import re
    root = Path(__file__).resolve().parent.parent
    pin = (root / "scripts" / "comfyui.pin").read_text()
    sha = re.search(r'COMFYUI_COMMIT="([0-9a-f]{40})"', pin)
    assert sha, "comfyui.pin must define a full-length COMFYUI_COMMIT"
    for script in ("install.sh", "lab-restore.sh"):
        text = (root / "scripts" / script).read_text()
        assert "comfyui.pin" in text, f"{script} must source scripts/comfyui.pin"
    # lab-restore must not carry its own SHA copy; install.sh may keep ONE
    # bootstrap fallback (standalone curl|bash runs before the repo exists)
    assert len(re.findall(r'COMFYUI_COMMIT="[0-9a-f]{40}"',
                          (root / "scripts" / "lab-restore.sh").read_text())) == 0
    inst = re.findall(r'COMFYUI_COMMIT="([0-9a-f]{40})"',
                      (root / "scripts" / "install.sh").read_text())
    assert len(inst) == 1
    # the standalone-bootstrap fallback must not drift from the pin (single source)
    assert inst[0] == sha.group(1), (
        f"install.sh fallback {inst[0]} != comfyui.pin {sha.group(1)}")
