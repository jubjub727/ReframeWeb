use winfsp_wrs_sys::{NTSTATUS, PWSTR};

use super::status;

pub(super) unsafe fn from_wide(raw: PWSTR) -> Result<String, NTSTATUS> {
    normalize(&unsafe { decode_wide(raw) }?)
}

pub(super) unsafe fn optional_component(raw: PWSTR) -> Result<Option<String>, NTSTATUS> {
    if raw.is_null() {
        return Ok(None);
    }
    let value = unsafe { decode_wide(raw) }?;
    validate_marker(&value)?;
    Ok(Some(value))
}

unsafe fn decode_wide(raw: PWSTR) -> Result<String, NTSTATUS> {
    if raw.is_null() {
        return Err(status::INVALID_PARAMETER);
    }
    let mut length = 0usize;
    while unsafe { *raw.add(length) } != 0 {
        length = length.checked_add(1).ok_or(status::INVALID_PARAMETER)?;
        if length > 32_767 {
            return Err(status::INVALID_PARAMETER);
        }
    }
    let wide = unsafe { std::slice::from_raw_parts(raw, length) };
    String::from_utf16(wide).map_err(|_| status::INVALID_PARAMETER)
}

fn validate_marker(value: &str) -> Result<(), NTSTATUS> {
    if value.contains(['/', '\\', ':']) {
        return Err(status::INVALID_PARAMETER);
    }
    Ok(())
}

fn normalize(value: &str) -> Result<String, NTSTATUS> {
    let value = value.trim_start_matches(['\\', '/']).replace('\\', "/");
    if value.is_empty() {
        return Ok(String::new());
    }
    if value.contains(':')
        || value
            .split('/')
            .any(|component| component.is_empty() || component == "." || component == "..")
    {
        return Err(status::INVALID_PARAMETER);
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::{normalize, validate_marker};

    #[test]
    fn normalizes_winfsp_names() {
        assert_eq!(normalize("\\src\\lib.rs").unwrap(), "src/lib.rs");
        assert_eq!(normalize("\\").unwrap(), "");
        assert!(normalize("\\..\\secret").is_err());
    }

    #[test]
    fn directory_markers_allow_synthetic_dot_entries_only_as_components() {
        assert!(validate_marker(".").is_ok());
        assert!(validate_marker("..").is_ok());
        assert!(validate_marker("child.txt").is_ok());
        assert!(validate_marker("nested/child").is_err());
        assert!(validate_marker("C:escape").is_err());
    }
}
