use prost_reflect::{DescriptorPool, Kind};
use reframe_store_protocol::{
    annotation_proto_include_dir,
    annotations::{
        CAPABILITY_OPTION_FULL_NAME, CAPABILITY_OPTION_NUMBER, PROTO_IMPORT,
        STORE_SERVICE_OPTION_FULL_NAME, STORE_SERVICE_OPTION_NUMBER,
    },
    descriptor_set_bytes,
};

#[test]
fn canonical_annotation_asset_and_descriptor_agree() {
    let source = annotation_proto_include_dir().join(PROTO_IMPORT);
    assert!(
        source.is_file(),
        "annotation source is missing: {}",
        source.display()
    );

    let pool = DescriptorPool::decode(descriptor_set_bytes()).expect("protocol descriptor set");
    let extension = pool
        .get_extension_by_name(CAPABILITY_OPTION_FULL_NAME)
        .expect("capability method option");
    assert_eq!(extension.number(), CAPABILITY_OPTION_NUMBER);
    assert_eq!(
        extension.containing_message().full_name(),
        "google.protobuf.MethodOptions"
    );
    assert!(matches!(
        extension.kind(),
        Kind::Message(message)
            if message.full_name() == "reframe.semantic_store.options.v1.Capability"
    ));

    let service_extension = pool
        .get_extension_by_name(STORE_SERVICE_OPTION_FULL_NAME)
        .expect("Store service option");
    assert_eq!(service_extension.number(), STORE_SERVICE_OPTION_NUMBER);
    assert_eq!(
        service_extension.containing_message().full_name(),
        "google.protobuf.ServiceOptions"
    );
    assert!(matches!(
        service_extension.kind(),
        Kind::Message(message)
            if message.full_name() == "reframe.semantic_store.options.v1.StoreService"
    ));
}
