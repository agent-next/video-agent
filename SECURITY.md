# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `0.0.x` (main / master) | ✅ |
| Older tags | Best-effort |

## Reporting a vulnerability

**Do not** open a public GitHub issue for security-sensitive reports.

1. Prefer [GitHub Security Advisories](https://github.com/agent-next/video-agent/security/advisories/new) on this repository.
2. Or email the maintainers via the org contact listed on the [agent-next](https://github.com/agent-next) profile once public.

Please include:

- Impact description
- Reproduction steps or PoC (non-destructive)
- Affected version / commit
- Whether you plan to disclose publicly and on what timeline

We aim to acknowledge within **72 hours** and provide a remediation plan for confirmed issues.

## Scope notes

- **Model weights** (MiniMax H3, etc.) are third-party; report weight/model license issues to the upstream provider when appropriate.
- **ComfyUI** is an external engine; report ComfyUI core vulns upstream when the issue is not in open-video’s adapter code.
- **Generated content** (CSAM, malware in prompts, etc.) is handled under community moderation and hoster ToS — not as a product CVE unless there is a clear product bug enabling abuse at scale.

## Safe contribution rules

- Never commit API keys, cloud tokens, `.env`, or private GPU host paths with credentials.
- Installer and CLI must not exfiltrate user prompts or videos to third parties without explicit opt-in.
