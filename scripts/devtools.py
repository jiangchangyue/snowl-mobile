#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_command(argv: list[str], *, pythonpath: bool = False) -> int:
    env = os.environ.copy()
    if pythonpath:
        src_path = str(ROOT / "src")
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    completed = subprocess.run(argv, cwd=ROOT, env=env, check=False)
    return completed.returncode


def format_command() -> int:
    print("Phase 0 stub: no formatter is vendored yet. Keep using `make format` as the stable hook.")
    return 0


def lint_command() -> int:
    return run_command(
        [sys.executable, "-m", "compileall", "-q", "src", "tests", "scripts"],
        pythonpath=True,
    )


def test_command() -> int:
    return run_command(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-t",
            ".",
            "-p",
            "test_*.py",
        ],
        pythonpath=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("usage: devtools.py [format|lint|test]", file=sys.stderr)
        return 1

    command = args[0]
    if command == "format":
        return format_command()
    if command == "lint":
        return lint_command()
    if command == "test":
        return test_command()

    print(f"unknown command: {command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
