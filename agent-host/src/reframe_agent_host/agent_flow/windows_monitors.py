from __future__ import annotations

import platform

from reframe_agent_host.agent_flow.monitor_detection import MonitorGeometry


def windows_monitor_geometries() -> list[MonitorGeometry]:
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

    _set_dpi_awareness(ctypes)
    monitors = []
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
        resolution = _display_settings_resolution(device_name, ctypes)
        monitors.append(monitor_geometry_from_rect(rect, resolution))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(
        None, None, callback_type(callback), 0
    )
    return monitors


def monitor_geometry_from_rect(
    rect,
    resolution: tuple[int, int] | None,
) -> MonitorGeometry:
    width, height = int(rect.right - rect.left), int(rect.bottom - rect.top)
    if resolution is not None:
        width, height = resolution
    return MonitorGeometry(int(rect.left), int(rect.top), width, height)


def _set_dpi_awareness(ctypes_module) -> None:
    setters = (
        lambda: ctypes_module.windll.user32.SetProcessDpiAwarenessContext(
            ctypes_module.c_void_p(-4)
        ),
        lambda: ctypes_module.windll.shcore.SetProcessDpiAwareness(2),
        lambda: ctypes_module.windll.user32.SetProcessDPIAware(),
    )
    for setter in setters:
        try:
            setter()
            return
        except Exception:
            continue


def _display_settings_resolution(device_name: str, ctypes_module):
    if not device_name:
        return None

    class PointL(ctypes_module.Structure):
        _fields_ = (("x", ctypes_module.c_long), ("y", ctypes_module.c_long))

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
    if not ctypes_module.windll.user32.EnumDisplaySettingsW(
        device_name, -1, ctypes_module.byref(mode)
    ):
        return None
    width, height = int(mode.dmPelsWidth), int(mode.dmPelsHeight)
    return (width, height) if width > 0 and height > 0 else None
