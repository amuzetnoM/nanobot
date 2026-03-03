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
[![License](https://img.shields.io/github/license/ArtifactVirtual/nanobots?style=flat-square)](LICENSE)

[Install](#install) · [Quick Start](#quick-start) · [Spaces](#built-in-spaces) · [Python API](#python-api) · [Write Your Own](#write-your-own-bot) · [Philosophy](#philosophy)

</div>

---

Your AI agents don't need another framework. They need surgical tools. A nanobot does one thing, does it now, and disappears. No state. No infrastructure. No dependency hell.

**One bot. One job. Gone.**

## Install

```bash
pip install nanobots
```

Or from source:

```bash
git clone https://github.com/ArtifactVirtual/nanobots.git
cd nanobots
pip install -e .
```

## Quick Start

### Command Line

```bash
# List available spaces
nanobot list

# Run a health check
nanobot ops/health

# Scan for leaked secrets
nanobot code/secrets /path/to/project

# Run threat radar
nanobot security/threat-radar

# Self-destruct mode (clean up all traces)
nanobot ops/health --self-destruct

# JSON output for piping
nanobot ops/health --json

# Custom report location
nanobot security/threat-radar --output ./reports/
```

### Python API

```python
from nanobots import spawn

# Fire and forget
result = spawn("ops/health")
print(result.ok)      # True
print(result.report)  # Full markdown report

# Self-destruct mode
result = spawn("code/secrets", args=["/my/project"], self_destruct=True)
# Report is in result.report, but no file left on disk

# Async (background)
from nanobots import spawn_async

handle = spawn_async("security/threat-radar")
# ... do other work ...
result = handle.wait()
```

### Full Control

```python
from nanobots import Nanobot

bot = Nanobot("security", "threat-radar")
bot.timeout = 120
bot.self_destruct = True
result = bot.run()

if result.ok:
    print(result.report)
else:
    print(f"Failed: {result.stderr}")
```

## Built-in Spaces

Nanobots ship with six specialized spaces. Each contains purpose-built bots for a specific domain.

### ops

System health monitoring and operations.

| Bot | Description |
|-----|-------------|
| `health` | CPU load, memory, disk, services, temperatures |

```bash
nanobot ops/health
```

### security

Cybersecurity scanning and threat intelligence.

| Bot | Description |
|-----|-------------|
| `threat-radar` | NVD CVE scanning, CISA KEV catalog, arXiv security research |

```bash
nanobot security/threat-radar
```

### code

Code quality and security analysis.

| Bot | Description |
|-----|-------------|
| `secrets` | Scan for leaked API keys, tokens, passwords, private keys |

```bash
nanobot code/secrets /path/to/scan
```

### research

AI/ML research intelligence. Papers, trends, benchmarks.

*Bots coming soon. Space is ready for your custom bots.*

### recon

OSINT and infrastructure reconnaissance.

*Bots coming soon. Space is ready for your custom bots.*

### intel

Threat intelligence, APT tracking, IOC analysis.

*Bots coming soon. Space is ready for your custom bots.*

## How It Works

```
You                    nanobots                    Bot Script
 │                        │                            │
 ├── spawn("ops/health") ─┤                            │
 │                        ├── resolve bot path          │
 │                        ├── set env vars              │
 │                        ├── subprocess.run() ─────────┤
 │                        │                            ├── do the work
 │                        │                            ├── write report
 │                        │                            ├── exit
 │                        ├── collect stdout/stderr ◄───┤
 │                        ├── read report file          │
 │                        ├── self-destruct (optional)  │
 │  ◄── NanobotResult ────┤                            │
 │                        │                            │
```

Every nanobot runs in its own subprocess. No shared state. No side effects. The parent process gets a clean `NanobotResult` with the report, status, and timing.

Self-destruct mode cleans up temp files, reports, and logs after reading them into memory. The result object still has the report content, but nothing is left on disk.

## Write Your Own Bot

A nanobot is just a script. Python or Bash. That's it.

### 1. Create a Space

```
my-spaces/
└── myspace/
    ├── space.yaml
    └── my-bot.py
```

### 2. Define the Space

```yaml
# space.yaml
name: myspace
description: "My custom nanobot space"
version: 1.0

bots:
  my-bot:
    description: "Does something useful"
    args: ["target"]
```

### 3. Write the Bot

```python
#!/usr/bin/env python3
"""My custom nanobot."""

import os
import sys
from pathlib import Path

OUTPUT = os.environ.get("NANOBOT_OUTPUT", "report.md")
RUN_ID = os.environ.get("NANOBOT_RUN_ID", "unknown")

def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "default"

    # Do the work
    report = f"# My Bot Report\n\nTarget: {target}\nResult: Everything is fine.\n"
    report += f"\n---\n*Run ID: {RUN_ID}*\n"

    Path(OUTPUT).write_text(report)
    print(f"Done: {target}")

if __name__ == "__main__":
    main()
```

### 4. Point Nanobots to Your Spaces

```bash
export NANOBOT_SPACES_DIR=/path/to/my-spaces
nanobot myspace/my-bot target-value
```

Or place them in `./spaces/` relative to where you run the command.

### Environment Variables Available to Bots

| Variable | Description |
|----------|-------------|
| `NANOBOT_RUN_ID` | Unique 8-char hex ID for this run |
| `NANOBOT_SPACE` | Space name |
| `NANOBOT_BOT` | Bot name |
| `NANOBOT_OUTPUT` | Path to write the report file |
| `NANOBOT_SELF_DESTRUCT` | "1" if self-destruct mode is on |

## Composing Nanobots

Chain them. Parallelize them. Swarm them.

```python
from nanobots import spawn, spawn_async

# Sequential chain
secrets = spawn("code/secrets", args=["/my/project"])
if not secrets.ok or "Critical" in (secrets.report or ""):
    # Found secrets, investigate
    recon = spawn("recon/domain", args=["leaked-domain.com"])

# Parallel swarm
handles = [
    spawn_async("ops/health"),
    spawn_async("security/threat-radar"),
    spawn_async("code/secrets", args=["./src"]),
]
results = [h.wait() for h in handles]
```

## Self-Destruct Mode

When you need results but no traces:

```python
result = spawn("security/threat-radar", self_destruct=True)
# result.report has the content
# result.report_path is None (file was deleted)
# No temp files remain on disk
```

From CLI:

```bash
nanobot security/threat-radar --self-destruct
```

The report prints to stdout, then all files are cleaned up.

## Philosophy

Nanobots exist because heavyweight agent frameworks are the wrong tool for most jobs.

You don't need a state machine to check disk usage. You don't need a vector database to scan for leaked API keys. You don't need an orchestrator to fetch CVEs.

You need a script that does one thing, returns a report, and gets out of the way.

**Design principles:**

- **One bot, one job.** No Swiss army knives. If a bot does two things, it's two bots.
- **Fire and forget.** Spawn it, get a report, move on. No sessions, no connections, no cleanup.
- **Zero infrastructure.** Pure Python stdlib. No servers, no databases, no Docker, no cloud.
- **Self-destruct capable.** When you need results but not traces.
- **Composable.** Chain them, parallelize them, embed them. They're functions, not services.
- **Reports, not noise.** Every bot writes structured markdown. Readable by humans and machines.

## Project Structure

```
nanobots/
├── src/nanobots/
│   ├── __init__.py         # Public API
│   ├── core.py             # Spawn engine, Nanobot class, async handles
│   ├── registry.py         # Space and bot discovery
│   ├── cli.py              # Command-line interface
│   └── spaces/             # Built-in bot spaces
│       ├── ops/            # System operations
│       ├── security/       # Cybersecurity
│       ├── code/           # Code quality
│       ├── research/       # AI/ML research
│       ├── recon/          # OSINT
│       └── intel/          # Threat intelligence
├── tests/                  # Test suite
├── docs/                   # Extended documentation
├── pyproject.toml          # Package config
├── LICENSE                 # MIT
└── README.md               # You are here
```

## Contributing

Contributions welcome. Especially new bots and spaces.

1. Fork it
2. Create your space or bot
3. Write tests
4. Submit a PR

Keep it simple. Keep it stdlib. One bot, one job.

## License

MIT. See [LICENSE](LICENSE).

---

<div align="center">

Built by [Artifact Virtual](https://artifactvirtual.com)

*The monument, reversed.*

</div>
