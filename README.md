<div align="center">

```
    ┌─────────────────────────────────┐
    │  ╔╗╔╔═╗╔╗╔╔═╗╔╗  ╔═╗╔╦╗╔═╗   │
    │  ║║║╠═╣║║║║ ║╠╩╗ ║ ║ ║ ╚═╗   │
    │  ╝╚╝╩ ╩╝╚╝╚═╝╚═╝ ╚═╝ ╩ ╚═╝   │
    │  fire and forget micro-agents   │
    └─────────────────────────────────┘
```

**Surgical micro-agents for AI systems. Spawn, execute, self-destruct.**

[![PyPI](https://img.shields.io/pypi/v/nanobots?style=flat-square)](https://pypi.org/project/nanobots/)
[![Python](https://img.shields.io/pypi/pyversions/nanobots?style=flat-square)](https://pypi.org/project/nanobots/)
[![License](https://img.shields.io/github/license/amuzetnoM/nanobot?style=flat-square)](LICENSE)

[Install](#install) · [Quick Start](#quick-start) · [Self-Destruct](#self-destruct) · [Spaces](#built-in-spaces) · [Python API](#python-api) · [Designed for AI](#designed-for-ai) · [Philosophy](#philosophy)

</div>

---

Your AI agents don't need another framework. They need disposable tools that execute, report, and vanish. A nanobot does one thing, does it now, and leaves no trace.

**One bot. One job. Gone.**

## Install

```bash
pip install nanobots
```

## Quick Start

### CLI

```bash
nanobot ops/health                      # Run a health check
nanobot security/threat-radar           # Scan for CVEs
nanobot code/secrets /path/to/project   # Find leaked secrets
nanobot ops/health --self-destruct      # Run, report, vanish
nanobot ops/health --json               # Machine-readable output
```

### Python

```python
from nanobots import spawn

result = spawn("ops/health")
print(result.ok)      # True
print(result.report)  # Full markdown report

# Self-destruct: content in memory, nothing on disk
result = spawn("code/secrets", args=["/my/project"], self_destruct=True)
```

### Full Control

```python
from nanobots import Nanobot

bot = Nanobot("security", "threat-radar")
bot.timeout = 120
bot.self_destruct = True
result = bot.run()
```

## Self-Destruct

Nanobots have a layered destruct system. Choose your level of erasure.

### Destruct Modes

| Mode | What Happens | Use Case |
|------|-------------|----------|
| `self_destruct` | Deletes report file. Content stays in result object. | Default cleanup |
| `full_destruct` | Deletes report + writes a tombstone (proof of run, zero content) | Audit-compliant erasure |
| `report_ttl` | Report auto-deletes after N seconds | Temp visibility windows |
| `auto` policy | Bot decides: simple tasks self-clean, complex tasks persist | Set-and-forget |

### CLI

```bash
nanobot ops/health --self-destruct       # Delete report after read
nanobot ops/health --full-destruct       # Tombstone mode
nanobot ops/health --report-ttl 60       # Report vanishes in 60 seconds
nanobot ops/health --auto-destruct       # Let the bot decide
```

### Python

```python
from nanobots import spawn, Nanobot

# Standard destruct
result = spawn("ops/health", self_destruct=True)

# Full destruct with tombstone
result = spawn("ops/health", full_destruct=True, destruct_policy="on")

# Report TTL — file vanishes in 60 seconds, result object keeps the data
result = spawn("ops/health", report_ttl=60)

# Auto-destruct policy
result = spawn("ops/health", destruct_policy="auto")

# Destruct callback — custom cleanup logic
def on_cleanup(result):
    print(f"Destructed: {result.run_id}")

result = spawn("ops/health", destruct_policy="on", on_destruct=on_cleanup)

# Full control
bot = Nanobot("security", "threat-radar",
    destruct_policy="auto",
    report_ttl=120,
    full_destruct=True,
    on_destruct=on_cleanup,
)
result = bot.run()
```

### Auto-Destruct

The `"auto"` policy lets the bot decide based on task characteristics:

- **Self-destructs** when: duration < 5s AND exit code 0 AND report < 10KB
- **Persists** when: long-running, failed, or produced significant output

Simple tasks (quick health check, empty recycle bin) clean up after themselves. Complex tasks (security scans, research, anything that fails) keep their reports for investigation.

Set defaults per-bot in `space.yaml`:

```yaml
bots:
  health:
    description: System health check
    destruct: auto    # quick checks auto-clean

  threat-radar:
    description: CVE scanning
    destruct: off     # security reports persist
```

## Built-in Spaces

Six specialized spaces, each with purpose-built bots.

### ops — System Operations

| Bot | Description |
|-----|-------------|
| `health` | CPU load, memory, disk, services, temperatures |

```bash
nanobot ops/health
```

### security — Cybersecurity

| Bot | Description |
|-----|-------------|
| `threat-radar` | NVD CVE scanning, CISA KEV catalog, arXiv security research |

```bash
nanobot security/threat-radar
```

### code — Code Analysis

| Bot | Description |
|-----|-------------|
| `secrets` | Scan for leaked API keys, tokens, passwords, private keys |

```bash
nanobot code/secrets /path/to/scan
```

### research · recon · intel

AI/ML research, OSINT reconnaissance, and threat intelligence spaces. Ready for custom bots.

## How It Works

```
Caller                  nanobots                      Bot Script
 │                         │                              │
 ├── spawn("ops/health") ──┤                              │
 │                         ├── resolve bot (registry)     │
 │                         ├── set env vars               │
 │                         ├── subprocess.run() ──────────┤
 │                         │                              ├── execute
 │                         │                              ├── write report
 │                         │                              ├── exit(0)
 │                         ├── collect stdout/stderr  ◄───┤
 │                         ├── read report into memory    │
 │                         │                              │
 │                         ├── DESTRUCT DECISION          │
 │                         │   ├─ policy=off  → keep      │
 │                         │   ├─ policy=on   → delete    │
 │                         │   ├─ policy=auto → evaluate  │
 │                         │   │   ├─ <5s + exit 0 + <10KB → delete
 │                         │   │   └─ otherwise           → keep
 │                         │   ├─ full_destruct → tombstone
 │                         │   └─ report_ttl → timer thread
 │                         │                              │
 │  ◄── NanobotResult ────┤                              │
 │   .report (in memory)   │                              │
 │   .destructed = true    │                              │
```

Every nanobot runs in its own subprocess. No shared state. No side effects. The parent gets a clean `NanobotResult` with report content in memory regardless of what happens to the file on disk.

## Python API

```python
from nanobots import spawn, spawn_async, Nanobot

# Simple
result = spawn("ops/health")

# With destruct options
result = spawn("ops/health",
    destruct_policy="auto",
    report_ttl=60,
    full_destruct=True,
    on_destruct=lambda r: print(f"cleaned: {r.run_id}"),
)

# Async (background)
handle = spawn_async("security/threat-radar")
result = handle.wait()

# Parallel swarm
handles = [
    spawn_async("ops/health"),
    spawn_async("security/threat-radar"),
    spawn_async("code/secrets", args=["./src"]),
]
results = [h.wait() for h in handles]
```

### NanobotResult

```python
result.ok           # bool — success + exit code 0
result.report       # str — markdown report content (always available)
result.report_path  # Path | None — file path (None if destructed)
result.destructed   # bool — whether destruct fired
result.status       # "success" | "error" | "timeout"
result.exit_code    # int
result.duration_ms  # int
result.run_id       # str — 8-char hex ID
result.to_dict()    # dict — serializable, includes destructed field
```

## Designed for AI

Nanobots are built to be called by agents, not clicked by humans. The entire API is optimized for programmatic consumption.

**Why this exists:** AI agents need to interact with operating systems, scan codebases, check security posture, and monitor infrastructure. They don't need a framework for that. They need a function call that returns a report.

```python
# An agent skill is just a spawn call
def check_security(target: str) -> str:
    result = spawn("security/threat-radar", self_destruct=True)
    return result.report if result.ok else f"Scan failed: {result.stderr}"
```

**Properties agents care about:**
- **Deterministic:** Same input → same behavior. No sessions, no connections.
- **Self-cleaning:** `destruct_policy="auto"` — routine checks vanish, anomalies persist.
- **Structured output:** Markdown reports. Parseable by LLMs. Readable by humans.
- **Composable:** Chain them, parallelize them, embed them in any framework.
- **No infrastructure:** Pure Python. No servers, no containers, no API keys.

### Framework Integration

```python
# LangChain
@tool
def nanobot_run(target: str, args: str = "") -> str:
    result = spawn(target, args=args.split(), self_destruct=True)
    return result.report if result.ok else f"Error: {result.stderr}"

# OpenAI function calling
tools = [{"type": "function", "function": {
    "name": "run_nanobot",
    "parameters": {"properties": {
        "target": {"type": "string"},
        "args": {"type": "array", "items": {"type": "string"}},
    }}
}}]
```

## Write Your Own Bot

A nanobot is just a script. Python or Bash.

```
my-spaces/
└── myspace/
    ├── space.yaml
    └── my-bot.py
```

```yaml
# space.yaml
name: myspace
description: "My custom space"
version: 1.0

bots:
  my-bot:
    description: "Does one thing"
    destruct: auto
```

```python
#!/usr/bin/env python3
import os, sys
from pathlib import Path

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "default"
    report = f"# Result\n\nTarget: {target}\nStatus: Done.\n"
    Path(os.environ["NANOBOT_OUTPUT"]).write_text(report)

if __name__ == "__main__":
    main()
```

```bash
export NANOBOT_SPACES_DIR=/path/to/my-spaces
nanobot myspace/my-bot target-value
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `NANOBOT_RUN_ID` | Unique 8-char hex ID |
| `NANOBOT_SPACE` | Space name |
| `NANOBOT_BOT` | Bot name |
| `NANOBOT_OUTPUT` | Report file path |
| `NANOBOT_SELF_DESTRUCT` | `"1"` if destruct is active |
| `NANOBOT_CALLER_CWD` | Caller's working directory |

## Philosophy

Nanobots exist because heavyweight agent frameworks are the wrong abstraction for surgical tasks.

You don't need a state machine to check disk usage. You don't need a vector database to scan for API keys. You don't need an orchestrator to fetch CVEs.

You need a script that does one thing, returns a report, and disappears.

- **One bot, one job.** No multi-tools. Two responsibilities = two bots.
- **Fire and forget.** Spawn, report, gone. No sessions. No connections.
- **Zero infrastructure.** Pure stdlib. No servers, no Docker, no cloud.
- **Self-destruct capable.** Results without traces.
- **Composable.** Functions, not services.
- **Reports, not noise.** Structured markdown. Machine-readable. Human-scannable.

## License

MIT. See [LICENSE](LICENSE).

---

<div align="center">

Built by [Artifact Virtual](https://artifactvirtual.com)

*The monument, reversed.*

</div>
