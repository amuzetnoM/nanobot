# Guides

## Integration with AI Agents

Nanobots are designed to be spawned by AI agents, not operated by humans clicking buttons. Here's how to integrate them into your agent workflows.

### Mach6 Integration

```python
# Inside a Mach6 agent skill
from nanobots import spawn

async def check_system_health(ctx):
    result = spawn("ops/health", self_destruct=True)
    if result.ok:
        return result.report
    return f"Health check failed: {result.stderr}"
```

### LangChain Tool

```python
from langchain.tools import tool
from nanobots import spawn

@tool
def nanobot_run(target: str, args: str = "") -> str:
    """Run a nanobot. Target format: space/bot. Optional args separated by spaces."""
    bot_args = args.split() if args else []
    result = spawn(target, args=bot_args, self_destruct=True, timeout=60)
    return result.report if result.ok else f"Error: {result.stderr}"
```

### OpenAI Function Calling

```python
tools = [{
    "type": "function",
    "function": {
        "name": "run_nanobot",
        "description": "Run a security/ops/code micro-agent",
        "parameters": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "space/bot, e.g. ops/health"},
                "args": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["target"],
        },
    },
}]
```

### Cron / Scheduled Scanning

```bash
# Run threat radar daily at 6 AM
0 6 * * * /usr/local/bin/nanobot security/threat-radar --output /var/reports/ --quiet

# Health check every 4 hours
0 */4 * * * /usr/local/bin/nanobot ops/health --json >> /var/log/health.jsonl
```

## Writing Custom Spaces

### Space Structure

A space is a directory containing:
- `space.yaml` (required): metadata and bot definitions
- One or more `.py` or `.sh` bot scripts
- Optionally a `default.py` fallback handler

### The space.yaml File

```yaml
name: my-space
description: "What this space does"
version: 1.0

purpose: |
  Longer description of the space's purpose.
  What problems it solves. Who should use it.

bots:
  my-bot:
    description: "One-line description"
    args: ["required_arg", "optional_arg"]
    schedule: "0 */6 * * *"  # optional cron schedule hint

  another-bot:
    description: "Another bot"
    args: []
```

### Bot Conventions

1. **Read config from environment.** `NANOBOT_OUTPUT`, `NANOBOT_RUN_ID`, etc.
2. **Read arguments from `sys.argv`** (Python) or `$@` (Bash).
3. **Write a markdown report** to `$NANOBOT_OUTPUT`.
4. **Print progress to stdout** (captured by the engine).
5. **Exit 0 on success, non-zero on failure.**
6. **Use only stdlib.** No pip dependencies in built-in bots.
7. **Include the run ID** in report footers for traceability.

### Testing Your Bot

```bash
# Direct execution
NANOBOT_OUTPUT=/tmp/test.md NANOBOT_RUN_ID=test123 python my-bot.py arg1 arg2
cat /tmp/test.md

# Through the dispatcher
export NANOBOT_SPACES_DIR=/path/to/my-spaces
nanobot my-space/my-bot arg1 arg2
```

## Self-Destruct Deep Dive

Self-destruct mode is for when you need the data but not the trail.

### What Gets Cleaned Up

- The report file on disk (content is still in `result.report`)
- Temp files created by the engine

### What Persists

- The `NanobotResult` object in memory (your code holds the reference)
- Stdout/stderr output (in `result.stdout` / `result.stderr`)
- Any files the bot itself creates outside of `$NANOBOT_OUTPUT`

### When to Use It

- Security scans that contain sensitive findings
- One-off diagnostics you don't need to archive
- Automated pipelines where results flow into another system
- Any case where disk artifacts are a liability

### Bot-Level Self-Destruct

Bots can check `NANOBOT_SELF_DESTRUCT` to clean up their own artifacts:

```python
import os

if os.environ.get("NANOBOT_SELF_DESTRUCT") == "1":
    # Clean up any temp files this bot created
    cleanup_temp_files()
```

## Composing Swarms

### Sequential Pipeline

```python
from nanobots import spawn

# Step 1: Find secrets
secrets = spawn("code/secrets", args=["./src"])

# Step 2: If secrets found, run security scan
if secrets.ok and "Critical" in (secrets.report or ""):
    radar = spawn("security/threat-radar")
    # Step 3: Generate combined report
    combined = f"{secrets.report}\n\n---\n\n{radar.report}"
```

### Parallel Swarm

```python
from nanobots import spawn_async

targets = [
    ("ops/health", []),
    ("security/threat-radar", []),
    ("code/secrets", ["./src"]),
    ("code/secrets", ["./config"]),
]

handles = [spawn_async(t, args=a) for t, a in targets]
results = [h.wait() for h in handles]

failed = [r for r in results if not r.ok]
if failed:
    print(f"{len(failed)} bots failed")
```

### Map-Reduce Pattern

```python
from nanobots import spawn_async

# Map: scan multiple directories
directories = ["./src", "./lib", "./config", "./scripts"]
handles = [spawn_async("code/secrets", args=[d]) for d in directories]
results = [h.wait() for h in handles]

# Reduce: aggregate findings
all_reports = [r.report for r in results if r.ok and r.report]
combined = "\n\n---\n\n".join(all_reports)
```
