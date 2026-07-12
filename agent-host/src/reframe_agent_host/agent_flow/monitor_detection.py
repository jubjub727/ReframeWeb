from __future__ import annotations

from dataclasses import dataclass
import json
import platform
import re
import subprocess
from typing import Any


@dataclass(frozen=True)
class MachineMonitor:
    horizontal_resolution: int
    vertical_resolution: int


@dataclass(frozen=True)
class MonitorGeometry:
    x: int
    y: int
    width: int
    height: int


def machine_monitors() -> list[MachineMonitor]:
    return [
        MachineMonitor(item.width, item.height)
        for item in _dedupe_monitor_geometries(_detect_monitor_geometries())
    ]


def _detect_monitor_geometries() -> list[MonitorGeometry]:
    from reframe_agent_host.agent_flow.windows_monitors import (
        windows_monitor_geometries,
    )

    detectors = (
        _screeninfo_monitor_geometries,
        windows_monitor_geometries,
        _macos_monitor_geometries,
        _swaymsg_monitor_geometries,
        _xrandr_list_monitor_geometries,
        _xrandr_monitor_geometries,
        _tkinter_monitor_geometry,
    )
    for detector in detectors:
        try:
            geometries = detector()
        except Exception:
            continue
        if geometries:
            return geometries
    return []


def _dedupe_monitor_geometries(
    geometries: list[MonitorGeometry],
) -> list[MonitorGeometry]:
    monitors = []
    seen = set()
    for item in geometries:
        key = (item.x, item.y, item.width, item.height)
        if item.width > 0 and item.height > 0 and key not in seen:
            seen.add(key)
            monitors.append(item)
    return monitors


def _screeninfo_monitor_geometries() -> list[MonitorGeometry]:
    try:
        from screeninfo import get_monitors  # type: ignore[import-not-found]
    except ImportError:
        return []
    return [
        MonitorGeometry(
            x=int(item.x),
            y=int(item.y),
            width=int(item.width),
            height=int(item.height),
        )
        for item in get_monitors()
    ]


def _macos_monitor_geometries() -> list[MonitorGeometry]:
    if platform.system() != "Darwin":
        return []
    try:
        from AppKit import NSScreen  # type: ignore[import-not-found]
    except ImportError:
        return _macos_system_profiler_monitors()
    monitors = []
    for screen in NSScreen.screens():
        frame = screen.frame()
        scale = float(screen.backingScaleFactor())
        monitors.append(
            MonitorGeometry(
                x=int(frame.origin.x * scale),
                y=int(frame.origin.y * scale),
                width=int(frame.size.width * scale),
                height=int(frame.size.height * scale),
            )
        )
    return monitors


def _macos_system_profiler_monitors() -> list[MonitorGeometry]:
    payload = json.loads(
        _run_monitor_command(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            timeout_seconds=3.0,
        )
    )
    displays = payload.get("SPDisplaysDataType")
    if not isinstance(displays, list):
        return []
    monitors = []
    for display in displays:
        drivers = display.get("spdisplays_ndrvs") if isinstance(display, dict) else None
        if not isinstance(drivers, list):
            continue
        for driver in drivers:
            value = driver.get("_spdisplays_resolution") if isinstance(driver, dict) else None
            parsed = _parse_resolution(str(value or ""))
            if parsed is not None:
                monitors.append(MonitorGeometry(0, 0, *parsed))
    return monitors


def _xrandr_monitor_geometries() -> list[MonitorGeometry]:
    if not _x11_platform():
        return []
    output = _run_monitor_command(["xrandr", "--query"], timeout_seconds=1.0)
    pattern = re.compile(r"\b(\d+)x(\d+)\+(-?\d+)\+(-?\d+)")
    monitors = []
    for line in output.splitlines():
        match = pattern.search(line) if " connected" in line else None
        if match:
            width, height, x, y = (int(value) for value in match.groups())
            monitors.append(MonitorGeometry(x, y, width, height))
    return monitors


def _swaymsg_monitor_geometries() -> list[MonitorGeometry]:
    if not _x11_platform():
        return []
    payload = json.loads(
        _run_monitor_command(
            ["swaymsg", "-t", "get_outputs", "--raw"], timeout_seconds=1.0
        )
    )
    if not isinstance(payload, list):
        return []
    monitors = []
    for output in payload:
        if not isinstance(output, dict) or output.get("active") is False:
            continue
        rect = output.get("rect")
        if not isinstance(rect, dict):
            continue
        width, height = _int_value(rect.get("width")), _int_value(rect.get("height"))
        if width is not None and height is not None:
            monitors.append(
                MonitorGeometry(
                    _int_value(rect.get("x")) or 0,
                    _int_value(rect.get("y")) or 0,
                    width,
                    height,
                )
            )
    return monitors


def _xrandr_list_monitor_geometries() -> list[MonitorGeometry]:
    if not _x11_platform():
        return []
    output = _run_monitor_command(["xrandr", "--listmonitors"], timeout_seconds=1.0)
    pattern = re.compile(r"\s\d+:\s+\S+\s+(\d+)/\d+x(\d+)/\d+\+(-?\d+)\+(-?\d+)")
    monitors = []
    for line in output.splitlines():
        match = pattern.search(line)
        if match:
            width, height, x, y = (int(value) for value in match.groups())
            monitors.append(MonitorGeometry(x, y, width, height))
    return monitors


def _tkinter_monitor_geometry() -> list[MonitorGeometry]:
    import tkinter

    root = tkinter.Tk()
    try:
        root.withdraw()
        return [MonitorGeometry(0, 0, root.winfo_screenwidth(), root.winfo_screenheight())]
    finally:
        root.destroy()


def _run_monitor_command(command: list[str], *, timeout_seconds: float) -> str:
    return subprocess.run(
        command,
        capture_output=True,
        check=True,
        text=True,
        timeout=timeout_seconds,
    ).stdout


def _parse_resolution(value: str) -> tuple[int, int] | None:
    match = re.search(r"\b(\d+)\s*x\s*(\d+)\b", value)
    return (int(match.group(1)), int(match.group(2))) if match else None


def _x11_platform() -> bool:
    return platform.system() in {"Linux", "FreeBSD", "OpenBSD"}


def _int_value(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
