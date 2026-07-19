use std::collections::BTreeMap;

use prost_types::{
    DescriptorProto, EnumDescriptorProto, FileDescriptorSet, ServiceDescriptorProto,
};

pub(super) struct SchemaIndex<'a> {
    pub(super) messages: BTreeMap<String, &'a DescriptorProto>,
    pub(super) enums: BTreeMap<String, &'a EnumDescriptorProto>,
    pub(super) services: BTreeMap<String, &'a ServiceDescriptorProto>,
}

impl<'a> SchemaIndex<'a> {
    pub(super) fn new(set: &'a FileDescriptorSet) -> Self {
        let mut index = Self {
            messages: BTreeMap::new(),
            enums: BTreeMap::new(),
            services: BTreeMap::new(),
        };
        for file in &set.file {
            let package = file.package.as_deref().unwrap_or_default();
            for message in &file.message_type {
                index.insert_message(package, message);
            }
            for enumeration in &file.enum_type {
                index.enums.insert(
                    qualified(package, enumeration.name.as_deref().unwrap_or_default()),
                    enumeration,
                );
            }
            for service in &file.service {
                index.services.insert(
                    qualified(package, service.name.as_deref().unwrap_or_default()),
                    service,
                );
            }
        }
        index
    }

    fn insert_message(&mut self, prefix: &str, message: &'a DescriptorProto) {
        let name = qualified(prefix, message.name.as_deref().unwrap_or_default());
        self.messages.insert(name.clone(), message);
        for nested in &message.nested_type {
            self.insert_message(&name, nested);
        }
        for enumeration in &message.enum_type {
            self.enums.insert(
                qualified(&name, enumeration.name.as_deref().unwrap_or_default()),
                enumeration,
            );
        }
    }
}

fn qualified(prefix: &str, name: &str) -> String {
    if prefix.is_empty() {
        name.to_owned()
    } else {
        format!("{prefix}.{name}")
    }
}
