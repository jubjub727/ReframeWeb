use prost_types::{
    DescriptorProto, EnumDescriptorProto, EnumValueDescriptorProto, FieldDescriptorProto,
    FileDescriptorProto, FileDescriptorSet, MethodDescriptorProto, ServiceDescriptorProto,
    field_descriptor_proto::{Label, Type},
};

pub(super) fn schema(
    messages: Vec<DescriptorProto>,
    enums: Vec<EnumDescriptorProto>,
    services: Vec<ServiceDescriptorProto>,
) -> FileDescriptorSet {
    FileDescriptorSet {
        file: vec![FileDescriptorProto {
            name: Some("compat.proto".to_owned()),
            package: Some("compat".to_owned()),
            message_type: messages,
            enum_type: enums,
            service: services,
            syntax: Some("proto3".to_owned()),
            ..FileDescriptorProto::default()
        }],
    }
}

pub(super) fn message(
    name: &str,
    fields: impl IntoIterator<Item = FieldDescriptorProto>,
) -> DescriptorProto {
    DescriptorProto {
        name: Some(name.to_owned()),
        field: fields.into_iter().collect(),
        ..DescriptorProto::default()
    }
}

pub(super) fn field(
    name: &str,
    number: i32,
    field_type: Type,
    label: Label,
) -> FieldDescriptorProto {
    FieldDescriptorProto {
        name: Some(name.to_owned()),
        number: Some(number),
        label: Some(label as i32),
        r#type: Some(field_type as i32),
        ..FieldDescriptorProto::default()
    }
}

pub(super) fn enumeration(
    name: &str,
    values: impl IntoIterator<Item = (&'static str, i32)>,
) -> EnumDescriptorProto {
    EnumDescriptorProto {
        name: Some(name.to_owned()),
        value: values
            .into_iter()
            .map(|(name, number)| EnumValueDescriptorProto {
                name: Some(name.to_owned()),
                number: Some(number),
                ..EnumValueDescriptorProto::default()
            })
            .collect(),
        ..EnumDescriptorProto::default()
    }
}

pub(super) fn service(
    name: &str,
    methods: impl IntoIterator<Item = MethodDescriptorProto>,
) -> ServiceDescriptorProto {
    ServiceDescriptorProto {
        name: Some(name.to_owned()),
        method: methods.into_iter().collect(),
        ..ServiceDescriptorProto::default()
    }
}

pub(super) fn method(name: &str, input: &str, output: &str) -> MethodDescriptorProto {
    MethodDescriptorProto {
        name: Some(name.to_owned()),
        input_type: Some(input.to_owned()),
        output_type: Some(output.to_owned()),
        ..MethodDescriptorProto::default()
    }
}
