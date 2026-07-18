from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys

from reframe_agent_host.baml_artifacts import normalize_generated_output


_WORKSPACE_TESTS = (
    "::manual workspace policy is deterministic",
    "::manual checkpoint retains only explicit paths",
    "::empty manual selections stay empty",
)


def generate() -> None:
    root = _project_root()
    generated = root / "src" / "baml_sdk"
    _generate_and_normalize(root, generated)


def check() -> None:
    root = _project_root()
    generated = root / "src" / "baml_sdk"
    before = _tree_hashes(generated)
    _generate_and_normalize(root, generated)
    after = _tree_hashes(generated)
    changed = sorted(
        path
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    )
    if changed:
        print("BAML generated output was stale:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        raise SystemExit(1)


def _generate_and_normalize(root: Path, generated: Path) -> None:
    _run(root, "baml", "check")
    for test in _WORKSPACE_TESTS:
        _run(root, "baml", "test", "-i", test)
    _run(root, "baml", "generate")
    normalize_generated_output(generated)


def _project_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (
            (candidate / "baml.toml").is_file()
            and (candidate / "baml_src").is_dir()
            and (candidate / "src" / "baml_sdk").is_dir()
        ):
            return candidate
    raise RuntimeError(
        "BAML generation requires an Agent Host developer checkout; "
        "run this command from agent-host or one of its subdirectories"
    )


def _run(root: Path, *command: str) -> None:
    subprocess.run(command, cwd=root, check=True)


def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


if __name__ == "__main__":
    check()
