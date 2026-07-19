use std::collections::HashMap;

use prost_reflect::DescriptorPool;
use reframe_store_protocol::annotations::{
    CAPABILITY_OPTION_FULL_NAME, Capability, Idempotency, STORE_SERVICE_OPTION_FULL_NAME,
    SideEffect, StoreService, capability,
};

#[test]
fn raw_descriptor_bytes_preserve_reference_capability_options() {
    let descriptor = include_bytes!(concat!(env!("OUT_DIR"), "/reference_store_descriptor.bin"));
    let pool = DescriptorPool::decode(descriptor.as_slice()).expect("reference descriptor set");
    let extension = pool
        .get_extension_by_name(CAPABILITY_OPTION_FULL_NAME)
        .expect("canonical capability option");
    let service = pool
        .get_service_by_name("reframe.examples.reference.v1.ReferenceStore")
        .expect("reference service");
    let store_extension = pool
        .get_extension_by_name(STORE_SERVICE_OPTION_FULL_NAME)
        .expect("canonical Store service option");
    let store = service
        .options()
        .get_extension(&store_extension)
        .as_message()
        .expect("Store service message")
        .transcode_to::<StoreService>()
        .expect("typed Store service option");
    assert_eq!(store.store_id, "dev.reframe.reference-store");

    let capabilities = service
        .methods()
        .map(|method| {
            let options = method.options();
            assert!(options.has_extension(&extension));
            let value = options.get_extension(&extension);
            let capability = value
                .as_message()
                .expect("capability message")
                .transcode_to::<Capability>()
                .expect("typed capability option");
            (
                method.name().to_owned(),
                (
                    method.input().full_name().to_owned(),
                    method.output().full_name().to_owned(),
                    capability,
                ),
            )
        })
        .collect::<HashMap<_, _>>();

    assert_eq!(capabilities.len(), 5);

    let (input, output, loopback) = &capabilities["ReadLoopbackSnapshot"];
    assert_eq!(input, "reframe.examples.reference.v1.LoopbackSelector");
    assert_eq!(output, "reframe.examples.reference.v1.LoopbackSnapshot");
    assert_eq!(loopback.id, "reference.http.loopback_snapshot");
    assert!(matches!(
        loopback.kind,
        Some(capability::Kind::Resource(resource)) if !resource.supports_subscriptions
    ));

    let (input, output, http) = &capabilities["ReadHttpSnapshot"];
    assert_eq!(input, "reframe.examples.reference.v1.HttpSnapshotSelector");
    assert_eq!(output, "reframe.examples.reference.v1.HttpSnapshot");
    assert_eq!(http.id, "reference.http.snapshot");
    assert!(matches!(
        http.kind,
        Some(capability::Kind::Resource(resource)) if !resource.supports_subscriptions
    ));

    let (input, output, counter) = &capabilities["ReadCounter"];
    assert_eq!(input, "reframe.examples.reference.v1.CounterSelector");
    assert_eq!(output, "reframe.examples.reference.v1.CounterSample");
    assert_eq!(counter.id, "reference.streams.counter");
    assert!(matches!(
        counter.kind,
        Some(capability::Kind::Resource(resource)) if resource.supports_subscriptions
    ));

    let (input, output, normalize) = &capabilities["NormalizeLabel"];
    assert_eq!(input, "reframe.examples.reference.v1.NormalizeLabelInput");
    assert_eq!(output, "reframe.examples.reference.v1.NormalizeLabelOutput");
    assert_eq!(normalize.id, "reference.text.normalize_label");
    assert!(matches!(
        normalize.kind,
        Some(capability::Kind::Function(function))
            if function.side_effect == SideEffect::None as i32
                && function.idempotency == Idempotency::Idempotent as i32
    ));

    let (input, output, trap) = &capabilities["RunDiagnosticTrap"];
    assert_eq!(input, "reframe.examples.reference.v1.DiagnosticTrapInput");
    assert_eq!(output, "reframe.examples.reference.v1.DiagnosticTrapOutput");
    assert_eq!(trap.id, "reference.diagnostics.trap");
    assert!(matches!(
        trap.kind,
        Some(capability::Kind::Function(function))
            if function.side_effect == SideEffect::None as i32
                && function.idempotency == Idempotency::Idempotent as i32
    ));
}
