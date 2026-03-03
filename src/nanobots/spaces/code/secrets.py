#!/usr/bin/env python3
"""
secrets.py - Secret and credential scanner nanobot

Scans files recursively for leaked API keys, tokens, passwords, private keys,
and other sensitive credentials using regex pattern matching. Redacts found
values in output. Skips binary files and common noise directories.

Uses only Python stdlib. No external dependencies.

Usage:
    nanobot code/secrets <path> [format]

Examples:
    nanobot code/secrets /path/to/project
    nanobot code/secrets ./src json

Environment:
    NANOBOT_OUTPUT   - Path to write the markdown report
    NANOBOT_RUN_ID   - Unique run identifier
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Directories to always skip
SKIP_DIRS = frozenset({
    ".git", ".svn", ".hg",
    "node_modules", "vendor", "venv", ".venv", "env",
    "__pycache__", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", ".ruff_cache",
    "dist", "build",
    ".terraform", ".serverless",
    "coverage", ".nyc_output", "htmlcov",
    ".next", ".nuxt", ".cache",
    "site-packages",
})

# File extensions to skip (binary / non-text)
SKIP_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mkv", ".mov", ".flac",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".o", ".a",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".exe", ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
    ".jar", ".class", ".war",
    ".lock", ".sum", ".map",
    ".onnx", ".safetensors", ".pt", ".pth", ".h5", ".hdf5",
})

# Files that generate false positives
SKIP_FILES = frozenset({
    "package-lock.json", "yarn.lock", "Cargo.lock",
    "poetry.lock", "Pipfile.lock", "composer.lock",
    "pnpm-lock.yaml", "go.sum",
})

# Placeholder indicators (skip matches containing these)
PLACEHOLDERS = frozenset({
    "example", "placeholder", "your_", "xxx", "changeme",
    "replace", "insert", "todo", "fixme", "dummy", "test",
    "sample", "fake", "mock", "<your", "${", "{{",
})

# Max file size to scan (skip huge files)
MAX_FILE_SIZE = 1_000_000  # 1 MB
MAX_LINE_LENGTH = 2000

# Detection patterns: (name, severity, compiled regex, description)
PATTERNS: list[tuple[str, str, re.Pattern, str]] = [
    # --- Critical ---

    # AWS
    ("AWS Access Key", "critical",
     re.compile(r"(?<![A-Za-z0-9/+=])(AKIA[0-9A-Z]{16})(?![A-Za-z0-9/+=])"),
     "AWS IAM access key ID"),
    ("AWS Secret Key", "critical",
     re.compile(r"""(?i)aws(.{0,20})?['"][0-9a-zA-Z/+]{40}['"]"""),
     "AWS secret access key"),

    # Private Keys
    ("Private Key Header", "critical",
     re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY(?: BLOCK)?-----"),
     "Private key file header"),

    # GCP
    ("GCP API Key", "critical",
     re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
     "Google Cloud API key"),
    ("GCP Service Account", "critical",
     re.compile(r'"type"\s*:\s*"service_account"'),
     "GCP service account JSON file"),
    ("Google OAuth Secret", "critical",
     re.compile(r"GOCSPX-[A-Za-z0-9_\-]{28}"),
     "Google OAuth client secret"),

    # Azure
    ("Azure Storage Key", "critical",
     re.compile(r"AccountKey=([A-Za-z0-9/+=]{88})"),
     "Azure storage account key"),

    # --- High ---

    # GitHub
    ("GitHub Token (classic)", "high",
     re.compile(r"ghp_[A-Za-z0-9]{36}"),
     "GitHub personal access token (classic)"),
    ("GitHub Token (fine-grained)", "high",
     re.compile(r"github_pat_[A-Za-z0-9_]{82}"),
     "GitHub fine-grained personal access token"),
    ("GitHub OAuth", "high",
     re.compile(r"gho_[A-Za-z0-9]{36}"),
     "GitHub OAuth access token"),
    ("GitHub User Token", "high",
     re.compile(r"ghu_[A-Za-z0-9]{36}"),
     "GitHub user-to-server token"),

    # GitLab
    ("GitLab Token", "high",
     re.compile(r"glpat-[A-Za-z0-9\-]{20,}"),
     "GitLab personal access token"),

    # Slack
    ("Slack Token", "high",
     re.compile(r"xox[bporas]-[0-9a-zA-Z\-]{10,}"),
     "Slack API token"),
    ("Slack Webhook", "high",
     re.compile(r"https://hooks\.slack\.com/services/T[A-Z0-9]{8,}/B[A-Z0-9]{8,}/[A-Za-z0-9]{24}"),
     "Slack incoming webhook URL"),

    # Stripe
    ("Stripe Key", "high",
     re.compile(r"(?:sk|pk)_(?:live|test)_[A-Za-z0-9]{20,}"),
     "Stripe API key"),

    # Twilio
    ("Twilio API Key", "high",
     re.compile(r"SK[0-9a-fA-F]{32}"),
     "Twilio API key SID"),

    # SendGrid
    ("SendGrid API Key", "high",
     re.compile(r"SG\.[A-Za-z0-9_-]{22}\.[A-Za-z0-9_-]{43}"),
     "SendGrid API key"),

    # Discord
    ("Discord Token", "high",
     re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}"),
     "Discord bot or user token"),
    ("Discord Webhook", "high",
     re.compile(r"https://discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+"),
     "Discord webhook URL"),

    # JWT
    ("JWT Token", "high",
     re.compile(r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_.+/=]+"),
     "JSON Web Token"),

    # Bearer
    ("Bearer Token", "high",
     re.compile(r"(?i)bearer\s+[A-Za-z0-9\-_.~+/]{20,}"),
     "Bearer authorization token"),

    # NPM
    ("NPM Token", "high",
     re.compile(r"npm_[A-Za-z0-9]{36}"),
     "NPM access token"),

    # PyPI
    ("PyPI Token", "high",
     re.compile(r"pypi-[A-Za-z0-9_-]{50,}"),
     "PyPI API token"),

    # Telegram
    ("Telegram Bot Token", "high",
     re.compile(r"\d{8,10}:[A-Za-z0-9_-]{35}"),
     "Telegram Bot API token"),

    # --- Medium ---

    # Generic patterns
    ("Generic API Key", "medium",
     re.compile(r"""(?i)(api[_\-]?key|apikey)\s*[:=]\s*['"]?[A-Za-z0-9\-_]{20,}"""),
     "Generic API key assignment"),
    ("Generic Secret", "medium",
     re.compile(r"""(?i)(secret|password|passwd|pwd)\s*[:=]\s*['"]?[^\s'"]{8,}"""),
     "Hardcoded secret or password"),
    ("Hex Secret (32+)", "medium",
     re.compile(r"""(?i)(secret|key|token|password)\s*[:=]\s*['"]?[0-9a-f]{32,}"""),
     "Long hex value in secret context"),
    ("Connection String", "medium",
     re.compile(r"""(?i)(mysql|postgres|mongodb|redis|amqp)://[^\s"']+@[^\s"']+"""),
     "Database connection string with credentials"),
    ("Hardcoded IP:Port", "medium",
     re.compile(r"\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}:\d{2,5}\b"),
     "Private IP address with port"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def redact(text: str, keep_start: int = 8, keep_end: int = 4) -> str:
    """Redact a secret, showing only the start and end."""
    if len(text) <= keep_start + keep_end + 3:
        return text[:keep_start] + "..."
    return text[:keep_start] + "..." + text[-keep_end:]


def is_placeholder(match_text: str) -> bool:
    """Check if a match is likely a placeholder or example value."""
    lower = match_text.lower()
    return any(p in lower for p in PLACEHOLDERS)


def is_binary(filepath: Path) -> bool:
    """Quick heuristic to detect binary files."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, PermissionError):
        return True


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

def scan_file(filepath: Path) -> list[dict]:
    """Scan a single file for secrets. Returns list of findings."""
    findings = []

    try:
        content = filepath.read_text(errors="replace")
    except (PermissionError, OSError):
        return findings

    for line_num, line in enumerate(content.splitlines(), 1):
        if not line.strip() or len(line) > MAX_LINE_LENGTH:
            continue

        for name, severity, pattern, description in PATTERNS:
            for match in pattern.finditer(line):
                matched = match.group(0)

                # Skip placeholders and example values
                if is_placeholder(matched):
                    continue

                findings.append({
                    "file": str(filepath),
                    "line": line_num,
                    "type": name,
                    "severity": severity,
                    "description": description,
                    "match": redact(matched),
                    "context": line.strip()[:120],
                })

    return findings


def scan_directory(root: Path) -> tuple[list[dict], int, int]:
    """
    Recursively scan a directory for secrets.
    Returns (findings, files_scanned, files_skipped).
    """
    all_findings = []
    files_scanned = 0
    files_skipped = 0

    if root.is_file():
        if root.suffix.lower() in SKIP_EXTENSIONS or is_binary(root):
            return [], 0, 1
        return scan_file(root), 1, 0

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skipped directories in-place
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.endswith(".egg-info")]

        for filename in sorted(filenames):
            if filename in SKIP_FILES:
                files_skipped += 1
                continue

            filepath = Path(dirpath) / filename

            if filepath.suffix.lower() in SKIP_EXTENSIONS:
                files_skipped += 1
                continue

            try:
                if filepath.stat().st_size > MAX_FILE_SIZE:
                    files_skipped += 1
                    continue
            except OSError:
                files_skipped += 1
                continue

            if is_binary(filepath):
                files_skipped += 1
                continue

            file_findings = scan_file(filepath)
            all_findings.extend(file_findings)
            files_scanned += 1

    return all_findings, files_scanned, files_skipped


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(target: str, findings: list[dict], files_scanned: int, files_skipped: int) -> str:
    """Build the markdown report."""
    run_id = os.environ.get("NANOBOT_RUN_ID", "unknown")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    critical = [f for f in findings if f["severity"] == "critical"]
    high = [f for f in findings if f["severity"] == "high"]
    medium = [f for f in findings if f["severity"] == "medium"]

    lines: list[str] = []
    lines.append("# Secret Scanner Report")
    lines.append("")
    lines.append(f"**Target:** `{target}`  ")
    lines.append(f"**Files scanned:** {files_scanned}  ")
    lines.append(f"**Files skipped:** {files_skipped}  ")
    lines.append(f"**Findings:** {len(findings)}  ")
    lines.append(f"**Generated:** {now}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|----------|-------|")
    lines.append(f"| Critical | {len(critical)} |")
    lines.append(f"| High | {len(high)} |")
    lines.append(f"| Medium | {len(medium)} |")
    lines.append(f"| **Total** | **{len(findings)}** |")
    lines.append("")

    if not findings:
        lines.append("## Result: CLEAN")
        lines.append("")
        lines.append("No secrets or credentials detected in the scanned files.")
    else:
        lines.append("## Result: ALERT")
        lines.append("")

        # Findings by severity
        for severity_label, icon, items in [
            ("Critical", "!!", critical),
            ("High", "!", high),
            ("Medium", "~", medium),
        ]:
            if not items:
                continue

            lines.append(f"### [{icon}] {severity_label}")
            lines.append("")
            for f in items:
                lines.append(f"**{f['type']}** in `{f['file']}` line {f['line']}")
                lines.append(f"- {f['description']}")
                lines.append(f"- Match: `{f['match']}`")
                lines.append("")
    lines.append("")

    # Patterns info
    lines.append("## Coverage")
    lines.append("")
    lines.append(f"Scanned against **{len(PATTERNS)}** patterns covering: "
                 f"AWS, GCP, Azure, GitHub, GitLab, Slack, Stripe, Twilio, "
                 f"SendGrid, Discord, NPM, PyPI, Telegram, JWT, private keys, "
                 f"connection strings, and generic secret assignments.")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*nanobot run `{run_id}` | code/secrets | {now}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print("Usage: nanobot code/secrets <path> [format]", file=sys.stderr)
        print("  path    - Directory or file to scan", file=sys.stderr)
        print("  format  - Output format: markdown (default) or json", file=sys.stderr)
        sys.exit(1)

    target = sys.argv[1]
    output_format = sys.argv[2] if len(sys.argv) > 2 else "markdown"

    target_path = Path(target).resolve()
    if not target_path.exists():
        print(f"Error: path does not exist: {target}", file=sys.stderr)
        sys.exit(1)

    findings, files_scanned, files_skipped = scan_directory(target_path)

    if output_format == "json":
        import json
        result = {
            "target": str(target_path),
            "files_scanned": files_scanned,
            "files_skipped": files_skipped,
            "total_findings": len(findings),
            "findings": findings,
            "run_id": os.environ.get("NANOBOT_RUN_ID", "unknown"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        report = json.dumps(result, indent=2)
    else:
        report = build_report(str(target_path), findings, files_scanned, files_skipped)

    output_path = os.environ.get("NANOBOT_OUTPUT")
    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(report)
    else:
        print(report)

    # Exit non-zero if secrets found (useful for CI pipelines)
    sys.exit(1 if findings else 0)


if __name__ == "__main__":
    main()
