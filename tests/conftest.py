"""Unit tests never reach the network: `npx` is replaced by an offline stub for the whole session."""

import os
import stat
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def offline_npx(tmp_path_factory: pytest.TempPathFactory):
    """Put a stub `npx` first on PATH so hooks that shell out to claude-flow fail fast and offline.

    The hooks treat a failing claude-flow as "no data", which is what the unit tests assert on. Spawned hook
    processes inherit PATH, so the stub also covers the subprocess-based tests. Real-npx runs belong to
    tests marked `network`, excluded from the unit run.
    """
    bin_dir = tmp_path_factory.mktemp("offline-bin")
    npx = bin_dir / "npx"
    npx.write_text('#!/bin/sh\necho "npx is stubbed in unit tests (offline)" >&2\nexit 1\n')
    npx.chmod(npx.stat().st_mode | stat.S_IEXEC)
    previous = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{previous}"
    yield Path(npx)
    os.environ["PATH"] = previous
