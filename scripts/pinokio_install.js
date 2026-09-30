//---------------------------------------------------------------------------
// OpenVideo — Pinokio one-click installer
//
// Does the full first-run setup, then launches ComfyUI (with the H3 backend
// wired in) and opens the OpenVideo web interface:
//   1. clone the open-video repo into ./app
//   2. create + link a uv venv (app/env)
//   3. install torch (platform / GPU aware), then ComfyUI + open-video deps
//   4. clone ComfyUI into ./app/ComfyUI
//   5. download the MiniMax H3 weights (~54 GB, int8_convrot set) from HF
//   6. launch ComfyUI on 127.0.0.1:8188 (daemon) and surface the web UI URL
//
// Format: standard Pinokio script (module.exports = { run: [...] }). Every step
// is idempotent (guarded by `when: {{!exists(...)}}`) so re-running Install is
// safe and fast. `daemon: true` keeps the launched ComfyUI alive after the
// script returns.
//
// H3 file/URL/size/hash policy lives in models/h3_manifest.json (shared with
// install.sh and h3_download.sh) and matches the filenames in
// backends/h3/backend.py -> default_settings().
//---------------------------------------------------------------------------
module.exports = {
  daemon: true,
  run: [
    // ── 0. Welcome notice ────────────────────────────────────────────────
    {
      method: "input",
      params: {
        title: "Install OpenVideo + MiniMax H3",
        description: "This downloads the MiniMax H3 model weights (~54 GB) on top of ComfyUI, so the first install needs a fast connection and ~60 GB of free disk. An NVIDIA GPU with 16 GB+ VRAM is recommended (24 GB+ ideal) for the int8 weights. Click OK to start."
      }
    },

    // ── 1. Clone open-video ──────────────────────────────────────────────
    {
      when: "{{!exists('app')}}",
      method: "shell.run",
      params: {
        message: [
          "git clone --depth 1 https://github.com/agent-next/video-agent app"
        ]
      }
    },
    // Keep the clone current if it already exists.
    {
      when: "{{exists('app')}}",
      method: "shell.run",
      params: {
        path: "app",
        message: "git pull --ff-only"
      }
    },

    // ── 2. Create the venv (app/env) and register it with Pinokio ────────
    {
      when: "{{!exists('app/env')}}",
      method: "shell.run",
      params: {
        path: "app",
        message: "uv venv env"
      }
    },
    {
      method: "fs.link",
      params: {
        venv: "app/env"
      }
    },

    // ── 3. torch — platform / GPU aware ──────────────────────────────────
    // Windows + NVIDIA
    {
      when: "{{platform === 'win32' && gpu === 'nvidia'}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121"
      }
    },
    // Windows + AMD
    {
      when: "{{platform === 'win32' && gpu === 'amd'}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch-directml torchaudio torchvision numpy==1.26.4"
      }
    },
    // Windows + CPU/other
    {
      when: "{{platform === 'win32' && (gpu !== 'nvidia' && gpu !== 'amd')}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 numpy==1.26.4"
      }
    },
    // macOS (Apple Silicon)
    {
      when: "{{platform === 'darwin'}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1"
      }
    },
    // Linux + NVIDIA
    {
      when: "{{platform === 'linux' && gpu === 'nvidia'}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121"
      }
    },
    // Linux + AMD (ROCm)
    {
      when: "{{platform === 'linux' && gpu === 'amd'}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/rocm6.0"
      }
    },
    // Linux + CPU/other
    {
      when: "{{platform === 'linux' && (gpu !== 'nvidia' && gpu !== 'amd')}}",
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: "uv pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu"
      }
    },

    // ── 4. Clone ComfyUI into ./app/ComfyUI ──────────────────────────────
    {
      when: "{{!exists('app/ComfyUI')}}",
      method: "shell.run",
      params: {
        path: "app",
        message: "git clone https://github.com/comfyanonymous/ComfyUI"
      }
    },

    // ── 5. Install ComfyUI + open-video Python deps ──────────────────────
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: [
          "uv pip install -r ComfyUI/requirements.txt",
          "uv pip install -e .",
          "uv pip install -U huggingface_hub"
        ]
      }
    },

    // ── 6. Download MiniMax H3 weights (~54 GB) ──────────────────────────
    // Source: https://huggingface.co/Comfy-Org/MiniMax-H3  (int8_convrot set,
    // matching backends/h3/backend.py default_settings()).
    // Files land in ComfyUI's standard model dirs so ComfyUI auto-discovers them.
    // Paths, byte sizes, URLs and release commit/sha256 come from the shared
    // models/h3_manifest.json via scripts/verify_h3_manifest.py: `fetch`
    // curl-downloads missing/incomplete files (resumable), `check` verifies
    // size + sha256 and fails closed while release hashes are pending.
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: [
          "mkdir -p ComfyUI/models/vae ComfyUI/models/diffusion_models ComfyUI/models/text_encoders",
          "python scripts/verify_h3_manifest.py fetch --manifest models/h3_manifest.json --models-dir ComfyUI/models",
          "python scripts/verify_h3_manifest.py check --manifest models/h3_manifest.json --models-dir ComfyUI/models"
        ]
      }
    },

    // ── 7. Wire open-video's H3 workflows into ComfyUI/user · ───────────
    // Copy the shipped H3 API workflows (t2v / flf2v) into ComfyUI's user
    // defaults so they appear in the ComfyUI UI's workflow browser.
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app",
        message: [
          "mkdir -p ComfyUI/user/default/workflows",
          "cp -f backends/h3/workflows/h3_t2v_api.json ComfyUI/user/default/workflows/openvideo_h3_t2v.json || true",
          "cp -f backends/h3/workflows/h3_flf2v_api.json ComfyUI/user/default/workflows/openvideo_h3_flf2v.json || true"
        ]
      }
    },

    // ── 8. All done — summary, then launch ───────────────────────────────
    {
      method: "input",
      params: {
        title: "Setup complete",
        description: "Weights are in place. Click OK to launch ComfyUI (with MiniMax H3) and open the OpenVideo interface at http://127.0.0.1:8188. The first launch can take a minute as the model loads into VRAM."
      }
    },

    // ── 9. Launch ComfyUI (daemon) and capture the URL ───────────────────
    // `daemon: true` (top-level) keeps this process alive after the script
    // returns. The `on` regex waits for ComfyUI to print its GUI URL, then
    // moves on while leaving the server running.
    {
      method: "shell.run",
      params: {
        venv: "env",
        path: "app/ComfyUI",
        env: {
          HF_HUB_OFFLINE: "1"
        },
        message: "python main.py --listen 127.0.0.1 --port 8188 --lowvram",
        on: [
          {
            event: "/http:\\/\\/[0-9.:]+/",
            done: true
          }
        ]
      }
    },
    {
      method: "local.set",
      params: {
        // input.event[0] is the full regex match from the previous step
        // (ComfyUI's "To see the GUI go to: http://127.0.0.1:8188" line).
        // Pinokio exposes this as an "Open Web UI" tab.
        url: "{{input.event[0]}}"
      }
    }
  ]
}
