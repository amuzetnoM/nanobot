# Changelog

All notable changes to this project will be documented in this file.

## [0.1.0] - 2026-03-03

### Added

- Core engine: `spawn()`, `spawn_async()`, `Nanobot`, `AsyncNanobot`
- CLI: `nanobot` command with space/bot targeting
- Self-destruct mode for trace-free execution
- Bot registry with multi-directory resolution (user spaces + built-in)
- JSON output mode for pipeline integration
- Built-in spaces:
  - `ops/health` - System health monitoring (CPU, memory, disk, services, temps)
  - `security/threat-radar` - NVD CVE scanning, CISA KEV catalog, arXiv security research
  - `code/secrets` - Credential and secret scanner with regex patterns
  - `research/` - AI/ML research space (ready for custom bots)
  - `recon/` - OSINT space (ready for custom bots)
  - `intel/` - Threat intelligence space (ready for custom bots)
- Full test suite
- Documentation and guides

### Philosophy

The monument, reversed. Fire and forget micro-agents that do one thing and disappear.
