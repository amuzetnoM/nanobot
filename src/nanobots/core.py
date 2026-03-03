"""
Core engine. Spawn nanobots, get results, clean up.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from nanobots.registry import resolve_bot


@dataclass
class NanobotResult:
    """Result from a nanobot execution."""

    run_id: str
    space: str
    bot: str
    status: str  # "success", "error", "timeout"
    exit_code: int
    stdout: str
    stderr: str
    report: Optional[str]  # markdown report content
    report_path: Optional[Path]
    duration_ms: int
    timestamp: str
    metadata: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == "success" and self.exit_code == 0

    def __repr__(self) -> str:
        emoji = "+" if self.ok else "x"
        return f"[{emoji}] {self.space}/{self.bot} ({self.run_id}) {self.status} in {self.duration_ms}ms"

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "space": self.space,
            "bot": self.bot,
            "status": self.status,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
            "report_path": str(self.report_path) if self.report_path else None,
            "metadata": self.metadata,
        }


class Nanobot:
    """
    A single nanobot instance. Configurable before launch.

    Usage:
        bot = Nanobot("security", "threat-radar")
        bot.timeout = 120
        bot.self_destruct = True
        result = bot.run()
    """

    def __init__(
        self,
        space: str,
        bot: str,
        args: list[str] | None = None,
        *,
        timeout: int = 300,
        self_destruct: bool = False,
        output_dir: str | Path | None = None,
        env: dict[str, str] | None = None,
    ):
        self.space = space
        self.bot = bot
        self.args = args or []
        self.timeout = timeout
        self.self_destruct = self_destruct
        self.output_dir = Path(output_dir) if output_dir else None
        self.extra_env = env or {}

        self.run_id = hashlib.md5(
            f"{space}-{bot}-{time.time()}-{os.getpid()}".encode()
        ).hexdigest()[:8]

        self._result: NanobotResult | None = None

    def run(self) -> NanobotResult:
        """Execute the nanobot synchronously. Returns result."""
        bot_path = resolve_bot(self.space, self.bot)
        if bot_path is None:
            return NanobotResult(
                run_id=self.run_id,
                space=self.space,
                bot=self.bot,
                status="error",
                exit_code=-1,
                stdout="",
                stderr=f"Bot not found: {self.space}/{self.bot}",
                report=None,
                report_path=None,
                duration_ms=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        # Prepare output location
        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            report_path = self.output_dir / f"{self.space}-{self.bot}-{self.run_id}.md"
        else:
            report_path = Path(tempfile.mktemp(suffix=".md", prefix=f"nanobot-{self.run_id}-"))

        # Build environment
        env = os.environ.copy()
        env.update(
            {
                "NANOBOT_RUN_ID": self.run_id,
                "NANOBOT_SPACE": self.space,
                "NANOBOT_BOT": self.bot,
                "NANOBOT_OUTPUT": str(report_path),
                "NANOBOT_SELF_DESTRUCT": "1" if self.self_destruct else "0",
            }
        )
        # Pass the caller's cwd so bots can resolve relative paths
        env["NANOBOT_CALLER_CWD"] = os.getcwd()
        env.update(self.extra_env)

        # Determine command (use absolute path so cwd doesn't matter)
        if bot_path.suffix == ".py":
            cmd = [sys.executable, str(bot_path.resolve())] + self.args
        elif bot_path.suffix == ".sh":
            cmd = ["bash", str(bot_path.resolve())] + self.args
        else:
            cmd = [str(bot_path.resolve())] + self.args

        # Execute in caller's cwd so relative paths work naturally
        start = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
            )
            status = "success" if proc.returncode == 0 else "error"
            exit_code = proc.returncode
            stdout = proc.stdout
            stderr = proc.stderr
        except subprocess.TimeoutExpired:
            status = "timeout"
            exit_code = -1
            stdout = ""
            stderr = f"Timed out after {self.timeout}s"
        except Exception as e:
            status = "error"
            exit_code = -1
            stdout = ""
            stderr = str(e)

        duration_ms = int((time.monotonic() - start) * 1000)

        # Read report if generated
        report_content = None
        actual_report_path = None
        if report_path.exists():
            report_content = report_path.read_text()
            actual_report_path = report_path

        # Self-destruct: clean up temp files
        if self.self_destruct:
            if report_path.exists() and not self.output_dir:
                report_path.unlink(missing_ok=True)
                actual_report_path = None

        self._result = NanobotResult(
            run_id=self.run_id,
            space=self.space,
            bot=self.bot,
            status=status,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            report=report_content,
            report_path=actual_report_path,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        return self._result


class AsyncNanobot:
    """
    Background nanobot. Spawns and returns immediately.

    Usage:
        handle = AsyncNanobot("ops", "health").launch()
        # ... do other work ...
        result = handle.poll()  # None if still running
        result = handle.wait()  # blocks until done
    """

    def __init__(
        self,
        space: str,
        bot: str,
        args: list[str] | None = None,
        *,
        timeout: int = 300,
        self_destruct: bool = False,
        output_dir: str | Path | None = None,
        env: dict[str, str] | None = None,
    ):
        self.space = space
        self.bot = bot
        self.args = args or []
        self.timeout = timeout
        self.self_destruct = self_destruct
        self.output_dir = Path(output_dir) if output_dir else None
        self.extra_env = env or {}

        self.run_id = hashlib.md5(
            f"{space}-{bot}-{time.time()}-{os.getpid()}".encode()
        ).hexdigest()[:8]

        self._process: subprocess.Popen | None = None
        self._report_path: Path | None = None
        self._start_time: float = 0

    def launch(self) -> "AsyncNanobot":
        """Launch the nanobot in the background. Returns self for chaining."""
        bot_path = resolve_bot(self.space, self.bot)
        if bot_path is None:
            raise FileNotFoundError(f"Bot not found: {self.space}/{self.bot}")

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._report_path = self.output_dir / f"{self.space}-{self.bot}-{self.run_id}.md"
        else:
            self._report_path = Path(
                tempfile.mktemp(suffix=".md", prefix=f"nanobot-{self.run_id}-")
            )

        env = os.environ.copy()
        env.update(
            {
                "NANOBOT_RUN_ID": self.run_id,
                "NANOBOT_SPACE": self.space,
                "NANOBOT_BOT": self.bot,
                "NANOBOT_OUTPUT": str(self._report_path),
                "NANOBOT_SELF_DESTRUCT": "1" if self.self_destruct else "0",
            }
        )
        env["NANOBOT_CALLER_CWD"] = os.getcwd()
        env.update(self.extra_env)

        if bot_path.suffix == ".py":
            cmd = [sys.executable, str(bot_path.resolve())] + self.args
        elif bot_path.suffix == ".sh":
            cmd = ["bash", str(bot_path.resolve())] + self.args
        else:
            cmd = [str(bot_path.resolve())] + self.args

        self._start_time = time.monotonic()
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        return self

    def poll(self) -> NanobotResult | None:
        """Check if done. Returns result or None if still running."""
        if self._process is None:
            raise RuntimeError("Not launched yet. Call .launch() first.")

        retcode = self._process.poll()
        if retcode is None:
            return None

        return self._collect(retcode)

    def wait(self) -> NanobotResult:
        """Block until done. Returns result."""
        if self._process is None:
            raise RuntimeError("Not launched yet. Call .launch() first.")

        try:
            self._process.wait(timeout=self.timeout)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
            duration_ms = int((time.monotonic() - self._start_time) * 1000)
            return NanobotResult(
                run_id=self.run_id,
                space=self.space,
                bot=self.bot,
                status="timeout",
                exit_code=-1,
                stdout="",
                stderr=f"Timed out after {self.timeout}s",
                report=None,
                report_path=None,
                duration_ms=duration_ms,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        return self._collect(self._process.returncode)

    def kill(self) -> None:
        """Kill the running nanobot."""
        if self._process and self._process.poll() is None:
            self._process.kill()

    def _collect(self, retcode: int) -> NanobotResult:
        duration_ms = int((time.monotonic() - self._start_time) * 1000)
        stdout = self._process.stdout.read().decode("utf-8", errors="replace") if self._process.stdout else ""
        stderr = self._process.stderr.read().decode("utf-8", errors="replace") if self._process.stderr else ""

        report_content = None
        report_path = None
        if self._report_path and self._report_path.exists():
            report_content = self._report_path.read_text()
            report_path = self._report_path

        if self.self_destruct and self._report_path and self._report_path.exists() and not self.output_dir:
            self._report_path.unlink(missing_ok=True)
            report_path = None

        return NanobotResult(
            run_id=self.run_id,
            space=self.space,
            bot=self.bot,
            status="success" if retcode == 0 else "error",
            exit_code=retcode,
            stdout=stdout,
            stderr=stderr,
            report=report_content,
            report_path=report_path,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


def spawn(
    target: str,
    args: list[str] | None = None,
    *,
    timeout: int = 300,
    self_destruct: bool = False,
    output_dir: str | Path | None = None,
) -> NanobotResult:
    """
    Fire-and-forget nanobot spawn. The simplest API.

    Args:
        target: "space/bot" string, e.g. "security/threat-radar"
        args: Arguments to pass to the bot
        timeout: Max execution time in seconds
        self_destruct: Clean up all traces after execution
        output_dir: Where to save reports (temp dir if None)

    Returns:
        NanobotResult with status, report, and metadata

    Example:
        result = spawn("ops/health")
        if result.ok:
            print(result.report)
    """
    if "/" not in target:
        raise ValueError(f"Target must be 'space/bot', got: {target}")

    space, bot = target.split("/", 1)
    nanobot = Nanobot(
        space, bot, args,
        timeout=timeout,
        self_destruct=self_destruct,
        output_dir=output_dir,
    )
    return nanobot.run()


def spawn_async(
    target: str,
    args: list[str] | None = None,
    *,
    timeout: int = 300,
    self_destruct: bool = False,
    output_dir: str | Path | None = None,
) -> AsyncNanobot:
    """
    Launch a nanobot in the background. Returns immediately.

    Args:
        target: "space/bot" string
        args: Arguments to pass
        timeout: Max time before kill
        self_destruct: Clean up after done
        output_dir: Report destination

    Returns:
        AsyncNanobot handle. Use .poll() or .wait() to get result.

    Example:
        handle = spawn_async("security/threat-radar")
        # ... do other things ...
        result = handle.wait()
    """
    if "/" not in target:
        raise ValueError(f"Target must be 'space/bot', got: {target}")

    space, bot = target.split("/", 1)
    handle = AsyncNanobot(
        space, bot, args,
        timeout=timeout,
        self_destruct=self_destruct,
        output_dir=output_dir,
    )
    handle.launch()
    return handle
