use super::*;

pub unsafe extern "system" fn start_enumeration(
    data: *const PRJ_CALLBACK_DATA,
    id: *const GUID,
) -> HRESULT {
    guard("start_directory_enumeration", || {
        let runtime = runtime(data)?;
        runtime.enumerations.lock().map_err(|_| E_FAIL)?.insert(
            unsafe { *id },
            Enumeration {
                entries: Vec::new(),
                next: 0,
                expression: String::new(),
            },
        );
        Ok(())
    })
}

pub unsafe extern "system" fn end_enumeration(
    data: *const PRJ_CALLBACK_DATA,
    id: *const GUID,
) -> HRESULT {
    guard("end_directory_enumeration", || {
        runtime(data)?
            .enumerations
            .lock()
            .map_err(|_| E_FAIL)?
            .remove(&unsafe { *id });
        Ok(())
    })
}

pub unsafe extern "system" fn get_enumeration(
    data: *const PRJ_CALLBACK_DATA,
    id: *const GUID,
    expression: PCWSTR,
    buffer: PRJ_DIR_ENTRY_BUFFER_HANDLE,
) -> HRESULT {
    guard("get_directory_enumeration", || {
        let runtime = runtime(data)?;
        let callback = unsafe { &*data };
        let directory = wide(callback.FilePathName)?;
        let expression = wide(expression).unwrap_or_default();
        let expression = if expression.is_empty() {
            "*".into()
        } else {
            expression
        };
        let mut states = runtime.enumerations.lock().map_err(|_| E_FAIL)?;
        let state = states.get_mut(&unsafe { *id }).ok_or(E_INVALIDARG)?;
        if state.entries.is_empty() || callback.Flags.0 & PRJ_CB_DATA_FLAG_ENUM_RESTART_SCAN.0 != 0
        {
            state.entries = runtime.entries(&directory);
            state
                .entries
                .retain(|entry| matches_name(&entry.name, &expression));
            state
                .entries
                .sort_by(|left, right| compare_name(&left.name, &right.name));
            state.next = 0;
            state.expression = expression;
        }
        let mut wrote = false;
        while let Some(entry) = state.entries.get(state.next) {
            let name = wide_null(&entry.name);
            let info = basic_info(entry.is_directory, entry.size);
            match unsafe {
                PrjFillDirEntryBuffer(PCWSTR::from_raw(name.as_ptr()), Some(&info), buffer)
            } {
                Ok(()) => {
                    state.next += 1;
                    wrote = true;
                }
                Err(error) if error.code() == HRESULT::from_win32(ERROR_INSUFFICIENT_BUFFER.0) => {
                    if wrote {
                        return Ok(());
                    }
                    return Err(error.code());
                }
                Err(error) => return Err(error.code()),
            }
            if callback.Flags.0 & PRJ_CB_DATA_FLAG_ENUM_RETURN_SINGLE_ENTRY.0 != 0 {
                break;
            }
        }
        Ok(())
    })
}
