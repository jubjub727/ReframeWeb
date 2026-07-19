use prost_reflect::DescriptorPool;
use prost_types::{
    DescriptorProto, FieldDescriptorProto, FileDescriptorProto, FileDescriptorSet,
    field_descriptor_proto::{Label, Type},
};

use crate::{
    budget::ProjectionBudget, field_selection::Selection, type_projection::project_message,
};

#[test]
fn wide_shared_graph_stops_before_quadratic_expansion() {
    const WIDTH: usize = 128;
    const WORK_BUDGET: usize = 64 * 1024;

    let pool = shared_wide_pool(WIDTH);
    let root = pool
        .get_message_by_name("stress.Root")
        .expect("root descriptor");
    let mut budget = ProjectionBudget::new(WORK_BUDGET);
    let view = project_message(&root, &Selection::All, 2, &mut budget);

    // Breadth is retained before any one shared child is expanded. Without a
    // construction budget this graph would allocate WIDTH squared leaf fields.
    assert_eq!(view.fields.len(), WIDTH);
    assert!(view.truncated);
    assert!(budget.exhausted());
    assert!(
        view.fields
            .iter()
            .filter(|field| field.nested.is_some())
            .count()
            < WIDTH / 4
    );
    let fully_expanded_fields = WIDTH + WIDTH * WIDTH;
    assert!(projected_field_count(&view) < fully_expanded_fields / 8);
}

fn shared_wide_pool(width: usize) -> DescriptorPool {
    let leaf = DescriptorProto {
        name: Some("Leaf".to_owned()),
        field: (1..=width)
            .map(|number| scalar_field(&format!("value_{number}"), number))
            .collect(),
        ..Default::default()
    };
    let root = DescriptorProto {
        name: Some("Root".to_owned()),
        field: (1..=width)
            .map(|number| FieldDescriptorProto {
                name: Some(format!("branch_{number}")),
                number: Some(i32::try_from(number).expect("small field number")),
                label: Some(Label::Optional as i32),
                r#type: Some(Type::Message as i32),
                type_name: Some(".stress.Leaf".to_owned()),
                ..Default::default()
            })
            .collect(),
        ..Default::default()
    };
    DescriptorPool::from_file_descriptor_set(FileDescriptorSet {
        file: vec![FileDescriptorProto {
            name: Some("stress.proto".to_owned()),
            package: Some("stress".to_owned()),
            syntax: Some("proto3".to_owned()),
            message_type: vec![leaf, root],
            ..Default::default()
        }],
    })
    .expect("valid descriptor graph")
}

fn scalar_field(name: &str, number: usize) -> FieldDescriptorProto {
    FieldDescriptorProto {
        name: Some(name.to_owned()),
        number: Some(i32::try_from(number).expect("small field number")),
        label: Some(Label::Optional as i32),
        r#type: Some(Type::String as i32),
        ..Default::default()
    }
}

fn projected_field_count(view: &reframe_store_protocol::wire::TypeView) -> usize {
    view.fields
        .iter()
        .map(|field| 1 + field.nested.as_ref().map_or(0, projected_field_count))
        .sum()
}
