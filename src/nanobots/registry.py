"""
Bot registry. Discovers and resolves nanobot spaces and bots.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Optional

import yaml


# Look for spaces in multiple locations (in priority order):
# 1. User-defined NANOBOT_SPACES_DIR env var
# 2. ./spaces/ relative to cwd
# 3. Built-in spaces shipped with the package

def _builtin_spaces_dir() -> Path:
    """Path to built-in spaces shipped with nanobots."""
    return Path(__file__).parent / "spaces"


def _user_spaces_dirs() -> list[Path]:
    """User-configured space directories."""
    import os

    dirs = []

    # Environment variable
    env_dir = os.environ.get("NANOBOT_SPACES_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            dirs.append(p)

    # Current working directory
    cwd_spaces = Path.cwd() / "spaces"
    if cwd_spaces.is_dir():
        dirs.append(cwd_spaces)

    return dirs


def _all_spaces_dirs() -> list[Path]:
    """All space directories, user-defined first, built-in last."""
    dirs = _user_spaces_dirs()
    builtin = _builtin_spaces_dir()
    if builtin.is_dir():
        dirs.append(builtin)
    return dirs


def resolve_bot(space: str, bot: str) -> Optional[Path]:
    """
    Find the bot script for a given space/bot combination.
    Searches user dirs first, then built-in spaces.

    Returns the Path to the bot script, or None if not found.
    """
    for spaces_dir in _all_spaces_dirs():
        # Try .py first, then .sh
        for ext in (".py", ".sh"):
            candidate = spaces_dir / space / f"{bot}{ext}"
            if candidate.exists():
                return candidate

        # Try default handler
        default = spaces_dir / space / "default.py"
        if default.exists():
            return default

    return None


def list_spaces() -> list[dict]:
    """
    List all available nanobot spaces with their metadata.

    Returns list of dicts with keys: name, description, path, source
    """
    seen = set()
    spaces = []

    for spaces_dir in _all_spaces_dirs():
        if not spaces_dir.is_dir():
            continue

        source = "builtin" if spaces_dir == _builtin_spaces_dir() else "user"

        for entry in sorted(spaces_dir.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("_") or entry.name.startswith("."):
                continue
            if entry.name in seen:
                continue

            seen.add(entry.name)

            # Try to load space.yaml for metadata
            meta = _load_space_yaml(entry / "space.yaml")

            spaces.append(
                {
                    "name": entry.name,
                    "description": meta.get("description", ""),
                    "path": str(entry),
                    "source": source,
                    "version": meta.get("version", ""),
                }
            )

    return spaces


def list_bots(space: str) -> list[dict]:
    """
    List all bots in a given space.

    Returns list of dicts with keys: name, description, path, type
    """
    bots = []
    seen = set()

    for spaces_dir in _all_spaces_dirs():
        space_dir = spaces_dir / space
        if not space_dir.is_dir():
            continue

        # Load space.yaml for bot descriptions
        meta = _load_space_yaml(space_dir / "space.yaml")
        bot_meta = meta.get("bots", {})

        for script in sorted(space_dir.iterdir()):
            if script.name.startswith("_") or script.name.startswith("."):
                continue
            if script.name in ("default.py", "space.yaml"):
                continue
            if script.suffix not in (".py", ".sh"):
                continue
            if script.stem in seen:
                continue

            seen.add(script.stem)

            bot_info = bot_meta.get(script.stem, {})
            bots.append(
                {
                    "name": script.stem,
                    "description": bot_info.get("description", ""),
                    "path": str(script),
                    "type": script.suffix[1:],
                    "args": bot_info.get("args", []),
                    "schedule": bot_info.get("schedule", ""),
                }
            )

    return bots


def get_bot(space: str, bot: str) -> Optional[dict]:
    """Get metadata for a specific bot."""
    for b in list_bots(space):
        if b["name"] == bot:
            return b
    return None


def _load_space_yaml(path: Path) -> dict:
    """Load a space.yaml file, returning empty dict on failure."""
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}
