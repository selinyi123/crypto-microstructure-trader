from __future__ import annotations

import json
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

import crypto_microstructure_trader.cli as cli_module
from crypto_microstructure_trader import EventStore

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
PYTHON_EXECUTABLE = getattr(sys, "_base_executable", sys.executable)


def run_cli(*arguments: object) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{SRC_ROOT}{os.pathsep}{current_pythonpath}" if current_pythonpath else str(SRC_ROOT)
    )
    return subprocess.run(
        [
            PYTHON_EXECUTABLE,
            "-m",
            "crypto_microstructure_trader",
            *(str(arg) for arg in arguments),
        ],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def create_demo(tmp_path: Path) -> Path:
    output_dir = tmp_path / "demo"
    result = run_cli("demo", output_dir)
    assert result.returncode == 0, result.stderr
    return output_dir


def test_demo_creates_three_deterministic_event_stores(tmp_path: Path) -> None:
    output_dir = create_demo(tmp_path)

    assert sorted(path.name for path in output_dir.iterdir()) == [
        "run-a.jsonl",
        "run-b.jsonl",
        "run-changed.jsonl",
    ]
    assert (output_dir / "run-a.jsonl").read_bytes() == (output_dir / "run-b.jsonl").read_bytes()
    assert (output_dir / "run-a.jsonl").read_bytes() != (
        output_dir / "run-changed.jsonl"
    ).read_bytes()
    assert "mismatch index 1" in run_cli("demo", output_dir, "--force").stdout


def test_demo_refuses_overwrite_unless_forced(tmp_path: Path) -> None:
    output_dir = create_demo(tmp_path)
    baseline = output_dir / "run-a.jsonl"
    baseline.write_text("do not overwrite\n", encoding="utf-8")

    refused = run_cli("demo", output_dir)
    assert refused.returncode == 2
    assert "refusing to overwrite" in refused.stderr
    assert "Traceback" not in refused.stderr
    assert baseline.read_text(encoding="utf-8") == "do not overwrite\n"

    forced = run_cli("demo", output_dir, "--force")
    assert forced.returncode == 0
    assert baseline.read_text(encoding="utf-8") != "do not overwrite\n"


def test_demo_rejects_target_directory_before_writing_any_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "demo"
    (output_dir / "run-b.jsonl").mkdir(parents=True)

    result = run_cli("demo", output_dir, "--force")
    assert result.returncode == 2
    assert "target is a directory" in result.stderr
    assert not (output_dir / "run-a.jsonl").exists()
    assert not (output_dir / "run-changed.jsonl").exists()


def test_demo_staging_failure_preserves_existing_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = create_demo(tmp_path)
    targets = [output_dir / name for name in cli_module.DEMO_FILENAMES]
    before = {path.name: path.read_bytes() for path in targets}
    original_write = EventStore.write
    write_count = 0

    def fail_second_staged_write(self, events):
        nonlocal write_count
        write_count += 1
        if write_count == 2:
            raise OSError("synthetic staging failure")
        return original_write(self, events)

    monkeypatch.setattr(EventStore, "write", fail_second_staged_write)

    with pytest.raises(OSError, match="synthetic staging failure"):
        cli_module._run_demo(Namespace(output_dir=str(output_dir), force=True))

    assert {path.name: path.read_bytes() for path in targets} == before
    assert not list(tmp_path.glob(".cmt-demo-*"))
    assert not list(output_dir.glob(".cmt-demo-*"))


def test_demo_commit_failure_rolls_back_existing_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = create_demo(tmp_path)
    targets = [output_dir / name for name in cli_module.DEMO_FILENAMES]
    for index, target in enumerate(targets):
        target.write_bytes(f"original-{index}".encode())
    before = {path.name: path.read_bytes() for path in targets}
    original_replace = cli_module._replace_file
    replace_count = 0

    def fail_during_second_install(source: Path, target: Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 4:
            raise OSError("synthetic commit failure")
        original_replace(source, target)

    monkeypatch.setattr(cli_module, "_replace_file", fail_during_second_install)

    with pytest.raises(OSError, match="synthetic commit failure"):
        cli_module._run_demo(Namespace(output_dir=str(output_dir), force=True))

    assert {path.name: path.read_bytes() for path in targets} == before
    assert not list(tmp_path.glob(".cmt-demo-*"))
    assert not list(output_dir.glob(".cmt-demo-*"))


def test_demo_commit_failure_removes_partially_installed_new_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "new-demo"
    original_replace = cli_module._replace_file
    replace_count = 0

    def fail_during_second_install(source: Path, target: Path) -> None:
        nonlocal replace_count
        replace_count += 1
        if replace_count == 2:
            raise OSError("synthetic commit failure")
        original_replace(source, target)

    monkeypatch.setattr(cli_module, "_replace_file", fail_during_second_install)

    with pytest.raises(OSError, match="synthetic commit failure"):
        cli_module._run_demo(Namespace(output_dir=str(output_dir), force=False))

    assert not output_dir.exists()
    assert not list(tmp_path.glob(".cmt-demo-*"))


def test_inspect_json_is_deterministic_and_reports_manifest(tmp_path: Path) -> None:
    output_dir = create_demo(tmp_path)
    path = output_dir / "run-a.jsonl"

    first = run_cli("inspect", path, "--json")
    second = run_cli("inspect", path, "--json")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    assert first.stderr == ""

    report = json.loads(first.stdout)
    assert report == {
        "command": "inspect",
        "event_count": 3,
        "fingerprint": report["fingerprint"],
        "fingerprint_algorithm": "sha256-jsonl-v1",
        "path": str(path),
        "report_version": 1,
    }
    assert len(report["fingerprint"]) == 64


def test_compare_exit_codes_and_first_mismatch(tmp_path: Path) -> None:
    output_dir = create_demo(tmp_path)
    baseline = output_dir / "run-a.jsonl"

    same = run_cli("compare", baseline, output_dir / "run-b.jsonl", "--json")
    assert same.returncode == 0
    same_report = json.loads(same.stdout)
    assert same_report["deterministic"] is True
    assert same_report["first_mismatch_index"] is None
    assert same_report["first_event_count"] == same_report["second_event_count"] == 3
    assert same_report["first_fingerprint"] == same_report["second_fingerprint"]

    changed = run_cli("compare", baseline, output_dir / "run-changed.jsonl", "--json")
    assert changed.returncode == 1
    changed_report = json.loads(changed.stdout)
    assert changed_report["deterministic"] is False
    assert changed_report["first_mismatch_index"] == 1
    assert changed_report["first_fingerprint"] != changed_report["second_fingerprint"]


def test_latency_reports_safe_and_fail_closed_results() -> None:
    safe = run_cli("latency", 10, 20, 30, "--threshold", 100, "--json")
    assert safe.returncode == 0
    safe_report = json.loads(safe.stdout)
    assert safe_report["cancel"] is False
    assert safe_report["stats"]["valid"] is True
    assert safe_report["stats"]["p95_ms"] == 29.0

    slow = run_cli("latency", 100, 200, 300, "--threshold", 150, "--json")
    assert slow.returncode == 1
    assert json.loads(slow.stdout)["cancel"] is True

    invalid = run_cli("latency", 10, "nan", 20, "--threshold", 100, "--json")
    assert invalid.returncode == 1
    invalid_report = json.loads(invalid.stdout)
    assert invalid_report["cancel"] is True
    assert invalid_report["stats"]["valid"] is False
    assert "fail-closed" in invalid_report["reason"]

    sub_rounding_threshold = run_cli("latency", "0.00001", "--threshold", "0", "--json")
    assert sub_rounding_threshold.returncode == 1
    precise_report = json.loads(sub_rounding_threshold.stdout)
    assert precise_report["cancel"] is True
    assert precise_report["stats"]["p95_ms"] == 0.00001

    bad_threshold = run_cli("latency", "nan", "--threshold", "nan", "--json")
    assert bad_threshold.returncode == 2
    assert bad_threshold.stdout == ""
    assert "threshold" in bad_threshold.stderr


def test_data_and_argument_errors_are_concise(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"symbol":\n', encoding="utf-8")

    bad_store = run_cli("inspect", malformed, "--json")
    assert bad_store.returncode == 2
    assert bad_store.stdout == ""
    assert bad_store.stderr.startswith("error: ")
    assert "Traceback" not in bad_store.stderr

    missing = run_cli("inspect", tmp_path / "missing.jsonl")
    assert missing.returncode == 2
    assert "does not exist" in missing.stderr

    bad_sample = run_cli("latency", "not-a-number")
    assert bad_sample.returncode == 2
    assert "Traceback" not in bad_sample.stderr


def test_deeply_nested_json_error_has_no_traceback(tmp_path: Path) -> None:
    path = tmp_path / "deeply-nested.jsonl"
    nested_metadata = "null"
    for _ in range(2_000):
        nested_metadata = f'{{"nested":{nested_metadata}}}'
    path.write_text(
        '{"symbol":"BTC-USDT","timestamp":1,"event_type":"signal",'
        '"action":"observe","strength":0.5,"confidence":0.5,"reason":"test",'
        f'"level_price":null,"invalidation_price":null,"metadata":{nested_metadata}}}\n',
        encoding="utf-8",
    )

    result = run_cli("inspect", path)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "nesting depth" in result.stderr
    assert "Traceback" not in result.stderr
