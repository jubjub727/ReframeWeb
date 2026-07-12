from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import platform
import re
import subprocess
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from baml_sdk import context as baml_context


DEFAULT_GEOLOCATION_ATTEMPTS = 5
DEFAULT_GEOLOCATION_RETRY_DELAY_SECONDS = 1.0
DEFAULT_GEOLOCATION_TIMEOUT_SECONDS = 4.0


class MachineStateError(RuntimeError):
    pass


@dataclass(frozen=True)
class MachineGeolocation:
    source: str
    ip_address: str | None = None
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    postal_code: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    timezone_name: str | None = None
    organization: str | None = None
    asn: str | None = None


@dataclass(frozen=True)
class MachineMonitor:
    horizontal_resolution: int
    vertical_resolution: int


@dataclass(frozen=True)
class _MonitorGeometry:
    x: int
    y: int
    width: int
    height: int


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

    def context(self) -> baml_context.MachineStateContext:
        if self._state is None:
            msg = "machine state geolocation has not loaded"
            raise MachineStateError(msg)
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
        return _StartupMachineState(
            geolocation=fetcher(),
            os_architecture=machine_os_architecture(),
        )


def machine_state_context(
    geolocation: MachineGeolocation,
    *,
    monitors: list[MachineMonitor] | None = None,
    os_architecture: str | None = None,
) -> baml_context.MachineStateContext:
    now = datetime.now().astimezone()
    utc_now = datetime.now(timezone.utc).replace(microsecond=0)
    resolved_monitors = machine_monitors() if monitors is None else monitors
    return baml_context.MachineStateContext(
        captured_at_utc=_iso_utc(utc_now),
        current_local_time=now.replace(microsecond=0).isoformat(),
        current_utc_time=_iso_utc(utc_now),
        timezone_name=_local_timezone_name(now),
        utc_offset=_utc_offset(now),
        os_architecture=os_architecture or machine_os_architecture(),
        monitor_count=len(resolved_monitors),
        monitors=_monitor_contexts(resolved_monitors),
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


def local_machine_state_context(reason: str = "IP geolocation unavailable") -> baml_context.MachineStateContext:
    now = datetime.now().astimezone()
    utc_now = datetime.now(timezone.utc).replace(microsecond=0)
    monitors = machine_monitors()
    return baml_context.MachineStateContext(
        captured_at_utc=_iso_utc(utc_now),
        current_local_time=now.replace(microsecond=0).isoformat(),
        current_utc_time=_iso_utc(utc_now),
        timezone_name=_local_timezone_name(now),
        utc_offset=_utc_offset(now),
        os_architecture=machine_os_architecture(),
        monitor_count=len(monitors),
        monitors=_monitor_contexts(monitors),
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


def machine_monitors() -> list[MachineMonitor]:
    geometries = _dedupe_monitor_geometries(_detect_monitor_geometries())
    return [
        MachineMonitor(
            horizontal_resolution=geometry.width,
            vertical_resolution=geometry.height,
        )
        for geometry in geometries
    ]


def machine_os_architecture() -> str:
    return f"{_operating_system_label()} {_architecture_label()}".strip()


def _operating_system_label() -> str:
    system = platform.system().strip()
    if system == "Darwin":
        return "macOS"
    if system in {"Windows", "Linux"}:
        return system
    return system or "unknown-os"


def _architecture_label() -> str:
    machine = platform.machine().strip().lower()
    if machine in {"amd64", "x86_64"}:
        return "x86_64"
    if machine in {"arm64", "aarch64"}:
        return "arm64"
    if machine in {"i386", "i686", "x86"}:
        return "x86"
    return machine or "unknown-arch"


def fetch_ip_geolocation(
    *,
    max_attempts: int = DEFAULT_GEOLOCATION_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_GEOLOCATION_RETRY_DELAY_SECONDS,
    timeout_seconds: float = DEFAULT_GEOLOCATION_TIMEOUT_SECONDS,
) -> MachineGeolocation:
    last_error: Exception | None = None
    endpoints = (_fetch_ipapi, _fetch_ipwho)
    for attempt in range(1, max_attempts + 1):
        for endpoint in endpoints:
            try:
                return endpoint(timeout_seconds)
            except Exception as error:
                last_error = error
        if attempt < max_attempts:
            time.sleep(retry_delay_seconds)

    detail = str(last_error) if last_error is not None else "unknown error"
    msg = f"IP geolocation failed after {max_attempts} attempts: {detail}"
    raise MachineStateError(msg)


def _monitor_contexts(monitors: list[MachineMonitor]) -> list[baml_context.MachineMonitorContext]:
    return [
        baml_context.MachineMonitorContext(
            horizontal_resolution=monitor.horizontal_resolution,
            vertical_resolution=monitor.vertical_resolution,
        )
        for monitor in monitors
    ]


def _detect_monitor_geometries() -> list[_MonitorGeometry]:
    for detector in (
        _screeninfo_monitor_geometries,
        _windows_monitor_geometries,
        _macos_monitor_geometries,
        _swaymsg_monitor_geometries,
        _xrandr_list_monitor_geometries,
        _xrandr_monitor_geometries,
        _tkinter_monitor_geometry,
    ):
        try:
            geometries = detector()
        except Exception:
            continue
        if geometries:
            return geometries
    return []


def _dedupe_monitor_geometries(
    geometries: list[_MonitorGeometry],
) -> list[_MonitorGeometry]:
    monitors: list[_MonitorGeometry] = []
    seen: set[tuple[int, int, int, int]] = set()
    for geometry in geometries:
        if geometry.width <= 0 or geometry.height <= 0:
            continue
        key = (geometry.x, geometry.y, geometry.width, geometry.height)
        if key in seen:
            continue
        seen.add(key)
        monitors.append(geometry)
    return monitors


def _screeninfo_monitor_geometries() -> list[_MonitorGeometry]:
    try:
        from screeninfo import get_monitors  # type: ignore[import-not-found]
    except ImportError:
        return []

    return [
        _MonitorGeometry(
            x=int(monitor.x),
            y=int(monitor.y),
            width=int(monitor.width),
            height=int(monitor.height),
        )
        for monitor in get_monitors()
    ]


def _windows_monitor_geometries() -> list[_MonitorGeometry]:
    if platform.system() != "Windows":
        return []

    import ctypes

    from ctypes import wintypes

    class Rect(ctypes.Structure):
        _fields_ = (
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        )

    class MonitorInfoEx(ctypes.Structure):
        _fields_ = (
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", Rect),
            ("rcWork", Rect),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32),
        )

    _set_windows_dpi_awareness(ctypes)

    monitors: list[_MonitorGeometry] = []
    callback_type = ctypes.WINFUNCTYPE(
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(Rect),
        ctypes.c_long,
    )

    def callback(monitor, _dc, rect_pointer, _data) -> int:
        rect = rect_pointer.contents
        device_name = ""
        info = MonitorInfoEx()
        info.cbSize = ctypes.sizeof(MonitorInfoEx)
        if ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            rect = info.rcMonitor
            device_name = str(info.szDevice)
        resolution = _windows_display_settings_resolution(device_name, ctypes)
        monitors.append(_monitor_geometry_from_rect(rect, resolution))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(
        None,
        None,
        callback_type(callback),
        0,
    )
    return monitors


def _set_windows_dpi_awareness(ctypes_module) -> None:
    for setter in (
        lambda: ctypes_module.windll.user32.SetProcessDpiAwarenessContext(
            ctypes_module.c_void_p(-4)
        ),
        lambda: ctypes_module.windll.shcore.SetProcessDpiAwareness(2),
        lambda: ctypes_module.windll.user32.SetProcessDPIAware(),
    ):
        try:
            setter()
            return
        except Exception:
            continue


def _windows_display_settings_resolution(
    device_name: str,
    ctypes_module,
) -> tuple[int, int] | None:
    if not device_name:
        return None

    class PointL(ctypes_module.Structure):
        _fields_ = (
            ("x", ctypes_module.c_long),
            ("y", ctypes_module.c_long),
        )

    class DevModeW(ctypes_module.Structure):
        _fields_ = (
            ("dmDeviceName", ctypes_module.c_wchar * 32),
            ("dmSpecVersion", ctypes_module.c_ushort),
            ("dmDriverVersion", ctypes_module.c_ushort),
            ("dmSize", ctypes_module.c_ushort),
            ("dmDriverExtra", ctypes_module.c_ushort),
            ("dmFields", ctypes_module.c_ulong),
            ("dmPosition", PointL),
            ("dmDisplayOrientation", ctypes_module.c_ulong),
            ("dmDisplayFixedOutput", ctypes_module.c_ulong),
            ("dmColor", ctypes_module.c_short),
            ("dmDuplex", ctypes_module.c_short),
            ("dmYResolution", ctypes_module.c_short),
            ("dmTTOption", ctypes_module.c_short),
            ("dmCollate", ctypes_module.c_short),
            ("dmFormName", ctypes_module.c_wchar * 32),
            ("dmLogPixels", ctypes_module.c_ushort),
            ("dmBitsPerPel", ctypes_module.c_ulong),
            ("dmPelsWidth", ctypes_module.c_ulong),
            ("dmPelsHeight", ctypes_module.c_ulong),
            ("dmDisplayFlags", ctypes_module.c_ulong),
            ("dmDisplayFrequency", ctypes_module.c_ulong),
        )

    mode = DevModeW()
    mode.dmSize = ctypes_module.sizeof(DevModeW)
    enum_current_settings = -1
    if not ctypes_module.windll.user32.EnumDisplaySettingsW(
        device_name,
        enum_current_settings,
        ctypes_module.byref(mode),
    ):
        return None
    width = int(mode.dmPelsWidth)
    height = int(mode.dmPelsHeight)
    if width <= 0 or height <= 0:
        return None
    return width, height


def _monitor_geometry_from_rect(
    rect,
    resolution: tuple[int, int] | None,
) -> _MonitorGeometry:
    width = int(rect.right - rect.left)
    height = int(rect.bottom - rect.top)
    if resolution is not None:
        width, height = resolution
    return _MonitorGeometry(
        x=int(rect.left),
        y=int(rect.top),
        width=width,
        height=height,
    )


def _macos_monitor_geometries() -> list[_MonitorGeometry]:
    if platform.system() != "Darwin":
        return []

    try:
        from AppKit import NSScreen  # type: ignore[import-not-found]
    except ImportError:
        return _macos_system_profiler_monitors()

    monitors: list[_MonitorGeometry] = []
    for screen in NSScreen.screens():
        frame = screen.frame()
        scale = float(screen.backingScaleFactor())
        monitors.append(
            _MonitorGeometry(
                x=int(frame.origin.x * scale),
                y=int(frame.origin.y * scale),
                width=int(frame.size.width * scale),
                height=int(frame.size.height * scale),
            )
        )
    return monitors


def _macos_system_profiler_monitors() -> list[_MonitorGeometry]:
    command = ["system_profiler", "SPDisplaysDataType", "-json"]
    payload = json.loads(_run_monitor_command(command, timeout_seconds=3.0))
    displays = payload.get("SPDisplaysDataType")
    if not isinstance(displays, list):
        return []

    monitors: list[_MonitorGeometry] = []
    for display in displays:
        if not isinstance(display, dict):
            continue
        drivers = display.get("spdisplays_ndrvs")
        if not isinstance(drivers, list):
            continue
        for driver in drivers:
            if not isinstance(driver, dict):
                continue
            resolution = _text(driver.get("_spdisplays_resolution"))
            parsed = _parse_resolution(resolution or "")
            if parsed is not None:
                width, height = parsed
                monitors.append(_MonitorGeometry(0, 0, width, height))
    return monitors


def _xrandr_monitor_geometries() -> list[_MonitorGeometry]:
    if platform.system() not in {"Linux", "FreeBSD", "OpenBSD"}:
        return []

    output = _run_monitor_command(["xrandr", "--query"], timeout_seconds=1.0)
    monitors: list[_MonitorGeometry] = []
    pattern = re.compile(r"\b(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")
    for line in output.splitlines():
        if " connected" not in line:
            continue
        match = pattern.search(line)
        if match is None:
            continue
        width, height, x, y = (int(value) for value in match.groups())
        monitors.append(_MonitorGeometry(x=x, y=y, width=width, height=height))
    return monitors


def _swaymsg_monitor_geometries() -> list[_MonitorGeometry]:
    if platform.system() not in {"Linux", "FreeBSD", "OpenBSD"}:
        return []

    payload = json.loads(
        _run_monitor_command(
            ["swaymsg", "-t", "get_outputs", "--raw"],
            timeout_seconds=1.0,
        )
    )
    if not isinstance(payload, list):
        return []

    monitors: list[_MonitorGeometry] = []
    for output in payload:
        if not isinstance(output, dict) or output.get("active") is False:
            continue
        rect = output.get("rect")
        if not isinstance(rect, dict):
            continue
        width = _int_value(rect.get("width"))
        height = _int_value(rect.get("height"))
        x = _int_value(rect.get("x")) or 0
        y = _int_value(rect.get("y")) or 0
        if width is None or height is None:
            continue
        monitors.append(_MonitorGeometry(x=x, y=y, width=width, height=height))
    return monitors


def _xrandr_list_monitor_geometries() -> list[_MonitorGeometry]:
    if platform.system() not in {"Linux", "FreeBSD", "OpenBSD"}:
        return []

    output = _run_monitor_command(["xrandr", "--listmonitors"], timeout_seconds=1.0)
    monitors: list[_MonitorGeometry] = []
    pattern = re.compile(r"\s\d+:\s+\S+\s+(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)")
    for line in output.splitlines():
        match = pattern.search(line)
        if match is None:
            continue
        width, height, x, y = (int(value) for value in match.groups())
        monitors.append(_MonitorGeometry(x=x, y=y, width=width, height=height))
    return monitors


def _tkinter_monitor_geometry() -> list[_MonitorGeometry]:
    import tkinter

    root = tkinter.Tk()
    try:
        root.withdraw()
        width = int(root.winfo_screenwidth())
        height = int(root.winfo_screenheight())
    finally:
        root.destroy()
    return [_MonitorGeometry(0, 0, width, height)]


def _run_monitor_command(command: list[str], *, timeout_seconds: float) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        check=True,
        text=True,
        timeout=timeout_seconds,
    )
    return completed.stdout


def _parse_resolution(value: str) -> tuple[int, int] | None:
    match = re.search(r"\b(\d+)\s*x\s*(\d+)\b", value)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _fetch_ipapi(timeout_seconds: float) -> MachineGeolocation:
    payload = _fetch_json("https://ipapi.co/json/", timeout_seconds)
    if payload.get("error"):
        raise MachineStateError(str(payload.get("reason") or payload.get("error")))
    return MachineGeolocation(
        source="ipapi.co",
        ip_address=_text(payload.get("ip")),
        country=_text(payload.get("country_name")),
        country_code=_text(payload.get("country_code")),
        region=_text(payload.get("region")),
        city=_text(payload.get("city")),
        postal_code=_text(payload.get("postal")),
        latitude=_text(payload.get("latitude")),
        longitude=_text(payload.get("longitude")),
        timezone_name=_text(payload.get("timezone")),
        organization=_text(payload.get("org")),
        asn=_text(payload.get("asn")),
    )


def _fetch_ipwho(timeout_seconds: float) -> MachineGeolocation:
    payload = _fetch_json("https://ipwho.is/", timeout_seconds)
    if payload.get("success") is False:
        raise MachineStateError(str(payload.get("message") or "ipwho.is failed"))
    connection = payload.get("connection")
    if not isinstance(connection, dict):
        connection = {}
    return MachineGeolocation(
        source="ipwho.is",
        ip_address=_text(payload.get("ip")),
        country=_text(payload.get("country")),
        country_code=_text(payload.get("country_code")),
        region=_text(payload.get("region")),
        city=_text(payload.get("city")),
        postal_code=_text(payload.get("postal")),
        latitude=_text(payload.get("latitude")),
        longitude=_text(payload.get("longitude")),
        timezone_name=_timezone_from_ipwho(payload),
        organization=_text(connection.get("org")),
        asn=_text(connection.get("asn")),
    )


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(
        url,
        headers={"User-Agent": "reframe-agent-host/0.1"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(64_000)
    except URLError as error:
        raise MachineStateError(str(error)) from error

    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise MachineStateError(f"unexpected geolocation response from {url}")
    return payload


def _timezone_from_ipwho(payload: dict[str, Any]) -> str | None:
    timezone_payload = payload.get("timezone")
    if isinstance(timezone_payload, dict):
        return _text(timezone_payload.get("id"))
    return _text(timezone_payload)


def _local_timezone_name(now: datetime) -> str:
    tzinfo = now.tzinfo
    if tzinfo is None:
        return "local"
    key = getattr(tzinfo, "key", None)
    if isinstance(key, str) and key:
        return key
    return tzinfo.tzname(now) or "local"


def _utc_offset(now: datetime) -> str:
    offset = now.utcoffset()
    if offset is None:
        return "unknown"
    total_seconds = int(offset.total_seconds())
    sign = "+" if total_seconds >= 0 else "-"
    total_seconds = abs(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes = remainder // 60
    return f"{sign}{hours:02d}:{minutes:02d}"


def _iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
