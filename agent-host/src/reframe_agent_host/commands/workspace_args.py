from __future__ import annotations

import argparse


def add_workspace_parser(subparsers) -> None:
    workspace = subparsers.add_parser(
        "workspace",
        help="Manage projected agent task workspaces.",
    )
    areas = workspace.add_subparsers(dest="workspace_area", required=True)
    _add_memory_parser(areas)
    _add_session_parser(areas)


def _add_memory_parser(areas) -> None:
    memory = areas.add_parser("memory", help="Manage filesystem memory sources.")
    commands = memory.add_subparsers(dest="workspace_action", required=True)
    commands.add_parser(
        "create",
        help="Register the current project as a filesystem memory.",
    )
    commands.add_parser("list", help="List filesystem memory nodes.")


def _add_session_parser(areas) -> None:
    session = areas.add_parser("session", help="Manage agent task sessions.")
    commands = session.add_subparsers(dest="workspace_action", required=True)

    create = commands.add_parser("create", help="Create a projected task session.")
    create.add_argument("--memory", action="append", default=[])
    create.add_argument(
        "--continue",
        dest="continue_session",
        nargs="?",
        const="latest",
        help="Continue the latest checkpoint, or the supplied session ID.",
    )

    commands.add_parser(
        "shortcut",
        help="Create this machine's native sessions-folder shortcut.",
    )

    status = commands.add_parser("status", help="Show session state and journal.")
    _add_session_selector(status)

    checkpoint = commands.add_parser(
        "checkpoint",
        help="Retain selected changes in an immutable checkpoint.",
    )
    _add_session_selector(checkpoint)
    checkpoint.add_argument("--include", action="append", default=[])
    checkpoint.add_argument("--all", action="store_true")

    execute = commands.add_parser("exec", help="Run a command in the mounted VFS.")
    _add_session_selector(execute)
    execute.add_argument("exec_command", nargs=argparse.REMAINDER)

    shell = commands.add_parser("shell", help="Open a shell in the mounted VFS.")
    _add_session_selector(shell)

    close = commands.add_parser("close", help="Close a task session.")
    _add_session_selector(close)

    destroy = commands.add_parser(
        "destroy",
        help="Remove a session's ephemeral worktree and scratch data.",
    )
    _add_session_selector(destroy)


def _add_session_selector(parser) -> None:
    parser.add_argument(
        "--session",
        help="Override automatic latest-session selection.",
    )
