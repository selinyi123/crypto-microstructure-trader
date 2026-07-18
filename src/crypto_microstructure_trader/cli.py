"""Command-line interface for the offline Replay Lab.

The CLI intentionally stays small: it exercises the deterministic storage,
comparison, and latency primitives without implying that this package is a
market simulator or trading system.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .replay.event_store import EventStore, StoredEvent
from .replay.latency_model import LatencyModel
from .replay.replay_validator import ReplayValidator

REPORT_VERSION = 1
DEMO_FILENAMES = ("run-a.jsonl", "run-b.jsonl", "run-changed.jsonl")


def _demo_events() -> tuple[StoredEvent, ...]:
    """Return fixed synthetic events suitable for a reproducible smoke test."""

    return (
        StoredEvent(
            symbol="BTC-USDT",
            timestamp=1_700_000_000_000,
            event_type="book_imbalance",
            action="observe",
            strength=0.64,
            confidence=0.82,
            reason="synthetic bid-side imbalance",
            level_price=35_000.0,
            invalidation_price=34_850.0,
            metadata={"sequence": 1, "source": "replay-lab-demo"},
        ),
        StoredEvent(
            symbol="BTC-USDT",
            timestamp=1_700_000_000_250,
            event_type="trade_burst",
            action="accept",
            strength=0.81,
            confidence=0.9,
            reason="synthetic aggressive buy burst",
            level_price=35_020.5,
            invalidation_price=34_900.0,
            metadata={"sequence": 2, "source": "replay-lab-demo"},
        ),
        StoredEvent(
            symbol="BTC-USDT",
            timestamp=1_700_000_000_500,
            event_type="spread_normalized",
            action="observe",
            strength=0.41,
            confidence=0.76,
            reason="synthetic spread normalization",
            level_price=35_015.0,
            invalidation_price=None,
            metadata={"sequence": 3, "source": "replay-lab-demo"},
        ),
    )


def _write_json(report: dict[str, Any]) -> None:
    print(
        json.dumps(
            report,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _require_event_file(path: Path) -> None:
    if not path.exists():
        raise ValueError(f"event store does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"event store is not a file: {path}")


def _path_entry_exists(path: Path) -> bool:
    """Return whether a filesystem entry exists, including a broken symlink."""

    return path.exists() or path.is_symlink()


def _replace_file(source: Path, target: Path) -> None:
    """Replace one file; kept as an injection seam for commit-failure tests."""

    os.replace(source, target)


def _commit_demo_files(
    staged_targets: tuple[Path, ...],
    targets: tuple[Path, ...],
    *,
    force: bool,
) -> None:
    """Commit a staged demo set and roll back ordinary replacement failures.

    This protects the three-file logical set from handled write and replacement
    errors.  It is intentionally not described as crash-atomic: a process or
    operating-system failure can interrupt the sequence of replacements.
    """

    output_dir = targets[0].parent
    output_dir_preexisted = output_dir.exists()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not force:
        existing = tuple(path.name for path in targets if _path_entry_exists(path))
        if existing:
            names = ", ".join(existing)
            raise ValueError(f"refusing to overwrite existing demo files: {names}; use --force")

    backup_dir = staged_targets[0].parent / "backups"
    backup_dir.mkdir()
    backups: dict[Path, Path] = {}
    installed: set[Path] = set()

    try:
        for staged, target in zip(staged_targets, targets, strict=True):
            if _path_entry_exists(target):
                backup = backup_dir / target.name
                _replace_file(target, backup)
                backups[target] = backup
            _replace_file(staged, target)
            installed.add(target)
    except BaseException as commit_error:
        rollback_errors: list[str] = []
        for target in reversed(targets):
            backup = backups.get(target)
            try:
                if backup is not None and _path_entry_exists(backup):
                    _replace_file(backup, target)
                elif target in installed and _path_entry_exists(target):
                    target.unlink()
            except OSError as rollback_error:
                rollback_errors.append(f"{target.name}: {rollback_error}")

        if not output_dir_preexisted:
            with suppress(OSError):
                output_dir.rmdir()

        if rollback_errors:
            details = "; ".join(rollback_errors)
            raise OSError(
                f"demo commit failed and rollback was incomplete: {details}"
            ) from commit_error
        raise


def _run_demo(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    if output_dir.exists() and not output_dir.is_dir():
        raise ValueError(f"output path is not a directory: {output_dir}")

    targets = tuple(output_dir / name for name in DEMO_FILENAMES)
    directory_targets = tuple(path.name for path in targets if path.is_dir())
    if directory_targets:
        names = ", ".join(directory_targets)
        raise ValueError(f"demo target is a directory and cannot be overwritten: {names}")
    existing = tuple(path.name for path in targets if _path_entry_exists(path))
    if existing and not args.force:
        names = ", ".join(existing)
        raise ValueError(f"refusing to overwrite existing demo files: {names}; use --force")

    events = _demo_events()
    changed = list(events)
    changed[1] = replace(changed[1], confidence=0.91)

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    # Existing output directories may be symlinks or mount points, so stage
    # inside them to keep backups and replacements on the targets' filesystem.
    staging_parent = output_dir if output_dir.exists() else output_dir.parent
    with tempfile.TemporaryDirectory(prefix=".cmt-demo-", dir=staging_parent) as temporary:
        staging_dir = Path(temporary)
        staged_targets = tuple(staging_dir / name for name in DEMO_FILENAMES)
        EventStore(staged_targets[0]).write(events)
        EventStore(staged_targets[1]).write(events)
        EventStore(staged_targets[2]).write(changed)
        _commit_demo_files(staged_targets, targets, force=args.force)

    baseline_fingerprint = EventStore.fingerprint(events)
    changed_fingerprint = EventStore.fingerprint(changed)
    print(f"created deterministic Replay Lab data in {output_dir}")
    print(f"run-a.jsonl: {len(events)} events, fingerprint={baseline_fingerprint}")
    print(f"run-b.jsonl: {len(events)} events, fingerprint={baseline_fingerprint}")
    print(f"run-changed.jsonl: {len(changed)} events, fingerprint={changed_fingerprint}")
    print("expected: run-a == run-b; run-a != run-changed (mismatch index 1)")
    return 0


def _run_inspect(args: argparse.Namespace) -> int:
    path = Path(args.path)
    _require_event_file(path)
    manifest = EventStore(path).manifest()
    report = {
        "command": "inspect",
        "event_count": manifest.event_count,
        "fingerprint": manifest.fingerprint,
        "fingerprint_algorithm": manifest.fingerprint_algorithm,
        "path": str(path),
        "report_version": REPORT_VERSION,
    }
    if args.json:
        _write_json(report)
    else:
        print(f"path: {report['path']}")
        print(f"event_count: {report['event_count']}")
        print(f"fingerprint: {report['fingerprint']}")
    return 0


def _run_compare(args: argparse.Namespace) -> int:
    first_path = Path(args.first)
    second_path = Path(args.second)
    _require_event_file(first_path)
    _require_event_file(second_path)
    first = EventStore(first_path).iter_read()
    second = EventStore(second_path).iter_read()
    result = ReplayValidator().compare(first, second)
    report = {
        "command": "compare",
        "deterministic": result.deterministic,
        "first_event_count": result.first_event_count,
        "first_fingerprint": result.first_fingerprint,
        "first_mismatch_index": result.first_mismatch_index,
        "first_path": str(first_path),
        "reason": result.reason,
        "report_version": REPORT_VERSION,
        "second_event_count": result.second_event_count,
        "second_fingerprint": result.second_fingerprint,
        "second_path": str(second_path),
    }
    if args.json:
        _write_json(report)
    else:
        status = "SAME" if result.deterministic else "CHANGED"
        mismatch = "none" if result.first_mismatch_index is None else result.first_mismatch_index
        print(f"result: {status}")
        print(
            f"first: path={first_path} count={result.first_event_count} "
            f"fingerprint={result.first_fingerprint}"
        )
        print(
            f"second: path={second_path} count={result.second_event_count} "
            f"fingerprint={result.second_fingerprint}"
        )
        print(f"first_mismatch_index: {mismatch}")
        print(f"reason: {result.reason}")
    return 0 if result.deterministic else 1


def _run_latency(args: argparse.Namespace) -> int:
    model = LatencyModel()
    stats = model.summarize(args.samples)
    threshold_cancel = model.should_cancel(stats.p95_ms, args.threshold)
    cancel = not stats.valid or threshold_cancel
    if not stats.valid:
        reason = "invalid latency samples; fail-closed cancellation"
    elif cancel:
        reason = "p95 latency exceeds threshold"
    else:
        reason = "latency is within threshold"

    report = {
        "cancel": cancel,
        "command": "latency",
        "reason": reason,
        "report_version": REPORT_VERSION,
        "stats": asdict(stats),
        "threshold_ms": args.threshold,
    }
    if args.json:
        _write_json(report)
    else:
        print(f"valid: {stats.valid}")
        print(f"count: {stats.count}")
        print(f"invalid_count: {stats.invalid_count}")
        print(f"mean_ms: {stats.mean_ms}")
        print(f"p95_ms: {stats.p95_ms}")
        print(f"max_ms: {stats.max_ms}")
        print(f"threshold_ms: {args.threshold}")
        print(f"cancel: {cancel}")
        print(f"reason: {reason}")
    return 1 if cancel else 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cmt-lab",
        description="Offline deterministic Replay Lab for synthetic research events.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo = subparsers.add_parser("demo", help="create deterministic synthetic replay files")
    demo.add_argument("output_dir", metavar="OUTPUT_DIR")
    demo.add_argument("--force", action="store_true", help="overwrite the three demo files")
    demo.set_defaults(handler=_run_demo)

    inspect = subparsers.add_parser("inspect", help="validate and summarize an event store")
    inspect.add_argument("path", metavar="PATH")
    inspect.add_argument("--json", action="store_true", help="emit deterministic JSON")
    inspect.set_defaults(handler=_run_inspect)

    compare = subparsers.add_parser("compare", help="compare two event sequences")
    compare.add_argument("first", metavar="FIRST")
    compare.add_argument("second", metavar="SECOND")
    compare.add_argument("--json", action="store_true", help="emit deterministic JSON")
    compare.set_defaults(handler=_run_compare)

    latency = subparsers.add_parser("latency", help="summarize latency and apply a guardrail")
    latency.add_argument("samples", metavar="SAMPLE", nargs="+", type=float)
    latency.add_argument("--threshold", metavar="N", type=float, default=250.0)
    latency.add_argument("--json", action="store_true", help="emit deterministic JSON")
    latency.set_defaults(handler=_run_latency)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Replay Lab command and return a process exit code."""

    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (OSError, TypeError, ValueError) as exc:
        message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        print(f"error: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - exercised through __main__.
    raise SystemExit(main())
