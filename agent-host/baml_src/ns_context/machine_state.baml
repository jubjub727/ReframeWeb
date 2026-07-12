class MachineMonitorContext {
    horizontal_resolution: int,
    vertical_resolution: int,
}

class MachineStateContext {
    captured_at_utc: string,
    current_local_time: string,
    current_utc_time: string,
    timezone_name: string,
    utc_offset: string,
    os_architecture: string,
    monitor_count: int,
    monitors: MachineMonitorContext[],
    geolocation_status: string,
    geolocation_source: string?,
    ip_address: string?,
    country: string?,
    country_code: string?,
    region: string?,
    city: string?,
    postal_code: string?,
    latitude: string?,
    longitude: string?,
    geolocation_timezone: string?,
    organization: string?,
    asn: string?,
    geolocation_error: string?,
}
