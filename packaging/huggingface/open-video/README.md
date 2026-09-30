---
license: apache-2.0
library_name: open-video
tags:
  - video-generation
  - text-to-video
  - image-to-video
  - comfyui
  - minimax-h3
  - open-source
  - agent
  - local-first
  - open-video
pipeline_tag: text-to-video
---

# OpenVideo · v0.1.0

**OpenVideo** is open-source video generation.

v0.1.0 focuses on **local MiniMax H3**: Ollama-style install/CLI (`pull` · `run` · `status`) and a **skill harness** so any agent can generate high-quality video on your GPU. Reliability release: integrity-verified weights, atomic recipe-in-render metadata, honest `SKIPPED` judge verdicts without a configured VLM, and unique I2V/FL2V input staging.

| | |
|---|---|
| **Product** | OpenVideo |
| **Code** | open-video |
| **Website** | https://open-video.ai |
| **GitHub** | https://github.com/agent-next/video-agent |
| **License (code)** | Apache-2.0 |

```bash
git clone --depth 1 --branch v0.1.0 https://github.com/agent-next/video-agent
cd open-video && bash scripts/install.sh
open-video pull h3
open-video run "a red panda in mist" --duration 5
```

Use the versioned clone above to install this release. The website installer is updated separately and may serve an older version.

Agent: load `skill/h3-video/SKILL.md` from the repo.

This Hub card is software documentation — it does not re-host H3 weights (~54 GB; pulled upstream by the installer).
