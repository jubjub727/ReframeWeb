use std::collections::BTreeMap;

use prost_reflect::{Kind, MessageDescriptor};

use crate::CatalogError;

#[derive(Debug, Default)]
pub(crate) enum Selection {
    #[default]
    All,
    Fields(BTreeMap<String, Selection>),
}

impl Selection {
    pub(crate) const fn is_all(&self) -> bool {
        matches!(self, Self::All)
    }
}

pub(crate) fn selected_field<'a>(
    selection: &'a Selection,
    field_name: &str,
) -> Option<&'a Selection> {
    match selection {
        Selection::All => Some(selection),
        Selection::Fields(fields) => fields.get(field_name),
    }
}

pub(crate) fn build_selection(
    root: &MessageDescriptor,
    paths: &[String],
    requested_type_name: &str,
) -> Result<Selection, CatalogError> {
    let mut selection = Selection::Fields(BTreeMap::new());
    for path in paths {
        validate_path(root, path, requested_type_name)?;
        insert_path(&mut selection, &mut path.split('.'));
    }
    Ok(selection)
}

fn validate_path(
    root: &MessageDescriptor,
    path: &str,
    requested_type_name: &str,
) -> Result<(), CatalogError> {
    if path.is_empty() || path.split('.').any(str::is_empty) {
        return Err(invalid_path(requested_type_name, path));
    }
    let segments = path.split('.').collect::<Vec<_>>();
    let mut message = root.clone();
    for (index, segment) in segments.iter().enumerate() {
        let Some(field) = message.get_field_by_name(segment) else {
            return Err(invalid_path(requested_type_name, path));
        };
        if index + 1 < segments.len() {
            let Kind::Message(nested) = field.kind() else {
                return Err(invalid_path(requested_type_name, path));
            };
            message = nested;
        }
    }
    Ok(())
}

fn insert_path<'a>(selection: &mut Selection, segments: &mut impl Iterator<Item = &'a str>) {
    let Some(segment) = segments.next() else {
        *selection = Selection::All;
        return;
    };
    let Selection::Fields(fields) = selection else {
        return;
    };
    let child = fields
        .entry(segment.to_owned())
        .or_insert_with(|| Selection::Fields(BTreeMap::new()));
    insert_path(child, segments);
}

fn invalid_path(type_name: &str, field_path: &str) -> CatalogError {
    CatalogError::InvalidFieldPath {
        type_name: type_name.to_owned(),
        field_path: field_path.to_owned(),
    }
}
