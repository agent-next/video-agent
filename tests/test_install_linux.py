"""Linux installer robustness: root without sudo, venv bootstrap, interrupt cleanup, log location."""
import os
import re
import shlex
import subprocess
from pathlib import Path


INSTALL = Path(__file__).resolve().parents[1] / "scripts" / "install.sh"
SOURCE = INSTALL.read_text()

STUBS = """set -uo pipefail
info() { :; }
ok() { printf 'ok: %s\\n' "$*"; }
warn() { printf 'warn: %s\\n' "$*" >&2; }
err() { printf 'err: %s\\n' "$*" >&2; }
step() { :; }
confirm() { return 0; }
"""


def functions(*names):
    return "\n".join(
        re.search(rf"^{name}\(\) \{{.*?^\}}", SOURCE, re.M | re.S).group()
        for name in names
    )


def run(tmp_path, body, *, path_dirs=()):
    harness = tmp_path / "harness.sh"
    harness.write_text(STUBS + body)
    env = dict(os.environ)
    env["PATH"] = ":".join([*map(str, path_dirs), "/usr/bin", "/bin"])
    return subprocess.run(["bash", str(harness)], text=True, capture_output=True, env=env)


def fake_bin(tmp_path, *names, record):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name in names:
        exe = bin_dir / name
        exe.write_text(f"#!/bin/sh\necho {name} \"$@\" >> {shlex.quote(str(record))}\n")
        exe.chmod(0o755)
    return bin_dir


def install_tools_harness(uid, *, sudo_available):
    sudo_check = "return 0" if sudo_available else "return 1"
    return f"""
id() {{ echo {uid}; }}
have() {{ [[ "$1" == sudo ]] && {{ {sudo_check}; }}; command -v "$1" >/dev/null; }}
PKG_MGR=apt
{functions("install_tools")}
install_tools git curl
"""


def test_root_installs_tools_without_sudo(tmp_path):
    record = tmp_path / "calls.log"
    bin_dir = fake_bin(tmp_path, "apt-get", "sudo", record=record)
    result = run(tmp_path, install_tools_harness(0, sudo_available=False), path_dirs=[bin_dir])
    assert result.returncode == 0, result.stderr
    calls = record.read_text().splitlines()
    assert calls == ["apt-get update -y", "apt-get install -y git curl"]


def test_non_root_without_sudo_explains_instead_of_crashing(tmp_path):
    record = tmp_path / "calls.log"
    bin_dir = fake_bin(tmp_path, "apt-get", record=record)
    result = run(tmp_path, install_tools_harness(1000, sudo_available=False), path_dirs=[bin_dir])
    assert result.returncode == 1
    assert "sudo is not available" in result.stderr
    assert not record.exists()


def test_non_root_uses_sudo(tmp_path):
    record = tmp_path / "calls.log"
    bin_dir = fake_bin(tmp_path, "apt-get", "sudo", record=record)
    result = run(tmp_path, install_tools_harness(1000, sudo_available=True), path_dirs=[bin_dir])
    assert result.returncode == 0, result.stderr
    assert record.read_text().splitlines()[0] == "sudo apt-get update -y"


def test_venv_failure_on_apt_installs_python3_venv_and_retries(tmp_path):
    venv = tmp_path / "venv"
    marker = tmp_path / "python3-venv-installed"
    body = f"""
VENV_DIR={shlex.quote(str(venv))}
PKG_MGR=apt
die() {{ printf 'die: %s\\n' "$*" >&2; exit 1; }}
install_tools() {{ echo "install_tools $*" >&2; touch {shlex.quote(str(marker))}; }}
python3() {{
    [[ -e {shlex.quote(str(marker))} ]] || return 1
    [[ "$*" == "-m venv --clear $VENV_DIR" ]] || return 3
    mkdir -p "$VENV_DIR/bin"; printf '#!/bin/sh\\nexit 0\\n' > "$VENV_DIR/bin/python"
    chmod +x "$VENV_DIR/bin/python"
}}
{functions("make_venv")}
make_venv
"""
    result = run(tmp_path, body)
    assert result.returncode == 0, result.stderr
    assert "install_tools python3-venv" in result.stderr
    assert (venv / "bin/python").exists()


def test_interrupt_stops_server_started_by_this_run(tmp_path):
    (tmp_path / ".cache").mkdir()
    body = f"""
OV_ROOT={shlex.quote(str(tmp_path))}
KEEP_SERVER=0
{re.search(r'^COMFY_PID="".*?^trap on_interrupt INT TERM$', SOURCE, re.M | re.S).group()}
{functions("stop_server_if_ours")}
sleep 300 &
COMFY_PID=$!
echo "$COMFY_PID" > {shlex.quote(str(tmp_path / "pid"))}
kill -TERM $$
sleep 5
echo "not interrupted"
"""
    result = run(tmp_path, body)
    assert result.returncode == 130, result.stdout + result.stderr
    pid = int((tmp_path / "pid").read_text())
    assert subprocess.run(["kill", "-0", str(pid)], capture_output=True).returncode != 0
    assert "Stopped ComfyUI" in result.stdout


def test_trap_is_installed_after_comfy_pid_is_declared():
    assert SOURCE.index('COMFY_PID=""') < SOURCE.index("trap on_interrupt INT TERM")


def test_logs_live_under_install_root_not_shared_tmp():
    assert "/tmp/" not in SOURCE
    assert 'LOG_DIR="$OV_ROOT/.cache/logs"' in SOURCE
