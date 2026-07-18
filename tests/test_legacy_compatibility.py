from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
LEGACY_ROOT = REPOSITORY_ROOT / "modules" / "event-simulation-core"
PYTHON_EXECUTABLE = getattr(sys, "_base_executable", sys.executable)


def run_without_site(source: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [PYTHON_EXECUTABLE, "-S", "-c", source],
        cwd=LEGACY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_legacy_simulator_import_works_without_installed_package() -> None:
    result = run_without_site(
        "from simulator import Event, EventScorer; "
        "decision = EventScorer().score(Event('legacy', 0.8, 1)); "
        "assert decision.action == 'accept'"
    )

    assert result.returncode == 0, result.stderr


def test_legacy_replay_imports_work_without_installed_package() -> None:
    result = run_without_site(
        "from replay.event_store import EventStore, StoredEvent; "
        "from replay.latency_model import LatencyModel; "
        "from replay.replay_validator import ReplayValidator; "
        "event = StoredEvent('BTC-USDT', 1, 'test', 'observe', 0.5, 0.5, 'legacy'); "
        "assert EventStore.fingerprint([event]); "
        "assert LatencyModel().summarize([10]).valid; "
        "assert ReplayValidator().compare([event], [event]).deterministic"
    )

    assert result.returncode == 0, result.stderr


def test_legacy_simulator_can_run_as_script() -> None:
    result = subprocess.run(
        [PYTHON_EXECUTABLE, "-S", str(LEGACY_ROOT / "simulator.py")],
        cwd=LEGACY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "accept" in result.stdout
