"""
CLI entry point for nanobots.

Usage:
    nanobot list                        List all spaces
    nanobot <space>                     List bots in a space
    nanobot <space>/<bot> [args...]     Run a bot
    nanobot spawn <space>/<bot>         Same as above (explicit)
    nanobot run <space>/<bot>           Same as above
"""

from __future__ import annotations

import argparse
import sys
import json

from nanobots import __version__
from nanobots.core import spawn, Nanobot
from nanobots.registry import list_spaces, list_bots


BANNER = r"""
    ┌─────────────────────────────────┐
    │  ╔╗╔╔═╗╔╗╔╔═╗╔╗  ╔═╗╔╦╗╔═╗   │
    │  ║║║╠═╣║║║║ ║╠╩╗ ║ ║ ║ ╚═╗   │
    │  ╝╚╝╩ ╩╝╚╝╚═╝╚═╝ ╚═╝ ╩ ╚═╝   │
    │  fire and forget micro-agents   │
    └─────────────────────────────────┘
"""


def cmd_list(args):
    """List spaces or bots."""
    if args.target:
        # List bots in a space
        bots = list_bots(args.target)
        if not bots:
            print(f"  No bots found in space '{args.target}'")
            return

        print(f"\n  {args.target}/\n")
        for bot in bots:
            desc = f"  {bot['description']}" if bot["description"] else ""
            print(f"    {bot['name']:<20}{desc}")
        print()
    else:
        # List all spaces
        spaces = list_spaces()
        if not spaces:
            print("  No spaces found. Create a spaces/ directory or set NANOBOT_SPACES_DIR.")
            return

        print(BANNER)
        print("  Spaces:\n")
        for space in spaces:
            tag = f" [{space['source']}]" if space["source"] != "builtin" else ""
            desc = f"  {space['description']}" if space["description"] else ""
            print(f"    {space['name']:<16}{desc}{tag}")
        print(f"\n  Run: nanobot <space>/<bot> [args...]\n")


def cmd_run(args):
    """Run a nanobot."""
    target = args.target

    if "/" not in target:
        # Treat as space listing
        args_ns = argparse.Namespace(target=target)
        cmd_list(args_ns)
        return

    space, bot = target.split("/", 1)

    nanobot = Nanobot(
        space,
        bot,
        args.bot_args,
        timeout=args.timeout,
        self_destruct=args.self_destruct,
        output_dir=args.output,
    )

    result = nanobot.run()

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        status_icon = "OK" if result.ok else "FAIL"
        print(f"\n  [{status_icon}] {result.space}/{result.bot} ({result.run_id})")
        print(f"  Duration: {result.duration_ms}ms")

        if result.report_path:
            print(f"  Report: {result.report_path}")

        if result.stderr and not result.ok:
            print(f"\n  Error:\n  {result.stderr[:500]}")

        if result.report and not args.quiet:
            print(f"\n{'='*60}")
            print(result.report)

    sys.exit(0 if result.ok else 1)


def main():
    parser = argparse.ArgumentParser(
        prog="nanobot",
        description="Fire-and-forget micro-agents for AI systems",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  nanobot list                          List all spaces
  nanobot security                      List bots in security space
  nanobot ops/health                    Run health check
  nanobot security/threat-radar         Run threat radar
  nanobot code/secrets /path/to/scan    Scan for leaked secrets
  nanobot ops/health --self-destruct    Run and clean up all traces
  nanobot ops/health --json             Output result as JSON
""",
    )

    parser.add_argument(
        "-v", "--version",
        action="version",
        version=f"nanobots {__version__}",
    )

    parser.add_argument(
        "target",
        nargs="?",
        help="Space name or space/bot target",
    )

    parser.add_argument(
        "bot_args",
        nargs="*",
        help="Arguments to pass to the bot",
    )

    parser.add_argument(
        "--timeout", "-t",
        type=int,
        default=300,
        help="Max execution time in seconds (default: 300)",
    )

    parser.add_argument(
        "--self-destruct", "-sd",
        action="store_true",
        help="Clean up all traces after execution",
    )

    parser.add_argument(
        "--output", "-o",
        help="Directory to save reports",
    )

    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output result as JSON",
    )

    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress report output",
    )

    args = parser.parse_args()

    if not args.target or args.target == "list":
        args_ns = argparse.Namespace(target=None)
        cmd_list(args_ns)
    elif "/" in args.target:
        cmd_run(args)
    else:
        args_ns = argparse.Namespace(target=args.target)
        cmd_list(args_ns)


if __name__ == "__main__":
    main()
