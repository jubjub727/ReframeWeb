from __future__ import annotations

from datetime import datetime


def cutoff_age(current_timestamp: str, cutoff_timestamp: str) -> dict[str, object]:
    current = parse_timestamp(current_timestamp)
    cutoff = parse_timestamp(cutoff_timestamp)
    seconds = int(round((current - cutoff).total_seconds()))
    return {
        "seconds": seconds,
        "display": format_duration(seconds),
    }


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def format_duration(seconds: int | float) -> str:
    rounded = int(round(abs(seconds)))
    if rounded < 60:
        return _unit(rounded, "second")

    minutes = rounded // 60
    days, remaining_minutes = divmod(minutes, 24 * 60)
    hours, mins = divmod(remaining_minutes, 60)

    parts = []
    if days:
        parts.append(_unit(days, "day"))
    if hours:
        parts.append(_unit(hours, "hour"))
    if mins:
        parts.append(_unit(mins, "minute"))

    if not parts:
        parts.append("0 minutes")
    return _join_parts(parts)


def _unit(value: int, name: str) -> str:
    suffix = "" if value == 1 else "s"
    return f"{value} {name}{suffix}"


def _join_parts(parts: list[str]) -> str:
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} and {parts[1]}"
    return " ".join(parts[:-1]) + f" and {parts[-1]}"
