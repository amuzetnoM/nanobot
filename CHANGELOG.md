# Changelog

All notable changes to this project will be documented in this file.

## [0.1.1] - 2026-03-03

### Added

- **Destruct policy system:** `destruct_policy` field on `Nanobot` — `"off"`, `"on"`, or `"auto"`
  - `"auto"` self-destructs when: duration < 5s AND exit code 0 AND report < 10KB
  - Policy defaults can be set per-bot in `space.yaml` via `destruct: auto|on|off`
- **Report TTL:** `report_ttl` parameter — spawns a daemon thread that deletes the report file after N seconds. Content stays in the result object.
- **Full destruct mode:** `full_destruct=True` — deletes report, writes a tombstone file (run_id + timestamp + DESTRUCTED). Proof of execution, zero content.
- **Destruct callback:** `on_destruct` — optional callable invoked after destruct for custom cleanup
- **`destructed` field** on `NanobotResult` and `to_dict()` output
- CLI flags: `--full-destruct`, `--report-ttl N`, `--auto-destruct`
- `get_bot_meta()` registry function for reading bot metadata from space.yaml
- Tests for all new destruct features

### Changed

- `NanobotResult.to_dict()` now includes `destructed: bool`
- `list_bots()` now includes `destruct` key in returned dicts
- CLI bot listing shows destruct policy when not `"off"`

### Fixed

- Project URLs now point to `amuzetnoM/nanobot`

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
