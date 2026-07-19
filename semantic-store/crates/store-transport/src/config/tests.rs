use super::*;

#[test]
fn rejects_zero_resource_limits() {
    assert!(TransportConfig::new(0, 1, 1, 1).is_err());
    assert!(TransportConfig::new(1, 0, 1, 1).is_err());
    assert!(TransportConfig::new(1, 1, 0, 1).is_err());
    assert!(TransportConfig::new(1, 1, 1, 0).is_err());
    assert!(
        TransportConfig::new(2, 1, 1, 1)
            .unwrap()
            .with_outbound_byte_budget(1)
            .is_err()
    );
    assert!(
        TransportConfig::new(2, 1, 1, 1)
            .unwrap()
            .with_aggregate_outbound_byte_budget(1)
            .is_err()
    );
    assert!(
        TransportConfig::new(2, 1, 1, 1)
            .unwrap()
            .with_inbound_byte_budget(1)
            .is_err()
    );
    assert!(
        TransportConfig::default()
            .with_write_timeout(Duration::ZERO)
            .is_err()
    );
}

#[test]
fn rejects_counts_above_their_explicit_ceiling() {
    assert!(TransportConfig::new(1, usize::MAX, 1, 1).is_err());
    assert!(TransportConfig::new(1, 1, usize::MAX, 1).is_err());
    assert!(TransportConfig::new(1, 1, 1, usize::MAX).is_err());
    assert!(
        TransportConfig::default()
            .with_outbound_capacity(usize::MAX)
            .is_err()
    );
    assert!(
        TransportConfig::default()
            .with_max_in_flight(usize::MAX)
            .is_err()
    );
    assert!(
        TransportConfig::default()
            .with_max_connections(usize::MAX)
            .is_err()
    );

    let config =
        TransportConfig::new(1, MAX_OUTBOUND_CAPACITY, MAX_IN_FLIGHT, MAX_CONNECTIONS).unwrap();
    assert_eq!(config.outbound_capacity(), MAX_OUTBOUND_CAPACITY);
    assert_eq!(config.max_in_flight(), MAX_IN_FLIGHT);
    assert_eq!(config.max_connections(), MAX_CONNECTIONS);
}

#[test]
fn increasing_frame_size_preserves_a_progress_capable_byte_budget() {
    let config = TransportConfig::default()
        .with_max_frame_size(DEFAULT_MAX_FRAME_SIZE * 2)
        .unwrap();

    assert_eq!(config.outbound_byte_budget(), config.max_frame_size());
    assert!(config.aggregate_outbound_byte_budget() >= config.max_frame_size());
    assert!(config.inbound_byte_budget() >= config.max_frame_size());
}

#[test]
fn hard_frame_limit_and_default_global_admission_are_explicit() {
    assert!(TransportConfig::new(MAX_FRAME_SIZE + 1, 1, 1, 1).is_err());
    assert!(
        TransportConfig::default()
            .with_max_frame_size(MAX_FRAME_SIZE + 1)
            .is_err()
    );
    assert_eq!(
        TransportConfig::default().inbound_byte_budget()
            / TransportConfig::default().max_frame_size(),
        8
    );
    assert_eq!(
        TransportConfig::default().aggregate_outbound_byte_budget()
            / TransportConfig::default().max_frame_size(),
        8
    );
}
