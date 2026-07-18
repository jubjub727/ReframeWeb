"""Opt-in acceptance evidence for mounted workspace I/O versus native I/O.

Run from the repository root with::

    REFRAME_RUN_WORKSPACE_IO_BENCHMARK=1 uv run --project agent-host \
        python agent-host/tests/benchmark_workspace_mounted_io.py

This is deliberately not named ``test_*.py`` and has no built-in performance
threshold. It validates every workload and reports paired mounted/native
latency ratios; deciding what ratio is acceptable remains an explicit product
decision rather than a claim baked into this harness.

Both sides use ordinary buffered filesystem APIs. This measures the paths an
agent actually uses, including the operating system's caches; it is not a raw
storage-device bandwidth benchmark.

On Windows, combine ``--expect-backend winfsp``, ``--require-native-nvme``, and
``--require-faster-than-native`` for a fail-closed acceptance run. This prevents
provider fallback or a slower control disk from producing convincing-looking
but irrelevant evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from uuid import uuid4

from mounted_io_workloads import (
    MOUNTED,
    NATIVE,
    OperationResult,
    Percentiles,
    Workload,
    measure,
    seed_source,
)
from reframe_agent_host.workspace.models import DirectoryMemorySource
from reframe_agent_host.workspace.service import WorkspaceDaemon


_GATE = "REFRAME_RUN_WORKSPACE_IO_BENCHMARK"


def _same_volume(left: Path, right: Path) -> bool:
    if os.name == "nt":
        return left.drive.casefold() == right.drive.casefold()
    return os.stat(left).st_dev == os.stat(right).st_dev


def _format_percentiles(values: Percentiles, suffix: str) -> str:
    return "  ".join(
        (
            f"p50 {values.p50:9.2f}{suffix}",
            f"p95 {values.p95:9.2f}{suffix}",
            f"p99 {values.p99:9.2f}{suffix}",
        )
    )


def _size_label(size: int) -> str:
    return f"{size // 1024}k" if size % 1024 == 0 else f"{size}b"


def _native_device(path: Path) -> dict[str, Any]:
    if os.name != "nt":
        return {
            "bus_type": "unverified",
            "disk_number": None,
            "model": None,
            "validated_nvme": False,
        }
    drive = path.drive.rstrip(":")
    if len(drive) != 1 or not drive.isalpha():
        raise RuntimeError(f"cannot resolve a physical disk for native path: {path}")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$disk=Get-Partition -DriveLetter '{drive}' | Get-Disk;"
        "[pscustomobject]@{"
        "bus_type=[string]$disk.BusType;"
        "disk_number=$disk.Number;"
        "model=([string]$disk.Model).Trim();"
        "validated_nvme=([string]$disk.BusType -eq 'NVMe')"
        "}|ConvertTo-Json -Compress"
    )
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            script,
        ],
        capture_output=True,
        check=False,
        text=True,
        timeout=15,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"cannot identify native control disk: {detail}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("native control disk probe returned invalid JSON") from error
    if not isinstance(result, dict):
        raise RuntimeError("native control disk probe returned multiple disks")
    return result


def _print_report(report: dict[str, Any]) -> None:
    print(f"platform: {report['platform']}")
    print(f"daemon build: {report['daemon_build']}")
    print(
        f"resident mount: {report['mount_path']} [backend: {report['mount_backend']}] "
        f"({report['resident_files']} files, {report['resident_bytes']} bytes)"
    )
    print(f"native control: {report['native_path']}")
    device = report["native_device"]
    print(
        f"native device: {device.get('model') or 'unknown'} "
        f"[bus: {device['bus_type']}, disk: {device.get('disk_number')}] "
        f"(NVMe validated: {device['validated_nvme']})"
    )
    print(
        f"samples: {report['samples']} after "
        f"{report['warmups']} warmups per operation"
    )
    print("validation: passed for every timed operation")
    print(
        "ratio percentiles are from per-iteration mounted/native pairs; "
        "below 1.0 means the resident mount won\n"
    )
    print("native timings may include OS caching; this is not a raw NVMe benchmark\n")
    for name, values in report["operations"].items():
        result = OperationResult(
            mounted_us=Percentiles(**values["mounted_us"]),
            native_us=Percentiles(**values["native_us"]),
            mounted_over_native=Percentiles(**values["mounted_over_native"]),
        )
        print(name)
        print(f"  mounted  {_format_percentiles(result.mounted_us, ' us')}")
        print(f"  native   {_format_percentiles(result.native_us, ' us')}")
        print(f"  ratio    {_format_percentiles(result.mounted_over_native, 'x')}")


def _require_faster_than_native(measured: dict[str, dict[str, Any]]) -> None:
    failures = []
    for operation, values in measured.items():
        ratios = values["mounted_over_native"]
        for percentile in ("p50", "p95"):
            ratio = ratios[percentile]
            if ratio >= 1.0:
                failures.append(f"{operation} {percentile}={ratio:.2f}x")
    if failures:
        raise RuntimeError(
            "resident mount did not beat native NVMe at p50 and p95: "
            + ", ".join(failures)
        )


def run(args: argparse.Namespace) -> dict[str, Any]:
    parent = (
        Path(args.root).resolve()
        if args.root
        else Path(tempfile.gettempdir()).resolve()
    )
    parent.mkdir(parents=True, exist_ok=True)
    benchmark_root = Path(
        tempfile.mkdtemp(prefix="reframe-mounted-io-", dir=parent)
    ).resolve()
    store = benchmark_root / "store"
    source = benchmark_root / "source"
    native = benchmark_root / "native"
    daemon = WorkspaceDaemon(store)
    session_id = f"mounted-io-{uuid4()}"
    daemon_started = False
    workspace_created = False
    mount_attempted = False
    unmounted = True
    shutdown = False
    report: dict[str, Any] | None = None
    try:
        seed_source(
            source,
            file_size=args.file_size,
            entries=args.directory_entries,
            read_files=args.samples + args.warmups,
        )
        shutil.copytree(source, native)
        if not _same_volume(source, native):
            raise RuntimeError(
                "source and native control are not on the same backing volume"
            )
        native_device = _native_device(native)
        if args.require_native_nvme and not native_device["validated_nvme"]:
            raise RuntimeError(
                "native control is not reported as NVMe: "
                f"{native_device['bus_type']} ({native_device.get('model') or 'unknown'})"
            )
        daemon.start()
        daemon_started = True
        hello = daemon.hello()
        created = daemon.create_workspace(
            name="Mounted I/O benchmark",
            session_id=session_id,
            memory_sources=[
                DirectoryMemorySource(
                    memory_id=f"memory:benchmark-{uuid4()}",
                    source_path=str(source),
                )
            ],
            scratch_paths=[],
        )
        workspace_created = True
        mount_attempted = True
        unmounted = False
        mount = daemon.mount_workspace(created.session_id)
        mount_path = Path(mount.mount_path).resolve()
        mount_backend = mount.backend
        if (
            args.expect_backend
            and mount_backend.casefold() != args.expect_backend.casefold()
        ):
            raise RuntimeError(
                f"mounted backend is {mount_backend!r}, "
                f"expected {args.expect_backend!r}"
            )
        workload = Workload(
            {MOUNTED: mount_path, NATIVE: native},
            args.file_size,
            args.patch_size,
            args.directory_entries,
            args.warmups,
        )
        file_label = _size_label(args.file_size)
        operations = {
            "create_4k": workload.create,
            f"unique_read_{file_label}": workload.read,
            f"patch_{_size_label(args.patch_size)}": workload.patch,
            f"replace_{file_label}": workload.replace,
            "rename_4k": workload.rename,
            f"list_{args.directory_entries}": workload.list_directory,
        }
        measured = {
            name: asdict(
                measure(operation, samples=args.samples, warmups=args.warmups)
            )
            for name, operation in operations.items()
        }
        if args.require_faster_than_native:
            _require_faster_than_native(measured)
        report = {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "daemon_build": hello.build_fingerprint,
            "samples": args.samples,
            "warmups": args.warmups,
            "mount_path": str(mount_path),
            "mount_backend": mount_backend,
            "native_path": str(native),
            "native_device": native_device,
            "resident_files": mount.resident_files,
            "resident_bytes": mount.resident_bytes,
            "file_size": args.file_size,
            "patch_size": args.patch_size,
            "directory_entries": args.directory_entries,
            "operations": measured,
        }
        return report
    finally:
        cleanup_errors: list[str] = []
        if mount_attempted and not unmounted:
            try:
                daemon.unmount_workspace(session_id)
                unmounted = True
            except Exception as error:  # cleanup must preserve the mount on failure
                cleanup_errors.append(f"unmount failed: {error}")
        if workspace_created and unmounted:
            try:
                daemon.destroy_ephemeral_workspace(session_id)
            except Exception as error:
                cleanup_errors.append(f"destroy failed: {error}")
        if daemon_started:
            try:
                daemon.shutdown()
                shutdown = True
            except Exception as error:
                cleanup_errors.append(f"shutdown failed: {error}")
        daemon.close()
        can_remove = (
            report is not None
            and unmounted
            and (shutdown or not daemon_started)
            and not cleanup_errors
        )
        if not args.keep and can_remove:
            shutil.rmtree(benchmark_root)
        else:
            print(f"benchmark artifacts retained at {benchmark_root}", file=sys.stderr)
            for error in cleanup_errors:
                print(f"cleanup warning: {error}", file=sys.stderr)
        if cleanup_errors and report is not None:
            raise RuntimeError("; ".join(cleanup_errors))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=400)
    parser.add_argument("--warmups", type=int, default=40)
    parser.add_argument("--file-size", type=int, default=64 * 1024)
    parser.add_argument("--patch-size", type=int, default=256)
    parser.add_argument("--directory-entries", type=int, default=256)
    parser.add_argument("--root", help="parent directory for same-volume artifacts")
    parser.add_argument(
        "--require-native-nvme",
        action="store_true",
        help="fail unless Windows reports the native control disk bus as NVMe",
    )
    parser.add_argument(
        "--expect-backend",
        help="fail unless the daemon reports this exact mounted backend",
    )
    parser.add_argument(
        "--require-faster-than-native",
        action="store_true",
        help="fail unless every mounted operation beats native at p50 and p95",
    )
    parser.add_argument(
        "--keep", action="store_true", help="retain benchmark artifacts"
    )
    parser.add_argument(
        "--json", action="store_true", help="emit machine-readable JSON"
    )
    args = parser.parse_args()
    if args.samples < 100:
        parser.error("--samples must be at least 100 for a useful p99")
    if args.warmups < 0 or args.file_size < 1 or args.directory_entries < 1:
        parser.error("warmups cannot be negative and workload sizes must be positive")
    if args.patch_size < 1 or args.patch_size > args.file_size:
        parser.error("--patch-size must be between 1 and --file-size")
    if args.require_native_nvme and os.name != "nt":
        parser.error("--require-native-nvme currently supports Windows only")
    if args.require_native_nvme and not args.root:
        parser.error("--require-native-nvme requires an explicit --root on the target disk")
    if args.require_faster_than_native and not args.require_native_nvme:
        parser.error("--require-faster-than-native requires --require-native-nvme")
    if args.require_faster_than_native and args.expect_backend != "winfsp":
        parser.error(
            "--require-faster-than-native requires --expect-backend winfsp"
        )
    return args


def main() -> int:
    args = _arguments()
    if os.getenv(_GATE, "").casefold() not in {"1", "true", "yes"}:
        print(f"SKIP: set {_GATE}=1 to run the opt-in mounted I/O benchmark")
        return 0
    report = run(args)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
