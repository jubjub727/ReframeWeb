from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


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


def fetch_ip_geolocation(
    *,
    max_attempts: int = DEFAULT_GEOLOCATION_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_GEOLOCATION_RETRY_DELAY_SECONDS,
    timeout_seconds: float = DEFAULT_GEOLOCATION_TIMEOUT_SECONDS,
) -> MachineGeolocation:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        for endpoint in (_fetch_ipapi, _fetch_ipwho):
            try:
                return endpoint(timeout_seconds)
            except Exception as error:
                last_error = error
        if attempt < max_attempts:
            time.sleep(retry_delay_seconds)
    detail = str(last_error) if last_error is not None else "unknown error"
    raise MachineStateError(
        f"IP geolocation failed after {max_attempts} attempts: {detail}"
    )


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
    timezone = payload.get("timezone")
    timezone_name = (
        _text(timezone.get("id")) if isinstance(timezone, dict) else _text(timezone)
    )
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
        timezone_name=timezone_name,
        organization=_text(connection.get("org")),
        asn=_text(connection.get("asn")),
    )


def _fetch_json(url: str, timeout_seconds: float) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "reframe-agent-host/0.1"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read(64_000)
    except URLError as error:
        raise MachineStateError(str(error)) from error
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise MachineStateError(f"unexpected geolocation response from {url}")
    return payload


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
