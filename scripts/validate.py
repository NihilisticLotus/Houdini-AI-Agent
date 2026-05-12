"""Run the local validation suite for Houdini AI Agent.

This script is intentionally plain Python so it can run from a regular Python
interpreter or from Houdini's hython. It verifies imports, syntax, and unit
tests using the same repository checkout.
"""

from __future__ import annotations

import argparse
import compileall
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
PYTHON_LIBS = ROOT / "houdini" / "python3.11libs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Houdini AI Agent.")
    parser.add_argument("--skip-smoke", action="store_true", help="Skip scripts/smoke_import.py.")
    parser.add_argument("--skip-tests", action="store_true", help="Skip unittest discovery.")
    args = parser.parse_args()

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(PYTHON_LIBS) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")

    checks: list[tuple[str, list[str]]] = []
    if not args.skip_smoke:
        checks.append(("smoke import", [sys.executable, str(ROOT / "scripts" / "smoke_import.py")]))
    if not args.skip_tests:
        checks.append(("unit tests", [sys.executable, "-m", "unittest", "discover", "-s", str(ROOT / "tests")]))

    print(f"[validate] root: {ROOT}", flush=True)
    print(f"[validate] python: {sys.executable}", flush=True)
    print("[validate] compileall: houdini/python3.11libs and scripts", flush=True)
    if not compileall.compile_dir(str(PYTHON_LIBS), quiet=1):
        print("[validate] compileall failed for Houdini package", file=sys.stderr)
        return 1
    if not compileall.compile_dir(str(ROOT / "scripts"), quiet=1):
        print("[validate] compileall failed for scripts", file=sys.stderr)
        return 1

    for label, command in checks:
        print(f"[validate] running {label}", flush=True)
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if completed.stdout:
            print(completed.stdout, end="", flush=True)
        if completed.returncode != 0:
            print(f"[validate] {label} failed with exit code {completed.returncode}", file=sys.stderr)
            return completed.returncode

    print("[validate] all checks passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
