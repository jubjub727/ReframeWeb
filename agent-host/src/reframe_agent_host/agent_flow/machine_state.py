from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import platform

from baml_sdk import turn_context as baml_turn_context

from reframe_agent_host.agent_flow.geolocation import (
    DEFAULT_GEOLOCATION_ATTEMPTS,
    DEFAULT_GEOLOCATION_RETRY_DELAY_SECONDS,
    DEFAULT_GEOLOCATION_TIMEOUT_SECONDS,
    MachineGeolocation,
    MachineStateError,
    fetch_ip_geolocation,
)
from reframe_agent_host.agent_flow.monitor_detection import (
    MachineMonitor,
    machine_monitors,
)


@dataclass(frozen=True)
class _StartupMachineState:
    geolocation: MachineGeolocation
    os_architecture: str


GeolocationFetcher = Callable[[], MachineGeolocation]


@dataclass
class MachineStateProvider:
    fetcher: GeolocationFetcher | None = None
    max_attempts: int = DEFAULT_GEOLOCATION_ATTEMPTS
    retry_delay_seconds: float = DEFAULT_GEOLOCATION_RETRY_DELAY_SECONDS
    timeout_seconds: float = DEFAULT_GEOLOCATION_TIMEOUT_SECONDS
    _executor: ThreadPoolExecutor | None = None
    _future: Future[_StartupMachineState] | None = None
    _state: _StartupMachineState | None = None

    def start(self) -> None:
        if self._future is not None or self._state is not None:
            return
        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="machine-state",
        )
        self._future = self._executor.submit(self._fetch_startup_state)

    def wait_until_ready(self) -> None:
        if self._state is not None:
            return
        if self._future is None:
            self.start()
        assert self._future is not None
        try:
            self._state = self._future.result()
        finally:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=False)
                self._executor = None

    def context(self) -> baml_turn_context.MachineStateContext:
        if self._state is None:
            raise MachineStateError("machine state geolocation has not loaded")
        return machine_state_context(
            self._state.geolocation,
            os_architecture=self._state.os_architecture,
        )

    def _fetch_startup_state(self) -> _StartupMachineState:
        fetcher = self.fetcher or (
            lambda: fetch_ip_geolocation(
                max_attempts=self.max_attempts,
                retry_delay_seconds=self.retry_delay_seconds,
                timeout_seconds=self.timeout_seconds,
            )
        )
        return _StartupMachineState(fetcher(), machine_os_architecture())


def machine_state_context(
    geolocation: MachineGeolocation,
    *,
    monitors: list[MachineMonitor] | None = None,
    os_architecture: str | None = None,
) -> baml_turn_context.MachineStateContext:
    now, utc_now = _current_times()
    resolved_monitors = machine_monitors() if monitors is None else monitors
    return baml_turn_context.MachineStateContext(
        **_local_context_fields(now, utc_now, resolved_monitors),
        os_architecture=os_architecture or machine_os_architecture(),
        geolocation_status="available",
        geolocation_source=geolocation.source,
        ip_address=geolocation.ip_address,
        country=geolocation.country,
        country_code=geolocation.country_code,
        region=geolocation.region,
        city=geolocation.city,
        postal_code=geolocation.postal_code,
        latitude=geolocation.latitude,
        longitude=geolocation.longitude,
        geolocation_timezone=geolocation.timezone_name,
        organization=geolocation.organization,
        asn=geolocation.asn,
        geolocation_error=None,
    )


def local_machine_state_context(
    reason: str = "IP geolocation unavailable",
) -> baml_turn_context.MachineStateContext:
    now, utc_now = _current_times()
    monitors = machine_monitors()
    return baml_turn_context.MachineStateContext(
        **_local_context_fields(now, utc_now, monitors),
        os_architecture=machine_os_architecture(),
        geolocation_status="unavailable",
        geolocation_source=None,
        ip_address=None,
        country=None,
        country_code=None,
        region=None,
        city=None,
        postal_code=None,
        latitude=None,
        longitude=None,
        geolocation_timezone=None,
        organization=None,
        asn=None,
        geolocation_error=reason,
    )


def machine_os_architecture() -> str:
    system = platform.system().strip()
    operating_system = "macOS" if system == "Darwin" else (system or "unknown-os")
    machine = platform.machine().strip().lower()
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
        "i386": "x86",
        "i686": "x86",
        "x86": "x86",
    }.get(machine, machine or "unknown-arch")
    return f"{operating_system} {architecture}"


def _local_context_fields(now, utc_now, monitors) -> dict:
    return {
        "captured_at_utc": _iso_utc(utc_now),
        "current_local_time": now.replace(microsecond=0).isoformat(),
        "current_utc_time": _iso_utc(utc_now),
        "timezone_name": _local_timezone_name(now),
        "utc_offset": _utc_offset(now),
        "monitor_count": len(monitors),
        "monitors": [
            baml_turn_context.MachineMonitorContext(
                horizontal_resolution=item.horizontal_resolution,
                vertical_resolution=item.vertical_resolution,
            )
            for item in monitors
        ],
    }


def _current_times() -> tuple[datetime, datetime]:
    return (
        datetime.now().astimezone(),
        datetime.now(timezone.utc).replace(microsecond=0),
    )


def _local_timezone_name(now: datetime) -> str:
    tzinfo = now.tzinfo
    if tzinfo is None:
        return "local"
    key = getattr(tzinfo, "key", None)
    return key if isinstance(key, str) and key else (tzinfo.tzname(now) or "local")


def _utc_offset(now: datetime) -> str:
    offset = now.utcoffset()
    if offset is None:
        return "unknown"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    hours, remainder = divmod(abs(total_seconds), 3600)
    return f"{sign}{hours:02d}:{remainder // 60:02d}"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
