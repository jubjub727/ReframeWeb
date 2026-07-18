"""Validated workloads and paired statistics for the mounted I/O benchmark."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import time


MOUNTED = "resident mount"
NATIVE = "native directory"


@dataclass(frozen=True)
class Percentiles:
    p50: float
    p95: float
    p99: float


@dataclass(frozen=True)
class OperationResult:
    mounted_us: Percentiles
    native_us: Percentiles
    mounted_over_native: Percentiles


def _payload(label: str, size: int) -> bytes:
    block = hashlib.sha256(label.encode("utf-8")).digest()
    return (block * ((size + len(block) - 1) // len(block)))[:size]


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _percentile(values: Sequence[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index]


def _latency(values: Sequence[int]) -> Percentiles:
    if not values:
        raise ValueError("at least one benchmark sample is required")
    microseconds = [value / 1_000.0 for value in values]
    return Percentiles(
        p50=_percentile(microseconds, 0.50),
        p95=_percentile(microseconds, 0.95),
        p99=_percentile(microseconds, 0.99),
    )


def paired_ratios(mounted: Sequence[int], native: Sequence[int]) -> Percentiles:
    if len(mounted) != len(native) or not mounted:
        raise ValueError("mounted and native samples must form non-empty pairs")
    ratios = [
        mounted_ns / native_ns if native_ns else float("inf")
        for mounted_ns, native_ns in zip(mounted, native, strict=True)
    ]
    return Percentiles(
        p50=_percentile(ratios, 0.50),
        p95=_percentile(ratios, 0.95),
        p99=_percentile(ratios, 0.99),
    )


class Workload:
    def __init__(
        self,
        roots: dict[str, Path],
        file_size: int,
        patch_size: int,
        entries: int,
        warmups: int,
    ) -> None:
        self.roots = roots
        self.file_size = file_size
        self.warmups = warmups
        self.edit_payloads = (
            _payload("resident-edit-a", file_size),
            _payload("resident-edit-b", file_size),
        )
        self.patch_offset = (file_size - patch_size) // 2
        self.patch_payloads = (
            _payload("resident-patch-a", patch_size),
            _payload("resident-patch-b", patch_size),
        )
        self.patch_expected = tuple(
            self._patched(self.edit_payloads[0], patch) for patch in self.patch_payloads
        )
        self.create_payload = _payload("resident-create", 4 * 1024)
        self.rename_payload = _payload("resident-rename", 4 * 1024)
        self.expected_entries = {f"entry-{index:04d}.txt" for index in range(entries)}

    def create(self, side: str, iteration: int) -> int:
        path = self.roots[side] / "generated" / f"sample-{iteration:+06d}.bin"
        try:
            started = time.perf_counter_ns()
            path.write_bytes(self.create_payload)
            elapsed = time.perf_counter_ns() - started
            self._check_bytes("create", side, path.read_bytes(), self.create_payload)
            return elapsed
        finally:
            path.unlink(missing_ok=True)

    def read(self, side: str, iteration: int) -> int:
        index = iteration + self.warmups
        label = f"read-{index:04d}"
        expected = _payload(label, self.file_size)
        path = self.roots[side] / "readset" / f"{label}.bin"
        started = time.perf_counter_ns()
        observed = path.read_bytes()
        elapsed = time.perf_counter_ns() - started
        self._check_bytes("read", side, observed, expected)
        return elapsed

    def patch(self, side: str, iteration: int) -> int:
        index = iteration % len(self.patch_payloads)
        path = self.roots[side] / "hot" / "edit.bin"
        started = time.perf_counter_ns()
        with path.open("r+b", buffering=0) as handle:
            handle.seek(self.patch_offset)
            written = handle.write(self.patch_payloads[index])
        elapsed = time.perf_counter_ns() - started
        if written != len(self.patch_payloads[index]):
            raise RuntimeError(f"patch short write for {side}")
        self._check_bytes("patch", side, path.read_bytes(), self.patch_expected[index])
        return elapsed

    def replace(self, side: str, iteration: int) -> int:
        expected = self.edit_payloads[iteration % len(self.edit_payloads)]
        path = self.roots[side] / "hot" / "edit.bin"
        started = time.perf_counter_ns()
        path.write_bytes(expected)
        elapsed = time.perf_counter_ns() - started
        self._check_bytes("edit", side, path.read_bytes(), expected)
        return elapsed

    def rename(self, side: str, _iteration: int) -> int:
        directory = self.roots[side] / "rename"
        source = directory / "source.bin"
        destination = directory / "destination.bin"
        if destination.exists():
            destination.replace(source)
        self._check_bytes(
            "rename setup", side, source.read_bytes(), self.rename_payload
        )
        started = time.perf_counter_ns()
        source.replace(destination)
        elapsed = time.perf_counter_ns() - started
        if source.exists() or not destination.is_file():
            raise RuntimeError(f"rename path mismatch for {side}")
        self._check_bytes("rename", side, destination.read_bytes(), self.rename_payload)
        return elapsed

    def list_directory(self, side: str, _iteration: int) -> int:
        path = self.roots[side] / "corpus"
        started = time.perf_counter_ns()
        with os.scandir(path) as entries:
            observed = tuple(entry.name for entry in entries)
        elapsed = time.perf_counter_ns() - started
        if (
            len(observed) != len(self.expected_entries)
            or set(observed) != self.expected_entries
        ):
            raise RuntimeError(f"list checksum mismatch for {side}")
        return elapsed

    @staticmethod
    def _check_bytes(
        operation: str, side: str, observed: bytes, expected: bytes
    ) -> None:
        if len(observed) != len(expected) or _digest(observed) != _digest(expected):
            raise RuntimeError(f"{operation} checksum mismatch for {side}")

    def _patched(self, original: bytes, patch: bytes) -> bytes:
        expected = bytearray(original)
        expected[self.patch_offset : self.patch_offset + len(patch)] = patch
        return bytes(expected)


def measure(
    operation: Callable[[str, int], int],
    *,
    samples: int,
    warmups: int,
) -> OperationResult:
    timings: dict[str, list[int]] = {MOUNTED: [], NATIVE: []}
    for iteration in range(-warmups, samples):
        order = (MOUNTED, NATIVE) if iteration % 2 == 0 else (NATIVE, MOUNTED)
        for side in order:
            elapsed = operation(side, iteration)
            if iteration >= 0:
                timings[side].append(elapsed)
    mounted_samples = timings[MOUNTED]
    native_samples = timings[NATIVE]
    return OperationResult(
        _latency(mounted_samples),
        _latency(native_samples),
        paired_ratios(mounted_samples, native_samples),
    )


def seed_source(
    source: Path,
    *,
    file_size: int,
    entries: int,
    read_files: int,
) -> None:
    source.mkdir(parents=True)
    for name in ("corpus", "generated", "hot", "readset", "rename"):
        (source / name).mkdir()
    for index in range(entries):
        name = f"entry-{index:04d}.txt"
        (source / "corpus" / name).write_bytes(_payload(name, 1024))
    (source / "generated" / ".keep").write_bytes(b"")
    (source / "hot" / "edit.bin").write_bytes(
        _payload("resident-edit-a", file_size)
    )
    (source / "rename" / "source.bin").write_bytes(
        _payload("resident-rename", 4 * 1024)
    )
    for index in range(read_files):
        label = f"read-{index:04d}"
        (source / "readset" / f"{label}.bin").write_bytes(
            _payload(label, file_size)
        )
