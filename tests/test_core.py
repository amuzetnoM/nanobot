"""Tests for nanobots core functionality."""

import os
import tempfile
from pathlib import Path

import pytest

from nanobots.core import Nanobot, NanobotResult, spawn, spawn_async
from nanobots.registry import list_spaces, list_bots, resolve_bot


class TestNanobotResult:
    def test_ok_when_success(self):
        result = NanobotResult(
            run_id="test1234",
            space="test",
            bot="dummy",
            status="success",
            exit_code=0,
            stdout="ok",
            stderr="",
            report="# Report",
            report_path=None,
            duration_ms=100,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert result.ok is True

    def test_not_ok_on_error(self):
        result = NanobotResult(
            run_id="test1234",
            space="test",
            bot="dummy",
            status="error",
            exit_code=1,
            stdout="",
            stderr="failed",
            report=None,
            report_path=None,
            duration_ms=50,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert result.ok is False

    def test_not_ok_on_nonzero_exit(self):
        result = NanobotResult(
            run_id="test1234",
            space="test",
            bot="dummy",
            status="success",
            exit_code=1,
            stdout="",
            stderr="",
            report=None,
            report_path=None,
            duration_ms=50,
            timestamp="2026-01-01T00:00:00Z",
        )
        assert result.ok is False

    def test_to_dict(self):
        result = NanobotResult(
            run_id="abc",
            space="ops",
            bot="health",
            status="success",
            exit_code=0,
            stdout="",
            stderr="",
            report=None,
            report_path=None,
            duration_ms=200,
            timestamp="2026-01-01T00:00:00Z",
        )
        d = result.to_dict()
        assert d["run_id"] == "abc"
        assert d["space"] == "ops"
        assert d["status"] == "success"


class TestRegistry:
    def test_list_spaces_returns_builtin(self):
        spaces = list_spaces()
        names = [s["name"] for s in spaces]
        assert "ops" in names
        assert "security" in names
        assert "code" in names

    def test_list_bots_ops(self):
        bots = list_bots("ops")
        names = [b["name"] for b in bots]
        assert "health" in names

    def test_resolve_builtin_bot(self):
        path = resolve_bot("ops", "health")
        assert path is not None
        assert path.exists()
        assert path.suffix == ".py"

    def test_resolve_nonexistent_bot(self):
        path = resolve_bot("ops", "nonexistent_bot_xyz")
        assert path is None


class TestSpawn:
    def test_spawn_nonexistent_returns_error(self):
        result = spawn("fake/nonexistent")
        assert not result.ok
        assert "not found" in result.stderr.lower()

    def test_spawn_invalid_target_raises(self):
        with pytest.raises(ValueError, match="space/bot"):
            spawn("invalid-no-slash")

    def test_spawn_ops_health(self):
        """Integration test: actually run ops/health."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawn("ops/health", output_dir=tmpdir)
            assert result.status in ("success", "error")
            assert result.run_id
            assert result.duration_ms >= 0
            # On Linux, health should succeed
            if os.name == "posix":
                assert result.ok
                assert result.report is not None
                assert "Health" in result.report

    def test_spawn_self_destruct(self):
        """Self-destruct should still return report content but no file."""
        result = spawn("ops/health", self_destruct=True)
        if result.ok:
            assert result.report is not None
            assert result.report_path is None  # File was deleted


class TestSpawnAsync:
    def test_async_spawn_and_wait(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            handle = spawn_async("ops/health", output_dir=tmpdir)
            assert handle.run_id
            result = handle.wait()
            assert result.run_id == handle.run_id
            if os.name == "posix":
                assert result.ok

    def test_async_poll(self):
        handle = spawn_async("ops/health", self_destruct=True)
        # Poll might return None (still running) or result (fast)
        import time
        for _ in range(50):
            result = handle.poll()
            if result is not None:
                break
            time.sleep(0.1)
        # Should finish within 5 seconds
        if result is None:
            result = handle.wait()
        assert result is not None

    def test_async_invalid_target_raises(self):
        with pytest.raises(ValueError):
            spawn_async("no-slash")


class TestNanobot:
    def test_custom_timeout(self):
        bot = Nanobot("ops", "health", timeout=5)
        assert bot.timeout == 5

    def test_custom_env(self):
        bot = Nanobot("ops", "health", env={"CUSTOM_VAR": "hello"})
        assert bot.extra_env["CUSTOM_VAR"] == "hello"

    def test_run_nonexistent(self):
        bot = Nanobot("fake", "nonexistent")
        result = bot.run()
        assert not result.ok
