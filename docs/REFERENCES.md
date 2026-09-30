# Reference products — related open projects

> Public map of projects OpenVideo learns from (product UX, install patterns, local-agent
> surfaces). Update star counts and URLs before citing them.

## Canonical references

| Project | URL | Repo | Role for OpenVideo |
|---|---|---|---|
| **OpenCode** | [opencode.ai](https://opencode.ai/) | [anomalyco/opencode](https://github.com/anomalyco/opencode) | Install UX + multi-surface open agent pattern. |
| **Open Design** | [open-design.ai](https://open-design.ai/) | [nexu-io/open-design](https://github.com/nexu-io/open-design) | Local-first agent product; skills; Apache-2.0. |
| **OpenArt** | [openart.ai](https://openart.ai/) | [OpenArt-AI](https://github.com/OpenArt-AI) (partial) | Creator-facing studio DNA (product, not only node-graph). |
| **Cursor** | cursor.com | closed | Closed code incumbent (analogy only). |
| **Runway / Seedance** | runwayml.com / seedance | closed | Closed video incumbents (analogy / technical peers). |

## Family analogy (site-friendly)

| Domain | Closed product | Open alternative |
|---|---|---|
| **Code** | Cursor | **OpenCode** |
| **Design** | Claude Design / closed agents | **Open Design** |
| **Video** | Runway / Seedance | **OpenVideo** |

One-liner:

> **OpenCode → Cursor. Open Design → Claude Design. OpenVideo → Runway.**

## Patterns we copy

### From OpenCode
- Clear one-breath product H1.
- One install command on the site.
- Multi-surface thinking (for us: CLI + Skill first; App later).
- Model-agnostic framing.

### From Open Design
- “Open-source X alternative” clarity.
- Local-first + agent hosts.
- Apache-2.0, free local use.
- Skills packaging for agents.

### From OpenArt
- Ship a **product** story, not only a node-graph manual.
- Gallery / models library when they exist.
- Creator language over pure research jargon.

## Patterns we deliberately do **not** copy

| Source | Pattern | Why not |
|---|---|---|
| OpenArt | All-modality studio as equals | OpenVideo stays **video-focused** (native audio-with-clip is in-scope). |
| Hosted-only studios | Credits as the only path | We are **local-first**. |
| Closed Runway | Black-box API only | Lead with ownership and local runs. |
| Generic “AI studio” | Feature soup | Focus: H3 quality path now; director loop as roadmap. |

## Install UX parity

The table describes the website entry points. For the v0.1.0 versioned install,
follow [Quickstart](QUICKSTART.md); the website installer is updated separately.

| Surface | OpenCode | Open Design | OpenVideo |
|---|---|---|---|
| One-liner | `curl -fsSL https://opencode.ai/install \| bash` | `curl -fsSL https://open-design.ai/install.sh \| sh` | `curl -fsSL https://open-video.ai/install \| bash` |
| Docs | opencode.ai/docs | open-design.ai | open-video.ai/docs |
| Desktop | Download page | Download page | **Not primary** today (CLI + Try mockup) |
| Agent skill | — | Skills / MCP | `skill/h3-video` + `skill/open-video` (MCP **planned**, not current) |

## Repo / brand hygiene

- **Site:** `https://open-video.ai`
- **Code:** `agent-next/video-agent`
- Names: **OpenVideo**, **open-video**, **open-video.ai**
- Avoid bare `open-video.pages.dev` name collisions — use `open-video.ai`

## How to use this doc

1. Website copy — install clarity, honest v0.0.1 scope.
2. README — one-liner install + analogy without fake shipped features.
3. Pitch — product story; never “we’re only a ComfyUI wrapper,” and never claim free cloud GPU.

## Sources checked (2026-08-06)

- https://open-design.ai/ · https://github.com/nexu-io/open-design  
- https://opencode.ai/ · https://github.com/sst/opencode / anomalyco  
- https://openart.ai/ · https://github.com/OpenArt-AI  
- Local: `README.md`, `PLAN.md`; site in `open-video-web`
