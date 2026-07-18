fn runtime<'a>(data: *const PRJ_CALLBACK_DATA) -> Result<&'a Runtime, HRESULT> {
    if data.is_null() {
        return Err(E_INVALIDARG);
    }
    let context = unsafe { (*data).InstanceContext.cast::<Runtime>() };
    if context.is_null() {
        return Err(E_INVALIDARG);
    }
    Ok(unsafe { &*context })
}

fn guard(label: &str, operation: impl FnOnce() -> Result<(), HRESULT>) -> HRESULT {
    match catch_unwind(AssertUnwindSafe(operation)) {
        Ok(Ok(())) => S_OK,
        Ok(Err(code)) => {
            if code != HRESULT::from_win32(ERROR_FILE_NOT_FOUND.0) {
                eprintln!("[projfs] {label} failed: {code:?}");
            }
            code
        }
        Err(_) => {
            eprintln!("[projfs] {label} panicked");
            E_FAIL
        }
    }
}

fn wide(value: PCWSTR) -> Result<String, HRESULT> {
    if value.is_null() {
        return Ok(String::new());
    }
    unsafe { value.to_string() }
        .map(|value| value.replace('\\', "/"))
        .map_err(|_| E_INVALIDARG)
}

fn wide_null(value: &str) -> Vec<u16> {
    value.encode_utf16().chain([0]).collect()
}

fn matches_name(name: &str, expression: &str) -> bool {
    let name = wide_null(name);
    let expression = wide_null(expression);
    unsafe {
        PrjFileNameMatch(
            PCWSTR::from_raw(name.as_ptr()),
            PCWSTR::from_raw(expression.as_ptr()),
        )
    }
}

fn compare_name(left: &str, right: &str) -> std::cmp::Ordering {
    let left = wide_null(left);
    let right = wide_null(right);
    unsafe {
        PrjFileNameCompare(
            PCWSTR::from_raw(left.as_ptr()),
            PCWSTR::from_raw(right.as_ptr()),
        )
    }
    .cmp(&0)
}

fn basic_info(is_directory: bool, size: u64) -> PRJ_FILE_BASIC_INFO {
    PRJ_FILE_BASIC_INFO {
        IsDirectory: is_directory,
        FileSize: size as i64,
        // FILE_ATTRIBUTE_TEMPORARY asks the Windows cache manager to keep
        // projected bytes in memory and avoid mass-storage writeback.
        FileAttributes: if is_directory { 0x10 } else { 0x80 | 0x100 },
        ..Default::default()
    }
}

const _: () = assert!(size_of::<usize>() >= 4);
