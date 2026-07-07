from __future__ import annotations

from dataclasses import dataclass


PREFERRED_HOST_APIS = (
    "Windows WASAPI",
    "Core Audio",
    "ALSA",
    "PulseAudio",
    "JACK Audio Connection Kit",
    "Windows DirectSound",
    "MME",
    "Windows WDM-KS",
)


@dataclass(frozen=True)
class AudioDeviceInfo:
    index: int
    name: str
    host_api_name: str
    max_input_channels: int
    default_sample_rate: float
    is_default_input: bool


def list_input_devices() -> list[AudioDeviceInfo]:
    import sounddevice as sd

    devices = sd.query_devices()
    hostapis = sd.query_hostapis()
    default_input = sd.default.device[0]
    results: list[AudioDeviceInfo] = []

    for index, device in enumerate(devices):
        input_channels = int(device.get("max_input_channels", 0))
        if input_channels <= 0:
            continue

        hostapi = hostapis[int(device.get("hostapi", 0))]
        results.append(
            AudioDeviceInfo(
                index=index,
                name=str(device.get("name", f"Device {index}")),
                host_api_name=str(hostapi.get("name", "Unknown")),
                max_input_channels=input_channels,
                default_sample_rate=float(device.get("default_samplerate", 0.0)),
                is_default_input=index == default_input,
            )
        )

    return results


def resolve_input_device(device: int | str | None) -> int | str | None:
    return resolve_input_devices(device)[0]


def resolve_input_devices(device: int | str | None) -> tuple[int | str | None, ...]:
    devices = list_input_devices()
    if device is None:
        default = next((item for item in devices if item.is_default_input), None)
        if default is None:
            return (None,)
        return _device_indexes(_preferred_duplicates(default, devices))

    if isinstance(device, int):
        selected = next((item for item in devices if item.index == device), None)
        if selected is None:
            return (device,)
        return _device_indexes(_preferred_duplicates(selected, devices))

    matched = [
        item
        for item in devices
        if device.casefold() in item.name.casefold()
        or device.casefold() in item.host_api_name.casefold()
    ]
    if not matched:
        return (device,)
    return _device_indexes(_preferred_devices(matched))


def device_default_sample_rate(device: int | str | None) -> int:
    import sounddevice as sd

    info = sd.query_devices(device=device, kind="input")
    return int(round(float(info.get("default_samplerate", 16_000))))


def device_input_channels(device: int | str | None) -> int:
    import sounddevice as sd

    info = sd.query_devices(device=device, kind="input")
    return int(info.get("max_input_channels", 1))


def device_summary(device: int | str | None) -> str:
    info = _device_info(device)
    if info is None:
        return str(device or "default")
    return (
        f"{info.index} {info.name} via {info.host_api_name} "
        f"at {info.default_sample_rate:.0f} Hz"
    )


def _preferred_duplicate(
    selected: AudioDeviceInfo | None,
    devices: list[AudioDeviceInfo],
) -> AudioDeviceInfo:
    return _preferred_duplicates(selected, devices)[0]


def _preferred_duplicates(
    selected: AudioDeviceInfo | None,
    devices: list[AudioDeviceInfo],
) -> tuple[AudioDeviceInfo, ...]:
    if selected is None:
        raise ValueError("Input device was not found.")
    same_name = [item for item in devices if item.name == selected.name]
    return _preferred_devices(same_name)


def _preferred_device(devices: list[AudioDeviceInfo]) -> AudioDeviceInfo:
    return _preferred_devices(devices)[0]


def _preferred_devices(devices: list[AudioDeviceInfo]) -> tuple[AudioDeviceInfo, ...]:
    if not devices:
        raise ValueError("No input device candidates were found.")
    return tuple(sorted(devices, key=_device_rank))


def _device_rank(device: AudioDeviceInfo) -> tuple[int, int]:
    try:
        host_rank = PREFERRED_HOST_APIS.index(device.host_api_name)
    except ValueError:
        host_rank = len(PREFERRED_HOST_APIS)
    return (host_rank, device.index)


def _device_info(device: int | str | None) -> AudioDeviceInfo | None:
    if not isinstance(device, int):
        return None
    return next((item for item in list_input_devices() if item.index == device), None)


def _device_indexes(devices: tuple[AudioDeviceInfo, ...]) -> tuple[int, ...]:
    return tuple(device.index for device in devices)
