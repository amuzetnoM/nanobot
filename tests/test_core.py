"""Tests for nanobots core functionality."""

import os
import tempfile
import time
from pathlib import Path

import pytest

from nanobots.core import Nanobot, NanobotResult, spawn, spawn_async, _should_auto_destruct
from nanobots.registry import list_spaces, list_bots, resolve_bot, get_bot_meta


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
        assert "destructed" in d
        assert d["destructed"] is False

    def test_to_dict_destructed(self):
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
            destructed=True,
        )
        d = result.to_dict()
        assert d["destructed"] is True

    def test_repr_includes_destructed(self):
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
            destructed=True,
        )
        assert "DESTRUCTED" in repr(result)


class TestAutoDestructLogic:
    def test_auto_destruct_simple_task(self):
        """Short duration, exit 0, small report → should auto-destruct."""
        result = NanobotResult(
            run_id="a", space="ops", bot="health", status="success",
            exit_code=0, stdout="", stderr="", report="small report",
            report_path=None, duration_ms=500, timestamp="",
        )
        assert _should_auto_destruct(result) is True

    def test_auto_destruct_no_report(self):
        """No report at all → should auto-destruct (report size is 0)."""
        result = NanobotResult(
            run_id="a", space="ops", bot="health", status="success",
            exit_code=0, stdout="", stderr="", report=None,
            report_path=None, duration_ms=100, timestamp="",
        )
        assert _should_auto_destruct(result) is True

    def test_no_auto_destruct_on_failure(self):
        """Non-zero exit → should NOT auto-destruct."""
        result = NanobotResult(
            run_id="a", space="ops", bot="health", status="error",
            exit_code=1, stdout="", stderr="err", report="report",
            report_path=None, duration_ms=100, timestamp="",
        )
        assert _should_auto_destruct(result) is False

    def test_no_auto_destruct_long_duration(self):
        """Long duration → should NOT auto-destruct."""
        result = NanobotResult(
            run_id="a", space="ops", bot="health", status="success",
            exit_code=0, stdout="", stderr="", report="report",
            report_path=None, duration_ms=10000, timestamp="",
        )
        assert _should_auto_destruct(result) is False

    def test_no_auto_destruct_large_report(self):
        """Large report → should NOT auto-destruct."""
        big_report = "x" * (11 * 1024)  # 11 KB
        result = NanobotResult(
            run_id="a", space="ops", bot="health", status="success",
            exit_code=0, stdout="", stderr="", report=big_report,
            report_path=None, duration_ms=100, timestamp="",
        )
        assert _should_auto_destruct(result) is False


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

    def test_list_bots_includes_destruct(self):
        bots = list_bots("ops")
        for b in bots:
            assert "destruct" in b

    def test_resolve_builtin_bot(self):
        path = resolve_bot("ops", "health")
        assert path is not None
        assert path.exists()
        assert path.suffix == ".py"

    def test_resolve_nonexistent_bot(self):
        path = resolve_bot("ops", "nonexistent_bot_xyz")
        assert path is None

    def test_get_bot_meta_existing(self):
        meta = get_bot_meta("ops", "health")
        assert meta is not None
        assert "description" in meta

    def test_get_bot_meta_nonexistent(self):
        meta = get_bot_meta("ops", "nonexistent_bot_xyz")
        assert meta is None

    def test_get_bot_meta_nonexistent_space(self):
        meta = get_bot_meta("fakespace999", "fakebot")
        assert meta is None


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
            assert result.destructed is True

    def test_spawn_destruct_policy_on(self):
        """destruct_policy='on' should destruct."""
        result = spawn("ops/health", destruct_policy="on")
        if result.ok:
            assert result.destructed is True
            assert result.report is not None
            assert result.report_path is None

    def test_spawn_destruct_policy_off(self):
        """destruct_policy='off' should NOT destruct."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawn("ops/health", destruct_policy="off", output_dir=tmpdir)
            if result.ok:
                assert result.destructed is False
                assert result.report_path is not None
                assert result.report_path.exists()

    def test_spawn_destruct_policy_auto_quick_task(self):
        """Auto-destruct on a quick, successful, small-report task."""
        result = spawn("ops/health", destruct_policy="auto")
        if result.ok and result.duration_ms < 5000:
            assert result.destructed is True

    def test_spawn_full_destruct(self):
        """Full destruct should write a tombstone."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawn("ops/health", full_destruct=True, destruct_policy="on", output_dir=tmpdir)
            if result.ok:
                assert result.destructed is True
                assert result.report is not None  # content still in memory
                assert result.report_path is None  # file deleted
                # Check tombstone exists
                tombstones = list(Path(tmpdir).glob("*.tombstone"))
                assert len(tombstones) == 1
                content = tombstones[0].read_text()
                assert result.run_id in content
                assert "DESTRUCTED" in content

    def test_spawn_on_destruct_callback(self):
        """on_destruct callback should fire."""
        callback_results = []

        def my_callback(result):
            callback_results.append(result.run_id)

        result = spawn("ops/health", destruct_policy="on", on_destruct=my_callback)
        if result.ok:
            assert len(callback_results) == 1
            assert callback_results[0] == result.run_id

    def test_spawn_on_destruct_callback_not_called_when_off(self):
        """on_destruct should NOT fire when destruct is off."""
        callback_results = []

        def my_callback(result):
            callback_results.append(result.run_id)

        result = spawn("ops/health", destruct_policy="off", on_destruct=my_callback)
        assert len(callback_results) == 0

    def test_spawn_report_ttl(self):
        """Report TTL should schedule deletion."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = spawn("ops/health", output_dir=tmpdir, report_ttl=1)
            if result.ok:
                assert result.report is not None
                assert result.report_path is not None
                # File should exist right now
                assert result.report_path.exists()
                # Wait for TTL to expire
                time.sleep(2)
                assert not result.report_path.exists()


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

    def test_async_destruct_policy_on(self):
        handle = spawn_async("ops/health", destruct_policy="on")
        result = handle.wait()
        if result.ok:
            assert result.destructed is True


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

    def test_destruct_policy_default_off(self):
        # A bot with no space.yaml destruct default should be "off"
        bot = Nanobot("fake_space_no_yaml", "no_bot")
        assert bot.destruct_policy == "off"

    def test_destruct_policy_from_space_yaml(self):
        # ops/health has destruct: auto in space.yaml
        bot = Nanobot("ops", "health")
        assert bot.destruct_policy == "auto"

    def test_destruct_policy_explicit(self):
        bot = Nanobot("ops", "health", destruct_policy="auto")
        assert bot.destruct_policy == "auto"

    def test_self_destruct_implies_policy_on(self):
        # self_destruct=True on a bot with no yaml default → "on"
        bot = Nanobot("fake_space_no_yaml", "no_bot", self_destruct=True)
        assert bot.destruct_policy == "on"

    def test_explicit_policy_overrides_self_destruct(self):
        bot = Nanobot("ops", "health", self_destruct=True, destruct_policy="auto")
        assert bot.destruct_policy == "auto"

    def test_full_destruct_flag(self):
        bot = Nanobot("ops", "health", full_destruct=True)
        assert bot.full_destruct is True

    def test_report_ttl_field(self):
        bot = Nanobot("ops", "health", report_ttl=30)
        assert bot.report_ttl == 30

    def test_on_destruct_field(self):
        callback = lambda r: None
        bot = Nanobot("ops", "health", on_destruct=callback)
        assert bot.on_destruct is callback


class TestDestructWithSpaceYaml:
    """Test that space.yaml destruct defaults are respected."""

    def test_space_yaml_destruct_default(self):
        """Create a temp space with destruct: auto and verify it's picked up."""
        import yaml

        with tempfile.TemporaryDirectory() as tmpdir:
            space_dir = Path(tmpdir) / "spaces" / "testspace"
            space_dir.mkdir(parents=True)

            # Write space.yaml with destruct default
            space_yaml = {
                "name": "testspace",
                "description": "Test space",
                "version": "1.0",
                "bots": {
                    "mybot": {
                        "description": "Test bot",
                        "destruct": "auto",
                    }
                },
            }
            (space_dir / "space.yaml").write_text(yaml.dump(space_yaml))

            # Write a simple bot
            (space_dir / "mybot.py").write_text(
                '#!/usr/bin/env python3\nimport os; from pathlib import Path\n'
                'Path(os.environ["NANOBOT_OUTPUT"]).write_text("# Test\\n")\n'
            )

            # Set env to find our space
            old_env = os.environ.get("NANOBOT_SPACES_DIR")
            os.environ["NANOBOT_SPACES_DIR"] = str(Path(tmpdir) / "spaces")
            try:
                bot = Nanobot("testspace", "mybot")
                assert bot.destruct_policy == "auto"

                # Explicit override should win
                bot2 = Nanobot("testspace", "mybot", destruct_policy="off")
                assert bot2.destruct_policy == "off"
            finally:
                if old_env is not None:
                    os.environ["NANOBOT_SPACES_DIR"] = old_env
                else:
                    del os.environ["NANOBOT_SPACES_DIR"]
